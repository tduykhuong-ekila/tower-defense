// Real deployment UI beyond the old cap, plus bounded sprite-pool identity reuse.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5181';
const browser=await chromium.launch({headless:true,channel:'chrome'}),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const report={status:'RUNNING',errors:[]};page.on('pageerror',e=>report.errors.push(e.message));
async function api(path,data,token,host=false){const r=await context.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),`${path}: ${r.status()} ${await r.text()}`);return r.json();}
try{
 const match=await api('/matches/',{name:'Infantry render verification',configuration:{max_teams:2,max_active_units_per_team:1,initial_coins:10000,first_preparation_duration_seconds:600}}),teams=[],joins=[];
 for(let i=0;i<2;i++){const t=await api(`/matches/${match.id}/teams/`,{name:`Render ${i+1}`},match.host_token,true);teams.push(t);joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Player ${i+1}`,team_id:t.id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${t.id}/ready/`,{is_ready:true},match.host_token,true);}
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 for(let i=0;i<20;i++)await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[1].id,idempotency_key:`render-${i}`},joins[0].participant_token);
 await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match,join:joins[0]});await page.goto(base+'/tests/fixtures/continuous.html');
 await page.waitForFunction(()=>window.flowScene?.callbacks&&flowScene.visuals.size===20&&flowStore.getState().connectionStatus==='connected');
 const card=page.locator('.arsenal-card').filter({hasText:'Bộ binh'});assert.equal(await card.isDisabled(),false);assert.match(await card.innerText(),/80 HP.*7/s);
 await card.click();
 await page.getByRole('button',{name:'Xuất quân'}).click();
 await page.waitForFunction(()=>flowScene.visuals.size===21);
 const state=await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,joins[0].participant_token);assert.equal(state.team.coins,10000-21*15);
 report.ui_purchase_beyond_cap=true;
 report.pool=await page.evaluate(()=>{
  const scene=flowScene,ids=[...scene.visuals.keys()].slice(0,2),roots=ids.map(id=>scene.visuals.get(id).root),oldCount=scene.children.length;
  ids.forEach(id=>scene.destroyVisual(id));const pooled=scene.infantryPool.length;scene.reconcile();
  const recycled=ids.every(id=>roots.includes(scene.visuals.get(id).root));
  return {pooled,recycled,stable_ids:scene.visuals.size===21,ids_rebound:ids.every(id=>scene.visuals.get(id).root.getData('entityId')===id),no_new_objects:scene.children.length===oldCount};
 });
 assert.equal(report.pool.pooled,2);for(const key of ['recycled','stable_ids','ids_rebound','no_new_objects'])assert.equal(report.pool[key],true);
 await page.screenshot({path:new URL('../../docs/qa/infantry-ui-desktop.png',import.meta.url).pathname});
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(400);
 await page.screenshot({path:new URL('../../docs/qa/infantry-ui-mobile.png',import.meta.url).pathname});
 assert.deepEqual(report.errors,[]);report.status='PASS';
 await api(`/matches/${match.id}/end/`,{},match.host_token,true);console.log(JSON.stringify(report,null,2));
}catch(error){report.status='FAIL';report.error=String(error);report.debug=await page.evaluate(()=>({mode:window.flowScene?.state.mode,selected:window.flowScene?.state.selectedUnit,entities:window.flowStore?.getState().entities.length,body:document.body.innerText.slice(-1800)}));await page.screenshot({path:new URL('../../docs/qa/infantry-ui-failure.png',import.meta.url).pathname});throw error;}
finally{await fs.writeFile(new URL('../../docs/qa/infantry-render.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();}
