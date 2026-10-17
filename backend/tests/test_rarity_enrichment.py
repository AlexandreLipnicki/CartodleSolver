from copy import deepcopy
import json
from pathlib import Path
import pytest
from backend.app.catalog import Catalog,catalog
from backend.app.capture import observed_card
from backend.app.engine import filter_cards,recommend
from backend.app.models import VisionRow
from backend.app.prepared_catalog import read_catalog
from backend.app.rarity_enrichment import corrections,enrich_card,identity,verified_correction
from backend.app.settings import ROOT
from .test_automatic_capture import upload_result

GAME=Path(__file__).parent/'fixtures/cartodle/corvaillus-game.json'


@pytest.fixture(scope='module')
def french_catalog():
    cards,_=read_catalog(ROOT/'data/catalog.fr.sqlite3')
    return Catalog(cards)


def primary_secondary(cat):
    primary=dict(cat['sm1-20'],rarity='Rare',rarity_label='Rare')
    secondary={'id':primary['id'],'name':primary['names']['en'],'hp':str(primary['hp']),
               'nationalPokedexNumbers':primary['pokedex'],'types':primary['types'],
               'subtypes':['Stage 2'],'artist':primary['illustrator'],'number':primary['number'],'rarity':'Rare Holo'}
    return primary,secondary


def test_only_verified_holo_printings_are_corrected(french_catalog):
    assert french_catalog['sm1-20']['rarity']=='Rare Holo' # Sucreine
    assert french_catalog['sm1-85']['rarity']=='Rare Holo' # Crocorible
    assert french_catalog['sm1-41']['rarity']=='Rare'      # Oratoria, ordinary rare
    primary,secondary=primary_secondary(french_catalog)
    assert verified_correction(primary,secondary)==corrections()['cards'][primary['id']]
    assert enrich_card(primary)['rarity']=='Rare Holo'
    secondary['rarity']='Rare'
    assert verified_correction(primary,secondary) is None


@pytest.mark.parametrize('field,value',[
    ('hp','999'),('types',['Metal']),('nationalPokedexNumbers',[1]),('subtypes',['Basic']),
    ('artist','Autre artiste'),('name','Other Pokémon'),('number','999'),('id','other-20')])
def test_shared_id_cannot_override_disagreeing_metadata(french_catalog,field,value):
    primary,secondary=primary_secondary(french_catalog)
    secondary[field]=value
    assert verified_correction(primary,secondary) is None


def test_runtime_guard_rejects_changed_primary_metadata(french_catalog):
    primary,_=primary_secondary(french_catalog)
    assert enrich_card(dict(primary,hp=999))['rarity']=='Rare'
    overridden=Catalog([primary],overrides={primary['id']:{'rarity':'Rare','rarity_label':'Rare'}})
    assert overridden[primary['id']]['rarity']=='Rare'
    assert 'rarity_evidence' not in overridden[primary['id']]


def test_visible_rarity_overrides_enriched_source_for_this_game(french_catalog):
    row=VisionRow.model_validate(json.loads(GAME.read_text())[1]['row'])
    row.clues.rarity.value='Rare'
    actual=observed_card(row,french_catalog['sm1-20'],french_catalog)
    assert actual['rarity']=='Rare' and 'rarity_evidence' not in actual
    assert french_catalog['sm1-20']['rarity']=='Rare Holo'


def test_corrected_artifact_is_offline_and_auditable():
    cards,manifest=read_catalog(ROOT/'data/catalog.fr.sqlite3')
    marked=[c for c in cards if c.get('rarity_evidence')]
    assert len(marked)==corrections()['count']==manifest['rarity_enrichment']['applied']>700
    assert manifest['rarity_enrichment']['source']==corrections()['source']
    for card in marked:
        assert card['rarity']=='Rare Holo'
        assert identity(card)==corrections()['cards'][card['id']]['match']


def test_corvaillus_result_has_candidates_without_relaxing_any_clue(french_catalog):
    attempts=[]
    for entry in json.loads(GAME.read_text()):
        row=VisionRow.model_validate(entry['row'])
        actual=observed_card(row,french_catalog[entry['card_id']],french_catalog)
        attempts.append(dict(card_id=actual['id'],clues=row.clues.model_dump(),observed_card=actual))
    valid,unknown=filter_cards(french_catalog.pokemon,attempts,french_catalog)
    assert filter_cards(list(french_catalog.pokemon),attempts,french_catalog)==(valid,unknown)
    assert len(valid)==12 and not unknown
    assert {'sm1-20','sm1-85','sm3-53'}<={c['id'] for c in valid}
    assert all(448<c['pokedex'][0]<823 and 140<=c['hp']<160 and c['stage']=='Stage2' for c in valid)
    assert all(c['rarity']=='Rare Holo' and '2016-05-02'<c['release_date']<'2020-08-14' for c in valid)
    assert all(not set(c['types'])&{'Metal','Colorless'} for c in valid)
    assert all(c['series_id'] not in ('xy','swsh') and c['illustrator'] not in ('Hitoshi Ariga','Kouki Saitou') for c in valid)
    assert recommend(valid,attempts) in valid


def test_screenshot_history_is_accepted_through_api_and_survives_reload(logged,monkeypatch):
    from backend.app.importer import import_data
    import_data(ROOT/'data/catalog.fr.sqlite3',force=True);catalog.cache_clear()
    logged.post('/api/games')
    seen=[]
    for entry in json.loads(GAME.read_text()):
        seen.insert(0,entry['row'])
        result=upload_result(logged,monkeypatch,deepcopy(seen))
        assert result['status']=='done',result
        assert result['game']['history'][-1]['card']['id']==entry['card_id']
    game=result['game']
    assert len(game['history'])==2 and game['remaining']==12 and game['pending']
    assert game['pending']['card']['rarity']=='Rare Holo'
    assert game['history'][1]['clues']==seen[0]['clues']
    assert logged.get('/api/game').json()['history']==game['history']


def test_archived_metadata_cannot_erase_an_active_extension_date(french_catalog):
    current=french_catalog['xy10-63']
    archived=dict(current,id='retired-1',set_id='retired',active=False,release_date='2023-01-01')
    cards=Catalog([current,archived])
    row=VisionRow.model_validate(json.loads(GAME.read_text())[0]['row'])
    actual=observed_card(row,current,cards)
    assert actual['set_id']=='xy10' and actual['release_date']=='2016-05-02'
