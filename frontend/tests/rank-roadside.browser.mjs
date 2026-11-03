import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const rooms=JSON.parse(await fs.readFile('/private/tmp/rank-roadside-rooms.json','utf8'));
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5198';
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling']});
const report={status:'RUNNING',selection:[],maps:[],dimensions:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function open(room) {
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
 page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto(base);await page.evaluate(r=>localStorage.setItem('grid-room',JSON.stringify(r)),room);
 await page.goto(base+'/tests/fixtures/grid-placement.html');
 await page.waitForFunction(()=>window.gridScene?.state.mapData?.placement_grid&&window.gridStore?.getState().connectionStatus==='connected'&&gridScene.visuals.size>=10);
 return {page,context};
}
async function screen(page,p) {
 return page.evaluate(p=>{const s=gridScene,c=s.cameras.main,b=s.game.canvas.getBoundingClientRect(),t=c.matrix.transformPoint(p.x-c.scrollX,p.y-c.scrollY);return {x:b.left+t.x*b.width/s.scale.width,y:b.top+t.y*b.height/s.scale.height}},p);
}
async function selectEntity(page,code,enemy=false) {
 const id=await page.evaluate(({code,enemy})=>{
  const s=gridScene,v=[...s.visuals.values()].find(v=>v.data.unit_code===code&&(enemy?v.data.team_id!==s.state.myTeamId:v.data.team_id===s.state.myTeamId));
  if(!v)throw Error('Missing entity '+code);
  s.callbacks.onEntityClick(v.data.id,false);return v.data.id;
 },{code,enemy});
 await page.waitForFunction(({id,code,enemy})=>{const s=gridScene,e=s.state.entities.find(e=>e.id===s.state.selectedEntityId);return e?.id===id&&e.unit_code===code&&(enemy?e.team_id!==s.state.myTeamId:e.team_id===s.state.myTeamId)},{id,code,enemy});
}
async function chosen(page,code) {
 await page.waitForSelector(`.team-upgrade-panel h3[data-upgrade-type="${code}"]`);
 assert.equal(await page.locator('.team-upgrade-panel nav button[aria-pressed="true"]').getAttribute('data-upgrade-type'),code);
 assert.equal(await page.locator('.team-upgrade-panel h3').getAttribute('data-category'),['infantry','tank','artillery'].includes(code)?'UNIT':'TOWER');
}
async function close(page) {await page.getByRole('button',{name:'Đóng nâng cấp',exact:true}).click();}
try {
 const a=await open(rooms[0]),b=await open({...rooms[0],join:rooms[0].joins[1]});
 for(const code of ['infantry','tank','artillery','cannon_tower','mg_tower','shield_generator','tank']) {
  console.log('Select',code);await selectEntity(a.page,code);
  await a.page.locator('.upgrade-button').click();await chosen(a.page,code);
  await a.page.evaluate(async()=>{const {wsClient}=await import('/src/services/websocket.ts');wsClient.requestSync()});
  await wait(450);await chosen(a.page,code);
  report.selection.push({code,category:true,reopen:true,snapshotStable:true});await close(a.page);
 }
 await selectEntity(a.page,'infantry',true);assert.equal(await a.page.locator('.upgrade-button').count(),0);report.enemyInspectionSafe=true;
 await selectEntity(a.page,'tank');await a.page.locator('.upgrade-button').click();await chosen(a.page,'tank');
 console.log('Upgrade tank');
 for(const level of [2,3]) {
  console.log('Rank',level);
  await a.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).click();
  await a.page.getByRole('button',{name:/Xác nhận ·/}).click();
  await a.page.waitForFunction(level=>document.querySelector('.team-upgrade-panel h3 .unit-level-stars')?.dataset.level===String(level),level);
  await b.page.waitForFunction(level=>gridStore.getState().entities.filter(e=>e.unit_code==='tank').every(e=>e.level===level),level);
 }
 assert.equal(await a.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).count(),0);
 assert.ok((await a.page.locator('.team-upgrade-panel h3').textContent()).includes('CẤP TỐI ĐA'));
 assert.equal(await a.page.evaluate(()=>[...gridScene.visuals.values()].filter(v=>v.data.unit_code==='tank').every(v=>v.stars.texture.key==='upgrade-stars-3')),true);
 report.teamWideEliteRealtime=true;await a.page.screenshot({path:new URL('../../docs/qa/rank-elite-modal.png',import.meta.url).pathname});await close(a.page);
 for(const zoom of [.4,.7,1.1]) {
  await a.page.evaluate(zoom=>{gridScene.zoomController.zoomTo(zoom)},zoom);await wait(650);
  const results=await a.page.evaluate(()=>[...gridScene.visuals.values()].filter(v=>v.root.visible).map(v=>({code:v.data.unit_code,visible:v.stars.visible})));
  if(zoom===.4)assert.ok(results.every(r=>!r.visible));
 }
 report.zoomLOD=true;
 console.log('Roadside construction');
 for(const room of rooms) {
  console.log('Map',room.map.num_teams);
  const current=room===rooms[0]?a:await open(room),page=current.page;
  await page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
  await page.locator('.arsenal-card').filter({hasText:'Tháp đại bác'}).click();
  const cell=await page.evaluate(async cells=>{const {placementReason}=await import('/src/game/placement.ts');return cells.find(c=>!placementReason(gridScene.state.mapData,c,'cannon_tower',gridScene.state.myTeamId,gridScene.state.entities))},room.roadside);
  assert.ok(cell,'new roadside cell exists');
  const pointer=await page.evaluate(c=>{const g=gridScene.state.mapData.placement_grid,f=g.footprints.cannon_tower,p={x:g.originX+(c.col+f.widthCells/2)*g.cellSize,y:g.originY+(c.row+f.heightCells/2)*g.cellSize+f.anchorOffsetY};gridScene.navigate(p.x,p.y,1);return p},cell);
  await wait(650);const p=await screen(page,pointer);await page.mouse.move(p.x,p.y);await wait(100);
  assert.ok(await page.evaluate(()=>gridScene.placementLabel.text.includes('Nhấp để xây')));
  const before=await page.evaluate(()=>gridStore.getState().entities.length);
  await page.screenshot({path:new URL(`../../docs/qa/rank-roadside-${room.map.num_teams}.png`,import.meta.url).pathname});
  await page.mouse.click(p.x,p.y);await page.waitForFunction(n=>gridStore.getState().entities.length===n+1,before);
  if(room===rooms[0])await b.page.waitForFunction(n=>gridStore.getState().entities.length===n+1,before);
  const vegetation=await page.evaluate(async()=>{
   const {gridRect}=await import('/src/game/placement.ts'),s=gridScene,g=s.state.mapData.placement_grid;
   const rects=s.state.entities.filter(e=>e.entity_kind!=='UNIT'&&e.status!=='DESTROYED'&&e.simulation_state?.grid_placement)
    .map(e=>gridRect(g,e.simulation_state.grid_placement,e.simulation_state.grid_placement));
   const plants=s.children.list.filter(o=>o.name==='natural-vegetation');
   return {hidden:plants.filter(p=>!p.visible).length,overlapsVisible:plants.filter(p=>{const b=p.getBounds();return p.visible&&rects.some(r=>b.x<r.x+r.width&&b.right>r.x&&b.y<r.y+r.height&&b.bottom>r.y)}).length};
  });
  assert.equal(vegetation.overlapsVisible,0);
  report.maps.push({teams:room.map.num_teams,cell,newRoadside:true,previewAccepted:true,roadsideCells:room.roadside.length,vegetation});
  if(current!==a)await current.context.close();
 }
 await a.page.goto(base+'/tests/fixtures/grid-placement.html?panel');await a.page.waitForSelector('.team-upgrade-panel article h3');
 await a.page.evaluate(()=>renderSelection('cannon_tower',true));
 await a.page.getByText('Đang tải thông tin nâng cấp…').waitFor();
 assert.equal(await a.page.locator('.team-upgrade-panel h3').count(),0);
 await a.page.evaluate(()=>renderSelection('cannon_tower',false));await chosen(a.page,'cannon_tower');
 report.delayedMetadata=true;
 for(const viewport of [{width:1440,height:1000},{width:390,height:844},{width:844,height:390}]) {
  await a.page.setViewportSize(viewport);const boxes=[];
  for(const level of [1,2,3]) {
   await a.page.evaluate(level=>renderLevel(level),level);
   const tabs=a.page.locator('.team-upgrade-panel nav button');
   for(let i=0;i<await tabs.count();i++) {
    await tabs.nth(i).click();const badge=a.page.locator('.team-upgrade-panel h3 .unit-level-stars').first();
    assert.equal(await badge.locator('svg').count(),level);
    assert.ok((await badge.getAttribute('aria-label')).startsWith(`Cấp ${level} trên 3`));
    boxes.push(await a.page.locator('.team-upgrade-footer').boundingBox());
   }
  }
  assert.ok(Math.max(...boxes.map(b=>b.y))-Math.min(...boxes.map(b=>b.y))<1);
  assert.ok(boxes.every(b=>b.y+b.height<=viewport.height));
  await a.page.evaluate(()=>renderLevel(1));
  const before=await a.page.locator('.team-upgrade-footer').boundingBox();
  await a.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).click();
  const after=await a.page.locator('.team-upgrade-footer').boundingBox();assert.equal(before.y,after.y);
  assert.equal(await a.page.locator('.upgrade-confirm .btn-primary').isEnabled(),true);
  await a.page.getByRole('button',{name:'Hủy',exact:true}).click();
  report.dimensions.push({viewport,stableFooter:true,fourRanksAccessible:true,confirmationStable:true});
  await a.page.screenshot({path:new URL(`../../docs/qa/rank-modal-${viewport.width}.png`,import.meta.url).pathname});
 }
 assert.deepEqual(report.errors,[]);report.status='PASS';console.log(JSON.stringify(report,null,2));
} catch(e) {report.failure=String(e);throw e;} finally {
 await fs.writeFile(new URL('../../docs/qa/rank-roadside-results.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();
}
