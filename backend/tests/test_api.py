import asyncio
import io
import json
from fastapi.testclient import TestClient
from PIL import Image
from backend.app.main import app, jobs
from backend.app.models import FIELDS,VisionResult
from backend.app import vision
from backend.app.db import Session,Game
from .test_engine import clues

def batch(logged,version=0,card='xy10-63',cs=None):
    return {'game_id':logged.get('/api/game').json()['id'],'expected_version':version,'attempts':[{'card_id':card,'clues':(cs or clues()).model_dump()}]}

def test_auth_and_cookie(client):
    assert client.get('/api/game').status_code==401
    assert client.post('/api/login',json={'code':'anything'}).status_code==404
    r=client.post('/api/session')
    assert r.status_code==200
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
    assert client.post('/api/session',headers={'Origin':'https://evil.test'}).status_code==403

def test_http_workflow_and_persistence(logged):
    g=logged.get('/api/game').json()
    assert g['recommendation']['id']=='xy10-63'
    r=logged.post('/api/game/attempts',json=batch(logged,))
    assert r.status_code==200,r.text
    g=r.json();assert g['remaining']==1 and g['solved'] and g['recommendation']['id']=='xy10-63'
    assert len(g['history'])==1 and g['version']==1
    with Session() as db:assert db.get(Game,g['id']).recommendation=='xy10-63'
    assert logged.get('/api/game').json()['history']==g['history']
    r=logged.delete('/api/game/last?version=1&game_id='+g['id']);assert r.status_code==200
    assert r.json()['history']==[] and r.json()['remaining']==2

def test_duplicate_screenshots(logged):
    assert logged.post('/api/game/attempts',json=batch(logged,)).status_code==200
    b=batch(logged,version=1);b['attempts'][0]['clues']['hp']['value']='110'
    r=logged.post('/api/game/attempts',json=b)
    assert r.status_code==200 and len(r.json()['history'])==1

def test_contradiction_atomic(logged):
    cs=clues(hp={'color':'gray','arrow':'up'})
    r=logged.post('/api/game/attempts',json=batch(logged,cs=cs))
    assert r.status_code==409
    g=logged.get('/api/game').json();assert g['version']==0 and g['history']==[]
    assert logged.post('/api/game/attempts',json=batch(logged,)).status_code==200

def test_stale_version(logged):
    assert logged.post('/api/game/attempts',json=batch(logged,)).status_code==200
    assert logged.post('/api/game/attempts',json=batch(logged,)).status_code==409

def test_user_isolation_and_reset(logged):
    first=logged.get('/api/game').json()['id']
    with TestClient(app) as other:
        assert other.post('/api/session').status_code==200
        g=other.post('/api/games').json();assert g['id']!=first
        assert logged.post('/api/game/attempts',json=batch(logged,)).status_code==200
        assert other.get('/api/game').json()['history']==[]
        other.post('/api/games')
        assert len(logged.get('/api/game').json()['history'])==1
        assert logged.get('/api/game').json()['id']==first

def test_correct_last(logged):
    logged.post('/api/game/attempts',json=batch(logged,))
    # Replace instead of appending, and roll back deletion if contradiction.
    bad=batch(logged,version=1,cs=clues(hp={'color':'gray','arrow':'up'}))
    assert logged.put('/api/game/last',json=bad).status_code==409
    assert len(logged.get('/api/game').json()['history'])==1
    r=logged.put('/api/game/last',json=batch(logged,version=1));assert r.status_code==200
    assert len(r.json()['history'])==1

def test_search_local(logged):
    r=logged.get('/api/cards?q=xy10-63');assert r.json()[0]['name']=='Lucario'
    r=logged.get('/api/game/candidates');assert r.json()['total']==2
    assert logged.get('/api/health').json()['status']=='ok'
    assert logged.get('/api/game').headers['cache-control']=='no-store'

def image_bytes():
    b=io.BytesIO();Image.new('RGB',(50,50),'white').save(b,format='PNG');return b.getvalue()

def test_invalid_upload_and_limit(logged):
    assert logged.post('/api/game/analyze',files={'file':('bad.png',b'not an image','image/png')}).status_code==422
    assert logged.post('/api/game/analyze',files={'file':('big.png',b'x'*(9*1024*1024),'image/png')}).status_code==413

def test_ollama_job_json_and_ownership(logged,monkeypatch):
    response={'rows':[{'pokemon':'Lucario','card_id':'xy10-63','clues':clues().model_dump()}]}
    async def fake(content,on_start=None,expected=None):
        assert expected['id']=='xy10-63'
        return VisionResult.model_validate(response)
    monkeypatch.setattr(vision,'analyze',fake)
    r=logged.post('/api/game/analyze',files={'file':('capture.png',image_bytes(),'image/png')})
    assert r.status_code==202
    job=r.json()['job_id']
    import time
    for _ in range(100):
        result=logged.get('/api/analysis/'+job).json()
        if result['status'] in ('done','error'):break
        time.sleep(.01)
    assert result['status']=='done',result
    assert result['game']['history'][0]['card']['id']=='xy10-63'
    assert result['game']['solved'] and result['game']['pending'] is None
    with TestClient(app) as other:
        other.post('/api/session')
        assert other.get('/api/analysis/'+job).status_code==404
    g=logged.get('/api/game').json()
    assert g['remaining']==1 and len(g['history'])==1 and g['version']==1

def test_actual_ollama_client_structured_protocol(monkeypatch):
    import httpx
    original=httpx.AsyncClient
    def handler(req):
        payload=json.loads(req.content)
        assert payload['stream'] is False and payload['format']['properties']['rows']
        assert payload['messages'][0]['images']
        return httpx.Response(200,json={'message':{'content':json.dumps({'rows':[{'pokemon':'Lucario','card_id':None,'clues':clues().model_dump()}]})}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    result=asyncio.run(vision.analyze(image_bytes()));assert result.rows[0].pokemon=='Lucario'

def test_ollama_invalid_json(monkeypatch):
    import httpx
    import pytest
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'message':{'content':'not json'}})),**kwargs))
    with pytest.raises(ValueError,match='non conforme'):asyncio.run(vision.analyze(image_bytes()))

def test_image_proxy_cache(logged,monkeypatch,base_card):
    import httpx
    from backend.app.catalog import catalog
    from backend.app.settings import settings
    c=catalog()[base_card['id']]
    c['image_path']='fr/xy/xy10/63'
    raw=image_bytes();calls=[];original=httpx.AsyncClient
    def handler(req):
        calls.append(str(req.url));return httpx.Response(200,content=raw,headers={'content-type':'image/png'})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    response=logged.get('/api/images/xy10-63')
    assert response.status_code==200 and response.headers['content-type']=='image/webp'
    assert response.headers['cache-control']=='private, max-age=31536000, immutable'
    cached=logged.get('/api/images/xy10-63')
    assert cached.status_code==200 and cached.headers['cache-control']==response.headers['cache-control']
    assert calls==['https://assets.tcgdex.net/fr/xy/xy10/63/high.webp']
    assert Image.open(io.BytesIO(response.content)).format=='WEBP'
    for p in (settings.storage/'images').glob('*'):p.unlink()

def test_image_failure_retry_after_network_change(logged,monkeypatch,base_card):
    import httpx
    from backend.app.catalog import catalog
    catalog()[base_card['id']]['image_path']='fr/xy/xy10/63'
    original=httpx.AsyncClient;count=[0]
    def handler(req):
        count[0]+=1
        return httpx.Response(403) if count[0]==1 else httpx.Response(200,content=image_bytes())
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    assert logged.get('/api/images/xy10-63').status_code==404
    assert logged.get('/api/images/xy10-63').status_code==200

def test_streaming_body_limit(logged):
    # Missing Content-Length must not bypass the cap before multipart parsing.
    def chunks():
        for _ in range(10):yield b'x'*(1024*1024)
    response=logged.post('/api/game/analyze',content=chunks(),headers={'Content-Type':'application/octet-stream'})
    assert response.status_code==413

def test_logout_revokes_session(logged):
    assert logged.post('/api/logout').status_code==200
    assert logged.get('/api/me').status_code==401

def test_old_game_cannot_write_to_new_game(logged):
    old=batch(logged)
    logged.post('/api/games')
    assert logged.post('/api/game/attempts',json=old).status_code==409
    assert logged.get('/api/game').json()['history']==[]

def test_catalog_refresh_cannot_show_retired_recommendation(logged):
    from backend.app.catalog import catalog
    from backend.app.db import CardRecord
    with Session.begin() as db:
        row=db.get(CardRecord,'xy10-63');c=json.loads(row.payload);c['active']=False;row.payload=json.dumps(c)
    catalog.cache_clear()
    g=logged.get('/api/game').json()
    assert not g['recommendation'] or g['recommendation']['id']!='xy10-63'
    assert g['history']==[] and g['remaining']==1
    health=logged.get('/api/health').json()
    assert health['cards']==1 and health['archived_cards']==1

def test_anonymous_browser_keeps_its_game_without_any_code(client):
    r=client.post('/api/session');assert r.status_code==200 and not r.json()['has_game']
    initial_cookie=client.cookies.get('carto_session')
    g=client.post('/api/games').json()
    r=client.post('/api/session')
    assert r.status_code==200 and r.json()['has_game']
    assert client.cookies.get('carto_session')==initial_cookie
    assert client.get('/api/game').json()['id']==g['id']
    from backend.app.settings import settings
    assert not (settings.storage/'access-code.txt').exists()


def test_unknown_cookie_does_not_choose_another_anonymous_identity(client):
    client.cookies.set('carto_session','chosen-by-client')
    r=client.post('/api/session');assert r.status_code==200
    assert 'chosen-by-client' not in r.headers['set-cookie']
    assert client.get('/api/me').status_code==200


def test_image_uses_french_low_resolution_when_high_is_missing(logged,monkeypatch,base_card):
    import httpx
    from backend.app.catalog import catalog
    from backend.app.settings import settings
    for p in (settings.storage/'images').glob('*'):p.unlink()
    catalog()[base_card['id']]['image_path']='fr/xy/xy10/63'
    original=httpx.AsyncClient;calls=[]
    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(404) if req.url.path.endswith('/high.webp') else httpx.Response(200,content=image_bytes())
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    response=logged.get('/api/images/xy10-63')
    assert response.status_code==200
    assert calls==['https://assets.tcgdex.net/fr/xy/xy10/63/high.webp','https://assets.tcgdex.net/fr/xy/xy10/63/low.webp']
    assert Image.open(io.BytesIO(response.content)).format=='WEBP'
    for p in (settings.storage/'images').glob('*'):p.unlink()


def test_shining_fates_shiny_artwork_uses_parent_set(logged,monkeypatch,base_card):
    import httpx
    from backend.app.catalog import catalog
    from backend.app.settings import settings
    for p in (settings.storage/'images').glob('*'):p.unlink()
    catalog()[base_card['id']]['image_path']='fr/swsh/swsh4.5sv/SV008'
    original=httpx.AsyncClient;calls=[]
    def handler(req):
        calls.append(str(req.url));return httpx.Response(200,content=image_bytes())
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    assert logged.get('/api/images/xy10-63').status_code==200
    assert calls==['https://assets.tcgdex.net/fr/swsh/swsh4.5/SV008/high.webp']
    for p in (settings.storage/'images').glob('*'):p.unlink()
