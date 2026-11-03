import test from 'node:test';
import assert from 'node:assert/strict';
import { WebSocketClient } from '../src/services/websocket';
import { useMatchStore } from '../src/stores/matchStore';

class Socket {
  static OPEN=1; static CONNECTING=0; static instances: Socket[]=[];
  readyState=0; sent: any[]=[]; closed=false;
  onopen: any; onmessage: any; onclose: any; onerror: any;
  constructor(public url:string) { Socket.instances.push(this); }
  send(data:string) { this.sent.push(JSON.parse(data)); }
  close() { this.readyState=3; this.closed=true; }
  open() { this.readyState=1; this.onopen?.(); }
  receive(sequence:number,type='UNIT_DEPLOYED',match='m',id=`${type}-${sequence}`,payload:any={}) {
    this.onmessage?.({data:JSON.stringify({event_id:id,match_id:match,event_type:type,sequence_number:sequence,payload})});
  }
}
function setup(options={}) {
  const saved={WebSocket:globalThis.WebSocket,window:globalThis.window,sessionStorage:globalThis.sessionStorage};
  const online=new Map<string,()=>void>();
  Object.assign(globalThis,{WebSocket:Socket,window:{location:{protocol:'http:',host:'localhost'},addEventListener:(k:string,f:()=>void)=>online.set(k,f),removeEventListener:(k:string)=>online.delete(k)},sessionStorage:{getItem:()=>null}});
  const client=new WebSocketClient(options, () => new Promise(() => {})),seen:number[]=[];
  client.onEvent(e=>seen.push(e.sequence_number));client.connect('m');
  const socket=Socket.instances.at(-1)!;socket.open();
  return {client,socket,seen,online,cleanup:()=>{client.disconnect();Object.assign(globalThis,saved);}};
}

test('chunked snapshots apply atomically before buffered deltas and deduplicate on replay',()=>{
  const t=setup();
  try {
    const raw=JSON.stringify({event_id:'snapshot-10',match_id:'m',event_type:'MATCH_STATE_SNAPSHOT',sequence_number:10,payload:{entities:[]}});
    const middle=Math.floor(raw.length/2);
    t.socket.receive(0,'JSON_CHUNK','m','chunk-0',{id:'transfer',index:0,total:2,data:raw.slice(0,middle)});
    assert.deepEqual(t.seen,[]);
    t.socket.receive(11);
    assert.deepEqual(t.seen,[]);
    t.socket.receive(0,'JSON_CHUNK','m','chunk-1',{id:'transfer',index:1,total:2,data:raw.slice(middle)});
    assert.deepEqual(t.seen,[10,11]);
    t.socket.receive(11);
    assert.deepEqual(t.seen,[10,11]);
  } finally {t.cleanup();}
});

test('initial delta waits for full snapshot; duplicate buffered delivery creates one entity',()=>{
  const t=setup();
  try {
    t.socket.receive(12);t.socket.receive(12);
    assert.deepEqual(t.seen,[]);
    t.socket.receive(11,'MATCH_STATE_SNAPSHOT');
    assert.deepEqual(t.seen,[11,12]);
    t.socket.receive(12);assert.deepEqual(t.seen,[11,12]);
  } finally {t.cleanup();}
});

test('offline sync request cannot wedge the next connected recovery',()=>{
  const t=setup();
  try {
    t.client.disconnect();t.client.requestSync();t.client.connect('m');
    const socket=Socket.instances.at(-1)!;socket.open();socket.receive(1,'MATCH_STATE_SNAPSHOT');
    t.client.requestSync();assert.equal(socket.sent.filter(e=>e.event_type==='STATE_SYNC_REQUEST').length,1);
  } finally {t.cleanup();}
});

test('lost snapshot and half-open socket cause automatic reconnect instead of permanent pending state',async()=>{
  const t=setup({snapshotTimeoutMs:15});
  try {
    t.socket.receive(1,'MATCH_STATE_SNAPSHOT');t.client.requestSync();
    await new Promise(r=>setTimeout(r,40));
    assert.equal(t.socket.closed,true);assert.equal(t.client.getStatus(),'reconnecting');
  } finally {t.cleanup();}
});

test('heartbeat discovers missing last event without needing a later gameplay event',()=>{
  const t=setup();
  try {
    t.socket.receive(1,'MATCH_STATE_SNAPSHOT');t.socket.receive(0,'PONG','m','pong',{state_version:2});
    assert.equal(t.socket.sent.at(-1).event_type,'STATE_SYNC_REQUEST');
    t.socket.receive(2,'MATCH_STATE_SNAPSHOT');assert.deepEqual(t.seen,[1,2]);
  } finally {t.cleanup();}
});

test('old callbacks and buffered events cannot leak into another room',()=>{
  const t=setup();
  try {
    t.socket.receive(1,'MATCH_STATE_SNAPSHOT');t.socket.receive(3);
    const oldReceive=t.socket.onmessage,oldClose=t.socket.onclose;
    t.client.connect('new');const next=Socket.instances.at(-1)!;next.open();
    oldReceive({data:JSON.stringify({event_type:'UNIT_DEPLOYED',match_id:'new',sequence_number:20})});
    oldClose({code:1006});
    next.receive(0,'MATCH_STATE_SNAPSHOT','new');next.receive(1,'UNIT_DEPLOYED','new','new-1');
    assert.deepEqual(t.seen,[1,0,1]);assert.equal(t.client.getStatus(),'connected');
  } finally {t.cleanup();}
});

test('clean remote close reconnects, explicit disconnect cancels retries and wake listeners',()=>{
  const t=setup();
  try {
    t.socket.onclose({code:1000});assert.equal(t.client.getStatus(),'reconnecting');
    t.client.disconnect();assert.equal(t.client.getStatus(),'disconnected');assert.equal(t.online.size,0);
  } finally {t.cleanup();}
});

test('zero-version stale snapshot cannot erase newer entities',()=>{
  const store=useMatchStore.getState();store.reset();
  const snapshot:any={match:{id:'m'},entities:[{id:'u'}],teams:[],viewer:{},current_round:1};
  store.applySnapshot(snapshot,10);store.applySnapshot({...snapshot,entities:[]},0);
  assert.equal(useMatchStore.getState().entities.length,1);
  assert.equal(useMatchStore.getState().lastSequenceNumber,10);store.reset();
});

test('connection handshake timeout also recovers an indefinitely connecting socket',async()=>{
  const t=setup({snapshotTimeoutMs:15});
  try {
    t.client.disconnect();t.client.connect('m');
    const connecting=Socket.instances.at(-1)!;
    await new Promise(r=>setTimeout(r,40));
    assert.equal(connecting.closed,true);assert.equal(t.client.getStatus(),'reconnecting');
  } finally {t.cleanup();}
});

test('reconnection continues beyond the old eight-attempt cutoff',()=>{
  const t=setup();
  try {
    (t.client as any).reconnectAttempts=12;
    t.socket.onclose({code:1006});
    assert.equal(t.client.getStatus(),'reconnecting');
    assert.ok((t.client as any).reconnectTimer);
  } finally {t.cleanup();}
});

test('unsequenced action replies cannot drain live events before a recovery snapshot',()=>{
  const t=setup();
  try {
    t.socket.receive(1,'MATCH_STATE_SNAPSHOT');
    t.client.requestSync();
    t.socket.receive(2);t.socket.receive(3);
    t.socket.receive(0,'ACTION_ACCEPTED');
    assert.deepEqual(t.seen,[1,0]);
    t.socket.receive(2,'MATCH_STATE_SNAPSHOT','m','recovery');
    assert.deepEqual(t.seen,[1,0,2,3]);
  } finally {t.cleanup();}
});

test('a full tick restores late opponent entities, deduplicates IDs and removes destroyed towers',()=>{
  const store=useMatchStore.getState();store.reset();
  const snapshot:any={match:{id:'m'},entities:[],teams:[],viewer:{team_id:'a'},current_round:1};
  store.applySnapshot(snapshot,10);
  const entity={id:'opponent',team_id:'b',unit_code:'mg_tower',unit_name:'Tower',entity_kind:'TOWER',current_hp:95,max_hp:100,current_shield:0,level:1,status:'ACTIVE',current_node_id:'slot',target_team_id:null,simulation_state:{}};
  const tick:any={event_id:'tick',match_id:'m',event_type:'COMBAT_TICK',sequence_number:11,payload:{entity_updates:[entity,entity],events:[]}};
  store.applyEvent(tick);store.applyEvent(tick);
  assert.equal(useMatchStore.getState().entities.length,1);
  assert.equal(useMatchStore.getState().entities[0].team_id,'b');
  store.applyEvent({...tick,sequence_number:12,payload:{entity_updates:[{...entity,current_hp:0,status:'DESTROYED'}],events:[{type:'ENTITY_DESTROYED',entity_id:entity.id}]}});
  assert.deepEqual(useMatchStore.getState().entities,[]);
  store.applyEvent(tick);
  assert.deepEqual(useMatchStore.getState().entities,[]);
  store.reset();
});
