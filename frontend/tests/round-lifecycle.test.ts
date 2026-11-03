import test from 'node:test';
import assert from 'node:assert/strict';
import { useMatchStore } from '../src/stores/matchStore';
import { planningSeconds } from '../src/game/roundClock';
import { Match } from '../src/types/match';
import { reconcileCombat } from '../src/game/systems/reconcile';

const end = '2026-10-17T08:00:30Z';
function setup() {
  useMatchStore.getState().reset();
  useMatchStore.setState({ match: {id:'m',status:'ACTIVE',phase:'WAR', configuration:{
    round_duration_seconds:30, timer_state:{next_round_at:end}
  }} as Match, currentTeamId:'a', teams:[{id:'a',name:'A',base_hp:500,base_shield:40,status:'ACTIVE'},
    {id:'b',name:'B',base_hp:500,base_shield:40,status:'ACTIVE'}] as any });
}
function event(type:string, payload:any, seq=1) {
  useMatchStore.getState().applyEvent({match_id:'m',event_id:`e${seq}`,event_type:type,
    sequence_number:seq,server_timestamp:'2026-10-17T08:00:00Z',payload});
}

test('round result opens next planning round and duplicate cannot replay combat or income',()=>{
  setup();
  const payload={round_number:1, current_round:2,timer_state:{next_round_at:end},events:[
    {type:'BASE_DAMAGED',target_team_id:'b',base_hp_remaining:490,base_shield_remaining:0},
    {type:'INCOME_AWARDED',team_id:'a',new_balance:110}
  ]};
  event('COMBAT_RESOLVED',payload);
  const state=useMatchStore.getState();
  assert.equal(state.currentRound,2);
  assert.equal(state.teams[1].base_shield,0);
  assert.equal(state.teams[1].base_hp,490);
  assert.equal(state.coins,110);
  event('COMBAT_RESOLVED',payload);
  assert.equal(useMatchStore.getState().combatLogs.length,2);
  assert.equal(useMatchStore.getState().currentRound,2);
});

test('round countdown freezes on pause and follows server resume and phase events',()=>{
  setup();
  const now=Date.parse('2026-10-17T08:00:10Z');
  assert.equal(planningSeconds(useMatchStore.getState().match,now),20);
  event('MATCH_PAUSED',{timer_state:{next_round_at:end,round_remaining_seconds:20}});
  assert.equal(planningSeconds(useMatchStore.getState().match,now+600000),20);
  event('MATCH_RESUMED',{timer_state:{next_round_at:'2026-10-17T08:10:30Z'}},2);
  assert.equal(planningSeconds(useMatchStore.getState().match,now+600000),20);
  event('MATCH_PHASE_CHANGED',{phase:'FINAL_ASSAULT',timer_state:{next_round_at:end}},3);
  assert.equal(useMatchStore.getState().match?.phase,'FINAL_ASSAULT');
  assert.equal(planningSeconds(useMatchStore.getState().match,now+30000),0);
});

test('final round and leaderboard immediately expose finished state and actual scores',()=>{
  setup();
  event('COMBAT_RESOLVED',{round_number:5,is_match_over:true,eliminated_team_ids:['b'],events:[]});
  assert.equal(useMatchStore.getState().match?.status,'FINISHED');
  assert.equal(useMatchStore.getState().match?.phase,'RESULTS');
  assert.equal(planningSeconds(useMatchStore.getState().match,Date.now()),null);
  event('LEADERBOARD_UPDATED',{leaderboard:[{team_id:'a',score:150},{team_id:'b',score:12}]},2);
  assert.equal(useMatchStore.getState().teams[0].score,150);
});

test('EMP recovery, entity shield and fallback targeting come entirely from deltas',()=>{
  const entities=[{id:'u',current_hp:40,current_shield:20,target_team_id:'b'},
    {id:'t',status:'DISABLED'}] as any;
  const result=reconcileCombat([],entities,[
    {type:'UNIT_ATTACKED',target_entity_id:'u',target_hp_remaining:35,target_shield_remaining:0},
    {type:'UNIT_RETARGETED',entity_id:'u',target_team_id:'c'},
    {type:'TOWER_ENABLED',entity_id:'t'},
  ],'a',100);
  assert.equal(result.entities[0].current_hp,35);
  assert.equal(result.entities[0].current_shield,0);
  assert.equal(result.entities[0].target_team_id,'c');
  assert.equal(result.entities[1].status,'ACTIVE');
});
