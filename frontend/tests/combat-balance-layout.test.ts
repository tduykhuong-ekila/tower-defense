import test from 'node:test';
import assert from 'node:assert/strict';
import {graphRange} from '../src/game/range';
import {projectMap, ServerMap} from '../src/game/map';
import {formationPosition} from '../src/game/systems/formationPosition';
import {useMatchStore} from '../src/stores/matchStore';
import {normalizeEntity} from '../src/game/bridge';

const tower='node_tower_t1_slot1';
const map:ServerMap={num_teams:2,team_ids:['a','b'],nodes:[
 {node_id:tower,node_type:'tower_slot',is_passable:false,team_index:1,x:50,y:80},
 ...['a','b','c','d'].map((node_id,i)=>({node_id,node_type:'lane' as const,is_passable:true,team_index:1,x:i*100,y:0}))
],edges:[{from:tower,to:'a'},{from:tower,to:'b'},{from:'a',to:'b'},{from:'b',to:'c'},{from:'c',to:'d'}]};

test('Cannon preview is two thirds of previous three-hop range and excludes outer road',()=>{
 const current=graphRange(map,tower,3*(2/3)), previous=graphRange(map,tower,3);
 assert.deepEqual(current.nodes,[tower,'a','b','c']);
 assert.ok(previous.nodes.includes('d'));assert.ok(!current.nodes.includes('d'));
 assert.deepEqual(current.segments,[{from:'a',to:'b',start:0,end:1},{from:'b',to:'c',start:0,end:1}]);
});

test('instance range can retain three hops while newly selected Cannon uses two',()=>{
 assert.ok(graphRange(map,tower,3).nodes.includes('d'));
 assert.ok(!graphRange(map,tower,2).nodes.includes('d'));
 assert.deepEqual(graphRange(map,'a',1.5).segments.at(-1),{from:'b',to:'c',start:0,end:.5});
});

test('Artillery speed and 80 HP survive creation, updates and reconnect without duplicate IDs',()=>{
 const store=useMatchStore;store.getState().reset();
 store.getState().applyEvent({event_id:'create',event_type:'UNIT_DEPLOYED',sequence_number:1,payload:{entity_id:'arty',team_id:'a',unit_code:'artillery',current_hp:80,max_hp:80,range:1.5,movement_speed:5,status:'ACTIVE',current_node_id:'a',simulation_state:{movement_zone:'ROUTE',world_position:{x:0,y:0}}}} as any);
 let entity=store.getState().entities[0];assert.equal(entity.movement_speed,5);assert.equal(entity.max_hp,80);
 const rest=normalizeEntity({...entity,unit_type_code:'artillery',name:'Artillery',match_id:'m',unit_type_id:'type',created_at:''} as any);
 assert.equal(rest.movement_speed,5);
 const updated={...rest,current_hp:39,simulation_state:{...entity.simulation_state,world_position:{x:10,y:0},movement_state:'MOVING'}};
 store.getState().applyEvent({event_id:'tick',event_type:'COMBAT_TICK',sequence_number:2,payload:{tick:1,entity_updates:[updated],events:[]}} as any);
 store.getState().applySnapshot({entities:[updated],teams:[],match:{id:'m',configuration:{}},viewer:{team_id:'a'}} as any,3);
 assert.equal(store.getState().entities.length,1);entity=store.getState().entities[0];
 assert.equal(entity.current_hp,39);assert.equal(entity.max_hp,80);assert.equal(entity.movement_speed,5);assert.equal(entity.range,1.5);
 assert.deepEqual(entity.simulation_state?.world_position,{x:10,y:0});
});

test('slot projection follows authoritative coordinates and troop offsets use the same projection',()=>{
 const old=projectMap(map).get(tower)!;
 const changed={...map,nodes:map.nodes.map(n=>n.node_id===tower?{...n,y:68}:n)};
 const nodes=projectMap(changed), slot=nodes.get(tower)!;
 assert.notEqual(slot.worldX,old.worldX);assert.notEqual(slot.worldY,old.worldY);
 assert.deepEqual(formationPosition(slot,{world_position:{x:slot.x,y:slot.y}},nodes),{x:slot.worldX,y:slot.worldY});
});
