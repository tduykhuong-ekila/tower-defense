import test from 'node:test';
import assert from 'node:assert/strict';
import {MAX_UPGRADE_LEVEL, showBattleStars, starPoints, upgradeLevel} from '../src/game/upgradeLevel';
import {resolveUpgradeType} from '../src/game/upgradeSelection';
import {UnitType} from '../src/types/unit';

const codes = ['infantry', 'tank', 'artillery', 'cannon_tower', 'mg_tower', 'shield_generator'];
const catalog = codes.map((code, i) => ({code, id: `type-${i}`, category: i < 3 ? 'UNIT' : 'TOWER', upgrade: {eligible: true}})) as UnitType[];
test('levels and Phaser geometry stop at three filled stars', () => {
  assert.equal(MAX_UPGRADE_LEVEL, 3);
  for (const level of [1, 2, 3]) assert.equal(upgradeLevel(level), level);
  assert.equal(upgradeLevel(4), 3);
  assert.equal(starPoints(6, 6).length, 10);
});
test('star LOD suppresses dense armies in overview', () => {
  for (const code of codes) assert.equal(showBattleStars(code, .4), false);
  assert.equal(showBattleStars('infantry', .89), false);
  assert.equal(showBattleStars('infantry', .9), true);
  assert.equal(showBattleStars('cannon_tower', .55), true);
  assert.equal(showBattleStars('tank', .7), true);
});
for (const unit of catalog) test(`${unit.code} selects its exact team-wide type`, () => {
  assert.equal(resolveUpgradeType({team_id:'a',unit_code:unit.code},'a',catalog),unit.code);
  assert.equal(resolveUpgradeType({team_id:'a',unit_type_code:unit.code},'a',catalog),unit.code);
  assert.equal(resolveUpgradeType({team_id:'a',unit_type_id:unit.id},'a',catalog),unit.code);
  assert.equal(resolveUpgradeType({team_id:'enemy',unit_code:unit.code},'a',catalog),null);
});
test('unknown or ineligible types never fall back to another type', () => {
  assert.equal(resolveUpgradeType({team_id:'a',unit_code:'unknown'},'a',catalog),null);
  assert.equal(resolveUpgradeType({team_id:'a',unit_code:'tank'},'a',[]),null);
  assert.equal(resolveUpgradeType({team_id:'a',unit_code:'tank'},null,catalog),null);
  assert.equal(resolveUpgradeType({team_id:'a',unit_code:'tank'},'a',catalog.map(u=>({...u,upgrade:{...u.upgrade!,eligible:false}}))),null);
});
