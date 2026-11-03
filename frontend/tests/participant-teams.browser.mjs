// Run against a disposable backend database and the current frontend source.
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const { chromium } = createRequire(import.meta.url)('playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5199';
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const contexts = [];
const errors = [];
const scenarios = [];
async function page(viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport, permissions: ['clipboard-read', 'clipboard-write'] });
  contexts.push(context);
  const p = await context.newPage();
  p.on('pageerror', error => errors.push(error.message));
  return p;
}
async function ownTeam(p, name) {
  await p.waitForFunction(name => [...document.querySelectorAll('.lobby-team-card.is-my-team')]
    .some(card => card.textContent.includes(name)), name);
  return p.locator('.lobby-team-card.is-my-team');
}
async function invitation(p) {
  await p.locator('.lobby-team-card.is-my-team').getByRole('button', { name: 'Mời vào đội', exact: true }).click();
  const url = await p.getByLabel('Liên kết mời vào đội').inputValue();
  await p.getByRole('button', { name: 'Sao chép lời mời', exact: true }).click();
  await p.getByRole('button', { name: 'Đã sao chép!' }).waitFor();
  assert.equal(await p.evaluate(() => navigator.clipboard.readText()), url);
  await p.keyboard.press('Escape');
  assert.equal(await p.getByRole('dialog').count(), 0);
  return url;
}
async function assertLobbyCannotCreate(p, match) {
  assert.equal(await p.getByRole('button', { name: /Tạo đội của tôi|Thêm nhanh đội|Tạo đội đầu tiên|^Thêm đội$/ }).count(), 0);
  const token = await p.evaluate(() => sessionStorage.tower_participant_token);
  for (const path of ['teams', 'join']) {
    const result = await p.request.post(`${base}/api/v1/matches/${match.id}/${path}/`, {
      headers: { 'X-Participant-Token': token },
      data: path === 'teams' ? { name: 'Blocked lobby team' }
        : { display_name: 'Already joined', new_team_name: 'Blocked join replay' },
    });
    assert.equal(result.status(), 403);
  }
}
try {
  const a = await page();
  const response = await a.request.post(base + '/api/v1/matches/', {
    data: { name: 'Participant teams QA', configuration: { max_teams: 4, max_players_per_team: 2 } },
  });
  assert.equal(response.status(), 201);
  const match = await response.json();

  await a.goto(`${base}/join?code=${match.room_code}`);
  await a.getByLabel('TÊN HIỂN THỊ').fill('Mentee tạo đội');
  await a.getByLabel('CHỌN ĐỘI GIA NHẬP').selectOption('new');
  await a.getByLabel('TÊN ĐỘI MỚI').fill('Rồng Lửa');
  await a.screenshot({ path: '../docs/qa/participant-team-create.png', fullPage: true });
  await a.getByRole('button', { name: 'Vào Phòng Chờ', exact: true }).click();
  await ownTeam(a, 'Rồng Lửa');
  assert.equal((await a.evaluate(() => JSON.parse(sessionStorage.tower_active_member))).role, 'MENTEE');
  scenarios.push('Mentee creates and joins a team from an empty room');

  await assertLobbyCannotCreate(a, match);
  const url = await invitation(a);
  scenarios.push('Mentee has no lobby creation controls; both team API and join replay reject creation; invitations remain available');

  const b = await page({ width: 390, height: 844 });
  await b.goto(url);
  const target = new URL(url).searchParams.get('team');
  await b.waitForFunction(target => document.querySelector('#join-team')?.value === target, target);
  await b.getByLabel('TÊN HIỂN THỊ').fill('Mentor được mời');
  await b.getByRole('button', { name: 'Mentor Cố vấn' }).click();
  await b.getByRole('button', { name: 'Vào Phòng Chờ', exact: true }).click();
  await ownTeam(b, 'Rồng Lửa');
  assert.equal((await b.evaluate(() => JSON.parse(sessionStorage.tower_active_member))).role, 'MENTOR');
  await b.locator('.lobby-team-card.is-my-team').getByRole('button', { name: 'Đội đã đầy', exact: true }).waitFor();
  await assertLobbyCannotCreate(b, match);
  scenarios.push('Mobile mentor follows an invitation and joins the selected team; full team disables invitation');

  const mentor = await page();
  await mentor.goto(`${base}/join?code=${match.room_code}`);
  await mentor.getByLabel('TÊN HIỂN THỊ').fill('Mentor tạo đội');
  await mentor.getByRole('button', { name: 'Mentor Cố vấn' }).click();
  await mentor.getByLabel('CHỌN ĐỘI GIA NHẬP').selectOption('new');
  await mentor.getByLabel('TÊN ĐỘI MỚI').fill('Đội Mentor');
  await mentor.getByRole('button', { name: 'Vào Phòng Chờ', exact: true }).click();
  await ownTeam(mentor, 'Đội Mentor');
  await assertLobbyCannotCreate(mentor, match);
  const mentorUrl = await invitation(mentor);
  scenarios.push('Mentor creates a team only during initial join; lobby controls and APIs block further creation; invitations work');

  const c = await page();
  await c.goto(mentorUrl);
  await c.waitForFunction(id => document.querySelector('#join-team')?.value === id, new URL(mentorUrl).searchParams.get('team'));
  await c.getByRole('button', { name: 'Mentor Cố vấn' }).click();
  assert.equal(await c.getByRole('button', { name: 'Vào Phòng Chờ', exact: true }).isDisabled(), true);
  await c.getByRole('button', { name: 'Mentee Chiến binh' }).click();
  await c.getByLabel('TÊN HIỂN THỊ').fill('Mentee được mời');
  await c.getByRole('button', { name: 'Vào Phòng Chờ', exact: true }).click();
  await ownTeam(c, 'Đội Mentor');
  scenarios.push('Invitation prevents a second mentor and accepts a mentee');

  await b.screenshot({ path: '../docs/qa/participant-team-mobile.png', fullPage: true });
  const invalid = await page();
  await invalid.goto(`${base}/join?code=${match.room_code}&team=00000000-0000-0000-0000-000000000000`);
  await invalid.getByText('Đội trong lời mời không còn tồn tại.', { exact: false }).waitFor();
  assert.equal(await invalid.getByLabel('CHỌN ĐỘI GIA NHẬP').inputValue(), '');
  scenarios.push('Invalid invitation explicitly warns and leaves team choice to the recipient');

  const host = await page();
  await host.goto(base);
  await host.evaluate(token => sessionStorage.setItem('tower_host_token', token), match.host_token);
  await host.goto(`${base}/lobby/${match.id}?host=1`);
  await host.getByRole('button', { name: 'Thêm nhanh đội', exact: true }).click();
  await host.getByPlaceholder('Ví dụ: Đội Rồng Lửa').fill('Đội Host');
  await host.getByRole('button', { name: 'Tạo Đội', exact: true }).click();
  await host.getByRole('heading', { name: /Đội Host/ }).waitFor();
  const saved = await (await host.request.get(`${base}/api/v1/matches/${match.id}/`)).json();
  assert.equal(saved.teams.length, 3);
  assert.equal(saved.all_members.length, 4);
  scenarios.push('Host can still create teams from lobby; rejected participant requests leave no extra teams or members');
  assert.deepEqual(errors, []);
  await fs.writeFile('../docs/qa/participant-teams-browser.json', JSON.stringify({ status: 'PASSED', scenarios, errors }, null, 2));
  console.log(JSON.stringify({ status: 'PASSED', scenarios, errors }, null, 2));
} finally {
  await Promise.all(contexts.map(context => context.close()));
  await browser.close();
}
