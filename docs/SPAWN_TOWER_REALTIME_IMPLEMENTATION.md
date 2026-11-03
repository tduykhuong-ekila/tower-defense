# Spawn, tower combat and realtime implementation

Implemented 2026-10-21; final verification and local rollout 2026-10-22.

The [audit](SPAWN_TOWER_REALTIME_AUDIT.md) records the reproduced causes, including
the production-only lobby-to-battle socket lifecycle failure. Changes extend the
existing backend simulation and Phaser renderer; no graphics replacement or new
database migration is required.

## Movement and rally areas

`backend/apps/combat/balance.py` now sets `TROOP_MOVEMENT_SPEED = 4` in the existing
dimensionless conversion, replacing 2 once:

`map units/second = catalog movement × saved reference_hop_length / movement_baseline_round_seconds × 4`.

With the fallback length 80 and default baseline 30, a movement-1 troop travels
10.6667 map units/second. The two-team assigned route saves its actual mean edge
length and travels 11.3517 map units/second. No accumulated historical modifiers
or client speed multiplication are applied. Damage, 100 mobile HP, tower stats,
cooldowns, projectile timing, costs, rewards and base HP are unchanged.

The map now publishes `rally_areas` with `team_id`, `team_index`, `spawn_node_id`,
`entry_node_id`, `spawn_point` and a bounded `radius`. Snapshot and map REST APIs
use the same ordered team IDs. For team index `i` among `n` teams, map scale `s`:

`angle = 2π(i−1)/n + min(0.15, π/(2n))`

`spawn_point = (240s cos(angle), 240s sin(angle))`.

Examples for team 1: 2/4 teams `(237.3051, 35.8652)`; 8 teams
`(379.6881, 57.3842)`; 20 teams `(957.0406, 75.3207)`. Each team's own
`node_spawn_t{i}` is its gate at route distance zero. Compact projected 66×62 cell
candidates behind it, tested against actual sprite body bounds, support 30 Infantry, Tanks or Artillery and provide compact
two-dimensional gathering without repositioning existing troops. The radius is
the maximum distance of these reserved capacity candidates; ordinary five-unit
deployments occupy only the closest free cells.

Departure priority uses persisted formation order, creation time and stable ID.
Only the oldest eligible staging troop per team walks toward the shared gate;
other troops stay at their saved gathering positions. New live purchases cannot
occupy the gate ahead of older waiting troops. Road movement still uses body-based
clearance and independent local passing around attacking friendlies. New rooms
default to a 2-map-unit gap; explicit stored room gaps remain respected.

Every staging, road and passing segment spends the same authoritative physical
distance budget. Sent polylines include bends for smooth `MotionTrack` playback.
Preexisting saved queues/staging positions are preserved, including old approaches
outside the new patch; they walk into the road without teleportation or healing.
New deployments always use the common zero-distance entry.

## Tower combat

The existing engine already supported tower targets, shields, HP and destruction.
The range fix treats a tower slot connected to both endpoints of a road edge as
covering the intervening span at range 1. Previously the midpoint incorrectly
required a 1.5-hop endpoint detour; Infantry could skip the entire attack window.
Catalog attack ranges remain unchanged. Unconnected roads still use ordinary
continuous graph distance; destroyed/friendly/staging targets are excluded.
Grid-built towers are measured to their footprint rather than only their anchor:
attacker reach includes a half-hop target radius, and the spatial broad phase
searches that same extra distance. This lets Infantry engage towers whose legal
build clearance places their anchors just beyond one hop from a road.

`troop_target_priority` defaults to `["TOWER", "UNIT"]`, configurable in the match
configuration as either permutation. Eligible targets sort by that priority,
distance, then ID. The assigned base is attacked under the existing arrival rule
when there is no eligible entity target. Towers retain closest-threat selection
and fire before the simultaneous troop tier.

Damage and cooldowns remain per attacker. Shield absorption and zero-HP clamping
remain authoritative. Remaining simultaneous intents skip an already killed
target, preventing extra zero-HP impacts. Destruction is persisted with
`destroyed_at`, emitted once, excluded from later ticks and restored snapshots,
and shown through existing impact/HP/death effects on all clients. Build occupancy
keeps the existing active/queued/disabled-only rule; this update adds no new slot
rebuild policy.

## Realtime and persistence

BattlePage now requests a fresh snapshot immediately after attaching listeners
and connecting, including when `connect` reuses the lobby socket. This restores
opponents created while the lazy battlefield page was loading. Initialization
does not depend on the player's first purchase.

Public events retain their committed match-wide envelope, stable event ID,
monotonic sequence/state version and server timestamp. Match/REST/socket/scene IDs
remain consistent. Existing match row locking, `transaction.on_commit`, Redis fanout,
per-viewer private redaction and durable outbox retries are retained.

Tick entity updates now include owner, type, display name, max HP and level in
addition to physical/combat state, HP and status. Zustand can upsert an unknown
late entity directly; Phaser reconciles it by stable ID. Older partial deltas
still request a full snapshot. Snapshot recovery holds all buffered live events
until the snapshot arrives, even when an unsequenced action reply intervenes.
Existing watchdog/reconnect, heartbeat, gap detection, stale-frame protection
and scene readiness buffering remain active.

Formation body data now uses JSON-stable lists, avoiding repeated bulk writes
for stationary rally troops after database reload.

The running Docker stack also exposed a Redis idle-disconnect defect: Channels'
5-second blocking receive raced redis-py 8's default 5-second read timeout.
`config/settings/base.py` now explicitly configures a 10-second read timeout and
5-second connection timeout. The new idle regression waits beyond a blocking poll,
then checks PING/PONG and both deployment directions through real Redis. See the
[confirmed production transport audit](SPAWN_TOWER_REALTIME_AUDIT.md#additional-confirmed-production-transport-cause-2026-10-22)
and [upstream report](https://github.com/django/channels_redis/issues/422).

## Files changed

- Backend: combat `balance.py`, `formation.py`, `navigation.py`, `continuous.py`,
  `continuous_service.py`, `map.py`, `views.py`; match `defaults.py`, `serializers.py`;
  realtime `services.py`.
- Backend runtime: `config/settings/base.py` sets Redis timeouts explicitly.
- Frontend: `BattlePage.tsx`, WebSocket client, match store, map types and
  `BattleScene.ts`. Existing banners mark each rally gate persistently.
- Tests: `test_spawn_tower_realtime.py`, movement/speed test expectations,
  `realtime-recovery.test.ts`, `spawn-tower-realtime.browser.mjs` and its single-mount
  production-lifecycle fixture.
- Documentation: this report, audit, README, balancing, architecture and event
  contract. Earlier movement reports are explicitly marked historical.

## Verification and rollout

Final results: **257 backend tests passed**; six PostgreSQL-only tests were
skipped in SQLite and then **34 tests passed on PostgreSQL**, including all six
concurrency tests and the new regressions. **69 frontend tests passed**. Four
additional fanout/reconnect/idle tests passed through a real Redis channel layer
using the production timeout configuration. Ruff, Django checks, migration drift check, TypeScript and production build
passed. Vite retains its existing advisory about the large Phaser bundle.

Evidence: [test results](qa/spawn-tower-realtime-tests.json),
[browser results](qa/spawn-tower-realtime-browser.json),
[standard capacity](qa/spawn-tower-realtime-standard-benchmark.json),
[30-troop capacity](qa/spawn-tower-realtime-benchmark.json) and
[baseline reproduction](qa/spawn-tower-realtime-before.json).

The browser suite uses independent authenticated Chrome contexts and disposable
rooms, including both action orders, lazy navigation, Battle-time purchases,
retargeting, round transitions, offline/reconnect recovery, out-of-order ticks,
identical tower hits/death and independent follower movement. All three scenarios
converged with **zero divergent entities, zero duplicate sprites and zero page
errors**. Every dedicated tower battle produced exactly 20 Infantry hits of 5 HP
and one tower destruction, seen identically on both clients.

| Teams | Deploy-to-both-sprites ms (4 samples) | Delivery p95 A/B ms | Frames with attacking + moving troops |
|---|---|---|---|
| 4 | 112 / 162 / 72 / 45 | 98 / 88 | 70 |
| 8 | 124 / 58 / 59 / 39 | 162 / 172 | 37 |
| 20 | 144 / 125 / 51 / 71 | 176 / 166 | 20 |

Local SQLite benchmarks ran 30 committed ticks per scenario with 3 towers per
team. At the default 5 troops per team, 20 teams/160 entities took median **51.22
ms**, p95 **77.95 ms**. At 30 troops per team, 20 teams/660 entities took median
**173.36 ms**, p95 **290.31 ms**. The latter exceeds the 200 ms tick budget at p95;
that maximum-capacity stress case cannot promise a sustained 5 Hz on this local
SQLite setup. Production PostgreSQL/multiple-room/remote-network throughput needs
its own profiling; these measurements are local single-room results. The
scheduler retains delayed ticks instead of discarding combat or repeating damage.

Reproduce unit/build checks:

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/python manage.py check --settings=config.settings.test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
cd ../frontend
npm test
npm run build
```

For browser verification, run `TEST_SCHEDULER=1 TEST_BACKEND_PORT=8011
.venv/bin/python tests/browser_preview.py` from backend; run Vite with
`API_PROXY_TARGET=http://127.0.0.1:8011 npm run dev -- --host 127.0.0.1 --port 5177`
from frontend, then `node tests/spawn-tower-realtime.browser.mjs`. Chrome and a
resolvable Playwright installation are required (the verification used the bundled
workspace runtime via `NODE_PATH`). The fixture uses one React effect mount to
match production lifecycle behavior. No existing database is touched by this
harness. `AUDIT_BEFORE=1` applies only to the original code and deliberately
expects the initialization defect; run the default mode against the corrected code.

Rebuild/restart backend and frontend together. Production uses shared Redis and
PostgreSQL; the browser harness uses a disposable single-process SQLite database.
Existing rooms retain their phase rules and saved physical positions. No new
migration is needed; existing migrations must already have been applied.

Local Docker rollout completed on 2026-10-22: backend/frontend rebuilt and
restarted with the existing PostgreSQL and Redis data retained. The running backend
reports authoritative speed 4 and explicit Redis timeouts 10/5 seconds. A private
verification channel inside the running container survived 12 seconds of idle
blocking receive and then delivered a message successfully. Frontend and health
API return HTTP 200; database/channel layer are connected and the production page
boots with zero JavaScript errors. Evidence: [Docker verification](qa/spawn-tower-realtime-docker.json).
The app is available at `http://localhost:5173`. Disposable test servers were stopped.
