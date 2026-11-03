import {createRequire} from 'node:module';import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright'),base=process.env.TEST_BASE_URL||'http://127.0.0.1:5198';
const room=JSON.parse(await fs.readFile('/private/tmp/roadside-stars-rooms.json','utf8'))[0];
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--enable-precise-memory-info']});
const report={status:'RUNNING',scenarios:[],liveLayouts:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
try {
 const clients=[];
 for(const join of room.joins.slice(0,2)) {
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
  await page.goto(base);await page.evaluate(r=>localStorage.setItem('grid-room',JSON.stringify(r)),{...room,join});await page.goto(base+'/tests/fixtures/grid-placement.html');
  await page.waitForFunction(()=>window.gridStore?.getState().connectionStatus==='connected'&&window.gridScene?.state.mapData);clients.push({context,page});
 }
 const [a,b]=clients;
 for(const quantity of [25,50]) {
  for(const [index,client] of clients.entries()) {
   const cells=await client.page.evaluate(async quantity=>{
    const {placementReason}=await import('/src/game/placement.ts'),s=gridScene,g=s.state.mapData.placement_grid,f=g.footprints.mg_tower;
    let entities=[...s.state.entities];const cells=[],current=entities.filter(e=>e.team_id===s.state.myTeamId&&e.entity_kind==='TOWER'&&e.status!=='DESTROYED').length;
    for(let row=0;row<=g.rows-f.heightCells;row++)for(let col=0;col<=g.cols-f.widthCells;col++) {
     if(cells.length>=quantity-current)return cells;
     const cell={row,col};if(placementReason(s.state.mapData,cell,'mg_tower',s.state.myTeamId,entities))continue;
     cells.push(cell);entities=[...entities,{entity_kind:'TOWER',status:'ACTIVE',current_node_id:'',simulation_state:{grid_placement:{...cell,...f}}}];
    }return cells;
   },quantity);
   for(const cell of cells){const response=await client.page.request.post(`${base}/api/v1/matches/${room.match.id}/actions/build/`,{headers:{'X-Participant-Token':room.joins[index].participant_token},data:{unit_type_code_or_id:'mg_tower',grid_row:cell.row,grid_col:cell.col,idempotency_key:`star-load-${index}-${cell.row}-${cell.col}`}});assert.ok(response.ok(),await response.text());}
  }
  for(const client of clients)await client.page.waitForFunction(n=>gridStore.getState().entities.filter(e=>e.entity_kind==='TOWER'&&e.status!=='DESTROYED').length>=n*2,quantity);
  if(quantity===25)for(const [index,client] of clients.entries()){
   const response=await client.page.request.post(`${base}/api/v1/matches/${room.match.id}/actions/deploy/`,{headers:{'X-Participant-Token':room.joins[index].participant_token},data:{unit_type_code_or_id:'infantry',target_team_id:room.map.team_ids[1-index],quantity:50,idempotency_key:`star-load-army-${index}`}});assert.ok(response.ok(),await response.text());
  }
  const metrics=await a.page.evaluate(async()=>{
   const startSeq=gridStore.getState().lastSequenceNumber,frames=[];let previous=performance.now();const start=previous;
   await new Promise(resolve=>{function next(t){frames.push(t-previous);previous=t;if(t-start<2200)requestAnimationFrame(next);else resolve()}requestAnimationFrame(next)});
   return {rafFPS:Math.round(frames.length/2.2),maxFrameMs:Math.round(Math.max(...frames)),heapMB:Math.round(performance.memory.usedJSHeapSize/1048576*10)/10,receivedSequences:gridStore.getState().lastSequenceNumber-startSeq,towers:gridStore.getState().entities.filter(e=>e.entity_kind==='TOWER'&&e.status!=='DESTROYED').length,troops:gridStore.getState().entities.filter(e=>e.entity_kind==='UNIT'&&e.status!=='DESTROYED').length};
  });assert.equal(metrics.towers,quantity*2);assert.ok(metrics.receivedSequences>0);report.scenarios.push({towersPerTeam:quantity,...metrics});
 }
 await a.page.keyboard.press('Escape');
 for(const viewport of [{width:1440,height:1000},{width:390,height:844},{width:320,height:844},{width:844,height:390}]) {
  await a.page.setViewportSize(viewport);
  for(const category of ['QUÂN ĐỘI','CÔNG SỰ']){
   await a.page.getByRole('button',{name:category,exact:true}).click();await wait(80);
   const dimensions=await a.page.locator('.game-item-card').evaluateAll(cards=>cards.map(card=>{const r=card.getBoundingClientRect(),name=card.querySelector('strong'),art=card.querySelector('img');return {x:r.x,right:r.right,height:r.height,artHeight:art.getBoundingClientRect().height,overflow:name.scrollHeight>name.clientHeight+1||name.scrollWidth>name.clientWidth+1}}));
   assert.equal(dimensions.length,3);assert.ok(dimensions.every(d=>d.x>=0&&d.right<=viewport.width+1&&!d.overflow));
   await a.page.screenshot({path:new URL(`../../docs/qa/stars-live-${category==='QUÂN ĐỘI'?'army':'towers'}-${viewport.width}.png`,import.meta.url).pathname});report.liveLayouts.push({viewport,category,dimensions});
  }
 }
 for(const c of clients)await c.context.close();assert.deepEqual(report.errors,[]);report.status='PASS';console.log(JSON.stringify(report,null,2));
}catch(error){report.failure=String(error);throw error;}finally{await fs.writeFile(new URL('../../docs/qa/roadside-stars-load.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();}
