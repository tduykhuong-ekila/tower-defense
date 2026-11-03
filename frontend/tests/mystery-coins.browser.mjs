import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const { chromium } = createRequire(import.meta.url)('playwright');
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const teammate = await context.newPage();
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5186';
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const evidence = {};
const amounts = [20, 25, 30, 40, 60];
const odds = amounts.map((amount, index) => ({ amount, probability_percent: [15, 20, 35, 25, 5][index] }));
async function api(path, data, token, host = false) {
  const response = await page.request.fetch(base + '/api/v1' + path, {
    method: data === undefined ? 'GET' : 'POST',
    ...(data === undefined ? {} : { data }),
    headers: token ? { [host ? 'X-Host-Token' : 'X-Participant-Token']: token } : {},
  });
  assert.ok(response.ok(), await response.text());
  return response.json();
}
try {
  await page.goto(base);
  const match = await api('/matches/', { name: 'Mystery coin browser QA', configuration: { initial_coins: 1000 } });
  const teams = [], joins = [];
  for (let i = 0; i < 2; i++) {
    teams.push(await api(`/matches/${match.id}/teams/`, { name: `Coin team ${i}` }, match.host_token, true));
    joins.push(await api(`/matches/${match.id}/join/`, { display_name: `Player ${i}`, team_id: teams[i].id, role: 'MENTEE' }));
  }
  const third = await api(`/matches/${match.id}/join/`, { display_name: 'Teammate', team_id: teams[0].id, role: 'MENTEE' });
  for (const team of teams) await api(`/matches/${match.id}/teams/${team.id}/ready/`, { is_ready: true }, match.host_token, true);
  await api(`/matches/${match.id}/start/`, {}, match.host_token, true);
  const room = { match, a: joins[0], b: joins[1], c: third };
  await page.evaluate(room => localStorage.setItem('full-gameplay-test-room', JSON.stringify(room)), room);
  await page.goto(base + '/tests/fixtures/full-gameplay.html?view=a');
  await teammate.goto(base + '/tests/fixtures/full-gameplay.html?view=c');
  const token = joins[0].participant_token;
  const current = () => api(`/matches/${match.id}/questions/current/`, undefined, token);
  const teamState = () => api(`/matches/${match.id}/teams/${teams[0].id}/state/`, undefined, token);
  async function openAndAnswer() {
    await page.getByRole('button', { name: /^(Mở câu hỏi tri thức|Xem kết quả câu hỏi)$/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Câu hỏi tri thức' });
    const text = await dialog.innerText();
    await dialog.getByPlaceholder('Nhập câu trả lời hoặc kết quả giải mã...').fill(text.includes('2 + 2') ? '4' : '6');
    await dialog.getByRole('button', { name: 'Xác Nhận Nộp Bài' }).click();
    await page.getByRole('button', { name: 'Mở túi coin · 20–60', exact: true }).waitFor();
    const q = await current();
    assert.equal(q.reward_options.coin_amount, null);
    assert.deepEqual(q.reward_options.coin_distribution, odds);
    return q;
  }
  const q = await openAndAnswer();
  await page.getByText('Xem tỷ lệ nhận coin', { exact: true }).click();
  for (const row of odds) await page.getByRole('row', { name: `${row.amount} ${row.probability_percent}%`, exact: true }).waitFor();
  await page.screenshot({ path: new URL('../../docs/qa/mystery-coins-desktop.png', import.meta.url).pathname });
  // Close/reload/reconnect retain the sealed entitlement and never reveal its draw.
  await page.getByRole('button', { name: 'Đóng phần thưởng', exact: true }).click();
  await page.goto(base + '/tests/fixtures/full-gameplay.html?view=a');
  await page.getByRole('button', { name: 'Nhận phần thưởng', exact: true }).click();
  assert.equal((await current()).id, q.id);
  assert.equal((await current()).reward_options.coin_amount, null);
  const before = (await teamState()).team.coins;
  const claimResponse = page.waitForResponse(response => response.url().endsWith('/rewards/claim/') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Mở túi coin · 20–60', exact: true }).click();
  await page.getByRole('heading', { name: 'Đang mở túi coin...' }).waitFor();
  const claim = await (await claimResponse).json();
  assert.ok(amounts.includes(claim.coin_amount));
  await page.getByText(`+${claim.coin_amount} coin`, { exact: true }).waitFor();
  assert.equal((await teamState()).team.coins, before + claim.coin_amount);
  await page.screenshot({ path: new URL('../../docs/qa/mystery-coins-reveal.png', import.meta.url).pathname });
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  await page.locator('.reward-overlay').waitFor({ state: 'hidden' });
  const duplicate = await api(`/matches/${match.id}/rewards/claim/`, { team_question_id: q.id, reward_type: 'COIN', idempotency_key: crypto.randomUUID() }, third.participant_token);
  assert.equal(duplicate.id, claim.id);
  assert.equal(duplicate.coin_amount, claim.coin_amount);
  assert.equal((await teamState()).team.coins, before + claim.coin_amount);
  await teammate.waitForFunction(value => document.querySelector('.kingdom-resources .gold')?.textContent.includes(String(value)), before + claim.coin_amount);
  evidence.realClaim = { amount: claim.coin_amount, before, after: before + claim.coin_amount, teammateDuplicateSafe: true, reloadStayedSealed: true };
  // The alternate free unlock remains available after a coin claim.
  await openAndAnswer();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByText('Xem tỷ lệ nhận coin', { exact: true }).click();
  await page.screenshot({ path: new URL('../../docs/qa/mystery-coins-mobile.png', import.meta.url).pathname });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.getByRole('button', { name: /Chọn Đơn Vị Mở Khóa/ }).click();
  await page.locator('.unlock-card').filter({ hasText: 'Xe tăng' }).click();
  const beforeUnlock = (await teamState()).team.coins;
  await page.getByRole('button', { name: 'Xác Nhận Mở Khóa Đơn Vị', exact: true }).click();
  await page.locator('.reward-overlay').waitFor({ state: 'hidden' });
  const unlocked = await teamState();
  assert.equal(unlocked.team.coins, beforeUnlock);
  evidence.freeUnlock = true;
  // Deterministic visual check for the rare 60-coin result using the real modal.
  await page.goto(base + '/tests/fixtures/mystery-coins.html');
  await page.getByRole('button', { name: 'Mở túi coin · 20–60', exact: true }).click();
  await page.getByRole('heading', { name: 'May mắn!', exact: true }).waitFor();
  await page.getByText('+60 coin', { exact: true }).waitFor();
  assert.equal(await page.locator('.coin-bag-reveal.jackpot').count(), 1);
  await page.screenshot({ path: new URL('../../docs/qa/mystery-coins-jackpot.png', import.meta.url).pathname });
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  await page.locator('.reward-overlay').waitFor({ state: 'hidden' });
  evidence.jackpotFixture = { amount: 60, earlyEventPreservedReveal: true };
  assert.deepEqual(errors, []);
  evidence.pageErrors = errors;
  await fs.writeFile(new URL('../../docs/qa/mystery-coins-browser.json', import.meta.url), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence));
} catch (error) {
  console.error('Page errors:', errors);
  await page.screenshot({ path: '/tmp/mystery-coins-failure.png' });
  throw error;
} finally {
  await browser.close();
}
