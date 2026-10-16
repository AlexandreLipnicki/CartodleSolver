import json
from functools import lru_cache
from sqlalchemy import select
from .db import Session, CardRecord

@lru_cache(maxsize=1)
def catalog():
    with Session() as db:
        all_cards=[json.loads(r.payload) for r in db.scalars(select(CardRecord))]
    return {c['id']:c for c in all_cards}

def pokemon_cards():
    return [c for c in catalog().values() if c.get('category')=='Pokemon' and c.get('active',True)]
