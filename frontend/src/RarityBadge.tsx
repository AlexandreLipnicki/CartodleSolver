import { Crown } from 'lucide-react'
import rarities from '../../config/holopocket-rarities.json'

const normalize=(value:string)=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim().replace(/\s+/g,' ')
const entries=new Map(rarities.entries.flatMap(entry=>[
 [normalize(entry.canonical),entry], [normalize(entry.label),entry],
] as const))
const symbols:Record<string,string>={
 promo:'★','one-blue':'★','one-purple':'★','two-purple':'★★',
 'four-diamonds':'◆◆◆◆','one-gold':'★','two-gold':'★★',
 'two-rainbow':'✦✦','three-rainbow':'★★★',
}

export function RarityBadge({rarity,label}:{rarity?:string|null;label:string|null}){
 const entry=(rarity&&entries.get(normalize(rarity)))||(label&&entries.get(normalize(label)))
 if(!entry)return null
 return <span className={`rarity-badge rarity-badge--${entry.level}`} data-rarity-level={entry.level} aria-hidden="true">
  {entry.level==='crown'?<Crown size={13} strokeWidth={2.2}/>:symbols[entry.level]}
 </span>
}
