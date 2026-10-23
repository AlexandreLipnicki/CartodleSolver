"""Pure deterministic deduction. None means metadata/rule is insufficient, never False."""
import json
import math
from collections import Counter
from functools import lru_cache
from .models import Clues, FIELDS
from .normalization import norm,rarity,set_identity
from .settings import settings

@lru_cache(maxsize=1)
def rules():
    return json.loads(settings.rules_path.read_text(encoding='utf-8'))


def rarity_tables():
    current=rules()
    return ({rarity(k):v for k,v in current.get('rarity_groups',{}).items()},
            {rarity(k):v for k,v in current.get('rarity_order',{}).items()})


def rarity_direction(a,b,order):
    if a in order and b in order:
        return (order[a]>order[b])-(order[a]<order[b])
    edges=tuple((rarity(x),rarity(y)) for x,y in rules().get('rarity_order_relations',[]))
    reachable=rarity_reachability(edges)
    if (a,b) in reachable:return -1
    if (b,a) in reachable:return 1
    return None

@lru_cache(maxsize=16)
def rarity_reachability(edges):
    result=set(edges)
    while True:
        expanded=result|{(a,d) for a,b in result for c,d in result if b==c}
        if any(a==b for a,b in expanded):raise ValueError('Ordre des raretés cyclique')
        if expanded==result:return result
        result=expanded


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
        a,b=rarity(target.get('rarity')),rarity(guess.get('rarity'))
        if not a or not b: return None
        if color=='green': return a==b
        if a==b: return False
        groups,order=rarity_tables()
        checks=[]
        if a in groups and b in groups:
            checks.append((groups[a]==groups[b]) == (color=='yellow'))
        else:checks.append(None)
        if arrow:
            direction=rarity_direction(a,b,order)
            checks.append(None if direction is None else direction==(1 if arrow=='up' else -1))
        if False in checks:return False
        return None if None in checks else True
    if field == 'set':
        a,b=set_identity(target.get('set_id')),set_identity(guess.get('set_id'))
        if color=='green': return a==b if a and b else None
        if a and b and a==b:return False
        result=True if a and b else None
        sa,sb=series(target),series(guess)
        if rules().get('series_proximity_verified') and sa and sb:
            if (sa==sb)!=(color=='yellow'): return False
        else: result=None
        if arrow:
            da,db=target.get('release_date'),guess.get('release_date')
            if target.get('release_year') and da and int(da[:4])!=int(target['release_year']):da=None
            if guess.get('release_year') and db and int(db[:4])!=int(guess['release_year']):db=None
            if da and db and da!=db:
                if not (da>db if arrow=='up' else da<db):return False
            else:
                # A visible year still supplies a bound when OCR/source disagree
                # on the year or the extension name could not be resolved.
                ya=target.get('release_year') or (da[:4] if da else None)
                yb=guess.get('release_year') or (db[:4] if db else None)
                if ya and yb and int(ya)!=int(yb):
                    if not (int(ya)>int(yb) if arrow=='up' else int(ya)<int(yb)):return False
                else:result=None if result is not False else False
        return result
    raise ValueError(field)

def complete(c):
    return bool(c.get('name') and len(c.get('pokedex',[]))==1 and c.get('types') and
                all(c.get(k) is not None for k in ('hp','stage','rarity','set_id','set_name','series_id','release_date','illustrator')))

def filter_cards(cards, attempts, by_id):
    from .search_index import IndexedCards
    observed={a['card_id']:a['observed_card'] for a in attempts if a.get('observed_card')}
    if isinstance(cards,IndexedCards):
        valid, uncertain=cards.filtered(attempts,by_id)
        if not observed: return valid,uncertain
        # Only re-evaluate corrected printings; keep the shared bitset index intact.
        replacements=[observed[c['id']] for c in cards if c['id'] in observed]
        extra_valid,extra_uncertain=filter_cards(replacements,attempts,by_id)
        order={c['id']:i for i,c in enumerate(cards)}
        return (sorted([c for c in valid if c['id'] not in observed]+extra_valid,key=lambda c:order[c['id']]),
                sorted([c for c in uncertain if c['id'] not in observed]+extra_uncertain,key=lambda c:order[c['id']]))
    valid, uncertain = [], []
    prepared=[(a.get('observed_card') or by_id[a['card_id']], Clues.model_validate(a['clues']),set(a.get('ignored_fields',[]))) for a in attempts]
    for c in cards:
        c=observed.get(c['id'],c)
        unknown=not complete(c); incompatible=False
        for guess, clues, ignored in prepared:
            for f in FIELDS:
                if f in ignored:continue
                check=compare(c,guess,f,getattr(clues,f))
                if check is False: incompatible=True; break
                # Unknown game rules do not eliminate metadata-complete cards.
                # Missing card attributes are quarantined by complete().
            if incompatible: break
        if not incompatible:
            (uncertain if unknown else valid).append(c)
    return valid,uncertain

def features(c):
    return (c['pokedex'][0], frozenset(c['types']), c['stage'], c['hp'], rarity(c['rarity']),
            set_identity(c['set_id']), series(c), c['release_date'], norm(c['illustrator']))


def _outcome(t,g,groups,order,directions=None):
    # All expensive string normalization and type-set construction occurs once per card.
    dex = (t[0]>g[0])-(t[0]<g[0])
    types = 'g' if t[1]==g[1] else 'y' if t[1]&g[1] else 'x'
    delta=t[3]-g[3]
    rarity=('g' if t[4]==g[4] else 'y' if t[4] in groups and g[4] in groups and groups[t[4]]==groups[g[4]] else 'different',
            directions.get((t[4],g[4])) if directions is not None else rarity_direction(t[4],g[4],order))
    extension=('g' if t[5]==g[5] else 'y' if t[6]==g[6] else 'x', (t[7]>g[7])-(t[7]<g[7]))
    return (dex, types, t[2]==g[2], ('g' if delta==0 else 'y' if abs(delta)<=20 else 'x', (delta>0)-(delta<0)),
            rarity, extension, t[8]==g[8])


def outcome(t,g):
    return _outcome(features(t),features(g),*rarity_tables())


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
    groups,order=rarity_tables()
    rarities={c[4] for c in encoded}|{rarity(c['rarity']) for c in pool}
    directions={(a,b):rarity_direction(a,b,order) for a in rarities for b in rarities}
    def score(g):
        guess=features(g)
        counts=Counter(_outcome(t,guess,groups,order,directions) for t in encoded)
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
            if field in attempt.get('ignored_fields',[]):continue
            guess=attempt.get('observed_card') or (by_id or {}).get(attempt['card_id'])
            clue=attempt['clues'][field]
            if not guess or clue['color']=='green': continue
            if field=='type' and clue['color']!='gray': continue
            value=guess.get(key)
            if isinstance(value,list): excluded.update(value)
            elif value is not None: excluded.add(value)
        result[field]['excluded']=sorted(excluded)
    return result
