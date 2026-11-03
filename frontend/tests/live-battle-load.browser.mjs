import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5176',dir=new URL('../../docs/qa/',import.meta.url);
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const errors=[],report={checks:[],scenarios:[]},request=await browser.newContext();
async function api(path,data,token,host=false){const r=await request.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),`${path}: ${r.status()} ${await r.text()}`);return r.json();}
async function room(count,rounds=2){
 const match=await api('/matches/',{name:`Continuous browser ${count}`,configuration:{total_rounds:rounds,max_teams:count,initial_coins:1000,first_preparation_duration_seconds:120,preparation_duration_seconds:4,battle_duration_seconds:12,movement_baseline_round_seconds:1}}),teams=[],joins=[];
 for(let i=0;i<count;i++){const team=await api(`/matches/${match.id}/teams/`,{name:`Team ${i+1}`},match.host_token,true);teams.push(team);joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:team.id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);}
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);return {match,teams,joins};
}
async function client(r,index){
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}}),page=await ctx.newPage(),network={bytes:0,ticks:0,latencies:[]};page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 page.on('websocket',ws=>ws.on('framereceived',({payload})=>{const text=payload.toString();network.bytes+=Buffer.byteLength(text);try{const e=JSON.parse(text);if(e.event_type==='COMBAT_TICK'){network.ticks++;network.latencies.push(Date.now()-Date.parse(e.server_timestamp));}}catch{}}));
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match:r.match,join:r.joins[index]});await page.goto(base+'/tests/fixtures/continuous.html');await page.waitForFunction(()=>window.flowScene?.callbacks&&window.flowStore?.getState().connectionStatus==='connected');
return {ctx,page,network};
}
async function buy(r,index,kind,slot=1){return api(`/matches/${r.match.id}/actions/${kind}/`,kind==='deploy'?{unit_type_code_or_id:'infantry',target_team_id:r.teams[(index+1)%r.teams.length].id,idempotency_key:crypto.randomUUID()}:{unit_type_code_or_id:'mg_tower',node_id:`node_tower_t${index+1}_slot${slot}`,idempotency_key:crypto.randomUUID()},r.joins[index].participant_token);}
const phase=r=>api(`/matches/${r.match.id}/advance-phase/`,{},r.match.host_token,true);
const visuals=page=>page.evaluate(()=>({ids:window.flowScene?[...flowScene.visuals.keys()]:flowStore.getState().entities.map(e=>e.id),entities:flowStore.getState().entities}));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
try{
 const r=await room(2),a=await client(r,0),b=await client(r,1);
 const deployedAt=Date.now(),unit=await buy(r,0,'deploy');
 const uid=unit.entity.id;
 await b.page.waitForFunction(id=>flowScene.visuals.has(id),uid);report.checks.push({name:'opponent sees REST deployment without reload',latency_ms:Date.now()-deployedAt});
 await a.page.evaluate(()=>{flowScene.time.paused=true;flowScene.playCombatEvents([{type:'TEAM_SCORE_UPDATED',team_id:'test',score:0}]);});
 const builtAt=Date.now(),tower=await buy(r,1,'build'),tid=tower.entity.id;
 await a.page.waitForFunction(id=>flowScene.visuals.has(id),tid);report.checks.push({name:'opponent sees tower without reload',latency_ms:Date.now()-builtAt});
 await a.page.evaluate(()=>{flowScene.time.paused=false;flowScene.skipCombat();});
 assert.equal((await visuals(a.page)).ids.length,2);assert.equal((await visuals(b.page)).ids.length,2);
 for(let i=0;i<4;i++)await buy(r,0,'deploy');await phase(r);
 await a.page.waitForFunction(()=>flowStore.getState().match?.phase==='WAR');
 const before=await a.page.evaluate(()=>[...flowScene.visuals.values()].find(v=>v.data.entity_kind==='UNIT').root.x);await pause(700);
 const after=await a.page.evaluate(()=>[...flowScene.visuals.values()].find(v=>v.data.entity_kind==='UNIT').root.x);assert.notEqual(before,after);assert.equal(await a.page.evaluate(()=>flowScene.playing),false);
 await a.page.screenshot({path:new URL('live-battle-load.png',dir).pathname});
 await b.page.reload();await b.page.evaluate(async()=>{window.flowStore=(await import('/src/stores/matchStore.ts')).useMatchStore;});await b.page.waitForFunction(()=>window.flowStore?.getState().match?.phase==='WAR');
 assert.deepEqual((await visuals(a.page)).ids.sort(),(await visuals(b.page)).ids.sort());
 await a.page.waitForFunction(()=>flowStore.getState().currentRound===2&&flowStore.getState().match?.phase==='PREPARATION',null,{timeout:20000});
 assert.ok((await visuals(a.page)).entities.some(e=>e.id===tid));report.checks.push({name:'continuous movement, live effects, reconnect and persistent tower in next preparation'});
 await a.page.waitForFunction(()=>flowStore.getState().match?.status==='FINISHED',null,{timeout:25000});
 assert.equal((await api(`/matches/${r.match.id}/results/`)).results.length,2);report.checks.push({name:'complete two-round multiplayer match and persisted ranking'});
 await a.page.screenshot({path:new URL('live-battle-load-results.png',dir).pathname});await a.ctx.close();await b.ctx.close();
 for(const count of [2,4,8,12,20]){
  const r=await room(count,3);for(let t=0;t<count;t++){for(let i=0;i<3;i++)await buy(r,t,'build',i+1);for(let i=0;i<5;i++)await buy(r,t,'deploy');}
  const c=await client(r,0),netStart=c.network.bytes,tickStart=c.network.ticks,start=Date.now();await phase(r);await pause(7500);
  const m=await c.page.evaluate(()=>({metrics:frameSamples,heap:performance.memory?.usedJSHeapSize,entities:flowStore.getState().entities.length,visuals:flowScene.visuals.size,unique:new Set([...flowScene.visuals.keys()]).size}));
  await api(`/matches/${r.match.id}/pause/`,{},r.match.host_token,true);await pause(400);
  const server=await api(`/matches/${r.match.id}/teams/${r.teams[0].id}/state/`,undefined,r.joins[0].participant_token),local=(await visuals(c.page)).entities;
  const divergent=server.entities.filter(e=>{const l=local.find(x=>x.id===e.id);return !l||l.current_hp!==e.current_hp||l.current_node_id!==e.current_node_id||Math.abs((l.simulation_state?.edge_progress||0)-(e.simulation_state?.edge_progress||0))>1e-6||Math.abs((l.simulation_state?.staging_distance||0)-(e.simulation_state?.staging_distance||0))>1e-6;});assert.equal(divergent.length,0);assert.equal(m.visuals,m.unique);
  report.scenarios.push({teams:count,initial_entities:count*8,final_entities:m.entities,measured_seconds:(Date.now()-start)/1000,ticks:c.network.ticks-tickStart,websocket_bytes:c.network.bytes-netStart,websocket_kb_s:+((c.network.bytes-netStart)/(Date.now()-start)).toFixed(2),fps_samples:m.metrics.map(x=>x.fps),frame_p95_ms_samples:m.metrics.map(x=>x.frameMsP95),heap_mb:+(m.heap/1048576).toFixed(1),divergent_own_entities:divergent.length,event_latency_ms_p95:c.network.latencies.sort((a,b)=>a-b)[Math.floor(c.network.latencies.length*.95)]});
  await api(`/matches/${r.match.id}/end/`,{},r.match.host_token,true);await c.ctx.close();console.log(JSON.stringify(report.scenarios.at(-1)));
 }
 assert.deepEqual(errors,[]);report.status='PASS';report.page_errors=errors;await fs.writeFile(new URL('live-battle-load.json',dir),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}catch(e){report.status='FAIL';report.error=String(e);report.page_errors=errors;await fs.writeFile(new URL('live-battle-load.json',dir),JSON.stringify(report,null,2));throw e;}finally{await browser.close();}
