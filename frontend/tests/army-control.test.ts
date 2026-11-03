import test from 'node:test';
import assert from 'node:assert/strict';
import {armyCommandRequest, controllableTroops, filterArmy, selectArmyGroup, updateArmySelection, shouldStartArmyBox} from '../src/game/armySelection';
import {useMatchStore} from '../src/stores/matchStore';
import {visibleGameplayModal} from '../src/game/gameplayModal';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {ArmyCommandPanel} from '../src/components/game/ArmyCommandPanel';

const unit = (id: string, team_id = 'a', extra = {}) => ({id, team_id, entity_kind:'UNIT', current_hp:39, max_hp:80,
  unit_code:'infantry', status:'ACTIVE', current_node_id:'road', level:3, target_team_id:'b', ...extra} as any);

test('selected troops show direct attack and retreat commands in the toolbar', () => {
  const noop = () => {};
  const html = renderToStaticMarkup(createElement(ArmyCommandPanel, {
    troops: [unit('i')], selected: [unit('i')],
    enemies: [{id: 'c', name: 'Đội C', status: 'ACTIVE', base_hp: 500, initial_base_hp: 500, base_shield: 0}],
    onAttack: noop, onSelectedRetreat: noop, onSelectGroup: noop, onClear: noop,
    multiple: false, onMultiple: noop, selectionMode: false, onSelectionMode: noop, disabled: false,
    onRetreat: noop, retreatOpen: false, onRetreatOpen: noop, retreatCount: 0, canRetreat: false,
  }));
  assert.match(html, /Đã chọn 1 quân/);
  assert.match(html, /Đội C/);
  assert.match(html, /role="group" aria-label="Tấn công căn cứ"/);
  assert.match(html, /Tấn công → Đội C/);
  assert.match(html, /class="army-selected-retreat" disabled=""/);
  assert.match(html, /Rút về điểm tập kết/);
  assert.doesNotMatch(html, /Thực hiện|army-order-picker/);
  assert.doesNotMatch(html, /army-group-chips|army-extra|Lọc trạng thái/);
});

test('empty map selection has a one-line hint and no executable command form', () => {
  const noop = () => {};
  const html = renderToStaticMarkup(createElement(ArmyCommandPanel, {
    troops: [unit('i')], selected: [], enemies: [], onAttack: noop, onSelectedRetreat: noop, onSelectGroup: noop, onClear: noop, multiple: false, onMultiple: noop,
    selectionMode: false, onSelectionMode: noop, disabled: false, onRetreat: noop,
    retreatOpen: false, onRetreatOpen: noop, retreatCount: 0,
  }));
  assert.match(html, /Chọn quân trên map để chỉ huy/);
  assert.doesNotMatch(html, /army-direct-commands|army-target-command|army-group-chips/);
});

test('selection includes mixed friendly mobile troops and rejects opponents, towers and dead units', () => {
  const entities = [unit('i'),unit('t','a',{unit_code:'tank'}),unit('r','a',{unit_code:'artillery'}),
    unit('enemy','b'),unit('dead','a',{current_hp:0}),unit('tower','a',{entity_kind:'TOWER'}),unit('still','a',{movement_speed:0})];
  assert.deepEqual(controllableTroops(entities,'a').map(e=>e.id),['i','t','r']);
  assert.deepEqual(updateArmySelection(['i'],['t'],true,true),['i','t']);
  assert.deepEqual(updateArmySelection(['i','t'],['i'],true,true),['t']);
  assert.deepEqual(updateArmySelection(['i'],['t','r'],true),['i','t','r']);
  assert.deepEqual(updateArmySelection(['i'],[],false),[]);
});

test('command deltas preserve unselected units and duplicates cannot undo newer retreat', () => {
  const store=useMatchStore;store.getState().reset();store.setState({entities:[unit('i'),unit('t')]});
  const event=(seq:number,type:string,updates:any[]) => ({event_id:`${seq}`,sequence_number:seq,event_type:type,
    payload:{entity_updates:updates,simulation_at:'2026-10-24T10:00:00Z',tick_interval_ms:200}} as any);
  const attack=event(1,'UNITS_RETARGETED',[unit('i','a',{target_team_id:'c',simulation_state:{order:'ATTACK',command_version:1}})]);
  store.getState().applyEvent(attack);
  assert.equal(store.getState().entities[0].target_team_id,'c');
  assert.equal(store.getState().entities[1].target_team_id,'b');
  store.getState().applyEvent(event(2,'ARMY_RETREAT_ORDERED',store.getState().entities.map(e=>({...e,target_team_id:null,simulation_state:{order:'RETREAT',command_version:2,destination_rally_id:'home'}}))));
  store.getState().applyEvent(attack);
  for(const entity of store.getState().entities) {
    assert.equal(entity.simulation_state?.order,'RETREAT');assert.equal(entity.current_hp,39);assert.equal(entity.level,3);
  }
  const returned=store.getState().entities.map(e=>({...e,simulation_state:{order:'AT_RALLY',world_position:{x:1,y:2}}}));
  store.getState().applySnapshot({entities:returned,teams:[],match:{id:'m',configuration:{}},viewer:{team_id:'a'}} as any,3);
  assert.ok(store.getState().entities.every(e=>e.simulation_state?.order==='AT_RALLY'));
});

test('question/reward events do not open a hidden quiz and open results remain visible',()=>{
  for(const status of ['PENDING_QUESTION','EXPIRED','ANSWER_INCORRECT','REWARD_CLAIMED','PENDING_REWARD']) {
    assert.equal(visibleGameplayModal(null,{status} as any,null),null);
  }
  assert.equal(visibleGameplayModal('QUESTION',{status:'EXPIRED'} as any,null),'QUESTION');
  assert.equal(visibleGameplayModal('REWARD',{status:'PENDING_REWARD'} as any,null),'REWARD');
});


test('multi-select toggles an entire type while preserving unrelated groups', () => {
  assert.deepEqual(selectArmyGroup(['i1', 'i2', 't1'], ['i1', 'i2'], true), ['t1']);
  assert.deepEqual(selectArmyGroup(['i1', 't1'], ['i1', 'i2'], true), ['i1', 't1', 'i2']);
  assert.deepEqual(selectArmyGroup(['i1'], ['t1', 't2'], false), ['t1', 't2']);
  const troops = [unit('i'), unit('t', 'a', {simulation_state: {order: 'RETREAT'}}),
    unit('r', 'a', {simulation_state: {order: 'AT_RALLY'}})];
  assert.deepEqual(filterArmy(troops, 'ATTACK').map(e => e.id), ['i']);
  assert.deepEqual(filterArmy(troops, 'RETREAT').map(e => e.id), ['t']);
  assert.deepEqual(filterArmy(troops, 'AT_RALLY').map(e => e.id), ['r']);
});

test('empty or expired selected-only commands never become implicit all-army retreat', () => {
  assert.equal(armyCommandRequest('RETREAT_ALL', [], ''), null);
  assert.equal(armyCommandRequest('RETARGET', [], 'b'), null);
  assert.equal(armyCommandRequest('RETARGET', ['i'], ''), null);
  const ids = ['i'];
  const request = armyCommandRequest('RETREAT_ALL', ids, '');
  ids.push('t');
  assert.deepEqual(request, {command_type: 'RETREAT_ALL', unit_ids: ['i']});
  assert.deepEqual(armyCommandRequest('RETARGET', ['i', 'i'], 'b'),
    {command_type: 'RETARGET', unit_ids: ['i'], target_team_id: 'b'});
});


test('trackpad drag pans unless Shift or the explicit box tool opts into selection', () => {
  const input = {enabled:true, mode:'IDLE' as const, touch:false, leftButton:true,
    shift:false, boxTool:false, panKey:false};
  assert.equal(shouldStartArmyBox(input), false);
  for (const mode of ['IDLE', 'INSPECT', 'COMBAT', 'DEPLOY', 'BUILD'] as const) {
    assert.equal(shouldStartArmyBox({...input, mode, shift:true}), true, mode);
  }
  assert.equal(shouldStartArmyBox({...input, boxTool:true}), true);
  assert.equal(shouldStartArmyBox({...input, shift:true, panKey:true}), false);
  assert.equal(shouldStartArmyBox({...input, shift:true, leftButton:false}), false);
  assert.equal(shouldStartArmyBox({...input, shift:true, enabled:false}), false);
  for (const mode of ['MODAL', 'WAITING'] as const) {
    assert.equal(shouldStartArmyBox({...input, mode, shift:true}), false);
    assert.equal(shouldStartArmyBox({...input, mode, boxTool:true}), false);
  }
  assert.equal(shouldStartArmyBox({...input, touch:true}), false);
  assert.equal(shouldStartArmyBox({...input, touch:true, shift:true}), false);
  assert.equal(shouldStartArmyBox({...input, touch:true, boxTool:true}), true);
});


test('context-only controls omit the toolbar while keeping whole-army retreat confirmation', () => {
  const noop = () => {};
  const html = renderToStaticMarkup(createElement(ArmyCommandPanel, {
    showToolbar:false, troops:[unit('i')], selected:[unit('i')], enemies:[],
    onAttack:noop, onSelectedRetreat:noop, onSelectGroup:noop, onClear:noop,
    multiple:false, onMultiple:noop, selectionMode:false, onSelectionMode:noop,
    disabled:false,  onRetreat:noop, retreatOpen:true,
    onRetreatOpen:noop, retreatCount:1,
  }));
  assert.doesNotMatch(html, /army-command-panel|army-command-form|army-map-summary/);
  assert.match(html, /role="alertdialog"/);
  assert.match(html, /Xác nhận rút 1 quân/);
});


test('group toolbar excludes eliminated targets and enables redirecting returning troops', () => {
  const noop = () => {};
  const render = (selected: any[], disabled = false) => renderToStaticMarkup(createElement(ArmyCommandPanel, {
    troops: selected, selected, enemies: [
      {id:'b', name:'Đội B', status:'ACTIVE', base_hp:500, initial_base_hp:500, base_shield:0},
      {id:'c', name:'Đội C', status:'ELIMINATED', base_hp:0, initial_base_hp:500, base_shield:0},
    ], onAttack:noop, onSelectedRetreat:noop, onSelectGroup:noop, onClear:noop,
    multiple:false, onMultiple:noop, selectionMode:false, onSelectionMode:noop, disabled,
    onRetreat:noop, retreatOpen:false, onRetreatOpen:noop, retreatCount:0,
  }));
  const attacking = render([unit('i'), unit('j')]);
  assert.match(attacking, /Đã chọn 2 quân/);
  assert.match(attacking, /class="army-target-command" disabled=""/);
  assert.doesNotMatch(attacking, /Đội C/);
  const returning = render([unit('i', 'a', {simulation_state:{order:'RETREAT'}})]);
  assert.doesNotMatch(returning, /class="army-target-command" disabled/);
  assert.match(returning, /class="army-selected-retreat" disabled=""/);
  const offline = render([unit('i', 'a', {target_team_id:'c'})], true);
  assert.match(offline, /class="army-target-command" disabled=""/);
  assert.match(offline, /class="army-selected-retreat" disabled=""/);
});


test('base defense sends only selected troops and applies realtime updates', () => {
  assert.equal(armyCommandRequest('DEFEND_BASE', [], 'b'), null);
  assert.deepEqual(armyCommandRequest('DEFEND_BASE', ['i', 'i', 't'], 'b'), {
    command_type: 'DEFEND_BASE', unit_ids: ['i', 't'],
  });
  const store = useMatchStore;
  store.getState().reset();
  store.setState({entities: [unit('i'), unit('t')]});
  store.getState().applyEvent({event_id: 'defend', sequence_number: 1, event_type: 'ARMY_DEFENSE_ORDERED',
    payload: {entity_updates: [unit('i', 'a', {target_team_id: null, simulation_state: {order: 'DEFEND_BASE'}})]}} as any);
  assert.equal(store.getState().entities[0].simulation_state?.order, 'DEFEND_BASE');
  assert.equal(store.getState().entities[0].target_team_id, null);
  assert.equal(store.getState().entities[1].target_team_id, 'b');
});

test('toolbar offers base defense and disables it before battle', () => {
  const noop = () => {};
  const props = {
    troops: [unit('i')], selected: [unit('i')], enemies: [],
    onAttack: noop, onSelectedRetreat: noop, onDefend: noop, onSelectGroup: noop, onClear: noop,
    multiple: false, onMultiple: noop, selectionMode: false, onSelectionMode: noop, disabled: false,
    onRetreat: noop, retreatOpen: false, onRetreatOpen: noop, retreatCount: 0,
  };
  const enabled = renderToStaticMarkup(createElement(ArmyCommandPanel, {...props, canRetreat: true}));
  assert.match(enabled, /class="army-selected-defend" title=/);
  assert.match(enabled, /Bảo vệ căn cứ/);
  const disabled = renderToStaticMarkup(createElement(ArmyCommandPanel, {...props, canRetreat: false}));
  assert.match(disabled, /class="army-selected-defend" disabled=""/);
});
