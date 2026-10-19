"""Shared identities for catalog values and screenshot observations."""
import json
import re
import unicodedata
from functools import lru_cache
from .settings import ROOT


@lru_cache(maxsize=8192)
def norm(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c)).casefold().split()) if value else None


@lru_cache(maxsize=1)
def rarity_names():
    labels=json.loads((ROOT/'config/tcgdex-fr.json').read_text(encoding='utf-8'))['rarity']
    aliases={norm(k):k for k in labels}
    aliases.update({norm(v):k for k,v in labels.items()})
    # Identical rarities with word order differences, not rarity group guesses.
    for tail in ('',' V',' VMAX',' VSTAR',' LV.X'):
        canonical='Rare Holo'+tail
        aliases[norm('Rare Holo'+tail)]=canonical
        aliases[norm('Holo Rare'+tail)]=canonical
        labels[canonical]=canonical
    aliases['rare galerie']='Rare Galerie';labels['Rare Galerie']='Rare Galerie'
    aliases['rare pikachu']='Pikachu Rare';aliases['pikachu rare']='Pikachu Rare'
    labels['Pikachu Rare']='Rare Pikachu'
    for tail in ('',' V',' VMAX'):
        canonical='Shiny rare'+tail
        aliases[norm('Rare Chromatique'+tail)]=canonical
        aliases[norm('Chromatique Rare'+tail)]=canonical
        labels[canonical]='Rare Chromatique'+tail
    verified=json.loads((ROOT/'config/holopocket-rarities.json').read_text(encoding='utf-8'))
    for entry in verified['entries']:
        canonical=entry['canonical']
        aliases[norm(entry['label'])]=canonical
        aliases[norm(canonical)]=canonical
        labels[canonical]=entry['label']
    # The readable menu prefix uniquely identifies Special illustration rare.
    aliases[norm('Illustration Spéciale')]='Special illustration rare'
    return aliases,labels


@lru_cache(maxsize=512)
def rarity(value):
    if not value:return None
    text=norm(re.sub(r'[↑↓⇧⇩⬆⬇≈✓✔]',' ',value))
    text=re.sub(r'^rarete\s*:\s*','',text).strip(' ():')
    return rarity_names()[0].get(text,text)


def normalize_card(card):
    if not card.get('rarity'):return dict(card)
    value=rarity(card['rarity'])
    return dict(card,rarity=value,rarity_label=rarity_names()[1].get(value,card.get('rarity_label') or card['rarity']))


def set_identity(value):
    # Trainer/Galarian Gallery cards belong to the corresponding main expansion
    # in CartoDle, although TCGdex gives them separate subset identifiers.
    return re.sub(r'^(swsh\d+(?:\.\d+)?)(?:tg|gg)$',r'\1',value) if value else None


def pokemon_names(card):
    names={norm(card.get('name')),norm(card.get('names',{}).get('en'))}-{None}
    return names|{re.sub(r'\s+(?:vmax|vstar|v|gx|ex|break)$','',name) for name in names}


def set_label(value):
    return re.sub(r'\s*(?:[·•—–-]\s*)?\(?(?:19|20)\d{2}\)?\s*$','',norm(str(value)) or '').strip()


def set_index(cards):
    active,archived={},{}
    for card in cards:
        index=active if card.get('active',True) else archived
        for key in (norm(card.get('set_name')),norm(card.get('set_id'))):
            if key:index.setdefault(key,{})[card['set_id']]=card
    # Retired metadata remains available for old games, but cannot make a known
    # current extension ambiguous or erase its release date during OCR lookup.
    return {**archived,**active}
