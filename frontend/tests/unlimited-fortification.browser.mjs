import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5199';
const rooms=JSON.parse(await fs.readFile('/private/tmp/unlimited-browser-rooms.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--enable-precise-memory-info']});
const report={status:'RUNNING',layouts:[],maps:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function open(room,viewport={width:1440,height:1000}) {
 const context=await browser.newContext({viewport});const page=await context.newPage();
 page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto(base);await page.evaluate(r=>localStorage.setItem('grid-room',JSON.stringify(r)),room);
 await page.goto(base+'/tests/fixtures/grid-placement.html');
 await page.waitForFunction(()=>window.gridScene?.state.mapData?.placement_grid&&window.gridStore?.getState().connectionStatus==='connected');
 return {context,page};
}
async function build(page,cell) {
 if(await page.evaluate(()=>gridScene.state.mode!=='BUILD')) {
  await page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
  await page.locator('.fortification-card').filter({hasText:'Tháp súng máy'}).click();
 }
 const before=await page.evaluate(()=>gridStore.getState().entities.length);
 const point=await page.evaluate(cell=>{const g=gridScene.state.mapData.placement_grid,f=g.footprints.mg_tower,p={x:g.originX+(cell.col+f.widthCells/2)*g.cellSize,y:g.originY+(cell.row+f.heightCells/2)*g.cellSize+f.anchorOffsetY};gridScene.navigate(p.x,p.y,1);return p},cell);
 await wait(500);
 const pos=await page.evaluate(p=>{const s=gridScene,c=s.cameras.main,b=s.game.canvas.getBoundingClientRect(),t=c.matrix.transformPoint(p.x-c.scrollX,p.y-c.scrollY);return {x:b.left+t.x*b.width/s.scale.width,y:b.top+t.y*b.height/s.scale.height}},point);
 await page.mouse.move(pos.x,pos.y);await wait(80);
 assert.ok(await page.evaluate(()=>gridScene.placementLabel.text.includes('Nhấp để xây')));
 await page.mouse.click(pos.x,pos.y);
 await page.waitForFunction(n=>gridStore.getState().entities.length===n+1,before);
}
try {
 const layout=await browser.newPage();
 for(const viewport of [{width:1440,height:1000},{width:1024,height:768},{width:390,height:844},{width:320,height:844},{width:844,height:390}]) {
  await layout.setViewportSize(viewport);await layout.goto(base+'/tests/fixtures/fortification-cards.html');
  const dimensions=[];
  for(const level of [1,2,3]) for(const state of ['available','selected','locked','unaffordable','building']) {
   await layout.evaluate(({level,state})=>renderCards(level,state),{level,state});await wait(30);
   await layout.locator('.fortification-card img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));
   const boxes=await layout.locator('.fortification-card').evaluateAll(cards=>cards.map(card=>{
    const art=card.querySelector('.game-item-card__artwork'),img=art.querySelector('img'),badge=card.querySelector('.unit-level-stars'),name=card.querySelector('strong'),cost=card.querySelector('.card-cost');
    const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}};
    return {card:rect(card),art:rect(art),img:rect(img),badge:rect(badge),name:rect(name),cost:rect(cost),
     absolute:getComputedStyle(badge).position,pointer:getComputedStyle(badge).pointerEvents,fit:getComputedStyle(img).objectFit,
     natural:[img.naturalWidth,img.naturalHeight],label:badge.getAttribute('aria-label'),chevrons:badge.querySelectorAll('svg').length,
     nameOverflow:name.scrollWidth>name.clientWidth||name.scrollHeight>name.clientHeight};
   }));
   for(const b of boxes) {
    assert.ok(b.card.x>=0&&b.card.right<=viewport.width, 'every complete card fits the viewport');
    assert.equal(b.absolute,'static');assert.equal(b.fit,'contain');assert.equal(b.chevrons,level);
    assert.ok(b.label===`Cấp ${level} trên 3`);assert.ok(b.natural[0]>0&&b.natural[1]>0);
    assert.ok(b.img.h>25&&b.img.w>50);assert.ok(b.img.y>=b.art.y&&b.img.bottom<=b.art.bottom+.1);
    assert.ok(b.badge.right<=b.art.right&&b.badge.y>=b.art.bottom);assert.ok(b.art.bottom<=b.name.y+.1);
    assert.ok(b.name.bottom<=b.cost.y+.1&&b.cost.bottom<=b.card.bottom);assert.equal(b.nameOverflow,false);
   }
   dimensions.push(boxes.map(b=>({height:b.card.h,art:b.art.h,nameY:b.name.y-b.card.y,costY:b.cost.y-b.card.y})));
  }
  assert.ok(dimensions.every(d=>JSON.stringify(d)===JSON.stringify(dimensions[0])),JSON.stringify({viewport,dimensions}));
  report.layouts.push({viewport,levels:[1,2,3],states:5,dimensions:dimensions[0],stable:true});
  await layout.evaluate(()=>renderCards(3,'selected'));await wait(60);
  await layout.screenshot({path:new URL(`../../docs/qa/fortification-${viewport.width}.png`,import.meta.url).pathname});
 }
 await layout.close();
 const a=await open(rooms[0]),b=await open({...rooms[0],join:rooms[0].joins[1]});
 // Real Phaser clicks through the seventh and eighth build, observed by another team.
 for(const cell of rooms[0].valid.slice(0,8))await build(a.page,cell);
 await b.page.waitForFunction(()=>gridStore.getState().entities.length===8);
 assert.equal(await a.page.evaluate(()=>gridStore.getState().coins),9800);
 assert.equal(await a.page.evaluate(()=>gridScene.visuals.size),8);
 report.eighthTower={charged:200,opponentRealtime:true,uniqueSprites:true};
 // Real team upgrade updates card rank, existing towers and future placement.
 await a.page.getByRole('button',{name:'NÂNG CẤP',exact:true}).click();
 await a.page.locator('.team-upgrade-panel nav button').filter({hasText:'Tháp súng máy'}).click();
 for(const level of [2,3]) {
  await a.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).click();
  await a.page.getByRole('button',{name:/Xác nhận ·/}).click();
  await a.page.waitForFunction(level=>document.querySelector('.team-upgrade-panel h3 .unit-level-stars')?.dataset.level===String(level),level);
  await b.page.waitForFunction(level=>gridStore.getState().entities.every(e=>e.level===level),level);
 }
 await a.page.getByRole('button',{name:'Đóng nâng cấp',exact:true}).click();
 await a.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
 await a.page.locator('.fortification-card').filter({hasText:'Tháp súng máy'}).locator('.unit-level-stars[data-level="3"]').waitFor();
 await build(a.page,rooms[0].valid[8]);
 assert.equal(await a.page.evaluate(()=>gridStore.getState().entities.at(-1).level),3);
 await b.page.goto(base+'/tests/fixtures/grid-placement.html');await b.page.waitForFunction(()=>window.gridStore?.getState().entities.length===9);
 report.teamUpgrade={ranks:[1,2,3],existingAndFuture:true,cardRefresh:true,reconnect:true};
 // Collect rendering cadence and actual JS heap with 10/25/50 paid towers per team.
 const auth=rooms[0].joins[0].participant_token,mid=rooms[0].match.id;
 let built=9,enemyBuilt=0;
 for(const quantity of [10,25,50]) {
  for(let i=built;i<quantity;i++) {
   const response=await a.page.request.post(`${base}/api/v1/matches/${mid}/actions/build/`,{headers:{'X-Participant-Token':auth},data:{unit_type_code_or_id:'mg_tower',grid_row:rooms[0].valid[i].row,grid_col:rooms[0].valid[i].col,idempotency_key:`load-${i}`}});
   assert.ok(response.ok(),await response.text());
  }
  for(let i=enemyBuilt;i<quantity;i++) {
   const cell=rooms[0].all_valid[1][i];
   const response=await b.page.request.post(`${base}/api/v1/matches/${mid}/actions/build/`,{headers:{'X-Participant-Token':rooms[0].joins[1].participant_token},data:{unit_type_code_or_id:'mg_tower',grid_row:cell.row,grid_col:cell.col,idempotency_key:`enemy-load-${i}`}});
   assert.ok(response.ok(),await response.text());
  }
  built=enemyBuilt=quantity;await a.page.waitForFunction(n=>gridScene.visuals.size===n,quantity*2);
  await a.page.keyboard.press('Escape');
  const metrics=await a.page.evaluate(async()=>{
   const s=gridScene;let result={};const previous=s.callbacks.onMetrics;s.callbacks.onMetrics=m=>{result=m;previous?.(m)};
   const frames=[];await new Promise(resolve=>{const start=performance.now();let last=start;function next(t){frames.push(t-last);last=t;if(t-start<2200)requestAnimationFrame(next);else resolve()}requestAnimationFrame(next)});
   s.callbacks.onMetrics=previous;
   return {...result,rafFPS:Math.round(frames.length/2.2),heapMB:Math.round(performance.memory.usedJSHeapSize/1048576*10)/10};
  });
  report.maps.push({teams:2,towersPerTeam:quantity,totalTowers:quantity*2,...metrics});
 }
 // Renderer stress only: replay 100 attack effects every 200ms without mutating game state.
 report.projectileStress=await a.page.evaluate(async()=>{
  const s=gridScene,entities=[...s.visuals.values()];let result={},maxShots=0;
  const previous=s.callbacks.onMetrics;s.callbacks.onMetrics=m=>{result=m;previous?.(m)};
  const timer=setInterval(()=>{for(let i=0;i<100;i++)s.animateEvent({type:'TOWER_ATTACKED',attacker_id:entities[i].data.id,target_entity_id:entities[(i+50)%entities.length].data.id,damage:10},200);maxShots=Math.max(maxShots,s.shots.filter(o=>o.active).length)},200);
  await new Promise(r=>setTimeout(r,2300));clearInterval(timer);s.callbacks.onMetrics=previous;
  return {...result,attackEffectsPerSecond:500,maxActiveShotEffects:maxShots,syntheticReplay:true};
 });
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
  await a.page.setViewportSize(viewport);await a.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
  await a.page.screenshot({path:new URL(`../../docs/qa/fortification-live-${viewport.width}.png`,import.meta.url).pathname});
  assert.equal(await a.page.locator('.fortification-card').count(),3);
  assert.ok(await a.page.locator('.fortification-card').evaluateAll(cards=>cards.every(card=>{
   const r=card.getBoundingClientRect(),name=card.querySelector('strong');
   return r.left>=0&&r.right<=innerWidth&&name.scrollHeight<=name.clientHeight&&name.scrollWidth<=name.clientWidth;
  })));
 }
 const legacy=rooms.find(r=>r.layout===5);
 if(legacy) {
  const oldA=await open(legacy),oldB=await open({...legacy,join:legacy.joins[1]});
  for(const cell of legacy.valid.slice(0,8))await build(oldA.page,cell);
  await oldB.page.waitForFunction(()=>gridStore.getState().entities.length===8);
  assert.equal(await oldA.page.evaluate(()=>[...gridScene.markers.keys()].some(id=>id.startsWith('node_tower'))),false);
  assert.equal(await oldA.page.getByRole('button',{name:/Vị trí [1-6]/}).count(),0);
  report.savedArena={layout:5,towers:8,opponentRealtime:true,grid:true,fixedSlotControls:false};
 }
 assert.deepEqual(report.errors,[]);report.status='PASS';console.log(JSON.stringify(report,null,2));
} finally {
 await fs.writeFile(new URL('../../docs/qa/unlimited-browser-results.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();
}
