# Army and Fortification card layout fix

> The layout measurements remain valid, but the game now displays at most three stars. See [THREE_STAR_UPGRADE_SYSTEM.md](THREE_STAR_UPGRADE_SYSTEM.md).

Implemented 24 October 2026. Supersedes the rank overlay layout in `FORTIFICATION_CARD_REDESIGN.md`.

## Root cause

Army cards used a constrained vertical flex layout with artwork, a no-wrap name plus a 27 px rank SVG, optional statistics and a cost row. The inline badge increased the name's dimensions and squeezed the image. Fortification cards used a separate three-row grid with a shield overlay inside their artwork region. Legacy responsive selectors adjusted all images at several breakpoints. These two hierarchies could not maintain the same alignment when levels, names, stats or selection borders changed.

## Shared hierarchy

Both pickers in BattlePage now render `GameItemCardContent` inside `.arsenal-card.game-item-card`:

1. `game-item-card__artwork`: current game SVG and team/level variant; fixed region, `object-fit: contain`, no flex shrinking.
2. `game-item-card__stars`: fixed-height centered `UnitLevelStars` row.
3. `game-item-card__name`: fixed-height centered name, allowing two lines.
4. `card-cost`: centered coin icon/price or lock status.

`FortificationCardContent` delegates to the same component so there is no separate tower implementation. The old shield overlay, inline name badge, item number and variable stats rows are removed from these compact pickers. Full unit stats remain in existing rich hover/inspection cards and deployment controls. Actual game illustrations and level equipment are retained.

## Layout and states

| Context | Artwork region | Stars | Name | Price | Card height |
| --- | ---: | ---: | ---: | ---: | ---: |
| Desktop | 66 px | 16 px | 28 px | 16 px | 142 px |
| Narrow portrait | 64 px | 16 px | 28 px | 16 px | 140 px |
| Short landscape | 51 px | 16 px | 28 px | 16 px | 127 px |

The grid also includes 2 px gaps, padding and a constant 1 px border. Selection uses an inset highlight so border changes cannot shift rows. Locked cards keep visible artwork and stars, use a dashed border and put the lock status in the price region. Existing availability rules still disable locked, unaffordable, pending, eliminated or otherwise unauthorized actions; stars never represent affordability.

On narrow screens the category buttons sit above the full-width three-column arsenal, and counts/navigation form a compact horizontal row below the selection information. This preserves readable names and four stars even at 320 px width and 125% page scaling. It avoids squeezing cards beside a vertical category column. Deployment controls retain their scroll limits. Short landscape army commands have a bounded scroll region above the command dock, keeping category buttons clickable.

The compact THUNG LŨNG LÁ XANH header, entity-click upgrade selection, team equipment modal/footer height, rich hover cards, quantity controls and action authorization remain intact. CSS changes target the command dock and picker regions; the upgrade modal's internal layout is unchanged.

## Visual and interaction QA

`roadside-stars.browser.mjs` measures both categories at:

- 1440×1000
- 1024×768
- 390×844
- 320×844
- 844×390

Each runs at 100% and 125% CSS page zoom, levels 1–4, and available, selected, locked, unaffordable, building and deploying states: **480 rendered category/state/level/viewport/scaling combinations**, three cards each. Assertions check identical row geometry, loaded real artwork, contain sizing, full card bounds, centered star counts, no old badge, no name/star overflow and stable selection dimensions. State fixtures exercise the production content and CSS; actual building/deploying permissions are checked in the live game and backend tests.

Actual game checks additionally inspect both categories at desktop, narrow portrait and short landscape sizes during a live match with 50 towers per team. They use ordinary pointer clicks, so an overlapping overlay cannot pass by forcing input. The first QA pass found name overflow at narrow 125% scaling; the full-width mobile arsenal fixes it. Live landscape testing found the army command panel covering category buttons; its bounded scroll region fixes that overlap.

Screenshots were visually inspected as well as measured. See `qa/stars-fortification-*.png`, `qa/stars-army-*.png`, `qa/stars-live-{army,towers}-*.png`, `qa/roadside-stars-browser.json`, `qa/roadside-stars-load.json`, and `qa/roadside-stars-validation.json`.

## Reproduce

1. From `backend/`, run `.venv/bin/python tests/roadside_stars_preview.py`. This creates a temporary migrated database, four isolated rooms and private temporary authentication fixtures; it does not use the normal game database. Stop the process after QA to remove that database.
2. From `frontend/`, run `API_PROXY_TARGET=http://127.0.0.1:8018 npm run dev -- --host 127.0.0.1 --port 5198 --strictPort`.
3. With Playwright available to Node, run `node tests/roadside-stars.browser.mjs`, then `node tests/roadside-stars-load.browser.mjs` against those fresh fixtures. `TEST_BASE_URL` can override the frontend address. Use a fresh preview for another complete run so upgrade/build idempotency and load quantities have a clean baseline.
4. Run `npm test`, `npm run build` and backend `.venv/bin/pytest -q`. PostgreSQL lock tests use `config.settings.test_postgres` with a disposable `DATABASE_URL`.

Known limits: Chrome is the measured engine, page scaling uses CSS zoom, and performance figures are local samples. Browser multiplayer uses one ASGI process/in-memory channels; production Redis fanout and a multi-worker deployment require environment-specific load testing. The existing Phaser bundle still produces Vite's large-chunk advisory; the build succeeds.

Final verification: **529 backend tests passed** (23 PostgreSQL-specific skips in the SQLite run), **128 frontend tests passed**, **6 PostgreSQL concurrency tests passed**, and frontend production build/Python lint passed. Chrome acceptance and live load reports both passed. At 50 towers per team the local two-client sample had 100 towers, 104 surviving troops, 60 RAF FPS and 11 received sequence updates over 2.2 seconds. These figures are observations, not capacity limits.
