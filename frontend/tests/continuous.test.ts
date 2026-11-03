import test from "node:test";
import assert from "node:assert/strict";
import { MotionTrack } from "../src/game/systems/interpolation";
import { useMatchStore } from "../src/stores/matchStore";
import { WebSocketClient } from "../src/services/websocket";

test("movement follows buffered road corner and clamps after packet loss", () => {
  const track = new MotionTrack(200);
  track.push({x:0,y:0},"a",1000);
  track.push({x:10,y:10},"b",1200,[{x:10,y:0}]);
  assert.deepEqual(track.at(1250),{x:5,y:0});
  assert.deepEqual(track.at(1350),{x:10,y:5});
  track.push({x:10,y:10},"b",1300);
  assert.deepEqual(track.at(1300),{x:10,y:0});
  assert.deepEqual(track.at(9999),{x:10,y:10});
});

test("spawn/build stable IDs and live tick HP reconcile without advancing major round", () => {
  const store=useMatchStore.getState();store.reset();
  const event=(type:string,sequence:number,payload:any)=>({match_id:"m",event_id:String(sequence),sequence_number:sequence,event_type:type,server_timestamp:"",payload});
  store.applyEvent(event("UNIT_DEPLOYED",1,{entity_id:"u",team_id:"a",unit_code:"infantry",spawn_node:"spawn",current_hp:40,max_hp:40}));
  store.applyEvent(event("UNIT_DEPLOYED",2,{entity_id:"u",team_id:"a",unit_code:"infantry",spawn_node:"spawn",current_hp:40,max_hp:40}));
  assert.equal(useMatchStore.getState().entities.length,1);
  store.applyEvent(event("COMBAT_TICK",3,{tick:1,simulation_at:"now",entity_updates:[{id:"u",status:"ACTIVE",simulation_state:{next_node_id:"lane",edge_progress:.1}}],events:[]}));
  assert.equal(useMatchStore.getState().currentRound,1);
  assert.equal(useMatchStore.getState().entities[0].simulation_state?.edge_progress,.1);
  store.applyEvent(event("COMBAT_TICK",4,{entity_updates:[{id:"u",current_hp:0,status:"DESTROYED"}],events:[{type:"ENTITY_DESTROYED",entity_id:"u"}]}));
  assert.equal(useMatchStore.getState().entities.length,0);
});

test("out of order events wait for snapshot and stale snapshots never overwrite newer state", () => {
  const original={WebSocket:globalThis.WebSocket,window:globalThis.window,sessionStorage:globalThis.sessionStorage};
  let socket:any;
  class Socket { static OPEN=1;static CONNECTING=0;readyState=1;onopen:any;onmessage:any;onclose:any;sent:any[]=[];constructor(){socket=this;}send(s:string){this.sent.push(s);}close(){} }
  Object.assign(globalThis,{WebSocket:Socket,window:{location:{protocol:"http:",host:"localhost",pathname:"/"}},sessionStorage:{getItem:()=>null}});
  const client=new WebSocketClient(), seen:number[]=[];
  client.on("any",(_,e)=>seen.push(e.sequence_number));
  const receive=(n:number,type="COMBAT_TICK")=>socket.onmessage({data:JSON.stringify({event_id:`${type}-${n}`,match_id:"m",event_type:type,sequence_number:n,payload:{}})});
  try {
    client.connect("m");socket.onopen();
    receive(10,"MATCH_STATE_SNAPSHOT");receive(12);receive(11);
    assert.deepEqual(seen,[10]);
    receive(11,"MATCH_STATE_SNAPSHOT");
    assert.deepEqual(seen,[10,11,12]);
    receive(9,"MATCH_STATE_SNAPSHOT");
    assert.deepEqual(seen,[10,11,12]);
    // An overtaken snapshot is ignored after successful repair, without starting
    // another blocking sync that would unnecessarily freeze subsequent builds.
    assert.equal(socket.sent.length,1);
  } finally {client.disconnect();Object.assign(globalThis,original);}
});


test("simulation timestamps keep interpolation pace despite receive jitter", () => {
  const track = new MotionTrack(200);
  track.push({x:0,y:0},"a",5000,[],1000);
  track.push({x:10,y:0},"b",5400,[],1200);
  assert.deepEqual(track.at(5250),{x:2.5,y:0});
  // A delayed older position never rewinds the movement history.
  track.push({x:-100,y:0},"stale",5500,[],1100);
  assert.deepEqual(track.at(5400),{x:10,y:0});
});

test('recovery snapshots retain the simulation clock before the next live tick', () => {
  const store = useMatchStore.getState(); store.reset();
  const snapshot:any={match:{id:'m',configuration:{}},teams:[],viewer:{},current_round:1,
    simulation_at:'2026-10-22T00:00:01.200Z',tick_interval_ms:200,
    entities:[{id:'u',current_node_id:'lane',simulation_state:{world_position:{x:10,y:0}}}]};
  store.applySnapshot(snapshot,10);
  const restored = useMatchStore.getState().entities[0];
  assert.equal(restored.simulation_at,snapshot.simulation_at);
  const track = new MotionTrack(200);
  track.push({x:0,y:0},'first',5000,[],1000);
  track.push(restored.simulation_state!.world_position!,'snapshot',5600,[],Date.parse(restored.simulation_at!)-Date.parse('2026-10-22T00:00:00Z'));
  track.push({x:20,y:0},'next-tick',5650,[],1400);
  assert.deepEqual(track.at(5500),{x:15,y:0});
  track.push({x:-100,y:0},'retry',5700,[],1300);
  track.push({x:30,y:0},'retry',5800,[],1600);
  assert.deepEqual(track.at(5700),{x:25,y:0});
  store.applySnapshot({...snapshot,entities:[]},9);
  assert.equal(useMatchStore.getState().entities.length,1);
  store.reset();
});
