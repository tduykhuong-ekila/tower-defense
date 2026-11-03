# Spawn, tower combat and realtime audit

Audit date: 2026-10-21. Inspected the existing Django/Channels simulation and
React/Zustand/Phaser pipeline before changing production code. Existing art and
the legacy combat mode remain in scope for regression protection.

## Confirmed findings before implementation

### 1. Movement still uses the previous setting of 2

`backend/apps/combat/balance.py` defines `TROOP_MOVEMENT_SPEED = 2`. Its unit is a
dimensionless multiplier of the catalog's hops per reference round, converted
once to map-coordinate units per second:

`catalog movement × saved reference_hop_length / movement_baseline_round_seconds × TROOP_MOVEMENT_SPEED`.

`initialize_route` saves the route's mean physical hop length. The fixed-step
engine spends the resulting distance budget; Phaser projects saved positions
and interpolates them with `MotionTrack`. No extra speed multiplier is needed.

### 2. A shared spawn node does not enforce a shared road entry

`formation.initialize_spawn` assigns stable free cells from
`navigation.staging_slots`. These are bounded, but spaced 72×70 projected pixels
apart and spread behind the spawn. `staging_entry` chooses the nearest location
on the first three route edges. `move_independently` can choose another free
entry farther along the road and admits every staging troop concurrently.

A five-infantry reproduction on the two-team map produced entry distances
`[0, 35.97, 35.97, 35.97, 106.54]`. Thus troops can bypass earlier waypoints and
leave in physical-arrival order rather than durable formation order. Existing
road body clearance and local passing around attacking troops should be kept.

### 3. Infantry can miss towers despite existing tower-target support

`ContinuousEngine.candidates` already includes enemy towers, and existing damage,
shield absorption, destruction persistence, and Phaser attack/HP/death rendering
are present. Missing support for the TOWER entity kind is not the root cause.

`continuous.distance` computes a detour through an edge endpoint. A tower slot
adjacent to both ends of a road edge is 1 hop from either endpoint but **1.5 hops
from its midpoint**. Standard infantry range is 1. A reproduction halfway between
`node_lane_t2_3` and `node_lane_t2_2`, beside `node_tower_t2_slot2`, produced zero
infantry attacks. A moving fixed-step troop generally does not land exactly on
an intermediate node, so it skips that tower's entire supposed coverage span.

Target ordering is nearest entity then ID, with no explicit troop/tower priority.
The engine excludes destroyed/friendly/staging entities and has independent
cooldowns. Tower attacks happen before troop attacks. Those rules and damage
values must be retained while correcting continuous coverage and priority.

### 4. Reused lobby socket loses the battlefield initialization snapshot

Confirmed in a real Chrome session using production effect behavior (single
mount), an authenticated lobby socket, and a delayed lazy BattlePage module:

1. Enter lobby and receive its initial snapshot before battle listeners exist.
2. Start match; the lobby listener navigates to the lazy battle page.
3. Deploy an opponent troop while that page loads.
4. BattlePage resets the store and installs its listener, then calls `connect`.
5. `WebSocketClient.connect` returns immediately for the already open socket.
   No initial snapshot is delivered to the new listener. The REST refresh loads
   only the local team's entities. The opponent troop is absent.
6. Calling the same `requestSync` that follows a player's own purchase restores
   the troop immediately, without reloading.

Evidence: `docs/qa/spawn-tower-realtime-before.json`. Reproduce against the disposable
backend with `AUDIT_BEFORE=1 node tests/spawn-tower-realtime.browser.mjs` in frontend.
The fixture disables development StrictMode's second effect mount because its
disconnect/reconnect masks this production lifecycle defect.

Affected code: `LobbyPage.tsx` leaves the shared socket alive on navigation;
`BattlePage.tsx` resets state without explicitly requesting a fresh snapshot;
`services/websocket.ts` silently reuses an open same-match connection. Action
order and page-loading timing determine which client has missed opponent state.

No incorrect match group or opponent ownership filter was found. All authorized
consumers immediately join `match.{id}`. Persisted public events already fan out
to that group after `transaction.on_commit`; per-viewer redaction preserves the
sequence even for private events. Event IDs and sequence allocation are durable
and serialized by the match lock. Snapshot reads also hold that lock.

## Recovery and concurrency audit

- Reconnect, PING/PONG watchdog, sequence-gap buffering, outbox retry and versioned
  snapshots already exist; they should be repaired/extended rather than replaced.
- Tick entity deltas lack owner/type/maximum HP and the store only updates known
  IDs. Late missing entities cannot be reconstructed directly from a tick.
- WebSocket buffer draining is not gated consistently during snapshot recovery;
  unsequenced replies can prematurely drain it.
- Phaser keeps a registry keyed by authoritative ID and buffers events until scene
  readiness. Live death animations already suppress duplicate destruction.
- Deployment, construction and ticks acquire the match row before team/entity
  locks. Purchase idempotency is persisted; simulation cannot overwrite a troop
  created after its locked read. SQLite preview is single-process; production
  config uses PostgreSQL and shared Redis.
- Existing construction rules treat only live/queued/disabled occupants as occupied.
  Preserve that existing rebuild policy; do not introduce a new one.
- Troop HP normalization to 100, half-damage carry, tower damage/costs, base HP,
  reward +20 once, phase rules, map scaling, minimap and camera are already present.

## Baseline verification

22 existing focused backend tests passed before production changes. Additional
regressions will cover the reproduced lifecycle and continuous-range defects,
centralized sequential admission, full tick reconciliation, both action orders,
reconnect and 4/8/20-team rooms. Final results and limits are recorded separately
in `SPAWN_TOWER_REALTIME_IMPLEMENTATION.md`.

## Additional findings reproduced during integration verification

- A live deployment could reuse the center spawn cell while an older troop was
  already approaching it. Sequencing departures then exposed an admission
  deadlock. Reserve the gate whenever older staging troops exist; a new purchase
  uses another free cell. The regression also verifies every troop eventually exits.
- `formation_body` was assigned a tuple on each simulation read, but persisted
  JSON returns a list. This made otherwise unchanged stationary troop state
  unequal every tick, forcing hundreds of unnecessary database writes at capacity.
  A service-level regression checks that a waiting troop is absent from bulk updates.
- Simultaneous troop intents could emit a 21st zero-HP hit after 20 Infantry hits
  had destroyed a 100-HP tower. HP did not go negative, but the extra event played
  a misleading impact. Skip remaining intents whose target HP already reached zero.

## Additional confirmed production transport cause (2026-10-22)

Post-build inspection of the running Docker stack found repeated WebSocket
disconnects with `redis.exceptions.TimeoutError: Timeout reading from redis:6379`
while health checks still reported Redis connected. The installed versions were
`channels_redis 4.3.0` and `redis 8.1.0`. Direct source inspection confirmed Channels'
blocking `BZPOPMIN` polls for 5 seconds, and redis-py 8's default socket read timeout
is also 5 seconds. Healthy idle connections therefore raced the read timeout.
Fast fanout tests did not reveal the defect because each completed in under 5s.

`config/settings/base.py` had used a bare Redis URL, inheriting that read timeout.
It now supplies explicit connection kwargs: 10-second read timeout and 5-second
connection timeout. The read budget exceeds the channel layer's idle poll. Added
an integration regression that waits 6.2s without broadcasting, then verifies
PING/PONG and deployment in both directions; it is also run on real Redis with
the production host configuration.

The inspected behavior matches the primary upstream report
[channels_redis issue 422](https://github.com/django/channels_redis/issues/422).
The [channel layer source](https://github.com/django/channels_redis/blob/main/channels_redis/core.py)
and [host configuration contract](https://github.com/django/channels_redis#hosts)
support the explicit connection-kwargs fix. This is separate from the reproduced
lobby snapshot lifecycle defect; both affected realtime reliability.
