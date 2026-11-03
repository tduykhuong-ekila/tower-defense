// Two independent clients, 20-team aggregate load, paid live deployment and recovery.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5181';
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const request=await browser.newContext(),report={status:'RUNNING',scenarios:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,data,token,host=false){
 const response=await request.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{},timeout:120000});
 assert.ok(response.ok(),`${path}: ${response.status()} ${await response.text()}`);return response.json();
}
function normalize(entities){return entities.map(e=>({id:e.id,hp:e.current_hp,max:e.max_hp,status:e.status,node:e.current_node_id,target:e.target_team_id,position:e.simulation_state?.world_position,progress:e.simulation_state?.edge_progress,crowd:e.simulation_state?.crowd_offset})).sort((a,b)=>a.id.localeCompare(b.id));}
async function client(room,index){
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),network={bytes:0,ticks:0};
 page.setDefaultTimeout(60000);page.on('pageerror',e=>report.errors.push(e.message));
 page.on('websocket',ws=>ws.on('framereceived',({payload})=>{const text=payload.toString();network.bytes+=Buffer.byteLength(text);try{if(JSON.parse(text).event_type==='COMBAT_TICK')network.ticks++;}catch{}}));
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match:room.match,join:room.joins[index]});
 await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
 await page.evaluate(()=>{window.infantryTickCount=0;flowSocketClient.onEvent(e=>{if(e.event_type==='COMBAT_TICK')window.infantryTickCount++;});});
 return {context,page,network};
}
try{
 for(const quantity of [20,50,100]){
  const match=await api('/matches/',{name:`Infantry load 20 x ${quantity}`,configuration:{max_teams:20,max_active_units_per_team:1,total_rounds:2,initial_coins:10000,first_preparation_duration_seconds:600,preparation_duration_seconds:600,battle_duration_seconds:600,movement_baseline_round_seconds:30}}),teams=[],joins=[];
  for(let i=0;i<20;i++){
   const team=await api(`/matches/${match.id}/teams/`,{name:`Infantry ${i+1}`},match.host_token,true);teams.push(team);
   joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:team.id,role:'MENTEE'}));
   await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);
  }
  const room={match,teams,joins};await api(`/matches/${match.id}/start/`,{},match.host_token,true);
  const buy=(i,key)=>api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[(i+1)%20].id,idempotency_key:key},joins[i].participant_token);
  // Distinct teams submit concurrently; each request passes the real transaction path.
  for(let j=0;j<quantity;j++)for(let batch=0;batch<20;batch+=4)await Promise.all(Array.from({length:4},(_,k)=>buy(batch+k,`load-${j}`)));
  const clients=[await client(room,0),await client(room,1)];
  const initial=await api(`/matches/${match.id}/snapshot/`);assert.equal(initial.payload.entities.length,quantity*20);
  for(const c of clients){
   await c.page.waitForFunction(total=>flowScene.visuals.size===total,quantity*20);
   const card=c.page.locator('.arsenal-card').filter({hasText:'Bộ binh'});assert.equal(await card.isDisabled(),false);
   assert.match(await card.innerText(),/80 HP.*7/s);
  }
  await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
  const started=Date.now(),net=clients.map(c=>c.network.bytes);
  await Promise.all(clients.map(c=>c.page.evaluate(()=>{frameSamples.length=0;flowScene.focusBase();})));
  const live=await Promise.all([buy(0,'live-a'),buy(1,'live-b')]);
  const retry=await buy(0,'live-a');assert.equal(retry.entity.id,live[0].entity.id);
  for(const c of clients)for(const e of live)await c.page.waitForFunction(id=>flowScene.visuals.has(id),e.entity.id);
  await wait(6000);
  const metrics=[];
  for(let i=0;i<clients.length;i++)metrics.push(await clients[i].page.evaluate(()=>({fps:frameSamples.map(x=>x.fps),frame_p95_ms:frameSamples.map(x=>x.frameMsP95),heap_mb:performance.memory?.usedJSHeapSize/1048576,visible:[...flowScene.visuals.values()].filter(v=>v.root.visible).length,pool:flowScene.infantryPool.length,entities:flowStore.getState().entities.length,combat_ticks:window.infantryTickCount})));
  await api(`/matches/${match.id}/pause/`,{},match.host_token,true);
  const snapshot=await api(`/matches/${match.id}/snapshot/`);
  for(const c of clients){
   await c.page.waitForFunction(seq=>flowStore.getState().lastSequenceNumber>=seq,snapshot.sequence_number);
   const local=await c.page.evaluate(()=>({entities:flowStore.getState().entities,ids:[...flowScene.visuals.keys()]}));
   assert.deepEqual(normalize(local.entities),normalize(snapshot.payload.entities));
   assert.deepEqual(local.ids.sort(),snapshot.payload.entities.map(e=>e.id).sort());
   assert.ok(local.entities.every(e=>e.simulation_state?.movement_state==='MOVING'));
  }
  await clients[1].page.evaluate(()=>history.replaceState(null,'','/tests/fixtures/continuous.html'));
  await clients[1].page.reload();await clients[1].page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
  await clients[1].page.waitForFunction(({sequence,total})=>flowStore.getState().lastSequenceNumber>=sequence&&flowStore.getState().entities.length===total,{sequence:snapshot.sequence_number,total:snapshot.payload.entities.length});
  assert.deepEqual(normalize(await clients[1].page.evaluate(()=>flowStore.getState().entities)),normalize(snapshot.payload.entities));
  for(const i of [0,1]){
   const state=await api(`/matches/${match.id}/teams/${teams[i].id}/state/`,undefined,joins[i].participant_token);
   assert.equal(state.team.coins,10000-(quantity+1)*15);assert.equal(state.limits.infantry.max,null);
  }
  await clients[0].page.screenshot({path:new URL(`../../docs/qa/infantry-${quantity}.png`,import.meta.url).pathname});
  report.scenarios.push({teams:20,infantry_per_team:quantity,initial_entities:quantity*20,final_entities:snapshot.payload.entities.length,measured_seconds:(Date.now()-started)/1000,clients:metrics.map((m,i)=>({...m,websocket_kb_per_second:(clients[i].network.bytes-net[i])/(Date.now()-started)*1000/1024})),divergent_entities:0,duplicate_sprites:0,reconnect_restored:true,paid_live_deployments_both_directions:true});
  console.log(JSON.stringify(report.scenarios.at(-1)));
  await api(`/matches/${match.id}/end/`,{},match.host_token,true);for(const c of clients)await c.context.close();
 }
 assert.deepEqual(report.errors,[]);report.status='PASS';
}catch(error){report.status='FAIL';report.error=String(error);throw error;}
finally{await fs.writeFile(new URL('../../docs/qa/infantry-browser.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();}
