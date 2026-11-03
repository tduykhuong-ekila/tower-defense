import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'}),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5176';
async function api(path,data,token,host=false){const r=await context.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),await r.text());return r.json();}
try{
 const match=await api('/matches/',{name:'30-unit approach camera verification',configuration:{max_teams:2,max_active_units_per_team:30,initial_coins:1000}}),teams=[],joins=[];
 for(let i=0;i<2;i++){const t=await api(`/matches/${match.id}/teams/`,{name:`Capacity ${i}`},match.host_token,true);teams.push(t);joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Member ${i}`,team_id:t.id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${t.id}/ready/`,{is_ready:true},match.host_token,true);}
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 await page.goto(base);await page.evaluate(r=>localStorage.setItem('continuous-room',JSON.stringify(r)),{match,join:joins[0]});await page.goto(base+'/tests/fixtures/continuous.html');await page.waitForFunction(()=>window.flowScene?.callbacks&&window.flowStore?.getState().connectionStatus==='connected');
 let last;
 for(let i=0;i<30;i++)last=await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[1].id,idempotency_key:`capacity-${i}`},joins[0].participant_token);
 await page.waitForFunction(()=>flowScene.visuals.size===30);
 await page.evaluate(id=>{const root=flowScene.visuals.get(id).root;flowScene.navigate(root.x,root.y,.8);},last.entity.id);
 await page.waitForTimeout(800);
 const position=await page.evaluate(id=>{const v=flowScene.visuals.get(id),c=flowScene.cameras.main;return {visible:v.root.visible,interactive:v.root.input.enabled,x:(v.root.x-c.worldView.x)*c.zoom+c.x,y:(v.root.y-15-c.worldView.y)*c.zoom+c.y};},last.entity.id);
 console.log(JSON.stringify(position));
 assert.ok(position.visible&&position.interactive);assert.ok(position.x>0&&position.x<1440&&position.y>120&&position.y<800);
 await page.mouse.click(position.x,position.y);await page.waitForFunction(id=>flowScene.state.selectedEntityId===id,last.entity.id);
 const snapshot=(await api(`/matches/${match.id}/snapshot/`)).payload;
 assert.equal(new Set(snapshot.entities.map(e=>JSON.stringify(e.simulation_state.world_position))).size,30);
 assert.ok(snapshot.entities.every(e=>e.simulation_state.movement_zone==='STAGING'));
 const proof={status:'PASS',units:30,lastTroopHP:`${last.entity.current_hp}/${last.entity.max_hp}`,lastTroopPosition:last.entity.simulation_state.world_position,distinctStagingPositions:30,lastTroopPannableAndInspectable:true};
 await fs.writeFile(new URL('../../docs/qa/live-battle-capacity.json',import.meta.url),JSON.stringify(proof,null,2));console.log(JSON.stringify(proof));await api(`/matches/${match.id}/end/`,{},match.host_token,true);
}finally{await browser.close();}
