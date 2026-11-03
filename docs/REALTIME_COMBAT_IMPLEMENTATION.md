# Realtime combat implementation — 2026-10-21

> Follow-up gameplay update: current troop speed is 0.75 of the original baseline, mobile HP is 100, formations are single-file, and deploy/build/target are allowed in Battle. See [Live Battle gameplay](LIVE_BATTLE_GAMEPLAY_IMPLEMENTATION.md); the rollout details below record the preceding version.

Implemented in the existing Django/Channels + React/Zustand/Phaser project, retaining arena graphics, camera/minimap, rooms/teams, questions, purchases, scoring and results.

## Delivered

- Deployment/construction immediately upsert interactive stable-ID sprites on opponents' battlefields, including stalled legacy playback. Committed events use a retryable outbox; private sequences use empty permission-projected markers. Socket gaps buffer until authoritative repair; stale snapshots/events cannot roll back state. Periodic repair covers silent final-packet loss.
- New rooms default to 3 major rounds; hosts can select 2/3 and preparation/battle durations. Battle simulation preserves survivors, partial positions, towers, HP, coins, unlocks and elimination across preparations. Common backend policy blocks player mutations during battle.
- Fixed-step automatic movement, targeting, tower/troop attacks, repeated base damage, shields, destruction, elimination, live scores and immutable rankings. Checkpointed deadlines plus row locks prevent duplicate damage and support bounded catch-up after restart, independently of browser/host connections.
- Phaser frame interpolation follows roads and plays walking, recoil/projectile/hit/HP/death visuals live without a round replay lock. Existing camera and inspection remain available.
- Central movement/damage factors 0.5; route-length conversion from legacy hops/round; persisted fractional damage carry; unchanged tower damage/HP/costs. Correct-answer coin rewards remain exactly +20 once.

## Configuration

| Parameter | Default | Meaning / bounds |
|---|---:|---|
| gameplay_mode | CONTINUOUS for new rooms | CONTINUOUS / LEGACY; old stored rooms retain legacy |
| total_rounds | 3 | 2 or 3 |
| first_preparation_duration_seconds | 120 | First preparation; 1–900 |
| preparation_duration_seconds | 180 | Later preparations; 1–900 |
| battle_duration_seconds | 300 | Each battle; 1–1800 |
| battle_tick_interval_ms | 200 | Fixed timestep; 100–1000 |
| attack_cooldown_seconds | 2.0 | Default cooldown; 0.2–60; unit base_stats may override |
| movement_baseline_round_seconds | 30 | Legacy movement conversion; 1–200; independent of tick/cooldown |
| TROOP_MOVEMENT_MULTIPLIER | 0.5 | Backend constant applied once |
| TROOP_DAMAGE_MULTIPLIER | 0.5 | Backend constant applied once before upgrades |
| current_round / simulation_tick | 1 / 0 | Runtime checkpoints, not host inputs |
| timer_state.phase_ends_at / next_tick_at | server timestamps | Persisted phase/tick deadlines |

Continuous match_duration_seconds is derived from preparations+battles: default 1,200 seconds. Legacy phase_durations/round_duration_seconds apply only to legacy mode. Standard preset uses 3 rounds/20 minutes; Quick 2 rounds/15 minutes; Blitz 2 rounds/10 minutes. Existing income is awarded once per completed major battle, including the last battle, never per tick. The creation form defaults the first preparation to 120 seconds when later preparations use 90; the API permits independent values.

## Verification

The browser check uses two independent Chrome contexts, real REST mutations/WebSockets, and actual React/Phaser rendering. It verifies cross-team sprites, stable IDs, construction during a stalled replay, continuous motion, reload recovery, next preparation with persistent towers, and a complete two-round match with stored rankings. It then measures 2/4/8/12/20 teams at normal capacity: five troops plus three towers per team. Instrumentation observes the real scene/store without replacing game rules.

Backend tests cover complete 2/3-round lifecycles, each mobile type's doubled route traversal, odd-damage carry, unchanged tower hits, troop/tower destruction, early victory, simultaneous elimination, +20 reward/idempotency, pause/restart checkpoints, outbox rollback/retry, genuine spectators and 20-team deltas. PostgreSQL tests race four workers on one tick and verify exactly one HP deduction, event and checkpoint.

From backend, run `.venv/bin/ruff check .`, `.venv/bin/pytest`, and `.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test`. Set DATABASE_URL and run `.venv/bin/pytest --ds=config.settings.test_postgres tests/test_round_concurrency.py tests/test_continuous_combat.py` for real row-lock checks. From frontend, run `npm test` and `npm run build`. The npm test command uses Node's tsx import hook directly to avoid the CLI's extra IPC listener.

Browser reproduction: from backend run `TEST_SCHEDULER=1 TEST_BACKEND_PORT=8011 .venv/bin/python tests/browser_preview.py` (temporary database); from frontend run `API_PROXY_TARGET=http://127.0.0.1:8011 npm run dev -- --port 5176 --host 127.0.0.1`, then `node tests/continuous.browser.mjs`. Playwright and Chrome are required; execution here used bundled Playwright through NODE_PATH.

Backend benchmark: run `manage.py benchmark_continuous --output OUTPUT.json` with a disposable database and InMemory Channels settings. It creates/deletes only its own measurement rooms. Forty committed ticks per team count include ORM persistence and outbox dispatch/checkpoint overhead, excluding scenario setup and connected-client fan-out. `--near-capacity` opts into 30 troops/team; reported results use the normal five.

## Deployment and limits

Apply `manage.py migrate`, then rebuild/restart backend/frontend. Production needs PostgreSQL row locks and shared Redis Channels for multiple processes. Migrations add GameEntity.simulation_state and MatchEvent.broadcasted_at; historical events are checkpointed to avoid replay flooding. No existing user database was changed: browser, benchmark and PostgreSQL verification used disposable databases. Create a new room to use continuous mode; existing rooms retain legacy rules.

Measurements are local on one macOS host, one active measured room, SQLite/InMemory Channels and Chrome headless. Preview SQLite now uses transaction_mode=IMMEDIATE to serialize writers and avoid deferred transaction upgrade conflicts with concurrent snapshots. TCP browser tests include real WebSockets but do not benchmark Redis or internet latency. Normal 20-team capacity reaches 160 entities. Optional 30 troops/team, many simultaneous rooms, mobile hardware and a sustained 20-minute browser run were not benchmarked. Divergence compares the observing team's entities against a paused server read; two-client identity/reconnect/public-payload checks are separate. No claim is made about every frame across 80 clients.

The build retains the existing large Phaser chunk warning. Finite tick logs can still be large; completed-match retention/archival is an operations concern. broadcasted_at means dispatch, not browser receipt; snapshots repair missed transport. Browser runs accelerate the explicit movement baseline and durations; default-speed route timing is covered by engine tests. Daphne starts scheduling on its first request, supplied by production health checks after a restart; lifespan-capable servers start on startup.

See [audit](REALTIME_COMBAT_AUDIT.md), [architecture](CONTINUOUS_BATTLE_ARCHITECTURE.md), [event contract](REALTIME_EVENT_CONTRACT.md), [balancing](COMBAT_BALANCING.md), [browser evidence](qa/continuous-browser.json), [backend measurements](qa/continuous-backend-benchmark.json), [battle](qa/continuous-battle.png) and [finished match](qa/continuous-results.png).

## Measured results

Final Chrome run: cross-team troop visibility **65 ms**, tower visibility **65 ms** (HTTP submission through observed sprite arrival, local host). The tower check deliberately stalled legacy replay. All browser checks passed, with no page errors.

| Teams | Initial entities | Tick median / p95 ms | Browser FPS median | Socket KB/s per viewer | Event latency p95 ms | JS heap MB |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 16 | 14.43 / 49.25 | 60 | 12.85 | 18 | 46 |
| 4 | 32 | 14.56 / 24.57 | 60 | 24.21 | 16 | 48.9 |
| 8 | 64 | 22.22 / 31.83 | 60 | 47.96 | 16 | 94.5 |
| 12 | 96 | 26.76 / 59.82 | 60 | 70.75 | 21 | 56.2 |
| 20 | 160 | 38.16 / 69.07 | 60 | 116.74 | 28 | 68.1 |

Backend ticks used a median of **11 SQL queries** at every measured team count. All paused own-team state comparisons reported **zero divergent entities**. Backend and browser measurements are separate runs; browser scenarios last about eight seconds each. Peak backend process RSS was 95.5 MB. Detailed samples and scope are in the JSON artifacts linked above.

Final automated results: **193 passed / 5 skipped on SQLite** (the skipped checks require PostgreSQL), **17 passed on disposable PostgreSQL 17**, **51 frontend tests passed**, **13 preview/continuous regression checks passed**, Ruff clean, TypeScript/Vite build passed, and no missing migrations. The browser report is PASS. See [machine-readable test summary](qa/continuous-test-results.json). PostgreSQL verification includes all five checks skipped in the SQLite run.
