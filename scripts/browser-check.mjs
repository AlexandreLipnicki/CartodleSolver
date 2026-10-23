import { chromium } from '@playwright/test';
import {readFile} from 'node:fs/promises';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=process.env.CARTO_BROWSER_URL||'http://127.0.0.1:8000';
let manualPosts=0;page.on('request',r=>{if(r.url().endsWith('/api/game/attempts')&&r.method()==='POST')manualPosts++});
await page.goto(base);
await page.locator('[data-testid="pending-attempt"][data-card-id="xy10-63"]').waitFor();
if(await page.locator('input[type="password"]').count())throw Error('A public app must not ask for an access code');
for(const text of ['La bonne carte est','VOTRE PROCHAINE DÉDUCTION','La piste à suivre','Sélection déterministe','Espace privé','LE RITUEL']){if(await page.getByText(text,{exact:false}).count())throw Error('Decorative content still present: '+text)}
await page.getByRole('button',{name:'Nouvelle partie',exact:true}).click();
await page.getByRole('heading',{name:'Lucario',exact:true}).waitFor();
await page.locator('[data-testid="pending-attempt"][data-card-id="xy10-63"]').waitFor();
if(await page.locator('.manual-tile').count()!==7)throw Error('Seven editable criteria are required');
await page.reload();await page.locator('[data-testid="pending-attempt"][data-card-id="xy10-63"]').waitFor();
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
  await page.locator(`[data-testid="pending-attempt"][data-card-id="${after.pending.card.id}"]`).waitFor();
 }
 if(!solved)throw Error('Automatic full game did not finish');
 console.log('Native paste → real HTTP upload → Ollama test server → automatic commit → next card: full game passed.');
}else if(process.env.CARTO_TEST_MANUAL==='1'){
 const state=await page.request.get(base+'/api/game').then(r=>r.json());
 const tile=field=>page.locator(`.manual-tile[data-field="${field}"]`);
 const editor=page.getByRole('region',{name:'Saisie manuelle'});
 await tile('type').click();
 if(await editor.getByRole('button',{name:'Invalide',exact:true}).getAttribute('aria-pressed')!=='true')throw Error('Invalid must be preselected');
 if(await editor.getByRole('button',{name:'Proche',exact:false}).count())throw Error('Type must not offer Proche');
 await tile('pokedex').click();
 if(await editor.getByRole('button',{name:'Invalide',exact:true}).getAttribute('aria-pressed')!=='true')throw Error('Gray must be preselected for directional fields too');
 if(await editor.getByRole('button',{name:'Critère suivant',exact:true}).isEnabled())throw Error('Pokédex still requires a direction');
 if(await editor.getByRole('button',{name:'Sans flèche',exact:true}).count())throw Error('Only rarity can omit directions');
 await tile('rarity').click();
 await editor.getByRole('button',{name:'Proche',exact:false}).click();
 await editor.getByRole('button',{name:'Plus grande',exact:false}).click();
 await editor.getByRole('button',{name:'Sans flèche',exact:true}).click();
 if(await tile('rarity').locator('.tile-arrow').count())throw Error('No arrow must clear rarity direction');
 if(await tile('rarity').getAttribute('data-color')!=='yellow')throw Error('Removing rarity arrow must retain yellow');
 if(!await editor.getByRole('button',{name:'Critère suivant',exact:true}).isEnabled())throw Error('Yellow rarity without an arrow must be complete');
 await tile('hp').click();
 await editor.getByRole('button',{name:'Proche',exact:false}).click();
 await editor.getByRole('button',{name:'Plus petite',exact:false}).click();
 if(await tile('hp').getAttribute('data-color')!=='yellow')throw Error('HP must become yellow');
 if(await editor.getByRole('button',{name:'Sans flèche',exact:true}).count())throw Error('HP must still require a direction');
 await editor.getByRole('button',{name:'Correct',exact:true}).click();
 if(await tile('hp').locator('.tile-arrow').count())throw Error('Green must clear the arrow');
 await editor.getByRole('button',{name:'Invalide',exact:true}).click();
 if(await tile('hp').locator('.tile-arrow').count())throw Error('Leaving green must require a new arrow');
 const reference=JSON.parse(await readFile('backend/tests/fixtures/cartodle/lucario.expected.json','utf8')).rows[0];
 reference.clues.rarity.arrow=null;
 for(const [field,clue] of Object.entries(reference.clues)){
  await tile(field).click();
  if(['type','stage','illustrator','pokedex'].includes(field)&&await editor.getByRole('button',{name:'Proche',exact:false}).count())throw Error('Unsupported yellow option');
  if(['type','stage','illustrator'].includes(field)&&await editor.getByRole('button',{name:'Plus grande',exact:false}).count())throw Error('Unsupported direction');
  if(field!=='pokedex')await editor.getByRole('button',{name:clue.color==='yellow'?'≈ Proche':'Invalide',exact:true}).click();
  // Direction alone on a previously untouched gray Pokémon tile is sufficient.
  if(clue.arrow)await editor.getByRole('button',{name:clue.arrow==='down'?'Plus petite':'Plus grande',exact:false}).click();
 }
 await page.route('**/api/game/attempts',route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Ces indices sont contradictoires. Vérifiez les cases.'})}),{times:1});
 await editor.getByRole('button',{name:'Proposer la carte suivante',exact:true}).click();
 await page.getByRole('alert').filter({hasText:'contradictoires'}).waitFor();
 await page.waitForFunction(()=>!document.querySelector('.manual-editor .primary').disabled);
 if(!(await editor.innerText()).includes('7 / 7'))throw Error('Manual draft lost after an error');
 await page.setViewportSize({width:390,height:900});
 await page.screenshot({path:'storage/manual-mobile.png',fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Manual editor overflows mobile');
 await page.setViewportSize({width:1440,height:1000});
 await page.screenshot({path:'storage/manual-desktop.png',fullPage:true});
 await editor.getByRole('button',{name:'Proposer la carte suivante',exact:true}).click();
 await page.getByTestId('completed-attempt').waitFor();
 const after=await page.request.get(base+'/api/game').then(r=>r.json());
 if(after.version!==state.version+1||after.history.length!==1)throw Error('Manual attempt did not commit exactly once');
 for(const [f,c] of Object.entries(reference.clues)){
  if(after.history[0].clues[f].color!==c.color||after.history[0].clues[f].arrow!==c.arrow)throw Error('Manual clue changed: '+f);
 }
 if(await page.locator('.manual-editor').count())throw Error('Manual draft was not reset after success');
 if(manualPosts!==2)throw Error('Unexpected manual request count');
 console.log('Manual entry: valid colors/arrows, draft retained after error, real API commit, next card and mobile layout passed.');
}else if(process.env.CARTO_TEST_REFERENCE_CAPTURE==='1'){
 const reference=JSON.parse(await readFile('backend/tests/fixtures/cartodle/lucario.expected.json','utf8')).rows[0];
 const state=await page.request.get(base+'/api/game').then(r=>r.json());
 const bytes=await readFile('backend/tests/fixtures/cartodle/lucario.recreated.png');
 await page.evaluate(async data=>{
  const binary=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
  const dt=new DataTransfer();dt.items.add(new File([binary],'lucario.recreated.png',{type:'image/png'}));
  window.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true}));
 },bytes.toString('base64'));
 const completed=page.getByTestId('completed-attempt');await completed.waitFor();
 for(const [field,clue] of Object.entries(reference.clues)){
  const cell=completed.locator(`[data-field="${field}"]`);
  if(await cell.getAttribute('data-color')!==clue.color)throw Error(field+': wrong background');
  if(await cell.getAttribute('data-arrow')!==(clue.arrow||'none'))throw Error(field+': wrong arrow');
  if((await cell.locator('.clue-reading').innerText())!==String(clue.value))throw Error(field+': wrong displayed value');
  if(await cell.locator('.clue-arrow').count()!==(clue.arrow?1:0))throw Error(field+': missing visible arrow');
  if(await cell.getAttribute('data-value-source')!=='capture')throw Error(field+': lost screenshot value');
  if(await cell.evaluate(el=>el.scrollWidth>el.clientWidth))throw Error(field+': text overflow');
 }
 if(await completed.locator('.clue-proximity').innerText()!=='≈')throw Error('Missing HP proximity sign');
 const after=await page.request.get(base+'/api/game').then(r=>r.json());
 if(after.version!==state.version+1||after.history.length!==1)throw Error('Reference paste did not commit automatically');
 if(!after.pending||after.pending.card.pokedex[0]>=448||after.pending.card.hp>=110)throw Error('Reference arrows were not used for the next deduction');
 await page.locator(`[data-testid="pending-attempt"][data-card-id="${after.pending.card.id}"]`).waitFor();
 const reloaded=await page.request.get(base+'/api/game').then(r=>r.json());
 if(JSON.stringify(reloaded.history[0].clues)!==JSON.stringify(after.history[0].clues))throw Error('Reference values were not persisted');
 await page.screenshot({path:'storage/history-reference.png',fullPage:true});
 console.log('Reference history: seven values, six purple cells, yellow HP, four arrows and ≈ displayed; next deduction respects 448 ↓ and 110 ↓.');
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
if(manualPosts&&process.env.CARTO_TEST_MANUAL!=='1')throw Error('Paste must never post manual attempts');
if(await page.locator('select,input[type="file"]').count())throw Error('Manual entry or file picker still present');
await page.setViewportSize({width:390,height:844});
await page.screenshot({path:'storage/mobile.png',fullPage:true});
if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth))throw Error('Mobile horizontal overflow');
if(errors.length)throw Error(errors.join('\n'));
console.log('Desktop/mobile: no console errors or overflow; manual criteria and native paste.');
await browser.close();
