"""Verified, offline rarity corrections; OCR observations never use this lookup."""
import json
from functools import lru_cache
from .normalization import norm,rarity
from .settings import ROOT


def identity(card):
    return {'name_en':norm(card.get('names',{}).get('en')),'hp':card.get('hp'),
            'pokedex':sorted(card.get('pokedex') or []),'types':sorted(card.get('types') or []),
            'stage':card.get('stage'),'illustrator':norm(card.get('illustrator')),
            'set_id':card.get('set_id'),'number':card.get('number')}


def secondary_identity(card):
    stages={'Basic':'Basic','Stage 1':'Stage1','Stage 2':'Stage2'}
    stage=next((stages[t] for t in card.get('subtypes',[]) if t in stages),None)
    hp=str(card.get('hp') or '')
    return {'name_en':norm(card.get('name')),'hp':int(hp) if hp.isdigit() else None,
            'pokedex':sorted(card.get('nationalPokedexNumbers') or []),'types':sorted(card.get('types') or []),
            'stage':stage,'illustrator':norm(card.get('artist')),
            'set_id':card.get('id','').rsplit('-',1)[0],'number':card.get('number')}


def verified_correction(primary,secondary):
    """A shared ID alone is insufficient: verify all independent solving fields."""
    if primary.get('id')!=secondary.get('id') or primary.get('category')!='Pokemon':return None
    if rarity(primary.get('rarity'))!='Rare' or rarity(secondary.get('rarity'))!='Rare Holo':return None
    a,b=identity(primary),secondary_identity(secondary)
    if any(v is None or v==[] or v=='' for v in a.values()) or a!=b:return None
    return {'rarity':'Rare Holo','match':a}


@lru_cache(maxsize=1)
def corrections():
    return json.loads((ROOT/'config/rarity-corrections.json').read_text(encoding='utf-8'))


def enrich_card(card):
    if rarity(card.get('rarity'))!='Rare':return card
    data=corrections();entry=data['cards'].get(card['id'])
    if not entry or identity(card)!=entry['match']:return card
    return dict(card,rarity=entry['rarity'],rarity_label=entry['rarity'],
                rarity_evidence='pokemon-tcg-data:'+data['source']['commit'])
