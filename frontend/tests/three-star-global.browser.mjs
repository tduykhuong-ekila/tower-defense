import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';

const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5198';
const [room]=JSON.parse(await fs.readFile('/private/tmp/roadside-stars-rooms.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
const report={status:'RUNNING',layouts:[],selection:[],overlays:[]};
async function open(join=room.join) {
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
 await page.goto(base);await page.evaluate(value=>localStorage.setItem('grid-room',JSON.stringify(value)),{...room,join});
 await page.goto(base+'/tests/fixtures/grid-placement.html');
 await page.waitForFunction(()=>window.gridScene?.visuals.size>=10&&window.gridStore?.getState().connectionStatus==='connected');
 return {context,page};
}
try {
 const owner=await open(),enemy=await open(room.joins[1]);
 const level3=await owner.page.evaluate(()=>[...gridScene.visuals.values()].filter(v=>v.data.unit_code==='cannon_tower'&&v.data.team_id===gridScene.state.myTeamId).map(v=>({level:v.data.level,texture:v.stars.texture.key,sprite:v.sprite.texture.key,hpY:v.hp.y,starsY:v.stars.y})));
 assert.ok(level3.length>0&&level3.every(v=>v.level===3&&v.texture==='upgrade-stars-3'&&v.sprite.includes('-lv3')&&v.starsY===-42));
 report.overlays.push({type:'cannon',level:3,cachedTexture:true,equipment:true});
 const codes=['infantry','tank','artillery','cannon_tower','mg_tower','shield_generator'];
 for(const code of codes) {
  const id=await owner.page.evaluate(code=>[...gridScene.visuals.values()].find(v=>v.data.unit_code===code&&v.data.team_id===gridScene.state.myTeamId)?.data.id,code);
  assert.ok(id,`entity ${code}`);
  await owner.page.evaluate(id=>gridScene.callbacks.onEntityClick(id,false),id);
  if(code!=='cannon_tower') {
   await owner.page.locator('.upgrade-button').click();
   await owner.page.locator(`.team-upgrade-panel h3[data-upgrade-type="${code}"]`).waitFor();
   const stars=owner.page.locator('.team-upgrade-panel h3 .unit-level-stars').first();
   assert.equal(await stars.locator('svg').count(),1);
   await owner.page.getByRole('button',{name:'Đóng nâng cấp'}).click();
  } else assert.equal(await owner.page.locator('.upgrade-button').isDisabled(),true);
  report.selection.push(code);
  await owner.page.evaluate(id=>gridScene.callbacks.onEntityInspect(id,500,300,false),id);
  await owner.page.locator('.entity-info-card .unit-level-stars').waitFor();
  assert.equal(await owner.page.locator('.entity-info-card .unit-level-stars').getAttribute('data-level'),code==='cannon_tower'?'3':'1');
  await owner.page.evaluate(()=>gridScene.callbacks.onEntityInspect(null,0,0));
 }
 const tank=await owner.page.evaluate(()=>[...gridScene.visuals.values()].find(v=>v.data.unit_code==='tank'&&v.data.team_id===gridScene.state.myTeamId).data.id);
 await owner.page.evaluate(id=>{window.savedTankRoot=gridScene.visuals.get(id).root},tank);
 for(const level of [2,3]) {
  await owner.page.evaluate(id=>gridScene.callbacks.onEntityClick(id,false),tank);
  await owner.page.locator('.upgrade-button').click();
  await owner.page.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).click();
  await owner.page.getByRole('button',{name:/Xác nhận ·/}).click();
  await owner.page.waitForFunction(({id,level})=>gridScene.visuals.get(id)?.data.level===level,{id:tank,level});
  assert.equal(await owner.page.evaluate(id=>gridScene.visuals.get(id).stars.texture.key,tank),`upgrade-stars-${level}`);
  await enemy.page.waitForFunction(({id,level})=>gridStore.getState().entities.find(e=>e.id===id)?.level===level,{id:tank,level});
  assert.equal(await enemy.page.evaluate(()=>gridStore.getState().teamUpgradeLevels[gridStore.getState().currentTeamId]?.tank||1),1);
  await owner.page.getByRole('button',{name:'Đóng nâng cấp'}).click();
 }
 // Object identity in the scene is checked inside one browser process.
 assert.equal(await owner.page.evaluate(id=>gridScene.visuals.get(id).root===window.savedTankRoot,tank),true);
 await owner.context.close();await enemy.context.close();
 const modal=await browser.newPage();
 await modal.goto(base);await modal.evaluate(value=>localStorage.setItem('grid-room',JSON.stringify(value)),room);
 await modal.goto(base+'/tests/fixtures/grid-placement.html?panel');
 await modal.locator('.team-upgrade-panel article').waitFor();
 for(const viewport of [{width:1440,height:1000},{width:390,height:844},{width:844,height:390}]) {
  await modal.setViewportSize(viewport);
  const frames=[];
  for(const level of [1,2,3]) {
   await modal.evaluate(level=>renderLevel(level),level);
   await modal.waitForFunction(level=>document.querySelector('.team-upgrade-panel h3 .unit-level-stars')?.dataset.level===String(level),level);
   const frame=await modal.locator('.team-upgrade-panel').boundingBox();
   const footer=await modal.locator('.team-upgrade-footer').boundingBox();
   frames.push([frame.y,frame.height,footer.y,footer.height]);
   assert.equal(await modal.locator('.team-upgrade-panel h3 .unit-level-stars').first().locator('svg').count(),level);
   if(level===3) {
    assert.equal(await modal.getByRole('button',{name:'NÂNG CẤP TOÀN ĐỘI',exact:true}).count(),0);
    assert.ok((await modal.locator('.team-upgrade-panel').innerText()).includes('CẤP TỐI ĐA'));
   }
  }
  assert.ok(frames.every(frame=>JSON.stringify(frame)===JSON.stringify(frames[0])),JSON.stringify({viewport,frames}));
  await modal.screenshot({path:new URL(`../../docs/qa/three-star-modal-${viewport.width}.png`,import.meta.url).pathname});
  report.layouts.push({viewport,stable:true,levels:[1,2,3]});
 }
 await modal.close();
 report.status='PASS';
} catch(error) {report.status='FAIL';report.failure=String(error?.stack||error);throw error;}
finally {await fs.writeFile(new URL('../../docs/qa/three-star-global-browser.json',import.meta.url),JSON.stringify(report,null,2));await browser.close();}
console.log(JSON.stringify(report));
