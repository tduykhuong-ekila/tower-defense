// Real HTTP, WebSockets, React HUD and Phaser input in a disposable three-client arena.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5183';
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const req=await browser.newContext(),report={status:'RUNNING',scenarios:[],errors:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,data,token,host=false,status=200){
 const r=await req.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{},timeout:120000});
 assert.ok(status===200?r.ok():r.status()===status,`${path}: ${r.status()} ${await r.text()}`);return r.json();
}
async function room(count){
 const match=await api('/matches/',{name:`Army QA ${count}`,configuration:{max_teams:count,initial_coins:5000,first_preparation_duration_seconds:600,battle_duration_seconds:600}}),teams=[],joins=[];
 for(let i=0;i<count;i++){
  teams.push(await api(`/matches/${match.id}/teams/`,{name:`Army ${i+1}`},match.host_token,true));
  joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:teams[i].id,role:'MENTEE'}));
  await api(`/matches/${match.id}/teams/${teams[i].id}/ready/`,{is_ready:true},match.host_token,true);
 }
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 return {match,teams,joins};
}
const host=(r,action)=>api(`/matches/${r.match.id}/${action}/`,{},r.match.host_token,true);
const deploy=(r,i,code,quantity=1)=>api(`/matches/${r.match.id}/actions/deploy/`,{unit_type_code_or_id:code,target_team_id:r.teams[(i+1)%r.teams.length].id,quantity,idempotency_key:crypto.randomUUID()},r.joins[i].participant_token);
async function quiz(r,i,unlock){
 const current=await api(`/matches/${r.match.id}/questions/current/`,undefined,r.joins[i].participant_token);
 const q=await api(`/matches/${r.match.id}/questions/current/`,{action:'OPEN_SESSION',question_id:current.id,viewer_id:crypto.randomUUID()},r.joins[i].participant_token);
 await api(`/matches/${r.match.id}/questions/${q.id}/answer/`,{answer:q.question.content.includes('3 + 3')?'6':'4'},r.joins[i].participant_token);
 return api(`/matches/${r.match.id}/rewards/claim/`,{team_question_id:q.id,reward_type:unlock?'UNLOCK':'COIN',...(unlock?{unit_type_id:unlock}:{}),idempotency_key:crypto.randomUUID()},r.joins[i].participant_token);
}
async function client(r,i,viewport={width:1440,height:1000},touch=false){
 const context=await browser.newContext({viewport,hasTouch:touch}),page=await context.newPage();
 page.setDefaultTimeout(20000);page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match:r.match,join:r.joins[i]});
 await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
 return {context,page};
}
async function focus(c,x,y,zoom=1.1){
 await c.page.evaluate(({x,y,zoom})=>{flowScene.zoomController.moveTo(x,y,zoom,true);},{x,y,zoom});
 await wait(150);
}
async function screen(c,point){return c.page.evaluate(({x,y})=>{const cam=flowScene.cameras.main,canvas=flowScene.game.canvas.getBoundingClientRect();return {x:canvas.left+cam.x+cam.width/2+(x-cam.scrollX-cam.width/2)*cam.zoom,y:canvas.top+cam.y+cam.height/2+(y-cam.scrollY-cam.height/2)*cam.zoom};},point);}
async function clickUnit(c,id,modifiers=[]){
 const point=await c.page.evaluate(id=>{const v=flowScene.visuals.get(id);return {x:v.root.x,y:v.root.y-18};},id);
 await focus(c,point.x,point.y);
 const p=await screen(c,point);
 for(const key of modifiers)await c.page.keyboard.down(key);
 await c.page.mouse.click(p.x,p.y);
 for(const key of modifiers)await c.page.keyboard.up(key);
}
async function orders(clients,ids,order){for(const c of clients)await c.page.waitForFunction(({ids,order})=>ids.every(id=>flowStore.getState().entities.find(e=>e.id===id)?.simulation_state?.order===order),{ids,order});}
try{
 const two=await room(2);
 const twoClients=[await client(two,0),await client(two,1,{width:1280,height:900},true)];
 for(let i=0;i<2;i++){
  const c=twoClients[i];
  await c.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();
  for(let slot=1;slot<=6;slot++){
   await c.page.locator('.arsenal-card').filter({hasText:'Tháp súng máy'}).click();
   const node=await c.page.evaluate(id=>{const n=flowScene.nodes.get(id);return {x:n.worldX,y:n.worldY};},`node_tower_t${i+1}_slot${slot}`);
   await focus(c,node.x,node.y);
   const p=await screen(c,node);
   if(i===1)await c.page.touchscreen.tap(p.x,p.y);else await c.page.mouse.click(p.x,p.y);
   await c.page.waitForFunction(id=>flowStore.getState().entities.some(e=>e.entity_kind==='TOWER'&&e.current_node_id===id),`node_tower_t${i+1}_slot${slot}`);
  }
  await c.page.screenshot({path:`../docs/qa/army-slots-team-${i+1}.png`});
 }
 report.scenarios.push('Two teams: all 12 slots built through actual Phaser hit testing, mouse and touch');
 await host(two,'end');for(const c of twoClients)await c.context.close();
 const r=await room(3);
 await quiz(r,0,'tank');await quiz(r,0,'artillery');
 const clients=[await client(r,0),await client(r,1),await client(r,2)],a=clients[0];
 // Hidden deadline expires without activating another question. User click opens the next directly.
 await a.page.locator('.quest-card').click();
 await a.page.getByRole('dialog',{name:'Câu hỏi tri thức'}).waitFor();
 const q=await a.page.evaluate(()=>flowStore.getState().currentQuestion);
 await a.page.getByRole('button',{name:'Đóng câu hỏi'}).first().click();
 await wait(9000);
 let same=await api(`/matches/${r.match.id}/questions/current/`,undefined,r.joins[0].participant_token);
 assert.equal(same.id,q.id);assert.equal(same.status,'EXPIRED');
 await a.page.locator('.quest-card').click();
 await a.page.getByRole('dialog',{name:'Câu hỏi tri thức'}).waitFor();
 await a.page.waitForFunction(seq=>flowStore.getState().currentQuestion.sequence_number>seq,q.sequence_number);
 assert.equal(await a.page.getByRole('button',{name:'Câu hỏi tiếp theo',exact:true}).count(),0);
 await a.page.getByRole('button',{name:'Đóng câu hỏi'}).first().click();
 report.scenarios.push('Quiz hidden expiry and explicit reopen without NEXT confirmation');
 const units=[];
 for(const code of ['infantry','tank','artillery'])units.push((await deploy(r,0,code)).entity);
 const ids=units.map(e=>e.id);
 for(const c of clients)await c.page.waitForFunction(ids=>ids.every(id=>flowScene.visuals.has(id)),ids);
 for(const c of clients)await c.page.evaluate(()=>window.armyOriginalVisuals=new Map(flowScene.visuals));
 await host(r,'advance-phase');
 await a.page.getByRole('button',{name:'RÚT TOÀN BỘ QUÂN',exact:true}).waitFor();
 // Keep enemy objectives far away while testing input and orders.
 await clickUnit(a,ids[0]);
 await a.page.waitForFunction(()=>flowScene.state.selectedArmyIds.length===1);
 await clickUnit(a,ids[1],['Shift']);
 await a.page.waitForFunction(()=>flowScene.state.selectedArmyIds.length===2);
 await a.page.locator('#army-target').selectOption(r.teams[2].id);
 await a.page.getByRole('button',{name:'ĐỔI MỤC TIÊU',exact:true}).click();
 await orders(clients,ids.slice(0,2),'ATTACK');
 for(const c of clients){
  const targets=await c.page.evaluate(ids=>ids.map(id=>flowStore.getState().entities.find(e=>e.id===id)?.target_team_id),ids);
  assert.deepEqual(targets,[r.teams[2].id,r.teams[2].id,r.teams[1].id]);
 }
 report.scenarios.push('Single and modifier selection, selected-only retarget replicated to Teams B and C');
 await a.page.getByRole('button',{name:'Chọn toàn quân',exact:true}).click();
 assert.match(await a.page.locator('.army-command-panel').innerText(),/Nhiều mục tiêu/);
 await a.page.getByRole('button',{name:'RÚT TOÀN BỘ QUÂN',exact:true}).click();
 await a.page.getByRole('alertdialog').waitFor();
 await a.page.getByRole('button',{name:'XÁC NHẬN RÚT QUÂN',exact:true}).click();
 // Some troops can arrive at home before the slowest browser observes RETREAT.
 for(const c of clients)await c.page.waitForFunction(ids=>ids.every(id=>['RETREAT','AT_RALLY'].includes(flowStore.getState().entities.find(e=>e.id===id)?.simulation_state?.order)),ids);
 await orders(clients,ids,'AT_RALLY');
 for(const c of clients){
  const returned=await c.page.evaluate(ids=>ids.map(id=>flowStore.getState().entities.find(e=>e.id===id)),ids);
  assert.ok(returned.every(e=>e.current_hp===units.find(u=>u.id===e.id).current_hp&&e.level===units.find(u=>u.id===e.id).level));
 }
 const arrived=await a.page.evaluate(ids=>ids.map(id=>flowStore.getState().entities.find(e=>e.id===id).simulation_state.world_position),ids);
 await wait(600);
 assert.deepEqual(await a.page.evaluate(ids=>ids.map(id=>flowStore.getState().entities.find(e=>e.id===id).simulation_state.world_position),ids),arrived);
 for(const c of clients)assert.ok(await c.page.evaluate(()=>[...armyOriginalVisuals].every(([id,v])=>flowScene.visuals.get(id)===v)));
 report.scenarios.push('Mixed Infantry/Tank/Artillery retreat, independent return, HP preservation and rally idle on all three clients');
 // Box selection around all returned mobile troops, with camera position invariant.
 await a.page.getByRole('button',{name:'Bỏ chọn',exact:true}).click();
 await a.page.getByRole('button',{name:'Kéo chọn: TẮT',exact:true}).click();
 const rect=await a.page.evaluate(ids=>{const points=ids.map(id=>flowScene.visuals.get(id).root);return {left:Math.min(...points.map(p=>p.x))-45,right:Math.max(...points.map(p=>p.x))+45,top:Math.min(...points.map(p=>p.y))-60,bottom:Math.max(...points.map(p=>p.y))+25};},ids);
 await focus(a,(rect.left+rect.right)/2,(rect.top+rect.bottom)/2);
 const beforeCamera=await a.page.evaluate(()=>({x:flowScene.cameras.main.scrollX,y:flowScene.cameras.main.scrollY}));
 const start=await screen(a,{x:rect.left,y:rect.top}),end=await screen(a,{x:rect.right,y:rect.bottom});
 await a.page.mouse.move(start.x,start.y);await a.page.mouse.down();await a.page.mouse.move(end.x,end.y,{steps:12});await a.page.mouse.up();
 await a.page.waitForFunction(()=>flowScene.state.selectedArmyIds.length===3);
 assert.deepEqual(await a.page.evaluate(()=>({x:flowScene.cameras.main.scrollX,y:flowScene.cameras.main.scrollY})),beforeCamera);
 await a.page.getByRole('button',{name:'ĐỔI MỤC TIÊU',exact:true}).click();await orders(clients,ids,'ATTACK');
 await clients[2].page.goto(base+'/tests/fixtures/continuous.html');await clients[2].page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');await orders([clients[2]],ids,'ATTACK');
 const enemy=(await deploy(r,1,'infantry')).entity;
 for(const c of clients)await c.page.waitForFunction(id=>flowStore.getState().entities.some(e=>e.id===id),enemy.id);
 await a.page.screenshot({path:'../docs/qa/army-controls-battle.png'});
 report.scenarios.push('Box selection preserves camera; returned troops attack again; client reconnect and new enemy deployment converge');
 await host(r,'end');for(const c of clients)await c.context.close();
 report.status='PASS';assert.deepEqual(report.errors,[]);
}catch(error){report.status='FAIL';report.failure=error.stack;console.error(error);for(const context of browser.contexts())for(const page of context.pages())await page.screenshot({path:'../docs/qa/army-control-failure.png'}).catch(()=>{});process.exitCode=1;}
finally{await fs.writeFile('../docs/qa/army-control-browser.json',JSON.stringify(report,null,2));await browser.close();}
