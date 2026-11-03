import test from 'node:test';
import assert from 'node:assert/strict';
import { useMatchStore } from '../src/stores/matchStore';
import { ServerEnvelope, MatchSnapshotPayload } from '../src/types/realtime';

test('matchStore initial state and reset', () => {
  const store = useMatchStore.getState();
  store.reset();

  assert.equal(useMatchStore.getState().match, null);
  assert.equal(useMatchStore.getState().coins, 100);
  assert.equal(useMatchStore.getState().lastSequenceNumber, 0);
  assert.equal(useMatchStore.getState().connectionStatus, 'disconnected');
});

test('matchStore applySnapshot sets authoritative state', () => {
  useMatchStore.getState().reset();
  useMatchStore.getState().setCurrentTeamId('team-alpha');

  const snapshot: MatchSnapshotPayload = {
    match: {
      id: 'match-1',
      name: 'Arena 1',
      room_code: 'ROOM01',
      status: 'ACTIVE',
      phase: 'WAR',
      is_locked: true,
      created_at: new Date().toISOString(),
      configuration: {},
    },
    teams: [
      {
        id: 'team-alpha',
        name: 'Team Alpha',
        base_hp: 480,
        initial_base_hp: 500,
        base_shield: 20,
        score: 10,
        status: 'ACTIVE',
        is_ready: true,
        coins: 140,
        members_count: 2,
        active_units_count: 1,
        towers_count: 1,
      },
      {
        id: 'team-beta',
        name: 'Team Beta',
        base_hp: 500,
        initial_base_hp: 500,
        base_shield: 0,
        score: 0,
        status: 'ACTIVE',
        is_ready: true,
        members_count: 2,
        active_units_count: 0,
        towers_count: 0,
      },
    ],
    entities: [
      {
        id: 'entity-1',
        team_id: 'team-alpha',
        team_name: 'Team Alpha',
        unit_code: 'infantry',
        unit_name: 'Infantry',
        entity_kind: 'UNIT',
        current_hp: 100,
        max_hp: 100,
        current_shield: 0,
        level: 1,
        status: 'ACTIVE',
        current_node_id: 'node-lane-1',
        target_team_id: 'team-beta',
      },
    ],
    current_round: 2,
    combat_stats: {},
    viewer: {
      is_host: false,
      team_id: 'team-alpha',
      coins: 140,
      unlocked_units: ['infantry', 'guard_tower', 'tank'],
      current_question: null,
      pending_reward: null,
    },
  };

  useMatchStore.getState().applySnapshot(snapshot, 15);

  const state = useMatchStore.getState();
  assert.equal(state.match?.id, 'match-1');
  assert.equal(state.match?.phase, 'WAR');
  assert.equal(state.coins, 140);
  assert.equal(state.lastSequenceNumber, 15);
  assert.equal(state.teams.length, 2);
  assert.equal(state.entities.length, 1);
  assert.deepEqual(state.unlockedUnits, ['infantry', 'guard_tower', 'tank']);
});

test('matchStore applyEvent updates state predictably and monotonically', () => {
  useMatchStore.getState().reset();
  useMatchStore.getState().setCurrentTeamId('team-alpha');

  // 1. Coins updated
  const coinEnvelope: ServerEnvelope = {
    event_id: 'ev-1',
    match_id: 'match-1',
    event_type: 'COINS_UPDATED',
    sequence_number: 16,
    server_timestamp: new Date().toISOString(),
    payload: {
      team_id: 'team-alpha',
      new_balance: 180,
    },
  };
  useMatchStore.getState().applyEvent(coinEnvelope);
  assert.equal(useMatchStore.getState().coins, 180);
  assert.equal(useMatchStore.getState().lastSequenceNumber, 16);

  // 2. Unit deployed
  const deployEnvelope: ServerEnvelope = {
    event_id: 'ev-2',
    match_id: 'match-1',
    event_type: 'UNIT_DEPLOYED',
    sequence_number: 17,
    server_timestamp: new Date().toISOString(),
    payload: {
      entity_id: 'unit-tank-1',
      team_id: 'team-alpha',
      unit_code: 'tank',
      unit_name: 'Tank',
      current_node_id: 'node-spawn-alpha',
      target_team_id: 'team-beta',
      coins_after: 140,
    },
  };
  useMatchStore.getState().applyEvent(deployEnvelope);
  assert.equal(useMatchStore.getState().coins, 140);
  assert.equal(useMatchStore.getState().entities.length, 1);
  assert.equal(useMatchStore.getState().entities[0].unit_code, 'tank');
  assert.equal(useMatchStore.getState().lastSequenceNumber, 17);

  // 3. Combat resolved & base damaged
  const combatEnvelope: ServerEnvelope = {
    event_id: 'ev-3',
    match_id: 'match-1',
    event_type: 'COMBAT_RESOLVED',
    sequence_number: 18,
    server_timestamp: new Date().toISOString(),
    payload: {
      round_number: 3,
      events: [
        {
          type: 'BASE_DAMAGED',
          target_team_id: 'team-beta',
          damage: 50,
          remaining_hp: 450,
        },
      ],
      eliminated_team_ids: [],
    },
  };
  useMatchStore.getState().applyEvent(combatEnvelope);
  assert.equal(useMatchStore.getState().currentRound, 4); // round 3 resolved; planning round 4 is open
  assert.equal(useMatchStore.getState().combatLogs.length, 1);
  assert.equal(useMatchStore.getState().lastSequenceNumber, 18);
});

test('sequence gap detection logic identifies gaps', () => {
  let gapDetected = false;
  let lastSequenceNumber = 10;

  function handleIncomingSequence(seq: number) {
    if (lastSequenceNumber > 0 && seq > lastSequenceNumber + 1) {
      gapDetected = true;
    }
    lastSequenceNumber = Math.max(lastSequenceNumber, seq);
  }

  // Next continuous event: 11
  handleIncomingSequence(11);
  assert.equal(gapDetected, false);
  assert.equal(lastSequenceNumber, 11);

  // Gap event: 14 received instead of 12
  handleIncomingSequence(14);
  assert.equal(gapDetected, true);
  assert.equal(lastSequenceNumber, 14);
});

test('event deduplication ignores identical event_id', () => {
  const seenEventIds = new Set<string>();
  let processCount = 0;

  function processEvent(envelope: { event_id: string }) {
    if (seenEventIds.has(envelope.event_id)) {
      return; // Deduplicated
    }
    seenEventIds.add(envelope.event_id);
    processCount++;
  }

  processEvent({ event_id: 'event-uuid-1' });
  processEvent({ event_id: 'event-uuid-1' }); // Duplicate
  processEvent({ event_id: 'event-uuid-2' });

  assert.equal(processCount, 2);
  assert.equal(seenEventIds.size, 2);
});
