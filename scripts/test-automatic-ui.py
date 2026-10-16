"""Real browser/API/SQLite flow with a local HTTP Ollama simulator, no vision claims."""
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
with sqlite3.connect(ROOT/'data/catalog.fr.sqlite3') as db:
    cards=[json.loads(row[0]) for row in db.execute('SELECT payload FROM cards')]
target=next(c for c in cards if c['id']=='base1-58')
rows=[]

def numeric(a,b,near=False):
    return {'color':'green' if a==b else 'yellow' if near and abs(a-b)<=20 else 'gray','arrow':None if a==b else 'up' if a>b else 'down'}

def feedback(g):
    t=target;a,b=set(t['types']),set(g['types'])
    clues={'pokedex':numeric(t['pokedex'][0],g['pokedex'][0]),'hp':numeric(t['hp'],g['hp'],True),
           'type':{'color':'green' if a==b else 'yellow' if a&b else 'gray','arrow':None},
           'stage':{'color':'green' if t['stage']==g['stage'] else 'gray','arrow':None},
           'rarity':{'color':'green' if t['rarity']==g['rarity'] else 'gray','arrow':None},
           'set':{'color':'green' if t['set_id']==g['set_id'] else 'yellow' if t['series_id']==g['series_id'] else 'gray','arrow':None if t['release_date']==g['release_date'] else 'up' if t['release_date']>g['release_date'] else 'down'},
           'illustrator':{'color':'green' if t['illustrator']==g['illustrator'] else 'gray','arrow':None}}
    values={'pokedex':g['pokedex'][0],'hp':g['hp'],'type':' / '.join(g['type_labels']),'stage':g['stage_label'],
            'rarity':g['rarity_label'],'set':g['set_name'],'illustrator':g['illustrator']}
    for f,v in values.items():clues[f]['value']=v
    return {'pokemon':g['name'],'card_id':None,'clues':clues}

class OllamaFixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        try:
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.path=='/api/chat' and body['messages'][0]['images'] and body['format']['properties']['rows']
            text=body['messages'][0]['content']
            match=re.search(r'Carte attendue : (.*?) — (.*?) — n° (.*?)\.',text)
            assert match,'Expected card context missing'
            g=next(c for c in cards if (c['name'],c['set_name'],c['number'])==match.groups())
            rows.append(feedback(g))
            result=json.dumps({'message':{'content':json.dumps({'rows':rows},ensure_ascii=False)}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(result)));self.end_headers();self.wfile.write(result)
        except Exception:
            self.send_response(500);self.end_headers()

server=ThreadingHTTPServer(('127.0.0.1',0),OllamaFixture)
threading.Thread(target=server.serve_forever,daemon=True).start()
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='cartosolver-auto-browser-') as folder:
    env=dict(os.environ,CARTO_STORAGE=folder,CARTO_OLLAMA_URL=f'http://127.0.0.1:{server.server_port}',
             CARTO_BROWSER_URL=f'http://127.0.0.1:{port}',CARTO_BROWSER_CODE_FILE=str(Path(folder)/'access-code.txt'),CARTO_TEST_REAL_PIPELINE='1')
    with (Path(folder)/'server.log').open('w') as log:
        proc=subprocess.Popen([str(ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')),'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log)
        try:
            for _ in range(100):
                if proc.poll() is not None:raise RuntimeError((Path(folder)/'server.log').read_text())
                try:
                    with urllib.request.urlopen(env['CARTO_BROWSER_URL']+'/api/health',timeout=1) as r:
                        if json.load(r)['cards']==22242:break
                except Exception:time.sleep(.2)
            else:raise RuntimeError('Test application did not start')
            subprocess.run(['node','scripts/browser-check.mjs'],env=env,cwd=ROOT,check=True,timeout=90)
            assert len(rows)>=2,'Vision simulator was not exercised'
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
server.shutdown();server.server_close()
print('Automatic browser integration passed with simulated Ollama, without user-data changes.')
