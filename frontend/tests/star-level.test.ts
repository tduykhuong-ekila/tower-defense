import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {useMatchStore} from '../src/stores/matchStore';
const require=createRequire(import.meta.url);
require.extensions['.css']=()=>{};
const {UnitLevelStars}=require('../src/components/game/UnitLevelStars');
const {GameItemCardContent}=require('../src/components/game/GameItemCardContent');
for(const level of [1,2,3]) test(`actual SVG stars and shared picker rows at level ${level}`,()=>{
 const stars=renderToStaticMarkup(createElement(UnitLevelStars,{level}));
 assert.equal((stars.match(/<svg/g)||[]).length,level);
 assert.ok(stars.includes(`aria-label="Cấp ${level} trên 3"`));
 for(const code of ['infantry','tank','artillery','mg_tower','cannon_tower','shield_generator']) {
  const html=renderToStaticMarkup(createElement(GameItemCardContent,{unit:{code,name:code,cost:40,level},teamIndex:0,unlocked:true}));
  assert.ok(html.indexOf('game-item-card__artwork')<html.indexOf('game-item-card__stars'));
  assert.ok(html.indexOf('game-item-card__stars')<html.indexOf('game-item-card__name'));
  assert.ok(html.indexOf('game-item-card__name')<html.indexOf('card-cost'));
  assert.ok(!html.includes('upgrade-rank')&&!html.includes('Lv.'));
  assert.ok(html.includes(`/assets/woodland/${code}${level>1?`-lv${level}`:''}.${['mg_tower','cannon_tower','tank','artillery','infantry'].includes(code)?'png':'svg'}`));
 }
});
test('unsupported saved Level 4 display clamps to the three-star maximum',()=>{
 const stars=renderToStaticMarkup(createElement(UnitLevelStars,{level:4}));
 assert.equal((stars.match(/<svg/g)||[]).length,3);
 assert.ok(stars.includes('aria-label="Cấp 3 trên 3"'));
});
test('upgrade stars stay authoritative with no deployed troops and are isolated per team',()=>{
 const store=useMatchStore;store.getState().reset();
 store.getState().applySnapshot({match:{id:'m'},teams:[],entities:[],viewer:{team_id:'a'},team_upgrades:{a:{infantry:2},b:{infantry:3}}} as any,10);
 store.getState().applyEvent({match_id:'m',event_type:'TEAM_UNIT_UPGRADED',sequence_number:11,payload:{team_id:'a',entity_type:'infantry',level:3,stats:{hp:104,damage:6}}} as any);
 assert.deepEqual(store.getState().teamUpgradeLevels,{a:{infantry:3},b:{infantry:3}});
 // An overtaken REST-equivalent snapshot cannot roll the stars back.
 store.getState().applySnapshot({match:{id:'m'},teams:[],entities:[],viewer:{team_id:'a'},team_upgrades:{a:{infantry:2}}} as any,9);
 assert.equal(store.getState().teamUpgradeLevels.a.infantry,3);
 store.getState().reset();assert.deepEqual(store.getState().teamUpgradeLevels,{});
});
