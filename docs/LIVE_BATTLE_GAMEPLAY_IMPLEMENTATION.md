# Live battle gameplay implementation — 2026-10-21

This update builds on the existing continuous server simulation and supersedes the earlier movement/HP and Battle action restrictions. The arena artwork, camera controller, tick frequency, round timers, question eligibility, coin costs, unlock rules and damage calculations are retained.

## Balancing and HP

| Setting | Previous effective behavior | Updated behavior |
|---|---|---|
| Troop movement factor versus original route baseline | 0.5 | **0.75 = previous × 1.5** |
| Infantry base/spawn HP | 40 | **100/100** |
| Tank base/spawn HP | 120 | **100/100** |
| Artillery base/spawn HP | 45 | **100/100** |
| Other mobile UNIT types | Their configured HP | **100/100** |
| Troop damage | 0.5 of raw damage | Unchanged: Infantry 5, Tank 12/13 alternating, Artillery 20 |
| Tower HP / damage, base HP, shields, costs | Existing settings | Unchanged |

`combat/balance.py` updates the existing movement factor, rather than stacking a per-tick multiplier. Speed remains `movement × persisted reference_hop_length / movement_baseline_round_seconds × 0.75`. The route reference is computed once from actual edge lengths and survives reloads/major rounds. An uninterrupted standard route now takes `N × baseline_seconds / movement / 0.75`, compared with the previous `N × baseline_seconds / movement / 0.5`: travel duration is divided by 1.5. Formation and combat can slow individual troops; speed comparisons use an unblocked unit on the same route.

`MOBILE_TROOP_HP=100`, standard seeds, UnitType saves and deployment creation enforce the mobile HP rule. UNIT types with positive movement (default 1 if omitted) are mobile; stationary structures are excluded. HP comes from backend persistence/serialization, not frontend constants. Existing tower types retain 100/150 HP and 15/30 damage; level upgrades, shields and fractional troop damage carry are unchanged.

Data migration `units/0005_mobile_troop_hp.py` updates mobile catalogs and entity maximum HP. Existing current HP is clamped to `[0,100]`, never increased: damaged 27 HP remains 27/100; an old 40-HP survivor remains 40/100; a 120-HP tank becomes 100/100. Destroyed units stay at zero. Existing positions/resources are not reset by the migration.

## Authoritative single-file movement

`combat/formation.py` uses physical arc distance along ordered passable routes. Per-entity simulation_state persists:

- `route_nodes`, `route_distance`: assigned route and progress;
- `reference_hop_length`: the existing physical speed conversion;
- `formation_order`: durable monotonic admission order allocated under the match lock;
- `formation_footprint`: collision diameter;
- `next_node_id`, `edge_progress`: the current authoritative road segment;
- `approach_node_id`, `staging_distance`: explicit spawn approach position while queued.

The controller builds friendly constraints per team and directed shared lane. Front units resolve before following units. Desired speed is capped by available distance behind the leader, including its movement during this tick. Faster followers cannot pass a slower/stopped leader. Casualties are excluded on subsequent ticks and the queue advances into the available space. Different teams and opposing traffic do not enter one friendly global queue. Enemies still engage through existing range/target/cooldown rules. A follower attacks only when its own position/range is eligible; it does not inherit base contact from the leader.

At merges, arrival time to a shared directed edge wins; persistent admission order and ID break ties. Far-away future intersections are not reserved. At road corners, physical Euclidean footprint clearance supplements arc separation so a sharp turn does not collapse the visual gap. Dependencies fail closed if an invalid/cyclic traffic state cannot safely advance. Pure-engine checks cover independent roads, mixed sizes, stopped/dead leaders, late admissions, merges, forks and twenty independent team queues.

`troop_formation_gap` defaults to **12 map-coordinate units**, accepted range 0–100 in match configuration. Collision diameters derive conservatively from the existing 43 px Infantry and 68 px vehicle sprites, using their diagonal and the map's minimum projection scale 0.86. Thus standard center distances on straight roads are approximately 82.71 (Infantry pair), 103.27 (mixed Infantry/vehicle), and 123.82 (vehicle pair). Custom mobile stats can specify `formation_footprint` in map units; it must match their rendered footprint.

## Spawn congestion and rendering

A new unit is placed behind the actual tail of its team's spawn approach. It does not overlap the leader or force existing troops forward. If congested, it starts with negative route distance and QUEUED status, moves along the approach on subsequent Battle ticks, and activates when it physically reaches the spawn. This is congestion-based admission, not a next-round wait or invented construction delay. Staged troops retain 100 HP, consume capacity and are immediately visible/inspectable to all permitted clients. They do not attack or receive ordinary active-target combat before admission.

Phaser projects these server positions directly onto road centerlines, draws the explicit approach road, and removes the old 6-column lateral offsets for formation units. Existing interpolation follows road corners, walking/orientation/depth and HP bars remain live, and attack animation does not move logical positions. Camera bounds extend for unusually long configurable queues so the tail remains pannable and inspectable; the normal map fit/artwork and smooth zoom controller are retained. The minimap keeps its existing node-level aggregation, rather than individual approach-position dots.

Already-overlapping old active troops retain their authoritative positions rather than teleporting backward. Followers wait while leaders establish clearance; new deployments are spaced from admission. If the old leader is blocked in combat, existing overlap can persist until it moves or dies. This compatibility behavior is intentionally documented instead of silently relocating ongoing troops.

## Live actions and concurrency

| Action | Preparation / PLANNING | War / BATTLE | Paused, Lobby, Results, eliminated/read-only |
|---|---|---|---|
| Deploy / build / choose target | Eligible actions enabled | **Eligible actions enabled** | Rejected |
| Questions / rewards / repair / upgrade / scout / EMP | Existing eligibility | Existing restriction retained | Existing restriction retained |
| Camera / inspection | Enabled | Enabled | Inspection retained |

ActionPolicy publishes matching phase rules in REST and snapshots; frontend availability follows them. Broad Battle mutation locks are removed only for DEPLOY_UNIT, BUILD_TOWER and TARGET_SELECTED. Coins, unlocks, capacity (including staged units), ownership, target reachability, placement occupancy and idempotency checks still apply. Battle-time actions do not rewrite phase/tick deadlines, pause the simulation or reset survivors.

Purchases and ticks already acquire the same match row lock. Accepted entities and coin deductions commit atomically; after-commit UNIT_DEPLOYED/TOWER_BUILT events reach opponents and spectators immediately. The next tick loads the committed entity. A tick that won the lock first cannot overwrite a later purchase; a purchase that won first is included by that tick. The deployment event includes formation position so the initiating REST response and broadcast reconcile to one stable sprite. Compact COMBAT_TICK projections include formation/admission fields; full snapshots retain all checkpoint state.

## Verification and reproduction

Automated engine/service tests cover all troop speeds, no modifier accumulation, real old-versus-new traversal, 100 HP including a custom mobile type, HP migration without healing, unchanged cannon/base stats, safe following and merges, corners, forks, leader death and opposing combat. A deterministic real-service scenario deploys two troops in Preparation, builds a tower and deploys a third in Battle, checks one debit/idempotency, continued movement, actual tower hits, unchanged phase deadline, then preserved entities at the next preparation.

Authenticated WebSocket tests include Battle deployments/builds, spectators and 20-team fan-out/reconnect. Real PostgreSQL tests race a combat tick with duplicate deployment and duplicate construction across five threads; the wallet, entity count, formation counter and battle deadline must remain correct.

The two-browser test uses actual React cards/placement controls to build and deploy in Battle. It checks remote sprite arrival, 100 HP, formation distances, continued movement, server-confirmed 15-damage tower fire, pause reconciliation, next preparation, reconnect, +20 question coins once, and stored results. Separate load tests run 2/4/8/12/20 teams with five troops and three towers per team. A separate 30-unit queue test verifies camera focus and an actual pointer selection at the tail.

Commands from backend: `.venv/bin/pytest`, `.venv/bin/ruff check .`, `.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test`. For PostgreSQL set DATABASE_URL and run `.venv/bin/pytest --ds=config.settings.test_postgres tests/test_round_concurrency.py tests/test_live_battle_gameplay.py tests/test_continuous_combat.py`. From frontend: `npm test`, `npm run build`.

Browser reproduction uses the disposable server `TEST_SCHEDULER=1 TEST_BACKEND_PORT=8011 .venv/bin/python tests/browser_preview.py`, Vite `API_PROXY_TARGET=http://127.0.0.1:8011 npm run dev -- --port 5176 --host 127.0.0.1`, then `node tests/live-battle.browser.mjs`, `node tests/live-battle-load.browser.mjs` and `node tests/live-battle-capacity.browser.mjs` with Playwright/Chrome available. Execution here used the bundled Playwright directory via NODE_PATH.

## Deployment and scope

Apply migrations, rebuild frontend and restart backend/frontend. The existing user database was not modified during verification; SQLite previews, backend measurements and PostgreSQL runs used disposable databases. Existing continuous matches adopt the new movement/live-action rules after restart; the migration applies HP without healing. Legacy matches retain their previous movement resolver/formation, while mobile catalog/spawn HP becomes 100.

Measurements are local, headless Chrome, one measured room, SQLite + InMemory Channels; PostgreSQL concurrency is verified separately. They do not establish Redis throughput, internet latency, many-room capacity, mobile FPS or a 20-minute soak. Normal 20-team load is 160 entities; the 30-unit test exercises one team's staging/camera, not a 600-unit full-battle performance guarantee. Existing Phaser bundle-size warnings remain. Existing overlapping active troops settle as described above; pathological custom road/traffic states may safely wait rather than overlap or teleport.

Evidence: [audit](LIVE_BATTLE_GAMEPLAY_AUDIT.md), [two-browser gameplay](qa/live-battle-browser.json), [load/FPS](qa/live-battle-load.json), [backend ticks](qa/live-battle-backend-benchmark.json), [30-unit camera](qa/live-battle-capacity.json), [formation screenshot](qa/live-battle-formation.png).

## Actual results

Final automated checks: **209 backend tests passed, 6 skipped on SQLite**; all six skipped row-lock checks are covered in the separate **34-test PostgreSQL run, all passed**. **54 frontend tests passed**. Ruff and migration drift checks passed; TypeScript/Vite build passed with the existing Phaser chunk warning. Both browser scenarios and the 30-unit camera/inspection check are PASS.

| Teams | Initial entities | Tick median / p95 ms | Browser FPS median | WebSocket KB/s/viewer | Event latency p95 ms | JS heap MB |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 16 | 11.7 / 13.89 | 60 | 13.31 | 15 | 41.2 |
| 4 | 32 | 20.78 / 47.34 | 60 | 24.07 | 14 | 44.5 |
| 8 | 64 | 21.0 / 26.27 | 60 | 49.09 | 32 | 84.2 |
| 12 | 96 | 28.25 / 55.04 | 60 | 67.47 | 30 | 45.8 |
| 20 | 160 | 43.36 / 69.07 | 60 | 105.03 | 37 | 100.9 |

Backend measurements use 40 committed ticks per team count with the default five troops and three towers per team. Median tick query count remained **11**. The 20-team browser samples were **59–61 FPS**, with zero divergent own-team entity positions/HP, including staged positions, after a paused authoritative comparison. These are separate local runs, not internet/Redis or 600-unit throughput guarantees. The 30-unit queue tail was 2,398.61 map units behind spawn and was successfully focused and selected with a real pointer click.
