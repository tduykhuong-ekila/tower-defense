import test from 'node:test';
import assert from 'node:assert/strict';
import { teamInvitationUrl, teamJoinIssue } from '../src/game/teamJoining';
import type { Team } from '../src/types/match';

test('team invitation contains only the room and team, without host credentials', () => {
  const url = new URL(teamInvitationUrl('https://game.example', 'ABC234', 'team-123'));
  assert.equal(url.pathname, '/join');
  assert.deepEqual([...url.searchParams], [['code', 'ABC234'], ['team', 'team-123']]);
});

test('full teams block both roles; a mentor slot remains independent of mentee capacity', () => {
  const team = { members: [{ role: 'MENTOR' }, { role: 'MENTEE' }] } as Team;
  assert.equal(teamJoinIssue(team, 'MENTEE', 2), 'Đội đã đầy');
  assert.equal(teamJoinIssue(team, 'MENTOR', 2), 'Đội đã đầy');
  assert.equal(teamJoinIssue(team, 'MENTOR', 4), 'Đội đã có Mentor');
  assert.equal(teamJoinIssue(team, 'MENTEE', 4), null);
  assert.equal(teamJoinIssue({ members: [] } as unknown as Team, 'MENTOR', 4), null);
});
