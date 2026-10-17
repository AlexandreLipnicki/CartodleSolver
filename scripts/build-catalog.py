"""Compile official TypeScript once into a portable French-only SQLite catalog."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--output',type=Path,default=ROOT/'data/catalog.fr.sqlite3')
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='cartosolver-catalog-build-') as storage:
    # Isolate the build from all user sessions and existing runtime data.
    os.environ['CARTO_STORAGE']=storage
    sys.path.insert(0,str(ROOT))
    from backend.app.importer import import_data
    from backend.app.catalog import catalog
    from backend.app.prepared_catalog import write_catalog
    report=import_data(args.source,force=True)
    if (args.source/'.git').exists():
        report['source_commit']=subprocess.check_output(['git','-C',str(args.source),'rev-parse','HEAD'],text=True).strip()
    report['source_url']='https://github.com/tcgdex/cards-database'
    report['license']='MIT; docs/TCGDEX-LICENSE.txt'
    # Do not persist machine-specific filesystem paths into the distributable.
    report.pop('source',None)
    from backend.app.rarity_enrichment import corrections
    cards=list(catalog().values())
    report['rarity_enrichment']={'source':corrections()['source'],'applied':sum(bool(c.get('rarity_evidence')) for c in cards)}
    result=write_catalog(cards,report,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
