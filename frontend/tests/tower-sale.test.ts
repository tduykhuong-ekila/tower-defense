import test from 'node:test';
import assert from 'node:assert/strict';
import {towerSalePrice} from '../src/game/towerSale';
import {useMatchStore} from '../src/stores/matchStore';
import {actionAvailability} from '../src/game/actionAvailability';

test('sale uses original cost and remaining HP, floors fractional coins and caps at original cost', () => {
  for (const [hp, max, expected] of [[100,100,25], [51,100,12], [1,100,0], [80,200,10], [120,100,25], [0,100,0]]) {
    assert.equal(towerSalePrice({current_hp:hp, max_hp:max, simulation_state:{build_cost:25}}, 999), expected);
  }
});

test('selling removes only the sold tower, updates owner coins and ignores duplicate events', () => {
  useMatchStore.getState().reset();
  useMatchStore.setState({currentTeamId:'a', coins:10, entities:[{id:'sold'}, {id:'keep'}] as any,
    teams:[{id:'a',coins:10}, {id:'b',coins:50}] as any});
  const event = {match_id:'m', event_id:'sale', sequence_number:1, event_type:'TOWER_SOLD',
    payload:{entity_id:'sold', team_id:'a', coins_after:22}, server_timestamp:''};
  useMatchStore.getState().applyEvent(event);
  useMatchStore.getState().applyEvent(event);
  assert.deepEqual(useMatchStore.getState().entities.map(e => e.id), ['keep']);
  assert.equal(useMatchStore.getState().coins, 22);
  assert.equal(useMatchStore.getState().teams[1].coins, 50);
  useMatchStore.getState().applyEvent({...event, event_id:'enemy-sale', sequence_number:2,
    payload:{entity_id:'keep', team_id:'b'} as any});
  assert.equal(useMatchStore.getState().coins, 22);
  assert.equal(useMatchStore.getState().teams[1].coins, 50);
  assert.equal(useMatchStore.getState().entities.length, 0);
});

test('sales are available during continuous combat with no purchase balance requirement', () => {
  const context:any = {match:{status:'ACTIVE',phase:'WAR',configuration:{gameplay_mode:'CONTINUOUS',timer_state:{round_phase:'BATTLE'}}},
    team:{id:'a',status:'ACTIVE'}, spectator:false,connection:'connected',pending:false,modal:false,coins:0};
  assert.equal(actionAvailability(context, 'SELL_TOWER').allowed, true);
  context.match.status='PAUSED';
  assert.equal(actionAvailability(context, 'SELL_TOWER').allowed, false);
});
