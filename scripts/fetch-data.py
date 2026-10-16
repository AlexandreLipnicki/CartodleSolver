"""Optional download of audited official TCGdex data; preserves existing files."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
COMMIT='4199850a6af49665db0080fa2bb9ef751750a406'
dest=ROOT/'data/cards-database'
if dest.exists():
    print(f'{dest} existe déjà. Aucun fichier remplacé.');sys.exit(1)
if any((ROOT/'data').rglob('*.ts')):
    print('Des données TCGdex existent déjà dans data/. Aucun téléchargement nécessaire.');sys.exit(0)
subprocess.run(['git','clone','--no-checkout','--filter=blob:none','https://github.com/tcgdex/cards-database.git',str(dest)],check=True)
subprocess.run(['git','-C',str(dest),'checkout','--detach',COMMIT],check=True)
print('Données officielles installées dans data/cards-database. Attribution : docs/TCGDEX-LICENSE.txt.')
