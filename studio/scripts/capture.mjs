import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
await mkdir('qa',{recursive:true});
const browser = await chromium.launch({channel:'chrome',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5173/studio/Experiment');
  await page.getByRole('heading',{name:'模拟日历'}).waitFor();
  await page.locator('canvas').waitFor();
  await page.screenshot({path:'qa/experiment-desktop.png',fullPage:true});
  await page.locator('.page-heading button').screenshot({path:'qa/implementation-button.png'});
  console.log(JSON.stringify({errors,title:await page.title(),overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)}));
  const source=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
  await source.goto('https://guokaigdg.github.io/animal-island-ui/',{waitUntil:'networkidle',timeout:30000});
  await source.screenshot({path:'qa/source-framework.png'});
  await source.getByText('开始使用', {exact:false}).first().locator('xpath=ancestor-or-self::button[1]').screenshot({path:'qa/source-button.png'});
  console.log('Captured framework visual reference and implementation');
} finally {await browser.close();}
