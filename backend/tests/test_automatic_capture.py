import time
import pytest
from backend.app import vision
from backend.app.models import VisionResult
from backend.app.capture import visible_mismatches
from .test_api import image_bytes
from .test_engine import clues


def row(name='Lucario',cs=None,card_id=None):
    return {'pokemon':name,'card_id':card_id,'clues':(cs or clues()).model_dump()}


def other_clues():
    return clues(pokedex={'color':'gray','arrow':'down'},type={'color':'gray'},stage={'color':'gray'},
                 hp={'color':'yellow','arrow':'down'},rarity={'color':'gray'},set={'color':'gray','arrow':'up'},illustrator={'color':'gray'})


def upload_result(logged,monkeypatch,rows):
    async def fake(content,on_start=None,expected=None):
        assert expected and expected['id']
        return VisionResult.model_validate({'rows':rows})
    monkeypatch.setattr(vision,'analyze',fake)
    r=logged.post('/api/game/analyze',files={'file':('capture.png',image_bytes(),'image/png')})
    assert r.status_code==202,r.text
    for _ in range(150):
        result=logged.get('/api/analysis/'+r.json()['job_id']).json()
        if result['status'] in ('done','error'):return result
        time.sleep(.01)
    pytest.fail('Automatic capture job did not finish')


def test_lucario_pending_immediately_and_survives_reload(logged):
    g=logged.get('/api/game').json()
    assert g['history']==[] and g['pending']['card']['id']=='xy10-63'
    assert g['pending']['number']==1 and g['pending']['status']=='awaiting_capture'
    assert logged.get('/api/game').json()['pending']==g['pending']


def test_auto_advances_without_card_id_or_confirmation(logged,monkeypatch):
    result=upload_result(logged,monkeypatch,[row(cs=other_clues())])
    assert result['status']=='done',result
    g=result['game']
    assert len(g['history'])==1 and g['history'][0]['card']['id']=='xy10-63'
    assert g['recommendation']['id']=='test-1' and g['pending']['card']['id']=='test-1'
    assert g['probable_solution'] and not g['solved']
    assert g['pending']['number']==2 and g['version']==1
    # A screenshot containing the previous row and the current one completes only the pending attempt.
    result=upload_result(logged,monkeypatch,[row(cs=other_clues()),row(name='Autre Pokémon')])
    assert result['status']=='done',result
    assert len(result['game']['history'])==2 and result['game']['pending'] is None and result['game']['solved']


def test_repeated_old_capture_does_not_consume_next_card(logged,monkeypatch):
    upload_result(logged,monkeypatch,[row(cs=other_clues())])
    result=upload_result(logged,monkeypatch,[row(cs=other_clues())])
    assert result['status']=='done' and result['duplicate'] is True
    assert result['game']['version']==1 and len(result['game']['history'])==1
    assert result['game']['pending']['card']['id']=='test-1'


@pytest.mark.parametrize('change',[{'pokemon':'Pikachu'},{'card_id':'wrong-print'}, {'field':'hp','value':120},
                                  {'field':'set','value':'Autre extension'}, {'field':'stage','value':'Niveau 2'},
                                  {'field':'type','value':'Eau'}, {'field':'illustrator','value':'Autre artiste'},
                                  {'field':'rarity','value':'Rare Holo'}, {'field':'pokedex','value':25}])
def test_wrong_card_or_visible_attribute_is_rejected_automatically(logged,monkeypatch,change):
    r=row()
    if 'field' in change:r['clues'][change['field']]['value']=change['value']
    else:r.update(change)
    result=upload_result(logged,monkeypatch,[r])
    assert result['status']=='error',result
    g=logged.get('/api/game').json()
    assert g['history']==[] and g['version']==0 and g['pending']['card']['id']=='xy10-63'


def test_visible_values_are_checked_against_known_printing(base_card):
    r=row()
    values={'pokedex':'Lucario #448','type':'Métal','stage':'Niv. 1','hp':'110 PV','rarity':'Rare','set':'Impact des Destins (2016)','illustrator':'HITOSHI ARIGA'}
    for f,v in values.items():r['clues'][f]['value']=v
    assert visible_mismatches(VisionResult.model_validate({'rows':[r]}).rows[0],base_card)==[]


def test_contradiction_is_atomic_and_leaves_pending_card(logged,monkeypatch):
    result=upload_result(logged,monkeypatch,[row(cs=clues(hp={'color':'gray','arrow':'up'}))])
    assert result['status']=='error' and 'contradictoires' in result['error']
    g=logged.get('/api/game').json()
    assert g['history']==[] and g['version']==0 and g['pending']['card']['id']=='xy10-63'


def test_two_different_matching_rows_need_new_capture_not_manual_form(logged,monkeypatch):
    result=upload_result(logged,monkeypatch,[row(),row(cs=other_clues())])
    assert result['status']=='error' and 'recadrée' in result['error']
    assert logged.get('/api/game').json()['history']==[]


def test_stale_analysis_cannot_fill_a_new_game(logged,monkeypatch):
    async def fake(content,on_start=None,expected=None):
        # Change the active game during the analysis, before its transaction commits.
        from backend.app.db import Session,UserSession,Game
        import uuid
        with Session.begin() as db:
            u=db.query(UserSession).first()
            g=Game(id=str(uuid.uuid4()),owner=u.token_hash,recommendation='xy10-63')
            db.add(g);db.flush();u.game_id=g.id
        return VisionResult.model_validate({'rows':[row()]})
    monkeypatch.setattr(vision,'analyze',fake)
    r=logged.post('/api/game/analyze',files={'file':('capture.png',image_bytes(),'image/png')})
    for _ in range(150):
        result=logged.get('/api/analysis/'+r.json()['job_id']).json()
        if result['status']=='error':break
        time.sleep(.01)
    assert result['status']=='error' and 'changé' in result['error']
    assert logged.get('/api/game').json()['history']==[]

def test_all_green_keeps_the_played_print_not_a_metadata_twin(logged,monkeypatch,base_card):
    import json
    from backend.app.db import Session,CardRecord
    from backend.app.catalog import catalog
    twin=dict(base_card,id='xy10-copy',number='copy')
    with Session.begin() as db:db.add(CardRecord(id=twin['id'],name=twin['name'],set_id=twin['set_id'],category='Pokemon',payload=json.dumps(twin)))
    catalog.cache_clear()
    result=upload_result(logged,monkeypatch,[row()])
    assert result['status']=='done' and result['game']['solved']
    assert result['game']['recommendation']['id']=='xy10-63' and result['game']['pending'] is None
