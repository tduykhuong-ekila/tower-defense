import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveAttackTarget } from '../src/game/defaultAttackTarget';

const teams = (count: number) => Array.from({length: count}, (_, i) => ({
  id: `team-${i + 1}`, status: 'ACTIVE',
}));

test('initial targets form a ring with one attacker per opponent', () => {
  for (const count of [2, 3, 4, 8, 20]) {
    const roster = teams(count);
    const targets = roster.map(team => resolveAttackTarget(roster, team.id, ''));
    assert.deepEqual(targets, [...roster.slice(1), roster[0]].map(team => team.id));
    assert.equal(new Set(targets).size, count);
  }
});

test('manual selections survive team updates', () => {
  const roster = teams(4);
  assert.equal(resolveAttackTarget(roster, 'team-2', 'team-1'), 'team-1');
  assert.equal(resolveAttackTarget([...roster], 'team-2', 'team-4'), 'team-4');
});

test('invalid selections rotate to the next active opponent', () => {
  const roster = teams(4);
  roster[2].status = 'ELIMINATED';
  for (const selected of ['', 'team-2', 'team-3', 'missing']) {
    assert.equal(resolveAttackTarget(roster, 'team-2', selected), 'team-4');
  }
  assert.equal(resolveAttackTarget(roster, 'team-4', ''), 'team-1');
});

test('waits for assignment and handles having no opponents', () => {
  assert.equal(resolveAttackTarget(teams(3), null, ''), '');
  assert.equal(resolveAttackTarget(teams(3), 'missing', 'team-1'), '');
  assert.equal(resolveAttackTarget([], 'team-1', ''), '');
  assert.equal(resolveAttackTarget(teams(1), 'team-1', ''), '');
  const roster = teams(2);
  roster[1].status = 'ELIMINATED';
  assert.equal(resolveAttackTarget(roster, 'team-1', 'team-2'), '');
});
