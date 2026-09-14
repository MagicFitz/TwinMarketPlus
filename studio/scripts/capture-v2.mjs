import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
await mkdir('qa/v2',{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const space of ['Experiment','Agent','Market','Setting','Documentation']) {
    await page.goto(`http://127.0.0.1:5173/studio/${space}`);
    await page.waitForTimeout(1200);
    console.log(space,JSON.stringify({errors,text:(await page.locator('body').innerText()).slice(0,1000)}));
    await page.screenshot({path:`qa/v2/${space}.png`,fullPage:true});
  }
} finally {await browser.close();}
