import {chromium} from '@playwright/test';
import {readFile} from 'node:fs/promises';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
try{
 const page=await browser.newPage({viewport:{width:1134,height:148},deviceScaleFactor:1});
 await page.setContent(await readFile('backend/tests/fixtures/cartodle/lucario.recreated.html','utf8'));
 await page.screenshot({path:'backend/tests/fixtures/cartodle/lucario.recreated.png'});
}finally{await browser.close()}
