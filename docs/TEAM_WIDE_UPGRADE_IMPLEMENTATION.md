# Team-wide upgrades implementation

## API and persistence

`POST /api/v1/matches/{match_id}/upgrades/`

```json
{"entity_type":"infantry","expected_current_level":1,"idempotency_key":"unique-request-id"}
```

Participant authentication resolves the caller's own team. Spectators, other-team actors, locked/inactive types, invalid phases, insufficient funds, invalid expected levels and level 5 are rejected. Clients cannot set stats or costs. The service locks Match then Team, checks a durable GameAction retry before phase checks, validates the current level, debits EconomyService once, updates the team-type row and living entities, and records the upgrade event in one transaction. Combat ticks/spawns use the same lock order.

REST returns action plus team_id, entity_type, previous_level, level, stats, cost and coins_after. `UPGRADE_REQUEST` accepts the same payload via WebSocket. Legacy `/actions/upgrade/` and entity_id socket requests resolve the tower's type and invoke the same team-wide purchase service; they cannot bypass the team level. Legacy service callers may omit keys as before; new clients always supply stable keys.

Events: existing `COINS_UPDATED` plus public `TEAM_UNIT_UPGRADED`, both committed through the existing outbox/on_commit path. Enemy coin balances remain redacted. No per-entity full-state fan-out is added. The upgrade event includes stat_version=1. All-team levels are present in snapshots, including types with no entities; units/team-state endpoints return level, authoritative current/next stats, price and max state. Snapshot query budget increases by one bounded all-team query (8→9 in the existing 20-team fixture).

Migrations: units 0009 creates TeamUnitUpgrade and action choice; 0010 preserves the highest paid legacy level per team/type, reconciles living entities and their HP proportion without another debit. Paid legacy Lv.2 towers adopt the shared Lv.2 balance (15% HP, 10% damage and 5% attack-rate bonuses), replacing their former 25%-damage-only rule; no repeat payment is charged. Deployments must run `python manage.py migrate` before starting the changed server. The regular development/deployment database was not migrated by QA; QA used the local preview and disposable databases.

## UI and equipment

The compact NÂNG CẤP dock button opens TeamUpgradeModal. It provides six type choices, current/next equipment, HP/damage/fire-rate/interval/range/speed, deployment price, upgrade price, explicit confirmation, unlock/insufficient-funds feedback and CẤP TỐI ĐA. Failed requests retain their idempotency key; a changed type/level gets a new key. Team events refresh the catalog while reconciling live entities immediately.

`frontend/scripts/generate-upgrade-art.py` layers original SVG equipment over existing art, preserving viewboxes, sprite origins and walk-frame dimensions. Run it after regenerating base art. Level 1 uses the originals; 255 added SVGs cover levels 2–4, including all 20 teams and four walk frames.

| Entity | Level 2 | Level 3 | Level 4 |
|---|---|---|---|
| Infantry | chest armor, helmet plate | shoulder armor, equipment belt, reinforced weapon | elite visor, gold armor, weapon detail |
| Tank / Artillery | side plating, reinforced tracks | heavy turret and barrel sleeve | elite plating, targeting antenna, muzzle detail |
| Towers / Shield | reinforced foundation | side armor supports | fortified corners and targeting/shield detail |

Phaser changes textures/animation keys on the existing sprite; roots, interpolation, attack effects and HP bars remain. React arsenal cards, previews and tooltips use the same artwork and server stats. No extra active projectile or weapon logic was added.

## Validation

See QA results at the end of this document. New backend tests cover all six types, existing/future entities, HP ratio, destroyed entities, unlock/auth/phase restrictions, exact payment, idempotency conflicts, level cap, continuous ticks, three authenticated sockets and PostgreSQL races. Frontend tests cover team reconciliation, artwork and scenery geometry. The browser acceptance script exercises real REST, Channels, React and Phaser; no gameplay services are replaced.

Limitations: level prices require playtesting; legacy rounds do not simulate attack-rate bonuses; future custom tower codes use existing fallback artwork until a matching asset is supplied. Existing Phaser bundle-size warning remains. Browser performance evidence is local headless Chrome, not a low-end mobile or production Redis load certification.


## Confirmed QA results — 2026-10-24

- Full backend suite: **421 passed**, 16 skipped (PostgreSQL-only tests in the SQLite run).
- PostgreSQL selected concurrency/session suite: **34 passed**, including duplicate and competing upgrades, simultaneous spawn/upgrade/tick, shared question deadlines and exclusive rewards.
- Final focused upgrade/quiz checks after adding hidden host-resume coverage: **18 passed**, 1 PostgreSQL-only skip.
- Frontend unit tests: **100 passed**. TypeScript and Vite production build passed; existing bundle-size advisory remains.
- Changed backend modules pass Ruff; Django reports no missing migrations.
- `tests/team-upgrades-quiz-map.browser.mjs`: **PASS** using real REST/Channels/React/Phaser. Three clients, six types at level 4, ten existing plus five future Infantry, opponent isolation, stable sprite root, exact retry behavior, reconnect, unlocks, +30 reward, a real 60-second hidden expiration, explicit Next and immediate Next→Close.
- `tests/upgrade-camera.browser.mjs`: **PASS**. Pan/zoom on all map sizes, loaded elite equipment preview and a 390×844 upgrade panel without horizontal overflow. Frame sampling is for scenery/camera in read-only scenes, 120 samples each, local headless Chrome at 1440×1000.

| Teams | Vegetation sprites | Mean FPS | Frame p95 |
|---|---:|---:|---:|
| 2 | 54 | 59.5 | 17.5 ms |
| 4 | 57 | 60.0 | 17.5 ms |
| 8 | 88 | 60.0 | 17.5 ms |
| 20 | 155 | 60.0 | 17.5 ms |

All four maps retain six slots per team (12/24/48/120 total). The two connected clients' scenery arrays match exactly. Equipment contact sheets and desktop/mobile captures were visually inspected.

Evidence: [browser gameplay report](qa/team-upgrades-browser.json), [camera metrics](qa/team-upgrade-camera.json), [equipment sheet](qa/team-upgrade-equipment.png), [upgrade panel](qa/team-upgrade-panel.png), [elite/mobile panel](qa/team-upgrade-mobile.png), [20-team scenery](qa/team-upgrade-camera-20.png). Full test/build logs are stored alongside these reports.

Reproduction uses the repository's existing Python virtual environment and `npm test` / `npm run build`. For PostgreSQL use `pytest --ds=config.settings.test_postgres` with a disposable test database. Browser scripts use Playwright via NODE_PATH when it is supplied by the workspace runtime, and TEST_BASE_URL to target a migrated local backend/frontend pair. They create their own QA rooms and upload the supplied test bank. The separate inspection HTML fixture renders the real upgrade component for deterministic artwork/mobile screenshots and uses read-only BattlePage scenes for camera measurement.
