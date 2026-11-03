import test from 'node:test';
import assert from 'node:assert/strict';
import {actionAvailability,purchaseAvailability,AvailabilityContext} from '../src/game/actionAvailability';
import {UnitType} from '../src/types/unit';
import {useMatchStore} from '../src/stores/matchStore';
const infantry={code:'infantry',category:'UNIT',is_starter:true,cost:15} as UnitType;
const tower={code:'mg_tower',category:'TOWER',is_starter:true,cost:25} as UnitType;
const context=():AvailabilityContext=>({match:{id:'m',status:'ACTIVE',phase:'WAR',configuration:{current_round:2,max_active_units_per_team:5,max_towers_per_team:3,timer_state:{round_phase:'PLANNING'}}} as any,
 team:{id:'a',name:'A',status:'ACTIVE'} as any,spectator:false,connection:'connected',pending:false,modal:false,coins:100,entities:[],unlocked:['infantry','mg_tower'],slots:['node_tower_t1_slot1']});

test('rounds 1, 2 and 5 permit purchases without resetting persistent state or depending on animation',()=>{
 for(const round of [1,2,5]){const c=context();c.match!.configuration.current_round=round;
  assert.equal(purchaseAvailability(c,infantry).allowed,true);assert.equal(purchaseAvailability(c,tower).allowed,true);
  assert.equal(c.coins,100);assert.deepEqual(c.unlocked,['infantry','mg_tower']);}
});
test('actual capacity, coins, unlock, placement and phase have distinct rejection reasons',()=>{
 const c=context();c.coins=0;assert.equal(purchaseAvailability(c,infantry).reason_code,'INSUFFICIENT_COINS');
 c.coins=100;c.entities=Array.from({length:5},(_,i)=>({id:String(i),team_id:'a',entity_kind:'UNIT',status:'ACTIVE'})) as any;
 assert.equal(purchaseAvailability(c,infantry).allowed,true);
 assert.equal(purchaseAvailability(c,{...infantry,code:'tank'}).reason_code,'UNIT_LIMIT_REACHED');c.entities[0].status='DESTROYED';
 assert.equal(purchaseAvailability(c,infantry).allowed,true);
 assert.equal(purchaseAvailability(c,{...infantry,code:'tank',is_starter:false}).reason_code,'UNIT_LOCKED');
 c.unlocked.push('tank');assert.equal(purchaseAvailability(c,{...infantry,code:'tank',is_starter:false}).allowed,true);
 c.slots=[];assert.equal(purchaseAvailability(c,tower).reason_code,'INVALID_POSITION');
 c.match!.configuration.timer_state!.round_phase='RESOLVING';assert.equal(purchaseAvailability(c,infantry).reason_code,'INVALID_PHASE');
 c.match!.status='FINISHED';assert.equal(purchaseAvailability(c,infantry).reason_code,'MATCH_FINISHED');
});
test('pause, pending request and elimination stay locked while next planning is restored',()=>{
 const c=context();c.pending=true;assert.equal(actionAvailability(c).reason_code,'ACTION_ALREADY_PROCESSING');
 c.pending=false;c.match!.status='PAUSED';assert.equal(actionAvailability(c).reason_code,'MATCH_PAUSED');
 c.match!.status='ACTIVE';assert.equal(actionAvailability(c).allowed,true);
 c.team!.status='ELIMINATED';assert.equal(actionAvailability(c).reason_code,'TEAM_ELIMINATED');
});
test('late old-round events cannot roll back a newer planning round or its HP',()=>{
 useMatchStore.getState().reset();const c=context();useMatchStore.setState({match:c.match,currentRound:5,teams:[{...c.team,base_hp:400}] as any});
 const event=(type:string,payload:any,seq:number)=>useMatchStore.getState().applyEvent({match_id:'m',event_id:String(seq),sequence_number:seq,event_type:type,payload,server_timestamp:''});
 event('COMBAT_RESOLVED',{round_number:2,events:[{type:'BASE_DAMAGED',target_team_id:'a',base_hp_remaining:490}]},10);
 event('ROUND_STARTED',{current_round:3,timer_state:{round_phase:'PLANNING'}},11);
 assert.equal(useMatchStore.getState().currentRound,5);assert.equal(useMatchStore.getState().teams[0].base_hp,400);
});

test('tower quantity never rejects valid grid construction, including stale saved caps',()=>{
 const c=context();c.gridPlacement=true;c.slots=[];
 for(const cap of [1,6,null]) for(const count of [6,7,8,25,50,1000]) {
  c.match!.configuration.max_towers_per_team=cap;
  c.entities=Array.from({length:count},(_,i)=>({id:String(i),team_id:'a',entity_kind:'TOWER',status:'ACTIVE'})) as any;
  assert.equal(purchaseAvailability(c,tower).allowed,true,`${cap}/${count}`);
 }
 c.coins=24;assert.equal(purchaseAvailability(c,tower).reason_code,'INSUFFICIENT_COINS');
 c.coins=100;assert.equal(purchaseAvailability(c,{...tower,code:'cannon_tower',is_starter:false}).reason_code,'TOWER_LOCKED');
});


test('eliminated participants can answer and claim rewards while combat remains blocked',()=>{
 const c=context();c.team!.status='ELIMINATED';
 for(const continuous of [false,true]) {
  c.match!.configuration.gameplay_mode=continuous?'CONTINUOUS':undefined;
  c.match!.configuration.timer_state!.round_phase=continuous?'BATTLE':'PLANNING';
  for(const action of ['ANSWER_QUESTION','CLAIM_REWARD']) assert.equal(actionAvailability(c,action).allowed,true);
  for(const action of ['DEPLOY_UNIT','BUILD_TOWER','UPGRADE_TEAM_TYPE','SELL_TOWER']) assert.equal(actionAvailability(c,action).reason_code,'TEAM_ELIMINATED');
 }
 c.spectator=true;assert.equal(actionAvailability(c,'ANSWER_QUESTION').reason_code,'SPECTATOR_READ_ONLY');
 c.spectator=false;c.match!.status='PAUSED';assert.equal(actionAvailability(c,'ANSWER_QUESTION').reason_code,'MATCH_PAUSED');
 c.match!.status='FINISHED';assert.equal(actionAvailability(c,'CLAIM_REWARD').reason_code,'MATCH_FINISHED');
});
