import json
from functools import lru_cache
from sqlalchemy import text
from .db import engine
from .search_index import IndexedCards
from .normalization import normalize_card,set_index


class Catalog(dict):
    def __init__(self, cards):
        cards=[normalize_card(c) for c in cards]
        super().__init__((c['id'], c) for c in cards)
        self.set_index=set_index(cards)
        self.pokemon = IndexedCards(c for c in cards if c.get('category') == 'Pokemon' and c.get('active', True))


@lru_cache(maxsize=1)
def catalog():
    # Avoid constructing 20,000 ORM entities just to decode their JSON payloads.
    with engine.connect() as db:
        cards = [json.loads(row[0]) for row in db.execute(text('SELECT payload FROM cards ORDER BY id'))]
    from .settings import ROOT
    overrides=json.loads((ROOT/'config/card-overrides.json').read_text(encoding='utf-8'))
    return Catalog([dict(c,**overrides.get(c['id'],{})) for c in cards])


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
