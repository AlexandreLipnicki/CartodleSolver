import asyncio
import hashlib
import io
import json
import logging
import secrets
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, delete, update
from starlette.concurrency import run_in_threadpool
from .settings import ROOT, settings
from .db import Session, init_db, UserSession, Game, Attempt, Meta
from .models import BatchInput, FIELDS, AttemptInput
from .catalog import catalog, pokemon_cards, search_cards
from .engine import filter_cards, recommend, summarize, norm, complete, rules, compare
from . import vision

log=logging.getLogger(__name__)
COOKIE='carto_session'
limits=defaultdict(deque)
jobs={}
tasks=set()
reservations=set()


@asynccontextmanager
async def lifespan(app):
    init_db()
    with Session() as db:
        indexed=db.get(Meta,'import') is not None
    if settings.auto_import and ((settings.data/'catalog.fr.sqlite3').exists() or (not indexed and any(settings.data.rglob('*.ts')))):
        from .importer import import_data
        await run_in_threadpool(import_data,settings.data)
    catalog.cache_clear(); catalog()
    await run_in_threadpool(lambda:pokemon_cards().filtered([],catalog()))
    yield
    for task in tasks: task.cancel()
    if tasks: await asyncio.gather(*tasks,return_exceptions=True)

app=FastAPI(title='CartoSolver',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
from .body_limit import BodyLimitMiddleware
app.add_middleware(BodyLimitMiddleware,max_upload_bytes=(settings.max_upload_mb+1)*1024*1024)

def throttle(key, count, window):
    current=time.monotonic()
    if len(limits)>10000:
        for k in list(limits):
            if not limits[k] or limits[k][-1]<current-3600: limits.pop(k,None)
    q=limits[key]
    while q and q[0]<current-window: q.popleft()
    if len(q)>=count: raise HTTPException(429,'Trop de requêtes. Patientez avant de réessayer.')
    q.append(current)

@app.middleware('http')
async def security(request:Request,call_next):
    if request.method in ('POST','PUT','PATCH','DELETE'):
        origin=request.headers.get('origin')
        allowed={str(request.base_url).rstrip('/')} | {x.strip().rstrip('/') for x in settings.allowed_origins.split(',') if x.strip()}
        if origin and origin.rstrip('/') not in allowed:
            return JSONResponse({'detail':'Origine non autorisée.'},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'detail':'Requête intersite refusée.'},status_code=403)
    if request.url.path.endswith('/analyze'):
        try:
            if int(request.headers.get('content-length','0'))>(settings.max_upload_mb+1)*1024*1024:
                return JSONResponse({'detail':'Capture trop volumineuse.'},status_code=413)
        except ValueError:
            return JSONResponse({'detail':'Taille invalide.'},status_code=400)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

def user(request:Request):
    token=request.cookies.get(COOKIE,'')
    digest=hashlib.sha256(token.encode()).hexdigest()
    with Session() as db:
        u=db.get(UserSession,digest)
        if not u or u.expires<int(time.time()): raise HTTPException(401,'Session expirée. Rechargez la page.')
    return u

def owned_game(db,u):
    g=db.get(Game,u.game_id) if u.game_id else None
    if not g or g.owner!=u.token_hash: raise HTTPException(404,'Créez une nouvelle partie.')
    return g

def history(db,g):
    return list(db.scalars(select(Attempt).where(Attempt.game_id==g.id).order_by(Attempt.id)))

def attempts_data(rows):
    return [dict(card_id=a.card_id,clues=json.loads(a.clues)) for a in rows]

def state(db,u):
    g=owned_game(db,u); hist=history(db,g); attempts=attempts_data(hist)
    valid,uncertain=filter_cards(pokemon_cards(),attempts,catalog())
    rec=catalog().get(g.recommendation) if g.recommendation else None
    if rec and not any(c['id']==rec['id'] for c in valid):
        rec=recommend(valid,attempts)
    solved=bool(hist) and all(json.loads(hist[-1].clues)[f]['color']=='green' for f in FIELDS)
    if solved:rec=catalog().get(hist[-1].card_id)
    pending=dict(card=rec,number=len(hist)+1,status='awaiting_capture') if rec and not solved else None
    return dict(pending=pending,probable_solution=len(valid)==1 and not uncertain and not solved,id=g.id,version=g.version,total=len(pokemon_cards()),remaining=len(valid),uncertain=len(uncertain),
                recommendation=rec,solved=solved,
                constraints=summarize(valid,uncertain,attempts,catalog()),
                warnings=warnings(attempts),
                history=[dict(id=a.id,card=catalog().get(a.card_id),clues=json.loads(a.clues),remaining=a.remaining,created=a.created) for a in hist])

def warnings(attempts):
    messages=[]
    if any(a['clues']['rarity']['color']!='green' for a in attempts) and not rules().get('rarity_groups'):
        messages.append('Groupes et ordre de rareté non confirmés : seule l’exclusion de la rareté exacte est appliquée. Les flèches de rareté restent à vérifier.')
    if not rules().get('series_proximity_verified'):
        messages.append('Regroupement des extensions non confirmé : les indices de proximité de série ne sont pas appliqués.')
    return messages

@app.get('/api/health')
def health():
    with Session() as db:
        report=db.get(Meta,'import')
    active=sum(bool(c.get('active',True)) for c in catalog().values())
    return {'status':'ok','indexed':bool(report),'cards':active,'archived_cards':len(catalog())-active,'pokemon':len(pokemon_cards())}

@app.post('/api/session')
def open_session(request:Request,response:Response):
    # Public access. The random cookie identifies a browser, never an IP address.
    existing=request.cookies.get(COOKIE,'')
    digest=hashlib.sha256(existing.encode()).hexdigest()
    with Session.begin() as db:
        current=db.get(UserSession,digest) if existing else None
        if current and current.expires>int(time.time()):
            return {'has_game':bool(current.game_id)}
        throttle(('session',request.client.host if request.client else 'unknown'),60,300)
        token=secrets.token_urlsafe(32)
        db.add(UserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),expires=int(time.time())+30*86400))
    response.set_cookie(COOKIE,token,max_age=30*86400,httponly=True,secure=settings.secure_cookies,samesite='strict',path='/')
    return {'has_game':False}

@app.post('/api/logout')
def logout(response:Response,u=Depends(user)):
    with Session.begin() as db:
        row=db.get(UserSession,u.token_hash); row.expires=0
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True}

@app.get('/api/me')
def me(u=Depends(user)):
    return {'anonymous':True,'has_game':bool(u.game_id),'cards':len(pokemon_cards())}

@app.get('/api/game')
def game(u=Depends(user)):
    with Session() as db: return state(db,u)

@app.post('/api/games')
def new_game(u=Depends(user)):
    throttle(('new',u.token_hash),20,60)
    with Session.begin() as db:
        current=db.get(UserSession,u.token_hash)
        rec=recommend([c for c in pokemon_cards() if complete(c)],[])
        g=Game(id=str(uuid.uuid4()),owner=u.token_hash,recommendation=rec['id'] if rec else None)
        db.add(g); db.flush(); current.game_id=g.id
        return state(db,current)

def apply_batch(db,u,body,replace=False):
    g=owned_game(db,u)
    if body.game_id!=g.id: raise HTTPException(409,'Une nouvelle partie a été créée. Rechargez avant d’enregistrer ces indices.')
    # Optimistic update holds SQLite's write lock; prevents stale simultaneous analyses.
    changed=db.execute(update(Game).where(Game.id==g.id,Game.version==body.expected_version).values(version=Game.version+1))
    if changed.rowcount!=1: raise HTTPException(409,'La partie a changé. Rechargez les indices avant de recommencer.')
    hist=history(db,g)
    if replace:
        if not hist: raise HTTPException(400,'Aucun essai à corriger.')
        db.delete(hist.pop())
    current=attempts_data(hist); known={a['card_id']:a for a in current}
    added=0
    for entry in body.attempts:
        c=catalog().get(entry.card_id)
        if not c or c['category']!='Pokemon': raise HTTPException(422,'Carte introuvable dans la base locale.')
        item=entry.model_dump()
        if entry.card_id in known:
            if all((known[entry.card_id]['clues'][f]['color'],known[entry.card_id]['clues'][f]['arrow']) == (item['clues'][f]['color'],item['clues'][f]['arrow']) for f in FIELDS): continue
            raise HTTPException(409,'Une autre lecture de cette carte existe déjà. Corrigez ou annulez le dernier essai.')
        trial=current+[item]
        valid,uncertain=filter_cards(pokemon_cards(),trial,catalog())
        if not valid and not uncertain:
            baseline_a,baseline_b=filter_cards(pokemon_cards(),current,catalog())
            baseline=baseline_a+baseline_b
            counts={f:sum(compare(t,c,f,getattr(entry.clues,f)) is not False for t in baseline) for f in FIELDS}
            ordered=sorted(counts,key=counts.get)
            labels={'pokedex':'Pokédex','type':'Type','stage':'Stade','hp':'PV','rarity':'Rareté','set':'Extension','illustrator':'Illustrateur'}
            conflicts=[f for f in ordered if counts[f]==0]
            diagnosis='Vérifiez en priorité : '+', '.join(labels[f] for f in (conflicts or ordered[:3]))+'.'
            raise HTTPException(409,{'message':'Ces indices éliminent toutes les cartes. '+diagnosis+' Aucun nouvel essai n’a été enregistré.',
                                     'card_id':entry.card_id,'fields':conflicts or ordered[:3], 'remaining_by_field':counts,
                                     'advice':'Vérifiez les couleurs, flèches et l’impression exacte dans le formulaire de correction.'})
        db.add(Attempt(game_id=g.id,card_id=entry.card_id,clues=entry.clues.model_dump_json(),remaining=len(valid)))
        current=trial; known[entry.card_id]=item; added+=1
    valid,uncertain=filter_cards(pokemon_cards(),current,catalog())
    rec=recommend(valid,current)
    if current and all(current[-1]['clues'][f]['color']=='green' for f in FIELDS):rec=catalog()[current[-1]['card_id']]
    g.recommendation=rec['id'] if rec else None
    db.flush()
    return state(db,u)

@app.post('/api/game/attempts')
def add_attempts(body:BatchInput,u=Depends(user)):
    throttle(('attempt',u.token_hash),60,60)
    with Session.begin() as db: return apply_batch(db,u,body)

@app.put('/api/game/last')
def correct(body:BatchInput,u=Depends(user)):
    if len(body.attempts)!=1: raise HTTPException(422,'Corrigez un seul essai à la fois.')
    with Session.begin() as db: return apply_batch(db,u,body,True)

@app.delete('/api/game/last')
def undo(version:int,game_id:str,u=Depends(user)):
    with Session.begin() as db:
        g=owned_game(db,u)
        if game_id!=g.id: raise HTTPException(409,'La partie active a changé.')
        changed=db.execute(update(Game).where(Game.id==g.id,Game.version==version).values(version=Game.version+1))
        if changed.rowcount!=1: raise HTTPException(409,'La partie a changé.')
        hist=history(db,g)
        if not hist: raise HTTPException(400,'Aucun essai à annuler.')
        db.delete(hist.pop()); attempts=attempts_data(hist)
        valid,_=filter_cards(pokemon_cards(),attempts,catalog()); rec=recommend(valid,attempts)
        g.recommendation=rec['id'] if rec else None; db.flush()
        return state(db,u)

@app.get('/api/cards')
def search(q:str='',u=Depends(user)):
    query=norm(q) or ''
    if len(query)<2: return []
    return search_cards(query)

@app.get('/api/game/candidates')
def candidates(offset:int=0,uncertain:bool=False,u=Depends(user)):
    with Session() as db:
        g=owned_game(db,u); valid,pending=filter_cards(pokemon_cards(),attempts_data(history(db,g)),catalog())
    offset=max(0,offset); selected=pending if uncertain else valid
    return {'cards':selected[offset:offset+40],'uncertain':len(pending),'total':len(selected)}

def finish_capture(job,result):
    from .capture import expected_row
    with Session.begin() as db:
        u=db.get(UserSession,job['owner'])
        if not u or u.expires<int(time.time()):raise ValueError('Session expirée. Rechargez la page avant de coller la capture.')
        g=owned_game(db,u)
        if g.id!=job['game_id'] or g.version!=job['version']:
            raise ValueError('La partie a changé pendant la lecture. Recollez le résultat de la carte actuellement proposée.')
        current=state(db,u)
        expected=current['recommendation']
        if not expected or expected['id']!=job['expected_card_id'] or current['solved']:
            raise ValueError('La carte attendue a changé. Recollez le résultat de la carte actuellement proposée.')
        row=expected_row(result,expected,attempts_data(history(db,g)),catalog())
        if row is None:
            return current,True
        body=BatchInput(game_id=g.id,expected_version=g.version,attempts=[AttemptInput(card_id=expected['id'],clues=row.clues)])
        return apply_batch(db,u,body),False


async def work(job_id,content):
    job=jobs[job_id]
    try:
        job['status']='queued'
        result=await vision.analyze(content,lambda:job.update(status='analyzing'),expected=catalog()[job['expected_card_id']])
        job['status']='calculating'
        job['game'],job['duplicate']=await run_in_threadpool(finish_capture,job,result)
        job['status']='done'
    except asyncio.CancelledError: raise
    except Exception as exc:
        job['status']='error'
        if isinstance(exc,HTTPException):
            job['error']=('La lecture donne des indices contradictoires. Recollez une capture plus nette du résultat de la carte proposée ; aucun nouvel indice n’a été enregistré.' if exc.status_code==409 else 'La capture n’a pas pu être enregistrée. Recollez le résultat de la carte proposée.')
        else:
            job['error']=str(exc) if isinstance(exc,ValueError) else 'L’analyse a échoué. Recollez une capture plus nette.'
        log.warning('Vision job failed: %s',type(exc).__name__)

@app.post('/api/game/analyze',status_code=202)
async def upload(file:UploadFile=File(...),u=Depends(user)):
    throttle(('vision',u.token_hash),12,300)
    for key in list(jobs):
        if jobs[key]['created']<time.time()-1800 and jobs[key]['status'] not in ('queued','analyzing','calculating'): jobs.pop(key)
    if sum(j['status'] in ('queued','analyzing','calculating') for j in jobs.values())+len(reservations)>=8:
        raise HTTPException(429,'La file d’analyse est pleine. Réessayez dans un instant.')
    if u.token_hash in reservations or any(j['owner']==u.token_hash and j['status'] in ('queued','analyzing','calculating') for j in jobs.values()):
        raise HTTPException(429,'Une capture est déjà en cours d’analyse pour votre partie.')
    reservations.add(u.token_hash)
    try:
        content=await file.read(settings.max_upload_mb*1024*1024+1)
        if len(content)>settings.max_upload_mb*1024*1024: raise HTTPException(413,'Capture trop volumineuse (8 Mo maximum).')
        try: content=await run_in_threadpool(vision.normalize_image,content)
        except ValueError as exc: raise HTTPException(422,str(exc))
        with Session() as db:
            current=state(db,u)
            if current['solved']:raise HTTPException(409,'Cette partie est terminée. Cliquez sur Nouvelle partie.')
            if not current['pending']:raise HTTPException(409,'Aucune carte attendue. Cliquez sur Nouvelle partie.')
            game_id,version=current['id'],current['version']
            expected_id=current['recommendation']['id']
        job_id=secrets.token_urlsafe(20)
        jobs[job_id]=dict(owner=u.token_hash,game_id=game_id,version=version,expected_card_id=expected_id,status='queued',created=time.time())
        task=asyncio.create_task(work(job_id,content)); tasks.add(task); task.add_done_callback(tasks.discard)
        return {'job_id':job_id,'version':version}
    finally:
        reservations.discard(u.token_hash)

@app.get('/api/analysis/{job_id}')
def analysis(job_id:str,u=Depends(user)):
    j=jobs.get(job_id)
    if not j or j['owner']!=u.token_hash: raise HTTPException(404,'Analyse introuvable ou expirée.')
    return {k:v for k,v in j.items() if k not in ('owner','created')}

@app.get('/api/images/{card_id}')
async def image(card_id:str,u=Depends(user)):
    c=catalog().get(card_id)
    if not c or not c.get('image_path'): return Response(status_code=404)
    folder=settings.storage/'images'; folder.mkdir(exist_ok=True)
    key=hashlib.sha256(card_id.encode()).hexdigest(); cached=folder/f'{key}.webp'; missing=folder/f'{key}.missing'
    if cached.exists(): return FileResponse(cached,media_type='image/webp')
    if missing.exists() and time.time()-missing.stat().st_mtime<86400: return Response(status_code=404)
    throttle(('images',u.token_hash),120,60)
    try:
        # Destination and path are derived solely from trusted local TCGdex metadata.
        parts=c['image_path'].split('/')
        if len(parts)!=4 or any(not p or p in ('.','..') for p in parts): return Response(status_code=404)
        from urllib.parse import quote
        url='https://assets.tcgdex.net/'+'/'.join(quote(p,safe='') for p in parts)+'/high.webp'
        async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
            async with client.stream('GET',url) as r:
                r.raise_for_status(); data=bytearray()
                async for chunk in r.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>4*1024*1024: raise ValueError('Image trop grande')
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            im.thumbnail((1000,1400)); temp=folder/f'{key}.{uuid.uuid4().hex}.tmp'; im.convert('RGB').save(temp,format='WEBP'); temp.replace(cached)
        return FileResponse(cached,media_type='image/webp')
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code==404: missing.touch()
        return Response(status_code=404)
    except (httpx.HTTPError,ValueError,OSError):
        return Response(status_code=404)

# No HTTP administration routes: reindex is an owner-only CLI command.
dist=ROOT/'frontend/dist'
if dist.exists():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')

@app.get('/')
def index():
    if not (dist/'index.html').exists(): raise HTTPException(503,'Construisez le frontend avec npm --prefix frontend run build.')
    return FileResponse(dist/'index.html')
