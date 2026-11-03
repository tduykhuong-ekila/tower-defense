# Artillery rebalance, six tower slots and batch deployment

Implemented and verified on 2026-10-22. This extends the existing Django services, graph map, React battle controls, Phaser scene and ordered Channels event stream.

## Audit findings

- **Long-Range Artillery is `artillery`, category `UNIT`, displayed as “Pháo Binh Tầm Xa”.** It is a mobile troop; `cannon_tower` is a separate stationary construction.
- The standard artillery catalog previously specified **3 graph hops and 100 HP**. `troop_max_hp()` also forced non-Infantry mobile deployments to 100 HP. Both paths needed changing.
- Continuous combat already measures fractional graph distances using partial edge progress. Legacy combat compares whole-node graph distances. Neither needs integer rounding of the configured range.
- `GameMap` generated three foundations; `MapDefinition`, match defaults, serializers and action policy also assumed three. Slot occupancy was already derived from surviving entities and synchronized by tower events and snapshots.
- REST and WebSocket deployment both called `UnitService.deploy_unit()`. The service locked the match and team, charged one unit, created one entity and recorded a durable idempotent action. Infantry was already unlimited, speed **7**, maximum HP **80**, and independent of vehicle departure traffic.
- Existing realtime sequencing, outbox retry, large-envelope chunking, ID reconciliation, camera bounds and crowd rendering were retained.

## Artillery configuration and compatibility

| Statistic | Previous | New deployments |
| --- | ---: | ---: |
| Catalog attack range | 3 hops | **1.5 hops** |
| Maximum / initial HP | 100 / 100 | **70 / 70** |
| Catalog damage | 40 | 40 |
| Continuous damage per hit | 20 | 20 |
| Movement multiplier | 4 | 4 |
| Coin cost | 45 | 45 |
| Unlock requirement | Existing artillery unlock | Unchanged |
| Attack cooldown | Existing match configuration | Unchanged |

The range is exactly `3 × 0.5`, with no rounding. Continuous targeting accepts a target at 1.5 hops and rejects one beyond that boundary. Legacy node-only targeting accepts integer distances `<= 1.5` (0 or 1); the catalog still reports 1.5.

`units/0007_artillery_balance_and_six_slots` snapshots the previous range into each existing artillery entity’s `simulation_state.attack_range` before changing the catalog. It **does not rewrite current HP, maximum HP, status or cooldowns**. A damaged survivor stays damaged, a destroyed entity stays destroyed, and an existing 100-HP artillery retains its prior maximum and range. New deployments, including in an existing match, use 70 HP and the updated catalog range.

Both combat services resolve effective range from the instance snapshot. REST serialization, WebSocket creations, combat deltas and reconnect snapshots include the effective `range`. The details panel prefers that instance value. Phaser previews and inspected-entity coverage use fractional graph segments, rather than converting graph range into a misleading circular pixel radius. Tank, Infantry and Cannon Tower combat statistics remain unchanged.

## Six-slot layout and construction

Every supported team count, **every integer from 2 through 20**, uses the same validated radial map generator. Every team has `node_tower_t{team_index}_slot1` through `slot6`.

Three bands lie at radii `350 / 270 / 190 × layout_scale`, each with a foundation on both sides of its branch. Lateral clearances are `108 / 108 / 88` map units. The inner pair uses a smaller offset to remain inside its sector in the twenty-team arena. All teams receive rotationally equivalent topology and coverage links.

IDs 1–3 retain their original logical coverage connections, and 4–6 mirror those connections. Existing occupied IDs survive; their displayed foundation coordinates move with the upgraded layout. Base, spawn, movement-road coordinates, route lengths and continuous movement conversion are unchanged.

`validate_build_geometry()` runs as part of authoritative map validation and checks:

- Exactly six slots per team, with tests verifying unique IDs and coordinates.
- World bounds after the actual Phaser rotation and nonuniform projection.
- At least 57 projected pixels from road curves and bridge axes. The validator samples the same quadratic curves used by terrain rendering; its chord error is below 0.1 pixel at the largest supported layout.
- Base and barrier clearance, and at least 54 pixels between foundation centers.
- Existing route connectivity and passability, including all spawn-to-enemy-base routes.

Stone construction platforms are painted after the decorative river, keeping build foundations dry, and forest decoration reserves their area. Foundations remain subtle at rest; existing selection halos, ghost placement, graph coverage, occupied towers, cost cards and slot buttons support construction. The six explicit slot buttons also work at overview zoom. Camera and minimap controls retain the same map bounds.

The map advertises `arena.version = 3`, with `radial-v3-six-slots-{count}` as its key, so clients rebuild cached terrain when they receive the upgraded map.

New rooms default to six active structures. The data migration raises stored room limits to six; hosts can still deliberately configure a lower limit. Total foundation count, surviving tower count and one-placement-per-command configuration remain separate. Towers are not reset between rounds. Destroyed towers free their slots; disabled towers still occupy them. The sixth tower succeeds; another construction is rejected when capacity or valid free slots are exhausted.

Construction retains authoritative phase, team ownership, unlock, coin and occupancy checks under the match/team locks. Retries return the existing tower without another charge, and reuse of a key for a different command or slot is rejected.

## Deployment API

The existing endpoint accepts a new optional integer `quantity` and optional owned `spawn_node_id`:

```http
POST /api/v1/matches/{match_id}/actions/deploy/
X-Participant-Token: ...
Content-Type: application/json
```

```json
{
  "unit_type_code_or_id": "infantry",
  "target_team_id": "<enemy-team-uuid>",
  "spawn_node_id": "node_spawn_t1",
  "quantity": 5,
  "idempotency_key": "<stable-request-uuid>"
}
```

Omitting quantity defaults to **1**. Zero, negatives, floats, booleans, strings and null are rejected. Infantry quantity has no gameplay cap; coins determine affordability. Tanks and Artillery share the existing non-Infantry capacity (default five), and retain physical rally-space validation.

The response retains `action`, `entity` and `team_coins`. `entity` is the first entity for compatibility; new `entities` contains the complete batch and `quantity` reports its size. The action records ordered `entity_ids`, `unit_cost`, total `cost`, target and spawn node. Original Python callers retain the single-entity `deploy_unit()` contract; transports use the new `deploy_units()` service.

WebSocket `DEPLOY_REQUEST` accepts the same quantity, defaults it to one and validates it in the same service. Existing `unit_code` / `unit_type_id` and `spawn_node` aliases remain supported.

## Transaction, idempotency and spawning

One transaction acquires the match lock and team lock in the existing order. It authenticates ownership, resolves the unit/unlock, validates phase, quantity, current coins, shared capacity, target and owned spawn, then prepares every spawn position in memory. A failure preparing any vehicle rejects the whole purchase.

A successful batch makes **one total debit** through `EconomyService`, one coin audit entry, one bulk entity insertion and one durable `GameAction`. Every entity has a distinct UUID and route. Formation order advances once by the batch size. Commit publishes the existing coin update and one creation event. Failed transactions publish no committed entities and charge nothing.

The `(team, idempotency_key)` uniqueness constraint and match/team locks serialize retries and concurrent teammates. Retrying the same quantity/type/target/key returns the original ordered entity set, including after phase changes, with no new debit or event. Conflicting reuse returns `IDEMPOTENCY_CONFLICT`. Pre-upgrade single-unit actions, including callers using catalog UUIDs, also replay safely. Old clients may omit a key for compatibility; they must supply the same key to obtain retry protection. The battle UI always supplies a UUID.

Infantry spawns immediately in the existing compact deterministic rally patch, retains independent movement and does not join a sequential departure queue. Existing crowd offsets repeat over a fifteen-position patch for large armies; individual entity IDs and combat state remain distinct. Vehicles use their existing larger body footprints and bounded staging positions. Vehicle batches can be rejected for rally congestion even when wallet and count capacity permit them.

For quantity one, the legacy `UNIT_DEPLOYED` shape is preserved. Larger batches emit one `ENTITIES_CREATED` envelope containing public authoritative entities. Existing sequence ordering, chunking, event scoping, outbox recovery and snapshot reconciliation remain in force. The store upserts by entity ID, so duplicated envelopes, REST refreshes and reconnects do not multiply sprites. Opponents do not receive private wallet balances.

## Quantity controls

The existing battle deployment panel now has minus/plus buttons, integer input, presets 1/5/10, Max, per-unit cost, total cost, available coins and rejection feedback. Max uses the latest wallet and remaining shared vehicle capacity; the server validates both again.

Both the map rally interaction and the deployment button send one quantity-aware command. A success clears pending state, retains the selected unit and quantity, updates the authoritative wallet, recalculates eligibility and uses existing deployment animation. A failure displays the backend error and resynchronizes without optimistic coin deductions or committed sprites. The quantity panel is positioned clear of the desktop minimap, with a mobile layout verified at 390 × 844.

## Verification

Executed against the final source:

- Backend full regression suite: **368 passed, 14 PostgreSQL-only checks skipped under SQLite**.
- PostgreSQL acceptance and concurrency suites: **58 passed**, including simultaneous same-key retries, competing wallet requests, shared vehicle caps, 20 simultaneous team batches, two authenticated sockets, live battle and reconnect.
- Frontend: **83 tests passed**, covering quantity eligibility, controls, total costs, zero eligibility, sixth tower, fractional range coverage, duplicate events and snapshots.
- Backend Ruff: passed. Django migration drift check: no changes detected.
- TypeScript and production Vite build: passed. Vite retains the existing large-bundle size advisory.
- Real Chrome: two independent clients deploy five Infantry and three Tanks through the React controls, construct tower six, reject the seventh, deploy and inspect 70-HP / 1.5-hop artillery, retry safely, advance continuous combat, reconnect and compare state. Desktop and mobile screenshots are saved under `docs/qa/`.
- Real Chrome load: 20 teams deploy 50 Infantry each; both clients retain **1,000 unique entities/sprites**, agree with the server and continue rendering smoothly. See the JSON evidence for frame samples and network counts.

Reproducible commands:

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
DATABASE_URL=postgresql://... .venv/bin/pytest tests/test_round_concurrency.py tests/test_artillery_slots_batch.py --ds=config.settings.test_postgres -q
DATABASE_URL=postgresql://... .venv/bin/python tests/benchmark_batches.py

cd ../frontend
npm test
npm run build
# With Playwright available and tests/browser_preview.py + Vite running:
TEST_BASE_URL=http://127.0.0.1:5177 node tests/artillery-slots-batch.browser.mjs
```

The backend browser runner uses a disposable SQLite database. PostgreSQL verification used a separate disposable local cluster; it did not migrate or flush the existing application database.

## Measured performance and limits

PostgreSQL benchmark, 20 simultaneous commands in one active 20-team match:

| Measurement | 10 units per team | 50 units per team |
| --- | ---: | ---: |
| Created entities | 200 | 1,000 |
| Total command completion | 491 ms | 2,088 ms |
| SQL queries per command | 29 | 29 |
| Creation events / coin events | 20 / 20 | 20 / 20 |
| Creation payload bytes, aggregate | 153,726 | 755,598 |
| Combat tick | 95 ms | 1,546 ms |
| Snapshot queries | 7 | 7 |
| Duplicate IDs / incorrect wallet balances | 0 / 0 | 0 / 0 |

The final Chrome run measured 56–60 FPS with 1,000 entities. Large combat envelopes can be chunked and recovered through snapshots; raw WebSocket frame counts therefore differ from applied event counts. These are local measurements, not production guarantees. The 1,000-unit combat tick exceeds the existing 200 ms simulation budget, even while Phaser remains near 60 FPS. This work removes per-entity deployment queries and per-entity creation events; the existing large-army combat simulation still needs separate optimization. **No Infantry cap or departure queue was introduced to hide that limit.**

Saved evidence:

- `docs/qa/artillery-slots-batch-benchmark.json`
- `docs/qa/artillery-slots-batch-browser.json`
- `docs/qa/batch-quantity-desktop.png`
- `docs/qa/batch-quantity-mobile.png`
- `docs/qa/batch-20-team.png`

## Applying the update

Run backend migrations, then rebuild/restart the backend and frontend together. Migrate before reseeding an existing catalog so old artillery ranges are snapshotted before the catalog changes. This applies the balance/catalog and stored tower-limit migration while preserving entity HP, unlocks, coins, occupied slot IDs and round state. Previously built Docker images continue to run their older source until rebuilt.
