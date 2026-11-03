// Real React/Phaser clients against tests/browser_preview.py (disposable database).
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {openCoinBag} from './helpers/coin-bag.mjs';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5177';
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const request=await browser.newContext(),report={checks:[],errors:[],worlds:[]};
const out=new URL('../../docs/qa/',import.meta.url).pathname;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,data,token,host=false,expected=200){
 const response=await request.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{},timeout:120000});
 assert.ok(expected===200?response.ok():response.status()===expected,`${path}: ${response.status()} ${await response.text()}`);return response.json();
}
async function room(count){
 const match=await api('/matches/',{name:`Battlefield UI QA ${count}`,configuration:{max_teams:count,initial_coins:300,first_preparation_duration_seconds:600,preparation_duration_seconds:600,battle_duration_seconds:600}}),teams=[],joins=[];
 for(let i=0;i<count;i++){
  const team=await api(`/matches/${match.id}/teams/`,{name:`QA Team ${i+1}`},match.host_token,true);teams.push(team);
  joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:team.id,role:'MENTEE'}));
  await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);
 }
 const teammate=await api(`/matches/${match.id}/join/`,{display_name:'Teammate',team_id:teams[0].id,role:'MENTEE'});
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);return {match,teams,joins,teammate};
}
async function client(r,join,viewport={width:1440,height:1000}){
 const context=await browser.newContext({viewport}),page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match:r.match,join});
 await page.goto(base+'/tests/fixtures/continuous.html');await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');return page;
}
async function pending(r,join){
 let q=await api(`/matches/${r.match.id}/questions/current/`,undefined,join.participant_token);
 if(['REWARD_CLAIMED','ANSWER_INCORRECT','EXPIRED'].includes(q.status)) q=await api(`/matches/${r.match.id}/questions/current/`,{action:'NEXT',question_id:q.id},join.participant_token);
 await api(`/matches/${r.match.id}/questions/current/`,{action:'OPEN',question_id:q.id,viewer_id:crypto.randomUUID()},join.participant_token);
 await api(`/matches/${r.match.id}/questions/${q.id}/answer/`,{answer:q.question.content.includes('3 + 3')?'6':'4'},join.participant_token);return q;
}
async function cameraCheck(page,count){
 const result=await page.evaluate(async()=>{
  const {battlefieldWorld,projectMap}=await import('/src/game/map.ts');
  const scene=flowScene,map=scene.state.mapData,world=battlefieldWorld(map),trees=scene.children.list.filter(o=>o.texture?.key?.startsWith('tree-'));
  if(trees.some(t=>t.x<110||t.x>scene.world.width-110||t.y<100||t.y>scene.world.height-90))throw Error('Perimeter tree survived');
  if(!trees.length)throw Error('Interior trees were removed');
  return {world,arena:map.arena,projected:projectMap(map).size,treeCount:trees.length,objects:scene.children.length};
 });
 for(const [u,v] of [[0,0],[1,0],[1,1],[0,1]])await page.evaluate(({world,u,v})=>{
  const s=flowScene,c=s.cameras.main;s.zoomController.moveTo(world.x+u*world.width,world.y+v*world.height,1,true);c.preRender();const g=s.terrain.backdrop,vw=c.worldView;
  if(vw.x<world.x-.01||vw.y<world.y-.01||vw.right>world.x+world.width+.01||vw.bottom>world.y+world.height+.01)throw Error('Camera escaped visual bounds');
  if(g.x>vw.x+.01||g.y>vw.y+.01||g.x+g.width<vw.right-.01||g.y+g.height<vw.bottom-.01)throw Error('Unrendered camera space');
 },{world:result.world,u,v});
 await page.evaluate(()=>flowScene.fit(true));await wait(150);await page.screenshot({path:out+`battlefield-open-${count}.png`});
 const minimap=page.locator('.arena-navigation svg'),box=await minimap.boundingBox();
 await page.evaluate(()=>{window.navigations=[];const original=flowScene.navigate.bind(flowScene);flowScene.navigate=(x,y,z)=>{window.navigations.push({x,y});return original(x,y,z);};});
 await minimap.click({position:{x:box.width*.05,y:box.height*.05}});
 const point=await page.evaluate(()=>window.navigations.at(-1));
 assert.ok(Math.abs(point.x-(result.world.x+result.world.width*.05))<20);assert.ok(Math.abs(point.y-(result.world.y+result.world.height*.05))<20);
 await page.evaluate(()=>flowScene.zoomController.moveTo(flowScene.world.centerX,flowScene.world.centerY,1,true));
 const before=await page.evaluate(()=>{const c=flowScene.cameras.main;c.preRender();return c.getWorldPoint(500,300);});
 await page.mouse.move(500,300);await page.mouse.wheel(0,-150);await wait(400);
 const after=await page.evaluate(()=>{const c=flowScene.cameras.main;c.preRender();return c.getWorldPoint(500,300);});assert.ok(Math.hypot(after.x-before.x,after.y-before.y)<2);
 const start=await page.evaluate(()=>flowScene.cameras.main.scrollX);
 await page.mouse.move(500,300);await page.mouse.down();await page.mouse.move(600,330,{steps:10});await page.mouse.up();assert.ok(Math.abs(await page.evaluate(()=>flowScene.cameras.main.scrollX)-start)>20);
 await page.setViewportSize({width:390,height:844});await wait(300);
 await page.evaluate(()=>{flowScene.fit(true);flowScene.cameras.main.preRender();const s=flowScene,c=s.cameras.main,g=s.terrain.backdrop,v=c.worldView;if(g.x>v.x+.01||g.y>v.y+.01||g.x+g.width<v.right-.01||g.y+g.height<v.bottom-.01)throw Error('Resize ground gap '+JSON.stringify({g:{x:g.x,y:g.y,w:g.width,h:g.height},v:{x:v.x,y:v.y,w:v.width,h:v.height},bounds:c.getBounds(),zoom:c.zoom,scale:{w:s.scale.width,h:s.scale.height}}));});
 await page.screenshot({path:out+`battlefield-open-${count}-mobile.png`});report.worlds.push(result);report.checks.push(`${count} teams: padded terrain at four edges; interior trees; minimap; cursor zoom; drag; mobile resize`);
}
try{
 const r=await room(2),a=await client(r,r.joins[0]),mate=await client(r,r.teammate),b=await client(r,r.joins[1]);
 const q=await pending(r,r.joins[0]);await a.locator('.quest-card').click();await a.getByRole('button',{name:/Chọn Đơn Vị Mở Khóa/}).click();
 const cards=a.locator('.unlock-card');assert.equal(await cards.count(),4);
 for(const name of ['Xe tăng','Pháo binh','Tháp đại bác','Tháp tạo khiên'])await cards.filter({hasText:name}).locator('img').evaluate(img=>{if(!img.complete||!img.naturalWidth)throw Error('Missing art '+img.src);});
 await a.locator('.unlock-card [data-state=ready]').last().waitFor();await wait(180);await a.screenshot({path:out+'battlefield-unlocks-desktop.png'});await a.setViewportSize({width:390,height:844});
 await cards.filter({hasText:'Xe tăng'}).focus();await a.keyboard.press('Enter');assert.equal(await cards.filter({hasText:'Xe tăng'}).getAttribute('aria-pressed'),'true');
 const footer=await a.locator('.unlock-footer').boundingBox();assert.ok(footer.y+footer.height<=844);await a.screenshot({path:out+'battlefield-unlocks-mobile.png'});
 await a.route('**/rewards/claim/',route=>route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'QA: máy chủ chưa xác nhận phần thưởng'})}),{times:1});
 await a.getByRole('button',{name:'Xác Nhận Mở Khóa Đơn Vị'}).click();await a.getByRole('alert').waitFor();assert.equal(await a.locator('.reward-overlay').count(),1);assert.equal(await cards.filter({hasText:'Xe tăng'}).getAttribute('aria-pressed'),'true');
 report.checks.push('Rejected reward shows server error and preserves selection without success');
 const response=a.waitForResponse(res=>res.url().includes('/rewards/claim/')&&res.request().method()==='POST');await a.getByRole('button',{name:'Xác Nhận Mở Khóa Đơn Vị'}).click();
 const claimed=await (await response).json();assert.equal(claimed.unlocked_unit.code,'tank');await mate.waitForFunction(()=>flowStore.getState().unlockedUnits.includes('tank'));assert.equal(await a.locator('.reward-overlay').count(),0);
 const replay=await api(`/matches/${r.match.id}/rewards/claim/`,{team_question_id:q.id,reward_type:'COIN',idempotency_key:crypto.randomUUID()},r.joins[0].participant_token);assert.equal(replay.id,claimed.id);assert.equal(replay.reward_type,'UNLOCK');assert.equal(replay.team_coins,claimed.team_coins);
 report.checks.push('All unlock artwork; mobile footer; keyboard selection; confirmed claim; teammate synchronization; duplicate claim cannot pay twice (existing idempotent replay)');
 await pending(r,r.joins[0]);await a.locator('.quest-card').click();await openCoinBag(a);report.checks.push('Mystery coin bag alternative');
 await a.setViewportSize({width:1440,height:1000});const card=name=>a.locator('.arsenal-card').filter({hasText:name});
 await card('Bộ binh').click();assert.equal(await a.locator('.quantity-panel').count(),1);assert.equal(await a.locator('.selection-info .quantity-panel').count(),1);
 await a.getByRole('button',{name:'5',exact:true}).click();assert.match(await a.locator('.quantity-total').innerText(),/Tổng: 75 xu/);
 const contained=await a.evaluate(()=>{const p=document.querySelector('.selection-info').getBoundingClientRect(),q=document.querySelector('.quantity-panel').getBoundingClientRect(),d=document.querySelector('.command-dock').getBoundingClientRect();return q.y>=p.y&&q.bottom<=p.bottom+1&&p.bottom<=d.bottom;});assert.ok(contained);
 await a.screenshot({path:out+'battlefield-deployment-desktop.png'});await a.getByRole('button',{name:'Xuất 5 Bộ binh',exact:true}).click();for(const p of [a,b])await p.waitForFunction(()=>flowStore.getState().entities.filter(e=>e.unit_code==='infantry').length===5);
 await a.getByRole('spinbutton',{name:'Số lượng quân'}).fill('1.5');assert.ok(await a.locator('.deploy-controls .gold-button').isDisabled());
 await card('Xe tăng').click();assert.equal(await a.getByRole('spinbutton',{name:'Số lượng quân'}).inputValue(),'1');await a.getByRole('button',{name:'Max',exact:true}).click();assert.equal(await a.getByRole('spinbutton',{name:'Số lượng quân'}).inputValue(),'5');
 await a.getByRole('spinbutton',{name:'Số lượng quân'}).fill('2');await a.getByRole('button',{name:'Xuất 2 Xe tăng',exact:true}).click();await b.waitForFunction(()=>flowStore.getState().entities.filter(e=>e.unit_code==='tank').length===2);
 await a.setViewportSize({width:390,height:844});await card('Bộ binh').click();await a.getByRole('button',{name:'Max',exact:true}).click();const coins=await a.evaluate(()=>flowStore.getState().coins);assert.equal(await a.getByRole('spinbutton',{name:'Số lượng quân'}).inputValue(),String(Math.floor(coins/15)));
 await a.screenshot({path:out+'battlefield-deployment-mobile.png'});assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 for(const viewport of [{width:320,height:568},{width:844,height:390},{width:1024,height:600}]){await a.setViewportSize(viewport);await wait(200);await a.locator('.deploy-controls .gold-button').scrollIntoViewIfNeeded();await a.locator('.deploy-controls .gold-button').click({trial:true});assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);if(viewport.width===844)await a.screenshot({path:out+'battlefield-deployment-landscape.png'});}report.checks.push('320px mobile, landscape and short desktop: primary action reachable without horizontal overflow');
 await a.setViewportSize({width:1440,height:1000});await api(`/matches/${r.match.id}/advance-phase/`,{},r.match.host_token,true);await a.waitForFunction(()=>flowStore.getState().match?.phase==='WAR');
 await a.getByRole('button',{name:'1',exact:true}).click();await a.getByRole('button',{name:'Xuất 1 Bộ binh',exact:true}).click();await b.waitForFunction(()=>flowStore.getState().entities.filter(e=>e.unit_code==='infantry').length===6);
 const state=()=>a.evaluate(()=>({seq:flowStore.getState().lastSequenceNumber,pos:flowStore.getState().entities.find(e=>e.unit_code==='infantry').simulation_state.world_position}));const first=await state();await wait(900);const later=await state();assert.ok(later.seq>first.seq);assert.notDeepEqual(later.pos,first.pos);
 report.checks.push('Contained single quantity control; Infantry/Tank batches; presets/MAX; costs; invalid quantity; mobile; Battle deployment, movement and opposing client synchronization');
 await a.keyboard.press('Escape');await cameraCheck(a,2);
 await pending(r,r.joins[1]);await b.locator('.quest-card').click();await b.getByRole('button',{name:/Chọn Đơn Vị Mở Khóa/}).click();
 await b.locator('.unlock-card').filter({hasText:'Pháo binh'}).locator('img').evaluate(img=>img.dispatchEvent(new Event('error')));await b.locator('.unlock-card').filter({hasText:'Pháo binh'}).locator('[data-state=fallback]').waitFor();report.checks.push('Failed image fallback');const modalBefore=await b.evaluate(()=>({seq:flowStore.getState().lastSequenceNumber,pos:flowStore.getState().entities.find(e=>e.unit_code==='infantry')?.simulation_state.world_position}));await wait(900);const modalAfter=await b.evaluate(()=>({seq:flowStore.getState().lastSequenceNumber,pos:flowStore.getState().entities.find(e=>e.unit_code==='infantry')?.simulation_state.world_position}));assert.ok(modalAfter.seq>modalBefore.seq);assert.notDeepEqual(modalAfter.pos,modalBefore.pos);report.checks.push('Reward popup leaves Battle movement and WebSocket ticks running');
 for(const count of [4,8,20]){const large=await room(count),p=await client(large,large.joins[0]);await cameraCheck(p,count);await p.context().close();}assert.deepEqual(report.errors,[]);report.status='PASS';
}catch(e){report.status='FAIL';report.failure=e.stack;throw e;}
finally{await fs.writeFile(out+'battlefield-ui-map-browser.json',JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report,null,2));}
