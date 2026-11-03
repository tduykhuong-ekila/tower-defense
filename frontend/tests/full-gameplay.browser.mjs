// Real API + real React/Phaser scene, against tests/browser_preview.py's disposable DB.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5176';
const proofDir=new URL('../../docs/qa/',import.meta.url);
const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const a=await context.newPage(),b=await context.newPage();
const errors=[],checks=[];
for(const page of [a,b]){page.setDefaultTimeout(12000);page.on('pageerror',e=>errors.push(e.message));}
async function api(path,data,token,host=false){const r=await context.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),`${path}: ${r.status()} ${await r.text()}`);return r.json();}
async function state(page){return page.evaluate(async()=>{
 const id=sessionStorage.getItem('tower_active_match_id'),token=sessionStorage.getItem('tower_participant_token'),member=JSON.parse(sessionStorage.getItem('tower_active_member'));
 const match=await fetch(`/api/v1/matches/${id}/`).then(r=>r.json());
 const team=await fetch(`/api/v1/matches/${id}/teams/${member.team_id}/state/`,{headers:{'X-Participant-Token':token}}).then(r=>r.json());
 return {round:Number(document.querySelector('.round-standard h1')?.textContent.match(/\d+/)?.[0]||match.configuration.current_round),match,coins:team.team.coins,entities:team.entities,team:member.team_id,unlocked:team.unlocked_units.filter(u=>u.is_unlocked).map(u=>u.code)};
});}
async function waitRound(page,round){await page.waitForFunction(n=>Number(document.querySelector('.round-standard h1')?.textContent.match(/\d+/)?.[0]||0)>=n,round,{timeout:50000});}
async function load(page,role){await page.goto(`${base}/tests/fixtures/full-gameplay.html?view=${role}`);await page.waitForFunction(()=>window.flowScene?.callbacks);await page.locator('.connection-dot.connected').waitFor();await page.locator('.arsenal-card').first().waitFor();}
async function clickNode(page,nodeId){await page.waitForTimeout(550);const p=await page.evaluate(id=>{const s=flowScene,n=s.nodes.get(id),c=s.cameras.main;return {x:c.x+c.width/2+(n.worldX-c.scrollX-c.width/2)*c.zoom,y:c.y+c.height/2+(n.worldY-c.scrollY-c.height/2)*c.zoom};},nodeId);await page.mouse.click(p.x,p.y);}
async function deploy(page,canvas=false){await page.getByRole('button',{name:'QUÂN ĐỘI',exact:true}).click();const card=page.locator('.arsenal-card').filter({hasText:'Bộ binh'});assert.equal(await card.isDisabled(),false);await card.click();const response=page.waitForResponse(r=>r.url().endsWith('/actions/deploy/')&&r.request().method()==='POST');if(canvas)await clickNode(page,'node_spawn_t1');else await page.getByRole('button',{name:'Xuất quân',exact:true}).click();const result=await response;assert.ok(result.ok(),await result.text());return result.json();}
async function build(page,slot,canvas=false){await page.getByRole('button',{name:'CÔNG SỰ',exact:true}).click();const card=page.locator('.arsenal-card').filter({hasText:'Tháp súng máy'});assert.equal(await card.isDisabled(),false);await card.click();const response=page.waitForResponse(r=>r.url().endsWith('/actions/build/')&&r.request().method()==='POST');if(canvas)await clickNode(page,`node_tower_t2_slot${slot}`);else await page.getByRole('button',{name:`Vị trí ${slot}`,exact:true}).click();const result=await response;assert.ok(result.ok(),await result.text());return result.json();}
async function answer(page){await page.getByRole('button',{name:/^(Mở câu hỏi tri thức|Câu hỏi tiếp theo)$/}).click();const dialog=page.getByRole('dialog',{name:'Câu hỏi tri thức'});const text=await dialog.innerText();await dialog.getByPlaceholder('Nhập câu trả lời hoặc kết quả giải mã...').fill(text.includes('2 + 2')?'4':'6');await dialog.getByRole('button',{name:'Xác Nhận Nộp Bài'}).click();await page.getByRole('button',{name:/Nhận \+30 xu/}).waitFor();}
try{
 await a.goto(base);
 const match=await api('/matches/',{name:'Full gameplay E2E',configuration:{max_teams:2,initial_coins:1000,initial_base_hp:100,round_duration_seconds:30,phase_durations:{PREPARATION:10,BUILD_AND_SCOUT:240,WAR:100,FINAL_ASSAULT:100,RESULTS:10}}});
 const teams=[],joins=[];
 for(let i=0;i<2;i++){const t=await api(`/matches/${match.id}/teams/`,{name:i?'Blue Defense':'Amber Attack'},match.host_token,true);teams.push(t);joins.push(await api(`/matches/${match.id}/join/`,{display_name:i?'Bob':'Alice',team_id:t.id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${t.id}/ready/`,{is_ready:true},match.host_token,true);}
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 await a.evaluate(room=>localStorage.setItem('full-gameplay-test-room',JSON.stringify(room)),{match,a:joins[0],b:joins[1]});
 await Promise.all([load(a,'a'),load(b,'b')]);
 await answer(a);const coinsBefore=(await state(a)).coins;const coinReply=a.waitForResponse(r=>r.url().endsWith('/rewards/claim/')&&r.request().method()==='POST');await a.getByRole('button',{name:/Nhận \+30 xu/}).click();assert.equal((await (await coinReply).json()).team_coins,coinsBefore+30);
 checks.push('correct answer grants exactly 30 coins');
 await a.getByRole('button',{name:/^(Mở câu hỏi tri thức|Câu hỏi tiếp theo)$/}).waitFor();await answer(a);
 await a.getByRole('button',{name:/Chọn Đơn Vị Mở Khóa/}).click();await a.getByText('Xe Tăng Thiết Giáp',{exact:true}).click();const unlockCoins=(await state(a)).coins;
 const unlockReply=a.waitForResponse(r=>r.url().endsWith('/rewards/claim/')&&r.request().method()==='POST');await a.getByRole('button',{name:'Xác Nhận Mở Khóa Đơn Vị'}).click();assert.equal((await (await unlockReply).json()).team_coins,unlockCoins);await a.getByRole('dialog').waitFor({state:'hidden'});assert.ok((await state(a)).unlocked.includes('tank'));
 checks.push('free tank unlock persists');
 await deploy(a);await build(b,1);checks.push('round 1 real UI deployment and construction');
 await waitRound(a,2);await waitRound(b,2);assert.equal((await state(a)).match.configuration.timer_state.round_phase,'PLANNING');
 // These clicks happen while the previous replay can still be running; no Skip button is used.
 await deploy(a);await build(b,2);checks.push('automatic round 2 restores both purchases without host WebSocket or refresh');
 async function resolve(){const m=await api(`/matches/${match.id}/`);const n=m.configuration.current_round;await api(`/matches/${match.id}/combat/resolve/`,{expected_round:n},match.host_token,true);await waitRound(a,n+1);await waitRound(b,n+1);return n+1;}
 await resolve();await deploy(a,true);checks.push('round 3 actual Phaser spawn click sends purchase and renders confirmation');
 await a.reload();await a.getByRole('button',{name:/Bộ binh/}).waitFor();assert.equal((await state(a)).round,3);assert.ok((await state(a)).unlocked.includes('tank'));checks.push('refresh during planning restores state and eligibility');
 // Pause only the Phaser clock, reproducing a throttled renderer; gameplay remains server-owned.
 await b.evaluate(()=>{flowScene.time.paused=true;});await resolve();
 await b.waitForFunction(()=>!flowScene.playing,{timeout:10000});await b.evaluate(()=>{flowScene.time.paused=false;});checks.push('wall-clock watchdog clears a stalled Phaser replay');
 await deploy(a);await resolve();await deploy(a);await build(b,3,true);checks.push('round 5 deploy and canvas construction with persistent capacity');
 await b.getByRole('button',{name:'Phóng to',exact:true}).click();await b.waitForTimeout(350);
 await b.screenshot({path:new URL('full-gameplay-round5.png',proofDir).pathname});
 await resolve();
 const stable=await api(`/matches/${match.id}/teams/${teams[1].id}/state/`,undefined,joins[1].participant_token);
 assert.equal(stable.limits.towers.current,3);assert.equal(stable.team.coins,1000-75+50);
 // Refresh while combat replay is active. Only current authoritative state is restored.
 await b.reload();await b.getByRole('button',{name:/Tháp súng máy|Bộ binh/}).first().waitFor();assert.ok((await state(b)).round>=6);checks.push('refresh during playback restores current planning state');
 // Finish using legal tank waves, preserving the catalog and all capacity checks.
 let ended=false;
 for(let attempt=0;attempt<45;attempt++){
  const current=await api(`/matches/${match.id}/`);if(current.status==='FINISHED'){ended=true;break;}
  const teamState=await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,joins[0].participant_token);
  const roomLeft=teamState.limits.active_units.max-teamState.limits.active_units.current;
  for(let i=0;i<roomLeft&&(i+1)*35<=teamState.team.coins;i++)await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'tank',target_team_id:teams[1].id,idempotency_key:crypto.randomUUID()},joins[0].participant_token);
  await api(`/matches/${match.id}/combat/resolve/`,{expected_round:current.configuration.current_round},match.host_token,true);
 }
 assert.ok(ended,'combat did not finish');
 await a.getByRole('link',{name:'Xem kết quả và bảng xếp hạng →'}).waitFor();
 const outcome=await api(`/matches/${match.id}/results/`);assert.equal(outcome.winner_team_id,teams[0].id);assert.equal(outcome.results.length,2);assert.equal(outcome.results.find(r=>r.team_id===teams[1].id).remaining_base_hp,0);
 await a.getByRole('link',{name:'Xem kết quả và bảng xếp hạng →'}).click();await a.getByRole('heading',{name:'AMBER ATTACK',exact:true}).waitFor();
 await a.screenshot({path:new URL('full-gameplay-results.png',proofDir).pathname});
 checks.push('legal later-round tank waves cause elimination, victory and persisted results');assert.deepEqual(errors,[]);
 const proof={status:'PASS',checks,winner:outcome.winner_team_name,results:outcome.results.map(r=>({name:r.team_name,rank:r.final_rank,hp:r.remaining_base_hp,score:r.final_score}))};
 await fs.writeFile(new URL('full-gameplay-browser.json',proofDir),JSON.stringify(proof,null,2));console.log(JSON.stringify(proof,null,2));
}catch(error){await a.screenshot({path:new URL('full-gameplay-failure.png',proofDir).pathname});throw error;}finally{await browser.close();}
