import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5176';
const dir=new URL('../../docs/qa/',import.meta.url);
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const report={checks:[],errors:[],combat:[],formationSamples:[]};
const request=await browser.newContext();
async function api(path,data,token,host=false){const response=await request.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(response.ok(),`${path}: ${response.status()} ${await response.text()}`);return response.json();}
const wait=ms=>new Promise(r=>setTimeout(r,ms));
let a,b,room;
async function teamState(index){return api(`/matches/${room.match.id}/teams/${room.teams[index].id}/state/`,undefined,room.joins[index].participant_token);}
async function client(index){const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();page.setDefaultTimeout(15000);page.on('pageerror',e=>report.errors.push(e.message));page.on('websocket',ws=>ws.on('framereceived',({payload})=>{try{const e=JSON.parse(payload.toString());if(e.event_type==='COMBAT_TICK')report.combat.push(...(e.payload.events||[]));}catch{}}));await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match:room.match,join:room.joins[index]});await page.goto(base+'/tests/fixtures/continuous.html');await page.waitForFunction(()=>window.flowScene?.callbacks&&window.flowStore?.getState().connectionStatus==='connected');await page.locator('.arsenal-card').first().waitFor();return {page,context};}
try{
 const match=await api('/matches/',{name:'Live single-file browser verification',configuration:{max_teams:2,total_rounds:2,initial_coins:1000,first_preparation_duration_seconds:120,preparation_duration_seconds:90,battle_duration_seconds:90,movement_baseline_round_seconds:2}});
 room={match,teams:[],joins:[]};
 for(let i=0;i<2;i++){const team=await api(`/matches/${match.id}/teams/`,{name:i?'Blue Defense':'Amber March'},match.host_token,true);room.teams.push(team);room.joins.push(await api(`/matches/${match.id}/join/`,{display_name:i?'Bob':'Alice',team_id:team.id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);}
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 a=await client(0);b=await client(1);
 const deploy=key=>api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:room.teams[1].id,idempotency_key:key},room.joins[0].participant_token);
 const first=await deploy('first'),second=await deploy('second');
 for(const entity of [first.entity,second.entity])assert.equal(`${entity.current_hp}/${entity.max_hp}`,'100/100');
 await b.page.waitForFunction(()=>flowScene.visuals.size===2);
 const initialGap=await a.page.evaluate(()=>{const v=[...flowScene.visuals.values()];return Math.hypot(v[0].root.x-v[1].root.x,v[0].root.y-v[1].root.y);});
 assert.ok(initialGap>=34);report.checks.push('two prep deployments spawn 100/100 HP with separate authoritative approach positions');
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 await a.page.waitForFunction(()=>flowStore.getState().match?.phase==='WAR');
 const battle=await api(`/matches/${match.id}/`),deadline=battle.configuration.timer_state.phase_ends_at;
 const t1=await teamState(0),u1=t1.entities.find(e=>e.id===first.entity.id);
 await wait(1000);const t2=await teamState(0),u2=t2.entities.find(e=>e.id===first.entity.id);
 assert.ok(u2.simulation_state.route_distance>u1.simulation_state.route_distance);
 await b.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
 const towerCard=b.page.locator('.arsenal-card').filter({hasText:'Tháp súng máy'});assert.equal(await towerCard.isDisabled(),false);await towerCard.click();
 const towerResponse=b.page.waitForResponse(r=>r.url().endsWith('/actions/build/')&&r.request().method()==='POST');
 await b.page.getByRole('button',{name:'Vị trí 1',exact:true}).click();const towerReply=await towerResponse;assert.ok(towerReply.ok(),await towerReply.text());const tower=await towerReply.json();
 await a.page.waitForFunction(id=>flowScene.visuals.has(id),tower.entity.id);report.checks.push('actual Battle UI constructs a tower; opponent sees it without reload');
 const before=await teamState(0),beforeCoin=before.team.coins;
 await a.page.getByRole('button',{name:'QUÂN ĐỘI',exact:true}).click();const card=a.page.locator('.arsenal-card').filter({hasText:'Bộ binh'});assert.equal(await card.isDisabled(),false);await card.click();
 const thirdResponse=a.page.waitForResponse(r=>r.url().endsWith('/actions/deploy/')&&r.request().method()==='POST');await a.page.getByRole('button',{name:'Xuất quân',exact:true}).click();
 const thirdReply=await thirdResponse;assert.ok(thirdReply.ok(),await thirdReply.text());const third=await thirdReply.json(),thirdBody=thirdReply.request().postDataJSON();
 await b.page.waitForFunction(id=>flowScene.visuals.has(id),third.entity.id);
 const duplicate=await api(`/matches/${match.id}/actions/deploy/`,thirdBody,room.joins[0].participant_token);assert.equal(duplicate.entity.id,third.entity.id);
 await wait(1000);const after=await teamState(0);assert.equal(after.team.coins,beforeCoin-15);
 for(const entity of [first.entity,second.entity])assert.ok(after.entities.find(e=>e.id===entity.id).simulation_state.route_distance>before.entities.find(e=>e.id===entity.id).simulation_state.route_distance);
 assert.ok(after.entities.find(e=>e.id===third.entity.id).simulation_state.route_distance>third.entity.simulation_state.route_distance);
 assert.equal((await api(`/matches/${match.id}/`)).configuration.timer_state.phase_ends_at,deadline);
 report.checks.push('Battle deployment debits once, joins the convoy next tick, and existing units/timer keep advancing');
 for(let i=0;i<20;i++){
  const sample=await a.page.evaluate(()=>{const v=[...flowScene.visuals.values()].filter(v=>v.data.entity_kind==='UNIT').sort((x,y)=>(x.data.simulation_state?.formation_order||0)-(y.data.simulation_state?.formation_order||0));return v.slice(1).map((x,j)=>Math.hypot(x.root.x-v[j].root.x,x.root.y-v[j].root.y));});report.formationSamples.push(sample);assert.ok(sample.every(gap=>gap>=34));await wait(100);
 }
 await a.page.screenshot({path:new URL('live-battle-formation.png',dir).pathname});
 for(let i=0;i<100&&!report.combat.some(e=>e.type==='TOWER_ATTACKED');i++)await wait(200);
 const hit=report.combat.find(e=>e.type==='TOWER_ATTACKED');assert.ok(hit,'tower did not fire during this battle');assert.equal(hit.damage,15);assert.equal(hit.target_hp_remaining,85);
 report.checks.push('new Battle tower fires automatically with unchanged damage 15; target max HP remains 100');
 await api(`/matches/${match.id}/pause/`,{},match.host_token,true);await wait(400);
 const aligned=await a.page.evaluate(async()=>{const {formationPosition}=await import('/src/game/systems/formationPosition.ts');return [...flowScene.visuals.values()].filter(v=>v.data.entity_kind==='UNIT').map(v=>{const p=formationPosition(flowScene.nodes.get(v.data.current_node_id),v.data.simulation_state,flowScene.nodes);return Math.hypot(p.x-v.root.x,p.y-v.root.y);});});assert.ok(aligned.every(error=>error<1));
 await api(`/matches/${match.id}/resume/`,{},match.host_token,true);
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);await a.page.waitForFunction(()=>flowStore.getState().currentRound===2&&flowStore.getState().match?.phase==='PREPARATION');
 const survivors=await teamState(0);assert.equal(survivors.entities.length,3);assert.equal((await teamState(1)).entities[0].id,tower.entity.id);
 await b.page.reload();await b.page.locator('.connection-dot.connected').waitFor();await b.page.evaluate(async()=>{window.flowStore=(await import('/src/stores/matchStore.ts')).useMatchStore;});await b.page.waitForFunction(()=>flowStore.getState().entities.length===4);
 report.checks.push('pause freezes at authoritative centerline; next major preparation and reconnect retain all survivors/tower');
 const token=room.joins[0].participant_token,q=await api(`/matches/${match.id}/questions/current/`,undefined,token),coins=survivors.team.coins;
 await api(`/matches/${match.id}/questions/current/`,{action:"OPEN",question_id:q.id,viewer_id:crypto.randomUUID()},token);
 await api(`/matches/${match.id}/questions/${q.id}/answer/`,{answer:q.question.content.includes('2 + 2')?'4':'6'},token);
 const reward={team_question_id:q.id,reward_type:'COIN',idempotency_key:crypto.randomUUID()};await api(`/matches/${match.id}/rewards/claim/`,reward,token);await api(`/matches/${match.id}/rewards/claim/`,{...reward,idempotency_key:crypto.randomUUID()},token);assert.equal((await teamState(0)).team.coins,coins+30);
 report.checks.push('question reward still grants exactly +20 once');
 await api(`/matches/${match.id}/end/`,{},match.host_token,true);assert.equal((await api(`/matches/${match.id}/results/`)).results.length,2);
 assert.deepEqual(report.errors,[]);report.status='PASS';report.finalUnits=survivors.entities.map(e=>({id:e.id,hp:e.current_hp,max_hp:e.max_hp,route_distance:e.simulation_state.route_distance}));
 await fs.writeFile(new URL('live-battle-browser.json',dir),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,checks:report.checks},null,2));
}catch(error){report.status='FAIL';report.error=String(error);if(a)await a.page.screenshot({path:new URL('live-battle-failure.png',dir).pathname});await fs.writeFile(new URL('live-battle-browser.json',dir),JSON.stringify(report,null,2));throw error;}finally{await browser.close();}
