"""Read an image with real Ollama and optionally compare to human-verified JSON.

Does not create a game, modify the catalog or persist the input screenshot.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app import vision
from backend.app.engine import norm
from backend.app.models import FIELDS, VisionResult
from backend.app.settings import settings


def comparable(field,value):
    if value is None:return None
    text=norm(str(value))
    if field in ('pokedex','hp'):
        return tuple(int(n) for n in re.findall(r'\d+',text))
    if field=='set':return re.sub(r'[\W_]+',' ',text).strip()
    return text


def differences(actual,expected):
    errors=[]
    if len(actual.rows)!=len(expected.rows):
        errors.append(f'rows: {len(actual.rows)} au lieu de {len(expected.rows)}')
    for i,(got,wanted) in enumerate(zip(actual.rows,expected.rows),1):
        if norm(got.pokemon)!=norm(wanted.pokemon):errors.append(f'ligne {i}, pokemon: {got.pokemon!r} au lieu de {wanted.pokemon!r}')
        for field in FIELDS:
            a,b=getattr(got.clues,field),getattr(wanted.clues,field)
            for part in ('color','arrow','value'):
                av,bv=getattr(a,part),getattr(b,part)
                equal=comparable(field,av)==comparable(field,bv) if part=='value' else av==bv
                if not equal:errors.append(f'ligne {i}, {field}.{part}: {av!r} au lieu de {bv!r}')
    return errors


async def main(args):
    if args.model:settings.ollama_model=args.model
    if args.url:settings.ollama_url=args.url
    if args.timeout:settings.ollama_timeout=args.timeout
    content=vision.normalize_image(args.image.read_bytes())
    expected=VisionResult.model_validate_json(args.expected.read_text(encoding='utf-8')) if args.expected else None
    proposed=None
    if not args.no_context:
        with sqlite3.connect((ROOT/'data/catalog.fr.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
            proposed=json.loads(db.execute('SELECT payload FROM cards WHERE id=?',(args.card,)).fetchone()[0])
    report={'model':settings.ollama_model,'image':args.image.name,'runs':[]}
    for n in range(args.runs):
        started=time.monotonic();raw_results=[]
        try:
            result=await vision.analyze(content,expected=proposed,on_raw=raw_results.append)
            errors=differences(result,expected) if expected else []
            entry={'run':n+1,'seconds':round(time.monotonic()-started,2),'result':result.model_dump(),'differences':errors,'passed':not errors}
        except ValueError as exc:
            entry={'run':n+1,'seconds':round(time.monotonic()-started,2),'error':str(exc),'passed':False}
        if raw_results:entry['raw_model_result']=raw_results[0]
        report['runs'].append(entry)
        print(json.dumps(entry,ensure_ascii=False,indent=2),flush=True)
    report['passed']=all(r['passed'] for r in report['runs'])
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('--expected',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--model')
    parser.add_argument('--url')
    parser.add_argument('--timeout',type=float)
    parser.add_argument('--runs',type=int,default=1,choices=range(1,11))
    parser.add_argument('--card',default='xy10-63')
    parser.add_argument('--no-context',action='store_true')
    sys.exit(asyncio.run(main(parser.parse_args())))
