import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const { chromium } = createRequire(import.meta.url)('playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5177';
const audit = process.env.AUDIT_BEFORE === '1';
const output = new URL(`../../docs/qa/spawn-tower-realtime-${audit ? 'before' : 'browser'}.json`, import.meta.url);
const report = { status: 'RUNNING', audit, scenarios: [], errors: [] };
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'] });
const request = await browser.newContext();
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function api(path, data, token, host = false) {
  const response = await request.request.fetch(base + '/api/v1' + path, { method: data === undefined ? 'GET' : 'POST', ...(data === undefined ? {} : { data }), headers: token ? { [host ? 'X-Host-Token' : 'X-Participant-Token']: token } : {} });
  assert.ok(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}
async function room(count) {
  const match = await api('/matches/', { name: `Spawn tower realtime QA ${count}`, configuration: { max_teams: count, max_active_units_per_team: 30, initial_coins: 5000, total_rounds: 3, first_preparation_duration_seconds: 300, preparation_duration_seconds: 300, battle_duration_seconds: 300, movement_baseline_round_seconds: 5 } });
  const teams = [], joins = [];
  for (let i = 0; i < count; i++) {
    const team = await api(`/matches/${match.id}/teams/`, { name: `Team ${i + 1}` }, match.host_token, true);
    teams.push(team);
    joins.push(await api(`/matches/${match.id}/join/`, { display_name: `Player ${i + 1}`, team_id: team.id, role: 'MENTEE' }));
    await api(`/matches/${match.id}/teams/${team.id}/ready/`, { is_ready: true }, match.host_token, true);
  }
  return { match, teams, joins };
}
const host = (r, action) => api(`/matches/${r.match.id}/${action}/`, {}, r.match.host_token, true);
const buy = (r, i, key = crypto.randomUUID()) => api(`/matches/${r.match.id}/actions/deploy/`, { unit_type_code_or_id: 'infantry', target_team_id: r.teams[(i + 1) % r.teams.length].id, idempotency_key: key }, r.joins[i].participant_token);
const build = (r, i, slot, key = crypto.randomUUID()) => api(`/matches/${r.match.id}/actions/build/`, { unit_type_code_or_id: 'mg_tower', node_id: `node_tower_t${i + 1}_slot${slot}`, idempotency_key: key }, r.joins[i].participant_token);
async function client(r, i, lobby = false) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage(), frames = [], latencies = [];
  page.setDefaultTimeout(15000);
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('websocket', socket => socket.on('framereceived', ({ payload }) => {
    try { const event = JSON.parse(payload.toString()); frames.push(event); if (event.server_timestamp) latencies.push(Date.now() - Date.parse(event.server_timestamp)); } catch {}
  }));
  // Hold only the lazily imported battle page, leaving the existing lobby socket subscribed.
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  if (lobby) await page.route('**/src/pages/BattlePage.tsx*', async route => { await gate; await route.continue(); });
  await page.goto(base);
  await page.evaluate(data => localStorage.setItem('spawn-room', JSON.stringify(data)), { ...r, join: r.joins[i], lobby });
  await page.goto(base + '/tests/fixtures/spawn-realtime.html');
  if (lobby) await page.waitForFunction(() => window.flowSocketClient?.getStatus() === 'connected');
  else await ready({ page });
  return { context, page, frames, latencies, release };
}
async function ready(c) { await c.page.waitForFunction(() => window.flowScene?.callbacks && window.flowStore?.getState().connectionStatus === 'connected'); }
async function see(c, id) { await c.page.waitForFunction(id => flowScene.visuals.has(id) && flowStore.getState().entities.some(e => e.id === id), id); }
function normalized(entities) {
  return entities.map(e => ({ id: e.id, team: e.team_id, code: e.unit_code, hp: e.current_hp, shield: e.current_shield, status: e.status, node: e.current_node_id, target: e.target_team_id, position: e.simulation_state?.world_position, zone: e.simulation_state?.movement_zone, moving: e.simulation_state?.movement_state, combat: e.simulation_state?.combat_state, attack_target: e.simulation_state?.attack_target_id, cooldown: e.simulation_state?.attack_remaining })).sort((a, b) => a.id.localeCompare(b.id));
}
async function agree(r, clients) {
  const snapshot = await api(`/matches/${r.match.id}/snapshot/`), expected = normalized(snapshot.payload.entities);
  for (const c of clients) {
    await c.page.waitForFunction(seq => flowStore.getState().lastSequenceNumber >= seq, snapshot.sequence_number);
    await c.page.waitForFunction(ids => ids.length === flowScene.visuals.size && ids.every(id => flowScene.visuals.has(id)), expected.map(e => e.id));
    const local = await c.page.evaluate(() => flowStore.getState().entities);
    assert.deepEqual(normalized(local), expected);
  }
  return { version: snapshot.sequence_number, entities: expected.length, divergent_entities: 0 };
}
async function towerBattle(count) {
  const r = await room(count);
  await host(r, 'start');
  const a = await client(r, 0), b = await client(r, 1);
  try {
    const target = (await build(r, 1, 3)).entity;
    const troops = [];
    for (let i = 0; i < 5; i++) troops.push((await buy(r, 0)).entity);
    await Promise.all([see(a, target.id), see(b, target.id)]);
    await host(r, 'advance-phase');
    const destroyed = c => c.frames.some(f => f.event_type === 'COMBAT_TICK' && f.payload.events.some(e => e.type === 'ENTITY_DESTROYED' && e.entity_id === target.id));
    const started = Date.now();
    while ((!destroyed(a) || !destroyed(b)) && Date.now() - started < 60000) await wait(150);
    await host(r, 'pause'); await wait(400);
    assert.ok(destroyed(a) && destroyed(b), 'Infantry did not destroy the enemy tower on both clients');
    const hits = c => c.frames.flatMap(f => f.event_type === 'COMBAT_TICK' ? f.payload.events : []).filter(e => e.type === 'UNIT_ATTACKED' && e.target_entity_id === target.id);
    assert.deepEqual(hits(a), hits(b));
    assert.equal(hits(a).length, 20);
    assert.ok(hits(a).every(e => e.damage === 5));
    for (const c of [a, b]) assert.equal(await c.page.evaluate(id => flowScene.visuals.has(id), target.id), false);
    const independent = a.frames.filter(f => f.event_type === 'COMBAT_TICK' &&
      f.payload.entity_updates.some(e => e.simulation_state?.combat_state === 'ATTACKING' && e.simulation_state?.movement_state === 'STOPPED') &&
      f.payload.entity_updates.some(e => e.simulation_state?.movement_state === 'MOVING'));
    assert.ok(independent.length, 'No simultaneous stationary attacker and moving follower');
    const final = await agree(r, [a, b]);
    if (count === 4) await a.page.screenshot({ path: new URL('../../docs/qa/spawn-tower-realtime.png', import.meta.url).pathname });
    return { tower_hits: hits(a).length, towers_destroyed: 1, simultaneous_movement_frames: independent.length, elapsed_ms: Date.now() - started, final };
  } finally { await a.context.close(); await b.context.close(); await host(r, 'end'); }
}
try {
  for (const count of audit ? [4] : (process.env.TEAM_COUNTS || '4,8,20').split(',').map(Number)) {
    const r = await room(count), a = await client(r, 0, true), scenario = { teams: count, checks: [], action_latency_ms: [] };
    report.scenarios.push(scenario);
    let b;
    try {
      await host(r, 'start');
      await a.page.waitForURL('**/battle/**');
      const duringNavigation = await buy(r, 1);
      await wait(150);
      a.release(); await ready(a);
      if (audit) {
        await wait(700);
        scenario.reused_lobby_socket_missing_opponent = await a.page.evaluate(id => !flowStore.getState().entities.some(e => e.id === id), duringNavigation.entity.id);
        assert.equal(scenario.reused_lobby_socket_missing_opponent, true);
        // The player's own action runs requestSync, explaining the apparent action-order dependency.
        await a.page.evaluate(() => flowSocketClient.requestSync()); await see(a, duringNavigation.entity.id);
        scenario.own_sync_recovers_missing_opponent = true;
        continue;
      }
      await see(a, duringNavigation.entity.id);
      scenario.checks.push('lobby-to-battle socket reuse recovers opponent created while lazy page loads');
      b = await client(r, 1);
      // Both orders, with more than one deployment each and both tower builders.
      for (const order of [[0, 1], [1, 0]]) for (const i of order) {
        const start = Date.now(), result = await buy(r, i);
        await Promise.all([see(a, result.entity.id), see(b, result.entity.id)]);
        scenario.action_latency_ms.push(Date.now() - start);
      }
      for (const i of [0, 1]) {
        const tower = await build(r, i, 1);
        await Promise.all([see(a, tower.entity.id), see(b, tower.entity.id)]);
      }
      scenario.checks.push('A-first and B-first deployment and tower construction reach both sprites without reload');
      const own = await api(`/matches/${r.match.id}/teams/${r.teams[0].id}/state/`, undefined, r.joins[0].participant_token);
      const before = new Map(own.entities.filter(e => e.entity_kind === 'UNIT').map(e => [e.id, e.simulation_state.world_position]));
      for (let i = before.size; i < 5; i++) await buy(r, 0);
      const gathered = await api(`/matches/${r.match.id}/teams/${r.teams[0].id}/state/`, undefined, r.joins[0].participant_token);
      const troops = gathered.entities.filter(e => e.entity_kind === 'UNIT');
      assert.equal(troops.length, 5); assert.ok(troops.every(e => e.max_hp === 100 && e.simulation_state.staging_entry_distance === 0));
      for (const [id, position] of before) assert.deepEqual(troops.find(e => e.id === id).simulation_state.world_position, position);
      scenario.checks.push('five individually visible troops share one rally entry; later deployments preserve earlier positions');
      await host(r, 'advance-phase');
      const key = crypto.randomUUID(), retries = await Promise.all([buy(r, 0, key), buy(r, 0, key)]);
      assert.equal(retries[0].entity.id, retries[1].entity.id);
      await Promise.all([see(a, retries[0].entity.id), see(b, retries[0].entity.id)]);
      const liveTower = await build(r, 1, 2);
      await Promise.all([see(a, liveTower.entity.id), see(b, liveTower.entity.id)]);
      await a.page.evaluate(target => flowSocketClient.setTarget(target), r.teams[count - 1].id);
      for (const c of [a, b]) await c.page.waitForFunction(({ owner, target }) => flowStore.getState().entities.filter(e => e.team_id === owner && e.entity_kind === 'UNIT').every(e => e.target_team_id === target), { owner: r.teams[0].id, target: r.teams[count - 1].id });
      // Restore attack destination after verifying public retarget/formation updates.
      await a.page.evaluate(target => flowSocketClient.setTarget(target), r.teams[1].id);
      for (const c of [a, b]) await c.page.waitForFunction(({ owner, target }) => flowStore.getState().entities.filter(e => e.team_id === owner && e.entity_kind === 'UNIT').every(e => e.target_team_id === target), { owner: r.teams[0].id, target: r.teams[1].id });
      scenario.checks.push('Battle deployment retries create one entity; live build and retarget synchronize both ways');
      await host(r, 'pause'); await wait(350);
      scenario.before_recovery = await agree(r, [a, b]);
      await a.context.setOffline(true);
      await a.page.evaluate(() => flowSocketClient.ws?.close(4000, 'QA offline'));
      await host(r, 'resume');
      const offlineUnit = await buy(r, 1), offlineTower = await build(r, 1, 3);
      const reconnectAt = Date.now();
      await a.context.setOffline(false); await a.page.evaluate(() => window.dispatchEvent(new Event('online')));
      await see(a, offlineUnit.entity.id); await see(a, offlineTower.entity.id);
      scenario.reconnect_ms = Date.now() - reconnectAt;
      const subsequent = await buy(r, 1); await see(a, subsequent.entity.id);
      scenario.checks.push('offline client restores missed entities and continues receiving subsequent opponent actions');
      // Omit one real tick while later ticks arrive; recover automatically from the version gap.
      await a.page.evaluate(() => {
        const socket = flowSocketClient.ws, receive = socket.onmessage;
        window.heldTick = null;
        socket.onmessage = event => { const e = JSON.parse(event.data); if (!window.heldTick && e.event_type === 'COMBAT_TICK') { window.heldTick = event; return; } receive.call(socket, event); };
        window.deliverHeldTick = () => receive.call(socket, window.heldTick);
      });
      await a.page.waitForFunction(() => window.heldTick);
      await wait(500);
      const version = await a.page.evaluate(() => flowStore.getState().lastSequenceNumber);
      await a.page.evaluate(() => window.deliverHeldTick());
      assert.ok(await a.page.evaluate(() => flowStore.getState().lastSequenceNumber) >= version);
      await host(r, 'pause'); await wait(350);
      scenario.after_recovery = await agree(r, [a, b]);
      scenario.checks.push('missed/out-of-order tick repairs automatically without rollback or duplicate sprites');
      await host(r, 'resume'); await host(r, 'advance-phase');
      for (const i of [1, 0]) { const result = await buy(r, i); await Promise.all([see(a, result.entity.id), see(b, result.entity.id)]); }
      scenario.checks.push('bidirectional deployments still work after next major round');
      await host(r, 'pause'); await wait(350);
      scenario.final = await agree(r, [a, b]);
      for (const [name, c] of [['a', a], ['b', b]]) {
        const times = c.latencies.sort((x, y) => x - y);
        scenario[`client_${name}`] = { frames: c.frames.length, delivery_p95_ms: times[Math.floor(times.length * .95)] };
      }
    } finally {
      a.release(); await a.context.close(); await b?.context.close(); await host(r, 'end');
    }
    if (!audit) {
      scenario.combat = await towerBattle(count);
      scenario.checks.push('five Infantry attack and destroy enemy tower; both clients receive identical hits, independent movement, HP and removal');
      console.log(`PASS ${count} teams`);
    }
  }
  assert.deepEqual(report.errors, []); report.status = 'PASS';
} catch (error) { report.status = 'FAIL'; report.error = String(error); throw error; }
finally { await fs.writeFile(output, JSON.stringify(report, null, 2)); console.log(JSON.stringify(report, null, 2)); await browser.close(); }
