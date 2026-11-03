# Battlefield UI and map implementation

Implemented and verified 2026-10-24.

## Delivered behavior

### Illustrated unlock cards

`frontend/src/components/RewardSelectionModal.tsx` now shows the real game SVGs in responsive selectable cards, with Vietnamese names, entity category, effective server stats, cost and locked/selected status. Selection uses native buttons, supports keyboard activation and exposes `aria-pressed`. Only one eligible locked entity can be confirmed. Stale cards already unlocked by a team event are disabled. The popup traps focus, scrolls internally and keeps confirmation outside the scrolling card area.

The +20 coin alternative is unchanged. Claims still use the existing async REST endpoint, server eligibility checks, team events and idempotency. Server rejection leaves the popup and selection available for retry. Success follows a confirmed server claim.

`backend/apps/rewards/services.py` reuses `UnitTypeSerializer` with the current match/team context for reward options. This replaces baseline-only stat previews with the same effective HP, movement, range and damage used by the deployment catalog. It changes no balance values or reward rules.

The old server behavior for duplicate claims is intentionally preserved: it returns the original claim with HTTP 200, including when a different reward is subsequently requested for the same question. The duplicate request cannot create another claim, change the chosen reward or pay again. The browser test verifies the original claim ID, reward type and unchanged wallet; PostgreSQL tests verify competing claims.

### Shared artwork

BattlePage's existing React artwork and Vietnamese labels were extracted into `frontend/src/game/entityArtwork.ts`; there is one shared React mapping. Phaser keeps its existing texture loader and the same source files. No new art files, sprite sheets, external URLs or Phaser instances were added.

| Entity | Existing SVG under `frontend/public/assets/woodland/` |
| --- | --- |
| Infantry / Bộ binh | `infantry-{teamIndex}-0.svg` (team index clamped to 0–19) |
| Tank / Xe tăng | `tank.svg` |
| Artillery / Pháo binh | `artillery.svg` |
| Machine gun tower / Tháp súng máy | `mg_tower.svg` |
| Cannon tower / Tháp đại bác | `cannon_tower.svg` |
| Shield generator / Tháp tạo khiên | `shield_generator.svg` |

`components/game/EntityIllustration.tsx` reserves image dimensions, decodes asynchronously and shows a local category silhouette while loading or on failure. Unknown entity codes also get that fallback without requesting a nonexistent path. Supported entities use their actual artwork. Browser and static tests cover these paths.

### Consolidated deployment panel

- `BattlePage.tsx` retains its existing single `quantityInput` state, selected-unit reset-to-1 convention, authoritative wallet and availability calculation.
- `DeploymentQuantity.tsx` remains the only quantity selector. Its separate fantasy frame and absolute positioning were removed; it now appears in normal flow inside **SẴN SÀNG TRIỂN KHAI**.
- The panel displays a selected-unit illustration, effective stats, −/numeric input/+, 1/5/10/MAX, unit price, total, available coins, target and primary deployment action.
- Existing validation blocks nonpositive/fractional/over-budget/type-limit purchases. MAX respects wallet and shared vehicle capacity. Backend batch validation, atomic debit/create, idempotency and broadcast paths are unchanged.
- `game.css` gives the ready panel a coherent grid, wraps it below the arsenal on narrow screens and makes the dock scroll internally on short screens. Numeric input and controls remain keyboard accessible. The narrow header was adjusted to avoid wrapping the round number into the phase label.

### Expanded visual world

`game/map.ts` adds `battlefieldWorld`, separate from `arenaWorld` and node projection. Per-side padding is:

- Horizontal: `round(max(320, arena.width × 0.12))`.
- Vertical: `round(max(240, arena.height × 0.14))`.

The visual origin extends into negative coordinates. Server arena dimensions, centers, node coordinates, bases, roads, bridges, rally/staging areas, six build slots and routes are unchanged. Padding contains no new placement nodes or collision bodies, so it does not authorize construction or spawning.

Actual default version-4 maps verified in the browser:

| Teams | Previous arena bounds `(x, y, width, height)` | New visual bounds `(x, y, width, height)` |
| --- | --- | --- |
| 2 | `(0, 0, 1600, 1088)` | `(-320, -240, 2240, 1568)` |
| 4 | `(0, 0, 1600, 1088)` | `(-320, -240, 2240, 1568)` |
| 8 | `(0, 0, 2320, 1501)` | `(-320, -240, 2960, 1981)` |
| 20 | `(0, 0, 5200, 3152)` | `(-624, -441, 6448, 4034)` |

Legacy payloads without arena metadata continue to use the existing 1600×1040 fallback, with the same padding formula. No migration or entity-coordinate translation is needed.

### Camera, terrain and minimap

- `BattleScene.ts` fits and pans within the new visual world, retains smooth cursor-anchored wheel/button/pinch zoom, and preserves existing long-queue navigation extensions and resize behavior.
- HUD overview letterboxing can extend beyond the visual rectangle. A reusable 256×256 grass texture fills all camera bounds, with a small bleed for Phaser's rounded `worldView`. Its texture origin stays pinned to world coordinates during pan/zoom.
- Detailed roads, bridges, pads and staging patches remain in one transparent canvas capped at 2048px on its longest side. A single Graphics object continues the decorative river through letterboxing/long queues; its path is extended only when necessary, in 256-world-pixel increments. This prevents visible river cutoffs without scaling gameplay geometry or adding hundreds of objects.
- `ArenaNavigation.tsx` uses the negative-origin SVG viewBox, matching aspect ratio and corrected click projection. Its viewport rectangle clips the actual intersection with the padded world. Team markers and attack routes keep their original projected positions. Keyboard pan and focus controls remain available.

### Perimeter tree removal

The dedicated dense perimeter-tree loop in `rendering/terrain.ts` was deleted. The separate sparse interior decoration loop and graph barrier camps/crates remain. The removed trees were visual images only; there were no collision bodies or server obstacle records to remove. No dense replacement border was added. Ground and river fill the open area using two reusable rendering objects.

## Validation results

- `npm run build`: **passed** (TypeScript and Vite production build).
- `npm test`: **93 passed**, including six new artwork, immutable projection, negative bounds, overview and minimap tests.
- Existing full Django suite: **402 passed, 14 skipped** in SQLite. These 14 tests require PostgreSQL row locks.
- New `test_battlefield_reward_preview.py`: **1 passed** in SQLite; effective catalog stats, +20 option and locked eligibility verified.
- PostgreSQL run of `test_round_concurrency.py`, `test_question_bank_concurrency.py`, and the new preview test: **15 passed**. This includes the 14 tests skipped by SQLite, covering duplicate reward races, shared wallets, batch retries, capacity/overspend races, live ticks and 20-team simultaneous deployments.
- Ruff on both changed backend files: **passed**.
- `tests/battlefield-ui-map.browser.mjs`: **passed** against disposable Django/Vite servers, with real React controls, Phaser rendering and WebSocket clients. No uncaught browser errors.

Browser acceptance checks cover:

1. Server rejection/error and safe retry; Tank, Artillery and both nonstarter tower illustrations; keyboard single selection; fixed mobile confirmation footer; confirmed unlock; teammate update; duplicate claim prevention; unchanged +20 alternative.
2. Exactly one contained quantity selector; 5 Infantry and 2 Tank batches; live total; presets/MAX; unit reset; invalid fractional input; opponent sees purchases without reload.
3. Battle deployment and an open reward popup while existing troops move and WebSocket ticks continue.
4. Four-edge camera bounds, painted terrain coverage, minimap click coordinates, cursor zoom, drag and mobile resize for **2, 4, 8 and 20 teams**.
5. No perimeter trees; interior trees remain. Failed-image fallback remains usable.
6. 320×568, 390×844, 844×390 landscape, 1024×600 and 1440×1000 layouts, including primary-action reachability and horizontal-overflow checks.

The existing backend/frontend suites also cover current Infantry 80 HP/speed 7, Artillery 80 HP/speed 5/range 1.5, Cannon Tower range 2, six slots, independent movement/combat, live construction, XLSX question-bank upload, continuous questions, recovery/synchronization, victory and finalization.

Logs and screenshots are in `docs/qa/battlefield-*`. `battlefield-ui-map-browser.json` contains the browser assertions and measured world bounds. Desktop/mobile unlock, deployment, landscape and every tested map size have saved screenshots; these were opened and visually inspected.

## Remaining limitations

- The existing Vite warning for the large Phaser bundle remains; no new dependency was introduced.
- On short/landscape screens the consolidated dock scrolls internally so both the arsenal and all deployment controls remain reachable.
- Full 20-team overview intentionally renders small entities on narrow phones; existing base/target/combat focus and zoom provide close inspection.
- Browser verification used Chrome and a disposable SQLite backend. Row-lock races were checked separately against PostgreSQL; Safari/Firefox were not exercised.
