# Battlefield UI and map audit

Audited 2026-10-24, before implementation.

## Confirmed current behavior

- `frontend/src/components/RewardSelectionModal.tsx` owns reward choice, single selection, async claim and server-confirmed success. Unlock cards currently use category icons, pointer-only divs and raw catalog stats. Reward options contain only eligible locked items. The coin alternative reads the server's `coin_amount` (+20).
- `frontend/src/pages/BattlePage.tsx` contains the active arsenal and deployment panel. `UnitCard.tsx` and `TowerCard.tsx` are older components, not used by this page. Vietnamese entity names and SVG path selection currently live locally in BattlePage. Actual artwork for all six catalog entities exists in `frontend/public/assets/woodland/`; Phaser loads these same SVGs in `BootScene.ts`.
- `DeploymentQuantity.tsx` already receives the page's single `quantityInput` state and supports −/+, input, 1/5/10/MAX, cost and validation. It is nested in deployment markup, but `.quantity-panel` is absolutely positioned above the dock with its own fantasy frame. Small-screen `.selection-info` is a 43–45px horizontal scrolling strip. These styles cause the visibly detached quantity panel.
- `game/actionAvailability.ts` calculates affordable/type-limited quantities and gates deployment during planning and continuous Battle. Unit selection resets quantity to 1. Invalid values prevent submission; server state supplies coins and limits.
- `game/map.ts` projects the server graph around its original center. `arenaWorld` supplies legacy 1600×1040 or dynamically scaled server arena dimensions (2–20 teams). Routes, bases, six tower slots, staging and rally positions are authoritative backend data.
- `rendering/terrain.ts` paints ground/roads/water/bridges into one capped 2048px canvas, then scatters decorations. A dedicated nested loop adds dense perimeter tree rows. A separate 150-attempt loop adds interior trees, rocks and bushes. Trees are visual images only: they have no physics/collision or server obstacle metadata. Graph barrier nodes are separate camps and must remain.
- `scenes/BattleScene.ts` uses arena dimensions for camera limits and HUD-aware overview, extends limits for troop queues, supports smooth wheel/button/pinch zoom, drag pan and resize reset. Overview/queue bounds can exceed painted terrain, exposing the camera's flat background.
- `components/arena/ArenaNavigation.tsx` currently assumes a zero-origin world in SVG bounds, pointer projection and viewport clipping. Its fixed SVG aspect ratio can also letterbox nonmatching map dimensions.
- Backend `apps/combat/map.py` and `apps/units/map.py` own graph topology, base/spawn/slot validation and pathfinding. Decorative padding must not modify these coordinates or permit purchases outside graph slots.
- Backend `apps/units/services.py` locks match/team, validates quantity/actor/phase/unlock/target/spawn/limits/coins, atomically debits and creates a batch, records idempotency and broadcasts authoritative entity updates. No deployment schema change is needed.
- Backend `apps/rewards/services.py` locks and validates claims, prevents duplicate claims and publishes team unlock updates. Its options currently expose baseline `base_stats`, whereas `apps/units/serializers.py` and `apps/combat/balance.py` supply effective HP/movement. Use that existing catalog serialization for accurate previews.
- Existing tests cover frontend stores, camera, routing, batch controls and backend rewards, XLSX imports, combat, idempotency, multiplayer, victory and 2–20-team maps. Browser fixtures instrument the real React/Phaser clients against a disposable backend.

## Implementation locations

1. Extract BattlePage's existing entity names/art mapping into one shared module; add one reusable image/fallback view for unlock and deployment artwork.
2. Update `RewardSelectionModal.tsx` for illustrated keyboard-selectable cards, eligibility reconciliation, bounded internal scrolling and accessible confirmation. Reuse effective server catalog stats in reward options.
3. Update `DeploymentQuantity.tsx`, BattlePage selection markup and `game.css` to place controls in normal flow inside the ready panel, including mobile/short viewport layouts. Retain the existing quantity state and request logic.
4. Add visual bounds and camera/minimap geometry helpers to `map.ts`; update BattleScene camera bounds and ArenaNavigation. Keep `arenaWorld`, node projection, server map and all combat geometry intact.
5. Extend terrain across negative-origin visual bounds with a reusable ground tile; remove only the perimeter tree loop. Fill camera/queue letterbox space without adding decoration objects or collisions.
6. Add focused geometry/UI/integration checks and record actual results in `BATTLEFIELD_UI_MAP_IMPLEMENTATION.md`.
