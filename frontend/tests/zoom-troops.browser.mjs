import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const {chromium} = createRequire(import.meta.url)('playwright');
const browser = await chromium.launch({headless: true, channel: 'chrome'});
const page = await browser.newPage({viewport: {width: 1200, height: 800}});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(`${process.env.TEST_BASE_URL || 'http://127.0.0.1:5191'}/tests/fixtures/infantry-rifle.html`);
  await page.waitForFunction(() => window.rifleScene?.visuals.size === 12);
  await page.evaluate(() => {
    const scene = window.rifleScene, source = scene.state.entities[0];
    const origin = source.simulation_state.world_position;
    const entities = Array.from({length: 99}, (_, i) => ({...source, id: `zoom-${i}`,
      unit_code: ['infantry', 'tank', 'artillery'][i % 3], level: 1,
      simulation_state: {formation_order: i, world_position: {
        x: origin.x + (i % 11) * 24, y: origin.y + Math.floor(i / 11) * 28,
      }, movement_state: 'MOVING', combat_state: 'IDLE'},
    }));
    scene.updateState({...scene.state, entities});
    scene.zoomController.setLimits(0.1, 2);
    scene.zoomController.moveTo(800, 580, 0.25, true);
  });
  await page.waitForTimeout(400);
  const before = await page.evaluate(() => [...rifleScene.visuals.values()].map(v => ({
    id: v.data.id, x: v.root.x, y: v.root.y, visible: v.root.visible,
  })));
  assert.equal(before.length, 99);
  assert.ok(before.every(v => v.visible), 'All units, including vehicles beyond the old per-node cap, stay visible');
  for (let tick = 0; tick < 8; tick++) {
    await page.waitForTimeout(80);
    await page.evaluate(() => {
      const scene = rifleScene;
      scene.updateState({...scene.state, entities: scene.state.entities.map(e => ({...e,
        simulation_state: {...e.simulation_state, world_position: {
          x: e.simulation_state.world_position.x + 4,
          y: e.simulation_state.world_position.y,
        }},
      }))});
    });
  }
  await page.waitForTimeout(350);
  const result = await page.evaluate(() => ({zoom: rifleScene.cameras.main.zoom,
    units: [...rifleScene.visuals.values()].map(v => ({id: v.data.id, x: v.root.x, y: v.root.y,
      visible: v.root.visible, paused: v.sprite.anims.isPaused, code: v.data.unit_code})),
    counters: rifleScene.children.list.filter(o => o.type === 'Text' && o.getData('count') !== undefined).length,
  }));
  assert.equal(result.zoom, 0.25);
  for (const unit of result.units) {
    const old = before.find(v => v.id === unit.id);
    assert.ok(unit.visible && Math.hypot(unit.x - old.x, unit.y - old.y) > 1, `${unit.id} moves at overview zoom`);
    if (unit.code === 'infantry') assert.equal(unit.paused, false);
  }
  assert.equal(result.counters, 0);
  assert.deepEqual(errors, []);
  console.log('PASS: 99 infantry/tanks/artillery remain visible and moving at zoom 0.25; no numeric counters.');
} finally {
  await browser.close();
}
