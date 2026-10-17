"""Cross-check exact printings; create a small, reproducible offline correction map."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--primary',type=Path,required=True,help='Raw TCGdex TypeScript checkout')
parser.add_argument('--secondary',type=Path,required=True,help='PokemonTCG/pokemon-tcg-data checkout with cards/en')
parser.add_argument('--output',type=Path,default=ROOT/'config/rarity-corrections.json')
args=parser.parse_args()
if not (args.secondary/'cards/en').is_dir():parser.error('cards/en absent de la source secondaire')
if not args.primary.is_dir() or not any(args.primary.rglob('*.ts')) or (args.primary/'catalog.fr.sqlite3').exists():
    parser.error('La source primaire doit être le checkout TypeScript brut TCGdex, pas le catalogue déjà corrigé.')
with tempfile.TemporaryDirectory(prefix='cartosolver-rarity-build-') as storage:
    os.environ['CARTO_STORAGE']=storage
    sys.path.insert(0,str(ROOT))
    from backend.app.importer import import_data
    from backend.app.db import engine
    from backend.app.rarity_enrichment import verified_correction
    from sqlalchemy import text
    import_data(args.primary,force=True)
    with engine.connect() as db:primary=[json.loads(r[0]) for r in db.execute(text('SELECT payload FROM cards ORDER BY id'))]
    secondary={}
    for path in sorted((args.secondary/'cards/en').glob('*.json')):
        for card in json.loads(path.read_text(encoding='utf-8')):
            if card['id'] in secondary:raise ValueError('Duplicate secondary ID: '+card['id'])
            secondary[card['id']]=card
    overrides=json.loads((ROOT/'config/card-overrides.json').read_text(encoding='utf-8'))
    result={}
    for card in primary:
        if not card.get('name') or card['id'] in overrides:continue
        evidence=verified_correction(card,secondary.get(card['id'],{}))
        if evidence:result[card['id']]=evidence
    commit=lambda p:subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()
    report={'source':{'repository':'https://github.com/PokemonTCG/pokemon-tcg-data','commit':commit(args.secondary),
                      'primary_repository':'https://github.com/tcgdex/cards-database','primary_commit':commit(args.primary),
                      'purpose':'Historical Rare / Rare Holo disambiguation; exact independent metadata match.'},
            'count':len(result),'cards':result}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'corrections':len(result),'source':report['source']},ensure_ascii=False,indent=2))
