import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowDown, ArrowUp, Check, Clipboard, LoaderCircle, Plus, ScanLine, AlertTriangle } from 'lucide-react'
import './style.css'

type Field = 'pokedex'|'type'|'stage'|'hp'|'rarity'|'set'|'illustrator'
type Clue = {color:'green'|'yellow'|'gray';arrow:'up'|'down'|null;value?:string|number|null}
type Clues = Record<Field,Clue>
type Card = {id:string;name:string|null;pokedex:number[];type_labels:string[];stage_label:string|null;hp:number|null;rarity_label:string|null;set_name:string|null;series_name:string|null;release_date:string|null;illustrator:string|null;number:string;names:Record<string,string>}
type Attempt = {id:number;card:Card;clues:Clues;remaining:number;created:string}
type Summary = {min?:number|null;max?:number|null;values:(string|number)[];count:number;excluded?:(string|number)[]}
type Game = {id:string;version:number;total:number;remaining:number;uncertain:number;recommendation:Card|null;solved:boolean;probable_solution:boolean;pending:{card:Card;number:number;status:string}|null;constraints:Record<Field,Summary>;warnings:string[];history:Attempt[]}
const fields:Field[]=['pokedex','type','stage','hp','rarity','set','illustrator']
const labels:Record<Field,string>={pokedex:'Pokédex',type:'Type',stage:'Stade',hp:'PV',rarity:'Rareté',set:'Extension',illustrator:'Illustrateur'}
class ApiError extends Error {status:number;constructor(message:string,status:number){super(message);this.status=status}}
async function api<T>(url:string,options:RequestInit={}):Promise<T>{
 const res=await fetch('/api'+url,{...options,headers:options.body instanceof FormData?undefined:{'Content-Type':'application/json',...options.headers}})
 if(!res.ok){const body=await res.json().catch(()=>({detail:'Le serveur ne répond pas.'}));const d=body.detail;throw new ApiError(typeof d==='string'?d:Array.isArray(d)?'Indices invalides : vérifiez les couleurs et les flèches.':d?.message||'Une erreur est survenue.',res.status)}
 return res.json()
}
function CardImage({card,small=false}:{card:Card;small?:boolean}){
 const [failed,setFailed]=useState(false),[loaded,setLoaded]=useState(false)
 useEffect(()=>{setFailed(false);setLoaded(false)},[card.id])
 return <div className={'card-visual '+(small?'small':'')}>
  {!loaded&&<div className={'card-fallback '+(small?'small':'')}><div className="orb"/><span>{card.name||card.names.en||card.id}</span>{failed&&<small>Illustration indisponible</small>}</div>}
  {!failed&&<img className={small?'card-image small':'card-image'} style={{opacity:loaded?1:0}} src={'/api/images/'+encodeURIComponent(card.id)} alt={`${card.name} — ${card.set_name} · ${card.number}`} onLoad={()=>setLoaded(true)} onError={()=>setFailed(true)}/>}
 </div>
}
function Logo(){return <div className="brand"><div className="brandmark"><ScanLine size={21}/></div><span>Carto<span className="brand-light">Solver</span></span></div>}
function App(){
 const [ready,setReady]=useState(false),[game,setGame]=useState<Game|null>(null)
 const [error,setError]=useState(''),[feedback,setFeedback]=useState(''),[busy,setBusy]=useState(false),[phase,setPhase]=useState('')
 const mounted=useRef(true),gameRef=useRef<Game|null>(null),busyRef=useRef(false)
 useEffect(()=>{gameRef.current=game},[game])
 useEffect(()=>{mounted.current=true;api<{has_game:boolean}>('/session',{method:'POST'}).then(async m=>{const next=await api<Game>(m.has_game?'/game':'/games',m.has_game?{}:{method:'POST'});if(mounted.current){gameRef.current=next;setGame(next);setReady(true)}}).catch(e=>{if(mounted.current){setError(e.message);setReady(true)}});return()=>{mounted.current=false}},[])
 async function newGame(){if(busyRef.current)return;busyRef.current=true;setBusy(true);setError('');try{const next=await api<Game>('/games',{method:'POST'});gameRef.current=next;setGame(next);setFeedback('')}catch(e){setError((e as Error).message)}finally{busyRef.current=false;setBusy(false)}}
 const processFile=useCallback(async(file:File)=>{
  const current=gameRef.current
  if(!current){setError('Créez une partie avant d’importer une capture.');return}
  if(current.solved){setError('Cette partie est terminée. Cliquez sur Nouvelle partie.');return}
  if(busyRef.current)return
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){setError('Utilisez une image PNG, JPG ou WEBP.');return}
  if(file.size>8*1024*1024){setError('La capture dépasse la limite de 8 Mo.');return}
  busyRef.current=true;setBusy(true);setError('');setFeedback('');setPhase('Préparation de votre capture…')
  try{
   const form=new FormData();form.append('file',file)
   const job=await api<{job_id:string;version:number}>('/game/analyze',{method:'POST',body:form})
   let finished=false
   for(let i=0;i<1800;i++){
    await new Promise(r=>setTimeout(r,1000));if(!mounted.current)return
    const result=await api<{status:string;game?:Game;duplicate?:boolean;error?:string;game_id:string}>('/analysis/'+job.job_id)
    setPhase(result.status==='queued'?'En attente du lecteur d’image…':result.status==='calculating'?'Calcul de la prochaine carte…':'Lecture des résultats et vérification de la carte…')
    if(result.status==='error')throw Error(result.error)
    if(result.status==='done'){
     if(gameRef.current?.id!==result.game_id){throw Error('Cette capture appartient à une partie précédente. Recollez le résultat de la carte actuellement proposée.')}
     if(!result.game)throw Error('Réponse incomplète. Recollez votre capture.');
     if(result.game.version>=(gameRef.current?.version||0)){gameRef.current=result.game;setGame(result.game)}
     setFeedback(result.duplicate?'Capture déjà traitée. Collez votre nouveau résultat.':'');finished=true
     break
    }
   }
   if(!finished)throw Error('Le délai de lecture est dépassé. Recollez la capture.');
  }catch(e){setError((e as Error).message);try{const fresh=await api<Game>('/game');if(mounted.current){gameRef.current=fresh;setGame(fresh)}}catch{}}finally{busyRef.current=false;if(mounted.current){setBusy(false);setPhase('')}}
 },[])
 useEffect(()=>{if(!ready)return;const paste=(e:ClipboardEvent)=>{const item=Array.from(e.clipboardData?.items||[]).find(i=>i.type.startsWith('image/'));const f=item?.getAsFile();if(f){e.preventDefault();void processFile(f)}};window.addEventListener('paste',paste);return()=>window.removeEventListener('paste',paste)},[ready,processFile])
 const card=game?.recommendation
 if(!ready)return <div className="loading-screen"><LoaderCircle className="spin"/> Chargement…</div>
 return <div className="app">
  <header className="header"><Logo/><div className="header-actions"><button className="primary new-game" onClick={newGame} disabled={busy}><Plus size={16}/>Nouvelle partie</button></div></header>
  <main className="workspace">
   <section className="hero-panel">
    <div className="art-column">{card?<CardImage card={card}/>:<div className="card-fallback"><div className="orb"/><span>{game?'Aucune carte à proposer':'Une nouvelle énigme'}</span><small>{game?'Consultez les indices ou les données à vérifier.':'Lancez votre première partie'}</small></div>}</div>
    <div className="info-column"><div className="eyebrow">{game?.solved?'CARTE TROUVÉE':game?.probable_solution?'SOLUTION PROBABLE':'CARTE À ESSAYER'}</div><h2>{card?.name|| (game?'Affinons les indices':'À vous de jouer.')}</h2><p className="card-subtitle">{card?<>{card.set_name||'Extension inconnue'} <span>·</span> {card.release_date?.slice(0,4)||'Année inconnue'}</>:game?'Les données incomplètes restent à vérifier.':<>Commencez avec Lucario.<br/>Chaque résultat guidera le prochain essai.</>}</p>
    {card?<><div className="card-chips"><span>#{card.pokedex.join(' / ')}</span><span className="type-chip"><span className="metal-dot"/>{card.type_labels.join(' / ')}</span><span>{card.stage_label||'Stade inconnu'}</span><span>{card.hp} <small>PV</small></span></div><dl className="card-details"><div><dt>Rareté</dt><dd>{card.rarity_label||'À vérifier'}</dd></div><div><dt>Illustrateur</dt><dd>{card.illustrator||'À vérifier'}</dd></div><div><dt>Collection</dt><dd>N° {card.number} <span className="muted">· {card.id}</span></dd></div></dl></>:<p className="hero-start muted">Cliquez sur Nouvelle partie en haut de la page.</p>}
    </div>
    <div className="constraints-column"><div className="constraints-title"><span className="eyebrow">CRITÈRES</span></div><div className="criteria-list">{fields.map(f=>{const s=game?.constraints[f];const limited=!!game?.history.length;let text='—';if(limited&&s){text=s.count===0?'Aucune valeur connue':s.min!==undefined? s.min===s.max?`${s.min}${f==='hp'?' PV':''}`:`${s.min} — ${s.max}${f==='hp'?' PV':''}`:s.count<=2?s.values.join(' · '):`${s.count} possibilités`;}if(limited&&f==='hp'&&s?.values.length&&s.values.length<=4)text=s.values.join(' · ')+' PV';return <div className="criterion" key={f}><span>{labels[f]}</span><div className="criterion-result"><span className={'criterion-value '+(limited&&s?.count===1?'confirmed':'')} title={s?.values.join(', ')}>{limited&&s?.count===1&&<Check size={11}/>} {text}</span>{!!s?.excluded?.length&&<small title={s.excluded.join(', ')}>Exclu : {s.excluded.slice(0,2).join(' · ')}{s.excluded.length>2?'…':''}</small>}</div></div>})}</div></div>
   </section>
   <div className="stats-row"><span><strong>{game?.remaining.toLocaleString('fr-FR')??'—'}</strong> cartes compatibles</span>{!!game?.uncertain&&<span title="Métadonnées incomplètes : ces cartes ne sont pas proposées comme entièrement validées.">{game.uncertain.toLocaleString('fr-FR')} données incomplètes</span>}</div>
   {!!game?.warnings.length&&<p className="rule-warning" title={game.warnings.join(' ')}>Certains indices de proximité ne sont pas appliqués faute de règles confirmées.</p>}
   <section className="upload-panel" aria-live="polite"><div className="upload-icon">{busy&&phase?<LoaderCircle className="spin" size={21}/>:<Clipboard size={21}/>}</div><div className="upload-copy"><h3>{phase||(game?.solved?'Carte trouvée':'Collez votre résultat')}</h3><p>{game?.solved?'Nouvelle partie pour recommencer.':'PNG, JPG, WEBP · 8 Mo max.'}</p></div>{!game?.solved&&<span className="paste-shortcut"><kbd>Ctrl</kbd><span>+</span><kbd>V</kbd></span>}</section>
   {error&&<div className="message error" role="alert"><AlertTriangle size={16}/><span>{error}</span></div>}
   {feedback&&<p className="capture-feedback" role="status">{feedback}</p>}
   <section className="history-section"><div className="section-heading"><span>Le fil de votre enquête <span className="count-pill">{(game?.history.length||0)+(game?.pending?1:0)}</span></span></div>{!game?<div className="empty-history"><div><h3>Lucario ouvrira votre enquête.</h3><p>Cliquez sur Nouvelle partie. Son essai apparaîtra ici immédiatement.</p></div></div>:<div className="history-table"><div className="history-table-head"><span>CARTE PROPOSÉE</span><div>{fields.map(f=><span key={f}>{labels[f]}</span>)}</div><span>STATUT</span></div>{game.history.map((a,i)=><div className="history-row" key={a.id}><div className="history-card"><span className="attempt-index">{String(i+1).padStart(2,'0')}</span><CardImage card={a.card} small/><div><strong>{a.card.name||a.card.names.en}</strong><small>{a.card.set_name} · {a.card.number}</small></div></div><div className="clue-cells">{fields.map(f=><span title={labels[f]+' : '+a.clues[f].color} className={'clue-cell '+a.clues[f].color} key={f}>{a.clues[f].color==='green'?<Check size={14}/>:a.clues[f].arrow==='up'?<ArrowUp size={14}/>:a.clues[f].arrow==='down'?<ArrowDown size={14}/>:<span>•</span>}</span>)}</div><span className="remaining-cell">{a.remaining.toLocaleString('fr-FR')} restantes</span></div>)}{game.pending&&<div className="history-row pending-row" data-testid="pending-attempt"><div className="history-card"><span className="attempt-index">{String(game.pending.number).padStart(2,'0')}</span><CardImage card={game.pending.card} small/><div><strong>{game.pending.card.name}</strong><small>{game.pending.card.set_name} · {game.pending.card.number}</small></div></div><div className="clue-cells">{fields.map(f=><span title={labels[f]+' : en attente de capture'} className="clue-cell awaiting" key={f}>—</span>)}</div><span className="remaining-cell pending-status">{busy&&phase?'Lecture…':'À jouer · Ctrl + V'}</span></div>}</div>}</section>
  </main><footer className="footer">Données TCGdex · Pokémon © Nintendo / Creatures / GAME FREAK</footer>

 </div>
}
createRoot(document.getElementById('root')!).render(<App/> )
