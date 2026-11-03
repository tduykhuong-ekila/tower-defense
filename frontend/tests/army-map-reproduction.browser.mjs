import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'}),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5183',report={status:'RUNNING',layouts:[]};
async function api(path,data,token){const r=await context.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{'X-Host-Token':token}:{},timeout:120000});assert.ok(r.ok(),await r.text());return r.json();}
try{
 for(const [count,version] of [[2,4],[2,5],[4,5],[8,5],[20,5]]){
  const match=await api('/matches/',{name:`Layout v${version} ${count}`,configuration:{max_teams:count,arena_layout_version:version,initial_coins:5000,first_preparation_duration_seconds:600}}),teams=[];let join;
  for(let i=0;i<count;i++){
   const team=await api(`/matches/${match.id}/teams/`,{name:`Layout ${i+1}`},match.host_token);teams.push(team);
   const member=await api(`/matches/${match.id}/join/`,{display_name:`Layout player ${i+1}`,team_id:team.id});if(i===1)join=member;
   await api(`/matches/${match.id}/teams/${team.id}/ready/`,{is_ready:true},match.host_token);
  }
  await api(`/matches/${match.id}/start/`,{},match.host_token);
  await page.goto(base);await page.evaluate(data=>localStorage.setItem('continuous-room',JSON.stringify(data)),{match,join});await page.goto(base+'/tests/fixtures/continuous.html');
  await page.waitForFunction(()=>window.flowScene?.callbacks&&flowStore.getState().connectionStatus==='connected');
  const geometry=await page.evaluate(()=>{
   const s=flowScene,intersects=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
   const bases=[...s.bases].map(([id,root])=>({id,art:root.getByName('art').getBounds()}));
   const slots=[...s.markers].filter(([id])=>id.includes('tower')).map(([id,root])=>({id,point:{x:root.x,y:root.y},bounds:root.getBounds()}));
   return {slotCount:slots.length,overlaps:slots.flatMap(slot=>bases.filter(b=>intersects(slot.bounds,b.art)).map(b=>({slot:slot.id,base:b.id}))),slots};
  });
  assert.equal(geometry.slotCount,count*6);
  if(version===4)assert.ok(geometry.overlaps.some(o=>o.slot.startsWith('node_tower_t2')));
  else assert.deepEqual(geometry.overlaps,[]);
  if(count===2){
   await page.evaluate(id=>flowScene.focusBase(id),teams[1].id);await page.waitForTimeout(450);
   await page.screenshot({path:`../docs/qa/army-red-base-v${version}.png`});
  }
  for(const zoom of [.6,1,1.4]){
   await page.evaluate(z=>flowScene.zoomController.zoomTo(z),zoom);await page.waitForTimeout(200);
   assert.equal(await page.evaluate(()=>[...flowScene.markers].filter(([id,m])=>id.includes('tower')&&m.visible&&m.input?.enabled).length),count*6);
  }
  // Construct all six positions for every team using authoritative IDs.
  for(const team of teams)for(let slot=1;slot<=6;slot++){
   const index=teams.indexOf(team)+1;
   const result=await api(`/matches/${match.id}/actions/build/`,{team_id:team.id,unit_type_code_or_id:'mg_tower',node_id:`node_tower_t${index}_slot${slot}`,idempotency_key:crypto.randomUUID()},match.host_token);
   assert.equal(result.entity.current_node_id,`node_tower_t${index}_slot${slot}`);
  }
  report.layouts.push({count,version,slots:geometry.slotCount,baseMarkerOverlaps:geometry.overlaps,towersBuilt:count*6,zooms:[.6,1,1.4]});
  await api(`/matches/${match.id}/end/`,{},match.host_token);
 }
 report.status='PASS';
}catch(error){report.status='FAIL';report.failure=error.stack;console.error(error);process.exitCode=1;}
finally{await fs.writeFile('../docs/qa/army-map-browser.json',JSON.stringify(report,null,2));await browser.close();}
