# Upgrade modal selection fix

## Root cause

The Phaser callback already passed the correct entity instance ID. BattlePage correctly resolved that ID to the live render entity and displayed its command panel. The failure occurred after that: the entity's upgrade button only called `setUpgradeOpen(true)`. TeamUpgradeModal then initialized private selection with `units.find(u => u.upgrade?.eligible)?.code`, discarding the clicked entity's type. Reopening therefore always selected the first eligible catalog item. This was not an instance-ID/API mismatch or WebSocket ownership bug.

## Canonical mapping and controller

`frontend/src/game/upgradeSelection.ts` resolves the authoritative catalog code from either Phaser `unit_code`, REST `unit_type_code`, or an explicit catalog `unit_type_id`. It verifies the current team and catalog eligibility and returns null for enemies/unknown/ineligible types. Towers retain their individual codes: `cannon_tower`, `mg_tower` and `shield_generator`.

BattlePage now stores one nullable `UpgradeSelection` object containing `entityType` and optional `sourceEntityId`. Setting this object both opens the modal and chooses the type in one React update. Generic opening selects the first eligible catalog type. Closing clears the object.

TeamUpgradeModal takes controlled `selectedType` and `onSelectType` props. It has no private type initialization or effect tied to catalog/entity updates. Requested selection persists while metadata is absent; the panel shows a loading message instead of another type. Realtime snapshots and REST catalog refreshes can update statistics without changing the selection. The existing modal uses a flat navigation list rather than separate Troops/Towers navigation; its exact selected catalog record supplies both category and type. Buttons expose `aria-pressed`, `data-upgrade-type` and `data-category` for inspection.

The source instance ID is context only. The purchase still sends `entity_type: unit.code`, `expected_current_level`, and an idempotency key to the existing team-authorized endpoint. Server locks, unlock checks, coin debit, fan-out and level-4 limits remain intact. The selected-entity upgrade action is absent for enemies and unsupported types, and disabled at maximum rank. Global purchase availability still enforces spectator/team/match restrictions.

The fixed-height equipment panel and fixed footer remain in use; the article scrolls independently.

## Verified tests

- Canonical resolution for Infantry, Tank, Artillery, Cannon Tower, Machine Gun Tower and Shield Generator, including REST and render field names, type IDs, missing metadata, unknown/ineligible types, enemies and spectators.
- Actual canvas clicks followed by the upgrade action select the exact type/category immediately for all six types; reopening another entity changes selection.
- Recovery snapshots and their asynchronous REST refreshes retain the selection.
- A controlled delayed-metadata browser fixture shows loading, then the requested Cannon Tower without an Infantry flash.
- Two clients observe upgrades to all matching friendly Tanks through rank 4. Enemy inspection offers no upgrade action.
- Desktop/mobile/landscape modal dimensions and confirmation footer remain stable across all types and ranks.
- Existing team-upgrade backend coverage includes future spawns, HP proportions, opponent isolation, maximum level, costs, idempotency and authenticated WebSocket fan-out. PostgreSQL concurrent purchase tests pass.

Reproduce browser QA with `backend/tests/rank_roadside_preview.py`, a frontend dev server pointing at port 8018, and `frontend/tests/rank-roadside.browser.mjs`. The fixture uses a temporary SQLite database and never writes the normal game database. Results are saved in `docs/qa/rank-roadside-results.json`.

Final validation: backend **469 passed, 19 skipped**; frontend **121 passed**; **4 PostgreSQL concurrency regressions passed**; TypeScript/production build passed; Chrome interaction report **PASS**. See `docs/qa/rank-roadside-validation.json` for commands and scope.
