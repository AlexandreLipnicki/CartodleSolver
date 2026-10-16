import json
from pathlib import Path
import shutil
import subprocess
import pytest
from backend.app.importer import import_data
from backend.app.db import Session,CardRecord
from backend.app.settings import ROOT

FIXTURES=Path(__file__).parent/'fixtures/tcgdex'

def test_real_tcgdex_typescript_to_sqlite(client):
    report=import_data(FIXTURES,force=True)
    assert report['total']==1 and report['invalid']==[]
    with Session() as db:
        c=json.loads(db.get(CardRecord,'xy10-63').payload)
    assert c['name']=='Lucario' and c['pokedex']==[448] and c['hp']==110
    assert c['types']==['Metal'] and c['rarity']=='Rare'
    assert c['set_name']=='Impact des Destins' and c['release_date']=='2016-05-02'
    assert c['stage_label']=='Niveau 1' and c['illustrator']=='Hitoshi Ariga'
    assert import_data(FIXTURES)['total']==1  # no repeat import

def test_conflicting_duplicate_preserves_database(client,tmp_path):
    shutil.copytree(FIXTURES,tmp_path/'data')
    extra=tmp_path/'data/XY/Duplicate';extra.mkdir()
    text=(FIXTURES/'XY/Fates Collide/63.ts').read_text()
    (extra/'63.ts').write_text(text.replace('hp: 110','hp: 120'))
    with pytest.raises(ValueError,match='contradictoire'):import_data(tmp_path/'data',force=True)
    with Session() as db:
        c=json.loads(db.get(CardRecord,'xy10-63').payload)
    assert c['hp']==110

def test_ast_never_executes_code(tmp_path):
    shutil.copytree(FIXTURES,tmp_path/'data')
    payload=tmp_path/'executed'
    (tmp_path/'data/evil.ts').write_text(f"import fs from 'node:fs'; const card = fs.writeFileSync('{payload.as_posix()}', 'bad'); export default card")
    output=tmp_path/'parsed.json'
    subprocess.run(['node',str(ROOT/'scripts/parse-tcgdex.mjs'),str(tmp_path/'data'),str(output)],check=True,capture_output=True)
    result=json.loads(output.read_text())
    assert len(result['cards'])==1 and len(result['invalid'])==1
    assert not payload.exists()
