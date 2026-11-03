# Army controls, map and quiz implementation

Implemented in the existing Django/Channels and React/Phaser architecture. No replacement state manager, combat loop, pathfinding service or art system was introduced.

## Delivered behavior

- A quiz-card click restores a running question/reward or opens the next eligible question directly. Running deadlines survive closing; hidden expiration never starts another question. Earned rewards are retained across phase changes.
- New arena layout v5 protects complete base, tower and input footprints. Saved v3/v4 layouts remain unchanged.
- Friendly mobile troop selection supports click, modifier-click, explicit rectangle mode, select all, clear and Escape.
- Selected troops can receive authoritative Battle-time attack objectives. Team-wide retreat has a confirmation, preserves HP/upgrades/cooldowns and walks each troop home independently. Returned troops remain idle until explicitly commanded again.
- Existing WebSocket sequencing, outbox broadcasts, snapshots and interpolation distribute persistent orders and movement to all viewers.

## Implementation files

Backend:

- `apps/questions/services.py`, `views.py`, `state_machine.py`: atomic explicit open-session and reward-preserving progression.
- `apps/rewards/services.py`, `apps/matches/services.py`: retain earned pending rewards instead of legacy grace expiry.
- `apps/combat/build_geometry.py`, `map.py`: projected structure geometry, v5 placement and validation.
- `apps/matches/defaults.py`, `serializers.py`: new-match v5 default and saved-layout compatibility.
- `apps/units/commands.py`, `views.py`, `serializers.py`, `models.py`: tactical service and existing GameAction/REST extensions.
- `apps/units/migrations/0011_tactical_army_commands.py`: add command choices; no entity/order-table migration is needed because orders use existing simulation JSON.
- `apps/matches/urls.py`, `action_policy.py`: command route and authoritative Battle authorization.
- `apps/combat/formation.py`, `continuous.py`: reversible current-edge routing, explicit retreat/idle states, attack suppression and arrival.
- `apps/realtime/events.py`: public command event names. Existing post-commit event publication and snapshots already support the payloads.

Frontend:

- `src/components/QuestionModal.tsx`, `pages/BattlePage.tsx`, `services/api.ts`: direct quiz reopening and tactical command integration.
- `src/components/game/ArmyCommandPanel.tsx`, `game/armySelection.ts`: army HUD, focus-trapped retreat confirmation, friendly selection rules.
- `src/game/scenes/BattleScene.ts`, `bridge.ts`, `game.css`: pointer selection, explicit drag mode, stable rings/return indicator and styling.
- `src/stores/matchStore.ts`, `types/unit.ts`: command deltas and persistent order types.

Tests/fixtures:

- New `backend/tests/test_army_control_map_quiz.py`, `frontend/tests/army-control.test.ts`, `army-control.browser.mjs`, `army-map-reproduction.browser.mjs`.
- `backend/tests/browser_preview.py` accepts an optional short question duration for isolated browser tests.
- Existing layout/default/rally tests were updated to look up the match's authoritative layout version. The legacy reward-grace test now verifies entitlement retention.

## Validation (2026-10-24)

| Check | Confirmed result |
| --- | --- |
| Complete backend suite, SQLite | 446 passed; 18 PostgreSQL-only checks skipped. |
| PostgreSQL targeted/concurrency suite | 40 passed, including concurrent tactical commands/ticks, duplicate requests, simultaneous quiz opens, existing deployment/capacity/upgrade locks. |
| Frontend suite | 103 passed. |
| TypeScript and production build | Passed; existing large Phaser bundle warning remains. |
| Django system checks / migration drift | Passed; no missing migrations. |
| Ruff on changed backend implementation/new tests | Passed. |
| Three connected browser clients | Quiz, single/multi selection, selected-only retarget, mixed retreat, idle arrival, reattack, reconnect and live opponent deployment passed. Original Phaser visual instances remained stable. |
| Map browser checks | Original Red overlap reproduced in v4. Corrected 2/4/8/20-team maps have no base-marker overlap; six towers per team constructed, with marker checks at three zoom levels. |
| Geometry regression | Every supported team count 2–20 passes full geometry and serialization validation. |

Evidence is in `docs/qa/army-control-*.txt`, `army-control-browser.json`, `army-map-browser.json` and the corresponding PNGs. The browser backend uses a temporary database and in-memory Channels layer; concurrency tests use a disposable PostgreSQL test database, without migrating or flushing the running application's source database.

## Operational notes and limits

- Apply normal Django migrations before running the updated backend (`python manage.py migrate`); rebuild/restart application images when deploying these workspace changes.
- Existing live matches retain saved map coordinates and therefore do not receive the v5 overlap correction. Create a new match for the new geometry.
- Tactical commands are available in the continuous Battle mode. Legacy discrete-round matches retain their existing combat flow.
- Map/tower coverage and balance values are unchanged. The minimum small-arena scale changes visual space and physical edge lengths; existing movement normalization retains configured troop speeds and graph-based range.
- Automated browser checks use Chromium (including touch emulation), three clients for combat, and up to 20 teams for construction. A physical mobile-device/browser matrix and 20 simultaneously connected combat browsers were not run.
- Browser realtime tests use the existing in-memory channel transport. PostgreSQL row locking was tested separately; a production multiworker Redis deployment was not exercised in this change.

Detailed contracts and decisions: `TACTICAL_ARMY_COMMANDS.md`, `TWO_TEAM_BUILD_SLOT_FIX.md`, `QUIZ_PROGRESSION_UPDATE.md`, and `ARMY_CONTROL_MAP_QUIZ_AUDIT.md`.
