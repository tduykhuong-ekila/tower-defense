import test from "node:test";
import assert from "node:assert/strict";
import { actionAvailability } from "../src/game/actionAvailability";
import { formationPosition } from "../src/game/systems/formationPosition";
import { useMatchStore } from "../src/stores/matchStore";

test("battle permits deploy/build/target and continuous quiz, while special actions stay gated",()=>{
 const context:any={match:{status:"ACTIVE",phase:"WAR",configuration:{gameplay_mode:"CONTINUOUS",timer_state:{round_phase:"BATTLE"}}},team:{id:"a",status:"ACTIVE"},spectator:false,connection:"connected",pending:false,modal:false};
 for(const action of ["DEPLOY_UNIT","BUILD_TOWER","TARGET_SELECTED","ANSWER_QUESTION","CLAIM_REWARD","UPGRADE_TEAM_TYPE","UPGRADE_TOWER"])assert.equal(actionAvailability(context,action).allowed,true);
 for(const action of ["REPAIR_BASE","EMP","SCOUT"])assert.equal(actionAvailability(context,action).allowed,false);
 for(const status of ["PAUSED","FINISHED","LOBBY"])assert.equal(actionAvailability({...context,match:{...context.match,status}}).allowed,false);
 assert.equal(actionAvailability({...context,team:{id:"a",status:"ELIMINATED"}}).allowed,false);
});

test("formation is projected onto the authoritative centerline including its spawn approach",()=>{
 const a:any={id:"a",node_id:"a",x:0,y:0,worldX:100,worldY:100},b:any={id:"b",node_id:"b",x:80,y:0,worldX:220,worldY:100},nodes=new Map([["a",a],["b",b]]);
 assert.deepEqual(formationPosition(a,{next_node_id:"b",edge_progress:.25},nodes),{x:130,y:100});
 assert.deepEqual(formationPosition(a,{approach_node_id:"b",staging_distance:80},nodes),{x:-20,y:100});
});

test("live spawns retain 100 HP and authoritative staging; REST/socket stable IDs never duplicate",()=>{
 const store=useMatchStore.getState();store.reset();
 const e=(seq:number)=>({match_id:"m",event_type:"UNIT_DEPLOYED",sequence_number:seq,event_id:String(seq),server_timestamp:"",payload:{entity_id:"unit",team_id:"a",unit_code:"infantry",current_hp:100,max_hp:100,current_node_id:"spawn",simulation_state:{formation_order:3,approach_node_id:"merge",staging_distance:164}}});
 store.applyEvent(e(1));store.applyEvent(e(2));
 const state=useMatchStore.getState();assert.equal(state.entities.length,1);assert.equal(state.entities[0].current_hp,100);assert.equal(state.entities[0].max_hp,100);assert.equal(state.entities[0].simulation_state?.staging_distance,164);
});
