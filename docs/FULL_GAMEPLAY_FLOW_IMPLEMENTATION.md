# Full gameplay flow implementation — 17 October 2026

## Confirmed causes and outcome

The [audit](FULL_GAMEPLAY_FLOW_AUDIT.md) records two reproduced interaction locks:

1. The server had opened Round 2 PLANNING and accepted a deployment, while React
   disabled its card because Phaser was replaying Round 1. Accumulated/throttled
   animations could outlast the next planning window.
2. An expired pending reward removed the dialog's data/DOM without clearing the
   requested modal state. `MODAL_OPEN` then blocked purchases with no visible dialog.

A separate synchronization defect sent pre-purchase `coins_after` values after the
correct economy event. A client could consequently display more money than the server
would accept. API waiting also had no time limit or recovery snapshot on failure.

Legal actions now derive from authoritative planning state, occupancy, unlocks and
resources. Starting a legal placement finishes the previous replay without rebuilding
the scene. Invalid actions remain rejected with an explanation. Expired or removed
dialogs release their interaction lock. Purchases send the actual post-debit balance.

## Final state machine

The existing match stages remain:

```text
LOBBY → PREPARATION → BUILD_AND_SCOUT → WAR → FINAL_ASSAULT → RESULTS
```

Within the existing round clock:

```text
PLANNING(N, deadline)
  → LOCKED → RESOLVING → RESULTS
  → PLANNING(N+1, new deadline), or FINISHED / match RESULTS
```

`timer_state.round_phase` extends the existing JSON timer; there is no new round model
or parallel scheduler. Following architectural decision D3, resolution is one atomic
server transaction. LOCKED/RESOLVING/round RESULTS are internal steps, without a new
timed dwell. Commands serialize behind the match row lock and validate against the
committed state. Failed transactions roll back the round and its mutations together.
The client animation presents the completed round after the next planning window opens.

The existing ASGI clock resolves automatic rounds from BUILD_AND_SCOUT, continues in
WAR/FINAL_ASSAULT, and advances timed match stages. Preparation is a planning period;
the existing host override may resolve it manually. Deadlines, pause/resume and overdue
recovery remain server-owned. Host/browser disconnection does not own or stop the clock.
Explicit `expected_round` retries replay stored results without repeating damage/income.

## Eligibility and state lifetime

| Rule/state | Behavior |
|---|---|
| Deployment | Every eligible PLANNING window in PREPARATION, BUILD_AND_SCOUT, WAR or FINAL_ASSAULT |
| Construction | Every eligible PLANNING window in PREPARATION, BUILD_AND_SCOUT or WAR |
| FINAL_ASSAULT construction | Remains prohibited by the existing implementation |
| Purchase count | One entity per request; no invented deployment/construction quota per round |
| Active troops | Existing configured capacity, default five; QUEUED/ACTIVE/DISABLED occupy capacity |
| Towers and slots | Existing configured capacity, default three; surviving/disabled towers retain slots |
| Repair | One accepted use until round resolution; resolved actions release the existing limit |
| Coins/unlocks/question history | Persist across round entry |
| Bases/HP/shields/entities | Persist and change only through existing server rules |
| Planning round and deadline | Advance once per resolved round; fresh authoritative deadline |
| Pending reward | Existing expiry/grace period; never automatically selects a reward |
| Modal, placement, animation cursor | Transient presentation, never authoritative permission |

Destroyed entities release occupancy. A team with three living towers cannot build a
fourth in Round 5: the tests reserve its third slot for Round 5 instead of resetting
capacity. No catalog prices, HP, damage, movement, range, team limits, scoring weights
or reward amounts were changed. Standard definitions remain in `apps/units/seeds.py`
and the existing match configuration/GDD.

A correct answer still grants one choice: exactly **20 coins once**, or one **free
unlock**. A later purchase deducts the catalog cost. Successful idempotent retries
return the stored claim/action, including across a round boundary; they do not create
another mutation. Question/reward membership and history checks remain in their services.

## Backend changes

- `apps/matches/action_policy.py`: shared match/team/member/round/stage policy and
  unlock/capacity/coin purchase validation. Rejections carry codes including
  INVALID_PHASE, TEAM_ELIMINATED, MATCH_FINISHED, UNIT_LOCKED, TOWER_LOCKED,
  UNIT_LIMIT_REACHED, TOWER_LIMIT_REACHED, INSUFFICIENT_COINS and INVALID_POSITION.
  Rejection logs include match, team, round, round phase, match stage, action and reason,
  with no credentials. Existing endpoint error text remains in `error`; `error_code`
  is additive. Other existing validations use VALIDATION_ERROR if no specific code exists.
- `apps/units/services.py`: deployment, construction, targeting and special actions
  use the shared context; placement/ownership checks remain authoritative. All six
  debit paths refresh coins before creating their corresponding gameplay event.
- `apps/questions/services.py`, `apps/rewards/services.py`: use the shared context
  while retaining question eligibility, single-choice reward history and idempotency.
- `apps/units/views.py`, `apps/questions/views.py`, `apps/rewards/views.py`,
  `apps/realtime/consumers.py`: preserve API conventions and expose structured reasons.
  Private team-state adds `round_number` and contextual `action_availability`.
- `apps/matches/clock.py`, `apps/matches/services.py`: initialize/open PLANNING in the
  existing timer. `apps/matches/serializers.py` and `apps/realtime/services.py` expose
  server-owned `action_rules` in match configuration for frontend derivation.
- `apps/combat/services.py`: explicit internal resolution steps, persisted live team
  scores using the existing scoring function, `TEAM_SCORE_UPDATED` combat events and
  `ROUND_STARTED` with the actual next round/timer after `COMBAT_RESOLVED`.
  `apps/combat/scoring.py` retains RESULTS on finalization.

The existing combat engine still performs movement, targeting, towers/unit attacks,
shield/base damage, destruction, elimination, income and victory. Surviving units and
towers are loaded again in subsequent rounds. Purchases are charged at acceptance;
combat does not charge them again. Finalization persists the official rankings once.

## React, Phaser and synchronization changes

- `src/game/actionAvailability.ts`: a common preliminary policy for cards and placement,
  using server stage rules plus local synchronized resources/entities. Paused, finished,
  eliminated, spectator, disconnected, pending and actual non-planning states remain
  unavailable. Cards expose a reason/tooltip instead of silently disabling everything.
- `src/pages/BattlePage.tsx`: replay no longer overrides server permission. Selecting
  a legal card or issuing a mutation finishes the old replay. Placement rechecks its
  eligibility, then the server checks it again. HUD distinguishes current PLANNING from
  the previous combat replay. Special-action constraints receive explanations.
- `src/game/gameplayModal.ts`: only a dialog backed by valid question/reward data can
  block React/Phaser input. Expiry, claims, removed snapshot data and mismatched reward
  IDs clear stale requested modal state. Visible valid dialogs keep their input lock.
- `src/game/scenes/BattleScene.ts`: a newer combat supersedes stale playback; no replay
  backlog. An eight-second wall-clock watchdog recovers even if the Phaser timer is
  paused. Shutdown clears timers. Camera controls and read-only inspection remain usable;
  gameplay marker clicks retain mutation gating. Existing art/animations are retained.
- `src/game/PhaserGame.tsx`: snapshots/skip clear early queued events; visibility
  restoration ends stale replay. The scene and its camera are preserved.
- `src/stores/matchStore.ts`, match/team-state types: recognize ROUND_STARTED and round
  phase. Duplicate sequences and older snapshots are ignored; late old-round lifecycle
  events cannot regress the current round or replay old damage into newer state.
- `src/services/api.ts`: requests have a 15-second timeout unless the caller supplies
  its own signal. Timeout/error releases pending in `finally` and requests a fresh
  snapshot/team state. An uncertain purchase is never automatically submitted again.

Fresh snapshots remain the recovery source for missed messages/reconnect. Sequence
checks happen before playback side effects; REST results overtaken by newer WebSocket
events are ignored. Authoritative snapshots cancel obsolete playback and reconcile
question/reward state, entities, wallet, team status, round and deadlines. Private
balances/unlocks/rewards keep their existing team-scoped transport.

## Executed validation

| Check | Result |
|---|---|
| Complete PostgreSQL backend suite | **185 passed**, 95.99s |
| Complete SQLite backend suite | **181 passed, 4 PostgreSQL-only skips**, 31.32s |
| Frontend `npm test` | **48 passed** |
| Backend Ruff / Django system check | Passed |
| Migration drift | No changes detected |
| Frontend TypeScript lint / production build | Passed |
| Two-player real browser full match | Passed; no page errors |
| Expired reward browser regression | Passed; no dialog, deployment enabled and purchased successfully |

`tests/test_full_gameplay_flow.py` runs five successive purchase/combat cycles with
2/4/8/20 real joined teams, preserves entities/unlocks/question history/wallets,
retries purchases across boundaries and checks current event balances. It also rejects
deploy/build requests in LOCKED/RESOLVING/RESULTS without spending coins and verifies
distinct failure reasons and FINAL_ASSAULT policy.

`tests/test_round_concurrency.py` uses PostgreSQL row locks to race schedulers,
duplicate deployments and competing reward choices, plus two actual members independently
deploying against one shared wallet in Rounds 1 and 2. Existing tests cover overdue
restart recovery, pause/resume, host independence, shields/EMP, multi-round attacks,
eliminated/finished mutations and complete 4/20-team matches through final rankings.

Frontend regressions cover actual capacity/coins/unlocks/phase reasons, out-of-order
round events, timeout recovery, expired/missing/mismatched dialogs and valid modal locks.

The full browser script uses real authenticated APIs, React, Phaser and WebSockets:
room creation → team joins/readiness → start → questions → 20-coin reward/free tank
unlock → Round 1 infantry/MG purchases → automatic Round 2 → repeat both purchases →
Round 3 canvas deployment → planning refresh → paused Phaser clock/watchdog recovery →
Round 5 canvas construction/deployment → playback refresh → legal tank waves → base
destruction/elimination → victory → persisted results page. Subsequent manual rounds
accelerate this test via the existing host endpoint. The first transition is automatic,
with no host WebSocket. The browser fixture only captures the actual scene for canvas
coordinates/clock-stall simulation; it does not substitute combat or fabricate damage.

Evidence: [original Round 2 mismatch](qa/flow-reproduction.json),
[expired modal before](qa/reward-expiry-reproduction.json),
[expired modal after](qa/reward-expiry-browser.json),
[full browser checks](qa/full-gameplay-browser.json),
[Round 5 screenshot](qa/full-gameplay-round5.png),
[results screenshot](qa/full-gameplay-results.png).

## Repeating the checks and runtime requirements

From `backend`, run `.venv/bin/pytest -q`, `.venv/bin/ruff check .`, and Django's
`check` / `makemigrations --check --dry-run` with `--settings=config.settings.test`.
For real locking, use `DATABASE_URL` for a local account permitted to create test
databases, then run `.venv/bin/pytest --ds=config.settings.test_postgres --create-db -q`.
This creates `test_tower_defense_combat`; existing game tables are not migrated/flushed.
From `frontend`, run `npm test`, `npm run lint` and `npm run build`.

For browser checks, use two terminals:

```sh
# From backend: isolated temporary DB, removed on shutdown
TEST_SCHEDULER=1 TEST_BACKEND_PORT=8021 .venv/bin/python tests/browser_preview.py
# From frontend
API_PROXY_TARGET=http://127.0.0.1:8021 npm run dev -- --host 127.0.0.1 --port 5176 --strictPort
```

With a Playwright runtime and Chrome available, from `frontend`:

```sh
# NODE_PATH may point to an existing Playwright installation outside this repository.
TEST_BASE_URL=http://127.0.0.1:5176 node tests/full-gameplay.browser.mjs
TEST_BASE_URL=http://127.0.0.1:5176 node tests/reward-expiry.browser.mjs
```

The fixture questions are short-text questions so the real UI can answer them. Test
fixture HTML is served only by the development server and is absent from `dist`.

No dependency or migration was added. Rebuild/restart the existing backend/frontend
Docker images to apply source changes. Use ASGI (Daphne), as already configured;
the clock and WebSockets are not available through WSGI. No existing game database
was reset during validation.

## Known limits

- LOCKED/RESOLVING/round RESULTS remain internal atomic steps, so clients do not receive
  three separately timed windows. Combat playback may overlap the next planning period;
  legal interaction deliberately finishes that presentation.
- The complete browser match uses two player clients. 4/8/20-team five-round behavior
  and 4/20-team completion were verified by backend integration tests, not twenty
  simultaneous browser clients in this run.
- Build retains Vite's existing large Phaser chunk warning. It is not a build failure.
- PostgreSQL reported a teardown warning from a lingering test connection after all
  185 tests passed. After the test process exited, the disposable test database was
  explicitly dropped and its absence verified (remaining count: zero). Both isolated
  preview servers were stopped; source game tables remain untouched.
