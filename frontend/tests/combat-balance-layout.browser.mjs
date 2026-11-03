// Disposable end-to-end checks: real React controls, two Phaser clients and 20-team batches.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5181';
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const request=await browser.newContext(), report={status:'RUNNING',scenarios:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,data,token,host=false,expected=200){
 const response=await request.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{},timeout:120000});
 assert.ok(expected===200?response.ok():response.status()===expected,`${path}: ${response.status()} ${await response.text()}`);return response.json();
}
async function room(count){
 const match=await api('/matches/',{name:`Batch QA ${count}`,configuration:{max_teams:count,initial_coins:5000,first_preparation_duration_seconds:600,preparation_duration_seconds:600,battle_duration_seconds:600}}),teams=[],joins=[];
 for(let i=0;i<count;i++){
  const team=await api(`/matches/${match.id}/teams/`,{name:`Batch Team ${i+1}`},match.host_token,true);teams.push(team);
  joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:team.id,role:'MENTEE'}));
  await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);
 }
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 return {match,teams,joins};
}
const host=(r,action)=>api(`/matches/${r.match.id}/${action}/`,{},r.match.host_token,true);
const deploy=(r,i,code,quantity,key=crypto.randomUUID())=>api(`/matches/${r.match.id}/actions/deploy/`,{unit_type_code_or_id:code,target_team_id:r.teams[(i+1)%r.teams.length].id,quantity,idempotency_key:key},r.joins[i].participant_token);
async function unlock(r,i,code){
 let question=await api(`/matches/${r.match.id}/questions/current/`,undefined,r.joins[i].participant_token);
 if(['REWARD_CLAIMED','ANSWER_INCORRECT','EXPIRED'].includes(question.status)) question=await api(`/matches/${r.match.id}/questions/current/`,{action:'NEXT',question_id:question.id},r.joins[i].participant_token);
 await api(`/matches/${r.match.id}/questions/current/`,{action:'OPEN',question_id:question.id,viewer_id:crypto.randomUUID()},r.joins[i].participant_token);
 await api(`/matches/${r.match.id}/questions/${question.id}/answer/`,{answer:question.question.content.includes('3 + 3')?'6':'4'},r.joins[i].participant_token);
 await api(`/matches/${r.match.id}/rewards/claim/`,{team_question_id:question.id,reward_type:'UNLOCK',unit_type_id:code,idempotency_key:crypto.randomUUID()},r.joins[i].participant_token);
}
async function client(r,i,viewport={width:1440,height:1000}){
 const context=await browser.newContext({viewport}),page=await context.newPage(),network={bytes:0,batches:0,ticks:0};
 page.setDefaultTimeout(20000);page.on('pageerror',e=>report.errors.push(e.message));
 page.on('websocket',ws=>ws.on('framereceived',({payload})=>{network.bytes+=Buffer.byteLength(payload);try{const e=JSON.parse(payload.toString());if(e.event_type==='ENTITIES_CREATED')network.batches++;if(e.event_type==='COMBAT_TICK'){network.ticks++;network.firstTick??=e.payload;}}catch{}}));
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match:r.match,join:r.joins[i]});
 await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
 await page.evaluate(()=>{window.batchCombatTicks=0;flowSocketClient.onEvent(e=>{if(e.event_type==='COMBAT_TICK')window.batchCombatTicks++;});});
 return {context,page,network};
}
const card=(c,name)=>c.page.locator('.arsenal-card').filter({hasText:name});
async function see(c,ids){await c.page.waitForFunction(ids=>ids.every(id=>flowScene.visuals.has(id)&&flowStore.getState().entities.some(e=>e.id===id)),ids);}
function normalize(entities){return entities.map(e=>({id:e.id,hp:e.current_hp,max:e.max_hp,range:e.range,speed:e.movement_speed,status:e.status,node:e.current_node_id,position:e.simulation_state?.world_position})).sort((a,b)=>a.id.localeCompare(b.id));}
async function agree(r,clients){
 const snapshot=await api(`/matches/${r.match.id}/snapshot/`);
 for(const c of clients){
  await c.page.waitForFunction(seq=>flowStore.getState().lastSequenceNumber>=seq,snapshot.sequence_number);
  assert.deepEqual(normalize(await c.page.evaluate(()=>flowStore.getState().entities)),normalize(snapshot.payload.entities));
  const ids=await c.page.evaluate(()=>[...flowScene.visuals.keys()]);
  assert.deepEqual(ids.sort(),snapshot.payload.entities.map(e=>e.id).sort());
 }
 return snapshot;
}
try {
 for (const count of [2,4,8,20]) {
  const r=await room(count);
  for(const i of [0,1]) {await unlock(r,i,'tank');await unlock(r,i,'artillery');}
  if(count>=4)await unlock(r,2,'cannon_tower');
  const clients=[await client(r,0),await client(r,1)], [a,b]=clients;
  assert.match(await card(a,'Pháo binh').getAttribute('title'),/80 HP.*Tốc độ 5.*1.5 node/);
  const ids=[];
  for(const i of [0,1])for(const [code,quantity] of [['infantry',5],['tank',3],['artillery',2]]) {
   const result=await deploy(r,i,code,quantity);
   assert.ok(result.entities.every(e=>e.status==='ACTIVE'&&e.simulation_state.movement_zone==='ROUTE'));
   if(code==='artillery')assert.ok(result.entities.every(e=>e.current_hp===80&&e.max_hp===80&&e.range===1.5&&e.movement_speed===5));
   ids.push(...result.entities.map(e=>e.id));
   await Promise.all(clients.map(c=>see(c,result.entities.map(e=>e.id))));
  }
  const towers=[];
  for(const i of [0,1]) {
   const c=clients[i];await c.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
   for(const slot of [1,6]) {
    await card(c,'Tháp súng máy').click();
    await c.page.getByRole('button',{name:`Vị trí ${slot}`,exact:true}).click();
    await c.page.waitForFunction(({i,slot})=>flowStore.getState().entities.some(e=>e.entity_kind==='TOWER'&&e.current_node_id===`node_tower_t${i+1}_slot${slot}`),{i,slot});
   }
  }
  if(count>=4) {
   const result=await api(`/matches/${r.match.id}/actions/build/`,{unit_type_code_or_id:'cannon_tower',node_id:'node_tower_t3_slot2'},r.joins[2].participant_token);
   assert.equal(result.entity.range,2);towers.push(result.entity.id);
  }
  const snapshot=await agree(r,clients);
  assert.equal(snapshot.payload.map_data.arena.version,4);
  for(let i=1;i<=count;i++)assert.equal(snapshot.payload.map_data.nodes.filter(n=>n.node_type==='tower_slot'&&n.team_index===i).length,6);
  for(const c of clients)await c.page.evaluate(()=>{window.originalVisuals=new Map(flowScene.visuals);frameSamples.length=0;});
  await host(r,'advance-phase');await wait(1800);
  for(const c of clients) {
   assert.ok(c.network.ticks>0);
   const moving=c.network.firstTick.entity_updates.filter(e=>e.entity_kind==='UNIT');
   assert.equal(moving.length,20);
   assert.ok(moving.every(e=>e.simulation_state.movement_state==='MOVING'));
   assert.ok(await c.page.evaluate(()=>[...originalVisuals].every(([id,v])=>flowScene.visuals.get(id)===v)));
  }
  await host(r,'pause');await agree(r,clients);
  for(const c of clients) {
   const projected=await c.page.evaluate(()=>[...flowScene.nodes.values()].filter(n=>n.node_type==='tower_slot').map(n=>({id:n.id,x:n.worldX,y:n.worldY})));
   assert.equal(projected.length,count*6);
  }
  if(towers.length) {
   await a.page.evaluate(id=>flowScene.callbacks.onEntityClick(id),towers[0]);
   await a.page.waitForFunction(()=>document.querySelector('.selection-stats')?.textContent.includes('2'));
   assert.ok(await a.page.evaluate(()=>flowScene.range.commandBuffer.length>0));
  }
  await b.page.evaluate(()=>history.replaceState(null,'','/tests/fixtures/continuous.html'));await b.page.reload();
  await b.page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
  await agree(r,clients);
  const frames=await a.page.evaluate(()=>frameSamples);
  if([4,20].includes(count))await a.page.screenshot({path:new URL(`../../docs/qa/combat-balance-layout-${count}.png`,import.meta.url).pathname});
  report.scenarios.push({teams:count,units:20,all_move_first_tick:true,artillery_hp:80,artillery_speed:5,artillery_range:1.5,cannon_range:2,slots:count*6,layout_version:4,two_client_agreement:true,stable_visuals:true,reconnect:true,frames});
  await host(r,'end');for(const c of clients)await c.context.close();
 }
 assert.deepEqual(report.errors,[]);report.status='PASS';
} catch(error) {report.status='FAIL';report.error=error.stack;for(const context of browser.contexts())for(const page of context.pages())if(page.url().includes('battle'))await page.screenshot({path:new URL('../../docs/qa/combat-balance-layout-failure.png',import.meta.url).pathname});throw error;}
finally {await fs.writeFile(new URL('../../docs/qa/combat-balance-layout-browser.json',import.meta.url),JSON.stringify(report,null,2));await request.close();await browser.close();}
