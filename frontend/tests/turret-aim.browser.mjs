// Real BootScene/BattleScene rendering; no backend or changes to combat balance.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5199';
const cannon=process.env.TEST_TOWER_CODE==='cannon_tower',prefix=cannon?'cannon':'mg';
const out=new URL(cannon?'../../output/imagegen/cannon-tower-upgrades/integration/':'../../output/imagegen/machine-gun-upgrades/aiming/',import.meta.url);
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,channel:'chrome'});
const page=await browser.newPage({viewport:{width:1200,height:800}});
page.setDefaultTimeout(15000);
const report={status:'RUNNING',checks:[],errors:[],failures:[]};
page.on('pageerror',e=>report.errors.push(e.message));
page.on('response',r=>{if(r.status()>=400)report.failures.push(r.url())});
const probe=()=>page.evaluate(()=>[...aimScene.visuals.values()].filter(v=>v.turret).map(v=>({
 id:v.data.id,yaw:v.turret.yaw,desired:v.turret.desiredYaw,
 error:Math.abs(Math.atan2(Math.sin(v.turret.desiredYaw-v.turret.yaw),Math.cos(v.turret.desiredYaw-v.turret.yaw))),
 x:v.root.x,y:v.root.y,angle:v.sprite.angle,origin:v.sprite.originY,baseTexture:v.sprite.texture.key,
 frame:Number(v.turret.head.frame.name),headTexture:v.turret.head.texture.key,
 targetError:(()=>{const t=aimScene.visuals.get(v.data.simulation_state.attack_target_id).root;
  const desired=Math.atan2((t.y-v.root.y)/.55,t.x-v.root.x);
  return Math.abs(Math.atan2(Math.sin(desired-v.turret.yaw),Math.cos(desired-v.turret.yaw)))})(),
})));
try {
 await page.goto(base+'/tests/fixtures/turret-aim.html'+(cannon?'?tower=cannon':''));
 await page.waitForFunction(()=>window.aimScene?.visuals.size===6);
 await page.waitForTimeout(700);
 await page.evaluate(()=>aimScene.navigate(800,600,1.5));
 await page.waitForTimeout(700);
 assert.equal(await page.evaluate(()=>!!window.artError),false);
 const initial=await probe();
 assert.equal(initial.length,3);
 if(cannon)assert.deepEqual(initial.map(v=>v.baseTexture),['cannon_tower-base','cannon_tower-base-lv2','cannon_tower-base-lv3']);
 const detail=await page.evaluate(prefix=>{
  const gl=aimScene.game.renderer.gl, expected=!gl||gl.getParameter(gl.MAX_TEXTURE_SIZE)>=4096?512:256;
  return [1,2,3].map(level=>{
   const texture=aimScene.textures.get(prefix+'-turret-'+level),canvas=texture.getSourceImage(),ctx=canvas.getContext('2d');
   let clearEdges=true;
   for(let frame=0;frame<32;frame++) {
    const f=texture.get(frame);
    for(const [x,y,w,h] of [[f.cutX,f.cutY,f.width,1],[f.cutX,f.cutY+f.height-1,f.width,1],[f.cutX,f.cutY,1,f.height],[f.cutX+f.width-1,f.cutY,1,f.height]]) {
     const pixels=ctx.getImageData(x,y,w,h).data;
     for(let i=3;i<pixels.length;i+=4)if(pixels[i])clearEdges=false;
    }
   }
   return {level,width:texture.get(0).width,height:texture.get(0).height,expected,clearEdges};
  });
 },prefix);
 assert.ok(detail.every(d=>d.width===d.expected&&d.height===d.expected*3/4&&d.clearEdges),JSON.stringify(detail));
 report.checks.push({name:'Gun frames match original 512px detail density, with transparent padding at all 32 headings',detail});
 const directions=[];
 for(const direction of [0,4,8,12,15,1]) {
  await page.evaluate(d=>setTargets(d),direction);
  await page.waitForTimeout(750);
  const actual=await probe();
  assert.ok(actual.every(v=>v.error<.01),JSON.stringify(actual));
  assert.ok(actual.every(v=>v.targetError<.01),JSON.stringify(actual));
  assert.ok(actual.every((v,i)=>v.x===initial[i].x&&v.y===initial[i].y&&v.angle===0&&v.origin===.89));
  directions.push({direction,frames:actual.map(v=>v.frame)});
  if(direction%4===0)await page.screenshot({path:new URL(`direction-${direction}.png`,out).pathname});
 }
 assert.equal(new Set(directions.slice(0,4).map(d=>d.frames[0])).size,4);
 report.checks.push({name:'All three levels track moving targets in every quadrant while their foundations stay fixed',directions});
 if(cannon) {
  await page.evaluate(()=>aimScene.updateState({...aimScene.state,mode:'BUILD',selectedUnit:{code:'cannon_tower',level:3,category:'TOWER',cost:40,range:2}}));
  await page.mouse.move(650,500);
  await page.waitForFunction(()=>aimScene.ghost.visible&&aimScene.ghost.texture.key==='cannon_tower-lv3');
  await page.evaluate(()=>{aimScene.updateState({...aimScene.state,mode:'IDLE',selectedUnit:null});aimScene.hideGhost()});
  report.checks.push({name:'Construction preview uses the full approved PNG for the selected cannon level'});
 }
 // Observe the real projectile launcher, including the muzzle point and recoil.
 await page.evaluate(()=>{
  window.launched=[];
  const launch=aimScene.launchShot.bind(aimScene);
  aimScene.launchShot=(actor,target,duration,muzzle)=>{launched.push({id:actor.data.id,muzzle,ground:{x:actor.root.x,y:actor.root.y},yaw:actor.turret?.yaw});return launch(actor,target,duration,muzzle)};
  for(const v of aimScene.visuals.values())if(v.turret)v.turret.yaw-=Math.PI;
  aimScene.playLiveEvents([0,1,2].map(i=>({type:'TOWER_ATTACKED',tower_id:'mg'+i,target_entity_id:'enemy'+i,damage:5})));
 });
 await page.waitForTimeout(70);
 assert.equal(await page.evaluate(()=>launched.length),0,'a reversed gun must turn before its muzzle fires');
 await page.waitForFunction(()=>launched.length===3);
 const shots=await page.evaluate(()=>({shots:launched,recoils:[...aimScene.visuals.values()].filter(v=>v.turret).map(v=>({offset:Math.hypot(v.turret.head.x,v.turret.head.y),angle:v.sprite.angle}))}));
 assert.ok(shots.shots.every(s=>s.muzzle&&Math.hypot(s.muzzle.x-s.ground.x,s.muzzle.y-s.ground.y)>20));
 assert.ok(shots.recoils.every(s=>s.angle===0));
 await page.waitForFunction(()=>[...aimScene.visuals.values()].filter(v=>v.turret).some(v=>Math.hypot(v.turret.head.x,v.turret.head.y)>.1));
 report.checks.push({name:'Live shots wait for aim, leave the muzzle, and recoil only the upper assembly',shots:shots.shots});
 // Legacy rounds have attack events but no simulation target ID.
 await page.evaluate(()=>{setTower('mg0',{simulation_state:undefined});aimScene.playCombatEvents([{type:'TOWER_ATTACKED',tower_id:'mg0',target_entity_id:'enemy0',damage:5}])});
 await page.waitForFunction(()=>launched.length===4);
 report.checks.push({name:'Legacy round playback also aims and fires'});
 await page.waitForTimeout(900);
 await page.evaluate(()=>{window.preservedRoot=aimScene.visuals.get('mg0').root;window.preservedHead=aimScene.visuals.get('mg0').turret.head;window.preservedYaw=aimScene.visuals.get('mg0').turret.yaw;setTower('mg0',{level:3})});
 assert.ok(await page.evaluate(prefix=>{const v=aimScene.visuals.get('mg0');return v.root===preservedRoot&&v.turret.head===preservedHead&&v.turret.yaw===preservedYaw&&v.turret.head.texture.key===prefix+'-turret-3'},prefix));
 report.checks.push({name:'Upgrading preserves the turret, ground anchor and current bearing'});
 await page.evaluate(()=>{setTower('mg1',{status:'DISABLED'});setTargets(8);window.disabledYaw=aimScene.visuals.get('mg1').turret.yaw});
 await page.waitForTimeout(750);
 assert.ok(await page.evaluate(()=>{const t=aimScene.visuals.get('mg1').turret;return t.yaw===disabledYaw&&!t.flash.visible}));
 await page.evaluate(()=>setTower('mg2',{simulation_state:{attack_target_id:null,combat_state:'IDLE'}}));
 await page.waitForTimeout(400);
 const idle=await page.evaluate(()=>aimScene.visuals.get('mg2').turret.yaw);
 await page.evaluate(()=>setTargets(4));await page.waitForTimeout(750);
 assert.equal(await page.evaluate(()=>aimScene.visuals.get('mg2').turret.yaw),idle);
 await page.evaluate(()=>{window.removedHead=aimScene.visuals.get('mg0').turret.head;aimScene.updateState({...aimScene.state,entities:aimScene.state.entities.filter(e=>e.id!=='mg0')})});
 assert.equal(await page.evaluate(()=>!aimScene.visuals.has('mg0')&&!removedHead.scene),true);
 report.checks.push({name:'Disabled and idle towers stop tracking; destroyed towers dispose of their moving parts'});
 if(cannon) {
  await page.goto(base+'/tests/fixtures/fortification-cards.html');
  await page.waitForFunction(()=>typeof window.renderCards==='function');
  for(const level of [1,2,3]) {
   await page.evaluate(level=>renderCards(level),level);
   await page.waitForFunction(level=>{const img=document.querySelector('img[src*="cannon_tower"]');return img?.complete&&img.naturalWidth===512&&img.src.endsWith('cannon_tower'+(level>1?'-lv'+level:'')+'.png')},level);
  }
  await page.screenshot({path:new URL('picker-level-3.png',out).pathname});
  await page.goto(base+'/tests/fixtures/turret-aim.html?tower=cannon&panel');
  await page.waitForFunction(()=>typeof window.renderLevel==='function');
  for(const level of [1,2,3]) {
   await page.evaluate(level=>renderLevel(level),level);
   await page.waitForFunction(level=>{const images=[...document.querySelectorAll('.team-upgrade-panel img')];return images.length===(level<3?2:1)&&images.every(img=>img.complete&&img.naturalWidth===512)&&images[0].src.endsWith('cannon_tower'+(level>1?'-lv'+level:'')+'.png')},level);
  }
  await page.screenshot({path:new URL('upgrade-level-3.png',out).pathname});
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>renderLevel(1));
  await page.waitForFunction(()=>document.querySelectorAll('.entity-illustration[data-state="ready"]').length===2);
  assert.ok(await page.locator('.team-upgrade-panel').evaluate(el=>el.getBoundingClientRect().right<=innerWidth&&el.scrollWidth<=innerWidth));
  await page.screenshot({path:new URL('upgrade-mobile.png',out).pathname});
  report.checks.push({name:'All cannon picker cards and upgrade previews load the approved PNGs on desktop and mobile'});
 }
 assert.deepEqual(report.errors,[]);assert.deepEqual(report.failures,[]);
 report.status='PASS';console.log(JSON.stringify(report,null,2));
} catch(e) {report.status='FAIL';report.failure=String(e.stack||e);await page.screenshot({path:new URL('failure.png',out).pathname}).catch(()=>{});throw e;}
finally {await fs.writeFile(new URL('browser-qa.json',out),JSON.stringify(report,null,2));await browser.close();}
