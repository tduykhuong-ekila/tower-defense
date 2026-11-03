import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5197';
const rooms=JSON.parse(await fs.readFile(process.env.GRID_QA_ROOMS||'/private/tmp/grid-browser-rooms.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding']});
const report={status:'RUNNING',maps:[],modal:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function open(room,options={}) {
 const context=await browser.newContext({viewport:{width:1440,height:1000},...options});
 const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto(base);await page.evaluate(r=>localStorage.setItem('grid-room',JSON.stringify(r)),room);
 await page.goto(base+'/tests/fixtures/grid-placement.html');
 await page.waitForFunction(()=>window.gridScene?.state.mapData?.placement_grid&&window.gridStore?.getState().connectionStatus==='connected');
 return {page,context};
}
async function choose(page) {
 await page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
 await page.locator('.arsenal-card').filter({hasText:'Tháp đại bác'}).click();
 await page.waitForFunction(()=>gridScene.state.mode==='BUILD');
}
async function focusCell(page,cell) {
 return page.evaluate(async cell=>{
  const {gridAnchor}=await import('/src/game/placement.ts');const s=gridScene,g=s.state.mapData.placement_grid;
  const anchor=gridAnchor(g,cell,g.footprints.cannon_tower);
  // Point at the nearest tower anchor for the complete multi-cell footprint.
  const f=g.footprints.cannon_tower;
  const pointer={x:g.originX+(cell.col+f.widthCells/2)*g.cellSize,y:g.originY+(cell.row+f.heightCells/2)*g.cellSize+f.anchorOffsetY};
  s.navigate(pointer.x,pointer.y,1);
  return {anchor,pointer};
 },cell);
}
async function screen(page,world) {
 return page.evaluate(point=>{const s=gridScene,c=s.cameras.main,b=s.game.canvas.getBoundingClientRect();const p=c.matrix.transformPoint(point.x-c.scrollX,point.y-c.scrollY);return {x:b.left+p.x*b.width/s.scale.width,y:b.top+p.y*b.height/s.scale.height}},world);
}
try {
 const a=await open(rooms[0]),b=await open({...rooms[0],join:rooms[0].joins[1]});
 await choose(a.page);
 assert.equal(await a.page.evaluate(()=>[...gridScene.markers.keys()].some(id=>id.startsWith('node_tower'))),false);
 const cell=rooms[0].valid[Math.floor(rooms[0].valid.length/2)],point=await focusCell(a.page,cell);await wait(700);
 let pos=await screen(a.page,point.pointer);await a.page.mouse.move(pos.x,pos.y);await wait(100);
 assert.equal(await a.page.evaluate(()=>gridScene.placementLabel.text.includes('Nhấp để xây')),true);
 const ghost=await a.page.evaluate(()=>({x:gridScene.ghost.x,y:gridScene.ghost.y}));assert.ok(Math.abs(ghost.x-point.anchor.x)<.01&&Math.abs(ghost.y-point.anchor.y)<.01);
 // Zoom and pan preserve world-to-cell conversion.
 await a.page.mouse.wheel(0,-150);await wait(500);pos=await screen(a.page,point.pointer);await a.page.mouse.move(pos.x,pos.y);
 assert.ok(await a.page.evaluate(p=>Math.abs(gridScene.ghost.x-p.x)<.01,point.anchor));
 await a.page.mouse.move(700,390);await a.page.mouse.down();await a.page.mouse.move(760,420,{steps:6});await a.page.mouse.up();await wait(250);
 pos=await screen(a.page,point.pointer);await a.page.mouse.move(pos.x,pos.y);await a.page.mouse.click(pos.x,pos.y);
 await a.page.waitForFunction(()=>gridStore.getState().entities.some(e=>e.unit_code==='cannon_tower'));
 await b.page.waitForFunction(()=>gridStore.getState().entities.some(e=>e.unit_code==='cannon_tower'));
 const tower=await a.page.evaluate(()=>gridStore.getState().entities.find(e=>e.unit_code==='cannon_tower'));
 assert.deepEqual(tower.simulation_state.grid_placement,{...cell,...await a.page.evaluate(()=>gridScene.state.mapData.placement_grid.footprints.cannon_tower)});assert.equal(tower.damage,20);
 await choose(a.page);await focusCell(a.page,cell);await wait(650);pos=await screen(a.page,point.pointer);await a.page.mouse.move(pos.x,pos.y);await a.page.mouse.click(pos.x,pos.y);
 assert.ok(await a.page.evaluate(()=>gridScene.placementLabel.text.includes('đã có')));
 assert.equal(await a.page.evaluate(()=>gridStore.getState().entities.length),1);
 await a.page.keyboard.press('Escape');await a.page.waitForFunction(()=>gridScene.state.mode!=='BUILD');
 await choose(a.page);await a.page.mouse.click(650,400,{button:'right'});await a.page.waitForFunction(()=>gridScene.state.mode!=='BUILD');
 report.maps.push({teams:2,build:true,damage:20,opponentRealtime:true,zoomPanSnapping:true,occupiedRejected:true,escapeRightCancel:true});
 for(const room of rooms.slice(1)) {
  const {page,context}=await open(room);await choose(page);
  const cell=room.valid[Math.floor(room.valid.length/2)],point=await focusCell(page,cell);await wait(650);const pos=await screen(page,point.pointer);await page.mouse.move(pos.x,pos.y);
  assert.equal(await page.evaluate(()=>gridScene.placementLabel.text.includes('Nhấp để xây')),true);
  await page.screenshot({path:new URL(`../../docs/qa/grid-placement-${room.map.num_teams}.png`,import.meta.url).pathname});
  report.maps.push({teams:room.map.num_teams,preview:true,objects:await page.evaluate(()=>gridScene.children.list.length)});await context.close();
 }
 // Mobile uses deliberate second tap; pan/zoom do not issue a purchase.
 const mobile=await open(rooms[1],{viewport:{width:390,height:844},isMobile:true,hasTouch:true});await choose(mobile.page);
 const cdp=await mobile.context.newCDPSession(mobile.page);
 const zoomBefore=await mobile.page.evaluate(()=>gridScene.cameras.main.zoom);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:140,y:260,id:1},{x:240,y:260,id:2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:100,y:260,id:1},{x:280,y:260,id:2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:80,y:260,id:1},{x:300,y:260,id:2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await wait(450);
 assert.ok(await mobile.page.evaluate(z=>gridScene.cameras.main.zoom>z,zoomBefore));
 assert.equal(await mobile.page.evaluate(()=>gridStore.getState().entities.length),0);report.pinchWithoutBuild=true;
 const mcell=rooms[1].valid[Math.floor(rooms[1].valid.length/2)],mp=await focusCell(mobile.page,mcell);await wait(700);
 let ms=await screen(mobile.page,mp.pointer);await mobile.page.touchscreen.tap(ms.x,ms.y);await wait(150);
 assert.equal(await mobile.page.evaluate(()=>gridStore.getState().entities.length),0);
 await mobile.page.touchscreen.tap(ms.x,ms.y);await mobile.page.waitForFunction(()=>gridStore.getState().entities.length===1);
 report.touchSecondTap=true;await mobile.context.close();
 // Category, level, confirmation and delayed artwork must not move any frame region.
 await a.page.goto(base+'/tests/fixtures/grid-placement.html?panel');await a.page.waitForSelector('.team-upgrade-panel article');
 for(const viewport of [{width:1440,height:1000},{width:390,height:844},{width:844,height:390}]) {
  await a.page.setViewportSize(viewport);await wait(100);
  console.log("Modal viewport",viewport);
  const boxes=[];
  await a.page.route('**/*.svg',async route=>{await wait(180);await route.continue().catch(()=>{})});
  for(const level of [1,2,3]) {
   console.log("Level",level);
   await a.page.evaluate(level=>window.renderLevel(level),level);
   const tabs=a.page.locator('.team-upgrade-panel nav button');
   for(let i=0;i<await tabs.count();i++) {
    await tabs.nth(i).click();boxes.push(await a.page.evaluate(()=>{const p=document.querySelector('.team-upgrade-panel'),h=p.querySelector('header'),f=p.querySelector('footer');return {height:p.getBoundingClientRect().height,top:p.getBoundingClientRect().top,header:h.getBoundingClientRect().top,footer:f.getBoundingClientRect().top,bottom:f.getBoundingClientRect().bottom,scroll:p.querySelector('article').scrollHeight>p.querySelector('article').clientHeight}}));
   }
  }
  assert.ok(Math.max(...boxes.map(b=>b.height))-Math.min(...boxes.map(b=>b.height))<1);
  assert.ok(Math.max(...boxes.map(b=>b.footer))-Math.min(...boxes.map(b=>b.footer))<1);
  assert.ok(Math.max(...boxes.map(b=>b.top))-Math.min(...boxes.map(b=>b.top))<1);
  assert.ok(boxes.every(b=>b.bottom<=viewport.height));
  await a.page.evaluate(()=>window.renderLevel(1));
  await a.page.locator('.team-upgrade-panel nav button').filter({hasText:'Tháp đại bác'}).click();
  const baseline=await a.page.locator('.team-upgrade-footer').boundingBox();
  await a.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).click();
  const confirmed=await a.page.locator('.team-upgrade-footer').boundingBox();assert.equal(confirmed.y,baseline.y);
  await a.page.getByRole('button',{name:'Hủy',exact:true}).click();
  await a.page.locator('.upgrade-previews .entity-illustration[data-state="ready"]').first().waitFor();
  const afterImage=await a.page.locator('.team-upgrade-footer').boundingBox();assert.equal(afterImage.y,baseline.y);
  report.modal.push({viewport,height:boxes[0].height,stable:true,internalScroll:boxes.some(b=>b.scroll),delayedImage:true,confirmationStable:true});
  await a.page.screenshot({path:new URL(`../../docs/qa/grid-upgrade-modal-${viewport.width}.png`,import.meta.url).pathname});
  await a.page.unrouteAll({behavior:'ignoreErrors'});
 }
 // A real upgrade must update existing entities and a tower already selected for construction.
 await a.page.setViewportSize({width:1440,height:1000});
 await a.page.goto(base+'/tests/fixtures/grid-placement.html');
 await a.page.waitForFunction(()=>window.gridScene?.state.mapData&&window.gridStore?.getState().connectionStatus==='connected');
 await choose(a.page);await a.page.getByRole('button',{name:'NÂNG CẤP',exact:true}).click();
 await a.page.locator('.team-upgrade-panel nav button').filter({hasText:'Tháp đại bác'}).click();
 await a.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).click();
 await a.page.getByRole('button',{name:/Xác nhận · 70 xu/}).click();
 await a.page.waitForFunction(()=>document.querySelector('.team-upgrade-panel article h3 .unit-level-stars')?.getAttribute('data-level')==='2');
 await a.page.getByRole('button',{name:'Đóng nâng cấp',exact:true}).click();
 await a.page.waitForFunction(()=>gridScene.state.mode==='BUILD'&&gridScene.state.selectedUnit.level===2);
 assert.equal(await a.page.evaluate(()=>gridStore.getState().entities.find(e=>e.unit_code==='cannon_tower').damage),22);
 await a.page.mouse.move(700,400);await a.page.waitForFunction(()=>gridScene.ghost.texture.key==='cannon_tower-lv2');
 report.upgradeWhileBuilding=true;
 assert.deepEqual(report.errors,[]);report.status='PASS';console.log(JSON.stringify(report,null,2));
} finally {
 await fs.writeFile(new URL('../../docs/qa/grid-browser-results.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();
}
