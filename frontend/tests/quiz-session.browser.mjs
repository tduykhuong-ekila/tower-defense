import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {openCoinBag} from './helpers/coin-bag.mjs';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
const context=await browser.newContext({viewport:{width:1440,height:1000},hasTouch:true});
const page=await context.newPage(), teammate=await context.newPage();
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5181';
const evidence={};
async function api(path,data,token,host=false){const r=await page.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),await r.text());return r.json();}
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
try {
 await page.goto(base);
 const match=await api('/matches/',{name:'Quiz viewing browser regression',configuration:{initial_coins:1000}});
 const teams=[],joins=[];
 for(let i=0;i<2;i++) {teams.push(await api(`/matches/${match.id}/teams/`,{name:`Quiz ${i}`},match.host_token,true));joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Quiz player ${i}`,team_id:teams[i].id,role:'MENTEE'}));}
 const third=await api(`/matches/${match.id}/join/`,{display_name:'Quiz teammate',team_id:teams[0].id,role:'MENTEE'});
 for(const t of teams)await api(`/matches/${match.id}/teams/${t.id}/ready/`,{is_ready:true},match.host_token,true);
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 const room={match,a:joins[0],b:joins[1],c:third};
 await page.evaluate(room=>localStorage.setItem('full-gameplay-test-room',JSON.stringify(room)),room);
 await page.goto(base+'/tests/fixtures/full-gameplay.html?view=a');
 await teammate.goto(base+'/tests/fixtures/full-gameplay.html?view=c');
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).waitFor();
 await page.waitForFunction(()=>window.flowScene?.visuals);
 const token=joins[0].participant_token,other=joins[1].participant_token;
 const current=()=>api(`/matches/${match.id}/questions/current/`,undefined,token);
 let q=await current(); assert.equal(q.timer.status,'NOT_STARTED');
 await wait(1500);assert.equal((await current()).timer.remaining_ms,q.timer.remaining_ms);
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Câu hỏi tri thức'});
 const input=dialog.getByPlaceholder('Nhập câu trả lời hoặc kết quả giải mã...');
 const text=await dialog.innerText(); const correct=text.includes('2 + 2')?'4':'6';
 await input.fill(correct);
 await teammate.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[0].id,quantity:3,idempotency_key:crypto.randomUUID()},other);
 const enemyState=await api(`/matches/${match.id}/teams/${teams[1].id}/state/`,undefined,other);
 await api(`/matches/${match.id}/actions/build/`,{unit_type_code_or_id:'mg_tower',node_id:enemyState.valid_tower_slots[0],idempotency_key:crypto.randomUUID()},other);
 await wait(1600);
 assert.ok(await dialog.isVisible());assert.equal(await input.inputValue(),correct);assert.equal((await current()).id,q.id);
 await teammate.getByRole('dialog',{name:'Câu hỏi tri thức'}).getByRole('button',{name:'Đóng câu hỏi',exact:true}).first().click();
 assert.equal((await current()).timer.status,'RUNNING');
 await dialog.getByRole('button',{name:'Đóng câu hỏi',exact:true}).first().click();
 await dialog.waitFor({state:'hidden'});
 const paused=await current();assert.equal(paused.timer.status,'RUNNING');assert.ok(paused.timer.remaining_ms<q.timer.remaining_ms);
 await wait(2500);assert.ok((await current()).timer.remaining_ms<paused.timer.remaining_ms-2000);assert.equal((await current()).id,q.id);
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();
 assert.equal(await input.inputValue(),correct);
 const resumed=await current();assert.ok(resumed.timer.remaining_ms<=paused.timer.remaining_ms && resumed.timer.remaining_ms>paused.timer.remaining_ms-5000);
 await input.press('Escape');await dialog.waitFor({state:'hidden'});
 const reconnectBudget=(await current()).timer.remaining_ms;
 await page.goto(base+'/tests/fixtures/full-gameplay.html?view=a');await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).waitFor();
 assert.equal((await current()).id,q.id);assert.ok((await current()).timer.remaining_ms<reconnectBudget);
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();await input.fill(correct);
 await dialog.getByRole('button',{name:'Xác Nhận Nộp Bài'}).click();
 await page.getByRole('button',{name:'Mở túi coin · 20–60',exact:true}).waitFor();
 const before=(await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,token)).team.coins;
 const receipt=await openCoinBag(page);
 await page.locator('.reward-overlay').waitFor({state:'hidden'});
 await wait(700);
 const after=(await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,token)).team.coins;
 assert.equal(after,before+receipt.coin_amount);
 await api(`/matches/${match.id}/rewards/claim/`,{team_question_id:q.id,reward_type:'COIN',idempotency_key:crypto.randomUUID()},token);
 assert.equal((await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,token)).team.coins,after);
 assert.equal((await current()).id,q.id);assert.equal((await current()).status,'REWARD_CLAIMED');
 await teammate.waitForFunction(value=>document.querySelector('.kingdom-resources .gold')?.textContent.includes(String(value)),after);
 evidence.quiz={stableDuringCombat:true,sharedTimer:true,pausedMs:paused.timer.remaining_ms,reconnectBudget,coinsBefore:before,coinsAfter:after,duplicateClaimSafe:true};
 await page.getByRole('button',{name:'Xem kết quả câu hỏi',exact:true}).click();
 await dialog.getByRole('button',{name:'Câu hỏi tiếp theo',exact:true}).click();
 const text2=await dialog.innerText();await input.fill(text2.includes('2 + 2')?'4':'6');await dialog.getByRole('button',{name:'Xác Nhận Nộp Bài'}).click();
 await page.getByRole('button',{name:/Chọn Đơn Vị Mở Khóa/}).click();
 const tank=page.locator('.unlock-card').filter({hasText:'Xe tăng'});await tank.click();
 const q2=await current();
 // Opponent's own reward claim must never close this team's unlock dialog.
 const oq=await api(`/matches/${match.id}/questions/current/`,undefined,other);
 await api(`/matches/${match.id}/questions/current/`,{action:'OPEN',question_id:oq.id,viewer_id:crypto.randomUUID()},other);
 await api(`/matches/${match.id}/questions/${oq.id}/answer/`,{answer:oq.question.content.includes('2 + 2')?'4':'6'},other);
 await api(`/matches/${match.id}/rewards/claim/`,{team_question_id:oq.id,reward_type:'COIN'},other);
 await wait(800);assert.ok(await tank.isVisible());assert.equal(await tank.getAttribute('aria-pressed'),'true');
 await page.getByRole('button',{name:'Đóng phần thưởng',exact:true}).click();
 await page.getByRole('button',{name:'Nhận phần thưởng',exact:true}).click();
 assert.equal(await tank.getAttribute('aria-pressed'),'true');
 await page.waitForFunction(()=>Array.from(document.querySelectorAll(".unlock-card img")).every(i=>i.complete&&i.naturalWidth>0));
 await wait(250);
 await page.screenshot({path:new URL('../../docs/qa/quiz-unlock-stability.png',import.meta.url).pathname});
 await page.getByRole('button',{name:'Xác Nhận Mở Khóa Đơn Vị',exact:true}).click();
 await page.locator('.reward-overlay').waitFor({state:'hidden'});
 assert.equal((await current()).id,q2.id);
 evidence.unlock={selectedTankPreserved:true,opponentClaimDidNotClose:true,closeReopenPreserved:true};
 // Request each additional question explicitly and exercise the alternative reward.
 for (const name of ['Pháo binh','Tháp đại bác']) {
   await page.getByRole('button',{name:'Xem kết quả câu hỏi',exact:true}).click();
 await dialog.getByRole('button',{name:'Câu hỏi tiếp theo',exact:true}).click();
   const text=await dialog.innerText();await input.fill(text.includes('2 + 2')?'4':'6');
   await dialog.getByRole('button',{name:'Xác Nhận Nộp Bài'}).click();
   await page.getByRole('button',{name:/Chọn Đơn Vị Mở Khóa/}).click();
   await page.locator('.unlock-card').filter({hasText:name}).click();
   await page.getByRole('button',{name:'Xác Nhận Mở Khóa Đơn Vị',exact:true}).click();
   await page.locator('.reward-overlay').waitFor({state:'hidden'});
 }
 const additional=[];
 for (const code of ['tank','artillery']) {
   const deployed=await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:code,target_team_id:teams[1].id,quantity:1,idempotency_key:crypto.randomUUID()},token);
   additional.push(deployed.entity);
 }
 const ownState=await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,token);
 additional.push((await api(`/matches/${match.id}/actions/build/`,{unit_type_code_or_id:'cannon_tower',node_id:ownState.valid_tower_slots[0],idempotency_key:crypto.randomUUID()},token)).entity);
 // Real Phaser hit tests on desktop and touch, with one React information card.
 const mine=await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[1].id,quantity:1,idempotency_key:crypto.randomUUID()},token);
 const entityId=mine.entity.id;
 await page.waitForFunction(id=>window.flowScene.visuals.has(id),entityId);
 await page.evaluate(id=>{const s=window.flowScene,v=s.visuals.get(id);s.navigate(v.root.x,v.root.y,1.4);},entityId);
 await wait(800);
 async function point(){return page.evaluate(id=>{const s=window.flowScene,v=s.visuals.get(id),c=s.cameras.main,r=s.game.canvas.getBoundingClientRect();return {x:r.left+c.x+c.width/2+(v.root.x-c.scrollX-c.width/2)*c.zoom,y:r.top+c.y+c.height/2+(v.root.y-24-c.scrollY-c.height/2)*c.zoom};},entityId);}
 let spot=await point();await page.mouse.move(spot.x,spot.y);
 const tooltip=page.getByRole('tooltip',{name:'Thông tin Bộ binh'});await tooltip.waitFor();
 assert.ok(await tooltip.locator('img').count());assert.match(await tooltip.innerText(),/80 \/ 80/);assert.match(await tooltip.innerText(),/Tốc độ di chuyển\s+7/);
 await tooltip.locator(".entity-illustration[data-state=ready]").waitFor();await wait(250);
 const bounds=await tooltip.boundingBox();assert.ok(bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=1440&&bounds.y+bounds.height<=1000);
 await page.screenshot({path:new URL('../../docs/qa/quiz-entity-card-desktop.png',import.meta.url).pathname});
 await page.mouse.move(1,900);await tooltip.waitFor({state:'hidden'});
 spot=await point();await page.touchscreen.tap(spot.x,spot.y);
 const touch=page.getByRole('dialog',{name:'Thông tin Bộ binh'});await touch.waitFor();await touch.getByRole('button',{name:'Đóng thẻ thông tin'}).click();await touch.waitFor({state:'hidden'});
 evidence.tooltip={desktop:true,touch:true,illustrated:true,insideViewport:true};
 const inspectedStats=[];
 for (const ent of additional) {
   await page.waitForFunction(id=>window.flowScene.visuals.has(id),ent.id);
   await page.evaluate(id=>{const s=window.flowScene,v=s.visuals.get(id);s.navigate(v.root.x,v.root.y,1.4);},ent.id);await wait(600);
   const p=await page.evaluate(id=>{const s=window.flowScene,v=s.visuals.get(id),c=s.cameras.main;return{x:c.x+c.width/2+(v.root.x-c.scrollX-c.width/2)*c.zoom,y:c.y+c.height/2+(v.root.y-24-c.scrollY-c.height/2)*c.zoom};},ent.id);
   await page.mouse.move(p.x,p.y);
   const card=page.getByRole('tooltip');await card.waitFor();
   assert.match(await card.innerText(),new RegExp(String(ent.max_hp)));
   const actual=await card.locator('dl').innerText();
   assert.ok(actual.includes(String(ent.range)));
   if(ent.movement_speed)assert.ok(actual.includes(String(ent.movement_speed)));
   inspectedStats.push({code:ent.unit_type_code,range:ent.range,hp:ent.max_hp,speed:ent.movement_speed});
   await page.mouse.move(1,900);await card.waitFor({state:'hidden'});
 }
 evidence.tooltip.authoritativeStats=inspectedStats;
 // Compare the actual rendered header with the original desktop declarations.
 const afterBox=await page.locator('.round-standard').boundingBox();
 const oldStyle=await page.addStyleTag({content:'.woodland-game .round-standard{width:212px;max-width:none;top:-25px;padding:29px 12px 24px}.woodland-game .round-standard h1{display:block;font-size:29px;line-height:1.3;margin:6px 0 2px}.woodland-game .round-stitches{display:block;height:1px;margin:10px auto 0}'});
 const beforeBox=await page.locator('.round-standard').boundingBox();await oldStyle.evaluate(e=>e.remove());
 assert.ok(afterBox.height<beforeBox.height);
 await page.setViewportSize({width:390,height:844});await wait(700);
 const mobile=await page.locator('.round-standard').boundingBox();assert.ok(mobile.x>=0&&mobile.x+mobile.width<=390);
 const kingdom=await page.locator('.kingdom-panel').boundingBox(),tools=await page.locator('.top-tools').boundingBox();
 assert.ok(mobile.x>=kingdom.x+kingdom.width && mobile.x+mobile.width<=tools.x);
 await page.screenshot({path:new URL('../../docs/qa/quiz-compact-mobile.png',import.meta.url).pathname});
 evidence.header={desktopBefore:beforeBox,desktopAfter:afterBox,mobile};
 for (const width of [320,768]) {
   await page.setViewportSize({width,height:844});await wait(250);
   const header=await page.locator('.round-standard').boundingBox(),left=await page.locator('.kingdom-panel').boundingBox(),right=await page.locator('.top-tools').boundingBox();
   assert.ok(header.x>=left.x+left.width && header.x+header.width<=right.x);
 }
 // Match completion is an explicit message in the still-open question dialog.
 const oq2=await api(`/matches/${match.id}/questions/current/`,{action:'NEXT',question_id:oq.id,viewer_id:crypto.randomUUID()},other);
 await page.setViewportSize({width:1280,height:900});
 await page.goto(base+'/tests/fixtures/full-gameplay.html?view=b');
 await page.getByRole('button',{name:'Mở câu hỏi tri thức',exact:true}).click();
 await page.getByRole('dialog',{name:'Câu hỏi tri thức'}).waitFor();
 await api(`/matches/${match.id}/end/`,{},match.host_token,true);
 const terminal=page.getByRole('dialog',{name:'Câu hỏi tri thức'});
 await terminal.getByText(/Trận đấu đã kết thúc/).waitFor();
 assert.ok(await terminal.isVisible());assert.equal(await terminal.getByRole('button',{name:'Xác Nhận Nộp Bài'}).count(),0);
 await terminal.getByRole('button',{name:'Đóng câu hỏi',exact:true}).first().click();await terminal.waitFor({state:'hidden'});
 evidence.matchCompletion={explicitMessage:true,submissionUnavailable:true};
 console.log(JSON.stringify(evidence,null,2));
 await fs.writeFile(new URL('../../docs/qa/quiz-session-browser.json',import.meta.url),JSON.stringify(evidence,null,2));
} catch(e){await page.screenshot({path:new URL('../../docs/qa/quiz-session-failure.png',import.meta.url).pathname});throw e;}
finally {await browser.close();}
