from concurrent.futures import ThreadPoolExecutor
import random
from backend.app.engine import filter_cards
from backend.app.models import Clues,FIELDS
from backend.app.search_index import IndexedCards
from backend.app.catalog import search_cards


def make_cards(base):
    cards=[]
    for i in range(180):
        c=dict(base,id=f'c{i}',pokedex=[i%30+1],hp=30+i%30*5,
               types=[['Metal','Water','Fire'][i%3]],stage=['Basic','Stage1','Stage2'][i%3],
               rarity=['Common','Rare','Rare Holo'][i%3],set_id=f'set{i%5}',series_id=f'series{i%2}',
               release_date=f'202{i%5}-01-01',illustrator=f'Artist {i%7}')
        if i%17==0:c['hp']=None
        if i%19==0:c['pokedex']=[1,2]
        if i%23==0:c['stage']=None
        if i%29==0:c['set_name']=None
        cards.append(c)
    return cards


def test_index_matches_reference_for_colors_arrows_and_missing_metadata(base_card):
    rng=random.Random(428)
    cards=make_cards(base_card);indexed=IndexedCards(cards);by_id={c['id']:c for c in cards}
    attempts=[]
    for i in range(120):
        guess=cards[rng.randrange(len(cards))]
        clues={}
        for field in FIELDS:
            color=rng.choice(['green','gray'] if field in ('stage','illustrator') else ['green','gray','yellow'])
            arrow=rng.choice(['up','down',None]) if field in ('hp','pokedex','rarity','set') and color!='green' else None
            clues[field]={'color':color,'arrow':arrow}
        # Exercise both single and intersected histories; avoid only checking empty results.
        attempt={'card_id':guess['id'],'clues':Clues.model_validate(clues).model_dump()}
        attempts=attempts[-2:]+[attempt] if i%3 else [attempt]
        assert filter_cards(indexed,attempts,by_id)==filter_cards(cards,attempts,by_id)
    for field in FIELDS:
        for color in (['green','gray'] if field in ('stage','illustrator') else ['green','yellow','gray']):
            clues={f:{'color':'green','arrow':None} for f in FIELDS}
            clues[field]={'color':color,'arrow':None}
            a=[{'card_id':cards[1]['id'],'clues':clues}]
            assert filter_cards(indexed,a,by_id)==filter_cards(cards,a,by_id)


def test_rule_changes_invalidate_masks(base_card,monkeypatch):
    import backend.app.engine as engine
    cards=make_cards(base_card);indexed=IndexedCards(cards);by_id={c['id']:c for c in cards}
    a=[{'card_id':cards[1]['id'],'clues':{f:{'color':'green' if f!='rarity' else 'yellow','arrow':None} for f in FIELDS}}]
    filter_cards(indexed,a,by_id)
    monkeypatch.setattr(engine,'rules',lambda:{'rarity_groups':{'Rare':'r','Common':'r','Rare Holo':'x'},'series_proximity_verified':False})
    assert filter_cards(indexed,a,by_id)==filter_cards(cards,a,by_id)


def test_parallel_players_share_only_immutable_index(base_card):
    cards=make_cards(base_card);indexed=IndexedCards(cards);by_id={c['id']:c for c in cards}
    histories=[[{'card_id':cards[i]['id'],'clues':{f:{'color':'green','arrow':None} for f in FIELDS}}] for i in range(1,17)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        got=list(pool.map(lambda a:filter_cards(indexed,a,by_id),histories))
    assert got==[filter_cards(cards,a,by_id) for a in histories]


def test_cached_accent_insensitive_search(logged):
    assert search_cards('lucario')[0]['id']=='xy10-63'
    assert search_cards('IMPACT DES DESTINS')
    assert search_cards('xy10-63')[0]['id']=='xy10-63'
    assert search_cards('l')==[]


def test_observed_values_do_not_leak_between_index_queries(base_card):
    from backend.app.search_index import IndexedCards
    from backend.app.engine import filter_cards
    from .test_engine import clues
    cards=IndexedCards([base_card,dict(base_card,id='other',hp=120)])
    by_id={c['id']:c for c in cards}
    observed=dict(base_card,hp=120)
    a={'card_id':base_card['id'],'clues':clues().model_dump(),'observed_card':observed}
    b={'card_id':base_card['id'],'clues':clues().model_dump()}
    assert filter_cards(cards,[a],by_id)==filter_cards(list(cards),[a],by_id)
    assert {c['id'] for c in filter_cards(cards,[a],by_id)[0]}=={base_card['id'],'other'}
    assert [c['id'] for c in filter_cards(cards,[b],by_id)[0]]==[base_card['id']]
    assert filter_cards(cards,[a],by_id)==filter_cards(list(cards),[a],by_id)
