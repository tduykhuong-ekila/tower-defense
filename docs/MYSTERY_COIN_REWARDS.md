# Knowledge mission mystery coin bags

Implemented 2026-10-27.

| Coins | Probability |
| --- | --- |
| 20 | 15% |
| 25 | 20% |
| 30 | 35% |
| 40 | 25% |
| 60 | 5% |

Expected payout is **31.5 coins** per correct answer when choosing coins; maximum is 60.
The economy preview reports expected question income separately from the maximum.

## Persistence and API

`rewards/coin_rewards.py` owns the odds. The server draws one integer ticket in
`[0, 99]` using `secrets.randbelow`, under the existing answer transaction and
match/team/question locks. The draw is stored in `TeamQuestion.reward_coin_amount`
only on the first correct submission. Wrong, expired and duplicate submissions
cannot draw again. The free unit-unlock alternative remains available.

Mystery bag options expose `coin_amount: null` and `coin_distribution` containing
the public probabilities. The stored amount is omitted from participant question
serializers, reward options, answer events and reconnect snapshots. The claim
response and claim event disclose the actual credited amount. Existing atomic
claims, one-to-one claim constraints, team ownership and idempotent replay remain
in force. Reloads, close/reopen, network retries and teammate requests cannot reroll
the entitlement or add another credit.

Migration `questions.0005` enables bags for existing unanswered assignments.
Already earned or claimed fixed rewards retain their amount. The old
`correct_answer_coin_reward` configuration field remains for compatibility with
fixed assignments; new assignments use the mystery bag distribution.

## Interface

The choice card displays “Túi coin bí ẩn”, the 20–60 range and expandable odds.
Opening runs for at least 800ms, then shows the authoritative amount and a
Continue button. The 40-coin result has a special caption; 60 coins adds a golden
glow and “May mắn!”. Reduced-motion settings disable the shake/pop animations.
The opening/reveal remains visible if a WebSocket event clears pending options
before the HTTP claim response arrives. A receipt does not delay team balance
synchronization. Desktop and mobile use the existing scrollable modal.

## Verification

- Frontend production build and 140 Node tests passed.
- Focused backend regression run: 103 passed, 2 PostgreSQL-only tests skipped.
- Ten mystery bag tests passed, including exhaustive coverage of all 100 tickets,
  five actual payout amounts, no draw on a wrong answer, sealed REST/event/snapshot
  data, retries, unlocks, legacy payouts and rollout migration behavior.
- PostgreSQL: 24 passed covering reward behavior, simultaneous answers/claims and
  round concurrency. The additional exact-one-draw assertion was checked in a
  subsequent 3-test concurrency run, all passed.
- Initial full regression run: 538 passed, 23 skipped and 9 assertions expecting
  fixed +30 failed. These assertions were updated for mystery bags; eight passed
  in a failed-test rerun, and the renamed ninth passed in the focused run.
- `mystery-coins.browser.mjs`: real React/Phaser, REST and WebSocket checks for
  desktop/mobile odds, reload while sealed, authoritative payout, duplicate claim
  by a teammate, shared team balance and the free unlock alternative. A separate
  deterministic modal fixture checks the 60-coin visual and early claim event.
- Django migration drift check and targeted Ruff checks passed.

Evidence: `docs/qa/mystery-coins-browser.json` and `mystery-coins-*.png`.
Older browser scripts that selected the fixed +30 option now use the shared
`tests/helpers/coin-bag.mjs` receipt helper; those full historical scripts were not
rerun as part of this change.

## Local application

The Docker entrypoint runs migrations before starting Daphne. Rebuild both game
services and recreate them together:

```sh
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
```

No database reset or volume removal is needed. Already earned fixed rewards keep
their value; unanswered and subsequently assigned missions use the new odds.

The local backend/frontend containers were rebuilt and recreated for this change.
The backend health endpoint reports database and channel-layer connections healthy;
the frontend serves HTTP 200 at `http://localhost:5173/`.
