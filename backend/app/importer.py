import argparse
import json
import logging
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from .db import CardRecord, Meta, Session, init_db
from .settings import ROOT, settings

log = logging.getLogger(__name__)

def import_data(source: Path, force=False):
    init_db()
    source=Path(source).resolve()
    prepared=source if source.suffix=='.sqlite3' else source/'catalog.fr.sqlite3'
    if prepared.exists(): return import_prepared(prepared,force)
    with Session() as db:
        if db.get(Meta, 'import') and not force:
            return json.loads(db.get(Meta, 'import').value)
    source = source.resolve()
    if (source / 'cards-database/data').exists(): source = source / 'cards-database'
    if not source.exists() or not any(source.rglob('*.ts')):
        raise ValueError(f'Aucun fichier TCGdex dans {source}. Copiez le dépôt officiel dans data/.')
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp) / 'cards.json'
        subprocess.run(['node', str(ROOT / 'scripts/parse-tcgdex.mjs'), str(source), str(out)], check=True, cwd=ROOT)
        raw = json.loads(out.read_text(encoding='utf-8'))
    translations = {}
    for p in (source / 'meta/translations/fr.json', source.parent / 'meta/translations/fr.json', ROOT / 'config/tcgdex-fr.json'):
        if p.exists():
            translations = json.loads(p.read_text(encoding='utf-8')); break
    def tr(group, v):
        return translations.get(group, {}).get(v, v) if v else None
    def localized(v):
        return v.get('fr') if isinstance(v, dict) else v
    dates = sorted({d for c in raw['cards'] if (d := localized(c.get('set', {}).get('releaseDate')))})
    chronology = {d: i for i, d in enumerate(dates)}
    # Some French printings are stored in a different folder but import the same set.
    # Merge translations only after verifying every solving attribute matches.
    merged = {}; duplicate_count = 0
    for c in raw['cards']:
        key = (c.get('set',{}).get('id'), c['localId'])
        if key in merged:
            previous = merged[key]
            for field in ('hp','types','dexId','stage','rarity','illustrator','category'):
                if previous.get(field) != c.get(field):
                    raise ValueError(f'Doublon contradictoire {key}: {field}. Base préservée.')
            for lang, name in c.get('name',{}).items():
                if lang in previous['name'] and previous['name'][lang] != name:
                    raise ValueError(f'Traduction contradictoire {key}: {lang}')
                previous['name'][lang] = name
            duplicate_count += 1
        else:
            merged[key] = c
    cards = {}; missing_fr = 0
    for c in merged.values():
        s = c.get('set') or {}; series = s.get('serie') or {}
        sid = s.get('id'); number = c.get('localId'); name = localized(c.get('name'))
        if not sid or not number:
            raw['invalid'].append({'file':c.get('source'), 'error':'Identifiant extension ou collection absent'}); continue
        if not name:
            missing_fr += 1
        release = localized(s.get('releaseDate'))
        if release:
            try: date.fromisoformat(release)
            except ValueError: release = None
        dex = c.get('dexId') or []
        card = dict(id=f'{sid}-{number}', name=name, names=c.get('name', {}), pokedex=dex,
                    types=c.get('types') or [], type_labels=[tr('types', v) for v in c.get('types') or []],
                    stage=c.get('stage'), stage_label=tr('stage',c.get('stage')), hp=c.get('hp'),
                    rarity=c.get('rarity'), rarity_label=tr('rarity',c.get('rarity')), set_id=sid,
                    set_name=localized(s.get('name')), series_id=series.get('id'),
                    series_name=localized(series.get('name')), release_date=release,
                    chronology=chronology.get(release), illustrator=c.get('illustrator'),
                    number=number, category=c.get('category'), image_url=f'/api/images/{sid}-{number}' if name and series.get('id') else None,
                    image_path=f'fr/{series.get("id")}/{sid}/{number}' if name and series.get('id') else None,
                    source=c.get('source'), variants=c.get('variants'), active=True)
        if card['id'] in cards and cards[card['id']] != card:
            raise ValueError(f'Identifiant en doublon : {card["id"]}. Import annulé sans modifier la base.')
        cards[card['id']] = card
    if not cards:
        raise ValueError('Aucune carte valide : base existante préservée.')
    report = dict(total=len(cards), pokemon=sum(c['category']=='Pokemon' for c in cards.values()),
                  missing_french=missing_fr, invalid=raw['invalid'], metadata=raw['skipped'],
                  sets=len({c['set_id'] for c in cards.values()}), merged_translations=duplicate_count, source=str(source))
    # Transactional upsert: active games keep their exact card identities on reindex.
    with Session.begin() as db:
        for record in db.scalars(select(CardRecord)):
            if record.id not in cards:
                old=json.loads(record.payload); old['active']=False; record.payload=json.dumps(old,ensure_ascii=False)
        store_cards(db,cards.values())
        db.merge(Meta(key='import', value=json.dumps(report,ensure_ascii=False)))
    (settings.storage / 'import-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    log.info('Import: %s cartes, %s Pokémon, %s extensions, %s sans nom français, %s invalides',
             report['total'],report['pokemon'],report['sets'],missing_fr,len(raw['invalid']))
    return report

def store_cards(db, cards):
    records=[dict(id=c['id'],name=c['name'] or c.get('names',{}).get('en') or c['id'],
                  set_id=c['set_id'],category=c['category'] or 'Unknown',
                  payload=json.dumps(c,ensure_ascii=False,separators=(',',':'))) for c in cards]
    for i in range(0,len(records),500):
        statement=insert(CardRecord).values(records[i:i+500])
        db.execute(statement.on_conflict_do_update(index_elements=['id'],set_={
            k:getattr(statement.excluded,k) for k in ('name','set_id','category','payload')}))


def import_prepared(path,force=False):
    from .prepared_catalog import read_catalog, validate_catalog
    manifest=validate_catalog(path)
    with Session() as db:
        saved=db.get(Meta,'import')
        previous=json.loads(saved.value) if saved else {}
        if previous.get('sha256')==manifest['sha256'] and not force: return previous
    cards,manifest=read_catalog(path)
    identities={c['id'] for c in cards}
    with Session.begin() as db:
        for record in db.scalars(select(CardRecord)):
            if record.id not in identities:
                old=json.loads(record.payload);old['active']=False;record.payload=json.dumps(old,ensure_ascii=False)
        store_cards(db,cards)
        report=dict(manifest,source='catalog.fr.sqlite3')
        db.merge(Meta(key='import',value=json.dumps(report,ensure_ascii=False)))
    (settings.storage/'import-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    log.info('Catalogue FR: %s cartes, %s Pokémon, empreinte vérifiée.',len(cards),manifest['pokemon'])
    return report


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description='Indexer les fichiers TypeScript officiels TCGdex')
    parser.add_argument('--source', type=Path, default=settings.data)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    print(json.dumps(import_data(args.source,args.force),ensure_ascii=False,indent=2))
