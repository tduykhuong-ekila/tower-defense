// Pin the real entity card, resolve real combat, and compare its HP with persisted server HP.
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
const page=await browser.newPage({viewport:{width:1280,height:900},hasTouch:true});
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5181';
async function api(path,data,token,host=false){const r=await page.request.fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',...(data===undefined?{}:{data}),headers:token?{[host?'X-Host-Token':'X-Participant-Token']:token}:{}});assert.ok(r.ok(),await r.text());return r.json();}
try {
 await page.goto(base);
 const match=await api('/matches/',{name:'Live inspection HP regression',configuration:{gameplay_mode:'LEGACY',initial_coins:1000}});
 const teams=[],joins=[];
 for(let i=0;i<2;i++){teams.push(await api(`/matches/${match.id}/teams/`,{name:`Inspection ${i}`},match.host_token,true));joins.push(await api(`/matches/${match.id}/join/`,{display_name:`Inspection ${i}`,team_id:teams[i].id,role:'MENTEE'}));await api(`/matches/${match.id}/teams/${teams[i].id}/ready/`,{is_ready:true},match.host_token,true);}
 await api(`/matches/${match.id}/start/`,{},match.host_token,true);
 await api(`/matches/${match.id}/advance-phase/`,{},match.host_token,true);
 const own=await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[1].id},joins[0].participant_token);
 await api(`/matches/${match.id}/actions/deploy/`,{unit_type_code_or_id:'infantry',target_team_id:teams[0].id},joins[1].participant_token);
 await page.evaluate(room=>localStorage.setItem('full-gameplay-test-room',JSON.stringify(room)),{match,a:joins[0],b:joins[1]});
 await page.goto(base+'/tests/fixtures/full-gameplay.html?view=a');
 await page.waitForFunction(id=>window.flowScene?.visuals.has(id),own.entity.id);
 await page.evaluate(id=>{const s=window.flowScene,v=s.visuals.get(id);s.navigate(v.root.x,v.root.y,1.4);},own.entity.id);await page.waitForTimeout(700);
 const point=await page.evaluate(id=>{const s=window.flowScene,v=s.visuals.get(id),c=s.cameras.main;return{x:c.x+c.width/2+(v.root.x-c.scrollX-c.width/2)*c.zoom,y:c.y+c.height/2+(v.root.y-24-c.scrollY-c.height/2)*c.zoom};},own.entity.id);
 await page.touchscreen.tap(point.x,point.y);
 const card=page.getByRole('dialog',{name:'Thông tin Bộ binh'});await card.waitFor();
 assert.equal(await card.getByRole('progressbar').getAttribute('aria-valuenow'),'80');
 let hp=80, rounds=0;
 while(hp===80 && rounds++<12){
   const current=await api(`/matches/${match.id}/`,undefined,joins[0].participant_token);
   await api(`/matches/${match.id}/combat/resolve/`,{expected_round:current.configuration.current_round},match.host_token,true);
   const state=await api(`/matches/${match.id}/teams/${teams[0].id}/state/`,undefined,joins[0].participant_token);
   hp=state.entities.find(e=>e.id===own.entity.id)?.current_hp ?? 0;
 }
 assert.ok(hp>0&&hp<80,`Expected surviving damaged infantry, HP=${hp}`);
 await page.waitForFunction(expected=>document.querySelector('.entity-info-card [role=progressbar]')?.getAttribute('aria-valuenow')===String(expected),hp);
 assert.ok(await card.isVisible());
 const result={status:'PASS',initialHp:80,serverHp:hp,displayedHp:Number(await card.getByRole('progressbar').getAttribute('aria-valuenow')),combatRounds:rounds};
 await fs.writeFile(new URL('../../docs/qa/quiz-card-hp-browser.json',import.meta.url),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
