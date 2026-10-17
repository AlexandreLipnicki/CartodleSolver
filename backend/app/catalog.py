import json
from functools import lru_cache
from sqlalchemy import text
from .db import engine
from .search_index import IndexedCards
from .normalization import normalize_card,set_index,rarity
from .rarity_enrichment import enrich_card


class Catalog(dict):
    def __init__(self, cards, overrides=None):
        resolved=[]
        for card in cards:
            corrected=dict(enrich_card(card))
            override=(overrides or {}).get(card['id'],{})
            corrected.update(override)
            if 'rarity' in override:corrected.pop('rarity_evidence',None)
            resolved.append(normalize_card(corrected))
        cards=resolved
        super().__init__((c['id'], c) for c in cards)
        self.set_index=set_index(cards)
        from .engine import rules
        excluded=set(rules().get('excluded_series',[]))
        self.supported_pokemon = IndexedCards(c for c in cards if c.get('category') == 'Pokemon' and c.get('active', True) and c.get('series_id') not in excluded)
        excluded_rarities={rarity(r) for r in rules().get('excluded_target_rarities',[])}
        self.pokemon=IndexedCards(c for c in self.supported_pokemon if c.get('rarity') not in excluded_rarities)


@lru_cache(maxsize=1)
def catalog():
    # Avoid constructing 20,000 ORM entities just to decode their JSON payloads.
    with engine.connect() as db:
        cards = [json.loads(row[0]) for row in db.execute(text('SELECT payload FROM cards ORDER BY id'))]
    from .settings import ROOT
    overrides=json.loads((ROOT/'config/card-overrides.json').read_text(encoding='utf-8'))
    return Catalog(cards,overrides=overrides)


def pokemon_cards():
    return catalog().pokemon


def search_cards(query, limit=40):
    from .engine import norm
    query = norm(query) or ''
    if len(query) < 2:
        return []
    cards = pokemon_cards()
    if cards.search_keys is None:
        cards.search_keys = [norm(' '.join([c.get('name') or '', c['id'], c.get('set_name') or '', c['number']])) for c in cards]
    found = []
    for c, key in zip(cards, cards.search_keys):
        if query in key:
            found.append(c)
            if len(found) == limit:
                break
    return found
