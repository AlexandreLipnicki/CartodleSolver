"""One-command local bootstrap and startup (Windows/Linux/macOS)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)

def run(args,**kwargs):
    subprocess.run([str(a) for a in args],check=True,cwd=ROOT,**kwargs)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true',help='Installer et vérifier sans démarrer')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if sys.version_info<(3,11): raise RuntimeError('Python 3.11 ou supérieur est requis.')
    target=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if Path(sys.prefix).resolve()!=(ROOT/'.venv').resolve():
        if not target.exists():venv.EnvBuilder(with_pip=True).create(ROOT/'.venv')
        result=subprocess.run([str(target),str(Path(__file__).resolve()),*sys.argv[1:]],cwd=ROOT)
        return result.returncode
    npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
    if not npm or not shutil.which('node'):raise RuntimeError('Installez Node.js 22 LTS ou 24 LTS (npm inclus), puis relancez.')
    node=int(subprocess.check_output(['node','-p','process.versions.node.split(".")[0]'],text=True))
    if node<22:raise RuntimeError('Node.js 22+ est requis.')
    store=ROOT/'storage';store.mkdir(exist_ok=True)
    state_path=store/'setup-state.json'
    previous=json.loads(state_path.read_text()) if state_path.exists() else {}
    current={}
    requirements=hashlib.sha256((ROOT/'requirements.txt').read_bytes()).hexdigest()
    if previous.get('python')!=requirements:
        run([sys.executable,'-m','pip','install','-r','requirements.txt'])
    current['python']=requirements
    for folder,key in ((ROOT,'tools'),(ROOT/'frontend','frontend')):
        signature=hashlib.sha256((folder/'package-lock.json').read_bytes()).hexdigest()
        if previous.get(key)!=signature or not (folder/'node_modules').exists():
            subprocess.run([npm,'ci','--no-audit','--no-fund'],cwd=folder,check=True)
        current[key]=signature
    # Build on each launch so source changes are reflected in the served app.
    run([npm,'--prefix','frontend','run','build'])
    sys.path.insert(0,str(ROOT))
    from backend.app.settings import settings
    from backend.app.importer import import_data
    from backend.app.db import init_db
    init_db()
    source=settings.data
    if (source/'cards-database/data').exists():source=source/'cards-database'
    report=import_data(source)
    from backend.app.main import access_code
    access_code()
    print(f'Base vérifiée : {report["total"]} cartes, {report["sets"]} extensions.',flush=True)
    print('Code privé : valeur CARTO_INVITE_CODE de .env, ou fichier storage/access-code.txt.',flush=True)
    state_path.write_text(json.dumps(current),encoding='utf-8')
    if args.prepare:return 0
    with __import__('socket').socket() as sock:
        if sock.connect_ex(('127.0.0.1',args.port))==0:raise RuntimeError(f'Le port {args.port} est déjà utilisé. Fermez le serveur existant ou utilisez --port.')
    command=[sys.executable,'-m','uvicorn','backend.app.main:app','--host',args.host,'--port',str(args.port)]
    proc=subprocess.Popen(command,cwd=ROOT)
    url=f'http://127.0.0.1:{args.port}'
    try:
        ready=False
        for _ in range(120):
            if proc.poll() is not None:raise RuntimeError(f'Le serveur a quitté avec le code {proc.returncode}. Voir son erreur ci-dessus.')
            try:
                with urllib.request.urlopen(url+'/api/health',timeout=1) as r:
                    if json.load(r).get('status')=='ok':ready=True;break
            except Exception:time.sleep(.5)
        if not ready:raise RuntimeError('Le serveur ne répond pas dans le délai attendu. Voir les logs ci-dessus.')
        print(f'CartoSolver est disponible : {url} — Ctrl+C pour arrêter.',flush=True)
        if not args.no_browser:webbrowser.open(url)
        return proc.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':
    try:sys.exit(main())
    except (Exception,subprocess.CalledProcessError) as exc:
        print(f'\nÉCHEC DU LANCEMENT : {exc}',file=sys.stderr);sys.exit(1)
