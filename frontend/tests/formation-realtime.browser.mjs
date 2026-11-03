// Two independent authenticated Chrome contexts; disposable server only.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5177';
const output=new URL('../../docs/qa/formation-realtime-browser.json',import.meta.url);
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const request=await browser.newContext();
const report={status:'RUNNING',scenarios:[],page_errors:[]};
async function api(path,data,token,host=false){
 const response=await request.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});
 assert.ok(response.ok(),`${path} ${response.status()} ${await response.text()}`);return response.json();
}
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function createRoom(count){
 const match=await api('/matches/',{name:`Formation recovery QA ${count}`,configuration:{max_teams:count,max_active_units_per_team:10,total_rounds:2,initial_coins:2000,first_preparation_duration_seconds:300,preparation_duration_seconds:120,battle_duration_seconds:300,movement_baseline_round_seconds:1}});
 const teams=[],joins=[];
 for(let i=0;i<count;i++){
  const team=await api(`/matches/${match.id}/teams/`,{name:`Team ${i+1}`},match.host_token,true);teams.push(team);
  joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:team.id,role:'MENTEE'}));
  await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);
 }
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 // Unlock Tank through the normal question/reward flow before Battle.
 const token=joins[0].participant_token,q=await api(`/matches/${match.id}/questions/current/`,undefined,token);
 await api(`/matches/${match.id}/questions/current/`,{action:"OPEN",question_id:q.id,viewer_id:crypto.randomUUID()},token);
 await api(`/matches/${match.id}/questions/${q.id}/answer/`,{answer:q.question.content.includes('2 + 2')?'4':'6'},token);
 await api(`/matches/${match.id}/rewards/claim/`,{team_question_id:q.id,reward_type:'UNLOCK',unit_type_id:'tank',idempotency_key:crypto.randomUUID()},token);
 return {match,teams,joins};
}
async function client(r,index){
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();page.setDefaultTimeout(20000);
 const metrics={events:[],latencies:[],snapshots:0,combat:[]};
 page.on('pageerror',e=>report.page_errors.push(e.message));
 page.on('websocket',ws=>ws.on('framereceived',({payload})=>{try{const e=JSON.parse(payload.toString());if(e.sequence_number&&e.event_type!=='MATCH_STATE_SNAPSHOT'){metrics.events.push(e.sequence_number);metrics.latencies.push(Date.now()-Date.parse(e.server_timestamp));}if(e.event_type==='MATCH_STATE_SNAPSHOT')metrics.snapshots++;if(e.event_type==='COMBAT_TICK')metrics.combat.push(...(e.payload.events||[]));}catch{}}));
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match:r.match,join:r.joins[index]});
 await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&window.flowStore?.getState().connectionStatus==='connected'&&flowStore.getState().match);
 return {context,page,metrics};
}
const buy=(r,index,code='infantry',key=crypto.randomUUID())=>api(`/matches/${r.match.id}/actions/deploy/`,{unit_type_code_or_id:code,target_team_id:r.teams[(index+1)%r.teams.length].id,idempotency_key:key},r.joins[index].participant_token);
const build=(r,index,slot=1,key=crypto.randomUUID())=>api(`/matches/${r.match.id}/actions/build/`,{unit_type_code_or_id:'mg_tower',node_id:`node_tower_t${index+1}_slot${slot}`,idempotency_key:key},r.joins[index].participant_token);
async function see(c,id){await c.page.waitForFunction(id=>window.flowScene?.visuals.has(id),id);}
function normalized(entities){return entities.map(e=>({id:e.id,hp:e.current_hp,status:e.status,node:e.current_node_id,next:e.simulation_state?.next_node_id||null,progress:e.simulation_state?.edge_progress||0,staging:e.simulation_state?.staging_distance||0,target:e.target_team_id})).sort((a,b)=>a.id.localeCompare(b.id));}
async function convergence(r,clients){
 const snapshot=await api(`/matches/${r.match.id}/snapshot/`);
 const expected=normalized(snapshot.payload.entities);
 for(const c of clients){
  await c.page.waitForFunction(seq=>flowStore.getState().lastSequenceNumber>=seq,snapshot.sequence_number);
  const local=await c.page.evaluate(()=>({sequence:flowStore.getState().lastSequenceNumber,entities:flowStore.getState().entities,ids:[...flowScene.visuals.keys()]}));
  assert.deepEqual(normalized(local.entities),expected);
  assert.deepEqual(local.ids.sort(),expected.map(e=>e.id).sort());
  assert.equal(local.sequence,snapshot.sequence_number);
 }
 return {version:snapshot.sequence_number,entities:expected.length,divergent_entities:0,duplicate_sprites:0};
}
try{
 for(const count of [4,8,20]){
  const r=await createRoom(count),a=await client(r,0),b=await client(r,1),scenario={teams:count,checks:[],action_latency_ms:[]};
  for(const code of ['infantry','tank']){
   const start=Date.now(),reply=await buy(r,0,code);await see(b,reply.entity.id);scenario.action_latency_ms.push(Date.now()-start);
   assert.equal(reply.entity.max_hp,100);scenario.checks.push(`opponent sees ${code} without reload`);
  }
  const start=Date.now(),tower=await build(r,1);await see(a,tower.entity.id);scenario.action_latency_ms.push(Date.now()-start);
  for(let team=0;team<count;team++){
   for(let j=0;j<3;j++)await buy(r,team);
   if(team!==1)await build(r,team);
  }
  await api(`/matches/${r.match.id}/advance-phase/`,{},r.match.host_token,true);
  await a.page.waitForFunction(()=>flowStore.getState().match?.phase==='WAR');
  // Concurrent live commands and idempotent retries through actual HTTP handlers.
  const coinsBefore=(await api(`/matches/${r.match.id}/teams/${r.teams[0].id}/state/`,undefined,r.joins[0].participant_token)).team.coins;
  const key=crypto.randomUUID(),towerKey=crypto.randomUUID();
  const commands=await Promise.all([buy(r,0,'infantry',key),buy(r,0,'infantry',key),build(r,1,2,towerKey),build(r,1,2,towerKey)]);
  assert.equal(commands[0].entity.id,commands[1].entity.id);assert.equal(commands[2].entity.id,commands[3].entity.id);
  assert.equal((await api(`/matches/${r.match.id}/teams/${r.teams[0].id}/state/`,undefined,r.joins[0].participant_token)).team.coins,coinsBefore-15);
  scenario.checks.push('concurrent Battle deploy/build retries preserve one entity per key and debit once');
  const combatStart=Date.now();
  while(!a.metrics.combat.some(e=>e.type==='ENTITY_DESTROYED')&&Date.now()-combatStart<45000)await wait(200);
  assert.ok(a.metrics.combat.some(e=>e.type==='ENTITY_DESTROYED'),'combat destruction was not observed');
  assert.ok(b.metrics.combat.some(e=>e.type==='ENTITY_DESTROYED'));
  scenario.combat_measurement_ms=Date.now()-combatStart;
  scenario.combat_attacks=a.metrics.combat.filter(e=>['UNIT_ATTACKED','TOWER_ATTACKED'].includes(e.type)).length;
  scenario.combat_destructions=a.metrics.combat.filter(e=>e.type==='ENTITY_DESTROYED').length;
  await api(`/matches/${r.match.id}/pause/`,{},r.match.host_token,true);await wait(500);
  scenario.before_recovery=await convergence(r,[a,b]);
  scenario.checks.push('movement and HP agree with authoritative snapshot on both clients');
  // Real disconnect; deployment while the opponent has no socket, then automatic reconnect.
  await b.context.setOffline(true);
  await b.page.evaluate(()=>window.flowSocketClient.ws?.close(4000,"QA disconnect"));
  const disconnected=Date.now();
  // Live purchases require active Battle; resume while B is offline.
  await api(`/matches/${r.match.id}/resume/`,{},r.match.host_token,true);
  const offline=await buy(r,0);await build(r,1,3);await wait(300);
  await b.context.setOffline(false);await b.page.evaluate(()=>window.dispatchEvent(new Event('online')));
  await see(b,offline.entity.id);await b.page.waitForFunction(()=>window.flowSocketClient.ws?.readyState===1);scenario.reconnect_recovery_ms=Date.now()-disconnected;
  scenario.checks.push('offline opponent recovers deployments and towers automatically without reload');
  // Artificially delay a real frame until after newer frames/snapshot have arrived.
  const snapshotsBeforeInjection=b.metrics.snapshots;
  await b.page.evaluate(async()=>{
   const socket=window.flowSocketClient.ws,original=socket.onmessage;
   window.heldRealtimeFrame=null;
   socket.onmessage=event=>{const e=JSON.parse(event.data);if(!window.heldRealtimeFrame&&e.event_type==='COMBAT_TICK'){window.heldRealtimeFrame=event.data;return;}original.call(socket,event);};
   window.deliverHeldFrame=()=>{if(window.heldRealtimeFrame)original.call(socket,{data:window.heldRealtimeFrame});};
  });
  await b.page.waitForFunction(()=>window.heldRealtimeFrame);
  await wait(800);
  const pre=await b.page.evaluate(()=>flowStore.getState().lastSequenceNumber);
  await b.page.evaluate(()=>window.deliverHeldFrame());
  assert.ok(await b.page.evaluate(()=>flowStore.getState().lastSequenceNumber)>=pre);
  await api(`/matches/${r.match.id}/pause/`,{},r.match.host_token,true);await wait(600);
  scenario.after_recovery=await convergence(r,[a,b]);
  assert.ok(b.metrics.snapshots>snapshotsBeforeInjection);scenario.injected_delayed_frames=1;
  scenario.checks.push('dropped/out-of-order movement frame triggers recovery and cannot roll state back');
  // Metrics include raw socket deliveries: retries may be duplicates, cursors converge.
  for(const c of [a,b]){
   const sorted=[...new Set(c.metrics.events)].sort((x,y)=>x-y),gaps=sorted.slice(1).reduce((n,s,i)=>n+Math.max(0,s-sorted[i]-1),0);
   scenario[c===a?'client_a':'client_b']={raw_events:c.metrics.events.length,raw_duplicates:c.metrics.events.length-new Set(c.metrics.events).size,observed_raw_sequence_gaps:gaps,snapshots:c.metrics.snapshots,latency_p95_ms:c.metrics.latencies.sort((x,y)=>x-y)[Math.floor(c.metrics.latencies.length*.95)]};
  }
  const performance=await a.page.evaluate(()=>({frames:frameSamples,heap_bytes:performance.memory?.usedJSHeapSize}));scenario.performance=performance;
  if(count===4)await a.page.screenshot({path:new URL('../../docs/qa/formation-realtime.png',import.meta.url).pathname});
  await api(`/matches/${r.match.id}/end/`,{},r.match.host_token,true);
  await a.context.close();await b.context.close();report.scenarios.push(scenario);
  await fs.writeFile(output,JSON.stringify(report,null,2));console.log(JSON.stringify(scenario));
 }
 assert.deepEqual(report.page_errors,[]);report.status='PASS';
}catch(error){report.status='FAIL';report.error=String(error);throw error;}
finally{await fs.writeFile(output,JSON.stringify(report,null,2));await browser.close();}
