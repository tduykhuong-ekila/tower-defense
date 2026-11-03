// Real Phaser rendering/interpolation with server-shaped snapshots; no backend.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5199';
const vehicle=process.env.TEST_VEHICLE==='artillery'?'artillery':'tank';
const out=new URL(`../../output/imagegen/${vehicle}-upgrades/integration/`,import.meta.url);
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,channel:'chrome'});
const page=await browser.newPage({viewport:{width:1200,height:800}});
page.setDefaultTimeout(15000);
const report={status:'RUNNING',checks:[],errors:[],failures:[]};
page.on('pageerror',e=>report.errors.push(e.message));
page.on('response',r=>{if(r.status()>=400)report.failures.push(r.url())});
const sample=()=>page.evaluate(vehicle=>[...aimScene.visuals.values()].filter(v=>v.data.unit_code===vehicle).map(v=>{
 const target=aimScene.visuals.get(v.data.simulation_state?.attack_target_id)?.root;
 // Independent calculation from the hull's normalized mounting point.
 const mountX=vehicle==='artillery'?-4.5:-2.2;
 const mount={x:v.root.x+mountX*Math.cos(v.drive.yaw)*68/94,y:v.root.y+mountX*Math.sin(v.drive.yaw)*.55*68/94};
 const expected=target?Math.atan2((target.y-mount.y)/.55,target.x-mount.x):v.turret.yaw;
 return {id:v.data.id,x:v.root.x,y:v.root.y,angle:v.sprite.angle,yaw:v.turret.yaw,
  error:Math.abs(Math.atan2(Math.sin(expected-v.turret.yaw),Math.cos(expected-v.turret.yaw))),
  flipped:v.sprite.flipX,headFlipped:v.turret.head.flipX,frame:Number(v.turret.head.frame.name),
  bodyYaw:v.drive.yaw,desiredBodyYaw:v.drive.desiredYaw,bodyFrame:Number(v.sprite.frame.name),
  hull:v.sprite.texture.key,width:v.sprite.displayWidth,height:v.sprite.displayHeight,
  hitWidth:v.root.width,hitHeight:v.root.height,
  headWidth:v.turret.head.displayWidth,origin:v.sprite.originY};
}),vehicle);
try {
 await page.goto(base+'/tests/fixtures/turret-aim.html?tower='+vehicle);
 await page.waitForFunction(()=>window.aimScene?.visuals.size===6);
 await page.waitForTimeout(700);
 await page.evaluate(()=>aimScene.navigate(800,600,1.5));await page.waitForTimeout(700);
 const initial=await sample();
 assert.deepEqual(initial.map(v=>v.hull),[1,2,3].map(level=>`${vehicle}-hull-${level}`));
 const hullHeight=vehicle==='artillery'?.875:.75;
 assert.ok(initial.every(v=>v.width===68&&v.height===68*hullHeight&&v.hitWidth===68&&v.hitHeight===68&&v.headWidth===(vehicle==='artillery'?85:68)&&v.origin===(.89-.25)/hullHeight));
 const detail=await page.evaluate(vehicle=>[1,2,3].flatMap(level=>['turret','hull'].map(part=>{
  const texture=aimScene.textures.get(vehicle+'-'+part+'-'+level),ctx=texture.getSourceImage().getContext('2d');
  let clearEdges=true;
  for(let i=0;i<32;i++) {
   const f=texture.get(i);
   for(const [x,y,w,h] of [[f.cutX,f.cutY,f.width,1],[f.cutX,f.cutY+f.height-1,f.width,1],[f.cutX,f.cutY,1,f.height],[f.cutX+f.width-1,f.cutY,1,f.height]]) {
    const data=ctx.getImageData(x,y,w,h).data;
    for(let p=3;p<data.length;p+=4)if(data[p])clearEdges=false;
   }
  }
  return {level,part,width:texture.get(0).width,clearEdges};
 })),vehicle);
 assert.ok(detail.every(v=>v.width>=256&&v.clearEdges),JSON.stringify(detail));
 report.checks.push({name:'Three approved hulls retain 68px gameplay bounds and sharp directional gun frames',detail});
 // Save the real baked frames beside the approved sprites for visual review.
 const comparison=await page.evaluate(async(vehicle)=>{
  const canvas=document.createElement('canvas');canvas.width=1350;canvas.height=1200;
  const ctx=canvas.getContext('2d');ctx.fillStyle='#cbd1b9';ctx.fillRect(0,0,1350,1200);
  ctx.fillStyle='#243024';ctx.font='24px sans-serif';
  ctx.fillText('Approved '+vehicle+' artwork',24,38);ctx.fillText('In-game rotating assembly',24,528);
  for(let level=1;level<=3;level++) {
   const x=(level-1)*450;
   const image=new Image();image.src='/assets/woodland/'+vehicle+(level>1?'-lv'+level:'')+'.png';await image.decode();
   ctx.drawImage(image,x+25,55,400,400);
   const rootX=x+225,rootY=vehicle==='artillery'?1070:1000;
   for(const part of ['hull','turret']) {
    const texture=aimScene.textures.get(vehicle+'-'+part+'-'+level),f=texture.get(3);
    const scale=440/(part==='turret'&&vehicle==='artillery'?f.width/1.25:f.width);
    const mountX=vehicle==='artillery'?-4.5:-2.2;
    const offset=part==='turret'?{x:mountX*Math.cos(3/32*Math.PI*2)*440/94,y:mountX*Math.sin(3/32*Math.PI*2)*.55*440/94}:{x:0,y:0};
    const origin=part==='hull'?(.89-.25)/(vehicle==='artillery'?.875:.75):vehicle==='artillery'?1.14:.89/.75;
    ctx.drawImage(texture.getSourceImage(),f.cutX,f.cutY,f.width,f.height,
     rootX-f.width*scale/2+offset.x,rootY-f.height*scale*origin+offset.y,f.width*scale,f.height*scale);
   }
  }
  return canvas.toDataURL('image/png').split(',')[1];
 },vehicle);
 await fs.writeFile(new URL('barrel-comparison.png',out),Buffer.from(comparison,'base64'));
 const directions=[];
 for(const direction of [0,4,8,12,15,1]) {
  await page.evaluate(d=>setTargets(d),direction);await page.waitForTimeout(750);
  const actual=await sample();
  assert.ok(actual.every((v,i)=>v.error<.01&&v.x===initial[i].x&&v.y===initial[i].y&&v.angle===0),JSON.stringify(actual));
  directions.push({direction,frames:actual.map(v=>v.frame)});
  if(direction%4===0)await page.screenshot({path:new URL(`direction-${direction}.png`,out).pathname});
 }
 report.checks.push({name:'All levels aim in every quadrant independently of the chassis',directions});
 await page.evaluate(()=>{
  window.launched=[];
  const launch=aimScene.launchShot.bind(aimScene);
  aimScene.launchShot=(actor,target,duration,muzzle)=>{launched.push({id:actor.data.id,muzzle,
   ground:{x:actor.root.x,y:actor.root.y},flip:actor.sprite.flipX,yaw:actor.turret.yaw});return launch(actor,target,duration,muzzle)};
  for(const v of aimScene.visuals.values())if(v.turret)v.turret.yaw-=Math.PI;
  aimScene.playLiveEvents([0,1,2].map(i=>({type:'UNIT_ATTACKED',attacker_id:'mg'+i,target_entity_id:'enemy'+i,damage:5})));
 });
 await page.waitForTimeout(70);assert.equal(await page.evaluate(()=>launched.length),0);
 await page.waitForFunction(()=>launched.length===3);
 const shots=await page.evaluate(()=>launched);
 assert.ok(shots.every(s=>s.muzzle&&s.muzzle.y<s.ground.y-10));
 await page.waitForFunction(()=>[...aimScene.visuals.values()].some(v=>v.turret?.recoil>.1));
 report.checks.push({name:'Live shots turn before firing, originate at the scaled muzzle and recoil independently',shots});
 // Legacy replay receives only events, rather than an authoritative target ID.
 await page.evaluate(()=>{setTower('mg0',{simulation_state:undefined});aimScene.playCombatEvents([{type:'UNIT_ATTACKED',unit_id:'mg0',target_entity_id:'enemy0',damage:5}])});
 await page.waitForFunction(()=>launched.length===4);await page.waitForTimeout(900);
 report.checks.push({name:'Legacy vehicle attacks aim and fire without tilting the hull'});
 // Exercise real MotionTrack interpolation in both directions while firing right.
 await page.evaluate(()=>{window.originalRoots=[0,1,2].map(i=>aimScene.visuals.get('mg'+i).root);setTargets(0);moveTanks(0)});
 await page.waitForTimeout(750);
 const motion=[];
 for(const offset of [18,36,54,36,18,0,-18,-36]) {
  await page.evaluate(x=>moveTanks(x),offset);await page.waitForTimeout(140);
  motion.push(await sample());
 }
 await page.waitForTimeout(300);
 const reversed=await sample();
 assert.ok(reversed.every(v=>!v.flipped&&!v.headFlipped&&Math.cos(v.bodyYaw)<-.99&&Math.cos(v.yaw)>.99&&v.error<.01),JSON.stringify(reversed));
 assert.ok(motion.some(state=>state[0].x>initial[0].x+20)&&reversed[0].x<initial[0].x-20);
 assert.ok(await page.evaluate(()=>originalRoots.every((root,i)=>aimScene.visuals.get('mg'+i).root===root)));
 const count=await page.evaluate(()=>launched.length);
 await page.evaluate(()=>aimScene.playLiveEvents([{type:'UNIT_ATTACKED',attacker_id:'mg0',target_entity_id:'enemy0',damage:5}]));
 await page.waitForFunction(n=>launched.length===n+1,count);
 const reverseShot=await page.evaluate(()=>launched.at(-1));
 assert.ok(!reverseShot.flip&&reverseShot.muzzle.x>reverseShot.ground.x&&reverseShot.muzzle.y<reverseShot.ground.y);
 await page.screenshot({path:new URL('reverse-and-aim.png',out).pathname});
 report.checks.push({name:'Reversing travel rotates the chassis through 180 degrees while the gun still fires right',reversed});
 const route=[[-36,-48],[12,-96],[60,-96],[108,-48],[108,0],[60,48],[12,48],[-36,0]];
 const chassisDirections=[];let previous={x:-36,y:0};
 for(const [x,y] of route) {
  const expected=Math.atan2((y-previous.y)/.55,x-previous.x);
  await page.evaluate(p=>moveTanks(p.x,p.y),{x,y});await page.waitForTimeout(800);
  const state=await sample();
  assert.ok(state.every(v=>Math.abs(Math.atan2(Math.sin(expected-v.bodyYaw),Math.cos(expected-v.bodyYaw)))<.015&&v.error<.02&&!v.flipped&&v.angle===0),JSON.stringify({expected,state}));
  chassisDirections.push({offset:{x,y},expected,bodyFrames:state.map(v=>v.bodyFrame)});
  await page.screenshot({path:new URL(`drive-${chassisDirections.length}.png`,out).pathname});
  previous={x,y};
 }
 assert.equal(new Set(chassisDirections.map(v=>v.bodyFrames[0])).size,8);
 const stopped=await sample();await page.waitForTimeout(350);
 assert.deepEqual((await sample()).map(v=>v.bodyYaw),stopped.map(v=>v.bodyYaw));
 report.checks.push({name:'Chassis follows all eight projected movement directions and retains its heading when stopped',chassisDirections});
 await page.evaluate(()=>{const v=aimScene.visuals.get('mg0');window.savedRoot=v.root;window.savedHead=v.turret.head;window.savedYaw=v.turret.yaw;window.savedDriveYaw=v.drive.yaw;window.savedBodyFrame=v.sprite.frame.name;setTower('mg0',{level:3})});
 assert.ok(await page.evaluate(vehicle=>{const v=aimScene.visuals.get('mg0');return v.root===savedRoot&&v.turret.head===savedHead&&v.turret.yaw===savedYaw&&v.drive.yaw===savedDriveYaw&&v.sprite.frame.name===savedBodyFrame&&v.turret.head.texture.key===vehicle+'-turret-3'&&v.sprite.texture.key===vehicle+'-hull-3'&&!v.sprite.flipX},vehicle));
 report.checks.push({name:'Upgrading retains object identity, heading, chassis direction and collision bounds'});
 // Base targets are a separate server target namespace; no whole-body recoil.
 await page.evaluate(()=>setTower('mg0',{simulation_state:{...aimScene.visuals.get('mg0').data.simulation_state,attack_target_id:'base:b',combat_state:'ATTACKING'}}));
 await page.waitForFunction(()=>{const v=aimScene.visuals.get('mg0'),b=aimScene.bases.get('b'),p=v.turret.mountPoint();if(!b)return false;const expected=Math.atan2((b.y-p.y)/.55,b.x-p.x);return Math.abs(Math.atan2(Math.sin(expected-v.turret.yaw),Math.cos(expected-v.turret.yaw)))<.01});
 const baseCount=await page.evaluate(()=>launched.length);
 await page.evaluate(()=>aimScene.playLiveEvents([{type:'BASE_DAMAGED',unit_id:'mg0',target_team_id:'b',hp_damage:5}]));
 await page.waitForFunction(n=>launched.length===n+1,baseCount);
 assert.equal(await page.evaluate(()=>aimScene.visuals.get('mg0').sprite.angle),0);
 report.checks.push({name:'Vehicles acquire enemy bases and fire from their barrel without rocking the chassis'});
 // Replay movement must use the same heading logic as live interpolation.
 await page.evaluate(()=>{
  aimScene.playCombatEvents([{type:'UNIT_MOVED',unit_id:'mg0',to_node:'target-0-8'}]);
  aimScene.updateState({...aimScene.state,liveBattle:false,entities:aimScene.state.entities.map(e=>e.id==='mg0'
   ?{...e,current_node_id:'target-0-8',simulation_state:{formation_order:0,attack_target_id:'enemy0',combat_state:'ATTACKING'}}:e)});
 });
 await page.waitForFunction(()=>{const v=aimScene.visuals.get('mg0'),node=aimScene.nodes.get('target-0-8');return Math.abs(v.root.x-node.worldX)<.1&&Math.abs(v.root.y-node.worldY)<.1&&Math.abs(Math.atan2(Math.sin(v.drive.yaw-Math.PI),Math.cos(v.drive.yaw-Math.PI)))<.01});
 assert.equal(await page.evaluate(()=>aimScene.visuals.get('mg0').sprite.flipX),false);
 report.checks.push({name:'Legacy UNIT_MOVED replay rotates the chassis toward the movement vector'});
 // A dead target cancels a queued shot instead of spawning a stale projectile.
 const cancelledCount=await page.evaluate(()=>launched.length);
 await page.evaluate(()=>{
  const v=aimScene.visuals.get('mg2');v.turret.yaw-=Math.PI;
  aimScene.playLiveEvents([{type:'UNIT_ATTACKED',attacker_id:'mg2',target_entity_id:'enemy2',damage:5}]);
  aimScene.updateState({...aimScene.state,entities:aimScene.state.entities.filter(e=>e.id!=='enemy2')});
  setTower('mg1',{status:'DISABLED'});window.disabledYaw=aimScene.visuals.get('mg1').turret.yaw;
 });
 await page.waitForTimeout(950);
 assert.equal(await page.evaluate(()=>launched.length),cancelledCount);
 assert.ok(await page.evaluate(()=>{const v=aimScene.visuals.get('mg1');return v.turret.yaw===disabledYaw&&!v.turret.flash.visible}));
 await page.evaluate(()=>{window.removedHead=aimScene.visuals.get('mg0').turret.head;aimScene.updateState({...aimScene.state,entities:aimScene.state.entities.filter(e=>e.id!=='mg0')})});
 assert.equal(await page.evaluate(()=>!aimScene.visuals.has('mg0')&&!removedHead.scene),true);
 report.checks.push({name:'Disabled vehicles stop aiming, dead targets cancel pending shots and destruction releases the turret'});
 await page.goto(base+'/tests/fixtures/game-item-cards.html');await page.waitForFunction(()=>typeof renderCards==='function');
 for(const level of [1,2,3]) {
  await page.evaluate(level=>renderCards(level),level);
  await page.waitForFunction(({level,vehicle})=>{const img=document.querySelector('img[src*="/'+vehicle+'"]');return img?.complete&&img.naturalWidth===512&&img.src.endsWith(vehicle+(level>1?'-lv'+level:'')+'.png')},{level,vehicle});
 }
 await page.screenshot({path:new URL('picker-level-3.png',out).pathname});
 await page.goto(base+'/tests/fixtures/turret-aim.html?tower='+vehicle+'&panel');await page.waitForFunction(()=>typeof renderLevel==='function');
 for(const level of [1,2,3]) {
  await page.evaluate(level=>renderLevel(level),level);
  await page.waitForFunction(({level,vehicle})=>{const images=[...document.querySelectorAll('.team-upgrade-panel img')];return images.length===(level<3?2:1)&&images.every(img=>img.complete&&img.naturalWidth===512)&&images[0].src.endsWith(vehicle+(level>1?'-lv'+level:'')+'.png')},{level,vehicle});
 }
 await page.screenshot({path:new URL('upgrade-level-3.png',out).pathname});
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>renderLevel(1));
 await page.waitForFunction(()=>document.querySelectorAll('.entity-illustration[data-state="ready"]').length===2);
 assert.ok(await page.locator('.team-upgrade-panel').evaluate(el=>el.getBoundingClientRect().right<=innerWidth&&el.scrollWidth<=innerWidth));
 await page.screenshot({path:new URL('upgrade-mobile.png',out).pathname});
 report.checks.push({name:'Army cards and upgrade dialogs show the three approved vehicle images on desktop and mobile'});
 assert.deepEqual(report.errors,[]);assert.deepEqual(report.failures,[]);
 report.status='PASS';console.log(JSON.stringify(report,null,2));
}catch(e){report.status='FAIL';report.failure=String(e.stack||e);await page.screenshot({path:new URL('failure.png',out).pathname}).catch(()=>{});throw e;}
finally{await fs.writeFile(new URL('browser-qa.json',out),JSON.stringify(report,null,2));await browser.close();}
