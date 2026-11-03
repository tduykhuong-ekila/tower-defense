# Infantry gameplay update — 2026-10-22

Historical speed-6 implementation. The subsequent [Infantry fire-rate, speed-7 and animation fix](INFANTRY_FIRE_RATE_MOVEMENT_FIX.md) supersedes the speed, cooldown and screen-cell rendering details below.

## Result and scope

New Infantry move independently, use authoritative speed **6**, spawn with **80/80 HP**, and have **no gameplay deployment-count cap**. The existing 15-coin price, phase/authorization/unlock/target checks, match/team row locks, idempotency keys, independent cooldowns, damage, tower/base combat, reward rules and match lifecycle remain in use.

This targets the default **CONTINUOUS** game mode. Its backend controls movement; Phaser interpolates confirmed positions. Legacy round movement remains the existing hop resolver. Infantry purchase-limit exemption and new spawn HP apply to both modes. Tank, Artillery, other mobile types, towers and bases keep their existing HP and balancing. Vehicles retain their traffic/admission rules and the configured shared **non-Infantry** unit capacity.

## Root causes

The prior `navigation.move_independently` selected exactly one staging departure per team. Ordinary road motion still used `FormationTraffic` leader dependencies and collision reservations. Although stopped combatants could sometimes be bypassed, normal departure and marching remained sequential. `initialize_spawn` searched a finite set of rally slots and rejected purchases when full. Separately, `ActionPolicy.require_purchase` and the frontend counted all troops against `max_active_units_per_team` (default five; configurable up to thirty).

HP was also normalized to 100 for every mobile type in both UnitType saves and deployments. Changing only the Infantry seed would have been overwritten. `TROOP_MOVEMENT_SPEED=4` was a shared conversion factor, so changing it globally would have changed vehicles too.

The expanded browser tests exposed another practical limit: a large reconnect snapshot exceeded Daphne's 1 MiB WebSocket message ceiling. Simply removing purchase caps would have left large armies in reconnect loops.

## Movement, rally areas and speed

`combat/infantry.py` advances every eligible Infantry by its own distance budget. Infantry never enter the vehicle departure selector, leader/follower graph, collision solver or passing reservations. A stopped attacker consumes only its own movement budget; targeting and cooldowns remain per entity. Every crossed waypoint is included in the authoritative interpolation polyline, including ticks that traverse multiple edges.

New Infantry enter `ACTIVE` at route distance zero in their team's existing centralized rally area. Their server-persisted deterministic cosmetic offsets form a compact 5 × 3 patch (88 × 32 projected pixels), repeated for denser crowds. No client randomness or battlefield-wide spawning is used. This is crowd rendering: it deliberately permits shared logical road segments and shared crowd slots. Offsets never change graph nodes, edge progress, attack range or base contact. Node badges report full army counts; viewport and cell sampling draw representative soldiers in dense areas. Selecting a soldier always keeps that sprite visible.

Existing saved staging/negative-distance Infantry walk toward their route independently using physical distance budgets. Saved road troops retain their physical offsets. Positions are not reset or teleported at restart. Their HP is untouched.

`combat/balance.py` defines:

```python
INFANTRY_MOVEMENT_SPEED = 6
INFANTRY_MAX_HP = 80
TROOP_MOVEMENT_SPEED = 4  # other mobile types
```

The existing authoritative unit is a dimensionless factor converting catalog hops per baseline round into map units per second:

```
speed = movement × persisted_reference_hop_length / movement_baseline_round_seconds × factor
```

The route's reference hop length is calculated once and retained across ticks, reconnects, retargeting and major rounds. Infantry uses factor 6 directly; it does not multiply historical speed 4 by 6. Unobstructed speed is 6/4 = **1.5×** the previous value. Catalog `movement` remains the original baseline (1 for Infantry); the API separately publishes `movement_speed: 6`. Damage remains 5 per unupgraded Infantry hit and the default cooldown remains two seconds.

## Unlimited paid deployment and HP compatibility

Infantry skips the count validator and finite rally-slot search. No replacement maximum, per-round quota or match deployment total is introduced. The existing `max_active_units_per_team` now governs the shared pool of **other** combat units; Infantry does not consume that pool. Tower capacity remains separate.

Catalog responses expose `max_active_units: null` for Infantry. Team state exposes `limits.infantry.max: null`, an unbounded total `active_units`, and a separate `other_units` count/maximum. The Infantry card remains enabled beyond five units when the request is otherwise eligible, displays its price, 80 HP and speed 6, and retains locked/affordable states. The HUD shows the wallet, total army count, unlimited Infantry and the separate vehicle cap.

Purchases still serialize under match/team row locks and debit coins in the same transaction that creates the entity/action/event. Duplicate accepted keys return the original entity without another debit. Insufficient funds still reject. Successful deployments broadcast with stable entity IDs after commit.

Migration `units/0006_infantry_hp.py` updates only the Infantry catalog to 80. It never rewrites GameEntity HP, maximum HP, shields or status. New deployments explicitly use 80/80 even if an old catalog row remains cached. Existing 91/100 Infantry stays 91/100; damaged units do not heal and destroyed units do not revive. Serializers, tick updates and reconnect snapshots use each entity's stored current/max HP. Other entity types retain their previous values.

Apply the migration and deploy backend/frontend together. Verification uses disposable databases; the user's existing database is not migrated or flushed by these checks.

## Rendering, simulation and transport work

- Infantry admission no longer queries/loads every existing friendly soldier or performs pairwise body-clearance searches.
- Route lengths are cached by immutable route/map (bounded LRU).
- Target indexes group by node **and team**, avoiding friendly-army candidate scans. Target selection uses a minimum rather than sorting every list, and caches equivalent logical-position/range queries only within a movement phase or simultaneous attack tier. Dead/other-tier state never survives in that cache.
- Infantry sprites are recycled in a bounded pool of 128 visuals. The live ID registry retains every authoritative entity; this pool is not a unit cap. Recycled callbacks read the current ID, animations/tweens are stopped, and map replacement clears the pool.
- HP graphics redraw only when HP/max/team changes. Large armies avoid per-soldier idle bob tweens. Existing atlas/frame reuse, bounded effects and viewport culling remain; dense Infantry uses projected screen cells instead of the old first-thirty-per-node display cutoff.
- Straight Infantry movement omits redundant two-point paths; crossed corners still transmit. Updates remain one batched combat envelope, not one message or React update per soldier.
- Large persisted events put a small durable event reference on Channels, avoiding Redis message-size ceilings. Each authorized consumer loads/scopes that event before delivery. This adds one database read per large event per subscriber, not per Infantry.
- WebSocket envelopes above 128 KiB are delivered in 64 KiB JSON string chunks. The client applies the original envelope only after complete reassembly, preserving its event ID, sequence and existing duplicate/gap/snapshot rules. Privacy filtering happens before chunking. Partial transfers clear on disconnect, invalid/missing chunks trigger normal recovery, and only one transfer is buffered with a 30-second / 128 MiB operational memory budget.
- The scheduler yields after at most one second of wall-clock catch-up per visit (or the existing 25 ticks). It retains the next authoritative deadline and does not skip simulation ticks. Every 25th over-budget tick emits structured duration/entity-count logging. These are operational safeguards, not gameplay quantity limits.

## Files changed

Backend gameplay/read models:

- `backend/apps/combat/{balance,continuous,continuous_service,formation,infantry,navigation}.py`
- `backend/apps/matches/{action_policy,scheduler}.py`
- `backend/apps/units/{models,seeds,serializers,services,views}.py`
- `backend/apps/units/migrations/0006_infantry_hp.py`
- `backend/apps/questions/management/commands/seed_phase_2.py`
- `backend/apps/combat/management/commands/simulate_match.py`
- `backend/apps/realtime/{consumers,services}.py`

Frontend:

- `frontend/src/game/actionAvailability.ts`, `game.css`, `scenes/BattleScene.ts`, `systems/crowd.ts`
- `frontend/src/pages/BattlePage.tsx`, `types/unit.ts`
- `frontend/src/services/{envelopeChunks,websocket}.ts`

Verification:

- New `backend/tests/test_infantry_gameplay.py`, `test_large_realtime.py`, `benchmark_infantry.py`
- Updated backend `test_arena_scaling`, `test_continuous_combat`, `test_formation_realtime`, `test_graphics`, `test_live_battle_gameplay`, `test_phase_3`, `test_phase_4`, `test_phase_7`, `test_round_concurrency`, `test_spawn_tower_realtime`, `test_troop_movement_combat`
- New `frontend/tests/infantry.test.ts`, `infantry.browser.mjs`, `infantry-render.browser.mjs`; updated `action-availability.test.ts`, `realtime-recovery.test.ts`, `troop-movement.browser.mjs`
- README, balancing/event-contract updates, this report and `docs/qa/infantry-*` measurements/screenshots

Tests that explicitly required single-file Infantry now exercise the retained vehicle traffic behavior. New Infantry-specific tests assert simultaneous departure and independent progress rather than disabling those checks.

## Verification and reproduction

Backend acceptance covers five simultaneous Infantry, a stopped attacker with moving peers, speed ratio/stability after JSON restore, multi-edge route corners, cosmetic-offset range invariance, 5/10/20/50/100 paid deployments with capacity configured to one, insufficient funds, duplicate keys, retained vehicle caps, preserved old HP and 80-HP snapshots, plus scheduler yielding without deadline loss.

PostgreSQL tests cover duplicate commands, competing scheduler ticks, reward claim races, purchase/tick races, twenty simultaneous purchases by two teammates, and twenty competing distinct/duplicate requests with funds for only six Infantry. Large-envelope tests exercise actual authenticated consumers and owner-only wallet fields. Frontend tests cover chunk reassembly, Unicode, duplicates, missing/expired transfers, atomic snapshots followed by buffered deltas, purchase eligibility and screen-cell crowd sampling.

Existing suites cover live tower construction, troop/tower/base damage, independent cooldowns, continuous combat, questions, +20 coins once, match completion, twenty-team fan-out, stale-event rejection and reconnect recovery. An 83-socket test (80 players, two spectators, host) now reconstructs chunked snapshots before checking privacy and state.

Commands:

```sh
# backend/
.venv/bin/pytest -q
.venv/bin/ruff check <changed Python files>
.venv/bin/python manage.py check --settings=config.settings.test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
# Point DATABASE_URL at a disposable PostgreSQL instance:
.venv/bin/pytest --ds=config.settings.test_postgres tests/test_round_concurrency.py -q
.venv/bin/python tests/benchmark_infantry.py

# frontend/
npm test
npm run build
# Start backend tests/browser_preview.py on 8021 with TEST_SCHEDULER=1,
# then Vite with API_PROXY_TARGET=http://127.0.0.1:8021 on 5181:
TEST_BASE_URL=http://127.0.0.1:5181 node tests/infantry.browser.mjs
TEST_BASE_URL=http://127.0.0.1:5181 node tests/troop-movement.browser.mjs
TEST_BASE_URL=http://127.0.0.1:5181 node tests/infantry-render.browser.mjs
```

Browser scripts require Playwright and Chrome; this run uses the bundled Playwright runtime via NODE_PATH. The browser server and backend benchmark always create temporary SQLite databases. PostgreSQL pytest creates/drops its test database.

## Measured results

- Backend full suite: **272 passed**, eight PostgreSQL-only tests skipped on SQLite.
- PostgreSQL row-lock suite: **8 passed**, including the twenty-thread purchase races.
- Frontend: **74 passed**; TypeScript and production build passed with the existing Phaser chunk-size warning.
- Ruff for all changed Python files, Django system checks and migration drift checks passed.
- Deployment UI and sprite recycling browser check: **PASS**. A real card/button purchase deploys the 21st Infantry with capacity configured to one and deducts 15 coins. Two recycled roots retain correct IDs without allocating new scene objects. Desktop/mobile screenshots were visually inspected.
- Two-client combat browser regression: **PASS**; five observed frames have stopped Artillery attacks alongside independently moving Infantry. Covers live towers, five live Infantry at 80 HP, +20 reward once, pause/reload and the next major round. The ranged unit gets a head start so faster Infantry do not arrive first.
- Twenty-team, two-client browser load scenarios: **PASS** for 20/50/100 Infantry per team, plus one live paid purchase from each observed team (402/1,002/2,002 final entities). Wallet checks, idempotent retry, exact paused/reconnected current HP, max HP, node, edge progress, target, cosmetic offset and world position agree. Zero page errors and duplicate sprites.

Committed-tick backend benchmark (20 ticks per quantity, disposable SQLite, no connected viewers). Dense combat is a separate ten-tick **pure-engine** workload with all opposing armies together, not a committed database/transport measurement:

| Infantry/team | Aggregate | Tick median / p95 ms | CPU median ms/tick | Peak RSS MiB | Queries/tick median | Payload KiB/s/viewer at 5 Hz | Dense combat engine median ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 400 | 147.49 / 280.31 | 144.29 | 119.8 | 12 | 1619.33 | 35.98 |
| 50 | 1000 | 363.45 / 529.13 | 359.79 | 148.3 | 14 | 4044.97 | 85.67 |
| 100 | 2000 | 757.75 / 1018.3 | 740.53 | 191.1 | 17 | 8092.59 | 184.06 |

Two independent headless Chrome clients per twenty-team room, around six seconds of movement sampling plus pause/recovery. Aggregate entity counts include every team's army; measured wire rate includes chunk framing, live commands and snapshot recovery, so it is not comparable to payload-only 5 Hz estimates above:

| Infantry/team | Final entities | FPS median A / B | JS heap MiB A / B | Measured wire KiB/s A / B | Divergent entities / duplicate sprites | Reconnect |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 20 | 402 | 60 / 60 | 103.2 / 131.1 | 1319 / 1319 | 0 / 0 | restored |
| 50 | 1002 | 60 / 60 | 110.9 / 112.2 | 1474 / 1586 | 0 / 0 | restored |
| 100 | 2002 | 60 / 60 | 70.9 / 175.1 | 1606 / 1606 | 0 / 0 | restored |

The important constraint is server cadence: 1,000/2,000 entities exceed the default 200 ms tick budget. At 2,000, neither measured browser accepted an individual COMBAT_TICK during the sampled window; newer recovery snapshots superseded delayed deltas. The final board recovered exactly, but this does **not** establish smooth sustained 5 Hz multiplayer at that size. FPS measures rendering, not authoritative simulation speed. Snapshots and ticks retain full entities rather than silently dropping soldiers. CPU times are per-process CPU milliseconds per tick; RSS is the process high-water mark, not isolated per-room allocation. Local concurrent test activity can affect wall-time tails.

Evidence: [backend measurements](qa/infantry-backend-benchmark.json), [browser measurements](qa/infantry-browser.json), [400-entity screenshot](qa/infantry-20.png), [1,000-entity screenshot](qa/infantry-50.png), [2,000-entity screenshot](qa/infantry-100.png). Combat regression results are recorded in [troop-movement-browser.json](qa/troop-movement-browser.json). UI/pool evidence: [infantry-render.json](qa/infantry-render.json), [desktop](qa/infantry-ui-desktop.png), [mobile](qa/infantry-ui-mobile.png).


## Remaining limitations

Unlimited deployment is a gameplay rule, not unlimited compute capacity. JSON payloads, per-entity database checkpoints and per-viewer delivery still scale with army size. Large-event references avoid channel-layer payload ceilings but add per-subscriber reads. Production PostgreSQL/Redis, internet latency, twenty simultaneous browser clients, mobile rendering and many-room soak throughput require separate deployment measurements. Local rendering samples use two independent headless Chrome contexts in each twenty-team room.

At sufficiently high aggregate load, server ticks exceed the configured 200 ms budget and simulation falls behind wall time. The scheduler yields, logs overruns and retains every tick; it does not reject Infantry by count. Dense crowds share cosmetic slots and are represented by sampled sprites plus count badges, rather than showing every soldier as a separated opaque body. Individual authoritative IDs/HP/progress remain in state and selection can reveal a chosen soldier. Vehicles continue to use their existing finite rally space and capacity. Legacy round-mode hop movement does not become the continuous speed model. The existing large Phaser production-bundle warning remains.
