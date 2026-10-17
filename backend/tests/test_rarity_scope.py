import pytest
from backend.app.catalog import Catalog
from backend.app.engine import compare, rarity_direction, rarity_reachability
from backend.app.models import Clue
from backend.app.normalization import rarity


def test_pikachu_aliases():
    assert rarity('Rare Pikachu') == rarity('Pikachu Rare')
    assert rarity('Rareté : Rare Holo ↑') == rarity('Rare Holo')


@pytest.mark.parametrize('target,guess,color,arrow,expected',[
    ('Common','Rare Holo','yellow','down',False),
    ('Pikachu Rare','Rare Holo','yellow','down',True),
    ('Rare Holo','Pikachu Rare','yellow','down',False),
    ('Common','Common','gray','up',False),
    ('Rare Galerie','Ultra Rare','yellow',None,True),
    ('Rare Holo V','Rare Galerie','gray','up',False),
    ('Rare Galerie','Rare Holo V','gray','up',None),
])
def test_verified_rarity_feedback(target,guess,color,arrow,expected):
    assert compare({'rarity':target},{'rarity':guess},'rarity',Clue(color=color,arrow=arrow)) is expected


def test_target_scope_keeps_common_guesses(base_card):
    cards=Catalog([dict(base_card,id='common',rarity='Common'),
                   dict(base_card,id='pocket',series_id='tcgp'),base_card])
    assert [c['id'] for c in cards.pokemon] == [base_card['id']]
    assert {c['id'] for c in cards.supported_pokemon} == {'common',base_card['id']}
    assert 'pocket' in cards  # Source retained; never proposed as a JCC target.


def test_partial_order():
    assert rarity_direction(rarity('Common'),rarity('Rare Galerie'),{}) == -1
    assert rarity_direction(rarity('Rare'),rarity('Rare Holo'),{}) is None
    with pytest.raises(ValueError):rarity_reachability((('a','b'),('b','a')))
