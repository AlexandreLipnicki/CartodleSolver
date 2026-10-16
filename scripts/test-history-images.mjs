// Real browser cache/lifecycle regression; game API and artwork are local fixtures.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from '@playwright/test';
const root=resolve('frontend/dist');
const cards=[['xy10-63','Lucario',448,110,'Impact des Destins'],['swsh8-142','Makuhita',296,90,'Poing de Fusion'],['sv2-3','Cotovol',189,90,'Évolutions à Paldea']].map(([id,name,dex,hp,set])=>({id,name,names:{fr:name,en:name},pokedex:[dex],hp,set_name:set,type_labels:['Métal'],stage_label:'Niveau 1',rarity_label:'Rare Holo',release_date:'2016-05-02',illustrator:'Illustrateur',number:id.split('-').at(-1)}));
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAB8AAAArCAIAAAAPJ8TVAAAAL0lEQVR4nO3MQQEAQAQAsHPtFVFBPSm8bAEW1fnW/L3abrfb7Xa73W632+32k/sArmUCPNddv0MAAAAASUVORK5CYII=','base64');
let step=0;const requests=new Map();
const clues=Object.fromEntries(['pokedex','type','stage','hp','rarity','set','illustrator'].map(f=>[f,{color:'gray',arrow:null}]));
const game=()=>({id:'image-regression',version:step,total:100,remaining:100-step,uncertain:0,solved:false,probable_solution:false,recommendation:cards[step],pending:{card:cards[step],number:step+1,status:'awaiting_capture'},constraints:{},warnings:[],history:cards.slice(0,step).map((card,i)=>({id:i+1,card,clues,remaining:99-i,created:'2026-10-16'}))});
const server=createServer(async(req,res)=>{
 const path=new URL(req.url,'http://localhost').pathname;
 const json=value=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value))};
 try{
  if(path==='/warm'){res.setHeader('Content-Type','text/html');return res.end(cards.map(c=>`<img src="/api/images/${c.id}">`).join(''))}
  if(path.startsWith('/api/images/')){requests.set(path,(requests.get(path)||0)+1);res.setHeader('Content-Type','image/png');res.setHeader('Cache-Control','private, max-age=31536000, immutable');return res.end(png)}
  if(path==='/api/session')return json({has_game:step>0});
  if(path==='/api/games'){step=0;return json(game())}
  if(path==='/api/game')return json(game());
  if(path==='/api/game/analyze'){step++;res.statusCode=202;return json({job_id:'test',version:step-1})}
  if(path==='/api/analysis/test')return json({status:'done',game_id:'image-regression',game:game()});
  const file=path==='/'?resolve(root,'index.html'):resolve(root,'.'+path);
  if(!file.startsWith(root+'/')){res.statusCode=404;return res.end()}
  res.setHeader('Content-Type',path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'text/html');res.end(await readFile(file));
 }catch(error){res.statusCode=500;res.end(String(error))}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
try{
 const page=await browser.newPage();const base=`http://127.0.0.1:${server.address().port}`;
 await page.goto(base+'/warm');await page.waitForFunction(()=>[...document.images].every(i=>i.complete&&i.naturalWidth>0));
 await page.goto(base);await page.getByTestId('pending-attempt').waitFor();
 async function visibleImages(){
  await page.waitForFunction(()=>{
   const images=[...document.querySelectorAll('.history-row img')];
   return images.length>0&&images.every(i=>i.complete&&i.naturalWidth>0&&getComputedStyle(i).opacity==='1')&&!document.querySelector('.history-row .card-fallback');
  },null,{timeout:10000});
 }
 await visibleImages();
 for(let i=1;i<=2;i++){
  await page.evaluate(async()=>{
   const canvas=document.createElement('canvas');canvas.width=20;canvas.height=20;
   const blob=await new Promise(resolve=>canvas.toBlob(resolve));const data=new DataTransfer();
   data.items.add(new File([blob],'capture.png',{type:'image/png'}));window.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true}));
  });
  await page.waitForFunction(n=>document.querySelectorAll('[data-testid="completed-attempt"]').length===n,i);
  await visibleImages();
  for(let j=0;j<i;j++)assert.equal(await page.getByTestId('completed-attempt').nth(j).locator('img').getAttribute('src'),'/api/images/'+cards[j].id);
 }
 await page.reload();await page.getByTestId('completed-attempt').first().waitFor();await visibleImages();
 for(const c of cards)assert.equal(requests.get('/api/images/'+c.id),1,'An already cached image was downloaded again');
 console.log('History images: two played cards and the pending card stay visible after successive pastes and reload; each image downloaded once.');
}finally{await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve))}
