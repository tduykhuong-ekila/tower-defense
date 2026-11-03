// Two authenticated teams deploy live and observe the same Infantry combat/deaths.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5181';
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const request=await browser.newContext(),report={status:'RUNNING',errors:[]},clients=[];
async function api(path,data,token,host=false){const r=await request.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),`${path}: ${r.status()} ${await r.text()}`);return r.json();}
let match;
try{
 match=await api('/matches/',{name:'Bidirectional Infantry combat',configuration:{max_teams:2,initial_coins:1000,first_preparation_duration_seconds:600,battle_duration_seconds:600,movement_baseline_round_seconds:8}});
 const teams=[],joins=[];
 for(let i=0;i<2;i++){
  const team=await api(`/matches/${match.id}/teams/`,{name:`Combat ${i+1}`},match.host_token,true);teams.push(team);
  joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:team.id,role:'MENTEE'}));
  await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);
 }
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 for(const join of joins){
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();clients.push({context,page});
  page.on('pageerror',e=>report.errors.push(e.message));
  await page.goto(base);await page.evaluate(room=>localStorage.setItem('continuous-room',JSON.stringify(room)),{match,join});
  await page.goto(base+'/tests/fixtures/continuous.html');
  await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
  await page.evaluate(()=>{
   window.combatProbe={events:[],moving:new Set(),created:new Map(),root_movement_from_shot:0};
   flowSocketClient.onEvent(e=>{if(e.event_type==='COMBAT_TICK')combatProbe.events.push(...e.payload.events);});
   const scene=flowScene,create=scene.createEntity.bind(scene),animate=scene.animateEvent.bind(scene);
   scene.createEntity=(e,...rest)=>{combatProbe.created.set(e.id,(combatProbe.created.get(e.id)||0)+1);return create(e,...rest);};
   scene.animateEvent=(e,...rest)=>{const v=scene.visuals.get(e.attacker_id||e.unit_id),x=v?.root.x,y=v?.root.y;animate(e,...rest);if(v&&(v.root.x!==x||v.root.y!==y))combatProbe.root_movement_from_shot++;};
   scene.events.on('postupdate',()=>{for(const [id,v] of scene.visuals)if(v.data.simulation_state?.movement_state==='MOVING')combatProbe.moving.add(id);});
  });
 }
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 const deployed=[];
 for(let n=0;n<5;n++)for(let i=0;i<2;i++)deployed.push((await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[1-i].id,idempotency_key:`both-${n}`},joins[i].participant_token)).entity);
 for(const {page} of clients)await page.waitForFunction(ids=>ids.every(id=>combatProbe.created.has(id)),deployed.map(e=>e.id));
 for(const {page} of clients)await page.waitForFunction(teamIds=>teamIds.every(id=>combatProbe.events.some(e=>e.type==='UNIT_ATTACKED'&&e.attacker_team_id===id))&&combatProbe.events.some(e=>e.type==='ENTITY_DESTROYED'),teams.map(t=>t.id),{timeout:45000});
 await api(`/matches/${match.id}/pause/`,{},match.host_token,true);
 const snapshot=await api(`/matches/${match.id}/snapshot/`);
 const normalize=entities=>entities.map(e=>({id:e.id,hp:e.current_hp,position:e.simulation_state?.world_position,cooldown:e.simulation_state?.attack_remaining})).sort((a,b)=>a.id.localeCompare(b.id));
 report.clients=[];
 for(const {page} of clients){
  await page.waitForFunction(seq=>flowStore.getState().lastSequenceNumber>=seq,snapshot.sequence_number);
  await page.waitForFunction(ids=>flowScene.visuals.size===ids.length&&ids.every(id=>flowScene.visuals.has(id)),snapshot.payload.entities.map(e=>e.id));
  const state=await page.evaluate(()=>({entities:flowStore.getState().entities,visuals:[...flowScene.visuals.keys()],created:[...combatProbe.created.values()],moving:[...combatProbe.moving],events:combatProbe.events,root_movement_from_shot:combatProbe.root_movement_from_shot}));
  assert.deepEqual(normalize(state.entities),normalize(snapshot.payload.entities));
  assert.deepEqual(state.visuals.sort(),snapshot.payload.entities.map(e=>e.id).sort());
  assert.ok(state.created.every(n=>n===1));assert.equal(state.moving.length,10);assert.equal(state.root_movement_from_shot,0);
  const attacks=state.events.filter(e=>e.type==='UNIT_ATTACKED');assert.ok(attacks.every(e=>e.damage===5&&e.hp_damage===5));
  report.clients.push({attack_teams:[...new Set(attacks.map(e=>e.attacker_team_id))].length,attacks:attacks.length,deaths:state.events.filter(e=>e.type==='ENTITY_DESTROYED').length,moved:state.moving.length,identity_replacements:0,shots_resetting_position:0,authoritative_state_matches:true});
 }
 assert.deepEqual(report.errors,[]);report.status='PASS';console.log(JSON.stringify(report,null,2));
}catch(error){report.status='FAIL';report.error=String(error);throw error;}finally{
 if(match)await api(`/matches/${match.id}/end/`,{},match.host_token,true).catch(()=>{});
 await fs.writeFile(new URL('../../docs/qa/infantry-combat.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();
}
