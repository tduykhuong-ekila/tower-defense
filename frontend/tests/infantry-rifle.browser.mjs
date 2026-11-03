import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
const page=await browser.newPage({viewport:{width:1200,height:800}});
page.setDefaultTimeout(15000);
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('response',r=>{if(r.status()>=400)errors.push(r.url())});
try {
 await page.goto((process.env.TEST_BASE_URL||'http://127.0.0.1:5199')+'/tests/fixtures/infantry-rifle.html');
 await page.waitForFunction(()=>window.rifleScene?.visuals.size===12);
 await page.evaluate(()=>{
  const s=rifleScene;s.cameras.main.stopFollow();s.cameras.main.panEffect.reset();s.cameras.main.zoomEffect.reset();s.cameras.main.setZoom(1.5).centerOn(800,590);window.freezeRifle=true;
  window.launched=[];const launch=s.launchShot.bind(s);
  s.launchShot=(actor,...args)=>{launched.push(actor.data.unit_code);return launch(actor,...args)};
 });
 await page.waitForFunction(()=>[...rifleScene.visuals.values()].every(v=>v.root.visible));
 assert.ok(await page.evaluate(()=>Array.from({length:20},(_,team)=>[1,2,3].every(level=>[0,1,2,3].every(frame=>rifleScene.textures.exists(`infantry-${team}-${frame}${level>1?'-lv'+level:''}`)))).every(Boolean)));
 await page.evaluate(()=>fire());
 const firing=await page.evaluate(()=>({launched,shots:rifleScene.shots.filter(s=>s.active).length,
  units:[...rifleScene.visuals.values()].filter(v=>v.data.id.startsWith('rifle')).map(v=>({attacking:v.rifle.attacking,flash:v.rifle.flash.visible,flip:v.sprite.flipX,texture:v.sprite.texture.key,x:v.root.x,y:v.root.y}))}));
 assert.equal(firing.shots,6);assert.deepEqual(firing.launched,Array(6).fill('infantry'));
 assert.ok(firing.units.every((v,i)=>v.attacking&&v.flash&&v.flip===(i>=3)&&v.texture===`infantry-soldier-${i%3+1}`));
 await page.evaluate(()=>{for(const v of rifleScene.visuals.values())v.rifle?.update(45,true,0,v.data.level)});
 const recoil=await page.evaluate(()=>[...rifleScene.visuals.values()].filter(v=>v.data.id.startsWith('rifle')).map(v=>({x:v.root.x,y:v.root.y,offset:v.sprite.x})));
 assert.ok(recoil.every((v,i)=>v.x===firing.units[i].x&&v.y===firing.units[i].y&&Math.abs(v.offset)<=3&&v.offset*(i<3?1:-1)<0));
 await fs.mkdir(new URL('../../docs/qa/infantry-rifle/',import.meta.url),{recursive:true});
 await page.screenshot({path:new URL('../../docs/qa/infantry-rifle/firing.png',import.meta.url).pathname});
 await page.evaluate(()=>{for(const v of rifleScene.visuals.values())v.rifle?.update(200,true,0,v.data.level)});
 assert.ok(await page.evaluate(()=>[...rifleScene.visuals.values()].filter(v=>v.rifle).every(v=>!v.rifle.attacking&&!v.rifle.flash.visible&&v.sprite.x===0)));
 await page.evaluate(()=>{
  const s=rifleScene,v=s.visuals.get('rifle0'),e=v.data,p=e.simulation_state.world_position;
  s.updateState({...s.state,entities:s.state.entities.map(item=>item.id===e.id?{...e,simulation_at:new Date().toISOString(),simulation_state:{...e.simulation_state,movement_state:'MOVING',world_position:{x:p.x+10,y:p.y}}}:item)});
 });
 await page.waitForFunction(()=>rifleScene.visuals.get('rifle0').sprite.anims.currentAnim?.key==='walk-0'&&rifleScene.visuals.get('rifle0').sprite.anims.isPlaying);
 await page.evaluate(()=>rifleScene.playLiveEvents([{type:'BASE_DAMAGED',attacker_id:'rifle1',target_team_id:'team1',damage:5}]));
 assert.ok(await page.evaluate(()=>rifleScene.visuals.get('rifle1').rifle.attacking));
 await page.evaluate(()=>{rifleScene.skipCombat();rifleScene.playCombatEvents([{type:'UNIT_ATTACKED',attacker_id:'rifle2',target_entity_id:'enemy2',damage:5}])});
 await page.waitForFunction(()=>rifleScene.visuals.get('rifle2').rifle.attacking);
 await page.evaluate(()=>rifleScene.skipCombat());
 const pooled=await page.evaluate(()=>{
  const s=rifleScene,old=s.visuals.get('rifle0'),data=old.data;
  s.destroyVisual('rifle0');const v=s.createEntity({...data,id:'reused',team_id:'team19',level:3},old.root.x,old.root.y);
  return {reused:v===old,idle:!v.rifle.attacking&&!v.rifle.flash.visible&&v.sprite.x===0,texture:v.sprite.texture.key};
 });
 assert.ok(pooled.reused&&pooled.idle);assert.equal(pooled.texture,'infantry-soldier-3');
 assert.deepEqual(errors,[]);
 console.log('PASS: rifle textures, six bullets, muzzle flashes, facing, recoil, fixed anchors, recovery, walking, base attacks, replay and pooling.');
} finally {await browser.close()}
