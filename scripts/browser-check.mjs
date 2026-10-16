import { chromium } from '@playwright/test';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=process.env.CARTO_BROWSER_URL||'http://127.0.0.1:8000';
let manualPosts=0;page.on('request',r=>{if(r.url().endsWith('/api/game/attempts')&&r.method()==='POST')manualPosts++});
await page.goto(base);
await page.getByTestId('pending-attempt').filter({hasText:'Lucario'}).waitFor();
if(await page.locator('input[type="password"]').count())throw Error('A public app must not ask for an access code');
for(const text of ['La bonne carte est','VOTRE PROCHAINE DÉDUCTION','La piste à suivre','Sélection déterministe','Espace privé','LE RITUEL']){if(await page.getByText(text,{exact:false}).count())throw Error('Decorative content still present: '+text)}
await page.getByRole('button',{name:'Nouvelle partie',exact:true}).click();
await page.getByRole('heading',{name:'Lucario',exact:true}).waitFor();
await page.getByTestId('pending-attempt').filter({hasText:'Lucario'}).waitFor();
if(await page.getByRole('button').count()!==1)throw Error('Only Nouvelle partie should be actionable');
await page.reload();await page.getByTestId('pending-attempt').filter({hasText:'Lucario'}).waitFor();
await page.screenshot({path:'storage/desktop.png',fullPage:true});
console.log('New game and reload: Lucario is already in the investigation, awaiting capture.');
async function paste(){await page.evaluate(async()=>{const blob=await new Promise(resolve=>{const c=document.createElement('canvas');c.width=20;c.height=20;c.getContext('2d').fillRect(0,0,20,20);c.toBlob(resolve)});const dt=new DataTransfer();dt.items.add(new File([blob],'capture.png',{type:'image/png'}));window.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true}))})}
if(process.env.CARTO_TEST_REAL_PIPELINE==='1'){
 let solved=false;
 for(let i=0;i<8;i++){
  const before=await page.request.get(base+'/api/game').then(r=>r.json());
  await paste();
  let after;
  for(let poll=0;poll<150;poll++){
   after=await page.request.get(base+'/api/game').then(r=>r.json());
   if(after.version>before.version)break;
   if(await page.getByRole('alert').count())throw Error(await page.getByRole('alert').textContent());
   await new Promise(r=>setTimeout(r,200));
  }
  await page.waitForFunction(()=>!document.querySelector('.spin'),{},{timeout:30000});
  if(after.version!==before.version+1)throw Error('Paste did not automatically commit the expected card');
  if(after.history.at(-1).card.id!==before.pending.card.id)throw Error('Wrong expected card completed');
  if(after.solved){solved=true;break}
  await page.getByTestId('pending-attempt').filter({hasText:after.pending.card.name}).waitFor();
 }
 if(!solved)throw Error('Automatic full game did not finish');
 console.log('Native paste → real HTTP upload → Ollama test server → automatic commit → next card: full game passed.');
}else{
 // UI-only check: the backend's automatic state is mocked; no manual save request is allowed.
 const state=await page.request.get(base+'/api/game').then(r=>r.json());
 const greens=Object.fromEntries(['pokedex','type','stage','hp','rarity','set','illustrator'].map(f=>[f,{color:'green',arrow:null}]));
 const done={...state,version:state.version+1,solved:true,pending:null,history:[{id:1,card:state.recommendation,clues:greens,remaining:1,created:new Date().toISOString()}]};
 await page.route('**/api/game/analyze',route=>route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({job_id:'browser-test',version:state.version})}));
 await page.route('**/api/analysis/browser-test',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'done',game_id:state.id,game:done,duplicate:false})}));
 await paste();await page.getByText('CARTE TROUVÉE',{exact:true}).waitFor();
 if(await page.getByTestId('pending-attempt').count())throw Error('Completed card still pending');
 console.log('Native paste renders an automatic server result without a verification form or manual save.');
}
if(manualPosts)throw Error('The browser must never post manual attempts');
if(await page.locator('select,input[type="file"]').count())throw Error('Manual entry or file picker still present');
await page.setViewportSize({width:390,height:844});
await page.screenshot({path:'storage/mobile.png',fullPage:true});
if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth))throw Error('Mobile horizontal overflow');
if(errors.length)throw Error(errors.join('\n'));
console.log('Desktop/mobile: no console errors or overflow; only Nouvelle partie + native paste.');
await browser.close();
