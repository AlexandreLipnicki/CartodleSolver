"""Regression of the user's Snorlax game, transcribed from the supplied image."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from backend.app.catalog import Catalog,catalog
from backend.app.capture import observed_card,resolve_capture
from backend.app.engine import compare,filter_cards,recommend
from backend.app.models import Clue,VisionResult,VisionRow
from backend.app.prepared_catalog import read_catalog
from backend.app.settings import ROOT
from .test_automatic_capture import upload_result

GAME=Path(__file__).parent/'fixtures/cartodle/ronflex-game.json'


@pytest.fixture(scope='module')
def french_catalog():
    cards,_=read_catalog(ROOT/'data/catalog.fr.sqlite3')
    return Catalog(cards)


@pytest.mark.parametrize('alias',['Holo Rare','RARE HOLO','Rare Holo','  holo   rare  '])
@pytest.mark.parametrize('color',['gray','yellow','green'])
def test_rarity_aliases_cannot_bypass_feedback(base_card,alias,color):
    candidate=dict(base_card,rarity=alias)
    guess=dict(base_card,rarity='Rare Holo')
    assert compare(candidate,guess,'rarity',Clue(color=color)) is (color=='green')
    assert compare(dict(candidate,rarity='Rare Holo V'),guess,'rarity',Clue(color='gray')) is not False


@pytest.mark.parametrize('value',['Évolution Céleste 2022','Extension illisible 2022','2022'])
def test_visible_year_remains_a_bound_when_full_date_is_unknown(french_catalog,value):
    row=VisionRow.model_validate(json.loads(GAME.read_text())[1]['row'])
    row.clues.set.value=value
    actual=observed_card(row,french_catalog['swsh7-169'],french_catalog)
    assert actual['release_year']==2022 and actual['release_date'] is None
    for date in ('2020-08-14','2021-08-27','2021-12-31'):
        candidate=dict(actual,id='older',set_id='older',series_id='swsh',release_date=date,release_year=None)
        assert compare(candidate,actual,'set',Clue(color='yellow',arrow='up')) is False
    candidate=dict(actual,id='later',set_id='later',series_id='swsh',release_date='2023-01-20',release_year=None)
    assert compare(candidate,actual,'set',Clue(color='yellow',arrow='up')) is not False


def test_known_extension_uses_full_date_within_the_same_year(french_catalog):
    row=VisionRow.model_validate(json.loads(GAME.read_text())[1]['row'])
    guess=observed_card(row,french_catalog['swsh7-169'],french_catalog)
    assert guess['release_date']=='2021-08-27'
    assert compare(french_catalog['swsh3-69'],guess,'set',row.clues.set) is False
    earlier=dict(guess,set_id='earlier',release_date='2021-03-19')
    later=dict(guess,set_id='later',release_date='2021-11-12')
    assert compare(earlier,guess,'set',row.clues.set) is False
    assert compare(later,guess,'set',row.clues.set) is True


def test_gallery_is_the_same_extension_but_a_different_rarity(french_catalog):
    normal=french_catalog['swsh11-143'];gallery=french_catalog['swsh11tg-TG10']
    assert gallery['rarity']=='Rare Galerie' and normal['rarity']=='Rare Holo'
    assert compare(gallery,normal,'set',Clue(color='green')) is True
    assert compare(gallery,normal,'rarity',Clue(color='gray',arrow='up')) is not False


def test_full_snorlax_history_preserves_target_and_all_exclusions(french_catalog):
    attempts=[];by_id=french_catalog;cards=by_id.pokemon
    for n,entry in enumerate(json.loads(GAME.read_text())):
        expected=by_id[entry['card_id']]
        result=VisionResult.model_validate({'rows':[entry['row']]})
        row,actual=resolve_capture(result,expected,attempts,by_id)
        assert actual['id']==entry['card_id']
        attempts.append({'card_id':actual['id'],'clues':row.clues.model_dump(),'observed_card':actual})
        valid,unknown=filter_cards(cards,attempts,by_id)
        assert filter_cards(list(cards),attempts,by_id)==(valid,unknown)
        assert any(c['id']=='swsh11tg-TG10' for c in valid),entry['card_id']
        assert all(c['rarity'] not in ('Holo Rare','Rare Holo') for c in valid)
        if n>=1:assert all(c['release_date']>'2021-08-27' for c in valid)
        if n>=3:assert all(c['release_date']>'2022-07-01' for c in valid)
        next_card=recommend(valid,attempts)
        assert next_card and next_card in valid
        if n>=1:assert next_card['id']!='swsh3-69'
    assert [c['id'] for c in valid]==['swsh11tg-TG10']


def test_full_history_through_capture_api_ignores_old_rows(logged,monkeypatch):
    from backend.app.importer import import_data
    import_data(ROOT/'data/catalog.fr.sqlite3',force=True);catalog.cache_clear()
    logged.post('/api/games')
    seen=[]
    for entry in json.loads(GAME.read_text()):
        seen.insert(0,entry['row']) # newest first, as in the supplied screenshot
        result=upload_result(logged,monkeypatch,deepcopy(seen))
        assert result['status']=='done',result
        game=result['game']
        assert game['history'][-1]['card']['id']==entry['card_id']
        assert len(game['history'])==len(seen)
        if not game['solved']:
            assert game['recommendation']['rarity'] not in ('Holo Rare','Rare Holo')
        if len(seen)>=2 and not game['solved']:
            assert game['recommendation']['release_date']>'2021-08-27'
    assert game['solved'] and game['recommendation']['id']=='swsh11tg-TG10'
    assert logged.get('/api/game').json()['history']==game['history']


def test_existing_game_recovers_a_lost_year_bound_without_rewriting_history(logged):
    from backend.app.importer import import_data
    from backend.app.db import Session,Attempt,Game
    import_data(ROOT/'data/catalog.fr.sqlite3',force=True);catalog.cache_clear()
    game=logged.post('/api/games').json()
    row=VisionRow.model_validate(json.loads(GAME.read_text())[1]['row'])
    row.clues.set.value='Évolution Céleste 2022'
    legacy=observed_card(row,catalog()['swsh7-169'],catalog())
    legacy.pop('release_year') # persisted by the old, faulty date handling
    with Session.begin() as db:
        db.add(Attempt(game_id=game['id'],card_id='swsh7-169',clues=row.clues.model_dump_json(),observed_card=json.dumps(legacy),remaining=100))
        g=db.get(Game,game['id']);g.version=1;g.recommendation='swsh3-69'
    repaired=logged.get('/api/game').json()
    assert repaired['recommendation']['release_date'][:4]>='2022'
    assert repaired['history'][0]['card']['release_year']==2022
    assert repaired['history'][0]['clues']['set']['value']=='Évolution Céleste 2022'
    with Session() as db:
        saved=db.query(Attempt).filter_by(game_id=game['id']).one()
        assert 'release_year' not in json.loads(saved.observed_card)
