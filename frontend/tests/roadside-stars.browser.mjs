import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5198';
const rooms=JSON.parse(await fs.readFile('/private/tmp/roadside-stars-rooms.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding']});
const report={status:'RUNNING',layouts:[],maps:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const shot=name=>new URL(`../../docs/qa/${name}.png`,import.meta.url).pathname;
async function open(room) {
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
 page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto(base);await page.evaluate(r=>localStorage.setItem('grid-room',JSON.stringify(r)),room);
 await page.goto(base+'/tests/fixtures/grid-placement.html');
 await page.waitForFunction(()=>window.gridScene?.state.mapData?.placement_grid&&window.gridStore?.getState().connectionStatus==='connected');
 return {page,context};
}
async function clickCell(page,cell,code='cannon_tower',zoom=1.1) {
 if(await page.evaluate(code=>gridScene.state.mode!=='BUILD'||gridScene.state.selectedUnit?.code!==code,code)) {
  await page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
  const name=code==='cannon_tower'?'Tháp đại bác':'Tháp súng máy';
  await page.locator('.game-item-card').filter({hasText:name}).click();
 }
 const anchor=await page.evaluate(async({cell,code,zoom})=>{
  const {gridAnchor}=await import('/src/game/placement.ts'),s=gridScene,g=s.state.mapData.placement_grid;
  const p=gridAnchor(g,cell,g.footprints[code]);s.navigate(p.x,p.y,zoom);return p;
 },{cell,code,zoom});
 await wait(650);
 // Exercise pan after zoom, then transform the exact nearest candidate anchor.
 const pos=await page.evaluate(p=>{const s=gridScene,c=s.cameras.main;c.scrollX+=13;c.scrollY-=9;const b=s.game.canvas.getBoundingClientRect(),t=c.matrix.transformPoint(p.x-c.scrollX,p.y-c.scrollY);return {x:b.left+t.x*b.width/s.scale.width,y:b.top+t.y*b.height/s.scale.height}},anchor);
 await page.mouse.move(pos.x,pos.y);await wait(80);
 assert.ok(await page.evaluate(()=>gridScene.placementLabel.text.includes('Nhấp để xây')),'server mask accepts ghost');
 const previous=await page.evaluate(()=>gridStore.getState().entities.filter(e=>e.entity_kind==='TOWER').map(e=>e.id));
 if(code==='cannon_tower') {const {teams,level}=await page.evaluate(()=>({teams:gridScene.state.mapData.num_teams,level:gridScene.state.selectedUnit.level}));await page.screenshot({path:shot(`refined-preview-${teams}${level>1?"-elite":""}`)});}
 await page.mouse.click(pos.x,pos.y);
 await page.waitForFunction(({previous,cell})=>gridStore.getState().entities.some(e=>!previous.includes(e.id)&&e.entity_kind==='TOWER'&&e.simulation_state?.grid_placement?.row===cell.row&&e.simulation_state?.grid_placement?.col===cell.col),{previous,cell});
 return page.evaluate(previous=>gridStore.getState().entities.find(e=>!previous.includes(e.id)&&e.entity_kind==='TOWER'),previous);
}
try {
 const layout=await browser.newPage();
 for(const viewport of [{width:1440,height:1000},{width:1024,height:768},{width:390,height:844},{width:320,height:844},{width:844,height:390}]) {
  await layout.setViewportSize(viewport);await layout.goto(base+'/tests/fixtures/game-item-cards.html');
  for(const zoom of [1,1.25]) {
   await layout.evaluate(zoom=>document.documentElement.style.zoom=String(zoom),zoom);
   const dimensions=[];
   for(const category of ['UNIT','TOWER']) for(const level of [1,2,3]) for(const state of ['available','selected','locked','unaffordable','building','deploying']) {
    await layout.evaluate(({level,state,category})=>renderCards(level,state,category),{level,state,category});
    await layout.waitForFunction(({level,category})=>document.querySelector('.unit-level-stars')?.dataset.level===String(level)&&document.querySelector('.command-category').textContent===(category==='UNIT'?'QUÂN ĐỘI':'CÔNG SỰ'),{level,category});
    await layout.locator('.game-item-card img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));
    const boxes=await layout.locator('.game-item-card').evaluateAll(cards=>cards.map(card=>{
     const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}};
     const art=card.querySelector('.game-item-card__artwork'),img=art.querySelector('img'),stars=card.querySelector('.game-item-card__stars'),name=card.querySelector('strong'),cost=card.querySelector('.card-cost');
     return {card:rect(card),art:rect(art),img:rect(img),stars:rect(stars),name:rect(name),cost:rect(cost),fit:getComputedStyle(img).objectFit,
      count:stars.querySelectorAll('svg').length,label:stars.querySelector('[role=img]').getAttribute('aria-label'),oldBadges:card.querySelectorAll('.upgrade-rank').length,
      overflow:name.scrollWidth>name.clientWidth+1||name.scrollHeight>name.clientHeight+1,starOverflow:stars.scrollWidth>stars.clientWidth+1};
    }));
    for(const b of boxes) {
     assert.ok(b.card.x>=0&&b.card.right<=viewport.width+1,`card fits ${JSON.stringify({viewport,zoom,category,state,b})}`);
     assert.equal(b.count,level);assert.equal(b.label,`Cấp ${level} trên 3`);assert.equal(b.oldBadges,0);assert.equal(b.fit,'contain');
     assert.ok(b.img.h>=50*zoom&&b.img.w>35*zoom);assert.equal(b.overflow,false,`name overflow ${JSON.stringify({viewport,zoom,category,state,b})}`);assert.equal(b.starOverflow,false,`star overflow ${JSON.stringify({viewport,zoom,category,state,b})}`);
     assert.ok(b.img.y>=b.art.y-.1&&b.img.bottom<=b.art.bottom+.1);
     assert.ok(b.art.bottom<=b.stars.y+.1&&b.stars.bottom<=b.name.y+.1&&b.name.bottom<=b.cost.y+.1&&b.cost.bottom<=b.card.bottom+.1);
    }
    dimensions.push(boxes.map(b=>[b.card.h,b.art.h,b.stars.y-b.card.y,b.name.y-b.card.y,b.cost.y-b.card.y]));
   }
   assert.ok(dimensions.every(d=>JSON.stringify(d)===JSON.stringify(dimensions[0])),`stable rows ${JSON.stringify({viewport,zoom})}`);
   report.layouts.push({viewport,zoom,levels:3,states:6,categories:2,stable:true});
  }
  await layout.evaluate(()=>{document.documentElement.style.zoom='1';renderCards(3,'selected','TOWER')});await wait(60);
  await layout.screenshot({path:shot(`stars-fortification-${viewport.width}`)});
  await layout.evaluate(()=>renderCards(3,'selected','UNIT'));await wait(60);
  await layout.screenshot({path:shot(`stars-army-${viewport.width}`)});
 }
 await layout.close();console.log('Responsive card matrix passed');
 const a=await open(rooms[0]),mate=await open(rooms[0]),b=await open({...rooms[0],join:rooms[0].joins[1]});
 for(const room of rooms) {
  const current=room===rooms[0]?a:await open(room),page=current.page;
  const cell=await page.evaluate(async cells=>{const {placementReason}=await import('/src/game/placement.ts');return cells.find(c=>!placementReason(gridScene.state.mapData,c,'cannon_tower',gridScene.state.myTeamId,gridScene.state.entities))},room.roadside);
  assert.ok(cell);
  const tower=await clickCell(page,cell,'cannon_tower',room.map.num_teams===8?.75:1.25);
  assert.equal(tower.simulation_state.grid_placement.widthCells,3);
  if(current===a)await b.page.waitForFunction(id=>gridStore.getState().entities.some(e=>e.id===id),tower.id);
  await wait(300);await page.screenshot({path:shot(`refined-roadside-${room.map.num_teams}`)});
  // Full road cells must remain invalid even after zoom and pan.
  const invalid=await page.evaluate(async()=>{const {placementReason}=await import('/src/game/placement.ts'),s=gridScene;return placementReason(s.state.mapData,{row:0,col:0},'cannon_tower',s.state.myTeamId,s.state.entities)});
  assert.ok(invalid);
  await page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();await page.locator('.game-item-card').filter({hasText:'Tháp đại bác'}).click();
  const roadPoint=await page.evaluate(async()=>{const {projectMap}=await import('/src/game/map.ts'),s=gridScene,p=projectMap(s.state.mapData).get('node_lane_t1_2');s.navigate(p.worldX,p.worldY,1);return {x:p.worldX,y:p.worldY}});
  await wait(650);
  const redPos=await page.evaluate(p=>{const s=gridScene,c=s.cameras.main,b=s.game.canvas.getBoundingClientRect(),t=c.matrix.transformPoint(p.x-c.scrollX,p.y-c.scrollY);return {x:b.left+t.x*b.width/s.scale.width,y:b.top+t.y*b.height/s.scale.height}},roadPoint);
  await page.mouse.move(redPos.x,redPos.y);await wait(80);
  assert.equal(await page.evaluate(()=>gridScene.ghost.tintTopLeft),0xe56858);
  const towerCount=await page.evaluate(()=>gridStore.getState().entities.filter(e=>e.entity_kind==='TOWER').length);
  await page.mouse.click(redPos.x,redPos.y);await wait(120);assert.equal(await page.evaluate(()=>gridStore.getState().entities.filter(e=>e.entity_kind==='TOWER').length),towerCount);
  await page.keyboard.press('Escape');
  report.maps.push({teams:room.map.num_teams,cell,nearestPaintedGap:room.nearestRoadGap,greenPreview:true,redRoadPreview:true,serverAccepted:true,zoomPan:true});
  if(current!==a)await current.context.close();
 }
 console.log('Roadside placement passed');
 await mate.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();await b.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
 await a.page.getByRole('button',{name:'NÂNG CẤP',exact:true}).click();
 await a.page.locator('.team-upgrade-panel nav button').filter({hasText:'Tháp đại bác'}).click();
 for(const level of [2,3]) {
  await a.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).click();await a.page.getByRole('button',{name:/Xác nhận ·/}).click();
  await a.page.waitForFunction(level=>document.querySelector('.team-upgrade-panel h3 .unit-level-stars')?.dataset.level===String(level),level);
  await mate.page.locator('.game-item-card').filter({hasText:'Tháp đại bác'}).locator(`.unit-level-stars[data-level="${level}"]`).waitFor();
  await b.page.waitForFunction(level=>gridStore.getState().entities.filter(e=>e.unit_code==='cannon_tower'&&e.team_id!==gridStore.getState().currentTeamId).every(e=>e.level===level),level);
  assert.equal(await b.page.locator('.game-item-card').filter({hasText:'Tháp đại bác'}).locator('.unit-level-stars').getAttribute('data-level'),'1');
 }
 assert.equal(await a.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).count(),0);
 await a.page.getByRole('button',{name:'Đóng nâng cấp',exact:true}).click();
 const nextCell=await a.page.evaluate(async cells=>{const {placementReason}=await import('/src/game/placement.ts'),s=gridScene;return cells.find(c=>!placementReason(s.state.mapData,c,'cannon_tower',s.state.myTeamId,s.state.entities))},rooms[0].valid);
 const elite=await clickCell(a.page,nextCell);assert.equal(elite.level,3);assert.equal(elite.damage,24);
 await a.page.goto(base+'/tests/fixtures/grid-placement.html');await a.page.waitForFunction(()=>window.gridStore?.getState().connectionStatus==='connected'&&gridStore.getState().teamUpgradeLevels[gridStore.getState().currentTeamId]?.cannon_tower===3);
 await a.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();await a.page.locator('.game-item-card').filter({hasText:'Tháp đại bác'}).locator('.unit-level-stars[data-level="3"]').waitFor();
 assert.deepEqual(await a.page.evaluate(id=>gridStore.getState().entities.find(e=>e.id===id).simulation_state.grid_placement,elite.id),elite.simulation_state.grid_placement);
 report.multiplayer={teammateStars:[2,3],opponentIsolated:true,existingAndFuture:true,reconnect:true,damage24:true};
 // Live movement and tactical commands on the same built roadside geometry.
 const response=await a.page.request.post(`${base}/api/v1/matches/${rooms[0].match.id}/advance-phase/`,{headers:{'X-Host-Token':rooms[0].host_token},data:{target_phase:'WAR',is_override:true,reason:'Disposable roadside acceptance'}});
 assert.ok(response.ok(),await response.text());
 await a.page.waitForSelector('.army-command-panel');
 const starts=await a.page.evaluate(()=>Object.fromEntries(gridStore.getState().entities.filter(e=>e.entity_kind==='UNIT'&&e.team_id===gridStore.getState().currentTeamId).map(e=>[e.id,e.simulation_state.world_position])));
 await wait(2200);
 const moved=await a.page.evaluate(starts=>gridStore.getState().entities.filter(e=>e.entity_kind==='UNIT'&&e.team_id===gridStore.getState().currentTeamId).map(e=>({code:e.unit_code,moved:JSON.stringify(e.simulation_state.world_position)!==JSON.stringify(starts[e.id])})),starts);
 assert.ok(moved.every(e=>e.moved));
 await a.page.getByRole('button',{name:'Chọn toàn quân',exact:true}).click();
 await a.page.getByRole('button',{name:'ĐỔI MỤC TIÊU',exact:true}).click();
 await a.page.waitForFunction(()=>gridStore.getState().entities.some(e=>e.simulation_state?.command_version>=1));
 await a.page.getByRole('button',{name:'RÚT TOÀN BỘ QUÂN',exact:true}).click();
 await a.page.locator('.army-confirm').getByRole('button',{name:'XÁC NHẬN RÚT QUÂN',exact:true}).click();
 await a.page.waitForFunction(()=>gridStore.getState().entities.filter(e=>e.entity_kind==='UNIT'&&e.team_id===gridStore.getState().currentTeamId).every(e=>e.simulation_state.order==='RETREAT'));
 report.movement={allThreeTypes:moved,retarget:true,retreatAll:true};
 await a.page.screenshot({path:shot('stars-live-retreat')});
 await a.context.close();await mate.context.close();await b.context.close();
 assert.deepEqual(report.errors,[]);report.status='PASS';console.log(JSON.stringify(report,null,2));
} catch(error) {report.failure=String(error);console.error(error);throw error;} finally {
 await fs.writeFile(new URL('../../docs/qa/roadside-stars-browser.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();
}
