# Three-star team upgrades

The playable upgrade range is Level 1, Level 2 and Level 3. An unlocked type starts at Level 1, and one team purchase promotes every surviving entity of that type plus future deployments and tower construction. Level 3 is maximum. Match placement, combat routes, question rewards and coin economy outside upgrade purchases are unchanged.

## Balance and authority

`backend/apps/units/upgrades.py` owns `DEFAULT_UPGRADE_LEVEL = 1` and `MAX_UPGRADE_LEVEL = 3`. The existing first three modifiers remain unchanged:

| Level | HP | Damage | Attack-rate multiplier |
| --- | ---: | ---: | ---: |
| 1 | 1.00 | 1.00 | 1.00 |
| 2 | 1.15 | 1.10 | 1.05 |
| 3 | 1.30 | 1.20 | 1.10 |

Only the first two upgrade costs remain: Infantry 50/100, Tank 80/160, Artillery 90/180, and each Tower type 70/140 coins. Saved per-match cost overrides can still define values, but the service indexes only the first two levels. The server verifies team membership, unlock, expected current level, wallet, and idempotency key under match and team row locks. It commits the team record, proportional HP change, action, transaction, and event atomically. It rejects any purchase at Level 3. Catalog serializers report `max_level: 3` and no `next_stats` or cost at maximum. API request validation accepts only current levels 1–3. Database constraints enforce levels 1–3 on team upgrade records and game entities.

The Game Entity admin shows the level read-only; team-wide purchases remain the supported way to change it.

The Level 1–3 modifiers were not rebalanced. Infantry remains speed 7 and base HP 80; Artillery remains speed 5 and base HP 80; Cannon remains base damage 20. Existing range snapshots are preserved. Level 3 Cannon damage is 24, using the existing 1.20 multiplier.

## Shared presentation

`frontend/src/components/game/UnitLevelStars.tsx` renders filled Lucide SVG stars, with one, two or three stars and an accessible label such as `Cấp 2 trên 3`. `frontend/src/game/upgradeLevel.ts` shares level normalization and five-point star geometry with Phaser. Size variants are tiny, compact, normal and large. The star area has stable height, warm gold, and no badge, shield, chevron, pill, or emoji.

Updated surfaces:

- Army and Fortification picker cards keep artwork, a reserved star row, name, and price in their existing fixed layout.
- The team upgrade modal uses stars in type tabs, current and next comparison, equipment previews, and confirmation. At Level 3 it shows `CẤP TỐI ĐA`, no next preview, and no purchase action. Its fixed panel and footer heights remain intact. Battlefield entity selection still opens its exact team upgrade type.
- Rich hover/inspection cards use the hovered entity's team upgrade level and current server-provided stats.
- Battlefield entity status, construction preview, scout tower details, older unit and tower cards, and upgrade buttons use the same star component.
- Phaser uses one cached 36×12 texture per level inside the existing entity container. Upgrades change that texture and the equipment sprite in place. There is no DOM node per entity, and low camera zoom hides sidecars according to the existing visibility thresholds. Stars sit to the side of sprites, HP bars, and selection rings.

Level 1–3 equipment textures are still loaded and selected for Infantry, Tank, Artillery, and Towers. The Level 4 texture/animation loading path is removed. Match result rank numbers remain because they describe tournament placement, not equipment upgrades.

## Realtime behavior

`TEAM_UNIT_UPGRADED` updates team-wide levels, matching surviving entities and client stars without creating a new sprite. The team's future entities get the authoritative level at spawn. Opponent levels remain independent. Reconnection snapshots include authoritative `team_upgrades` and entity levels. The previous idempotent purchase behavior remains in place.

## Verification

Final checks on 2026-10-24:

- SQLite backend suite: **530 passed, 23 skipped**. The skipped cases include PostgreSQL-specific locks and environment-dependent integration tests.
- PostgreSQL upgrade, migration, and unlimited tower suite: **46 passed** on a disposable PostgreSQL 17 cluster. Pytest left its disposable test database connected during teardown; that database was removed and the cluster stopped after the run.
- Frontend unit suite: **125 passed**. TypeScript production build and Ruff checks passed. Vite still reports its existing large bundle advisory.
- Real Chrome acceptance: [`qa/roadside-stars-browser.json`](qa/roadside-stars-browser.json) passed the 1–3 star card matrix at five viewport sizes and two page scales, 2/4/8/20 team roadside construction, Level 3 Cannon synchronization, opponent isolation, future build, reconnect, movement, retarget and retreat.
- Focused Chrome check: [`qa/three-star-global-browser.json`](qa/three-star-global-browser.json) passed all six entity-to-upgrade selections, hover stars, Level 3 disabled state, unchanged Phaser entity container across Tank upgrades, and fixed modal bounds at desktop, portrait and short landscape sizes.
- Dense Chrome check: [`qa/roadside-stars-load.json`](qa/roadside-stars-load.json) passed 25 and 50 towers per team with two clients, moving troops, and eight live Army/Fortification layouts. Local samples were 60 RAF frames/second with 17 ms maximum observed frame interval at both sizes; they are environment-specific measurements.

The browser checks use disposable local rooms and one ASGI process; they do not certify a production multi-worker Redis deployment. The older coordinate-click `rank-roadside.browser.mjs` fixture timed out selecting an overlapping Infantry; the new focused check exercised the scene selection callback and verified category resolution, while this revision left the entity hitbox unchanged. A machine-readable summary is in [`qa/three-star-validation.json`](qa/three-star-validation.json).
