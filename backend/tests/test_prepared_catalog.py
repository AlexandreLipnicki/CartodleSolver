import json
import sqlite3
import pytest
from sqlalchemy import select
from backend.app.prepared_catalog import write_catalog, read_catalog, validate_catalog
from backend.app.importer import import_data
from backend.app.db import Session, CardRecord
from backend.app.settings import ROOT


def test_french_only_and_relational_indexes(tmp_path,base_card):
    path=tmp_path/'catalog.fr.sqlite3'
    english=dict(base_card,id='en-1',name=None,names={'en':'English only'})
    report=write_catalog([base_card,english],{'total':2,'missing_french':1},path)
    cards,manifest=read_catalog(path)
    assert [c['id'] for c in cards]==['xy10-63']
    assert manifest['total']==1 and manifest['missing_french']==0 and manifest['excluded_without_french']==1
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT pokedex FROM card_dex WHERE card_id=?',('xy10-63',)).fetchone()==(448,)
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not tables & {'games','sessions','attempts'}
        indexes={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {'cards_set','cards_category_hp','cards_illustrator'}<=indexes


def test_prepared_import_without_typescript_and_preserves_history(client,base_card,tmp_path,monkeypatch):
    path=tmp_path/'catalog.fr.sqlite3'
    write_catalog([base_card],{'total':1},path)
    import subprocess
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:pytest.fail('Prepared catalog must not invoke Node or TypeScript'))
    first=import_data(path,force=True)
    assert first['total']==1 and first['locale']=='fr'
    assert import_data(path)['sha256']==first['sha256']
    with Session() as db:
        # Retired records remain available for existing histories, but leave the active catalog.
        assert json.loads(db.get(CardRecord,'test-1').payload)['active'] is False
        assert json.loads(db.get(CardRecord,'xy10-63').payload)['active'] is True


def test_bad_checksum_does_not_modify_runtime(client,base_card,tmp_path):
    path=tmp_path/'catalog.fr.sqlite3'
    write_catalog([dict(base_card,hp=120)],{'total':1},path)
    with path.open('r+b') as f:
        f.seek(-1,2);f.write(b'!')
    with pytest.raises(ValueError,match='Empreinte'):import_data(path,force=True)
    with Session() as db:assert json.loads(db.get(CardRecord,'xy10-63').payload)['hp']==110


def test_bundled_catalog_integrity_and_coverage():
    path=ROOT/'data/catalog.fr.sqlite3'
    cards,manifest=read_catalog(path)
    assert manifest['total']==len(cards)>22000
    assert manifest['pokemon']>18000 and manifest['complete_pokemon']>17000
    assert all(c.get('name') for c in cards)
    assert next(c for c in cards if c['id']=='xy10-63')['name']=='Lucario'
    assert manifest['source_commit'] and manifest['source_url'].endswith('tcgdex/cards-database')
    assert 'storage/' not in json.dumps(manifest)
