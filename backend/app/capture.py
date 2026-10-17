"""Resolve the played card and preserve screenshot values within its game."""
import re
from .engine import norm
from .models import FIELDS
from .normalization import normalize_card,rarity,pokemon_names,set_label,set_index,set_identity

LABELS={'pokedex':'Pokédex','type':'type','stage':'stade','hp':'PV','rarity':'rareté','set':'extension','illustrator':'illustrateur'}


def visible_mismatches(row, card):
    mismatches=[]
    if row.card_id and row.card_id!=card['id']:
        mismatches.append('impression')
    names=pokemon_names(card)
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
            year=str(card.get('release_year') or (card.get('release_date') or '')[:4])
            label=set_label(value)
            years=re.findall(r'\b(?:19|20)\d{2}\b',text)
            names={norm(card.get('set_name')),norm(card.get('set_id'))}
            if set_identity(card.get('set_id'))!=card.get('set_id'):
                names.add(re.sub(r'\s+galerie (?:de dresseurs|de galar|galar)$','',norm(card.get('set_name')) or ''))
                names.add(set_identity(card.get('set_id')))
            ok=(text==year or text in names or (label in names and all(y==year for y in years)))
        elif field=='rarity':
            ok=rarity(value)==rarity(card.get('rarity'))
        else:
            ok=text==norm(card.get('illustrator'))
        if not ok:mismatches.append(LABELS[field])
    return mismatches


def signature(clues):
    return tuple((getattr(clues,f).color,getattr(clues,f).arrow) for f in FIELDS)


def observed_card(row, card, by_id):
    """Read values as observations, never as a reason to reject a printing."""
    import json
    from .settings import ROOT
    translations=json.loads((ROOT/'config/tcgdex-fr.json').read_text(encoding='utf-8'))
    result=normalize_card(card)
    for field in FIELDS:
        value=getattr(row.clues,field).value
        if value is None or not str(value).strip():continue
        value=str(value).strip();text=norm(value)
        if field in ('hp','pokedex'):
            numbers=[int(n) for n in re.findall(r'\d+',value)]
            if numbers:
                if field=='hp' and len(numbers)!=1:raise ValueError('Les PV sont illisibles. Collez une capture recadrée.')
                result['hp' if field=='hp' else 'pokedex']=numbers[0] if field=='hp' else numbers
            elif field=='hp':raise ValueError('Les PV sont illisibles. Collez une capture recadrée.')
        elif field=='type':
            aliases={norm(k):k for k in translations['types']}
            aliases.update({norm(v):k for k,v in translations['types'].items()})
            parts=[p.strip() for p in re.split(r'[/,;+|&]',value) if p.strip()]
            if any(norm(p) not in aliases for p in parts):raise ValueError('Le type est illisible. Collez une capture recadrée.')
            result['types']=[aliases[norm(p)] for p in parts]
            result['type_labels']=[translations['types'].get(t,t) for t in result['types']]
        elif field=='stage':
            aliases={'base':'Basic','de base':'Basic','basic':'Basic'}
            for n in (1,2):
                for label in (f'niveau {n}',f'stade {n}',f'stage {n}',f'stage{n}',f'niv. {n}',f'niv {n}',str(n)):aliases[label]=f'Stage{n}'
            aliases.update({norm(k):k for k in translations['stage']})
            aliases.update({norm(v):k for k,v in translations['stage'].items()})
            if text not in aliases:raise ValueError('Le stade est illisible. Collez une capture recadrée.')
            result['stage']=aliases[text];result['stage_label']=translations['stage'].get(result['stage'],value)
        elif field=='rarity':
            result=normalize_card(dict(result,rarity=value,rarity_label=value))
            result.pop('rarity_evidence',None)
        elif field=='illustrator':result['illustrator']=value
        elif field=='set':
            label=set_label(value)
            years=re.findall(r'\b(?:19|20)\d{2}\b',text)
            lookup=by_id.set_index if hasattr(by_id,'set_index') else set_index(by_id.values())
            sets=lookup.get(label,{})
            if len(sets)==1:
                selected=next(iter(sets.values()))
                for key in ('set_id','set_name','series_id','series_name','release_date','chronology'):result[key]=selected.get(key)
                result['release_year']=int(years[0]) if years else int(result['release_date'][:4]) if result.get('release_date') else None
                if years and (result.get('release_date') or '')[:4]!=years[0]:result['release_date']=None;result['chronology']=None
            elif text.isdigit() and len(text)==4:
                result['release_year']=int(text)
                if not (result.get('release_date') or '').startswith(text):result['release_date']=None;result['chronology']=None
            else:
                result.update(set_id='observed:'+text,set_name=value,series_id=None,series_name=None,release_date=None,chronology=None,release_year=int(years[0]) if years else None)
    return result


def resolve_capture(result, expected, previous, by_id):
    """Ignore exact old rows; prefer the suggestion, otherwise use the actual row."""
    fresh=[]
    for row in result.rows:
        old_match=False
        for attempt in previous:
            old=attempt.get('observed_card') or by_id.get(attempt['card_id'])
            if old and not visible_mismatches(row,old) and signature(row.clues)==signature_from_dict(attempt['clues']):
                old_match=True;break
        if not old_match:fresh.append(row)
    if not fresh:return None
    proposed=[r for r in fresh if (r.card_id==expected['id'] if r.card_id else norm(r.pokemon) in pokemon_names(expected))]
    selected=proposed or fresh
    unique={r.model_dump_json():r for r in selected}
    if len(unique)!=1:raise ValueError('Plusieurs nouvelles lignes sont visibles. Collez une capture recadrée sur le dernier résultat ; aucun indice n’a été enregistré.')
    row=next(iter(unique.values()))
    if row.card_id:
        base=by_id.get(row.card_id)
        if not base or base.get('category')!='Pokemon':raise ValueError('Identifiant de carte illisible ou inconnu. Collez une capture recadrée.')
        if norm(row.pokemon) not in pokemon_names(base):raise ValueError('Le nom et l’identifiant lus ne correspondent pas. Collez une capture recadrée.')
    else:
        pool=by_id.supported_pokemon if hasattr(by_id,'supported_pokemon') else by_id.values()
        candidates=[c for c in pool if c.get('category')=='Pokemon' and c.get('active',True) and norm(row.pokemon) in pokemon_names(c)]
        if not candidates:raise ValueError('Le nom de la carte est illisible ou absent du catalogue. Collez une capture recadrée.')
        # Visible attributes help identify an alternative printing. Discrepancies
        # still become authoritative observations after that identification.
        identity_row=row.model_copy(deep=True)
        for field in FIELDS:
            if field!='set':getattr(identity_row.clues,field).value=None
        identified=[c for c in candidates if not visible_mismatches(identity_row,c)]
        if identified:candidates=identified
        artist=row.clues.illustrator.value
        if artist:
            matching_artist=[c for c in candidates if norm(c.get('illustrator'))==norm(str(artist))]
            if matching_artist:candidates=matching_artist
        if any(c['id']==expected['id'] for c in candidates):
            matches=[expected]
        else:
            scores=[(len(visible_mismatches(row,c)),c) for c in candidates]
            best=min(s for s,c in scores)
            matches=[c for s,c in scores if s==best]
        base=next((c for c in matches if c['id']==expected['id']),matches[0])
        if len(matches)>1 and base['id']!=expected['id']:
            # No invented metadata when multiple printings remain indistinguishable.
            base=dict(base,image_url=None,image_path=None,number='?',identity_uncertain=True)
            for key in ('hp','pokedex','types','type_labels','stage','stage_label','rarity','rarity_label','set_id','set_name','series_id','series_name','release_date','chronology','illustrator'):
                if any(c.get(key)!=matches[0].get(key) for c in matches[1:]):base[key]=[] if key in ('pokedex','types','type_labels') else None
    return row,observed_card(row,base,by_id)


def signature_from_dict(clues):
    return tuple((clues[f]['color'],clues[f]['arrow']) for f in FIELDS)
