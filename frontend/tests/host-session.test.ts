import test from 'node:test';
import assert from 'node:assert/strict';
import { apiRequest, clearHostToken, getAuthToken, getHostToken, getSavedHostSessions, setHostToken } from '../src/services/api';

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
    clear: () => values.clear(),
  };
}

test('host recovery survives a new tab, chooses each room credential, and keeps participant identity separate', async () => {
  const original = { sessionStorage: globalThis.sessionStorage, localStorage: globalThis.localStorage, window: globalThis.window, fetch: globalThis.fetch };
  const session = memoryStorage(), persistent = memoryStorage();
  const location = { pathname: '/host', search: '' };
  Object.assign(globalThis, { sessionStorage: session, localStorage: persistent, window: { location } });
  try {
    setHostToken('host-a', { id: 'room-a', name: 'Room A', room_code: 'AAAAAA' });
    setHostToken('host-b', { id: 'room-b', name: 'Room B', room_code: 'BBBBBB' });
    session.clear(); // Closing a tab loses sessionStorage, while localStorage survives.
    assert.equal(getSavedHostSessions().length, 2);
    assert.equal(getHostToken('room-a'), 'host-a');
    assert.equal(getHostToken('room-b'), 'host-b');
    location.pathname = '/battle/room-a';
    location.search = '?host=1';
    assert.equal(getAuthToken(), 'host-a');

    globalThis.fetch = async (_url, options) => {
      assert.equal((options!.headers as Record<string, string>)['X-Host-Token'], 'host-b');
      return Response.json({});
    };
    await apiRequest('/matches/room-b/host-telemetry/');

    location.search = '';
    session.setItem('tower_participant_token', 'participant-a');
    assert.equal(getAuthToken(), 'participant-a');
    globalThis.fetch = async (_url, options) => {
      const headers = options!.headers as Record<string, string>;
      assert.equal(headers['X-Host-Token'], undefined);
      assert.equal(headers['X-Participant-Token'], 'participant-a');
      return Response.json({});
    };
    await apiRequest('/matches/room-a/');
    clearHostToken();
    assert.equal(getHostToken(), null);
    assert.deepEqual(getSavedHostSessions(), []);
  } finally {
    Object.assign(globalThis, original);
  }
});

test('existing session tokens migrate and disabled or malformed persistent storage is tolerated', () => {
  const original = { sessionStorage: globalThis.sessionStorage, localStorage: globalThis.localStorage };
  const session = memoryStorage(), persistent = memoryStorage();
  Object.assign(globalThis, { sessionStorage: session, localStorage: persistent });
  try {
    session.setItem('tower_host_token', 'legacy-host');
    assert.equal(getHostToken(), 'legacy-host');
    session.clear();
    assert.equal(getHostToken(), 'legacy-host');
    persistent.setItem('tower_host_sessions', '{broken');
    assert.deepEqual(getSavedHostSessions(), []);
    Object.assign(globalThis, { localStorage: { getItem() { throw new Error('disabled'); }, setItem() { throw new Error('disabled'); } } });
    setHostToken('current-host', { id: 'room', name: 'Room', room_code: 'ABCDEF' });
    assert.equal(getHostToken(), 'current-host');
    assert.deepEqual(getSavedHostSessions(), []);
  } finally {
    Object.assign(globalThis, original);
  }
});
