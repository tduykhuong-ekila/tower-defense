# Excel bank and continuous quiz implementation

Implemented 2026-10-22 in the existing Django/React/Phaser game.

- [Verified workbook schema](QUESTION_BANK_EXCEL_SCHEMA.md)
- [Audit and repaired restrictions](QUESTION_BANK_GAMEPLAY_AUDIT.md)
- [Staging, preview and room API](QUESTION_BANK_IMPORT_API.md)
- [Gameplay, reward and realtime contracts](CONTINUOUS_QUIZ_GAMEPLAY.md)

## Code and database changes

`apps/questions/excel.py` implements the bounded sample-compatible parser. `banks.py`
implements capability ownership, validation staging, pagination, deletion and atomic
attachment. Existing Question records gain nullable bank/order and source metadata;
QuestionBank stores owner/hash/source/count/errors. Match gains a protected bank reference
and a nullable unique creation-token hash. Existing TeamQuestion, RewardClaim, CoinTransaction
and TeamUnlock remain authoritative, including their existing uniqueness constraints.

Migrations: `questions/0002_question_import_metadata_question_import_order_and_more` and
`matches/0003_match_creation_token_hash_match_question_bank`. Existing questions have no
bank and remain available only to legacy/global rooms. No stored match is silently converted
to a different gameplay mode.

The creation form preserves configuration fields and adds QuestionBankUpload. XLSX selection
supports progress, cancellation, errors, replacement/removal, paged answer-key preview and
explicit selection. Creation stays disabled while a selected bank is unvalidated/unconfirmed.
Room creation without an upload remains available for compatibility.

The existing question/reward services and HUD now support continuous Battle. Assignment,
answer state, team progress, wallet and unlocks survive reconnect and later major rounds.
All quiz data is scoped through the existing private-event projection and snapshot protocol.

## Deployment

```sh
cd backend
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
```

Restart backend workers and rebuild/restart the frontend (or rebuild both Docker images).
Keep Django SECRET_KEY stable for retry-stable creation credentials. Production multiplayer
requires PostgreSQL row locks and a shared Redis channel layer; the local preview uses
single-process SQLite with IMMEDIATE transactions. Cleanup unused expired staging records
with `manage.py cleanup_question_uploads`.

## Verification

See `docs/qa/question-bank-browser.json` and the adjacent upload/battle screenshots for the
actual browser result. Automated source coverage includes the unchanged supplied workbook,
row/header errors, empty/duplicate rows, multiple worksheets, unsafe XML/macros/external links,
limits, import and creation rollback, preview authorization, retry idempotency, isolated
2/4/8/20-team rooms, deterministic progress beyond eight questions, wrong/final answers,
coin/unlock exclusivity, paid deployment after unlocking, all-unlocked fallback, persistence,
private events and completed-match rejection.

PostgreSQL tests exercise competing room creation, assignment, teammate answers and mixed
coin/unlock claims in real separate database connections. Browser verification uses the
actual upload form and three independent React/Phaser sessions for two teams, including
two members of one team, while the real backend scheduler runs.

Verified results:

| Check | Executed result |
| --- | --- |
| Full backend suite, SQLite test database | 322 passed, 10 PostgreSQL-only cases skipped (51.90 seconds) |
| Import/gameplay + real PostgreSQL concurrency suites | 42 passed, no skips (8.77 seconds) |
| Frontend `npm test` | 78 passed |
| Frontend `npm run build` | Passed; existing large Phaser chunk warning remains |
| Backend `ruff check .` / Django `check` | Passed |
| `makemigrations --check --dry-run` | No unrecorded model changes |
| Chrome with actual Excel form + three independent clients | PASS, no page errors; movement while dialog open, single shared coin reward, independent other team, Host disconnect, real reload and second-round quiz verified |

The browser proof is `docs/qa/question-bank-browser.json`; images are
`question-bank-upload.png`, `question-bank-during-battle.png` and `question-bank-battle.png`.
All databases used in these checks were disposable. Existing development/production data
was not migrated during verification.

Repeatable commands from each application directory:

```sh
# backend
.venv/bin/pytest -q
DATABASE_URL=postgresql://USER@HOST:PORT/DATABASE .venv/bin/pytest \
  tests/test_question_banks.py tests/test_question_bank_concurrency.py \
  tests/test_round_concurrency.py --ds=config.settings.test_postgres -q
.venv/bin/ruff check .

# frontend
npm test
npm run build
NODE_PATH=<bundled-node_modules> TEST_BASE_URL=http://127.0.0.1:5187 \
  node tests/question-bank.browser.mjs
```

The browser test expects Vite to proxy to the disposable `tests/browser_preview.py` server
with `TEST_SCHEDULER=1`; set `TEST_BACKEND_PORT` and `API_PROXY_TARGET` together when using
non-default ports. It uses a local Chrome installation and the bundled Playwright package.

## Deliberate limits

The sample defines multiple-choice questions only. No arbitrary schema guessing, retries
for failed final answers or new reward policy is added. Original files are not retained;
normalized questions and source hashes/locations are persisted. Replacing a bank requires
a new stage before room creation; attached banks are immutable. Staging is owned by a
secret capability because existing pre-room creation has no login requirement. Anyone
given that secret has its owner privileges; participants receive no such capability.

These checks do not constitute a new large-army performance benchmark or production
deployment. Existing troop/combat tests are run as regression coverage.
