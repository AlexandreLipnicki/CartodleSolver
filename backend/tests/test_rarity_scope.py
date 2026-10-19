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
    ('Rare Galerie','Rare Holo V','gray','up',True),
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


def test_all_readable_holopocket_badges_have_consistent_feedback():
    import json
    from backend.app.settings import ROOT
    entries=json.loads((ROOT/'config/holopocket-rarities.json').read_text())['entries']
    for target in entries:
        assert rarity(target['label'])==target['canonical']
        for guess in entries:
            same=target['canonical']==guess['canonical']
            same_level=target['level']==guess['level']
            a,b={'rarity':target['label']},{'rarity':guess['label']}
            assert compare(a,b,'rarity',Clue(color='green')) is same
            assert compare(a,b,'rarity',Clue(color='yellow')) is (same_level and not same)
            assert compare(a,b,'rarity',Clue(color='gray')) is (not same_level)


def test_menu_does_not_invent_order_or_merge_missing_rarities():
    assert rarity_direction(rarity('Rare Radieuse'),rarity('Rare High-Tech'),{}) is None
    assert rarity('Rare')!=rarity('Rare Holo')
    assert compare({'rarity':'Rare'}, {'rarity':'Rare Holo'},'rarity',Clue(color='yellow')) is None
    assert rarity('Secret Rare')==rarity('Rare Secrète')
    assert rarity('Amazing Rare')==rarity('Rare Magnifique')
    assert rarity('Rare Magnifique')!=rarity('Rare Secrète')
    assert rarity('Rare Chromatique V…')!=rarity('Shiny rare VMAX')
