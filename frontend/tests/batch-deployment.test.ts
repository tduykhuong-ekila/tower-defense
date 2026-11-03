import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { DeploymentQuantity } from '../src/components/DeploymentQuantity';
import { maximumDeployment, purchaseAvailability, AvailabilityContext } from '../src/game/actionAvailability';
import { graphRange } from '../src/game/range';
import { ServerMap } from '../src/game/map';
import { useMatchStore } from '../src/stores/matchStore';

const unit = {code:'infantry', category:'UNIT', cost:15, is_starter:true} as any;
function context(coins=150): AvailabilityContext {
  return {match:{status:'ACTIVE',phase:'WAR',configuration:{gameplay_mode:'CONTINUOUS',timer_state:{round_phase:'BATTLE'}, max_towers_per_team:6,max_active_units_per_team:5}} as any,
    team:{id:'a',status:'ACTIVE'} as any,spectator:false,connection:'connected',pending:false,modal:false,coins,entities:[],unlocked:[],slots:['slot6']};
}
test('quantity maximum uses current wallet and shared vehicle capacity, excluding Infantry', () => {
  const c=context();
  c.entities=Array.from({length:100},(_,i)=>({id:`i${i}`,team_id:'a',unit_code:'infantry',entity_kind:'UNIT',status:'ACTIVE'})) as any;
  assert.equal(maximumDeployment(c,unit),10);
  assert.equal(purchaseAvailability(c,unit,10).allowed,true);
  assert.equal(purchaseAvailability(c,unit,11).reason_code,'INSUFFICIENT_COINS');
  c.entities.push({id:'tank',team_id:'a',unit_code:'tank',entity_kind:'UNIT',status:'QUEUED'} as any);
  const tank={...unit,code:'tank',cost:35};
  assert.equal(maximumDeployment(c,tank),4);
  assert.equal(purchaseAvailability(c,tank,5).reason_code,'UNIT_LIMIT_REACHED');
  c.coins=0;
  assert.equal(maximumDeployment(c,unit),0);
  assert.equal(purchaseAvailability(c,unit).reason_code,'INSUFFICIENT_COINS');
});
test('invalid quantities and unlimited tower eligibility reflect authoritative rules', () => {
  const c=context(500);
  for (const quantity of [0,-1,1.5,NaN,Infinity]) assert.equal(purchaseAvailability(c,unit,quantity).reason_code,'INVALID_QUANTITY');
  c.entities=Array.from({length:5},(_,i)=>({id:`t${i}`,team_id:'a',entity_kind:'TOWER',status:'ACTIVE'})) as any;
  const tower={...unit,code:'mg_tower',category:'TOWER'} as any;
  assert.equal(purchaseAvailability(c,tower).allowed,true);
  c.entities.push({id:'t6',team_id:'a',entity_kind:'TOWER',status:'ACTIVE'} as any);
  assert.equal(purchaseAvailability(c,tower).allowed,true);
});
test('quantity controls show numeric input, total cost and validation without quick presets', () => {
  const html=renderToStaticMarkup(React.createElement(DeploymentQuantity, {value:'5',maximum:8,cost:15,coins:120,disabled:false,onChange:()=>{}}));
  assert.match(html,/type="number"/);assert.match(html,/Giảm số lượng/);assert.match(html,/Tăng số lượng/);
  assert.doesNotMatch(html,/quantity-presets|aria-label="Max"/);assert.match(html,/Tổng: 75 xu/);assert.match(html,/Hiện có: 120 xu/);
  const invalid=renderToStaticMarkup(React.createElement(DeploymentQuantity, {value:'0',maximum:0,cost:35,coins:0,disabled:false,reason:'Không đủ xu',onChange:()=>{}}));
  assert.match(invalid,/aria-invalid="true"/);assert.match(invalid,/Không đủ xu/);
});
test('batched creations upsert stable IDs once across REST snapshots, duplicate events and reconnect', () => {
  const store=useMatchStore;
  store.getState().reset();store.setState({currentTeamId:'a',coins:150});
  const entities=Array.from({length:5},(_,i)=>({id:`u${i}`,team_id:'a',unit_code:'infantry',entity_kind:'UNIT',current_hp:80,max_hp:80,range:1,status:'ACTIVE',current_node_id:'spawn'}));
  const event={event_id:'batch',sequence_number:1,event_type:'ENTITIES_CREATED',payload:{team_id:'a',entities,coins_after:75}} as any;
  store.getState().applyEvent(event);store.getState().applyEvent(event);
  assert.equal(store.getState().entities.length,5);assert.equal(store.getState().coins,75);
  store.getState().applyEvent({...event,event_id:'batch-again',sequence_number:2});
  assert.equal(store.getState().entities.length,5);
  store.getState().applySnapshot({entities,teams:[],match:{id:'m',configuration:{}},viewer:{team_id:'a',coins:75}} as any,3);
  assert.equal(new Set(store.getState().entities.map(e=>e.id)).size,5);
  assert.equal(store.getState().entities[0].range,1);
});
test('artillery preview covers exactly 1.5 hops, clipping the second edge halfway', () => {
  const map:ServerMap={num_teams:2,team_ids:['a','b'],nodes:['a','b','c','d'].map((id,i)=>({node_id:id,node_type:'lane',team_index:null,is_passable:true,x:i*100,y:0})),edges:[{from:'a',to:'b'},{from:'b',to:'c'},{from:'c',to:'d'}]};
  const coverage=graphRange(map,'a',1.5);
  assert.deepEqual(coverage.nodes,['a','b']);
  assert.deepEqual(coverage.segments,[{from:'a',to:'b',start:0,end:1},{from:'b',to:'c',start:0,end:.5}]);
  const moving=graphRange(map,'a',1.5,{next_node_id:'b',edge_progress:.5});
  assert.ok(moving.nodes.includes('c'));assert.ok(!moving.nodes.includes('d'));
});
