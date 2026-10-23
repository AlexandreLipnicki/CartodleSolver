import {useState} from 'react'
import {ArrowDown,ArrowUp,Check,Pencil,X} from 'lucide-react'
import type {Field,Clue,Clues} from './main'

const fields:Field[]=['pokedex','type','stage','hp','rarity','set','illustrator']
const labels:Record<Field,string>={pokedex:'Pokémon',type:'Type',stage:'Stade',hp:'PV',rarity:'Rareté',set:'Extension',illustrator:'Illustrateur'}
const directional=new Set<Field>(['pokedex','hp','rarity','set'])
const proximity=new Set<Field>(['hp','rarity','set'])
const complete=(field:Field,clue?:Clue)=>!!clue&&(clue.color==='green'||field==='rarity'||!directional.has(field)||!!clue.arrow)

type Props={values:Record<Field,string>;pokemon:string;confirmed:Field[];enabled:boolean;busy:boolean;onSubmit:(clues:Clues)=>Promise<void>}
export function ManualFeedback({values,pokemon,confirmed,enabled,busy,onSubmit}:Props){
 const initial=()=>Object.fromEntries(fields.map(f=>[f,{color:confirmed.includes(f)?'green':'gray',arrow:null}])) as Partial<Clues>
 const [draft,setDraft]=useState<Partial<Clues>>(initial)
 const [active,setActive]=useState<Field|null>(null)
 const count=fields.filter(f=>complete(f,draft[f])).length
 const selected=active?draft[active]:undefined
 function color(value:Clue['color']){
  if(!active)return
  setDraft(old=>({...old,[active]:{color:value,arrow:value==='green'?null:old[active]?.arrow||null}}))
 }
 function arrow(value:Clue['arrow']){
  if(!active)return
  setDraft(old=>({...old,[active]:{color:old[active]?.color==='yellow'?'yellow':'gray',arrow:value}}))
 }
 const next=fields.find(f=>!complete(f,draft[f])&&f!==active)
 return <>
  {enabled&&<p className="manual-hint"><Pencil size={14}/>Cliquez sur les cases pour saisir les résultats <span>ou collez une capture avec Ctrl + V</span></p>}
  <div className="constraints-column"><div className="criteria-list">{fields.map(field=>{
   const clue=draft[field]
   return <button type="button" key={field} className={'criterion-tile manual-tile'+(clue?' feedback-'+clue.color:'')+(clue?.color==='green'?' confirmed':'')+(active===field?' active':'')} data-field={field} data-confirmed={clue?.color==='green'} data-color={clue?.color||'unset'} disabled={!enabled||busy} onClick={()=>setActive(field)} aria-label={labels[field]+' : '+values[field]+' · Modifier le résultat'} aria-expanded={active===field}>
    <span className="criterion-label">{labels[field]}</span>
    {clue?.color==='green'?<Check className="criterion-check" size={17}/>:enabled&&!busy&&clue?.color!=='yellow'&&<Pencil className="tile-pencil" size={13}/>}
    <span className="criterion-text">{field==='pokedex'&&pokemon&&<strong className="pokemon-name">{pokemon}</strong>}{values[field]}</span>
    {clue?.color==='yellow'&&<span className="tile-proximity">≈</span>}
    {clue?.arrow==='up'?<ArrowUp className="tile-arrow" size={24}/>:clue?.arrow==='down'?<ArrowDown className="tile-arrow" size={24}/>:null}
   </button>
  })}</div></div>
  {active&&enabled&&<section className="manual-editor" aria-label="Saisie manuelle" onKeyDown={e=>{if(e.key==='Escape')setActive(null)}}>
   <div className="manual-editor-heading"><div><strong>{labels[active]}</strong><span>Reproduisez la couleur et la flèche affichées dans Cartodle.</span></div><button type="button" className="manual-close" aria-label="Fermer la saisie" disabled={busy} onClick={()=>setActive(null)}><X size={18}/></button></div>
   <div className="manual-controls"><fieldset><legend>Couleur de la case</legend><div className="manual-options">
    <button type="button" className="choice-gray" aria-pressed={selected?.color==='gray'} disabled={busy} onClick={()=>color('gray')}>Invalide</button>
    {proximity.has(active)&&<button type="button" className="choice-yellow" aria-pressed={selected?.color==='yellow'} disabled={busy} onClick={()=>color('yellow')}>≈ Proche</button>}
    <button type="button" className="choice-green" aria-pressed={selected?.color==='green'} disabled={busy} onClick={()=>color('green')}><Check size={15}/>Correct</button>
   </div></fieldset>
   {directional.has(active)&&selected?.color!=='green'&&<fieldset><legend>{active==='rarity'?'Flèche (facultative)':'La valeur recherchée est…'}</legend><div className="manual-options">{active==='rarity'&&<button type="button" aria-pressed={!selected?.arrow} disabled={busy} onClick={()=>arrow(null)}>Sans flèche</button>}<button type="button" aria-pressed={selected?.arrow==='down'} disabled={busy} onClick={()=>arrow('down')}><ArrowDown size={17}/>Plus petite</button><button type="button" aria-pressed={selected?.arrow==='up'} disabled={busy} onClick={()=>arrow('up')}><ArrowUp size={17}/>Plus grande</button></div></fieldset>}
   </div>
   {confirmed.some(f=>draft[f]?.color!=='green')&&<p className="manual-correction-note">Correction : les anciens indices des critères modifiés seront écartés. Les autres informations restent conservées.</p>}
   <div className="manual-actions"><span role="status">{count} / 7 critères renseignés</span><div><button type="button" className="manual-reset" disabled={busy} onClick={()=>{setDraft(initial());setActive(null)}}>Annuler la saisie</button>{count<7?<button type="button" className="primary" disabled={busy||!next||!complete(active,draft[active])} onClick={()=>next&&setActive(next)}>Critère suivant</button>:<button type="button" className="primary" disabled={busy} onClick={()=>void onSubmit(draft as Clues)}>{busy?'Recherche…':'Proposer la carte suivante'}</button>}</div></div>
  </section>}
 </>
}
