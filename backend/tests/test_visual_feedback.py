import asyncio
from copy import deepcopy
import io
import json
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
import pytest
from backend.app import vision
from backend.app.models import VisionResult
from backend.app.visual_feedback import reconcile

FIXTURES=Path(__file__).parent/'fixtures/cartodle'


def reference():
    return json.loads((FIXTURES/'lucario.expected.json').read_text())


@pytest.mark.parametrize('scale,format',[(1,'PNG'),(.75,'PNG'),(1.5,'PNG'),(1,'JPEG')])
def test_pixels_recover_faint_arrows_and_feedback_without_changing_text(scale,format):
    im=Image.open(FIXTURES/'lucario.recreated.png').convert('RGB')
    if scale!=1:im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)
    out=io.BytesIO();im.save(out,format=format)
    payload=reference()
    for clue in payload['rows'][0]['clues'].values():clue.update(color='green',arrow=None)
    actual=reconcile(out.getvalue(),payload)
    assert actual==reference()
    VisionResult.model_validate(actual)


def test_unrecognized_layout_keeps_model_reading():
    out=io.BytesIO();Image.new('RGB',(1134,148),'white').save(out,format='PNG')
    payload=reference()
    assert reconcile(out.getvalue(),deepcopy(payload))==payload


def test_multiple_rows_are_not_assigned_single_row_pixels():
    payload=reference();payload['rows'].append(deepcopy(payload['rows'][0]))
    assert reconcile((FIXTURES/'lucario.recreated.png').read_bytes(),deepcopy(payload))==payload


def test_green_and_no_arrow_on_colored_grid():
    im=Image.open(FIXTURES/'lucario.recreated.png').convert('RGB');draw=ImageDraw.Draw(im)
    # Replace the HP box with a green tile and a text-like white patch, no arrow.
    draw.rectangle((548,9,683,132),fill=(40,100,55))
    draw.rectangle((559,104,580,116),fill='white')
    out=io.BytesIO();im.save(out,format='PNG')
    result=reconcile(out.getvalue(),reference())
    assert result['rows'][0]['clues']['hp']=={'value':110,'color':'green','arrow':None}


def test_ollama_http_result_uses_pixel_feedback(monkeypatch):
    original=httpx.AsyncClient
    def handler(req):
        body=json.loads(req.content)
        assert 'fond violet' in body['messages'][0]['content']
        payload=reference()
        for clue in payload['rows'][0]['clues'].values():clue.update(color='gray',arrow=None)
        return httpx.Response(200,json={'message':{'content':json.dumps(payload)}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    raw=[]
    result=asyncio.run(vision.analyze((FIXTURES/'lucario.recreated.png').read_bytes(),on_raw=raw.append))
    assert result.model_dump()==reference()
    assert raw[0]['rows'][0]['clues']['hp']['color']=='gray'
    assert raw[0]['rows'][0]['clues']['rarity']['arrow'] is None


def test_missing_ollama_model_has_actionable_diagnostic(monkeypatch):
    original=httpx.AsyncClient
    def handler(req):return httpx.Response(404,json={'error':"model 'qwen2.5vl:7b' not found, try pulling it first"})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    with pytest.raises(ValueError,match='ollama pull'):
        asyncio.run(vision.analyze((FIXTURES/'lucario.recreated.png').read_bytes()))
