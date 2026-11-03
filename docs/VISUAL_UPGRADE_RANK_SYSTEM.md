# Visual upgrade ranks

Implemented on 24 October 2026. Backend levels remain integers 1–4; no migrations or combat balance changes are needed.

| Level | Vietnamese name | Insignia |
| --- | --- | --- |
| 1 | Tân binh | One ivory chevron |
| 2 | Tinh nhuệ | Two pale blue chevrons |
| 3 | Thiện chiến | Three bronze chevrons |
| 4 | Huyền thoại | Four gold chevrons, gold name |

`frontend/src/components/game/UpgradeRankBadge.tsx` renders an inline shield SVG with an accessible image name and tooltip such as `Cấp 3 — Thiện chiến`. Chevron count communicates progression independently of color. Its CSS lives beside the component. Shared points, labels, colors and zoom thresholds live in `frontend/src/game/upgradeRank.ts`.

The badge replaces numeric-only labels in the team equipment selector, current/next comparison, confirmation, arsenal, construction summary, entity inspection, UnitCard, TowerCard and selected entity action. Detailed maximum-rank views show `CẤP TỐI ĐA`; the modal additionally checks eligibility and level < 4 before buying. Server maximum-level validation is unchanged.

BattleScene generates four shared 28 × 42 textures lazily. Each entity has one small Phaser Image, retained in the Infantry pool and updated in place on level changes. Infantry displays at 14 × 21 pixels from zoom 0.9; vehicles at 18 × 27 from zoom 0.7; towers from zoom 0.55. Existing entity culling also applies. The badge sits beside the sprite, away from HP, weapons, banners and selection rings. There are no per-soldier DOM elements, flashes or glow animations. Existing level-specific equipment and walking textures remain intact.

## Verification

- Frontend unit tests cover four chevron counts, names, elite state, zoom thresholds, and existing realtime team-wide upgrade reducers.
- Browser QA renders all four ranks across all six types, checks actual SVG chevron counts and accessible names, and verifies stable panel/footer dimensions at 1440×1000, 390×844 and 844×390.
- Two authenticated clients observe the same Tank upgrade through ranks 2, 3 and 4; existing Phaser overlays update to the elite texture.
- Screenshots and machine-readable results: `docs/qa/rank-elite-modal.png`, `rank-modal-*.png`, `rank-roadside-results.json`.

The badge does not change server statistics, weapon artwork, prices or persistence. Very small zoom intentionally hides individual insignias to preserve overview readability. Visual QA uses Chrome; other browser engines have not been separately exercised.

Final validation: backend **469 passed, 19 skipped**; frontend **121 passed**; **4 PostgreSQL concurrency regressions passed**; TypeScript/production build passed; Chrome interaction report **PASS**. See `docs/qa/rank-roadside-validation.json` for commands and scope.
