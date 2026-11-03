// Actual Excel upload form and three independent React/Phaser clients.
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {openCoinBag} from './helpers/coin-bag.mjs';
const { chromium } = createRequire(import.meta.url)('playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5187';
const sample = new URL('../../backend/tests/fixtures/De_Thi_Quiz_Demo.xlsx', import.meta.url).pathname;
const output = new URL('../../docs/qa/question-bank-browser.json', import.meta.url);
const report = { checks: [], errors: [] };
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--disable-background-timer-throttling', '--disable-renderer-backgrounding'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const hostPage = await context.newPage();
let match;
const clients = [];
async function api(path, data, token, host = false) {
  const response = await context.request.fetch(base + '/api/v1' + path, {
    method: data === undefined ? 'GET' : 'POST', ...(data === undefined ? {} : { data }),
    headers: token ? { [host ? 'X-Host-Token' : 'X-Participant-Token']: token } : {},
  });
  assert.ok(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}
async function client(join) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage(), frames = [];
  page.setDefaultTimeout(20000);
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('websocket', socket => socket.on('framereceived', ({ payload }) => {
    try { frames.push(JSON.parse(payload.toString())); } catch {}
  }));
  await page.goto(base);
  await page.evaluate(data => localStorage.setItem('spawn-room', JSON.stringify(data)), { match, join });
  await page.goto(base + '/tests/fixtures/spawn-realtime.html');
  await page.waitForFunction(() => window.flowScene?.callbacks && window.flowStore?.getState().connectionStatus === 'connected' && window.flowStore.getState().currentQuestion?.id);
  const result = { ctx, page, frames }; clients.push(result); return result;
}
const own = token => api(`/matches/${match.id}/questions/current/`, undefined, token);
async function choose(page, key = 'B') {
  await page.getByRole('button', { name: /^(Mở câu hỏi tri thức|Câu hỏi tiếp theo)$/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Câu hỏi tri thức' });
  await dialog.getByRole('button', { name: new RegExp(`^${key}\\.`) }).click();
  await dialog.getByRole('button', { name: 'Xác Nhận Nộp Bài' }).click();
  await page.locator('.reward-overlay').waitFor();
}
try {
  await hostPage.goto(base);
  await hostPage.getByRole('button', { name: /Tạo phòng đấu/ }).click();
  await hostPage.getByLabel('Tệp ngân hàng câu hỏi').setInputFiles({ name: 'invalid.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('bad xlsx') });
  await hostPage.getByRole('button', { name: 'Kiểm tra & xem trước' }).click();
  await hostPage.getByRole('alert').filter({ hasText: /Không đọc được/ }).waitFor();
  assert.equal(await hostPage.getByRole('button', { name: 'Khởi tạo phòng chờ' }).isDisabled(), true);
  await hostPage.getByLabel('Tệp ngân hàng câu hỏi').setInputFiles(sample);
  await hostPage.getByRole('button', { name: 'Kiểm tra & xem trước' }).click();
  await hostPage.getByText('20 câu hợp lệ · 0 câu lỗi', { exact: true }).waitFor();
  await hostPage.getByRole('button', { name: 'Sau', exact: true }).click();
  await hostPage.getByText('Trang 2/2', { exact: true }).waitFor();
  await hostPage.getByRole('checkbox').check();
  await hostPage.getByLabel('Maximum Teams').selectOption('4');
  await hostPage.screenshot({ path: new URL('../../docs/qa/question-bank-upload.png', import.meta.url).pathname });
  const created = hostPage.waitForResponse(r => r.url().endsWith('/api/v1/matches/') && r.request().method() === 'POST');
  await hostPage.getByRole('button', { name: 'Khởi tạo phòng chờ' }).click();
  match = await (await created).json();
  assert.ok(match.id && match.host_token && match.question_bank_id);
  report.checks.push('Invalid upload reports error; replacement validates 20 real questions; paginated host preview and confirmed room attachment.');
  const teams = [], joins = [];
  for (let i = 0; i < 2; i++) {
    const team = await api(`/matches/${match.id}/teams/`, { name: `Quiz Team ${i + 1}` }, match.host_token, true); teams.push(team);
    joins.push(await api(`/matches/${match.id}/join/`, { display_name: `Player ${i + 1}`, team_id: team.id, role: 'MENTEE' }));
    await api(`/matches/${match.id}/teams/${team.id}/ready/`, { is_ready: true }, match.host_token, true);
  }
  const mate = await api(`/matches/${match.id}/join/`, { display_name: 'Teammate', team_id: teams[0].id, role: 'MENTEE' });
  await api(`/matches/${match.id}/start/`, {}, match.host_token, true);
  await hostPage.close();
  const a = await client(joins[0]), b = await client(joins[1]), teammate = await client(mate);
  const first = await own(joins[0].participant_token);
  assert.equal(first.sequence_number, 1); assert.ok(!JSON.stringify(first).includes('answer_key'));
  // Open during Preparation; the exact pending question survives entry to Battle.
  await a.page.getByRole('button', { name: /^(Mở câu hỏi tri thức|Câu hỏi tiếp theo)$/ }).click();
  const chosen = a.page.getByRole('dialog', { name: 'Câu hỏi tri thức' }).getByRole('button', { name: /^B\./ });
  await chosen.click();
  const chosenStyle = await chosen.getAttribute('style');
  await api(`/matches/${match.id}/advance-phase/`, {}, match.host_token, true);
  await a.page.waitForFunction(() => flowStore.getState().match?.phase === 'WAR');
  assert.equal((await own(joins[0].participant_token)).id, first.id);
  const deployment = await api(`/matches/${match.id}/actions/deploy/`, { unit_type_code_or_id: 'infantry', target_team_id: teams[1].id, idempotency_key: crypto.randomUUID() }, joins[0].participant_token);
  await a.page.waitForFunction(id => flowScene.visuals.has(id), deployment.entity.id);
  const state = () => a.page.evaluate(id => ({
    tick: flowStore.getState().lastSequenceNumber,
    position: flowStore.getState().entities.find(e => e.id === id)?.simulation_state?.world_position,
    scene: flowScene.scene.isActive(),
  }), deployment.entity.id);
  const before = await state();
  await a.page.waitForTimeout(4600);
  const after = await state();
  assert.ok(after.tick > before.tick && after.scene);
  assert.notDeepEqual(after.position, before.position);
  assert.equal(await a.page.getByRole('dialog', { name: 'Câu hỏi tri thức' }).isVisible(), true);
  assert.equal(await chosen.getAttribute('style'), chosenStyle);
  await a.page.screenshot({ path: new URL('../../docs/qa/question-bank-during-battle.png', import.meta.url).pathname });
  const actionsBefore = await a.page.evaluate(() => flowStore.getState().entities.length);
  await a.page.getByRole('dialog', { name: 'Câu hỏi tri thức' }).getByRole('button', { name: /^B\./ }).click();
  assert.equal(await a.page.evaluate(() => flowStore.getState().entities.length), actionsBefore);
  await a.page.getByRole('button', { name: 'Xác Nhận Nộp Bài' }).click();
  await a.page.locator('.reward-overlay').waitFor();
  await teammate.page.waitForFunction(() => flowStore.getState().currentQuestion?.status === 'PENDING_REWARD');
  const coinsBefore = await a.page.evaluate(() => flowStore.getState().coins);
  const receipt = await openCoinBag(a.page);
  await a.page.waitForFunction(n => flowStore.getState().coins === n, coinsBefore + receipt.coin_amount);
  await teammate.page.waitForFunction(n => flowStore.getState().coins === n, coinsBefore + receipt.coin_amount);
  assert.equal(await b.page.evaluate(() => flowStore.getState().questionProgress.answered), 0);
  assert.ok(!b.frames.some(e => e.event_type === 'QUESTION_ANSWERED_CORRECT' && e.payload.team_id === teams[0].id));
  report.checks.push('Preparation question survives Battle; open modal preserves troop movement, live clock and active Phaser scene; teammates share a single mystery coin reward; other team remains independent.');
  await choose(b.page);
  await openCoinBag(b.page);
  await b.page.waitForFunction(() => flowStore.getState().questionProgress.answered === 1 && !flowStore.getState().pendingReward);
  // Reload preserves the completed question; explicitly request the next imported question.
  await a.page.reload();
  await a.page.locator('.connection-dot.connected').waitFor();
  await a.page.getByRole('button', { name: /^(Mở câu hỏi tri thức|Câu hỏi tiếp theo)$/ }).click();
  await a.page.getByText('THỬ THÁCH CHIẾN LƯỢC #2 / 20', { exact: true }).waitFor();
  await a.page.getByRole('button', { name: 'Đóng câu hỏi', exact: true }).first().click();
  assert.equal((await api(`/matches/${match.id}/questions/progress/`, undefined, joins[0].participant_token)).total, 20);
  await api(`/matches/${match.id}/advance-phase/`, {}, match.host_token, true);
  await a.page.waitForFunction(() => document.querySelector('.round-standard h1')?.textContent.includes('02'));
  await choose(a.page);
  await openCoinBag(a.page);
  await a.page.locator('.reward-overlay').waitFor({ state: 'hidden' });
  assert.equal((await api(`/matches/${match.id}/questions/progress/`, undefined, joins[0].participant_token)).answered, 2);
  await a.page.getByText('2/20', { exact: true }).waitFor();
  await a.page.waitForTimeout(1700);
  report.checks.push('Different teams answer independently after Host disconnect; refresh preserves progress and explicit Next opens the next imported question and total; second-round answer and reward preserve history.');
  await a.page.screenshot({ path: new URL('../../docs/qa/question-bank-battle.png', import.meta.url).pathname });
  await api(`/matches/${match.id}/end/`, {}, match.host_token, true);
  const finished = await context.request.post(`${base}/api/v1/matches/${match.id}/questions/${first.id}/answer/`, { data: { answer: 'B' }, headers: { 'X-Participant-Token': joins[0].participant_token } });
  assert.equal(finished.status(), 400);
  assert.deepEqual(report.errors, []);
  report.status = 'PASS';
} catch (error) {
  report.status = 'FAIL'; report.failure = String(error.stack || error);
  for (const [i, c] of clients.entries()) await c.page.screenshot({ path: `/private/tmp/question-bank-failure-${i}.png` }).catch(() => {});
  await hostPage.screenshot({ path: '/private/tmp/question-bank-host-failure.png' }).catch(() => {});
  throw error;
} finally {
  await fs.writeFile(output, JSON.stringify(report, null, 2));
  await browser.close();
}
