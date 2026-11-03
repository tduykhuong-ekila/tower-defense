// Two real clients, authoritative staging/passing, reload and battle commands.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5177';
const out=new URL('../../docs/qa/troop-movement-browser.json',import.meta.url);
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding']});
const request=await browser.newContext(), report={status:'RUNNING',checks:[],errors:[],simultaneous_frames:0};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,data,token,host=false){
 const response=await request.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});
 assert.ok(response.ok(),`${path}: ${response.status()} ${await response.text()}`);return response.json();
}
let match,teams=[],joins=[],clients=[];
async function client(index){
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),frames=[];
 page.setDefaultTimeout(20000);
 page.on('pageerror',e=>report.errors.push(e.message));
 page.on('websocket',ws=>ws.on('framereceived',({payload})=>{try{const e=JSON.parse(payload.toString());if(e.event_type==='COMBAT_TICK')frames.push(e.payload);}catch{}}));
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match,join:joins[index]});
 await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
 return {context,page,frames};
}
function normalize(entities){return entities.map(e=>({id:e.id,hp:e.current_hp,status:e.status,node:e.current_node_id,target:e.target_team_id,
  position:e.simulation_state?.world_position,zone:e.simulation_state?.movement_zone,moving:e.simulation_state?.movement_state,
  combat:e.simulation_state?.combat_state,attack_target:e.simulation_state?.attack_target_id,cooldown:e.simulation_state?.attack_remaining})).sort((a,b)=>a.id.localeCompare(b.id));}
async function agree(){
 const snapshot=await api(`/matches/${match.id}/snapshot/`);
 for(const c of clients){
  await c.page.waitForFunction(seq=>flowStore.getState().lastSequenceNumber>=seq,snapshot.sequence_number);
  const local=await c.page.evaluate(()=>({entities:flowStore.getState().entities,visuals:[...flowScene.visuals.keys()]}));
  assert.deepEqual(normalize(local.entities),normalize(snapshot.payload.entities));
  assert.deepEqual(local.visuals.sort(),snapshot.payload.entities.map(e=>e.id).sort());
 }
 report.final_version=snapshot.sequence_number;return snapshot;
}
try{
 match=await api('/matches/',{name:'Independent troop movement QA',configuration:{max_teams:4,max_active_units_per_team:6,total_rounds:2,initial_coins:2000,first_preparation_duration_seconds:120,preparation_duration_seconds:90,battle_duration_seconds:300,movement_baseline_round_seconds:8}});
 for(let i=0;i<4;i++){
  const team=await api(`/matches/${match.id}/teams/`,{name:`Movement ${i+1}`},match.host_token,true);teams.push(team);
  joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:team.id,role:'MENTEE'}));
  await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);
 }
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 const token=joins[0].participant_token,q=await api(`/matches/${match.id}/questions/current/`,undefined,token);
 await api(`/matches/${match.id}/questions/current/`,{action:"OPEN",question_id:q.id,viewer_id:crypto.randomUUID()},token);
 await api(`/matches/${match.id}/questions/${q.id}/answer/`,{answer:q.question.content.includes('2 + 2')?'4':'6'},token);
 const initialCoins=(await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,token)).team.coins;
 for(let i=0;i<2;i++)await api(`/matches/${match.id}/rewards/claim/`,{team_question_id:q.id,reward_type:'COIN',idempotency_key:crypto.randomUUID()},token);
 assert.equal((await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,token)).team.coins,initialCoins+30);
 report.checks.push('+30 coin reward remains claimable exactly once');
 const unlock=await api(`/matches/${match.id}/questions/current/`,{action:"NEXT",question_id:q.id},token);
 await api(`/matches/${match.id}/questions/current/`,{action:"OPEN",question_id:unlock.id,viewer_id:crypto.randomUUID()},token);
 await api(`/matches/${match.id}/questions/${unlock.id}/answer/`,{answer:unlock.question.content.includes('2 + 2')?'4':'6'},token);
 await api(`/matches/${match.id}/rewards/claim/`,{team_question_id:unlock.id,reward_type:'UNLOCK',unit_type_id:'artillery',idempotency_key:crypto.randomUUID()},token);
 clients=[await client(0),await client(1)];
 const buy=code=>api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:code,target_team_id:teams[1].id,idempotency_key:crypto.randomUUID()},token);
 const lead=(await buy('artillery')).entity,infantry=[];
 assert.equal(lead.max_hp,100);assert.equal(lead.simulation_state.movement_zone,'STAGING');
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 const tower=await api(`/matches/${match.id}/actions/build/`,{unit_type_code_or_id:'mg_tower',node_id:'node_tower_t2_slot1',idempotency_key:'live-tower'},joins[1].participant_token);
 await clients[0].page.waitForFunction(id=>flowScene.visuals.has(id),tower.entity.id);
 await clients[0].page.waitForFunction(id=>flowStore.getState().entities.some(e=>e.id===id&&e.simulation_state?.combat_state==='ATTACKING'),lead.id);
 // Give the slower ranged unit a head start, then introduce the live Infantry wave.
 // Speed-7 soldiers starting beside speed-4 Artillery otherwise arrive first.
 for(let i=0;i<5;i++)infantry.push((await buy('infantry')).entity);
 assert.equal(new Set(infantry.map(e=>JSON.stringify(e.simulation_state.world_position))).size,5);
 assert.ok(infantry.every(e=>e.simulation_state.movement_zone==='ROUTE'&&e.current_hp===80&&e.max_hp===80));
 for(const c of clients)await c.page.waitForFunction(()=>flowScene.visuals.size===7);
 report.checks.push('five distinct server rally positions, immediate live Infantry eligibility at 80 HP, Artillery retains 100 HP');
 await clients[0].page.screenshot({path:new URL('../../docs/qa/troop-staging.png',import.meta.url).pathname});
 const started=Date.now();
 while(Date.now()-started<25000){
  const simultaneous=clients[0].frames.filter(f=>f.entity_updates.some(e=>e.id===lead.id&&e.simulation_state?.combat_state==='ATTACKING'&&e.simulation_state?.movement_state==='STOPPED')
    && f.entity_updates.some(e=>infantry.some(u=>u.id===e.id)&&e.simulation_state?.movement_state==='MOVING'));
  report.simultaneous_frames=simultaneous.length;
  if(simultaneous.length>=5)break;
  await wait(100);
 }
 assert.ok(report.simultaneous_frames>=5,'no simultaneous stopped attacker and moving follower frames');
 for(const c of clients){
  assert.ok(c.frames.some(f=>f.events.some(e=>e.type==='UNIT_ATTACKED'&&e.attacker_id===lead.id)));
  const moving=new Set(c.frames.flatMap(f=>f.entity_updates.filter(e=>infantry.some(u=>u.id===e.id)&&e.simulation_state?.movement_state==='MOVING').map(e=>e.id)));
  assert.equal(moving.size,5);
 }
 report.checks.push('both clients see artillery attacks while all five infantry independently receive movement');
 await clients[0].page.screenshot({path:new URL('../../docs/qa/troop-independent-combat.png',import.meta.url).pathname});
 await api(`/matches/${match.id}/pause/`,{},match.host_token,true);await wait(500);await agree();
 await clients[1].page.evaluate(()=>history.replaceState(null,'','/tests/fixtures/continuous.html'));
 await clients[1].page.reload();await clients[1].page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');await agree();
 report.checks.push('pause and reload restore exact physical positions, zones, combat states, targets and cooldowns');
 const survivors=(await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,token)).entities.map(e=>e.id).sort();
 await api(`/matches/${match.id}/resume/`,{},match.host_token,true);
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 const state=await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,token);
 assert.deepEqual(state.entities.map(e=>e.id).sort(),survivors);
 report.checks.push('next major round retains surviving troops');
 await api(`/matches/${match.id}/end/`,{},match.host_token,true);
 assert.deepEqual(report.errors,[]);report.status='PASS';console.log(JSON.stringify(report,null,2));
}catch(error){report.status='FAIL';report.error=String(error);throw error;}
finally{await fs.writeFile(out,JSON.stringify(report,null,2));await browser.close();}
