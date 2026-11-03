// Real REST, WebSocket, React and Phaser acceptance. Local disposable QA rooms only.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {openCoinBag} from './helpers/coin-bag.mjs';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5182';
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const context=await browser.newContext({viewport:{width:1440,height:1000}}), request=context.request;
const report={status:'RUNNING',errors:[],vegetation:[]};
let debugPage;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,data,token,host=false,expected){
 const r=await request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{},timeout:30000});
 assert.ok(expected?r.status()===expected:r.ok(),`${path}: ${r.status()} ${await r.text()}`);return r.json();
}
async function makeRoom(count=2,bank){
 const match=await api('/matches/',{name:`Upgrade QA ${count}`,configuration:{max_teams:count,initial_coins:10000,initial_base_hp:5000,first_preparation_duration_seconds:600,preparation_duration_seconds:600,battle_duration_seconds:600,max_active_units_per_team:30},...(bank?{question_bank_id:bank.id,question_bank_token:bank.token}:{})});
 const teams=[],joins=[];
 for(let i=0;i<count;i++) {teams.push(await api(`/matches/${match.id}/teams/`,{name:`Upgrade Team ${i+1}`},match.host_token,true));joins.push(await api(`/matches/${match.id}/join/`,{display_name:`QA ${i}`,team_id:teams[i].id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${teams[i].id}/ready/`,{is_ready:true},match.host_token,true);}
 const teammate=await api(`/matches/${match.id}/join/`,{display_name:'QA teammate',team_id:teams[0].id,role:'MENTEE'});
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);return {match,teams,joins,teammate};
}
async function openPage(room,join){const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));await page.goto(base);await page.evaluate(r=>localStorage.setItem('continuous-room',JSON.stringify(r)),{match:room.match,join});await page.goto(base+'/tests/fixtures/continuous.html');await page.waitForFunction(()=>window.flowScene?.visuals&&window.flowStore?.getState().connectionStatus==='connected');return page;}
try {
 const bankToken=crypto.randomUUID();
 const upload=await request.post(base+'/api/v1/question-banks/upload/',{headers:{'X-Question-Bank-Token':bankToken},multipart:{file:{name:'team-upgrades.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:await fs.readFile(new URL('./fixtures/team-upgrades.xlsx',import.meta.url))}}});
 assert.ok(upload.ok(),await upload.text());const bank={...await upload.json(),token:bankToken};
 const r=await makeRoom(2,bank),token=r.joins[0].participant_token;
 await fs.writeFile('/private/tmp/team-upgrade-room.json',JSON.stringify(r));
 const page=await openPage(r,r.joins[0]); debugPage=page; const mate=await openPage(r,r.teammate),opponent=await openPage(r,r.joins[1]);
 await page.bringToFront();
 const qurl=`/matches/${r.match.id}/questions/current/`, state=()=>api(`/matches/${r.match.id}/teams/${r.teams[0].id}/state/`,undefined,token);
 let q=await api(qurl,undefined,token);assert.equal(q.timer.status,'NOT_STARTED');
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Câu hỏi tri thức'});
 await dialog.getByRole('button',{name:/^A\./}).click();
 const opened=await api(qurl,undefined,token),deadline=opened.expires_at;
 await wait(1100);await dialog.getByRole('button',{name:'Đóng câu hỏi',exact:true}).first().click();await dialog.waitFor({state:'hidden'});
 await wait(2200);const hidden=await api(qurl,undefined,token);
 assert.equal(hidden.id,q.id);assert.equal(hidden.timer.status,'RUNNING');assert.ok(hidden.timer.remaining_ms<opened.timer.remaining_ms-2000);
 await mate.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();assert.equal((await api(qurl,undefined,token)).expires_at,deadline);
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();assert.ok((await dialog.getByRole('button',{name:/^A\./}).getAttribute('style')).includes('2px solid'));
 await dialog.getByRole('button',{name:'Xác Nhận Nộp Bài'}).click();await page.getByRole('button',{name:'Mở túi coin · 20–60',exact:true}).waitFor();
 const beforeReward=(await state()).team.coins;const receipt=await openCoinBag(page);await page.locator('.reward-overlay').waitFor({state:'hidden'});
 assert.equal((await state()).team.coins,beforeReward+receipt.coin_amount);await api(`/matches/${r.match.id}/rewards/claim/`,{team_question_id:q.id,reward_type:'COIN',idempotency_key:'reward-retry'},token);assert.equal((await state()).team.coins,beforeReward+receipt.coin_amount);
 // Explicitly reopen the answered result, then Continue. Unlocks still use correct-answer rewards.
 await page.getByRole('button',{name:'Xem kết quả câu hỏi',exact:true}).click();assert.equal((await api(qurl,undefined,token)).id,q.id);
 await dialog.getByRole('button',{name:'Câu hỏi tiếp theo',exact:true}).click();
 await dialog.getByText(/THỬ THÁCH CHIẾN LƯỢC #2/).waitFor();
 for(const code of ['tank','artillery','cannon_tower','shield_generator']) {
   q=await api(qurl,undefined,token);
   await api(qurl,{action:"OPEN",question_id:q.id,viewer_id:crypto.randomUUID()},token);
   await api(`/matches/${r.match.id}/questions/${q.id}/answer/`,{answer:'A'},token);
   await api(`/matches/${r.match.id}/rewards/claim/`,{team_question_id:q.id,reward_type:'UNLOCK',unit_type_id:code,idempotency_key:crypto.randomUUID()},token);
   const next=await api(qurl,{action:'NEXT',question_id:q.id},token);q=next;await api(qurl,{action:'OPEN',question_id:q.id,viewer_id:crypto.randomUUID()},token);
 }
 await page.reload();await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).waitFor(); // fixture replaced history; use ordinary BattlePage after refresh
 // Reenter instrumentation after a true reload.
 await page.evaluate(room=>localStorage.setItem('continuous-room',JSON.stringify(room)),{match:r.match,join:r.joins[0]});await page.goto(base+'/tests/fixtures/continuous.html');await page.waitForFunction(()=>window.flowScene?.visuals&&window.flowStore?.getState().connectionStatus==='connected');await page.bringToFront();
 q=await api(qurl,undefined,token);await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();await dialog.getByRole('button',{name:'Đóng câu hỏi',exact:true}).first().click();
 console.log('Waiting for the real 60-second hidden deadline');
 const timeoutAt=Date.now()+70000;
 let expired=await api(qurl,undefined,token);
 while(expired.status!=='EXPIRED' && Date.now()<timeoutAt){await wait(1000);expired=await api(qurl,undefined,token);}
 assert.equal(expired.status,'EXPIRED');
 console.log('Hidden expiry client state',await page.evaluate(()=>({team:window.flowStore?.getState().currentTeamId,question:window.flowStore?.getState().currentQuestion?.status,questionId:window.flowStore?.getState().currentQuestion?.id,connection:window.flowSocketClient?.getStatus(),seq:window.flowStore?.getState().lastSequenceNumber,label:document.querySelector('.quest-card')?.getAttribute('aria-label')})));
 await page.screenshot({path:new URL('../../docs/qa/team-upgrade-hidden-state.png',import.meta.url).pathname});assert.equal(expired.id,q.id);assert.equal(expired.reward_options,null);
 await page.bringToFront();await page.locator('.quest-card').click();await dialog.getByText('ĐÃ HẾT THỜI GIAN TRẢ LỜI',{exact:true}).waitFor();assert.equal((await api(qurl,undefined,token)).id,q.id);
 await page.screenshot({path:new URL('../../docs/qa/team-upgrade-quiz-expired.png',import.meta.url).pathname});
 await dialog.getByRole('button',{name:'Câu hỏi tiếp theo',exact:true}).click();await dialog.getByText(new RegExp('THỬ THÁCH CHIẾN LƯỢC #'+(q.sequence_number+1))).waitFor();assert.equal((await api(qurl,undefined,token)).sequence_number,q.sequence_number+1);await dialog.getByRole('button',{name:'Đóng câu hỏi',exact:true}).first().click();await dialog.waitFor({state:'hidden'});
 report.quiz={hiddenCountdown:true,sharedDeadline:true,draftPreserved:true,hiddenExpirySameQuestion:true,reopenShowsExpired:true,explicitNext:true,reward30ExactlyOnce:true};
 const deploy=(code,quantity)=>api(`/matches/${r.match.id}/actions/deploy/`,{unit_type_code_or_id:code,target_team_id:r.teams[1].id,quantity,idempotency_key:crypto.randomUUID()},token);
 const first=await deploy('infantry',10);await deploy('tank',1);await deploy('artillery',1);
 for(const [index,code] of ['mg_tower','cannon_tower','shield_generator'].entries())await api(`/matches/${r.match.id}/actions/build/`,{unit_type_code_or_id:code,node_id:(await state()).valid_tower_slots[index],idempotency_key:crypto.randomUUID()},token);
 await api(`/matches/${r.match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:r.teams[0].id,quantity:1,idempotency_key:crypto.randomUUID()},r.joins[1].participant_token);
 await api(`/matches/${r.match.id}/advance-phase/`,{},r.match.host_token,true);
 await page.waitForFunction(id=>window.flowScene.visuals.has(id),first.entities[0].id);
 await page.evaluate(id=>{window.upgradeRoot=window.flowScene.visuals.get(id).root},first.entities[0].id);
 await page.getByRole('button',{name:'NÂNG CẤP',exact:true}).click();const panel=page.getByRole('dialog',{name:'Nâng cấp toàn đội'});await panel.getByRole('heading',{name:/Bộ binh/}).waitFor();
 await panel.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).click();await panel.getByRole('button',{name:'Xác nhận · 50 xu',exact:true}).click();await panel.getByRole('heading',{name:/Cấp 2 trên 3/}).waitFor();
 await page.screenshot({path:new URL('../../docs/qa/team-upgrade-panel.png',import.meta.url).pathname});
 await panel.getByRole('button',{name:'Đóng nâng cấp'}).click();
 for(const p of [page,mate,opponent])await p.waitForFunction(id=>window.flowScene.visuals.get(id)?.data.level===2,first.entities[0].id);
 assert.equal(await page.evaluate(id=>window.flowScene.visuals.get(id).root===window.upgradeRoot,first.entities[0].id),true);
 assert.equal(await page.evaluate(id=>window.flowScene.visuals.get(id).sprite.texture.key.includes('-lv2'),first.entities[0].id),true);
 let current=await state();assert.equal(current.entities.filter(e=>e.unit_type_code==='infantry'&&e.level===2).length,10);
 assert.equal((await deploy('infantry',5)).entities.every(e=>e.level===2),true);
 for(const code of ['infantry','tank','artillery','mg_tower','cannon_tower','shield_generator']) {
   for(let level=code==='infantry'?2:1;level<3;level++) {const key=crypto.randomUUID(), data={entity_type:code,expected_current_level:level,idempotency_key:key};const result=await api(`/matches/${r.match.id}/upgrades/`,data,token);await api(`/matches/${r.match.id}/upgrades/`,data,token);assert.equal(result.level,level+1);}
   await api(`/matches/${r.match.id}/upgrades/`,{entity_type:code,expected_current_level:3,idempotency_key:crypto.randomUUID()},token,false,400);
 }
 for(const p of [page,mate,opponent])await p.waitForFunction(id=>window.flowScene.visuals.get(id)?.data.level===3,first.entities[0].id);
 await page.evaluate(room=>localStorage.setItem('continuous-room',JSON.stringify(room)),{match:r.match,join:r.joins[0]});await page.goto(base+'/tests/fixtures/continuous.html');await page.waitForFunction(id=>window.flowScene?.visuals.get(id)?.data.level===3,first.entities[0].id);
 await page.getByRole('button',{name:'NÂNG CẤP',exact:true}).click();await panel.getByText('CẤP TỐI ĐA',{exact:true}).waitFor();await page.screenshot({path:new URL('../../docs/qa/team-upgrade-max.png',import.meta.url).pathname});await panel.getByRole('button',{name:'Đóng nâng cấp'}).click();
 report.upgrades={allSixTypesLevel3:true,allExistingAndFuture:true,threeClientsSynchronized:true,stableRoot:true,levelEquipment:true,maxLevelRejected:true,reconnectRecovered:true};
 const positions=p=>p.evaluate(()=>window.flowScene.children.list.filter(o=>o.name==='natural-vegetation').map(o=>o.getData('vegetation')));
 assert.deepEqual(await positions(page),await positions(mate));
 for(const count of [2,4,8,20]) {
   const rr=count===2?r:await makeRoom(count);const p=count===2?page:await openPage(rr,rr.joins[0]);
   const metrics=await p.evaluate(()=>({trees:window.flowScene.children.list.filter(o=>o.name==='natural-vegetation').length,slots:window.flowStore.getState().mapData.nodes.filter(n=>n.node_type==='tower_slot').length,frames:window.frameSamples.slice(-3)}));
   assert.ok(metrics.trees>10);assert.equal(metrics.slots,count*6);
   const beforeZoom=await p.evaluate(()=>window.flowScene.cameras.main.zoom);await p.getByRole('button',{name:'Phóng to',exact:true}).first().click();await wait(500);assert.ok(await p.evaluate(value=>window.flowScene.cameras.main.zoom>value,beforeZoom));
   await p.screenshot({path:new URL(`../../docs/qa/team-upgrade-map-${count}.png`,import.meta.url).pathname});
   report.vegetation.push({count,...metrics});if(count!==2)await p.close();
 }
 assert.deepEqual(report.errors,[]);report.status='PASS';console.log(JSON.stringify(report));
} catch(e){report.status='FAIL';report.failure=e.stack;if(debugPage){report.client=await debugPage.evaluate(()=>({team:window.flowStore?.getState().currentTeamId,question:window.flowStore?.getState().currentQuestion,body:document.body.innerText})).catch(()=>null);await debugPage.screenshot({path:new URL('../../docs/qa/team-upgrade-failure.png',import.meta.url).pathname}).catch(()=>{});}throw e;}
finally{await fs.writeFile(new URL('../../docs/qa/team-upgrades-browser.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();}
