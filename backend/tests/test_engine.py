import pytest
from backend.app.engine import compare,filter_cards,recommend,rules
from backend.app.models import Clue,Clues,VisionResult
from pydantic import ValidationError

def clues(**overrides):
    raw={f:{'color':'green','arrow':None} for f in ('pokedex','type','stage','hp','rarity','set','illustrator')}
    raw.update(overrides)
    return Clues.model_validate(raw)

@pytest.mark.parametrize('color,arrow,targets,expected',[
 ('yellow','up',[80,81,90,100,101],[81,90,100]),
 ('gray','up',[80,90,100,101,110],[101,110]),
 ('yellow','down',[59,60,70,79,80],[60,70,79]),
 ('gray','down',[50,59,60,70,80],[50,59]),
 ('green',None,[79,80,81],[80]),
 ('gray',None,[59,60,80,100,101],[59,101]),
])
def test_hp_boundaries(base_card,color,arrow,targets,expected):
    g=dict(base_card,hp=80)
    assert [n for n in targets if compare(dict(g,hp=n),g,'hp',Clue(color=color,arrow=arrow))] == expected

def test_hp_intersection(base_card):
    vals=[n for n in range(50,160) if all(compare(dict(base_card,hp=n),dict(base_card,hp=h),'hp',Clue(color='yellow',arrow='down')) for h in (120,110))]
    assert vals==list(range(100,110))

def test_dex_strict_bounds(base_card):
    vals=[n for n in range(1,400) if all(compare(dict(base_card,pokedex=[n]),dict(base_card,pokedex=[g]),'pokedex',Clue(color='gray',arrow=a)) for g,a in [(119,'up'),(326,'down')])]
    assert vals==list(range(120,326))

def test_stage_green(base_card):
    assert compare(base_card,base_card,'stage',Clue(color='green'))
    assert not compare(dict(base_card,stage='Basic'),base_card,'stage',Clue(color='green'))

def test_set_gray_up(base_card):
    clue=Clue(color='gray',arrow='up')
    assert compare(dict(base_card,set_id='sv1',series_id='sv',release_date='2023-01-01'),base_card,'set',clue)
    assert not compare(dict(base_card,set_id='xy11',release_date='2016-08-01'),base_card,'set',clue)
    assert not compare(dict(base_card,set_id='base1',series_id='base',release_date='1999-01-01'),base_card,'set',clue)
    assert not compare(base_card,base_card,'set',clue)

def test_types_sets(base_card):
    g=dict(base_card,types=['Metal','Fighting'])
    assert compare(dict(g,types=['Metal']),g,'type',Clue(color='yellow'))
    assert not compare(g,g,'type',Clue(color='yellow'))
    assert not compare(dict(g,types=['Metal']),g,'type',Clue(color='gray'))
    assert compare(dict(g,types=['Water']),g,'type',Clue(color='gray'))

def test_unverified_rarity_never_excludes(base_card):
    assert compare(dict(base_card,rarity='Common'),base_card,'rarity',Clue(color='yellow',arrow='up')) is None
    assert compare(base_card,base_card,'rarity',Clue(color='gray')) is False

def test_explicit_rarity_config(base_card,monkeypatch):
    import backend.app.engine as engine
    monkeypatch.setattr(engine,'rules',lambda:{'rarity_groups':{'Rare':'r','Rare Holo':'r','Common':'c'},'rarity_order':{'Common':0,'Rare':1,'Rare Holo':2}})
    assert engine.compare(dict(base_card,rarity='Rare Holo'),base_card,'rarity',Clue(color='yellow',arrow='up'))
    assert not engine.compare(dict(base_card,rarity='Rare Holo'),base_card,'rarity',Clue(color='gray',arrow='up'))

def test_missing_quarantined(base_card):
    missing=dict(base_card,id='missing',hp=None)
    attempts=[{'card_id':base_card['id'],'clues':clues().model_dump()}]
    valid,unknown=filter_cards([base_card,missing],attempts,{base_card['id']:base_card})
    assert valid==[base_card] and unknown==[missing]
    assert recommend(valid,attempts)==base_card

def test_deterministic_compatible_recommendation(base_card):
    cards=[dict(base_card,id=f'c{i}',hp=70+i*10) for i in range(10)]
    attempts=[{'card_id':'used','clues':clues().model_dump()}]
    assert recommend(cards,attempts)==recommend(list(reversed(cards)),attempts)
    assert recommend(cards,attempts) in cards

@pytest.mark.parametrize('bad',[{'color':'blue'}, {'color':'gray','arrow':'left'}, {'color':'green','unknown':1}])
def test_strict_clues(bad):
    with pytest.raises(ValidationError):Clue.model_validate(bad)

def test_invalid_semantics():
    with pytest.raises(ValidationError):clues(stage={'color':'yellow'})
    with pytest.raises(ValidationError):clues(hp={'color':'green','arrow':'up'})
    with pytest.raises(ValidationError):VisionResult.model_validate({'rows':[]})

def test_illustrator_normalized(base_card):
    assert compare(dict(base_card,illustrator='  HITOSHI   ARIGA '),base_card,'illustrator',Clue(color='green'))
