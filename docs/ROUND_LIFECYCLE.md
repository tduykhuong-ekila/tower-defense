# Round lifecycle investigation and implementation

This records the initial combat/lifecycle work. The subsequent
[full gameplay audit](FULL_GAMEPLAY_FLOW_AUDIT.md) and
[implementation report](FULL_GAMEPLAY_FLOW_IMPLEMENTATION.md) document later-round
interaction recovery, the current replay policy and the expanded final test results.

## Findings before changes

- Django already has a deterministic combat engine, graph movement, tower/unit attacks,
  shield/base damage, income, scoring and a host-only manual resolution endpoint.
- No running scheduler calls that engine or advances timed phases. Phaser already consumes
  `COMBAT_RESOLVED`, so deployment alone cannot cause movement or attacks.
- The client treats the resolved round as the next planning round; timer changes are
  absent from live lifecycle events.
- The database bridge omits disabled towers, resets generator cooldowns each round and
  never saves shield lifetimes. EMP consequently disables a tower indefinitely.
- Final score ranking can contradict an elimination winner; final scores are not copied
  onto teams. Base shield and retargeting deltas are incomplete on clients.
- WebSocket answer submission uses an invalid service argument and references a missing
  unit `tier` attribute, although the REST question flow works.

## Minimal implementation plan

1. Add a persisted match clock and an ASGI scheduler using existing Django/Channels
   dependencies. Lock matches before checking deadlines; reuse combat round idempotency.
   Start automatic combat in BUILD_AND_SCOUT (as used by the existing balance preview),
   then continue through WAR and FINAL_ASSAULT. Preparation remains a planning period.
2. Preserve pause/resume remaining times, resolve equal round/phase boundaries once,
   recover overdue work after restart, expire questions/reward grace periods, and end
   by elimination or the configured match/phase deadline.
3. Repair combat persistence, targeting and result consistency without changing catalog
   prices, HP, damage, range or movement. Keep a single 20-coin or free-unlock reward.
4. Extend live deltas with authoritative timers, shields and targets. Show the planning
   countdown and completion state while retaining the existing Phaser playback.
5. Add regression and complete-match integration tests, run existing backend/frontend
   suites and build, then exercise real browser/WebSocket clients against an isolated DB.

This checkout has no Git metadata. Changes are made in place; existing databases and
preview matches are not used for destructive validation.

## Implemented behavior

- `backend/apps/matches/scheduler.py` wraps the ASGI application. Daphne starts one
  clock task per worker on its first request (lifespan-capable servers can start it at
  startup). It ticks every second and continues after all browsers disconnect.
- `timer_state` stores phase start, round start, next round deadline and match deadline.
  Automatic rounds begin in BUILD_AND_SCOUT, continue across WAR/FINAL_ASSAULT, and
  resolve before a phase transition when deadlines are equal. Overdue deadlines are
  replayed in order, at most 120 transitions per tick. This is discrete turn-based
  resolution, not continuous combat. Results end gameplay immediately.
- Match row locks serialize the clock, purchases, snapshots and manual resolutions.
  Each scheduled round supplies `expected_round`. Replaying a resolved round returns
  its existing events without moving units, charging coins or awarding income again.
- Host manual resolution remains available in battlefield Settings. It uses the displayed
  planning round and opens a fresh planning window. It retains the existing host override
  ability to resolve during preparation.
- Pause freezes phase, round, match and reward deadlines; resume shifts them forward.
  Open questions close on pause. Pending rewards at phase boundaries have the configured
  grace period, then expire without an arbitrary reward. No rewards can mutate a finished
  match. A retry of a previously successful reward still returns that claim.
- Shield duration and generator cooldown are persisted in match configuration. EMP towers
  are loaded into combat, skip their attack and recover after one resolved round.
  Disabled towers continue occupying their slots and counting toward capacity.
- Unit attacks can damage enemy towers within the configured graph range; artillery's
  catalog range is respected. Base impacts remain restricted to the configured base
  attack node and consume the attacking unit. Dead bases cannot receive extra impacts
  or have their destruction credit stolen by later overkill.
- Live events carry the next planning round, clock, shield values and retargeting. The
  client reconciles server values, runs the existing Phaser animation queue (bounded
  below the minimum planning interval), disables finished-match commands, and exposes
  results immediately. Reconnect snapshots lock the same match row for coherent sequence
  and board data, retaining the existing bounded query budget.
- Elimination victory outranks an eliminated opponent's score. Timed victory uses existing
  score/tie rules, including shared first place. Team scores are persisted, end events
  occur once, and a failed results request no longer displays fictional standings.
- WebSocket question/reward/construction/special-action handlers now call the actual
  domain services and return refreshed private balances.
- Reward choice is exactly **20 coins once** or a **free unlock**. Deployment/construction
  still deduct catalog prices. No Action Tokens, new unit stats, or dependencies were added.
  Runtime fields use existing JSON configuration, so no migration is required.

## Repeating verification

Normal development/production continues to use the documented Daphne/runserver ASGI
entry point. Rebuild existing Docker backend/frontend images to use the new code. Do not
run this game through the WSGI entry point: WebSockets and the clock belong to ASGI.

```sh
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/python manage.py check --settings=config.settings.test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
# PostgreSQL: use a local account permitted to create test databases.
# pytest creates/drops test_tower_defense_combat; existing game tables are untouched.
DATABASE_URL=postgres://USER:PASSWORD@HOST:PORT/DATABASE \
  .venv/bin/pytest --ds=config.settings.test_postgres -q
cd ../frontend
npm test
npm run build
```

The PostgreSQL-only tests race four scheduler workers on one deadline, four identical
purchases against the same shared team wallet, and four competing coin/unlock claims.
SQLite skips those three tests because it does not implement PostgreSQL row locks.

For a disposable live browser run, start the isolated server and frontend separately:

```sh
cd backend
TEST_SCHEDULER=1 TEST_BACKEND_PORT=8021 .venv/bin/python tests/browser_preview.py
# Another terminal, from frontend:
API_PROXY_TARGET=http://127.0.0.1:8021 npm run dev -- --host 127.0.0.1 --port 5176
```

Open `http://127.0.0.1:5176/tests/fixtures/combat.html`, create the battle, and open the
attacker/defender links in separate tabs. The fixture makes real API purchases and
observes real WebSocket events; it does not alter DB combat outcomes, teleport entities,
or calculate damage. The disposable DB is removed when the backend exits. Fixture HTML
is a Vite development asset and is not included in the production build.

## Browser evidence (17 October 2026)

Two independent player tabs completed an automatic match in seven combat rounds:

| Authoritative event | Count |
|---|---:|
| Unit spawned | 6 |
| Unit moved | 38 |
| Unit attack | 9 |
| Tower attack | 3 |
| Base damage | 1 |
| Entity destroyed | 3 |
| Base destroyed / team eliminated / victory declared | 1 each |

The room used allowed host configuration (10 base HP, 500 initial coins, 10-second
planning windows). Unit/tower stats and prices were unchanged. Amber Attack won with
148 points; Blue Defense's base reached zero HP and its client entered spectator mode.
Both tabs displayed the same final state. [Results screenshot](qa/combat-results.png).
Automated complete-match tests separately cover 4 and 20 teams using legal deployments
from spawn through every opponent's elimination and persisted final rankings.

## Final executed checks

| Check | Result |
|---|---|
| Full PostgreSQL backend suite | **175 passed** (91.12s) |
| Full SQLite backend suite | **172 passed, 3 PostgreSQL-only skips** (32.23s) |
| Frontend `npm test` | **40 passed** |
| Backend Ruff | Passed |
| Django system checks | Passed |
| Migration drift check | No changes detected |
| Frontend TypeScript + Vite production build | Passed |
| Live browser match | Seven automatic rounds; elimination, synchronized spectator mode and persisted winner verified |

The PostgreSQL suite produced a teardown warning about a lingering test connection
preventing automatic database removal. After the test process exited, the disposable
`test_tower_defense_combat` database was explicitly dropped and its absence verified.
No existing game database was reset or migrated during verification. The existing Vite
warning about Phaser's large bundle remains; it does not prevent the production build.

The previous restart test was changed to use committed test transactions: closing a
PostgreSQL connection inside a wrapping test transaction otherwise discards the state
it was supposed to recover. PostgreSQL locking tests now run against real row locks,
and the existing 20-team snapshot query-budget test remains green.
