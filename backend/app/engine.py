"""Pure deterministic deduction. None means metadata/rule is insufficient, never False."""
import json
import math
import unicodedata
from collections import Counter
from functools import lru_cache
from .models import Clues, FIELDS
from .settings import settings

@lru_cache(maxsize=1)
def rules():
    return json.loads(settings.rules_path.read_text(encoding='utf-8'))

@lru_cache(maxsize=8192)
def norm(s):
    return ' '.join(''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch)).casefold().split()) if s else None

def series(c):
    return rules().get('set_series_overrides',{}).get(c['set_id'],c.get('series_id'))

def compare(target, guess, field, clue):
    color, arrow = clue.color, clue.arrow
    if field == 'pokedex':
        a, b = target.get('pokedex'), guess.get('pokedex')
        if not a or not b: return None
        if color == 'green': return set(a) == set(b)
        # Multi-Pokémon cards cannot be ordered without a verified game rule.
        if len(a)!=1 or len(b)!=1: return None
        if a == b: return False
        return a[0] > b[0] if arrow == 'up' else a[0] < b[0] if arrow == 'down' else True
    if field == 'hp':
        a, b = target.get('hp'), guess.get('hp')
        if a is None or b is None: return None
        if color == 'green': return a == b
        delta = a-b
        proximity = 0 < abs(delta) <= 20 if color == 'yellow' else abs(delta) > 20
        return proximity and (delta>0 if arrow=='up' else delta<0 if arrow=='down' else True)
    if field == 'type':
        a, b = set(target.get('types') or []), set(guess.get('types') or [])
        if not a or not b: return None
        return a == b if color=='green' else bool(a & b) and a != b if color=='yellow' else not bool(a & b)
    if field in ('stage','illustrator'):
        a, b = target.get(field),guess.get(field)
        if field=='illustrator': a,b=norm(a),norm(b)
        if a is None or b is None: return None
        return a==b if color=='green' else a!=b
    if field == 'rarity':
        a,b=target.get('rarity'),guess.get('rarity')
        if not a or not b: return None
        if color=='green': return a==b
        if a==b: return False
        groups, order=rules().get('rarity_groups',{}),rules().get('rarity_order',{})
        if a not in groups or b not in groups: return None
        if (groups[a]==groups[b]) != (color=='yellow'): return False
        if arrow:
            if a not in order or b not in order: return None
            return order[a]>order[b] if arrow=='up' else order[a]<order[b]
        return True
    if field == 'set':
        a,b=target.get('set_id'),guess.get('set_id')
        if not a or not b: return None
        if color=='green': return a==b
        if a==b: return False
        result=True
        sa,sb=series(target),series(guess)
        if rules().get('series_proximity_verified') and sa and sb:
            if (sa==sb)!=(color=='yellow'): return False
        else: result=None
        if arrow:
            da,db=target.get('release_date'),guess.get('release_date')
            if not da or not db or da==db: return None if result is not False else False
            if not (da>db if arrow=='up' else da<db): return False
        return result
    raise ValueError(field)

def complete(c):
    return bool(c.get('name') and len(c.get('pokedex',[]))==1 and c.get('types') and
                all(c.get(k) is not None for k in ('hp','stage','rarity','set_id','set_name','series_id','release_date','illustrator')))

def filter_cards(cards, attempts, by_id):
    from .search_index import IndexedCards
    if isinstance(cards,IndexedCards):
        return cards.filtered(attempts,by_id)
    valid, uncertain = [], []
    prepared=[(by_id[a['card_id']], Clues.model_validate(a['clues'])) for a in attempts]
    for c in cards:
        unknown=not complete(c); incompatible=False
        for guess, clues in prepared:
            for f in FIELDS:
                check=compare(c,guess,f,getattr(clues,f))
                if check is False: incompatible=True; break
                # Unknown game rules do not eliminate metadata-complete cards.
                # Missing card attributes are quarantined by complete().
            if incompatible: break
        if not incompatible:
            (uncertain if unknown else valid).append(c)
    return valid,uncertain

def features(c):
    return (c['pokedex'][0], frozenset(c['types']), c['stage'], c['hp'], c['rarity'],
            c['set_id'], series(c), c['release_date'], norm(c['illustrator']))


def _outcome(t,g,groups,order):
    # All expensive string normalization and type-set construction occurs once per card.
    dex = (t[0]>g[0])-(t[0]<g[0])
    types = 'g' if t[1]==g[1] else 'y' if t[1]&g[1] else 'x'
    delta=t[3]-g[3]
    rarity=('g' if t[4]==g[4] else 'y' if t[4] in groups and g[4] in groups and groups[t[4]]==groups[g[4]] else 'different',
            (order[t[4]]>order[g[4]])-(order[t[4]]<order[g[4]]) if t[4] in order and g[4] in order else None)
    extension=('g' if t[5]==g[5] else 'y' if t[6]==g[6] else 'x', (t[7]>g[7])-(t[7]<g[7]))
    return (dex, types, t[2]==g[2], ('g' if delta==0 else 'y' if abs(delta)<=20 else 'x', (delta>0)-(delta<0)),
            rarity, extension, t[8]==g[8])


def outcome(t,g):
    return _outcome(features(t),features(g),rules().get('rarity_groups',{}),rules().get('rarity_order',{}))


def sample(items,n):
    return items if len(items)<=n else [items[i*len(items)//n] for i in range(n)]

def recommend(valid, attempts):
    if len(valid)==1: return valid[0]
    if not attempts:
        return next((c for c in valid if c['id']=='xy10-63'),None)
    tried={a['card_id'] for a in attempts}
    pool=sorted((c for c in valid if c['id'] not in tried),key=lambda c:c['id'])
    if not pool: return None
    if len(pool)==1: return pool[0]
    # Bounded deterministic approximation for large sets; exact below 160 guesses/512 targets.
    targets=sample(sorted(valid,key=lambda c:c['id']),512)
    encoded=[features(t) for t in targets]
    groups,order=rules().get('rarity_groups',{}),rules().get('rarity_order',{})
    def score(g):
        guess=features(g)
        counts=Counter(_outcome(t,guess,groups,order) for t in encoded)
        entropy=-sum((n/len(targets))*math.log2(n/len(targets)) for n in counts.values())
        return (entropy, bool(g.get('image_url')), -len(g['name']))
    return max(sample(pool,160),key=score)

def summarize(valid,uncertain,attempts,by_id=None):
    allc=valid+uncertain
    result={}
    for field,key in [('pokedex','pokedex'),('type','type_labels'),('stage','stage_label'),('hp','hp'),('rarity','rarity_label'),('set','set_name'),('illustrator','illustrator')]:
        values=set()
        for c in allc:
            value=c.get(key)
            if isinstance(value,list): values.update(value)
            elif value is not None: values.add(value)
        ordered=sorted(values)
        if field in ('pokedex','hp'):
            result[field]={'min':min(ordered) if ordered else None,'max':max(ordered) if ordered else None,'values':ordered if len(ordered)<=24 else [],'count':len(ordered)}
        else: result[field]={'values':ordered[:12],'count':len(ordered)}
        excluded=set()
        for attempt in attempts:
            guess=(by_id or {}).get(attempt['card_id'])
            clue=attempt['clues'][field]
            if not guess or clue['color']=='green': continue
            if field=='type' and clue['color']!='gray': continue
            value=guess.get(key)
            if isinstance(value,list): excluded.update(value)
            elif value is not None: excluded.add(value)
        result[field]['excluded']=sorted(excluded)
    return result
