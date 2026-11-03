import test from "node:test";
import assert from "node:assert/strict";
import {formationPosition} from "../src/game/systems/formationPosition";
import {MotionTrack} from "../src/game/systems/interpolation";
import {projectMap, ServerMap} from "../src/game/map";
import {useMatchStore} from "../src/stores/matchStore";

test("staging and bypass positions use the server projection without client offsets", () => {
  const data: ServerMap = {num_teams: 2, team_ids: ["a","b"], edges: [], nodes: [
    {node_id:"spawn", node_type:"spawn", team_index:1, is_passable:true, x:240, y:36},
    {node_id:"position", node_type:"lane", team_index:1, is_passable:true, x:294, y:94},
  ]};
  const nodes = projectMap(data), node = nodes.get("spawn")!, expected = nodes.get("position")!;
  const point = formationPosition(node, {movement_zone:"STAGING", world_position:{x:294,y:94}}, nodes);
  assert.ok(Math.hypot(point.x-expected.worldX,point.y-expected.worldY)<1e-9);
  assert.deepEqual(formationPosition(node, {movement_zone:"ROUTE", combat_state:"ATTACKING", world_position:{x:294,y:94}},nodes),point);
});

test("one stopped attack track does not pause another unit's bypass interpolation", () => {
  const attacking = new MotionTrack(200), passing = new MotionTrack(200);
  attacking.push({x:0,y:0},"a1",1000);
  passing.push({x:-10,y:0},"b1",1000);
  attacking.push({x:0,y:0},"a2",1200);
  passing.push({x:10,y:10},"b2",1200,[{x:-10,y:10}]);
  assert.deepEqual(attacking.at(1300),{x:0,y:0});
  assert.ok(Math.abs(passing.at(1300)!.x + 5) < 1e-9);
  assert.equal(passing.at(1300)!.y,10);
  assert.deepEqual(passing.at(9999),{x:10,y:10});
});

test("combat events and position deltas retain each unit's independent state", () => {
  const store = useMatchStore.getState(); store.reset();
  const event = (event_type:string,sequence_number:number,payload:any) => ({event_type,sequence_number,payload,event_id:String(sequence_number),match_id:"m",server_timestamp:""});
  for (const [index,id] of ["attacker","follower"].entries()) store.applyEvent(event("UNIT_DEPLOYED",index+1,
    {entity_id:id,team_id:"a",unit_code:"infantry",current_node_id:"spawn",current_hp:100,max_hp:100}));
  store.applyEvent(event("COMBAT_TICK",3,{simulation_at:"2026-10-21T00:00:01Z",entity_updates:[
    {id:"attacker",simulation_state:{movement_zone:"ROUTE",movement_state:"STOPPED",combat_state:"ATTACKING",attack_target_id:"enemy",attack_remaining:1.8,world_position:{x:10,y:0}}},
    {id:"follower",simulation_state:{movement_zone:"ROUTE",movement_state:"MOVING",combat_state:"IDLE",world_position:{x:12,y:20}}},
  ],events:[{type:"UNIT_ATTACKED",attacker_id:"attacker",target_entity_id:"enemy",target_hp_remaining:95}]}));
  const entities = useMatchStore.getState().entities;
  assert.equal(entities[0].simulation_state?.combat_state,"ATTACKING");
  assert.deepEqual(entities[1].simulation_state?.world_position,{x:12,y:20});
  assert.equal(entities[1].simulation_state?.movement_state,"MOVING");
  assert.equal(entities[1].current_hp,100);
  store.reset();
});

test("road routing chooses physical length and excludes grass nodes", async () => {
  const {roadPath} = await import("../src/game/map");
  const nodes = [["a",0,0],["b",50,100],["c",1,0],["d",2,0],["z",3,0],["grass",1.5,0]] as const;
  const data: ServerMap = {num_teams:2, team_ids:["a","b"],
    nodes:nodes.map(([node_id,x,y]) => ({node_id,x,y,node_type:"lane",team_index:null,is_passable:node_id!=="grass"})),
    edges:[["a","b"],["b","z"],["a","c"],["c","d"],["d","z"],["a","grass"],["grass","z"]]
      .map(([from,to]) => ({from,to}))};
  assert.deepEqual(roadPath(data,"a","z"),["a","c","d","z"]);
  assert.deepEqual(roadPath(data,"a","grass"),[]);
  assert.deepEqual(roadPath(data,"grass","grass"),[]);
});
