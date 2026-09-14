import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
await mkdir('qa/v2',{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const base='http://127.0.0.1:5173', checks=[], errors=[], writes=[];
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().includes('/api/')&&r.method()!=='GET')writes.push(r.method());});
  await page.goto(`${base}/studio/Experiment`);
  await page.getByRole('heading',{name:'模拟日历'}).waitFor();
  await page.locator('canvas').waitFor();
  assert.ok(await page.locator('[class*="bg-dots-dark-green"]').count());
  assert.equal(await page.locator('.page-heading p, .panel-heading p, .panel-note, .resource-note, .workflow').count(),0);
  assert.equal(await page.getByRole('tooltip').count(),0);
  const before=await page.locator('.update-time').textContent();
  await page.waitForFunction(value=>document.querySelector('.update-time')?.textContent!==value,before,{timeout:12000});
  await page.getByRole('button',{name:'每 5 秒读取'}).click();
  await page.waitForTimeout(400);
  const paused=await page.locator('.update-time').textContent();
  await page.waitForTimeout(5300);
  assert.equal(await page.locator('.update-time').textContent(),paused);
  checks.push('official dots background, reduced descriptions, polling and pause');

  const hint=page.getByRole('button',{name:'本次模拟交易口径'});
  await hint.hover();
  await page.getByRole('tooltip').filter({hasText:'初始化历史'}).waitFor();
  assert.ok(await page.getByRole('tooltip').filter({hasText:'初始化历史'}).locator('svg path[stroke]').count());
  await page.screenshot({path:'qa/v2/island-tooltip.png'});
  await page.mouse.move(10,10);await page.waitForTimeout(200);
  await hint.focus();
  await page.getByRole('tooltip').filter({hasText:'初始化历史'}).waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('tooltip').filter({hasText:'初始化历史'}).waitFor({state:'hidden'});
  checks.push('Island bordered tooltip: hover, keyboard focus, Escape');
  await page.getByRole('button',{name:'紧凑',exact:true}).click();
  await page.screenshot({path:'qa/v2/Experiment-compact.png',fullPage:true});
  await page.getByRole('button',{name:'舒适',exact:true}).click();
  await page.screenshot({path:'qa/v2/Experiment.png',fullPage:true});
  await page.getByRole('button',{name:'查看数据',exact:true}).click();
  assert.ok(await page.locator('tbody tr').count()>10);
  await page.getByRole('button',{name:'查看曲线'}).click();
  await page.getByRole('combobox',{name:'选择资产'}).click();
  await page.getByRole('option').filter({hasText:'TTEI'}).click();
  assert.match(await page.getByRole('combobox',{name:'选择资产'}).textContent(),/TTEI/);
  await page.getByRole('tab',{name:'Agent 快照'}).click();
  await page.locator('tbody tr').first().waitFor();
  const first=await page.locator('tbody tr td').first().textContent();
  await page.getByRole('button',{name:'下一页'}).click();
  await page.waitForFunction(old=>document.querySelector('tbody tr td')?.textContent!==old,first);
  await page.locator('tbody .text-link').first().click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('heading',{name:'当前持仓'}).waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.getByRole('textbox',{name:'搜索成员'}).fill('NO_SUCH_MEMBER');
  await page.getByText('没有匹配的成员').waitFor();
  checks.push('official Select, Drawer, search, pagination, chart/table, density');

  await page.locator('.sidebar a[href="/studio/Documentation"]').click();
  await page.locator('.markdown').waitFor();
  assert.equal(await page.locator('.docs-index nav a').count(),2);
  await page.getByRole('textbox',{name:'搜索文档'}).fill('发布');
  assert.equal(await page.locator('.docs-index nav a').count(),1);
  await page.getByRole('textbox',{name:'搜索文档'}).fill('');
  await page.locator('.markdown a').filter({hasText:'文档发布约定'}).click();
  await page.waitForURL('**doc=DOCUMENTATION_PUBLISHING_ZH.md');
  await page.getByRole('heading',{name:'发布一篇文档'}).waitFor();
  await page.reload();await page.getByRole('heading',{name:'发布一篇文档'}).waitFor();
  await page.goBack();await page.getByRole('heading',{name:'实验监控',exact:true}).waitFor();
  const unpublished=await page.request.get(`${base}/api/documentation?path=DESIGN_PROMPT.md`);
  assert.equal(unpublished.status(),404);
  const escaped=await page.request.get(`${base}/api/documentation?path=../config/api.yaml`);
  assert.equal(escaped.status(),404);
  checks.push('published-only list/detail, search, MD links, reload/back, traversal rejection');

  // Isolated browser responses exercise unsafe Markdown and revocation without editing source docs.
  let revoked=false;
  const doc={path:'fixture.md',title:'安全测试',category:'测试',content:'# 安全测试\n\n<script>window.__unsafe=1</script>\n\n<img src="https://example.invalid/track" onerror="window.__unsafe=1"/>\n\n![Blocked](https://example.invalid/track)\n\n[bad](javascript:alert(1))\n\n[private](DESIGN_PROMPT.md)'};
  const outbound=[];page.on('request',r=>{if(r.url().includes('example.invalid'))outbound.push(r.url());});
  await page.route('**/api/documentation**',route=>{
    if(new URL(route.request().url()).searchParams.has('path'))return route.fulfill({status:revoked?404:200,json:revoked?{error:'未发布'}:doc});
    return route.fulfill({json:{items:revoked?[]:[{path:doc.path,title:doc.title,category:doc.category}]}});
  });
  await page.goto(`${base}/studio/Documentation?doc=fixture.md`);
  await page.getByRole('heading',{name:'安全测试'}).waitFor();
  assert.equal(await page.evaluate(()=>window.__unsafe),undefined);
  assert.equal(await page.locator('.markdown script,.markdown img,.markdown a[href^="javascript:"]').count(),0);
  assert.deepEqual(outbound,[]);
  revoked=true;
  await page.getByRole('status').filter({hasText:'文档未发布或已撤回'}).waitFor({timeout:12000});
  assert.equal(await page.locator('.markdown').count(),0);
  await page.unroute('**/api/documentation**');
  checks.push('HTML/script/image isolation and automatic revocation clears open document');

  for(const width of [1440,1024,390]) {
    await page.setViewportSize({width,height:1000});
    for(const space of ['Experiment','Agent','Market','Setting','Documentation']) {
      await page.goto(`${base}/studio/${space}`);await page.locator('h1').waitFor();
      if(space==='Documentation')await page.locator('.markdown').waitFor();
      else if(space==='Agent')await page.locator('tbody tr').first().waitFor();
      else if(space==='Market')await page.locator('canvas').waitFor();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${space} overflow at ${width}`);
      await page.screenshot({path:`qa/v2/${space}-${width}.png`,fullPage:true});
      if(width===390&&space==='Experiment') {
        await page.getByRole('button',{name:'本次模拟交易口径'}).hover();
        const bubble=page.getByRole('tooltip').filter({hasText:'初始化历史'});
        await bubble.waitFor();
        const bounds=await bubble.boundingBox();assert.ok(bounds.x>=0 && bounds.x+bounds.width<=width+1,'mobile tooltip stays within viewport');
        await page.screenshot({path:'qa/v2/island-tooltip-mobile.png'});
      }
    }
  }
  checks.push('five routes at desktop/tablet/mobile, tooltip stays inside viewport');
  await page.goto(`${base}/studio/Experiment`);await page.locator('.metrics').waitFor();
  const metrics=await page.locator('.metrics').textContent();
  await page.route('**/api/**',route=>route.abort());
  await page.getByRole('button',{name:'立即刷新'}).click();
  await page.getByRole('status').filter({hasText:'连接中断'}).waitFor();
  assert.equal(await page.locator('.metrics').textContent(),metrics);
  await page.unroute('**/api/**');await page.getByRole('button',{name:'立即刷新'}).click();
  await page.getByRole('status').filter({hasText:'连接中断'}).waitFor({state:'hidden'});
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  assert.equal((await page.request.post(`${base}/api/documentation`,{data:{}})).status(),405);
  checks.push('monitor disconnect/recovery, no runtime errors or write requests, POST rejected');
  console.log(JSON.stringify({passed:true,checks},null,2));
} finally {await browser.close();}
