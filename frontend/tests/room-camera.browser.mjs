// Run against the dev frontend + an isolated backend. No production game hooks.
// NODE_PATH may point to the bundled runtime's node_modules for Playwright.
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const { chromium } = createRequire(import.meta.url)('playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5174';
const browser = await chromium.launch({ headless: true, channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, hasTouch: true });
page.setDefaultTimeout(12000);
const errors = [];
page.on('pageerror', e => { errors.push(e.message); console.error('Browser error:', e.message); });
async function api(path, data, host) {
  const response = await page.request.fetch(`${base}/api/v1${path}`, {
    method: data === undefined ? 'GET' : 'POST',
    ...(data === undefined ? {} : {data}), headers: host ? {'X-Host-Token':host} : {}
  });
  assert.ok(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}
try {
  await page.goto(base);
  await page.getByRole('button', { name: /TẠO PHÒNG|Tạo Phòng|Tạo phòng/i }).first().click();
  const maximum = page.getByRole('combobox', { name: 'Maximum Teams' });
  await maximum.waitFor();
  await page.waitForFunction(() => !document.querySelector('[aria-label="Maximum Teams"]').disabled);
  assert.equal(await maximum.inputValue(), '4');
  assert.equal(await maximum.locator('option').count(), 19);
  assert.equal(await page.getByLabel('Số đội tối thiểu').count(), 0);
  await maximum.selectOption('20');
  const createResponse = page.waitForResponse(r=>r.url().endsWith('/api/v1/matches/') && r.request().method()==='POST');
  await page.getByRole('button', {name:'Khởi tạo phòng chờ'}).click();
  const room=await (await createResponse).json();
  assert.equal(room.configuration.max_teams,20);
  assert.equal(room.configuration.min_teams,2);
  await page.waitForURL(/lobby/);
  await page.getByText('Teams: 0 / 20', {exact: true}).waitFor();
  console.log('PASS create form');
  const teams=[];
  for(let i=0;i<6;i++) {
    const t=await api(`/matches/${room.id}/teams/`,{name:`Solo ${i+1}`},room.host_token);
    await api(`/matches/${room.id}/join/`,{display_name:`Player ${i+1}`,team_id:t.id,role:'MENTEE'});
    await api(`/matches/${room.id}/teams/${t.id}/ready/`,{is_ready:true},room.host_token);
    teams.push(t);
  }
  await page.reload();
  await page.getByRole('button',{name:/BẮT ĐẦU TRẬN ĐẤU/}).waitFor();
  assert.ok(await page.getByRole('button',{name:/BẮT ĐẦU TRẬN ĐẤU/}).isEnabled());
  console.log('PASS solo lobby');
  await page.getByRole('button',{name:/BẮT ĐẦU TRẬN ĐẤU/}).click();
  await page.waitForURL(/battle/);
  await page.locator('canvas').waitFor();
  await page.getByRole('button', {name:'Phóng to',exact:true}).waitFor();
  await page.getByRole('button', {name:'Thu nhỏ',exact:true}).waitFor();
  await page.screenshot({path:'/tmp/tower-room-camera-battle.png'});
  // Use the real rendering scene with a synthetic visual tower; map comes from backend.
  await page.goto(`${base}/tests/fixtures/camera.html?match=${room.id}`);
  await page.waitForFunction(()=>window.fixture?.scene.visuals.has('test-tower'));
  console.log('PASS scene loaded');
  await page.waitForTimeout(700);
  await page.evaluate(()=>{
    const s=fixture.scene,c=s.cameras.main,v=s.visuals.get('test-tower').root;
    s.navigate(v.x,v.y,1); return {x:v.x,y:v.y};
  });
  await page.waitForTimeout(600);
  const authoritativeBefore = await page.evaluate(()=>JSON.stringify(fixture.state));
  // Real wheel input: target changes immediately, actual zoom converges over frames.
  const anchor={x:740,y:350};
  await page.mouse.move(anchor.x,anchor.y);
  const before=await page.evaluate(a=>{
    const c=fixture.scene.cameras.main; const p=c.getWorldPoint(a.x,a.y);return {x:p.x,y:p.y,z:c.zoom};
  },anchor);
  await page.mouse.wheel(0,-100);
  await page.waitForTimeout(500);
  const after=await page.evaluate(a=>{const c=fixture.scene.cameras.main,p=c.getWorldPoint(a.x,a.y);return {x:p.x,y:p.y,z:c.zoom};},anchor);
  assert.ok(after.z>before.z);
  assert.ok(Math.hypot(after.x-before.x,after.y-before.y)<0.05,'cursor world anchor');
  // Both buttons share the target and defer actual zoom until scene updates.
  for (const id of ['in','out']) {
    const change=await page.evaluate(id=>{const s=fixture.scene,c=s.cameras.main,before=c.zoom;
      document.getElementById(id).click();return {before,after:c.zoom,target:s.zoomController.targetZoom};},id);
    assert.equal(change.before,change.after);assert.notEqual(change.target,change.after);
    await page.waitForTimeout(350);
  }
  // Pinch uses real touch events and must never turn into a selection click.
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:true});
  const pinchBefore=await page.evaluate(()=>({z:fixture.scene.zoomController.targetZoom,n:fixture.selected.length}));
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:500,y:450,id:1},{x:700,y:450,id:2}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:495,y:450,id:1},{x:705,y:450,id:2}]});
  await page.waitForTimeout(50);
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:460,y:450,id:1},{x:740,y:450,id:2}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await page.waitForTimeout(400);
  const pinchAfter=await page.evaluate(()=>({z:fixture.scene.cameras.main.zoom,n:fixture.selected.length}));
  assert.ok(pinchAfter.z>pinchBefore.z);assert.equal(pinchAfter.n,pinchBefore.n);
  await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:false});
  // Repeated input never creates camera tweens and stays clamped.
  await page.evaluate(()=>{for(let i=0;i<80;i++)fixture.scene.input.emit('wheel',{x:640,y:450},[],0,i%2?100:-100);});
  await page.waitForTimeout(500);
  const bounds=await page.evaluate(()=>{const s=fixture.scene,c=s.cameras.main;return {z:c.zoom,min:s.fitZoom,max:Math.max(1.5,s.fitZoom*2.7),tweens:s.tweens.getTweensOf(c).length};});
  assert.ok(bounds.z>=bounds.min && bounds.z<=bounds.max);assert.equal(bounds.tweens,0);
  // Hit testing in actual Phaser after zoom, and during ongoing interpolation.
  for (const moving of [false,true]) {
    await page.evaluate(()=>{const s=fixture.scene,v=s.visuals.get('test-tower').root;s.navigate(v.x,v.y,1);});
    await page.waitForTimeout(500);
    if(moving)await page.evaluate(()=>fixture.scene.zoomIn());
    const point=await page.evaluate(()=>{
      const c=fixture.scene.cameras.main,v=fixture.scene.visuals.get('test-tower').root;
      return {x:c.x+c.width/2+(v.x-c.scrollX-c.width/2)*c.zoom,
        y:c.y+c.height/2+(v.y-25-c.scrollY-c.height/2)*c.zoom};
    });
    const selectionsBefore = await page.evaluate(()=>fixture.selected.length);
    await page.mouse.click(point.x,point.y);
    assert.equal(await page.evaluate(()=>fixture.selected.length),selectionsBefore+1);
    assert.equal(await page.evaluate(()=>fixture.selected.at(-1)),'test-tower');
  }
  await page.evaluate(()=>fixture.scene.focusBase(fixture.state.teams[0].id));
  await page.waitForTimeout(500);
  const basePoint=await page.evaluate(()=>{const c=fixture.scene.cameras.main,b=fixture.scene.bases.get(fixture.state.teams[0].id);
    return {x:c.x+c.width/2+(b.x-c.scrollX-c.width/2)*c.zoom,
      y:c.y+c.height/2+(b.y-55-c.scrollY-c.height/2)*c.zoom,id:fixture.state.teams[0].id};
  });
  const baseSelectionsBefore=await page.evaluate(()=>fixture.selected.length);
  await page.mouse.click(basePoint.x,basePoint.y);
  assert.equal(await page.evaluate(()=>fixture.selected.length),baseSelectionsBefore+1);
  assert.equal(await page.evaluate(()=>fixture.selected.at(-1)),basePoint.id);
  // Drag still moves camera and cannot select a tower.
  await page.evaluate(()=>fixture.scene.navigate(fixture.scene.world.centerX,fixture.scene.world.centerY,1.2));
  await page.waitForTimeout(500);
  const dragBefore=await page.evaluate(()=>({x:fixture.scene.cameras.main.scrollX,n:fixture.selected.length}));
  await page.mouse.move(640,500);await page.mouse.down();await page.mouse.move(740,540,{steps:10});await page.mouse.up();
  const dragAfter=await page.evaluate(()=>({x:fixture.scene.cameras.main.scrollX,n:fixture.selected.length}));
  assert.ok(Math.abs(dragAfter.x-dragBefore.x)>30);assert.equal(dragAfter.n,dragBefore.n);
  await page.locator('#fit').click();await page.waitForTimeout(650);
  const fit=await page.evaluate(async()=>{const {overviewCamera}=await import('/src/game/map.ts');const s=fixture.scene,c=s.cameras.main,o=overviewCamera(c.width,c.height,s.world);return {z:c.zoom,target:o.zoom,x:c.scrollX+c.width/2,y:c.scrollY+c.height/2,tx:o.centerX,ty:o.centerY};});
  assert.ok(Math.abs(fit.z-fit.target)<0.0001);assert.ok(Math.hypot(fit.x-fit.tx,fit.y-fit.ty)<0.1);
  assert.equal(await page.evaluate(()=>JSON.stringify(fixture.state)), authoritativeBefore);
  // A server HP update during zoom changes rendering state, never camera targets or nodes.
  const reconciliation=await page.evaluate(()=>{const s=fixture.scene;
    s.zoomIn();const target=s.zoomController.targetZoom;
    const nodes=JSON.stringify(fixture.state.mapData.nodes);
    s.updateState({...fixture.state,entities:fixture.state.entities.map(e=>({...e,current_hp:75}))});
    return {target,after:s.zoomController.targetZoom,hp:s.visuals.get('test-tower').data.current_hp,
      sameNodes:nodes===JSON.stringify(fixture.state.mapData.nodes)};
  });
  assert.equal(reconciliation.target,reconciliation.after);assert.equal(reconciliation.hp,75);assert.ok(reconciliation.sameNodes);
  // Shutdown removes our listeners; scene input plugin clears remaining Phaser handlers.
  const cleanup=await page.evaluate(()=>{const s=fixture.scene;fixture.game.scene.stop('BattleScene');return {wheel:s.input.listenerCount('wheel'),move:s.input.listenerCount('pointermove')};});
  assert.equal(cleanup.wheel,0);assert.equal(cleanup.move,0);
  // Phone fit handles arenas smaller than the viewport and keeps all bounds valid.
  await page.setViewportSize({width:390,height:844});
  await page.goto(`${base}/tests/fixtures/camera.html?match=${room.id}`);
  await page.waitForFunction(()=>window.fixture?.scene.visuals.has('test-tower'));
  await page.waitForTimeout(500);
  await page.evaluate(()=>fixture.scene.fit());
  await page.waitForTimeout(650);
  const mobile=await page.evaluate(()=>{const s=fixture.scene,c=s.cameras.main;return {z:c.zoom,target:s.fitZoom,
    x:c.scrollX,y:c.scrollY,cx:c.clampX(c.scrollX),cy:c.clampY(c.scrollY)};});
  assert.ok(Math.abs(mobile.z-mobile.target)<0.0001);assert.equal(mobile.x,mobile.cx);assert.equal(mobile.y,mobile.cy);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',checks:['create dropdown 2–20/default 4','6 solo teams start in room of 20','visible battle zoom controls','real Phaser wheel anchor','rapid input/clamps/no camera tweens','tower and base selection during and after zoom','buttons and real pinch','drag','smooth desktop/phone fit with HUD bounds','authoritative state preserved during zoom and HP updates','listener cleanup'],cursorError:Math.hypot(after.x-before.x,after.y-before.y)},null,2));
} finally { await browser.close(); }
