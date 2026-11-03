# Realtime event contract

> Previous update (2026-10-21): `TROOP_MOVEMENT_SPEED = 4` replaces 2 in the same authoritative unit, with one rally gate per team and bidirectional snapshot recovery. See [implementation and verification](SPAWN_TOWER_REALTIME_IMPLEMENTATION.md).

Retain the existing envelope: `event_id`, `match_id`, `event_type`, `sequence_number`, `state_version` (same sequence), `server_timestamp`, `payload`. MatchEvent sequences are allocated under the match row lock, persisted in the same transaction as mutations, and broadcast via on_commit.

| Event | Audience / purpose |
|---|---|
| UNIT_DEPLOYED | Public match; stable entity_id, team_id, unit_code, HP, authoritative spawn_node, target_team_id, status. Upsert entity; never clone REST + socket results. |
| TOWER_BUILT | Public match; stable entity_id, team_id, tower_code, HP, node_id, status. Register tower and occupy build slot immediately. |
| TOWER_UPGRADED / BASE_REPAIRED / EMP_FIRED / UNIT_RETARGETED | Reuse existing mutation contracts. |
| COINS_UPDATED / UNIT_UNLOCKED / question and reward events | Full payload only to owner and host. Other viewers receive EVENT_REDACTED with the same envelope ID/sequence and empty payload. No private balances, questions or unlock information is disclosed. |
| MATCH_PHASE_CHANGED / ROUND_STARTED | Existing lifecycle payload with status, phase, current_round, round_phase and timer_state. |
| BATTLE_STARTED / BATTLE_STOPPED | Phase boundary notification; no independent client clock. |
| COMBAT_TICK | Public compact committed state delta, described below. |
| MATCH_ENDED / LEADERBOARD_UPDATED | Existing immutable results, winner(s), final scores and awards. |
| MATCH_STATE_SNAPSHOT | Permission-filtered recovery authority. Includes all surviving entities, their partial-edge simulation_state, simulation_at and tick_interval_ms. |

A COMBAT_TICK payload contains:

```json
{
  "tick": 17,
  "simulation_at": "2026-10-21T07:00:03.400000+00:00",
  "tick_interval_ms": 200,
  "entity_updates": [{
    "id": "entity-uuid",
    "team_id": "owner-uuid",
    "unit_code": "infantry",
    "unit_name": "Infantry",
    "entity_kind": "UNIT",
    "max_hp": 80,
    "level": 1,
    "current_node_id": "node_lane_t1_2",
    "simulation_state": {"next_node_id": "node_lane_t1_3", "edge_progress": 0.12},
    "current_hp": 40,
    "current_shield": 0,
    "status": "ACTIVE",
    "target_team_id": "opponent-uuid"
  }],
  "events": [],
  "current_round": 1,
  "phase": "WAR",
  "round_phase": "BATTLE"
}
```

Only changed public entities appear. Route internals/reference lengths/fraction remainders are checkpointed in the database and recovery snapshot. Public state includes world position, movement polyline, movement/combat state, attack target and remaining cooldown. Full identity/type/HP fields let clients create a late missing sprite directly from a tick. Existing combat subevents carry exact HP/shield/damage values: UNIT_SPAWNED, UNIT_ATTACKED, TOWER_ATTACKED, BASE_DAMAGED, ENTITY_DESTROYED, SHIELD_GENERATED/EXPIRED, TOWER_ENABLED, UNIT_RETARGETED, BASE_DESTROYED, TEAM_ELIMINATED and TEAM_SCORE_UPDATED. No unchanged empty COMBAT_TICK is persisted/broadcast, so valid sequence numbers are contiguous even when simulation tick numbers skip in the event stream. This also limits log growth during idle battles.

Recovery snapshots carry the persisted `timer_state.simulation_at` as payload-level
`simulation_at` (null before the first tick), plus `tick_interval_ms`. Clients attach
that checkpoint time to snapshot entities before feeding the same interpolation
track used for ticks. Envelope `server_timestamp` is the response creation time,
not the simulation time. A snapshot must not stop live locomotion animations.

`broadcasted_at` is an outbox dispatch checkpoint, not proof of browser receipt. Failed sends leave it null; scheduler retries up to 200 pending rows per poll, including finished rooms. Crash after send/before checkpoint can duplicate an event. Stable IDs and sequence checks make this safe. The migration checkpoints historical events so upgrading does not flood clients with an old match log.

Clients buffer sequence gaps and request STATE_SYNC_REQUEST. A snapshot subsumes buffered sequences up to its high-water mark; consecutive later buffered events may then apply. Older snapshots/events cannot roll back newer state. Buffer capacity is 500 envelopes, event-ID cache 1000; overflow uses a fresh snapshot. Reconnect, visibility restoration and periodic snapshot repair stop stale movement. WebSocket is a transport; MatchEvent and database snapshots are the durable authority.

Existing consumers remain compatible with public spawn/build events. Clients must understand EVENT_REDACTED and COMBAT_TICK for continuous rooms. All viewers share one public match group; projection happens per consumer. InMemory Channels across multiple server processes cannot supply fan-out and is unsupported for production.

When battlefield listeners attach after lobby navigation, explicitly request a snapshot even when `connect` reuses an already open socket. Initial lobby snapshots and live events may have arrived before the battlefield existed. While a recovery snapshot is pending, unsequenced action acknowledgments cannot drain the live buffer.


## Large envelopes (2026-10-22)

Backend and frontend must be deployed together. Above 128 KiB, any snapshot or live envelope is serialized into `JSON_CHUNK` messages. Each wrapper has `event_type`, `match_id`, and `payload: {id, index, total, data}`. `id` identifies a transfer; `index` is zero-based and `data` contains up to 65,536 characters of the serialized original envelope. Join chunks in order and JSON-decode once. Only the reconstructed original envelope participates in event-ID/sequence handling or changes state; chunks themselves never advance a cursor. Privacy projection happens before chunking.

The client buffers one transfer, rejects invalid/missing/expired chunks, clears it on socket replacement, and uses existing snapshot recovery after errors. Limits are 30 seconds, 2,048 chunks and 128 MiB per transfer as operational memory safeguards. Snapshots subsume old deltas exactly as before. Large persisted events travel through Channels as `{type: "match_event", event_id: "..."}` references rather than oversized payloads; each consumer loads the committed event scoped to its match, applies viewer privacy, then streams it. Normal-sized events retain the existing format.

Infantry deployment/tick state now carries current/max HP 80 for new entities and a deterministic `crowd_offset`, with `world_position` and route progress owned by the server. Existing entities keep their stored maximum. Cosmetic offsets do not extend graph attack range. [Gameplay details and resource limits](INFANTRY_GAMEPLAY_UPDATE.md).
