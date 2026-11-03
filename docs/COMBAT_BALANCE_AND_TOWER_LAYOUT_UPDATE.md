# Combat balance, simultaneous troop movement and roadside foundations

Implemented and verified on 2026-10-22. This updates the existing Django combat services, radial arena generator, React controls and Phaser state pipeline. Existing artwork, quiz/reward rules, deployment costs and entity IDs are retained.

## Confirmed audit findings

- `cannon_tower` / **Tháp Đại Bác Phá Giáp** is the stationary Cannon Tower. Its current effective standard range was **3 graph hops**, from the catalog and per-instance range resolver. It is separate from mobile `artillery` / **Pháo Binh Tầm Xa**.
- Artillery's current values were **70 maximum HP**, movement multiplier **4**, and **1.5-hop range**, following migration `0007`. The reduced range was already fractional and supported by both continuous combat and Phaser.
- Infantry already had independent movement, **80 HP**, speed **7**, and its latest **1.5× attack-rate multiplier**. Vehicles still passed through `departures.setdefault(team_id, entity_id)`, which admitted only one vehicle per team. `FormationTraffic` added recursive leader/follower and merge reservations on roads. These were the confirmed sequential movement dependencies.
- Foundations already used six IDs per team, three road bands on both flanks. Positions came from a common radial generator. There was no stored layout version, so changing the generator alone would have moved existing built towers on reconnect.
- Creation events, REST refreshes, combat deltas and snapshots already reconciled by stable entity ID. The REST-to-render mapper required an additional movement-speed field to keep the new entity details consistent after refreshes.

## Balance changes and units

| Statistic | Previous | New |
| --- | ---: | ---: |
| Cannon Tower attack range | 3 graph hops | **2 graph hops** (`3 × 2/3`) |
| Cannon Tower HP / damage / cost | 150 / 30 / 40 | Unchanged |
| Cannon Tower default cooldown | 2 seconds | Unchanged |
| Artillery movement multiplier | 4 | **5** |
| Artillery maximum / initial HP | 70 / 70 | **80 / 80** |
| Artillery range | 1.5 graph hops | **1.5**, unchanged |
| Artillery catalog / continuous damage | 40 / 20 | Unchanged |
| Artillery default cooldown / cost | 2 seconds / 45 | Unchanged |
| Infantry HP / speed / continuous damage | 80 / 7 / 5 | Unchanged |
| Tank HP / speed / continuous damage | 100 / 4 / 12.5 | Unchanged |

The speed setting is the existing dimensionless movement multiplier, not world pixels per second. The unchanged conversion is:

```text
map units per second = catalog movement × reference hop length
                       / movement_baseline_round_seconds × movement multiplier
```

`ARTILLERY_MOVEMENT_SPEED = 5` replaces 4 absolutely; it is not compounded. Each troop retains its own reference hop length, route progress and cooldown. New Artillery spawns with current HP and max HP both 80.

Range remains logical graph-hop distance. Continuous range checks account for partial edges and the existing tower coverage rule for the road between two covered endpoints. No integer rounding is applied. Target acquisition rejects a target just beyond 2 hops. Phaser's existing `graphRange` paints the same covered nodes and clipped road segments for construction previews and inspected entities. Moving a foundation changes its position, not its coverage edges or weapon range.

Catalog values feed the cards and tooltips. Entity serializers, creation payloads, tick deltas, snapshots, REST normalization and the details panel carry authoritative `movement_speed`, instance `range`, current HP and maximum HP. HP bars and interpolation continue consuming these server values. Existing projectile behavior, unlocks, attack priorities, damage and cooldown rules are unchanged.

## Simultaneous movement

All mobile troops now use `mobile.move_mobile_units()` on the same fixed timestep. `navigation.move_independently()` delegates the complete eligible list to it. There is no departure selector, leader completion wait or convoy speed constraint; the former `FormationTraffic` class and its recursive constraints have been removed.

New vehicles receive valid, distinct positions in the existing bounded team rally patch and become `ACTIVE` in `ROUTE` immediately, just like Infantry. The deployment service persists that initialized status for every batch member. Rally-space validation still rejects an invalid vehicle purchase atomically, and the existing shared vehicle count limit remains. Infantry remains unlimited by unit count and retains its existing compact crowd rendering.

Vehicles carry their validated rally offsets along their routes as server-owned visual offsets. Their larger footprints reserve Infantry's central 5×3 patch, regardless of which type is purchased first. These offsets spread the artwork; graph nodes and partial-edge progress still determine range. Road motion has no hard body reservations that could hold an army behind a slower or attacking unit. Brief visual overlap during passing or at junctions is permitted. Existing crowd LOD and depth ordering are retained.

Movement advances by each unit's own speed budget and includes every crossed waypoint in a multi-edge tick. Only a unit's own combat state stops it. Saved staging/negative-progress approaches are processed independently from their saved physical positions, without healing or teleporting them to a new spawn. The compatibility imports in `infantry.py` preserve its prior API.

Phaser continues to interpolate server positions and movement paths. No client movement simulation or sprite recreation was introduced.

## Foundation placement and map versions

New rooms explicitly use `arena_layout_version = 4`. The map advertises `arena.version = 4` and `radial-v4-six-slots-{team_count}`. All integer team counts from **2 through 20** use the same deterministic generator, including SMALL, MEDIUM and LARGE arena profiles.

For each of the six existing slots per team, the generator:

1. Projects coordinates using the same rotation and nonuniform scale as Phaser.
2. Finds the closest point among road curves and straight bridge axes. Curves use the same quadratic control points as terrain rendering, sampled into 16 segments.
3. Attempts a **15% reduction** in distance to that road, along the local direction toward it.
4. Backs off through smaller deterministic adjustments if necessary to preserve road, base, barrier and foundation clearances.
5. Converts the accepted position back to authoritative map coordinates.

All slots move closer; the measured reduction is **1–15%**, with the smallest adjustments needed in constrained orientations of the expanded arena. Road/bridge clearance remains at least **57 projected pixels**, base clearance 70, barrier clearance 40 and foundation-center separation 54. World bounds are validated too. Every supported arena retains six unique, impassable tower slots per team. All passable nodes, roads, spawn locations, base positions, graph edges and coverage links remain unchanged. Teams retain equivalent logical defenses across all three bands.

The map REST endpoint, deployment, continuous and legacy combat, match-start validation and reconnect snapshots resolve the room's layout version. Cache keys include both team count and version. `GameMap.from_dict()` also restores the advertised version. Phaser already derives foundation markers, stone platforms, hit areas, ghost previews, constructed tower positions and range overlays from those server nodes, so no duplicate coordinate tables or artwork replacement are needed.

Projected terrain validation covers painted roads, bridge axes, bases and barrier/cliff nodes. Existing terrain rendering reserves forest space around foundations and paints raised construction platforms over decorative water, preserving the existing treatment of rivers. Browser screenshots were inspected at 4 and 20 teams.

## Compatibility and migration policy

Apply **`units/0008_cannon_artillery_and_layout_version` before reseeding the catalog**, then restart/rebuild backend and frontend together.

- New Cannon Towers use range **2**. Existing Cannon Towers retain their previous effective range through `simulation_state.attack_range`; previously snapshotted custom ranges are preserved. For a customized catalog, the migration multiplies its actual stored range by `2/3`, while retaining all other statistics. The standard seed uses 2.
- New Artillery, including new purchases in existing rooms, uses **80/80 HP**. Existing entities keep their current HP, maximum HP, status, attack range and cooldown. Damaged and destroyed Artillery is never healed or revived. Existing Artillery adopts speed **5** on its next eligible tick without changing its saved position.
- Existing rooms without a version are pinned to **layout 3**, retaining all prior foundation and built-tower coordinates. Their future construction and reconnects use that same layout. Missing versions also default to 3 at runtime. New rooms default to 4; rematches deliberately retain their copied room configuration.
- Existing active troop positions, coins, unlocks, questions, rewards, rounds and actions are not rewritten by the migration.

## Files changed

Authoritative implementation:

- `backend/apps/combat/balance.py`, `mobile.py`, `infantry.py`, `formation.py`, `navigation.py`, `continuous.py`, `continuous_service.py`, `engine.py`, `map.py`, `views.py`.
- `backend/apps/units/seeds.py`, `serializers.py`, `services.py`, `map.py`, `migrations/0008_cannon_artillery_and_layout_version.py`.
- `backend/apps/matches/defaults.py`, `serializers.py`, `services.py`; `backend/apps/realtime/services.py`.

Frontend synchronization and display:

- `frontend/src/types/unit.ts`, `stores/matchStore.ts`, `game/bridge.ts`, `pages/BattlePage.tsx`.
- Existing `game/range.ts`, `game/map.ts`, `BattleScene.ts` and interpolation code consume the updated authoritative data without changes.

Verification and documentation:

- New `backend/tests/test_combat_balance_layout.py` and `frontend/tests/combat-balance-layout.test.ts`.
- Updated current balance/departure assertions in `test_artillery_slots_batch.py`, `test_continuous_combat.py`, `test_live_battle_gameplay.py`, `test_spawn_tower_realtime.py`, `test_troop_movement_combat.py`, `test_phase_3.py`.
- New `frontend/tests/combat-balance-layout.browser.mjs`, this report, README link and `docs/qa/combat-balance-layout-*` evidence.

## Executed verification

- Full SQLite backend suite: **402 passed, 14 PostgreSQL-only checks skipped**. Includes combat, deployment, tower construction, unlimited Infantry, lifecycle/win conditions, question-bank uploads, Battle questions, +20 coin/unlock rewards and once-only claims.
- Separate disposable PostgreSQL cluster: **92 passed**, including row-lock/concurrency suites, batch commands, quiz/reward races, balance/compatibility and geometry. The two additional pure Cannon firing tests were added afterwards and passed in the full backend run.
- Frontend: **87 passed**. Includes the new Cannon preview boundary, historical instance range, Artillery HP/speed through REST refresh and reconnect, and authoritative slot projection tests.
- TypeScript/production Vite build: passed. The existing large-bundle advisory remains.
- Backend Ruff: passed. Django migration drift check: **no changes detected**.
- Real headless Chrome, **two independent contexts in each 2-, 4-, 8- and 20-team room**: each side deploys 5 Infantry + 3 Tanks + 2 Artillery; all 20 troops move on the first authoritative tick. Both clients see every batch without refresh, build towers through React controls, agree with the server snapshot, retain the same Phaser visual objects during updates and agree again after a client reconnects. Artillery cards show 80 HP / speed 5 / range 1.5; Cannon construction/details use range 2. Recorded frame samples were **60 FPS** in these runs, with no page errors.

Reproduction commands:

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
DATABASE_URL=postgresql://... .venv/bin/pytest tests/test_round_concurrency.py tests/test_question_bank_concurrency.py tests/test_artillery_slots_batch.py tests/test_combat_balance_layout.py --ds=config.settings.test_postgres -q

# Disposable browser backend; use another terminal for Vite.
TEST_SCHEDULER=1 TEST_BACKEND_PORT=8021 .venv/bin/python tests/browser_preview.py
cd ../frontend
npm test
npm run build
API_PROXY_TARGET=http://127.0.0.1:8021 npm run dev -- --host 127.0.0.1 --port 5181
# Requires Playwright and Chrome; set NODE_PATH if Playwright is provided externally.
TEST_BASE_URL=http://127.0.0.1:5181 node tests/combat-balance-layout.browser.mjs
```

Evidence: `docs/qa/combat-balance-layout-browser.json`, `combat-balance-layout-geometry.json`, `combat-balance-layout-4.png`, `combat-balance-layout-20.png`, and the backend, PostgreSQL, frontend and build logs alongside them.

## Remaining limitations and rollout

This is a source update with a data migration; existing deployed processes/images must be migrated and rebuilt/restarted to load it. Browser checks used disposable SQLite rooms and the separate concurrency checks used disposable PostgreSQL; no existing application database was migrated or reset.

The browser run exercised two viewers per arena and 20 mixed troops per room. It is not a twenty-browser load benchmark. The prior report's large-army combat tick-budget limitation remains; this change does not claim to resolve production-scale simulation performance. Infantry crowd LOD, compact vehicle rally capacity and permitted visual overlap during passing remain deliberate existing-style rendering tradeoffs.
