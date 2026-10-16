"""Bind OCR to the server's expected printing, never to a catalog-wide guess."""
import re
from .engine import norm
from .models import FIELDS

LABELS={'pokedex':'Pokédex','type':'type','stage':'stade','hp':'PV','rarity':'rareté','set':'extension','illustrator':'illustrateur'}


def visible_mismatches(row, card):
    mismatches=[]
    if row.card_id and row.card_id!=card['id']:
        mismatches.append('impression')
    names={norm(card.get('name')),norm(card.get('names',{}).get('en'))}
    if norm(row.pokemon) not in names:
        mismatches.append('Pokémon')
    for field in FIELDS:
        value=getattr(row.clues,field).value
        if value is None or str(value).strip()=='':continue
        text=norm(str(value))
        if field in ('hp','pokedex'):
            numbers=[int(n) for n in re.findall(r'\d+',str(value))]
            expected=card.get('pokedex',[]) if field=='pokedex' else [card.get('hp')]
            ok=(bool(numbers) and set(numbers)==set(expected)) or (field=='pokedex' and not numbers and text in names)
        elif field=='type':
            parts={norm(p.strip()) for p in re.split(r'[/,;+|&]',str(value)) if p.strip()}
            ok=parts in ({norm(t) for t in card.get('types',[])},{norm(t) for t in card.get('type_labels',[])})
        elif field=='stage':
            aliases={'basic':{'base','de base','basic'},'stage1':{'niveau 1','stade 1','stage 1','stage1','niv. 1','niv 1','1'},'stage2':{'niveau 2','stade 2','stage 2','stage2','niv. 2','niv 2','2'}}
            ok=text in ({norm(card.get('stage')),norm(card.get('stage_label'))}|aliases.get(norm(card.get('stage')),set()))
        elif field=='set':
            year=(card.get('release_date') or '')[:4]
            label=re.sub(r'\s*\(\d{4}\)\s*$','',text).strip()
            years=re.findall(r'\b(?:19|20)\d{2}\b',text)
            ok=(text==year or text in {norm(card.get('set_name')),norm(card.get('set_id'))} or (label==norm(card.get('set_name')) and all(y==year for y in years)))
        elif field=='rarity':
            ok=text in {norm(card.get('rarity')),norm(card.get('rarity_label'))}
        else:
            ok=text==norm(card.get('illustrator'))
        if not ok:mismatches.append(LABELS[field])
    return mismatches


def signature(clues):
    return tuple((getattr(clues,f).color,getattr(clues,f).arrow) for f in FIELDS)


def expected_row(result,card,previous,by_id):
    matches=[];problems=[]
    for row in result.rows:
        # Old rows can be present in the screenshot, but never become new attempts.
        errors=visible_mismatches(row,card)
        if not errors:
            matches.append(row)
        elif norm(row.pokemon) in {norm(card.get('name')),norm(card.get('names',{}).get('en'))}:
            problems.extend(errors)
    unique={signature(r.clues):r for r in matches}
    if len(unique)==1:
        return next(iter(unique.values()))
    if len(unique)>1:
        raise ValueError('Plusieurs lignes différentes correspondent à la carte attendue. Collez une capture recadrée sur son résultat ; aucun indice n’a été enregistré.')
    if problems:
        raise ValueError('La capture ne correspond pas à '+card['name']+' ('+card['id']+') : '+', '.join(sorted(set(problems)))+'. Recollez le résultat de la carte proposée.')
    # An exact replay is harmless; the currently pending card remains unchanged.
    for row in result.rows:
        for attempt in previous:
            old=by_id.get(attempt['card_id'])
            if old and not visible_mismatches(row,old) and signature(row.clues)==tuple((attempt['clues'][f]['color'],attempt['clues'][f]['arrow']) for f in FIELDS):
                return None
    raise ValueError('La carte attendue est '+card['name']+' ('+card['id']+'). Son résultat n’est pas lisible dans cette capture. Recollez une capture de cette carte ; aucun indice n’a été enregistré.')
