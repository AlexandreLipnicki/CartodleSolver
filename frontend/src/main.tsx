import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowDown, ArrowUp, Check, Clipboard, LoaderCircle, Plus, ScanLine, AlertTriangle } from 'lucide-react'
import './style.css'
import { ManualFeedback } from './ManualFeedback'
import { RarityBadge } from './RarityBadge'

export type Field = 'pokedex'|'type'|'stage'|'hp'|'rarity'|'set'|'illustrator'
export type Clue = {color:'green'|'yellow'|'gray';arrow:'up'|'down'|null;value?:string|number|null}
export type Clues = Record<Field,Clue>
type Card = {id:string;name:string|null;pokedex:number[];type_labels:string[];stage_label:string|null;hp:number|null;rarity_label:string|null;rarity?:string|null;set_name:string|null;series_name:string|null;release_date:string|null;illustrator:string|null;number:string;names:Record<string,string>}
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
 return <CardArtwork key={card.id} card={card} small={small}/>
}
function CardArtwork({card,small}:{card:Card;small:boolean}){
 const [failed,setFailed]=useState(false),[loaded,setLoaded]=useState(false)
 return <div className={'card-visual '+(small?'small':'')}>
  {!loaded&&<div className={'card-fallback '+(small?'small':'')}><div className="orb"/><span>{card.name||card.names.en||card.id}</span>{failed&&<small>Illustration indisponible</small>}</div>}
  {!failed&&<img className={small?'card-image small':'card-image'} style={{opacity:loaded?1:0}} src={'/api/images/'+encodeURIComponent(card.id)} alt={`${card.name} — ${card.set_name} · ${card.number}`} onLoad={()=>setLoaded(true)} onError={()=>setFailed(true)}/>}
 </div>
}
const colorLabels={gray:'Incorrect',yellow:'Proche',green:'Correct'}
function historyValue(field:Field,clue:Clue,card:Card):string{
 if(clue.value!==null&&clue.value!==undefined&&String(clue.value).trim())return String(clue.value)
 switch(field){
  case 'pokedex':return card.pokedex.length?'n° '+card.pokedex.join(' / '):'—'
  case 'type':return card.type_labels.join(' / ')||'—'
  case 'stage':return card.stage_label||'—'
  case 'hp':return card.hp===null?'—':String(card.hp)
  case 'rarity':return card.rarity_label||'—'
  case 'set':return [card.set_name,card.release_date?.slice(0,4)].filter(Boolean).join('\n')||'—'
  case 'illustrator':return card.illustrator||'—'
 }
}
function HistoryClue({field,clue,card}:{field:Field;clue:Clue;card:Card}){
 const value=historyValue(field,clue,card)
 const read=clue.value!==null&&clue.value!==undefined&&String(clue.value).trim()!==''
 const direction=clue.arrow==='up'?'Supérieur':clue.arrow==='down'?'Inférieur':''
 const description=[labels[field],value,colorLabels[clue.color],direction,read?'Lu sur la capture':'Valeur du catalogue'].filter(Boolean).join(' · ')
 return <span className={'clue-cell '+clue.color} data-field={field} data-color={clue.color} data-arrow={clue.arrow||'none'} data-value-source={read?'capture':'catalog'} title={description} aria-label={description}>
  {field==='hp'&&clue.color==='yellow'&&<span className="clue-proximity" aria-label="Valeur proche">≈</span>}
  <span className="clue-value">{field==='pokedex'&&<strong className="pokemon-name">{card.name||card.names.en}</strong>}<span className="clue-reading">{value}</span></span>
  {clue.arrow==='up'?<ArrowUp className="clue-arrow" size={21} aria-label="Supérieur"/>:clue.arrow==='down'?<ArrowDown className="clue-arrow" size={21} aria-label="Inférieur"/>:clue.color==='green'?<Check className="clue-check" size={13} aria-label="Correct"/>:null}
 </span>
}
function Logo(){return <div className="brand"><div className="brandmark"><ScanLine size={21}/></div><span>Cartodle<span className="brand-light">-Solver</span></span></div>}
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
 async function submitManual(clues:Clues){
  const current=gameRef.current
  if(!current?.pending||busyRef.current)return
  busyRef.current=true;setBusy(true);setError('');setFeedback('')
  try{
   const next=await api<Game>('/game/attempts',{method:'POST',body:JSON.stringify({game_id:current.id,expected_version:current.version,attempts:[{card_id:current.pending.card.id,clues}]})})
   gameRef.current=next;setGame(next)
  }catch(e){
   setError((e as Error).message)
   try{const fresh=await api<Game>('/game');gameRef.current=fresh;setGame(fresh)}catch{}
  }finally{busyRef.current=false;setBusy(false)}
 }
 const card=game?.recommendation
 if(!ready)return <div className="loading-screen"><LoaderCircle className="spin"/> Chargement…</div>
 return <div className="app">
  <header className="header"><Logo/><div className="header-actions"><button className="primary new-game" onClick={newGame} disabled={busy}><Plus size={16}/>Nouvelle partie</button></div></header>
  <main className="workspace">
   <section className="hero-panel">
    <div className="recommendation-preview">
     <div className="art-column">{card?<CardImage card={card}/>:<div className="card-fallback"><div className="orb"/><span>{game?'Aucune carte à proposer':'Une nouvelle énigme'}</span></div>}</div>
     <div className="info-column">
      <div className="eyebrow">{game?.solved?'CARTE TROUVÉE':game?.probable_solution?'SOLUTION PROBABLE':'CARTE À ESSAYER'}</div>
      <h2>{card?.name|| (game?'Affinons les indices':'À vous de jouer.')}</h2>
      {card?<div className="preview-meta"><p className="card-subtitle">{card.set_name||'Extension inconnue'} <span>·</span> {card.release_date?.slice(0,4)||'Année inconnue'}</p><div className="rarity-detail"><RarityBadge rarity={card.rarity} label={card.rarity_label}/><span>{card.rarity_label||'Rareté inconnue'}</span></div></div>:<p className="card-subtitle">{game?'Aucune proposition avec les indices actuels.':'Commencez avec Lucario.'}</p>}
     </div>
    </div>
    <ManualFeedback key={(game?.id||'empty')+':'+(game?.version||0)} values={Object.fromEntries(fields.map(f=>[f,card?historyValue(f,{color:'gray',arrow:null},card):'—'])) as Record<Field,string>} pokemon={card?.name||''} confirmed={fields.filter(f=>game?.history.some(a=>a.clues[f].color==='green'))} enabled={!!game?.pending&&!game.solved} busy={busy} onSubmit={submitManual}/>
    {game&&<div className="hero-count"><strong>{game.remaining.toLocaleString('fr-FR')}</strong> cartes possibles</div>}
   </section>
   <section className="upload-panel" aria-live="polite"><div className="upload-icon">{busy&&phase?<LoaderCircle className="spin" size={21}/>:<Clipboard size={21}/>}</div><div className="upload-copy"><h3>{phase||(game?.solved?'Carte trouvée':'Collez votre résultat')}</h3><p>{game?.solved?'Nouvelle partie pour recommencer.':'PNG, JPG, WEBP · 8 Mo max.'}</p></div>{!game?.solved&&<span className="paste-shortcut"><kbd>Ctrl</kbd><span>+</span><kbd>V</kbd></span>}</section>
   {error&&<div className="message error" role="alert"><AlertTriangle size={16}/><span>{error}</span></div>}
   {feedback&&<p className="capture-feedback" role="status">{feedback}</p>}
   <section className="history-section"><div className="section-heading"><span>Tentatives <span className="count-pill">({(game?.history.length||0)+(game?.pending?1:0)})</span></span></div>{!game?<div className="empty-history"><div><h3>Lucario ouvrira votre enquête.</h3><p>Cliquez sur Nouvelle partie. Son essai apparaîtra ici immédiatement.</p></div></div>:<div className="history-table"><div className="history-table-head"><span>CARTE JOUÉE</span><div>{fields.map(f=><span key={f}>{f==='pokedex'?'Pokémon':labels[f]}</span>)}</div></div>{game.pending&&<div className="history-row pending-row" data-testid="pending-attempt" data-card-id={game.pending.card.id}><div className="history-card"><CardImage card={game.pending.card} small/></div><div className="clue-cells">{fields.map(f=><span title={labels[f]+' : en attente de capture'} className="clue-cell awaiting" key={f}>—</span>)}</div></div>}{[...game.history].reverse().map(a=><div className="history-row" data-testid="completed-attempt" data-card-id={a.card.id} key={a.id}><div className="history-card"><CardImage card={a.card} small/></div><div className="clue-cells">{fields.map(f=><HistoryClue key={f} field={f} clue={a.clues[f]} card={a.card}/>)}</div></div>)}</div>}</section>
  </main><footer className="footer">Données TCGdex · Pokémon © Nintendo / Creatures / GAME FREAK</footer>

 </div>
}
createRoot(document.getElementById('root')!).render(<App/> )
