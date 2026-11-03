# Grid placement implementation and verification

## Delivered behavior

- Cannon base damage is 20 in canonical seeds, the older seed command and simulation catalog. Migration `units.0012_cannon_damage` updates existing catalog rows and their damage description without altering range, HP, rate, cost, unlocks or deployed HP. Lv.1–4 damage is 20/22/24/27, calculated once with existing modifiers. Catalog cards, rich inspection, upgrade previews and entity snapshots use server stats.
- New rooms use grid placement version 1 and arena layout 7. Layout 7 preserves existing layouts; three-team maps expand and rebalance the green branch and river corridor. The generator creates no fixed tower nodes. Slot UI/foundations/markers disappear.
- Server-owned square masks, 4×4 footprints, territory/road/water/base/rally exclusions, physical positions, match-wide row locks, idempotent debit and after-commit events provide authoritative construction. Mobile placement requires a second tap; camera gestures remain available.
- Team upgrades keep their existing purchase path and apply to current and future towers. Grid tower range uses physical positions and the existing 80-map-unit reference hop. Ghost/inspection ellipses match combat. Legacy towers keep graph coverage and existing positions.
- The upgrade dialog has a stable viewport-constrained outer height, fixed header/navigation/footer, reserved image space and a scrolling article. Purchases, confirmation, lock state and selected category remain in the persistent component.

## Compatibility and migration

Run `python manage.py migrate` when deploying. No schema or entity-coordinate migration is required. Existing stored rooms default to placement version 0 and retain layouts 3–5 and slot APIs; saved layout 6 rooms keep their prior geometry. New-room defaults opt into layout 7/version 1. The configuration serializer rejects incompatible placement/layout pairs. Do not manually flip a running saved room to a different layout.

A `world_position` and `grid_placement` travel in the existing simulation_state JSON field. The public whitelist and TOWER_BUILT reducer preserve both across REST responses, WebSocket broadcasts, combat updates and reconnects. Active/disabled/queued structures reserve their full footprint; destroyed structures release it. Legacy physical rectangles are also recognized by the occupancy validator without teleportation.

## Source changes

Backend:

- `apps/units/placement.py`: cached mask generation, square geometry, ownership and occupancy validation, map metadata.
- `apps/units/{map,services,serializers,views,seeds}.py`: version-aware legacy API, canonical row/col requests, authoritative atomic purchase, empty fixed slots for grid matches, damage defaults.
- `apps/units/migrations/0012_cannon_damage.py`: existing catalog rebalance.
- `apps/matches/{defaults,serializers}.py`: new-room placement/layout defaults and compatible configuration validation.
- `apps/combat/{map,balance,formation,continuous,continuous_service,services,targeting,views}.py`: slot-free new layout, physical tower targeting and range, public placement state, authoritative map delivery. Existing public_entity already serializes whitelisted state; it needed no separate entity table.
- `apps/realtime/{services,consumers}.py`: shared map metadata and grid build requests.
- `apps/combat/benchmark.py`: legacy fixture configuration explicitly preserved for reproducible saved-slot scenarios.
- `apps/combat/management/commands/simulate_match.py`, `apps/questions/management/commands/seed_phase_2.py`: Cannon damage metadata.

Frontend:

- `game/placement.ts`, `game/map.ts`, `types/unit.ts`: decoded mask cache, square snapping, footprint collision, placement state types.
- `game/scenes/BattleScene.ts`: reusable ghost/grid/range/label, mouse/touch confirmation, modal/build interaction priority, pan/zoom and cancellation.
- `game/{bridge,actionAvailability}.ts`, `services/api.ts`, `stores/matchStore.ts`: canonical coordinates, grid-aware availability, realtime position/occupancy.
- `game/rendering/terrain.ts`: suppress obsolete fixed foundations in new maps.
- `pages/BattlePage.tsx`: grid build controls/instructions, hidden inspection during construction, authoritative damage on tower cards, phase/team availability.
- `components/game/{TeamUpgradeModal,TowerCard}.tsx`, `game/game.css`: stable dialog regions, responsive dimensions, current damage display.

Tests:

- `backend/tests/test_grid_placement.py`: mask geometry and six disjoint footprints for every team in 2/4/8/20 arenas; all damage levels; migration; REST authorization/unlock/economy/capacity; strict coordinates; exclusion zones; upgrades; destruction/rebuild; physical combat; idempotency; broadcasts, Battle and reconnect; PostgreSQL simultaneous overlap.
- `frontend/tests/grid-placement.test.ts` and public `fixtures/grid-maps.json`: actual server-mask parity, negative origins, footprints, occupancy and event deduplication.
- `frontend/tests/grid-placement.browser.mjs`, `fixtures/grid-placement.html`, `backend/tests/seed_grid_browser.py`: reproducible isolated React/Phaser desktop and mobile checks.
- Existing slot-based test fixtures explicitly choose legacy layout/placement. Historical Cannon assertions now expect 20. Their other assertions remain intact.

## Executed verification

Final logs are copied into `docs/qa/grid-*.txt`; browser measurements are in `docs/qa/grid-browser-results.json`.

- Backend complete suite: **463 passed, 19 skipped** (SQLite, 145.63 seconds). The skipped cases require PostgreSQL row locks; the new overlap case is executed in the PostgreSQL run.
- PostgreSQL grid integration suite: **18 passed** (3.94 seconds), including real row locks, two racing requests, one entity and one debit.
- Final physical-range/cache correction: **56 passed, 1 PostgreSQL-only skip** across grid, continuous combat, Infantry and troop movement tests (12.61 seconds). Troops with different physical offsets cannot share a cached grid-tower target outside their range.
- Frontend suite: 109 passing tests.
- Production TypeScript/Vite build: passed; Vite reports the existing large Phaser bundle warning.
- Ruff on changed backend production modules and new grid tests: passed.
- `manage.py makemigrations --check --dry-run`: no missing migrations.
- Chrome browser: 2-team real construction and opponent synchronization; 4/8/20-team previews; snapping after pan/zoom; blocked occupancy; Escape/right-click; two-tap mobile placement and real pinch without purchasing; loaded SVG and confirmation stability for all categories/levels; no browser errors. An additional real team purchase verifies existing tower damage 22 and an already selected Lv.2 build ghost.
- Modal outer heights: 720px at 1440×1000 and 390×844; 354px at 844×390. Header, panel top and footer positions remain unchanged. Mobile/landscape content scrolls internally.
- Scene object counts: 326/312/397 for 4/8/20 teams in browser preview, independent of grid cell count.

## Reproduce browser checks

Use the isolated preview settings, migrate that preview database, then seed test rooms (credentials are written only to a private temporary file):

```sh
cd backend
DJANGO_SETTINGS_MODULE=config.settings.preview .venv/bin/python manage.py migrate
PYTHONPATH=. DJANGO_SETTINGS_MODULE=config.settings.preview .venv/bin/python tests/seed_grid_browser.py
DJANGO_SETTINGS_MODULE=config.settings.preview .venv/bin/daphne -b 127.0.0.1 -p 8197 config.asgi:application
```

In another terminal run Vite with `API_PROXY_TARGET=http://127.0.0.1:8197 npm --prefix frontend run dev -- --port 5197`, then `TEST_BASE_URL=http://127.0.0.1:5197 node frontend/tests/grid-placement.browser.mjs`. The script requires Playwright and Chrome; set NODE_PATH to a bundled Playwright package directory if it is not locally installed. Normal gameplay requires neither the test fixture nor Playwright.

## Limits and deliberate policies

- Masks cover the existing deterministic procedural terrain; future movable obstacles or additional tower artwork require explicit geometry/footprints. Unknown tower codes fail closed.
- Construction is serialized per match. This provides correctness with the current six-per-team cap; large construction throughput beyond the tested two-request race has not been load-tested.
- Desktop/mobile layout and placement were exercised in Chrome. Safari, iOS browser engines and real multi-device latency were not tested here.
- Broad backend regressions cover quiz, XLSX import, rewards, retreat, upgrades, victory and elimination. Browser tests in this change focus on placement and modal behavior; they do not rerun every historical quiz/import browser script.
- The grid has no permanent sprites and appears only during build mode. Existing minimap navigation, base markers and scenery remain; the minimap did not previously show individual towers.
