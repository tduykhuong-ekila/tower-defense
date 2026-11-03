// Integration regression: real React HUD, Phaser, HTTP and WebSockets.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5199';
const output=new URL('../../docs/qa/',import.meta.url);
const browser=await chromium.launch({headless:true,channel:'chrome'});
const req=await browser.newContext(),report={status:'RUNNING',checks:[],layouts:[],deployment_layouts:[],errors:[]};
let room;
async function api(path,data,token,host=false){
 const r=await req.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{},timeout:30000});
 assert.ok(r.ok(),`${path}: ${r.status()} ${await r.text()}`);return r.json();
}
try{
 const bankToken=crypto.randomUUID()+crypto.randomUUID();
 const upload=await req.request.post(base+'/api/v1/question-banks/upload/',{headers:{'X-Question-Bank-Token':bankToken},multipart:{file:{name:'army-ux.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:await fs.readFile(new URL('./fixtures/team-upgrades.xlsx',import.meta.url))}}});
 assert.ok(upload.ok(),await upload.text());const bank=await upload.json();
 const match=await api('/matches/',{name:'Army UX regression',question_bank_id:bank.id,question_bank_token:bankToken,configuration:{max_teams:3,initial_coins:5000,first_preparation_duration_seconds:600,preparation_duration_seconds:600,battle_duration_seconds:600}});
 room={match,teams:[],joins:[]};
 for(let i=0;i<3;i++){
  const team=await api(`/matches/${match.id}/teams/`,{name:`UX Team ${i+1}`},match.host_token,true);room.teams.push(team);
  room.joins.push(await api(`/matches/${match.id}/join/`,{display_name:`UX Player ${i+1}`,team_id:team.id,role:'MENTEE'}));
  await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token,true);
 }
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 const token=room.joins[0].participant_token,q=await api(`/matches/${match.id}/questions/current/`,undefined,token);
 await api(`/matches/${match.id}/questions/current/`,{action:'OPEN_SESSION',question_id:q.id,viewer_id:crypto.randomUUID()},token);
 await api(`/matches/${match.id}/questions/${q.id}/answer/`,{answer:'A'},token);
 await api(`/matches/${match.id}/rewards/claim/`,{team_question_id:q.id,reward_type:'UNLOCK',unit_type_id:'tank',idempotency_key:crypto.randomUUID()},token);
 const context=await browser.newContext({viewport:{width:1440,height:1000},hasTouch:true}),page=await context.newPage(),commands=[];
 page.setDefaultTimeout(15000);page.on('pageerror',e=>report.errors.push(e.message));
 page.on('request',r=>{if(r.url().endsWith('/actions/army/')&&r.method()==='POST')commands.push(r.postDataJSON());});
 await page.goto(base);await page.evaluate(r=>localStorage.setItem('continuous-room',JSON.stringify(r)),{match,join:room.joins[0]});
 await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
 const button=(name)=>page.getByRole('button',{name,exact:true});
 const card=name=>page.locator('.arsenal-card').filter({hasText:name});
 await card('Bộ binh').click();await button('Chọn mục tiêu cho lính mới').click();
 assert.equal(await page.getByRole('dialog').locator('.attack-target-row').count(),2);
 await page.getByRole('dialog').getByRole('button',{name:/UX Team 2/}).click();
 await page.getByRole('spinbutton',{name:'Số lượng quân'}).fill('5');await button('Xuất 5 Bộ binh → UX Team 2').click();
 await page.waitForFunction(()=>flowStore.getState().entities.filter(e=>e.unit_code==='infantry').length===5);
 await card('Xe tăng').click();await button('Xuất 1 Xe tăng → UX Team 2').click();
 await page.waitForFunction(()=>flowStore.getState().entities.some(e=>e.unit_code==='tank'));
 const ready=page.getByRole('region',{name:'Sẵn sàng triển khai'});
 const readyTitle=await ready.locator('.selection-title').innerText(),readyStats=await ready.locator('.selection-stats').innerText();
 async function assertReadyUnchanged(expectedTarget=2){
  assert.equal(await ready.locator('.selection-title').innerText(),readyTitle);
  assert.equal(await ready.locator('.selection-stats').innerText(),readyStats);
  assert.match(await ready.innerText(),/SẴN SÀNG TRIỂN KHAI/);
  assert.doesNotMatch(await ready.innerText(),/THÔNG TIN CĂN CỨ|Khiên/);
  assert.ok((await button('Chọn mục tiêu cho lính mới').innerText()).includes(`UX Team ${expectedTarget}`));
 }
 await page.evaluate(id=>flowScene.callbacks.onBaseClick(id),room.teams[2].id);await assertReadyUnchanged(3);
 await page.getByRole('button',{name:'Căn cứ 2 UX Team 2',exact:true}).click();await assertReadyUnchanged(2);
 await page.evaluate(id=>flowScene.callbacks.onBaseClick(id),room.teams[0].id);await assertReadyUnchanged(2);
 await button('Xem căn cứ UX Team 3').click();await assertReadyUnchanged(3);
 await button('Xem các đội').click();await page.locator('.team-directory .drawer-team').filter({hasText:'UX Team 2'}).click();
 await assertReadyUnchanged(2);
 // Without a selected catalog unit, inspecting another base must remain read-only.
 await card('Xe tăng').click();
 await page.evaluate(id=>flowScene.callbacks.onBaseClick(id),room.teams[2].id);
 await page.waitForFunction(id=>flowScene.state.selectedEntityId===id,room.teams[2].id);
 assert.equal(await page.evaluate(()=>flowScene.state.selectedTargetTeamId),room.teams[1].id);
 await card('Xe tăng').click();await assertReadyUnchanged(2);
 assert.equal(commands.length,0);
 assert.ok((await page.evaluate(()=>flowStore.getState().entities.map(e=>e.target_team_id))).every(id=>id===room.teams[1].id));
 report.checks.push('While deploying, map/minimap/sidebar/directory clicks update the new-troop target without changing the ready title, stats or existing troop orders; own-base clicks and inspection with no unit selected preserve the target.');
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 const panel=page.getByRole('region',{name:'Điều khiển quân đội'}),pb=name=>panel.getByRole('button',{name,exact:true});
 const selectedIds=()=>page.evaluate(()=>flowScene.state.selectedArmyIds||[]);
 const allIds=await page.evaluate(()=>flowStore.getState().entities.filter(e=>e.entity_kind==='UNIT').map(e=>e.id));
 const tankId=await page.evaluate(()=>flowStore.getState().entities.find(e=>e.unit_code==='tank').id);
 async function pointAt(kind,id){
  await page.evaluate(({kind,id})=>{
   const s=flowScene,v=kind==='unit'?s.visuals.get(id).root:s.bases.get(id);
   s.zoomController.moveTo(v.x,v.y-(kind==='unit'?18:50),1.35,true);
  },{kind,id});
  await page.waitForTimeout(140);
  return page.evaluate(({kind,id})=>{
   const s=flowScene,v=kind==='unit'?s.visuals.get(id).root:s.bases.get(id),x=v.x,y=v.y-(kind==='unit'?18:50);
   const c=s.cameras.main,box=s.game.canvas.getBoundingClientRect();
   return {x:box.left+c.x+c.width/2+(x-c.scrollX-c.width/2)*c.zoom,y:box.top+c.y+c.height/2+(y-c.scrollY-c.height/2)*c.zoom};
  },{kind,id});
 }
 async function clickUnit(id,touch=false,shift=false){
  const p=await pointAt('unit',id);
  if(shift)await page.keyboard.down('Shift');
  if(touch)await page.touchscreen.tap(p.x,p.y);else await page.mouse.click(p.x,p.y);
  if(shift)await page.keyboard.up('Shift');
 }
 async function clickBase(id){const p=await pointAt('base',id);await page.mouse.click(p.x,p.y);}
 async function boxPoints(ids){
  await page.evaluate(ids=>{
   const s=flowScene,roots=ids.map(id=>s.visuals.get(id).root),xs=roots.map(r=>r.x),ys=roots.map(r=>r.y);
   const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
   const zoom=Math.min(1.15,(innerWidth<700?innerWidth-90:innerWidth-760)/(maxX-minX+80),(innerHeight-460)/(maxY-minY+80));
   s.zoomController.moveTo((minX+maxX)/2,(minY+maxY)/2,Math.max(.2,zoom),true);
  },ids);
  await page.waitForTimeout(140);
  return page.evaluate(ids=>{
   const s=flowScene,roots=ids.map(id=>s.visuals.get(id).root),xs=roots.map(r=>r.x),ys=roots.map(r=>r.y),c=s.cameras.main,canvas=s.game.canvas.getBoundingClientRect();
   const screen=(x,y)=>({x:canvas.left+c.x+c.width/2+(x-c.scrollX-c.width/2)*c.zoom,y:canvas.top+c.y+c.height/2+(y-c.scrollY-c.height/2)*c.zoom});
   return {from:screen(Math.min(...xs)-22,Math.min(...ys)-22),to:screen(Math.max(...xs)+22,Math.max(...ys)+22)};
  },ids);
 }
 async function chooseAll(){
  await pb('Tùy chọn chỉ huy').click();await page.getByRole('dialog',{name:'Tùy chọn chỉ huy'}).getByRole('button',{name:/^Chọn toàn quân/}).click();
 }
 // Real hit testing from catalog selection into map-first command mode.
 await clickUnit(tankId);await page.waitForFunction(id=>flowScene.state.selectedArmyIds?.length===1&&flowScene.state.selectedArmyIds[0]===id,tankId);
 assert.equal(await panel.locator('.army-group-chips').count(),0);
 const infantryId=allIds.find(id=>id!==tankId);
 await clickUnit(infantryId,false,true);await page.waitForFunction(()=>flowScene.state.selectedArmyIds?.length===2);
 const added=(await selectedIds()).find(id=>id!==tankId);
 await clickUnit(added,false,true);await page.waitForFunction(id=>flowScene.state.selectedArmyIds?.length===1&&flowScene.state.selectedArmyIds[0]===id,tankId);
 await clickBase(room.teams[2].id);
 assert.equal(commands.length,0);assert.match(await pb('Chọn mục tiêu cho quân đã chọn').innerText(),/UX Team 3/);
 await pb('Thực hiện lệnh cho 1 quân').click();
 await page.waitForFunction(id=>flowStore.getState().entities.find(e=>e.unit_code==='tank')?.target_team_id===id,room.teams[2].id);
 assert.equal(commands[0].unit_ids.length,1);
 assert.ok((await page.evaluate(()=>flowStore.getState().entities.filter(e=>e.unit_code==='infantry').map(e=>e.target_team_id))).every(id=>id===room.teams[1].id));
 report.checks.push('Actual mouse clicks select one unit; Shift-click adds/removes; clicking an enemy base prepares selected-only retarget without issuing an order.');
 // Shift-drag box-selects directly from the deployment tab.
 await button('Xuất lính / Xây dựng').click();
 let points=await boxPoints(allIds);await page.keyboard.down('Shift');await page.mouse.move(points.from.x,points.from.y);await page.mouse.down();await page.mouse.move(points.to.x,points.to.y,{steps:15});await page.mouse.up();await page.keyboard.up('Shift');
 await page.waitForFunction(()=>flowScene.state.selectedArmyIds?.length>=2);
 assert.ok((await selectedIds()).every(id=>allIds.includes(id)));
 await chooseAll();
 await page.keyboard.down('Shift');await page.mouse.move(650,390);await page.mouse.down();await page.mouse.move(750,460,{steps:5});
 await page.keyboard.press('Escape');await page.mouse.up();await page.keyboard.up('Shift');await page.waitForFunction(()=>flowScene.state.selectedArmyIds?.length===0);
 await chooseAll();
 const cameraBefore=await page.evaluate(()=>({x:flowScene.cameras.main.scrollX,y:flowScene.cameras.main.scrollY}));
 const beforePan=await selectedIds();
 await page.mouse.move(720,420);await page.mouse.down();await page.mouse.move(800,460,{steps:8});await page.mouse.up();
 assert.deepEqual((await selectedIds()).sort(),beforePan.sort());
 const cameraAfter=await page.evaluate(()=>({x:flowScene.cameras.main.scrollX,y:flowScene.cameras.main.scrollY}));
 assert.ok(Math.hypot(cameraAfter.x-cameraBefore.x,cameraAfter.y-cameraBefore.y)>1);
 report.checks.push('Shift-drag selects a rectangle, Escape cancels the box, and plain drag pans without changing the selected group.');
 await clickUnit(tankId);
 await panel.getByRole('button',{name:'Rút quân'}).click();await pb('Thực hiện lệnh cho 1 quân').click();
 await page.waitForFunction(()=>['RETREAT','AT_RALLY'].includes(flowStore.getState().entities.find(e=>e.unit_code==='tank')?.simulation_state?.order));
 assert.equal(await page.getByRole('alertdialog').count(),0);assert.equal(commands.at(-1).unit_ids.length,1);
 await clickBase(room.teams[2].id);
 assert.equal(await panel.getByRole('button',{name:'Tấn công'}).getAttribute('aria-pressed'),'true');
 await pb('Thực hiện lệnh cho 1 quân').click();await page.waitForFunction(()=>flowStore.getState().entities.find(e=>e.unit_code==='tank')?.simulation_state?.order==='ATTACK');
 report.checks.push('Retreat uses the home rally automatically; selecting an enemy base switches back to attack and lets the same tank rejoin combat.');
 await pb('Chọn mục tiêu cho quân đã chọn').click();
 const targetMenu=page.getByRole('dialog',{name:'Chọn mục tiêu tấn công'});
 assert.equal(await targetMenu.getByRole('button',{name:/^Tấn công →/}).count(),2);
 assert.equal(await targetMenu.getByRole('button',{name:'Tấn công → UX Team 3',exact:true}).isEnabled(),false);
 await page.keyboard.press('Escape');assert.equal((await selectedIds()).length,1);
 const beforeTargetCommand=commands.length;
 await pb('Chọn mục tiêu cho quân đã chọn').click();
 await targetMenu.getByRole('button',{name:'Tấn công → UX Team 2',exact:true}).click();
 await page.waitForFunction(id=>flowStore.getState().entities.find(e=>e.unit_code==='tank')?.target_team_id===id,room.teams[1].id);
 assert.equal(commands.length,beforeTargetCommand+1);
 assert.deepEqual(commands.at(-1).unit_ids,[tankId]);
 assert.equal(await targetMenu.count(),0);
 report.checks.push('Toolbar target selection shares the right-click command list: clicking a base issues exactly one selected-only attack immediately; Escape preserves the group.');
 // Actual touch events: additive taps, panning, pinch and explicit rectangle mode.
 await page.setViewportSize({width:390,height:844});await clickUnit(tankId,true);
 await panel.getByRole('button',{name:/^Chọn thêm/}).tap();await clickUnit(infantryId,true);
 await page.waitForFunction(()=>flowScene.state.selectedArmyIds?.length===2);
 const touchAdded=(await selectedIds()).find(id=>id!==tankId);await clickUnit(touchAdded,true);
 await page.waitForFunction(()=>flowScene.state.selectedArmyIds?.length===1);
 await panel.getByRole('button',{name:/^Chọn thêm/}).tap();
 assert.equal(await page.locator('.entity-info-card:visible').count(),0);
 const cdp=await context.newCDPSession(page),touch=async(type,touchPoints)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints});
 const selectedBeforeTouch=await selectedIds();
 await touch('touchStart',[{x:170,y:290,id:1}]);await touch('touchMove',[{x:205,y:320,id:1}]);await touch('touchEnd',[]);
 assert.deepEqual(await selectedIds(),selectedBeforeTouch);
 await panel.getByRole('button',{name:/^Khoanh vùng/}).tap();
 const zoomBefore=await page.evaluate(()=>flowScene.zoomController.targetZoom);
 report.pinch=[];const pinchState=()=>page.evaluate(()=>({zoom:flowScene.zoomController.targetZoom,distance:flowScene.pinchDistance,multi:flowScene.multiTouch,mode:flowScene.state.mode,touchPointers:flowScene.input.manager.pointers.filter(p=>p.wasTouch&&p.isDown).length}));
 await touch('touchStart',[{x:130,y:300,id:1},{x:230,y:300,id:2}]);await page.waitForTimeout(60);report.pinch.push(await pinchState());
 await touch('touchMove',[{x:130,y:300,id:1},{x:230,y:300,id:2}]);await page.waitForTimeout(60);report.pinch.push(await pinchState());
 await touch('touchMove',[{x:110,y:300,id:1},{x:250,y:300,id:2}]);await page.waitForTimeout(60);report.pinch.push(await pinchState());await touch('touchEnd',[]);
 assert.deepEqual(await selectedIds(),selectedBeforeTouch);
 const zoomAfter=await page.evaluate(()=>flowScene.zoomController.targetZoom);assert.ok(zoomAfter>zoomBefore,JSON.stringify({zoomBefore,zoomAfter,pointers:await page.evaluate(()=>[flowScene.input.pointer1,flowScene.input.pointer2].map(p=>({isDown:p.isDown,x:p.x,y:p.y})))}));
 await pb('Bỏ chọn').tap();await panel.getByRole('button',{name:/^Khoanh vùng/}).tap();
 points=await boxPoints(allIds);
 await touch('touchStart',[{...points.from,id:1}]);
 for(let i=1;i<=12;i++)await touch('touchMove',[{x:points.from.x+(points.to.x-points.from.x)*i/12,y:points.from.y+(points.to.y-points.from.y)*i/12,id:1}]);
 await touch('touchEnd',[]);
 await page.waitForFunction(()=>flowScene.state.selectedArmyIds?.length>=2&&!flowScene.state.armySelectionMode);
 assert.ok((await selectedIds()).every(id=>allIds.includes(id)));
 assert.equal(await page.evaluate(()=>flowScene.state.armySelectionMode),false);
 report.checks.push('Actual touch taps add/remove units, ordinary drag preserves selection, pinch zoom never selects, and touch rectangle selection automatically exits.');
 await chooseAll();
 await panel.getByRole('button',{name:'Rút quân'}).click();await pb('Thực hiện lệnh cho 6 quân').click();
 assert.match(await page.getByRole('alertdialog').innerText(),/6 quân/);await page.keyboard.press('Escape');assert.equal((await selectedIds()).length,6);
 await pb('Tùy chọn chỉ huy').click();await page.getByRole('dialog',{name:'Tùy chọn chỉ huy'}).getByRole('button',{name:'Rút toàn quân…',exact:true}).click();
 const extra=await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:room.teams[1].id,quantity:1,idempotency_key:crypto.randomUUID()},token);
 const extraId=extra.entities[0].id;
 await page.waitForFunction(id=>flowStore.getState().entities.some(e=>e.id===id),extraId);
 await button('Xác nhận rút 6 quân').click();
 await page.waitForFunction(ids=>ids.every(id=>['RETREAT','AT_RALLY'].includes(flowStore.getState().entities.find(e=>e.id===id)?.simulation_state?.order)),allIds);
 assert.equal(commands.at(-1).unit_ids.length,6);assert.ok(!commands.at(-1).unit_ids.includes(extraId));
 assert.equal(await page.evaluate(id=>flowStore.getState().entities.find(e=>e.id===id)?.simulation_state?.order||'ATTACK',extraId),'ATTACK');
 assert.ok(commands.every(command=>command.unit_ids?.length>0));
 report.checks.push('Canceling confirmation preserves map selection; all-army retreat freezes six IDs and excludes a troop deployed after opening confirmation.');
 for(const viewport of [{width:1440,height:1000},{width:390,height:844},{width:844,height:390}]){
  await page.setViewportSize(viewport);await pb('Bỏ chọn').click();
  const empty=await page.locator('.command-dock').boundingBox();
  assert.equal(await panel.locator('.army-command-form').count(),0);
  await chooseAll();
  const attack=await page.locator('.command-dock').boundingBox();
  await panel.getByRole('button',{name:'Rút quân'}).click();
  const retreat=await page.locator('.command-dock').boundingBox();
  assert.equal(retreat.height,attack.height);assert.equal(retreat.y,attack.y);
  assert.ok(attack.height<=(viewport.width<700?140:116));assert.ok(empty.height<attack.height);
  for(const control of await panel.locator('.army-command-form button').all())assert.equal(Math.round((await control.boundingBox()).height),32);
  assert.ok(retreat.x>=0&&retreat.x+retreat.width<=viewport.width+1&&retreat.y>=0&&retreat.y+retreat.height<=viewport.height+1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  report.layouts.push({...viewport,empty,selected:retreat});
  await page.screenshot({path:new URL(`army-map-command-${viewport.width}.png`,output).pathname});
  await panel.getByRole('button',{name:'Tấn công'}).click();await pb('Chọn mục tiêu cho quân đã chọn').click();
  const box=await page.getByRole('dialog').boundingBox();assert.ok(box.x>=0&&box.y>=0&&box.y+box.height<=viewport.height+1);await page.keyboard.press('Escape');
 }
 // Resupply allows retreat but must not turn a base click into an illegal attack order.
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 await page.waitForFunction(()=>!document.querySelector('.army-order-button[aria-label="Tấn công"]')?.disabled && document.querySelector('.army-order-button[aria-label="Rút quân"]')?.getAttribute('aria-pressed')==='true');
 report.resupply=await page.evaluate(()=>({phase:flowStore.getState().match?.phase,round:flowStore.getState().match?.configuration.current_round,order:document.querySelector('.army-order-button[aria-label="Rút quân"]')?.getAttribute('aria-pressed')==='true'?'RETREAT_ALL':'RETARGET',attackDisabled:document.querySelector('.army-order-button[aria-label="Tấn công"]')?.disabled}));
 assert.equal(report.resupply.attackDisabled,false);
 await page.evaluate(id=>flowScene.callbacks.onBaseClick(id),room.teams[2].id);
 await panel.getByRole('button',{name:'Tấn công'}).click();
 await pb('Thực hiện lệnh cho 6 quân').click();
 await page.waitForFunction(ids=>ids.every(id=>flowStore.getState().entities.find(e=>e.id===id)?.simulation_state?.order==='ATTACK'),allIds);
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 report.checks.push('Compact command row stays fixed between attack and retreat on desktop/mobile; selected returning troops can be redirected during later preparation.');
 await page.setViewportSize({width:390,height:844});await button('Thu gọn').tap();assert.equal(await page.locator('.command-dock').isVisible(),false);await button('Mở lệnh').tap();
 await button('Xuất lính / Xây dựng').tap();await card('Bộ binh').tap();
 for(const viewport of [{width:1440,height:1000},{width:390,height:844},{width:844,height:390}]){
  await page.setViewportSize(viewport);
  const frame=async()=>({dock:await page.locator('.command-dock').boundingBox(),cards:await page.locator('.arsenal').boundingBox(),category:await page.locator('.command-category').boundingBox()});
  const baseline=await frame();
  for(const name of ['Bộ binh','Bộ binh','Xe tăng','Bộ binh']) {
   await card(name).click();
   const next=await frame();
   for(const part of ['dock','cards','category']) for(const dimension of ['x','y','width','height'])
    assert.ok(Math.abs(next[part][dimension]-baseline[part][dimension])<=1,`Stable ${part}.${dimension} at ${viewport.width}: ${JSON.stringify({baseline,next})}`);
  }
  report.deployment_layouts.push({...viewport,...baseline,selectionChanges:'unchanged within 1px'});
  await page.evaluate(()=>document.activeElement instanceof HTMLElement && document.activeElement.blur());
  await page.mouse.move(viewport.width/2,90);
  await page.screenshot({path:new URL(`army-deployment-ux-${viewport.width}.png`,output).pathname});
  const dock=await page.locator('.command-dock').boundingBox();
  assert.ok(dock.x>=0 && dock.x+dock.width<=viewport.width+1 && dock.y>=0 && dock.y+dock.height<=viewport.height+1);
  const actionBounds=await page.locator('.deployment-action-bar>.gold-button').boundingBox();
  assert.ok(actionBounds.y>=0 && actionBounds.y+actionBounds.height<=viewport.height+1,'Deployment action remains visible without scrolling');
  await button('Chọn mục tiêu cho lính mới').click();
  const dialog=page.getByRole('dialog');
  await page.keyboard.press('Tab');
  assert.ok(await dialog.evaluate(el=>el.contains(document.activeElement)));
  await page.keyboard.press('Escape');
 }
 // Apply an eliminated-target update to the real store; never silently select another opponent.
 await page.evaluate(id=>flowStore.setState({teams:flowStore.getState().teams.map(t=>t.id===id?{...t,status:'ELIMINATED',base_hp:0}:t)}),room.teams[1].id);
 await page.waitForFunction(()=>document.querySelector('.target-picker')?.textContent.includes('Chọn đối thủ'));
 assert.equal(await page.locator('.deployment-action-bar>.gold-button').isDisabled(),true);
 report.checks.push('Eliminated target is cleared and blocks deployment; target dialogs trap keyboard focus.');
 assert.deepEqual(report.errors,[]);report.status='PASS';
}catch(e){report.status='FAIL';report.failure=e.stack;process.exitCode=1;for(const c of browser.contexts())for(const p of c.pages())await p.screenshot({path:new URL('army-command-ux-failure.png',output).pathname}).catch(()=>{});}
finally{if(room)await api(`/matches/${room.match.id}/end/`,{},room.match.host_token,true).catch(()=>{});await fs.writeFile(new URL('army-command-ux-browser.json',output),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));await browser.close();}
