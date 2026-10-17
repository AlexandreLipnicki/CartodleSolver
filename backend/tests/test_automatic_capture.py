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


@pytest.mark.parametrize('change',[{'pokemon':'Pikachu'},{'card_id':'wrong-print'}])
def test_unidentifiable_card_is_rejected(logged,monkeypatch,change):
    r=row();r.update(change)
    result=upload_result(logged,monkeypatch,[r])
    assert result['status']=='error'
    assert logged.get('/api/game').json()['history']==[]


@pytest.mark.parametrize('field,value,key,expected',[
    ('hp','120 PV','hp',120),('set','Autre extension','set_name','Autre extension'),
    ('stage','Niveau 2','stage','Stage2'),('type','Eau','types',['Water']),
    ('illustrator','Autre artiste','illustrator','Autre artiste'),
    ('rarity','RARE HOLO','rarity','Rare Holo'),('pokedex','25','pokedex',[25])])
def test_visible_values_override_catalog_and_survive_reload(logged,monkeypatch,field,value,key,expected):
    from backend.app.catalog import catalog
    baseline=catalog()['xy10-63'][key]
    r=row();r['clues'][field]['value']=value
    result=upload_result(logged,monkeypatch,[r])
    assert result['status']=='done',result
    g=result['game']
    assert g['solved'] and g['history'][0]['card'][key]==expected
    assert g['recommendation'][key]==expected
    assert logged.get('/api/game').json()['history'][0]['card'][key]==expected
    assert catalog()['xy10-63'][key]==baseline


def test_another_card_is_used_even_when_lucario_is_pending(logged,monkeypatch):
    result=upload_result(logged,monkeypatch,[row(name='Autre Pokémon')])
    assert result['status']=='done',result
    assert result['game']['history'][0]['card']['id']=='test-1'
    assert result['game']['solved']


def test_another_card_can_continue_toward_lucario(logged,monkeypatch):
    cs=clues(pokedex={'color':'gray','arrow':'up'},type={'color':'gray'},stage={'color':'gray'},
             hp={'color':'yellow','arrow':'up'},rarity={'color':'gray'},set={'color':'gray','arrow':'down'},illustrator={'color':'gray'})
    result=upload_result(logged,monkeypatch,[row(name='Autre Pokémon',cs=cs)])
    assert result['status']=='done',result
    assert result['game']['history'][0]['card']['id']=='test-1'
    assert result['game']['pending']['card']['id']=='xy10-63'
    assert not result['game']['solved']


def test_lucario_rarity_correct_before_first_capture(logged):
    assert logged.get('/api/game').json()['pending']['card']['rarity']=='Rare Holo'


def test_visible_values_are_checked_against_known_printing(base_card):
    r=row()
    values={'pokedex':'Lucario #448','type':'Métal','stage':'Niv. 1','hp':'110 PV','rarity':'Rare','set':'Impact des Destins (2016)','illustrator':'HITOSHI ARIGA'}
    for f,v in values.items():r['clues'][f]['value']=v
    assert visible_mismatches(VisionResult.model_validate({'rows':[r]}).rows[0],base_card)==[]


def test_contradiction_is_atomic_and_leaves_pending_card(logged,monkeypatch):
    result=upload_result(logged,monkeypatch,[row(cs=clues(hp={'color':'gray','arrow':'up'}))])
    assert result['status']=='error' and 'PV' in result['error']
    assert result['conflict_fields']==['hp']
    assert 'catalogue' in result['error']
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


def test_observed_hp_changes_next_deduction_not_only_history(logged,monkeypatch):
    # Catalog Lucario has 110 HP: gray/down would exclude the 100 HP target.
    # The screen says 140 HP, making gray/down consistent with that target.
    r=row(cs=other_clues());r['clues']['hp']={'color':'gray','arrow':'down','value':140}
    result=upload_result(logged,monkeypatch,[r])
    assert result['status']=='done',result
    assert result['game']['pending']['card']['id']=='test-1'
    assert result['game']['history'][0]['card']['hp']==140
    again=upload_result(logged,monkeypatch,[r])
    assert again['status']=='done' and again['duplicate']


def test_observations_do_not_change_another_session(logged,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    r=row();r['clues']['hp']['value']=140
    assert upload_result(logged,monkeypatch,[r])['status']=='done'
    with TestClient(app) as other:
        other.post('/api/session');g=other.post('/api/games').json()
        assert g['pending']['card']['hp']==110
        assert g['history']==[]


def test_existing_attempt_schema_migration_preserves_rows(tmp_path,monkeypatch):
    from sqlalchemy import create_engine
    from backend.app import db as module
    engine=create_engine('sqlite:///'+str(tmp_path/'legacy.sqlite3'))
    module.Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.exec_driver_sql('ALTER TABLE attempts DROP COLUMN observed_card')
        db.exec_driver_sql("INSERT INTO attempts (id,game_id,card_id,clues,remaining,created) VALUES (1,'legacy','xy10-63','{}',10,'2026-01-01')")
    monkeypatch.setattr(module,'engine',engine)
    module.init_db();module.init_db()
    with engine.connect() as db:
        assert db.exec_driver_sql('SELECT card_id,remaining,observed_card FROM attempts').fetchall()==[('xy10-63',10,None)]
    engine.dispose()


def test_suggestion_remains_default_when_only_attributes_differ(base_card):
    from backend.app.capture import resolve_capture
    twin=dict(base_card,id='xy10-other',hp=140,rarity='Common')
    r=row();r['clues']['hp']['value']=140;r['clues']['rarity']['value']='Commune'
    result=VisionResult.model_validate({'rows':[r]})
    _,actual=resolve_capture(result,base_card,[],{base_card['id']:base_card,twin['id']:twin})
    assert actual['id']==base_card['id'] and actual['hp']==140 and actual['rarity']=='Common'


def test_visible_extension_identifies_another_printing(base_card):
    from backend.app.capture import resolve_capture
    twin=dict(base_card,id='other-63',set_id='other',set_name='Autre extension',release_date='2020-01-01')
    r=row();r['clues']['set']['value']='Autre extension · 2020'
    _,actual=resolve_capture(VisionResult.model_validate({'rows':[r]}),base_card,[],{base_card['id']:base_card,twin['id']:twin})
    assert actual['id']=='other-63' and actual['set_id']=='other'
