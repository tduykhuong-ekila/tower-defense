import test from 'node:test';
import assert from 'node:assert/strict';
import { WebSocketClient, SnapshotLoader } from '../src/services/websocket';
import { ServerEnvelope } from '../src/types/realtime';
import { useMatchStore } from '../src/stores/matchStore';

class Socket {
  static OPEN = 1; static CONNECTING = 0; static latest: Socket;
  readyState = 0; sent: any[] = [];
  onopen: any; onmessage: any; onclose: any; onerror: any;
  constructor(_url: string) { Socket.latest = this; }
  send(data: string) { this.sent.push(JSON.parse(data)); }
  close() { this.readyState = 3; }
  open() { this.readyState = 1; this.onopen?.(); }
  receive(envelope: ServerEnvelope) { this.onmessage?.({data: JSON.stringify(envelope)}); }
}
const event = (sequence: number, type = 'TOWER_BUILT', payload: any = {}, match = 'm'): ServerEnvelope => ({
  match_id: match, event_id: `${match}-${type}-${sequence}`, event_type: type, sequence_number: sequence,
  server_timestamp: new Date().toISOString(), payload,
});
const opponent = {id: 'opponent-tower', team_id: 'b', tower_code: 'mg_tower', unit_code: 'mg_tower',
  entity_id: 'opponent-tower', entity_kind: 'TOWER', current_hp: 100, max_hp: 100,
  current_node_id: 'slot', node_id: 'slot', status: 'ACTIVE'};
const snapshot = (sequence: number, entities: any[] = [], match = 'm') => event(sequence, 'MATCH_STATE_SNAPSHOT', {
  match: {id: match, configuration: {}}, entities, teams: [], viewer: {team_id: 'a'}, current_round: 1,
}, match);
const pause = (ms = 0) => new Promise(resolve => setTimeout(resolve, ms));
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(r => { resolve = r; });
  return {promise, resolve};
}
function setup(options = {}, loader: SnapshotLoader = () => new Promise(() => {})) {
  const saved = {WebSocket: globalThis.WebSocket, window: globalThis.window, sessionStorage: globalThis.sessionStorage};
  const errors: unknown[][] = [], oldError = console.error, oldWarn = console.warn;
  console.error = (...args) => errors.push(args); console.warn = (...args) => errors.push(args);
  Object.assign(globalThis, {WebSocket: Socket, window: {location: {protocol: 'http:', host: 'localhost'}},
    sessionStorage: {getItem: () => null}});
  const client = new WebSocketClient(options, loader);
  useMatchStore.getState().reset();
  client.setStateHandler(e => useMatchStore.getState().applyEvent(e));
  client.connect('m');
  const socket = Socket.latest; socket.open();
  return {client, socket, errors, cleanup() {
    client.disconnect(); useMatchStore.getState().reset();
    console.error = oldError; console.warn = oldWarn; Object.assign(globalThis, saved);
  }};
}

test('failed build application is not acknowledged; snapshot restores opponent without reload', async () => {
  const http = deferred<ServerEnvelope>();
  const t = setup({}, () => http.promise);
  try {
    t.socket.receive(snapshot(1));
    t.client.setStateHandler(e => {
      if (e.event_type === 'TOWER_BUILT') throw new Error('injected reducer failure');
      useMatchStore.getState().applyEvent(e);
    });
    t.socket.receive(event(2, 'TOWER_BUILT', opponent));
    assert.equal(t.client.getDiagnostics().appliedSequence, 1);
    assert.equal(t.client.getDiagnostics().applicationErrors, 1);
    assert.equal(t.client.getStatus(), 'syncing');
    assert.equal(t.socket.sent.at(-1).event_type, 'STATE_SYNC_REQUEST');
    http.resolve(snapshot(2, [opponent])); await pause();
    assert.equal(t.client.getStatus(), 'connected');
    assert.equal(useMatchStore.getState().entities[0].id, opponent.id);
    assert.equal(t.client.getDiagnostics().appliedSequence, 2);
  } finally {t.cleanup();}
});

test('failed initial snapshot does not clear pending state or mark successful sync', () => {
  const t = setup();
  try {
    t.client.setStateHandler(() => {throw new Error('injected snapshot failure');});
    t.socket.receive(snapshot(5));
    assert.equal(t.client.getDiagnostics().appliedSequence, 0);
    assert.equal(t.client.getDiagnostics().lastSnapshotAt, 0);
    assert.equal(t.client.getDiagnostics().syncPending, true);
    assert.equal(t.client.getStatus(), 'syncing');
    t.client.setStateHandler(e => useMatchStore.getState().applyEvent(e));
    // Retry the same ID: it must not have been marked as seen on failure.
    t.socket.receive(snapshot(5));
    assert.equal(t.client.getStatus(), 'connected');
    assert.equal(useMatchStore.getState().lastSequenceNumber, 5);
  } finally {t.cleanup();}
});

test('UI observer failure cannot prevent store updates or the next deployment', () => {
  const t = setup();
  try {
    t.socket.receive(snapshot(1));
    t.client.onEvent(() => {throw new Error('injected animation failure');});
    t.socket.receive(event(2, 'TOWER_BUILT', opponent));
    t.socket.receive(event(3, 'UNIT_DEPLOYED', {...opponent, entity_id: 'opponent-unit', unit_code: 'infantry'}));
    assert.deepEqual(useMatchStore.getState().entities.map(e => e.id), ['opponent-tower', 'opponent-unit']);
    assert.equal(t.client.getDiagnostics().appliedSequence, 3);
    assert.equal(t.client.getDiagnostics().applicationErrors, 0);
    assert.equal(t.client.getStatus(), 'connected');
  } finally {t.cleanup();}
});

test('routine repair keeps contiguous builds live and rejects an overtaken snapshot', () => {
  const t = setup();
  try {
    t.socket.receive(snapshot(1)); t.client.requestSync(false);
    t.socket.receive(event(2, 'TOWER_BUILT', opponent));
    t.socket.receive(event(3, 'UNIT_DEPLOYED', {...opponent, entity_id: 'opponent-unit', unit_code: 'infantry'}));
    assert.equal(useMatchStore.getState().entities.length, 2);
    assert.equal(t.client.getStatus(), 'connected');
    t.socket.receive(snapshot(2));
    assert.equal(useMatchStore.getState().entities.length, 2);
    assert.equal(t.client.getDiagnostics().appliedSequence, 3);
    assert.equal(t.client.getDiagnostics().snapshotRequested, false);
  } finally {t.cleanup();}
});

test('a real gap upgrades routine repair to blocking and replays its newer tail once', () => {
  const t = setup();
  try {
    t.socket.receive(snapshot(1)); t.client.requestSync(false);
    t.socket.receive(event(3, 'TOWER_BUILT', opponent));
    assert.equal(t.client.getStatus(), 'syncing');
    assert.equal(t.socket.sent.length, 1);
    t.socket.receive(snapshot(2));
    assert.equal(t.client.getStatus(), 'connected');
    assert.equal(useMatchStore.getState().entities.length, 1);
    assert.equal(t.client.getDiagnostics().appliedSequence, 3);
  } finally {t.cleanup();}
});

test('lost WebSocket snapshot falls back to HTTP and later live events continue', async () => {
  let calls = 0;
  const t = setup({httpFallbackMs: 5, snapshotTimeoutMs: 1000}, async () => {calls++; return snapshot(2, [opponent]);});
  try {
    t.socket.receive(snapshot(1)); t.client.requestSync();
    await pause(25);
    assert.equal(calls, 1);
    assert.equal(t.client.getStatus(), 'connected');
    assert.equal(useMatchStore.getState().entities[0].id, opponent.id);
    t.socket.receive(event(3, 'UNIT_DEPLOYED', {...opponent, entity_id: 'later-unit', unit_code: 'infantry'}));
    assert.equal(useMatchStore.getState().entities.length, 2);
  } finally {t.cleanup();}
});

test('stale HTTP response cannot roll back live entities or finish a newer pending repair', async () => {
  const http = deferred<ServerEnvelope>();
  const t = setup({httpFallbackMs: 5}, () => http.promise);
  try {
    t.socket.receive(snapshot(1)); t.client.requestSync(false); await pause(15);
    t.socket.receive(event(2, 'TOWER_BUILT', opponent));
    t.socket.receive(event(4, 'UNIT_DEPLOYED', {...opponent, entity_id: 'later-unit', unit_code: 'infantry'}));
    http.resolve(snapshot(1)); await pause();
    assert.equal(useMatchStore.getState().entities.length, 1);
    assert.equal(t.client.getDiagnostics().syncPending, true);
    assert.equal(t.client.getDiagnostics().snapshotRequested, true);
    t.socket.receive(snapshot(3, [opponent]));
    assert.equal(t.client.getStatus(), 'connected');
    assert.equal(useMatchStore.getState().entities.length, 2);
  } finally {t.cleanup();}
});

test('room switch aborts HTTP and rejects its late response even if loader ignores abort', async () => {
  const http = deferred<ServerEnvelope>(); let signal: AbortSignal | undefined;
  const t = setup({httpFallbackMs: 5}, (_match, s) => {signal = s; return http.promise;});
  try {
    await pause(15);
    t.client.connect('new'); const next = Socket.latest; next.open(); next.receive(snapshot(0, [], 'new'));
    assert.equal(signal?.aborted, true);
    http.resolve(snapshot(9, [opponent])); await pause();
    assert.equal(useMatchStore.getState().match?.id, 'new');
    assert.equal(t.client.getDiagnostics().appliedSequence, 0);
    assert.deepEqual(useMatchStore.getState().entities, []);
  } finally {t.cleanup();}
});

test('overtaken routine HTTP snapshot finishes its check without reconnecting a healthy stream', async () => {
  const http = deferred<ServerEnvelope>();
  const t = setup({httpFallbackMs: 5}, () => http.promise);
  try {
    t.socket.receive(snapshot(1)); t.client.requestSync(false); await pause(15);
    t.socket.receive(event(2, 'TOWER_BUILT', opponent));
    http.resolve(snapshot(1)); await pause();
    assert.equal(t.client.getDiagnostics().snapshotRequested, false);
    assert.equal(t.client.getDiagnostics().appliedSequence, 2);
    assert.equal(t.client.getStatus(), 'connected');
    assert.equal(useMatchStore.getState().entities.length, 1);
  } finally {t.cleanup();}
});

test('HTTP timeout releases the in-flight slot and repeated gaps coalesce', async () => {
  let calls = 0;
  const t = setup({httpFallbackMs: 5, httpTimeoutMs: 10, httpRetryMs: 50}, () => {calls++; return new Promise(() => {});});
  try {
    t.socket.receive(snapshot(1));
    for (let seq = 3; seq < 10; seq++) t.socket.receive(event(seq));
    await pause(30);
    assert.equal(calls, 1);
    assert.equal(t.client.getDiagnostics().httpRecoveryPending, false);
    assert.equal(t.socket.sent.length, 1);
  } finally {t.cleanup();}
});

test('a malformed HTTP snapshot is rejected and a valid socket snapshot still recovers', async () => {
  const t = setup({httpFallbackMs: 5}, async () => ({...snapshot(20), payload: {}}));
  try {
    await pause(20);
    assert.equal(t.client.getDiagnostics().appliedSequence, 0);
    assert.equal(t.client.getDiagnostics().syncPending, true);
    t.socket.receive(snapshot(2, [opponent]));
    assert.equal(t.client.getStatus(), 'connected');
    assert.equal(useMatchStore.getState().entities.length, 1);
  } finally {t.cleanup();}
});

test('failed application of a routine HTTP snapshot enters blocking recovery without acknowledging it', async () => {
  const t = setup({httpFallbackMs: 5}, async () => snapshot(2, [opponent]));
  try {
    t.socket.receive(snapshot(1));
    t.client.setStateHandler(e => {
      if (e.event_type === 'MATCH_STATE_SNAPSHOT') throw new Error('injected HTTP snapshot reducer failure');
      useMatchStore.getState().applyEvent(e);
    });
    t.client.requestSync(false); await pause(25);
    assert.equal(t.client.getDiagnostics().appliedSequence, 1);
    assert.equal(t.client.getDiagnostics().applicationErrors, 1);
    assert.equal(t.client.getStatus(), 'syncing');
    t.client.setStateHandler(e => useMatchStore.getState().applyEvent(e));
    t.socket.receive(snapshot(2, [opponent]));
    assert.equal(t.client.getStatus(), 'connected');
    assert.equal(useMatchStore.getState().entities[0].id, opponent.id);
  } finally {t.cleanup();}
});

test('snapshot of another room replaces previous store before deltas arrive, without page listeners', () => {
  const t = setup();
  try {
    t.socket.receive(snapshot(10, [opponent]));
    t.client.connect('new'); const next = Socket.latest; next.open();
    next.receive(snapshot(1, [], 'new'));
    next.receive(event(2, 'TOWER_BUILT', opponent, 'new'));
    assert.equal(useMatchStore.getState().match?.id, 'new');
    assert.equal(useMatchStore.getState().lastSequenceNumber, 2);
    assert.equal(useMatchStore.getState().entities.length, 1);
  } finally {t.cleanup();}
});
