import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5182';
const browser=await chromium.launch({headless:true,channel:'chrome'}),page=await browser.newPage({viewport:{width:1440,height:1000}});
const results={status:'RUNNING',maps:[]},wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
try {
 const rooms=await (await page.request.get(base+'/api/v1/matches/')).json();
 for(const count of [2,4,8,20]) {
  const room=rooms.find(r=>r.name===`Upgrade QA ${count}`);assert.ok(room);
  await page.goto(base+`/tests/fixtures/upgrade-inspection.html?match=${room.id}`);
  await page.waitForFunction(()=>window.flowScene?.children.list.some(o=>o.name==='natural-vegetation'));
  await wait(1200);
  const before=await page.evaluate(()=>window.flowScene.cameras.main.zoom);
  await page.getByRole('button',{name:'Phóng to',exact:true}).first().click();await wait(500);
  assert.ok(await page.evaluate(value=>window.flowScene.cameras.main.zoom>value,before));
  const panBefore=await page.evaluate(()=>({x:flowScene.cameras.main.scrollX,y:flowScene.cameras.main.scrollY}));
  await page.mouse.move(730,410);await page.mouse.down();await page.mouse.move(890,490,{steps:12});await page.mouse.up();await wait(500);
  const after=await page.evaluate(()=>({x:flowScene.cameras.main.scrollX,y:flowScene.cameras.main.scrollY}));
  assert.ok(Math.abs(panBefore.x-after.x)+Math.abs(panBefore.y-after.y)>10);
  results.maps.push(await page.evaluate(count=>{const dt=frameTimes.filter(x=>x>0&&x<1000).slice(-120).sort((a,b)=>a-b);return {count,vegetation:flowScene.children.list.filter(o=>o.name==='natural-vegetation').length,frameSamples:dt.length,frameMsP95:dt[Math.floor(dt.length*.95)],fps:1000/(dt.reduce((a,b)=>a+b,0)/dt.length),pan:true,zoom:true}},count));
  assert.ok(results.maps.at(-1).frameSamples>30);
  await page.screenshot({path:new URL(`../../docs/qa/team-upgrade-camera-${count}.png`,import.meta.url).pathname});
 }
 const r=JSON.parse(await fs.readFile('/private/tmp/team-upgrade-room.json','utf8'));
 await page.goto(base);await page.evaluate(r=>localStorage.setItem('upgrade-inspection-room',JSON.stringify(r)),r);
 await page.goto(base+`/tests/fixtures/upgrade-inspection.html?match=${r.match.id}&mode=panel`);
 const panel=page.getByRole('dialog',{name:'Nâng cấp toàn đội'});
 await panel.locator('.entity-illustration[data-state="ready"]').waitFor();
 assert.equal(await panel.locator('img').evaluate(img=>img.complete&&img.naturalWidth>0&&img.src.includes('-lv4')),true);
 await page.screenshot({path:new URL('../../docs/qa/team-upgrade-max.png',import.meta.url).pathname});
 await page.setViewportSize({width:390,height:844});await wait(300);
 assert.ok(await panel.evaluate(el=>el.scrollWidth<=window.innerWidth));
 await page.screenshot({path:new URL('../../docs/qa/team-upgrade-mobile.png',import.meta.url).pathname});
 results.elitePreviewLoaded=true;results.mobilePanelFits=true;results.status='PASS';console.log(JSON.stringify(results));
} finally {await fs.writeFile(new URL('../../docs/qa/team-upgrade-camera.json',import.meta.url),JSON.stringify(results,null,2));await browser.close();}
