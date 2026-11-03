import test from 'node:test';
import assert from 'node:assert/strict';
import { attackTargetInfo } from '../src/game/attackTarget';
import type { EntityState } from '../src/stores/matchStore';
import type { RenderTeam } from '../src/game/bridge';

const enemy: EntityState = {
  id: 'enemy-tank', team_id: 'b', team_name: 'Đội cũ', unit_code: 'tank', unit_name: 'Tank',
  entity_kind: 'UNIT', current_hp: 80, max_hp: 150, current_shield: 12, level: 1,
  status: 'ACTIVE', current_node_id: 'n', target_team_id: 'a',
};
const attacker: EntityState = {...enemy, id: 'attacker', team_id: 'a',
  simulation_state: {combat_state: 'ATTACKING', attack_target_id: enemy.id}};
const team: RenderTeam = {id: 'b', name: 'Đội B', base_hp: 420, initial_base_hp: 500,
  base_shield: 30, status: 'ACTIVE'};

test('inspection follows the actual attack target and its live health', () => {
  // Strategic destination differs from the entity being attacked.
  assert.deepEqual(attackTargetInfo({...attacker, target_team_id: 'c'}, [enemy], [team]), {
    id: enemy.id, name: 'Xe tăng', teamName: 'Đội B', hp: 80, maxHp: 150, shield: 12,
  });
  assert.equal(attackTargetInfo(attacker, [{...enemy, current_hp: 35}], [team])?.hp, 35);
  const tower = {...enemy, id: 'tower', entity_kind: 'TOWER' as const, unit_code: 'mg_tower'};
  assert.equal(attackTargetInfo({...attacker, simulation_state: {
    combat_state: 'ATTACKING', attack_target_id: tower.id,
  }}, [enemy, tower], [team])?.name, 'Tháp súng máy');
});

test('base targets use the base team health and shield', () => {
  const attackingBase = {...attacker, simulation_state: {
    combat_state: 'ATTACKING' as const, attack_target_id: 'base:b',
  }};
  assert.deepEqual(attackTargetInfo(attackingBase, [], [team]), {
    id: 'base:b', name: 'Căn cứ', teamName: 'Đội B', hp: 420, maxHp: 500, shield: 30,
  });
  assert.equal(attackTargetInfo(attackingBase, [], [{...team, base_hp: 0}]), null);
  assert.equal(attackTargetInfo(attackingBase, [], []), null);
});

test('idle, missing and destroyed targets never show stale target details', () => {
  assert.equal(attackTargetInfo({...attacker, simulation_state: {
    combat_state: 'IDLE', attack_target_id: enemy.id,
  }}, [enemy], [team]), null);
  assert.equal(attackTargetInfo(attacker, [], [team]), null);
  assert.equal(attackTargetInfo(attacker, [{...enemy, status: 'DESTROYED'}], [team]), null);
  assert.equal(attackTargetInfo(attacker, [{...enemy, current_hp: 0}], [team]), null);
  assert.equal(attackTargetInfo({...attacker, status: 'DESTROYED'}, [enemy], [team]), null);
  assert.equal(attackTargetInfo({...attacker, simulation_state: undefined}, [enemy], [team]), null);
});
