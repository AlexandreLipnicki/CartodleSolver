"""Portable, read-only catalog distribution. Runtime sessions remain in storage/."""
import hashlib
import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
APPLICATION_ID = 0x43415254


def manifest_path(path):
    return Path(path).with_suffix('.manifest.json')


def fingerprint(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_catalog(path):
    path = Path(path).resolve()
    manifest = json.loads(manifest_path(path).read_text(encoding='utf-8'))
    if manifest.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Version de catalogue non prise en charge.')
    if fingerprint(path) != manifest.get('sha256'):
        raise ValueError('Empreinte du catalogue incorrecte : retéléchargez les fichiers SQLite et manifest ensemble.')
    return manifest


def read_catalog(path):
    path = Path(path).resolve()
    manifest = validate_catalog(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        if db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
            raise ValueError('Ce fichier ne contient pas un catalogue CartoSolver.')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Le catalogue SQLite est endommagé.')
        rows = [json.loads(row[0]) for row in db.execute('SELECT payload FROM cards ORDER BY id')]
    if len(rows) != manifest['total'] or not rows:
        raise ValueError('Le nombre de cartes diffère du manifeste du catalogue.')
    if any(not c.get('name') for c in rows):
        raise ValueError('Une carte sans nom français a été trouvée dans le catalogue français.')
    return rows, manifest


def write_catalog(cards, report, path):
    from .engine import complete, norm
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.building.sqlite3')
    if temp.exists():
        temp.unlink()
    french = sorted((c for c in cards if c.get('name')), key=lambda c: c['id'])
    pokemon = [c for c in french if c.get('category') == 'Pokemon']
    gaps = []
    required = ('pokedex', 'types', 'stage', 'hp', 'rarity', 'set_name', 'series_id', 'release_date', 'illustrator')
    for c in pokemon:
        missing = [f for f in required if c.get(f) is None or c.get(f) == [] or c.get(f) == '']
        if len(c.get('pokedex', [])) != 1:
            missing.append('single_pokedex')
        if missing:
            gaps.append({'id': c['id'], 'name': c['name'], 'missing': missing})
    try:
        with sqlite3.connect(temp) as db:
            db.executescript(f'''
                PRAGMA page_size=4096;
                PRAGMA application_id={APPLICATION_ID};
                PRAGMA user_version={SCHEMA_VERSION};
                CREATE TABLE series(id TEXT PRIMARY KEY, name_fr TEXT) WITHOUT ROWID;
                CREATE TABLE sets(id TEXT PRIMARY KEY, name_fr TEXT, series_id TEXT REFERENCES series(id), release_date TEXT, chronology INTEGER) WITHOUT ROWID;
                CREATE TABLE cards(id TEXT PRIMARY KEY, name_fr TEXT NOT NULL, category TEXT NOT NULL,
                    set_id TEXT NOT NULL REFERENCES sets(id), hp INTEGER, stage TEXT, rarity TEXT,
                    illustrator TEXT, collection_number TEXT NOT NULL, search_key TEXT NOT NULL, payload TEXT NOT NULL) WITHOUT ROWID;
                CREATE TABLE card_types(card_id TEXT REFERENCES cards(id), type TEXT, PRIMARY KEY(type,card_id)) WITHOUT ROWID;
                CREATE TABLE card_dex(card_id TEXT REFERENCES cards(id), pokedex INTEGER, PRIMARY KEY(pokedex,card_id)) WITHOUT ROWID;
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            ''')
            for c in french:
                db.execute('INSERT OR IGNORE INTO series VALUES (?,?)', (c.get('series_id'), c.get('series_name')))
                db.execute('INSERT OR IGNORE INTO sets VALUES (?,?,?,?,?)',
                           (c['set_id'], c.get('set_name'), c.get('series_id'), c.get('release_date'), c.get('chronology')))
                # Other languages and attack text are not used by the solver.
                c = dict(c, names={k: v for k, v in c.get('names', {}).items() if k in ('fr', 'en')}, active=True)
                search = norm(' '.join([c['name'], c['id'], c.get('set_name') or '', c['number']]))
                db.execute('INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (c['id'], c['name'], c['category'], c['set_id'], c.get('hp'), c.get('stage'), c.get('rarity'),
                            c.get('illustrator'), c['number'], search, json.dumps(c, ensure_ascii=False, separators=(',', ':'))))
                db.executemany('INSERT INTO card_types VALUES (?,?)', [(c['id'], t) for t in set(c.get('types', []))])
                db.executemany('INSERT INTO card_dex VALUES (?,?)', [(c['id'], d) for d in set(c.get('pokedex', []))])
            db.executescript('''
                CREATE INDEX cards_name ON cards(name_fr COLLATE NOCASE);
                CREATE INDEX cards_set ON cards(set_id);
                CREATE INDEX cards_category_hp ON cards(category,hp);
                CREATE INDEX cards_stage ON cards(stage);
                CREATE INDEX cards_rarity ON cards(rarity);
                CREATE INDEX cards_illustrator ON cards(illustrator);
                CREATE INDEX sets_date ON sets(release_date);
                CREATE INDEX sets_series ON sets(series_id);
            ''')
            dataset = dict({k:v for k,v in report.items() if k!='missing_french'}, total=len(french), pokemon=len(pokemon), locale='fr',
                           international_total=report['total'], source_missing_french=report.get('missing_french',0),
                           missing_french=0, excluded_without_french=report['total']-len(french),
                           complete_pokemon=sum(complete(c) for c in pokemon), pokemon_to_verify=sum(not complete(c) for c in pokemon),
                           missing_fields={f:sum(f in g['missing'] for g in gaps) for f in required},
                           sets=len({c['set_id'] for c in french}),
                           pocket_cards=sum(c.get('series_id')=='tcgp' for c in french))
            db.execute('INSERT INTO metadata VALUES (?,?)', ('dataset', json.dumps(dataset, ensure_ascii=False)))
            db.commit()
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Relations invalides dans le catalogue.')
            db.execute('ANALYZE')
            db.execute('VACUUM')
        temp.replace(path)
    finally:
        if temp.exists(): temp.unlink()
    manifest = dict(dataset, schema_version=SCHEMA_VERSION, sha256=fingerprint(path), bytes=path.stat().st_size)
    manifest_path(path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    path.with_suffix('.quality.json').write_text(json.dumps(gaps, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest
