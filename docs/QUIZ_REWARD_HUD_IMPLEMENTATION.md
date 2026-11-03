# Quiz, reward, inspection card and HUD implementation

> Fixed +30 rewards are superseded by [mystery coin bags](MYSTERY_COIN_REWARDS.md) for unanswered and newly assigned missions. Previously earned fixed rewards retain their amount.

> Historical viewing-lease behavior is superseded by [persistent countdown lifecycle](QUIZ_COUNTDOWN_LIFECYCLE.md). Closing or disconnecting now keeps the original deadline running.

Date: 2026-10-24 (Asia/Ho_Chi_Minh).

## Team session and countdown

`TeamQuestion` retains the existing answer/reward statuses. It now also stores `remaining_ms`, `timer_started_at`, `timer_status`, `timer_version`, private `viewing_leases`, and the snapshotted `reward_coin_amount`.

Timer states are `NOT_STARTED`, `RUNNING`, `PAUSED`, `EXPIRED`, `COMPLETED`. Temporary submission/claim progress is local UI state; final eligibility and transitions are server controlled.

- GET `.../questions/current/` recovers the latest team question, including an incorrect, expired or claimed result. The first assignment is NOT_STARTED. GET never acknowledges a result or advances to the next question.
- POST to that same URL accepts `action`, `question_id` and, for viewing operations, a UUID `viewer_id`.
- `OPEN` starts/resumes the existing remaining budget. A second participant opens another lease against the same row; it cannot reset the budget or create a second countdown.
- `HEARTBEAT` renews an existing lease. It cannot resurrect a lease explicitly removed by Close. An open visible UI can explicitly recover a lease after reconnection/suspension.
- `CLOSE` settles server elapsed time, removes only that participant/tab's lease, and pauses when the final lease closes. The UI waits for acknowledgement before hiding. Closing while submitting is blocked.
- `NEXT` acknowledges the completed question ID. Match-row locking plus identity comparison makes duplicate/stale Next requests return the existing next question rather than skip again. Unresolved questions and pending rewards block progression.
- Heartbeats run every 4 seconds only for a visible pending question. Leases expire after 12 seconds. Time consumed after an abrupt disconnect stops at the latest lease deadline, even if cleanup runs later. Normal Close/visibility-change pauses immediately on server acknowledgement.
- All elapsed-time calculations use server timestamps. Client timers only interpolate the server's returned milliseconds using `performance.now()`. Browser clock changes cannot extend submission eligibility.
- Submission settles the timer under the same match/team/question locking order. Unopened/paused submissions are rejected. Final submissions are idempotent, stop the timer, and either preserve the incorrect result or establish PENDING_REWARD. Timeout produces EXPIRED with no entitlement.
- Match pause and result finalization freeze unanswered sessions. Reopening after a host resume resumes the same budget. Match completion keeps an explanatory dialog with submission/claim actions unavailable.

REST and WebSocket snapshots expose the same `TeamQuestionSerializer` contract, including `timer` and pending reward options. `QUESTION_TIMER_UPDATED` is a private, team-scoped durable event; opponents receive redacted envelopes preserving the sequence stream. Timer revisions and question sequence numbers prevent older responses from replacing newer local state. `expires_at` remains for wire compatibility; `timer` is the eligibility/countdown contract for updated clients.

## Popup and reward stability

Modal intent is independent of combat state and answer status. Expired and peer-claimed rewards render explicit question/result feedback. Combat, coins, construction, deployments and round-clock updates cannot close a dialog. Match/team identity changes clear the local session.

Answer drafts reset only on question ID change. Reward mode/selected unit reset only on entitlement ID change. Closing either UI preserves its state; the Knowledge Mission control reopens a pending reward. Own successful claims close after acknowledgement. A teammate's successful claim renders an already-claimed message. Existing focus trapping is retained; Escape and Close share the same preservation policy. Backdrop clicks do not dismiss either dialog.

## Reward compatibility

Old default: **20 coins**. New-match default, preset/balance preview, tutorial and normal UI: **30 coins**. Stored configurations may retain 20; configuration validation accepts the two supported values.

Each assignment snapshots its match's configured amount. Options and coin credit both use that snapshot. Changing configuration after an answer cannot alter an earned amount. Existing match configurations are not rewritten. Migration `questions.0003` pins existing assignments to their stored match amount (20 when absent), pauses pending questions with their actual remaining old deadline budget, and never edits `RewardClaim` or coin transactions. Previously expired time is not reset.

Existing atomic claim handling, the one-to-one claim constraint, team ownership checks, idempotency keys and economy credit events remain in force. Unlock remains the free alternative, with deployment/build costs unchanged. Existing legacy phase-transition reward grace deadlines are retained; legitimate grace expiration now displays an explicit result instead of silently closing the UI.

## Entity information cards

`EntityInfoCard.tsx` renders one reusable illustrated card. A small inspection store isolates pointer selection from the battlefield component tree. Phaser retains hit testing, uses its existing sprite/container handlers (including pooled infantry), and passes only entity ID and screen anchor. There are no per-troop DOM roots or pointer-move fetches. The anchor is stable; positioning clamps to the viewport, and pointer-out hides after 120ms. Touch taps pin the same card; an outside capture layer or Close dismisses it without triggering deployment.

The card subscribes to the live entity registry so HP changes use the current authoritative entity. It shares `EntityIllustration` / `entityArtwork` with unlock cards, supports team ownership, current/max HP and bar, damage, range, movement speed, level, and continuous-mode attack interval. Server `inspection_stats` uses existing damage/upgrade/cooldown conversions without modifying fractional damage carry. Snapshots, spawn/tick deltas and REST entity payloads share these effective stats; bulk serializers receive match configuration without per-entity match queries. Fields absent in authoritative data are omitted. Arsenal native text tooltips are replaced with the illustrated preview.

## Compact arena header

The title is the React `.round-standard` overlay in `BattlePage`, not a Phaser map label. Decorative hanging-banner padding, pointed silhouette, ornament and stitches were removed. Round, phase, phase clock and legacy planning clock remain visible.

At 1440×1000, a browser comparison against the original declarations measured **140.28px → 53.34px height**, approximately 62% less height (87px of vertical battlefield coverage recovered). Its total rectangular footprint falls by approximately 47%. At 390×844 the header is 145×66.23px. At mobile/tablet sizes a grid reserves independent columns for team resources, arena information and controls. Automated assertions cover 320px, 390px and 768px widths without header/control overlap. The camera/canvas/deployment mechanics are unchanged.

## Verification

The full commands and saved outputs are recorded in `docs/qa/quiz-*-tests.txt` and `quiz-session-browser.json`. Tests were executed against disposable databases; the running Docker application's images/database were not redeployed.

- Full backend regression suite on SQLite: **412 passed, 15 skipped** (PostgreSQL-only cases).
- PostgreSQL row-lock suite: **85 passed**. Includes concurrent assignment, duplicate answers, mutually exclusive reward choices, concurrent viewer operations and idempotent Next, plus batch deployment and real Channels clients.
- Additional final match-end/pause suite: **30 passed** after centralized freezing was added. The final PostgreSQL session/concurrency subset also passed **24 tests** with that freeze behavior.
- Frontend Node tests: **94 passed**. TypeScript check and production build passed; Vite retains the existing large Phaser bundle warning.
- `quiz-session.browser.mjs`: PASS with real Chrome, two teammates, opponent actions, actual WebSockets and Phaser hit tests. Covers untouched unopened budget; shared open/close; preserved answer draft and question ID across deployment, tower building and phase/combat updates; paused hidden budget; close/reopen; reconnect recovery; exact +30 and duplicate claim; teammate balance synchronization; Tank selection surviving opponent claim and close/reopen; explicit extra questions/unlocks; Infantry/Tank/Artillery/Cannon artwork and real stats; desktop hover/touch; viewport bounds; responsive header measurements; explicit match-ended dialog.
- Reward-grace expiration browser: PASS in legacy mode, with explicit expiration feedback followed by Close and a successful deployment. XLSX/multiple-choice browser: PASS, including retained option B across phase/combat changes and a heartbeat, team-shared +30, bank order and explicit Next. Real timeout browser: PASS using the imported bank’s unchanged 60-second limit; EXPIRED remained visible, awarded nothing, and did not advance until explicit Next.
- `quiz-card-hp.browser.mjs`: PASS. A touch-pinned Infantry card stayed visible through three real server combat rounds; persisted HP and displayed HP both changed from 80 to 70 through the WebSocket flow.
- Django migration drift check, Python compilation and targeted Ruff checks passed.

Screenshots: `quiz-unlock-stability.png`, `quiz-entity-card-desktop.png`, `quiz-compact-mobile.png`.

Existing gameplay regressions cover up to 20 teams, 80 players, continuous combat, six tower slots, batch deployment, movement/formation/sprites, Infantry HP 80/speed 7, Artillery HP 80/speed 5, Cannon range 2, XLSX banks/team progress, bidirectional event recovery and match scoring/results.

## Operational notes and limitations

Apply the new database migration before starting the updated backend, and rebuild/restart the frontend/backend together because the quiz wire protocol changed. Existing Docker services use baked images rather than bind-mounted source; editing this repository alone does not update those containers.

A network outage/process death cannot deliver an immediate Close acknowledgement: the last viewing lease can consume at most 12 further seconds. Normal acknowledged Close consumes no time while hidden. Selected answers/unlock cards survive hide/reopen in the current mounted page; a full reload restores the authoritative question/budget/entitlement, but not an unsent local draft or unconfirmed unlock selection. Legacy non-continuous combat has no seconds-based fire cadence, so cards omit that field. Historical browser scripts were aligned with explicit opening/Next and +30, but only the browser suites explicitly listed as run are claimed verified here.

## Reproduction commands

From the repository root:

```sh
backend/.venv/bin/python -m pytest backend/tests -q --disable-warnings
npm test --prefix frontend
npm run build --prefix frontend
backend/.venv/bin/python backend/manage.py makemigrations --check --dry-run --settings=config.settings.test
```

For PostgreSQL, provide the local `DATABASE_URL` and run pytest with
`--ds=config.settings.test_postgres`; tests create/drop `test_tower_defense_combat`.
The executed 85-test selection included `test_quiz_sessions.py`,
`test_question_bank_concurrency.py`, `test_round_concurrency.py`, `test_phase_2.py`,
`test_artillery_slots_batch.py` and `test_battle_websocket.py`.

For browser checks, start the disposable backend with `TEST_SCHEDULER=1
TEST_QUIZ_SESSIONS=1 TEST_BACKEND_PORT=8021 backend/.venv/bin/python
backend/tests/browser_preview.py` and Vite with `API_PROXY_TARGET=http://127.0.0.1:8021`.
Set `TEST_BASE_URL` to Vite's port (5181 in this run) and `NODE_PATH` to an installed
Playwright package directory. Run the `.mjs` files with Node:
`quiz-session.browser.mjs`, `quiz-timeout.browser.mjs`,
`reward-expiry.browser.mjs`, `question-bank.browser.mjs`, and `quiz-card-hp.browser.mjs`.
