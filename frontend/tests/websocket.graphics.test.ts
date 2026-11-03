import test from "node:test";
import assert from "node:assert/strict";
import { WebSocketClient } from "../src/services/websocket";

class SocketStub {
  static OPEN = 1;
  static CONNECTING = 0;
  static instances: SocketStub[] = [];
  readyState = 0;
  closed = false;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: unknown = null;
  constructor(public url: string) {
    SocketStub.instances.push(this);
  }
  close() {
    this.closed = true;
    this.readyState = 3;
  }
  send(data: string) {
    this.sent.push(data);
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  receive(event: unknown) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}
test("real socket client changes rooms, resets sequence, deduplicates and reconnects safely", () => {
  const originals = {
    WebSocket: globalThis.WebSocket,
    window: globalThis.window,
    sessionStorage: globalThis.sessionStorage,
  };
  Object.assign(globalThis, {
    WebSocket: SocketStub,
    window: { location: { protocol: "http:", host: "localhost:5173" } },
    sessionStorage: { getItem: () => null },
  });
  const client = new WebSocketClient();
  let received = 0;
  client.on("any", () => received++);
  try {
    client.connect("room-a");
    const first = SocketStub.instances.at(-1)!;
    first.open();
    first.receive({event_type:"MATCH_STATE_SNAPSHOT",match_id:"room-a",sequence_number:19,payload:{}});
    received = 0;
    const envelope = {
      event_id: "same-id",
      match_id: "room-a",
      event_type: "UNIT_DEPLOYED",
      sequence_number: 20,
      payload: {},
    };
    first.receive(envelope);
    first.receive(envelope);
    assert.equal(received, 1);
    client.connect("room-b");
    const second = SocketStub.instances.at(-1)!;
    second.open();
    second.receive({event_type:"MATCH_STATE_SNAPSHOT",match_id:"room-b",sequence_number:0,payload:{}});
    received--;
    assert.ok(first.closed);
    assert.ok(second.url.includes("/room-b/"));
    second.receive({ ...envelope, match_id: "room-b", sequence_number: 1 });
    assert.equal(received, 2);
    assert.equal(
      second.sent.length,
      0,
      "Room B must not inherit a sequence gap from A",
    );
    client.disconnect();
    client.connect("room-b");
    const third = SocketStub.instances.at(-1)!;
    third.open();
    third.receive({event_type:"MATCH_STATE_SNAPSHOT",match_id:"room-b",sequence_number:0,payload:{}});
    received--;
    third.receive({ ...envelope, match_id: "room-b", sequence_number: 1 });
    assert.equal(received, 3);
  } finally {
    client.disconnect();
    Object.assign(globalThis, originals);
  }
});

test('many sequence gaps coalesce to one in-flight recovery snapshot', () => {
  const originals = {WebSocket:globalThis.WebSocket,window:globalThis.window,sessionStorage:globalThis.sessionStorage};
  Object.assign(globalThis,{WebSocket:SocketStub,window:{location:{protocol:'http:',host:'localhost:5173'}},sessionStorage:{getItem:()=>null}});
  const client=new WebSocketClient();
  try {
    client.connect('room-20');const socket=SocketStub.instances.at(-1)!;socket.open();
    const event=(seq:number,type='COINS_UPDATED')=>({event_id:`event-${seq}-${type}`,match_id:'room-20',event_type:type,sequence_number:seq,payload:{}});
    socket.receive(event(0,'MATCH_STATE_SNAPSHOT'));socket.receive(event(1));socket.receive(event(5));socket.receive(event(10));socket.receive(event(15));
    assert.equal(socket.sent.length,1);
    socket.receive(event(15,'MATCH_STATE_SNAPSHOT'));socket.receive(event(20));
    assert.equal(socket.sent.length,2);
  } finally {client.disconnect();Object.assign(globalThis,originals);}
});
