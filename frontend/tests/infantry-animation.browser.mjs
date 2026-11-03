// Real Phaser/React/WebSocket movement probe, against a disposable browser_preview database.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5181';
const baseline=process.env.INFANTRY_AUDIT_BASELINE==='1';
const browser=await chromium.launch({headless:true,channel:'chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const report={status:'RUNNING',baseline,errors:[]};
page.on('pageerror',e=>report.errors.push(e.message));
async function api(path,data,token,host=false){
 const r=await context.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});
 assert.ok(r.ok(),`${path}: ${r.status()} ${await r.text()}`);return r.json();
}
let match;
try{
 match=await api('/matches/',{name:'Infantry animation probe',configuration:{max_teams:2,initial_coins:10000,first_preparation_duration_seconds:600,battle_duration_seconds:600}});
 const teams=[],joins=[];
 for(let i=0;i<2;i++){
  const t=await api(`/matches/${match.id}/teams/`,{name:`Animation ${i+1}`},match.host_token,true);teams.push(t);
  joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:t.id,role:'MENTEE'}));
  await api(`/matches/${match.id}/teams/${t.id}/ready/`,{is_ready:true},match.host_token,true);
 }
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 for(let i=0;i<20;i++)await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[1].id,idempotency_key:`animation-${i}`},joins[0].participant_token);
 await page.goto(base);await page.evaluate(room=>localStorage.setItem('continuous-room',JSON.stringify(room)),{match,join:joins[0]});
 await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&flowScene.visuals.size===20&&flowStore.getState().connectionStatus==='connected');
 await page.evaluate(()=>flowScene.focusBase());await page.waitForTimeout(800);
 await page.evaluate(()=>{
  const scene=flowScene,roots=new Map([...scene.visuals].map(([id,v])=>[id,v.root]));
  window.animationProbe={frames:0,visibility_changes:0,animation_starts:0,identity_changes:0,invalid_render_frames:0,ticks:0,sampling:true,per_unit:{}};
  const previous=new Map();
  for(const v of scene.visuals.values())v.sprite.on('animationstart',()=>animationProbe.animation_starts++);
  flowSocketClient.onEvent(e=>{if(e.event_type==='COMBAT_TICK')animationProbe.ticks++;});
  scene.events.on('postupdate',()=>{
   animationProbe.frames++;
   if(!animationProbe.sampling)return;
   const view=scene.cameras.main.worldView;
   for(const [id,v] of scene.visuals){
    if(roots.get(id)!==v.root)animationProbe.identity_changes++;
    if(!v.root.active||!v.sprite.active||v.root.alpha<.99||v.sprite.alpha<.99||!scene.textures.exists(v.sprite.texture.key))animationProbe.invalid_render_frames++;
    if(!view.contains(v.root.x,v.root.y)||scene.cameras.main.zoom<.5)continue;
    const old=previous.get(id);
    if(old!==undefined&&old!==v.root.visible){animationProbe.visibility_changes++;animationProbe.per_unit[id]=(animationProbe.per_unit[id]||0)+1;}
    previous.set(id,v.root.visible);
   }
  });
 });
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 await page.waitForTimeout(7000);
 report.movement=await page.evaluate(()=>({...animationProbe,sprites:flowScene.visuals.size,visible:[...flowScene.visuals.values()].filter(v=>v.root.visible).length,fps:frameSamples.map(x=>x.fps)}));
 await page.screenshot({path:new URL(`../../docs/qa/infantry-animation-${baseline?'before':'after'}.png`,import.meta.url).pathname});
 assert.ok(report.movement.frames>100);assert.ok(report.movement.ticks>=10);assert.equal(report.movement.identity_changes,0);assert.deepEqual(report.errors,[]);
 if(!baseline){
  assert.equal(report.movement.visibility_changes,0,'moving soldiers must not blink inside the viewport');
  assert.equal(report.movement.invalid_render_frames,0);
  assert.equal(report.movement.animation_starts,20,'each walking animation should start once');
  await page.evaluate(()=>{animationProbe.sampling=false;window.startsBeforeRecovery=animationProbe.animation_starts;flowSocketClient.requestSync();});
  await page.waitForTimeout(600);
  assert.equal(await page.evaluate(()=>animationProbe.animation_starts),20,'a live recovery snapshot must preserve walk phase');
  report.recovery_preserves_walk=true;
  // Exercise pause/resume at the camera culling boundary without network teardown.
  await page.evaluate(()=>{window.oldScroll=flowScene.cameras.main.scrollX;flowScene.cameras.main.scrollX+=10000;});
  await page.waitForTimeout(300);
  await page.evaluate(()=>{flowScene.cameras.main.scrollX=oldScroll;});
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(()=>animationProbe.animation_starts),20,'offscreen pause/resume must not restart walking');
  report.viewport_resume_preserves_walk=true;
  // Hold genuine socket packets across a short gap, then deliver in order.
  await page.evaluate(()=>{const ws=flowSocketClient.ws;window.restorePackets=ws.onmessage;window.heldPackets=[];ws.onmessage=e=>heldPackets.push(e);});
  await page.waitForTimeout(500);
  await page.evaluate(()=>{const ws=flowSocketClient.ws;ws.onmessage=restorePackets;heldPackets.forEach(e=>ws.onmessage(e));});
  await page.waitForTimeout(500);
  assert.equal(await page.evaluate(()=>animationProbe.animation_starts),20,'packet starvation must not cycle idle/walk');
  report.packet_gap_preserves_walk=true;
  // Feed a controlled 300-entity visual fixture through the real scene. The
  // backend room is untouched; this isolates dense rendering from server load.
  await page.evaluate(()=>flowSocketClient.disconnect());await page.waitForTimeout(200);
  await page.evaluate(()=>{
   const scene=flowScene,source=scene.state.entities,baseTime=Date.now();
   const entities=Array.from({length:300},(_,i)=>({...source[i%source.length],id:`dense-${i}`,simulation_at:new Date(baseTime).toISOString(),simulation_state:{...source[i%source.length].simulation_state}}));
   window.denseOrigins=entities.map(e=>({...e.simulation_state.world_position}));
   window.denseTick=0;
   window.denseState={...scene.state,entities};scene.updateState(denseState);
   window.denseTimer=setInterval(()=>{
    denseTick++;
    denseState={...denseState,entities:denseState.entities.map((e,i)=>({...e,simulation_at:new Date(baseTime+denseTick*200).toISOString(),simulation_state:{...e.simulation_state,movement_state:'MOVING',world_position:{x:denseOrigins[i].x+denseTick*.4,y:denseOrigins[i].y}}}))};
    scene.updateState(denseState);
   },200);
  });
  await page.waitForTimeout(800);
  await page.evaluate(()=>{
   const scene=flowScene,roots=new Map([...scene.visuals].map(([id,v])=>[id,v.root])),visible=new Map([...scene.visuals].map(([id,v])=>[id,v.root.visible]));
   window.denseProbe={frames:0,visibility_changes:0,identity_changes:0,initial_objects:scene.children.length};
   scene.events.on('postupdate',()=>{denseProbe.frames++;for(const [id,v] of scene.visuals){if(roots.get(id)!==v.root)denseProbe.identity_changes++;if(visible.get(id)!==v.root.visible)denseProbe.visibility_changes++;visible.set(id,v.root.visible);}});
  });
  await page.waitForTimeout(3000);
  report.dense=await page.evaluate(()=>{
   clearInterval(denseTimer);
   return {...denseProbe,entities:flowScene.visuals.size,visible:[...flowScene.visuals.values()].filter(v=>v.root.visible).length,objects:flowScene.children.length,distinct_positions:new Set(denseState.entities.map(e=>JSON.stringify(e.simulation_state.world_position))).size};
  });
  assert.equal(report.dense.entities,300);assert.equal(report.dense.identity_changes,0);assert.equal(report.dense.visibility_changes,0);
  assert.equal(report.dense.visible,report.dense.distinct_positions);assert.equal(report.dense.objects,report.dense.initial_objects);
 }
 report.status='PASS';console.log(JSON.stringify(report,null,2));
}catch(error){report.status='FAIL';report.error=String(error);throw error;}finally{
 if(match)await api(`/matches/${match.id}/end/`,{},match.host_token,true).catch(()=>{});
 await fs.writeFile(new URL(`../../docs/qa/infantry-animation-${baseline?'before':'after'}.json`,import.meta.url),JSON.stringify(report,null,2));
 await browser.close();
}
