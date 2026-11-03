# Unlimited defensive tower construction

## Rules and compatibility

There is no active-tower maximum or round construction quota. Existing saved `max_towers_per_team` values are ignored by the purchase policy and client, even if they say 1 or 6. New/updated configuration normalizes this retired compatibility field to `null`; catalog `max_active_units` and team-state `limits.towers.max` are `null`. The HUD shows count / ∞. Vehicle capacity and paid Infantry deployment rules are unchanged.

New arenas use layout 7, placement version 1, with no fixed tower slots. Three-team rooms use the balanced green route and river corridor described in `GRID_TOWER_PLACEMENT_DESIGN.md`. Saved layout 3–6 arenas publish grid metadata and accept grid coordinates, using **their original geometry**. Existing towers and troop routes keep their exact positions. Historical node-only commands remain a compatibility API, but do not constrain grid builds. Team-state slot lists are empty and the UI never limits saved arenas to six foundations. Some compact old arenas genuinely lack additional 4×4 space after roads and existing structures are excluded; this yields a placement failure, never a count rejection. No schema/data migration is required; deploy backend and frontend together with existing migrations applied.

Every tower costs its normal catalog price (MG 25, Cannon 40; other prices remain authoritative catalog values). Unlocks, match phase, active team, ownership and sufficient coins remain required. Building is available in continuous Battle and Preparation. No combat, quiz, camera, popup or route reset was added.

## Territory and occupancy

The canonical `PlacementGrid` describes the same server-generated geometry used by 2/4/8/20-team arenas. Cells are 32 projected pixels; current towers reserve 4×4 cells. All corners of every cell must lie within the team's deterministic radial sector and authorized annulus. Neutral terrain is unavailable. The same masks are published to clients, whose ghost checks are preliminary only.

Full footprints exclude bases, rallies, protected road/bridge/intersection areas and movement envelopes, river water, barriers and existing defensive structures. Existing roadside safety margins and Infantry/Tank/Artillery swept-body clearance remain unchanged. Decorative natural trees are not blocking terrain. ACTIVE, QUEUED and DISABLED structures occupy space. Authoritatively destroyed structures release it; no separate client-owned occupancy reservation can become stale. Unknown tower footprints fail closed.

## Atomic construction and realtime state

REST and WebSocket build requests share `ConstructionService`. It locks Match, then Team in a transaction, validates authorization even on retries, checks phase/type/unlock/economy, validates the complete footprint and current occupants, debits once, and creates an entity and durable action. Match locking serializes construction against other builds, team upgrades and combat destruction. PostgreSQL row locks supply cross-worker safety. The SQLite preview remains single process.

A missing request ID is generated server-side for compatibility; clients send UUIDs. Explicit blank or oversized IDs are rejected. Same ID/type/position returns the original entity without another debit. Reusing an ID for a different operation/type/position fails. Failed validations leave coins and occupancy unchanged. Broadcasts run after commit; retries do not broadcast duplicate builds. Teammates receive updated balances; opponent financial fields retain existing privacy filtering.

New towers resolve current team/type upgrade level under the same lock. Existing and future towers use levels 1–4; upgrades remain team-wide purchases. TOWER_BUILT, TEAM_UNIT_UPGRADED, combat deltas and reconnect snapshots preserve ownership, stats and grid/world position. Entity-ID reducers deduplicate sprites and sequence checks ignore older events.

## Performance investigation and changes

`tests/benchmark_unlimited_towers.py` uses disposable SQLite test databases and real paid service calls. Each team also deploys ten Infantry. Fifty 200ms pure simulation steps are timed per scenario. These measurements exclude network latency and database tick persistence. Before/after runs share the same fixture and geometry; machine load varies.

The old physical-tower target lookup scanned all entities per tower. A per-phase spatial hash with 80-world-unit buckets now supplies broad-phase candidates. Physical distance to grid towers includes their half-hop footprint radius; team, HP, status, staging and target priority checks still decide combat. Legacy graph-range rules remain unchanged. A deterministic brute-force oracle checks 305 entities, negative coordinates, exact boundaries, six ranges and 2/4/8/20-team maps. Collision queries hydrate only the position fields they use.

| Teams | Towers/team | Entities | Median tick before → after (ms) | Target candidate pass before → after (ms) | Collision mean after (ms) | Snapshot bytes |
|---|---:|---:|---:|---:|---:|---:|
| 2 | 10 | 40 | 4.479 → 2.584 | 2.910 → 0.966 | 0.851 | 48,187 |
| 2 | 25 | 70 | 9.041 → 3.958 | 8.477 → 1.359 | 1.306 | 67,371 |
| 2 | 50 | 120 | 17.580 → 6.271 | 25.506 → 2.269 | 2.071 | 99,336 |
| 4 | 50 | 240 | 82.590 → 14.171 | 178.154 → 5.994 | 4.375 | 191,840 |
| 20 | 10 | 400 | 431.181 → 26.788 | 412.953 → 14.361 | 4.034 | 441,479 |
| 20 | 25 | 700 | 1101.590 → 39.590 | 1539.723 → 17.095 | 8.892 | 633,555 |

Raw measurements: `docs/qa/unlimited-performance-{before,after}.json`. After-run construction uses 27 SQLite statements including nested savepoints/event/economy operations; snapshots use eight queries, independent of tested tower quantity. Build-event JSON is 655–657 bytes. Snapshot size grows linearly; existing deltas, persistent visual IDs, offscreen culling and bounded projectile-effect pools remain in use. Collision checks still scan position rows in O(structures); at 500 towers the measured mean was 8.892ms, so a persistent occupancy cache was not introduced.

The 50-tower scenario is exercised on 2- and 4-team maps. Some 8-/20-team sectors cannot fit 50 current 4×4 footprints under existing protected geometry. This is available-space exhaustion, not a quota. The deterministic greedy packing fixture finds at least ten valid footprints for every team in every requested arena size; it does not claim maximal packing.

## Verification

- Full final SQLite backend suite: 500 passed, 23 PostgreSQL-only skips (153.14s).
- After final configuration normalization: 47 passed, four PostgreSQL-only skips, including unlimited construction, brute-force spatial equality, configuration and roadside clearance (10.83s). Saved-arena/grid suite: 48 passed, five PostgreSQL-only skips (18.33s).
- PostgreSQL integration: 65 passed (34.14s), including distinct-cell simultaneous builds, overlapping cells, same-ID retries, last-coins races, Battle, upgrades, spectators, reconnects and saved layout 3–5 grids. Test teardown reported one lingering async connection; the disposable PostgreSQL server is stopped after QA.
- Frontend: 122 tests passed; production TypeScript/Vite build passed, with the existing large Phaser chunk advisory. Ruff passes on changed production modules and new Python tests.
- Browser report: `docs/qa/unlimited-browser-results.json` (PASS). It verifies actual Phaser clicks through builds seven/eight, opponent visibility, team upgrades through level four, rank refresh, future tower inheritance, reconnect and paid 10/25/50-tower rendering scenarios. Card evidence is described in `FORTIFICATION_CARD_REDESIGN.md`.
- Existing regression suites cover Cannon damage 20/range, team upgrades, Infantry speed 7/HP 80, Artillery speed 5/HP 80, parallel movement, batches, retarget/retreat, quiz XLSX, rewards, persistent quiz deadlines and natural map scenery.

Run backend tests with `.venv/bin/pytest`; real concurrency requires `--ds=config.settings.test_postgres` and a disposable `DATABASE_URL`. Run the benchmark as `PYTHONPATH=. .venv/bin/python tests/benchmark_unlimited_towers.py OUTPUT.json`. Browser setup and reproduction are in the companion card document.

## Remaining limits

No network-load/Redis multi-process soak, Safari/iOS engine or real mobile hardware benchmark was performed. Server profile timings are local single-host measurements; the 20-team scenarios did not produce attack events in their ten-second movement window. Browser projectile stress replays effect events separately and is labeled synthetic. The system does not promise arbitrary entity counts at a fixed frame rate. Future movable obstacles or different artwork footprints require canonical geometry updates. These are performance/coverage limits, not enforced tower caps.
