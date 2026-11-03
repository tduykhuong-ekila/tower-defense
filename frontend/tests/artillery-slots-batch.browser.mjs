// Disposable end-to-end checks: real React controls, two Phaser clients and 20-team batches.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5177';
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
 page.on('websocket',ws=>ws.on('framereceived',({payload})=>{network.bytes+=Buffer.byteLength(payload);try{const e=JSON.parse(payload.toString());if(e.event_type==='ENTITIES_CREATED')network.batches++;if(e.event_type==='COMBAT_TICK')network.ticks++;}catch{}}));
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match:r.match,join:r.joins[i]});
 await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
 await page.evaluate(()=>{window.batchCombatTicks=0;flowSocketClient.onEvent(e=>{if(e.event_type==='COMBAT_TICK')window.batchCombatTicks++;});});
 return {context,page,network};
}
const card=(c,name)=>c.page.locator('.arsenal-card').filter({hasText:name});
async function see(c,ids){await c.page.waitForFunction(ids=>ids.every(id=>flowScene.visuals.has(id)&&flowStore.getState().entities.some(e=>e.id===id)),ids);}
function normalize(entities){return entities.map(e=>({id:e.id,hp:e.current_hp,max:e.max_hp,range:e.range,status:e.status,node:e.current_node_id,position:e.simulation_state?.world_position})).sort((a,b)=>a.id.localeCompare(b.id));}
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
try{
 const r=await room(4);await unlock(r,0,'artillery');await unlock(r,1,'tank');
 const clients=[await client(r,0),await client(r,1)],a=clients[0],b=clients[1];
 await card(a,'Bộ binh').click();
 await a.page.getByRole('button',{name:'5',exact:true}).click();
 assert.match(await a.page.locator('.quantity-total').innerText(),/Tổng: 75 xu/);
 assert.match(await card(a,'Pháo binh').getAttribute('title'),/70 HP.*1.5 node/);
 await a.page.getByRole('button',{name:'Xuất 5 Bộ binh',exact:true}).click();
 await a.page.waitForFunction(()=>flowStore.getState().entities.filter(e=>e.unit_code==='infantry').length===5);
 const infantry=await a.page.evaluate(()=>flowStore.getState().entities.filter(e=>e.unit_code==='infantry').map(e=>e.id));
 await see(b,infantry);
 assert.equal(await a.page.getByRole('spinbutton',{name:'Số lượng quân'}).inputValue(),'5');
 await a.page.getByRole('button',{name:'Tăng số lượng'}).click();await a.page.getByRole('button',{name:'Giảm số lượng'}).click();
 await a.page.getByRole('spinbutton',{name:'Số lượng quân'}).fill('1.5');
 assert.equal(await a.page.locator('.deploy-controls .gold-button').isDisabled(),true);
 assert.match(await a.page.locator('.quantity-error').innerText(),/số nguyên/);
 await a.page.getByRole('button',{name:'Max',exact:true}).click();
 assert.equal(await a.page.getByRole('spinbutton',{name:'Số lượng quân'}).inputValue(),String(Math.floor(4925/15)));
 await a.page.getByRole('spinbutton',{name:'Số lượng quân'}).fill('5');
 await a.page.screenshot({path:new URL('../../docs/qa/batch-quantity-desktop.png',import.meta.url).pathname});
 await b.page.getByRole('button',{name:'QUÂN ĐỘI',exact:true}).click();
 await card(b,'Xe tăng').click();await b.page.getByRole('spinbutton',{name:'Số lượng quân'}).fill('3');
 await b.page.getByRole('button',{name:'Xuất 3 Xe tăng',exact:true}).click();
 await b.page.waitForFunction(()=>flowStore.getState().entities.filter(e=>e.unit_code==='tank').length===3);
 const tanks=await b.page.evaluate(()=>flowStore.getState().entities.filter(e=>e.unit_code==='tank').map(e=>e.id));await see(a,tanks);
 const build=(slot,key=crypto.randomUUID())=>api(`/matches/${r.match.id}/actions/build/`,{unit_type_code_or_id:'mg_tower',node_id:`node_tower_t1_slot${slot}`,idempotency_key:key},r.joins[0].participant_token);
 for(let slot=1;slot<=5;slot++)await build(slot);
 await a.page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();await card(a,'Tháp súng máy').click();
 await a.page.getByRole('button',{name:'Vị trí 6',exact:true}).click();
 await b.page.waitForFunction(()=>flowStore.getState().entities.filter(e=>e.entity_kind==='TOWER').length===6);
 const seventh=await api(`/matches/${r.match.id}/actions/build/`,{unit_type_code_or_id:'mg_tower',node_id:'node_tower_t1_slot6'},r.joins[0].participant_token,false,400);
 assert.equal(seventh.error_code,'TOWER_LIMIT_REACHED');
 const artillery=await deploy(r,0,'artillery',2,'artillery-two');
 assert.ok(artillery.entities.every(e=>e.current_hp===70&&e.max_hp===70&&e.range===1.5));
 const retry=await deploy(r,0,'artillery',2,'artillery-two');assert.deepEqual(retry.entities.map(e=>e.id),artillery.entities.map(e=>e.id));
 await see(a,artillery.entities.map(e=>e.id));await see(b,artillery.entities.map(e=>e.id));
 await host(r,'advance-phase');await wait(1800);
 assert.ok(clients.every(c=>c.network.ticks>0));
 await host(r,'pause');await agree(r,clients);
 const inspected=artillery.entities[0].id;
 // Click the entity through the real scene hit area after focusing its rally area.
 await a.page.evaluate(id=>{flowScene.callbacks.onEntityClick(id);flowScene.focusBase();},inspected);
 await a.page.waitForFunction(()=>document.querySelector('.selection-stats')?.textContent.includes('1.5'));
 assert.ok(await a.page.evaluate(()=>flowScene.range.commandBuffer.length>0));
 await a.page.evaluate(()=>flowSocketClient.requestSync());
 await b.page.evaluate(()=>history.replaceState(null,'','/tests/fixtures/continuous.html'));await b.page.reload();
 await b.page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
 await agree(r,clients);
 const mobile=await client(r,0,{width:390,height:844});
 // Resume so quantity controls can be selected, then keep a stable UI screenshot.
 await host(r,'resume');await card(mobile,'Bộ binh').click();await mobile.page.getByRole('button',{name:'5',exact:true}).click();
 const bounds=await mobile.page.locator('.quantity-panel').boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=390&&bounds.y>=0);
 await mobile.page.screenshot({path:new URL('../../docs/qa/batch-quantity-mobile.png',import.meta.url).pathname});
 report.scenarios.push({teams:4,quantity_controls:true,total_cost:75,tanks:3,artillery_hp:70,artillery_range:1.5,sixth_tower:true,seventh_rejected:true,retry_deduplicated:true,two_client_agreement:true,reconnect:true,mobile_bounds:bounds});
 await host(r,'end');for(const c of [...clients,mobile])await c.context.close();
 const load=await room(20),loadClients=[await client(load,0),await client(load,1)],started=Date.now();
 for(let i=0;i<20;i+=4)await Promise.all(Array.from({length:4},(_,k)=>deploy(load,i+k,'infantry',50,`load-${i+k}`)));
 const creationMs=Date.now()-started;
 for(const c of loadClients)await c.page.waitForFunction(()=>flowStore.getState().entities.length===1000&&flowScene.visuals.size===1000);
 await agree(load,loadClients);await host(load,'advance-phase');
 await Promise.all(loadClients.map(c=>c.page.evaluate(()=>{frameSamples.length=0;flowScene.focusBase();})));
 await wait(5000);await host(load,'pause');const loadSnapshot=await agree(load,loadClients);
 assert.ok(loadSnapshot.payload.entities.every(e=>e.simulation_state.route_distance>0));
 const metrics=await Promise.all(loadClients.map(c=>c.page.evaluate(()=>({frames:frameSamples,applied_combat_ticks:window.batchCombatTicks,entities:flowStore.getState().entities.length,sprites:flowScene.visuals.size}))));
 report.scenarios.push({teams:20,quantity_per_team:50,entities:1000,creation_ms:creationMs,clients:metrics.map((m,i)=>({...m,websocket_events:loadClients[i].network})),duplicates:0,divergent_entities:0});
 await loadClients[0].page.screenshot({path:new URL('../../docs/qa/batch-20-team.png',import.meta.url).pathname});
 await host(load,'end');for(const c of loadClients)await c.context.close();
 assert.deepEqual(report.errors,[]);report.status='PASS';
}catch(error){report.status='FAIL';report.error=String(error);throw error;}
finally{await fs.writeFile(new URL('../../docs/qa/artillery-slots-batch-browser.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();}
