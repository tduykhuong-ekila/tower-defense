import test from 'node:test';
import assert from 'node:assert/strict';
import { WebSocketClient } from '../src/services/websocket';
import { apiRequest } from '../src/services/api';
import { acceptBrowserSessionEvent, getBrowserSessionId, onBrowserSessionBlocked } from '../src/security/browserSession';

class SecuritySocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static current: SecuritySocket;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: unknown = null;
  constructor(public url: string) { SecuritySocket.current = this; }
  send() {}
  close() { this.readyState = 3; }
}

test('server block bypasses snapshot synchronization, stops socket and also propagates through HTTP', async () => {
  const originals = { window: globalThis.window, sessionStorage: globalThis.sessionStorage,
    WebSocket: globalThis.WebSocket, fetch: globalThis.fetch };
  Object.assign(globalThis, {
    window: { location: { protocol: 'http:', host: 'localhost', pathname: '/battle/m' } },
    sessionStorage: { getItem: () => 'participant' }, WebSocket: SecuritySocket,
  });
  const client = new WebSocketClient();
  let blocks = 0;
  let stateApplications = 0;
  onBrowserSessionBlocked(() => { blocks++; });
  client.setStateHandler(() => { stateApplications++; });
  try {
    client.connect('m');
    const socket = SecuritySocket.current;
    assert.equal(new URL(socket.url).searchParams.get('browser_session'), getBrowserSessionId());
    socket.readyState = 1;
    socket.onopen?.();
    client.send('BUILD_REQUEST', {});
    const block = { event_type: 'SESSION_BLOCKED', match_id: 'm', sequence_number: 0, payload: { reload_required: true } };
    socket.onmessage?.({ data: JSON.stringify(block) });
    assert.equal(blocks, 1);
    assert.equal(socket.readyState, 3);
    assert.equal(client.getStatus(), 'disconnected');
    assert.equal(stateApplications, 0);
    assert.equal(client.getDiagnostics().httpRecoveryPending, false);
    assert.equal(acceptBrowserSessionEvent(block), true);
    assert.equal(blocks, 1, 'duplicate HTTP acknowledgement cannot unlock or remount the game');
    let requestHeaders: Headers | undefined;
    globalThis.fetch = async (_url, options) => {
      requestHeaders = new Headers(options?.headers);
      return new Response(JSON.stringify({ error: 'blocked', event: block }), { status: 403 });
    };
    await assert.rejects(apiRequest('/matches/m/snapshot/'), /blocked/);
    assert.equal(requestHeaders?.get('X-Browser-Session'), getBrowserSessionId());
    assert.equal(requestHeaders?.get('X-Participant-Token'), 'participant');
    assert.equal(blocks, 1);
  } finally {
    client.disconnect();
    Object.assign(globalThis, originals);
  }
});
