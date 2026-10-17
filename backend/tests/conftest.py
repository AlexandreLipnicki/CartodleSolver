import os
import tempfile
from pathlib import Path
import pytest

TEST_DIR = tempfile.TemporaryDirectory(prefix='cartosolver-tests-')
os.environ['CARTO_STORAGE']=TEST_DIR.name
os.environ['CARTO_AUTO_IMPORT']='false'

from backend.app.db import init_db, Session, CardRecord, Attempt, Game, UserSession
from backend.app.catalog import catalog
from backend.app.main import app, limits, jobs
from fastapi.testclient import TestClient
from sqlalchemy import delete
import json

@pytest.fixture
def base_card():
    return dict(id='xy10-63',name='Lucario',names={'fr':'Lucario','en':'Lucario'},pokedex=[448],types=['Metal'],type_labels=['Métal'],stage='Stage1',stage_label='Niveau 1',hp=110,rarity='Rare',rarity_label='Rare',set_id='xy10',set_name='Impact des Destins',series_id='xy',series_name='XY',release_date='2016-05-02',chronology=1,illustrator='Hitoshi Ariga',number='63',category='Pokemon',image_path=None,image_url=None)

@pytest.fixture
def client(base_card):
    init_db(); limits.clear(); jobs.clear()
    with Session.begin() as db:
        for model in (Attempt,Game,UserSession,CardRecord):db.execute(delete(model))
        cards=[base_card,dict(base_card,id='test-1',name='Autre Pokémon',names={'fr':'Autre Pokémon','en':'Other Pokémon'},pokedex=[200],hp=100,types=['Water'],stage='Basic',rarity='Rare',rarity_label='Rare',set_id='test',series_id='sv',release_date='2023-01-01',illustrator='Autre artiste')]
        for c in cards:db.add(CardRecord(id=c['id'],name=c['name'],set_id=c['set_id'],category='Pokemon',payload=json.dumps(c)))
    catalog.cache_clear()
    with TestClient(app) as c:
        yield c
    catalog.cache_clear()

@pytest.fixture
def logged(client):
    assert client.post('/api/session').status_code==200
    assert client.post('/api/games').status_code==200
    return client
