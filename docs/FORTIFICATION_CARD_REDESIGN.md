# CÔNG SỰ card redesign

## Confirmed cause and implementation

`BattlePage.tsx` renders the picker in `.arsenal-card`. Previously its image, title, 27px inline rank, stats and cost competed inside a short, bottom-aligned flex column. The no-wrap title grew vertically and horizontally when rank insignia were added, especially at the smaller responsive heights. The complete audit is in `UNLIMITED_TOWERS_FORTIFICATION_AUDIT.md`.

Tower cards now use `FortificationCardContent.tsx` and a `.fortification-card` modifier. Three explicit grid rows reserve artwork, a two-line title and a 16px cost area. The artwork wrapper is relative; the compact rank sits absolutely at its top-right. It consumes no row/column space, cannot shrink the image, and has `pointer-events: none`. No clipping mask hides the old layout problem.

Actual tower assets are individual 128×128 SVGs, including equipment variants for all four levels. Images use their complete viewBox with `object-fit: contain`, 2px padding and centered alignment. No sprite-sheet crop or cover scaling is applied. Natural transparent padding is retained.

Full combat stats and full rank names remain in the existing rich inspection view and upgrade modal. The compact card hierarchy is artwork, name, price, rank and availability/selection. The purchase handler, hover/focus inspection and server availability checks remain on the existing button. Selection uses `aria-pressed`, a border/inset outline and a small bottom-right check. The outline does not change box dimensions. Locked artwork is desaturated but recognizable; locked cards have a dashed border. Unaffordable/pending cards retain the same layout with their existing disabled reason. The accessible button name includes name, price/unlock status and the full Vietnamese rank label.

## Rank component API

`UpgradeRankBadge` accepts `size="standard" | "compact"` and `variant="inline" | "overlay"`. Defaults preserve existing detail/modal uses. Compact SVGs are 16×24px; rank names are suppressed even if `showName` is supplied. The existing shield and one/two/three/four chevrons remain, with gold at level four. Every badge retains its accessible label and title:

- Cấp 1 — Tân binh
- Cấp 2 — Tinh nhuệ
- Cấp 3 — Thiện chiến
- Cấp 4 — Huyền thoại

## Responsive behavior

Desktop/tablet cards have 56px artwork, 28px title and 16px cost tracks inside a 114px card. Portrait phone cards use 48px artwork and 106px height. The fortification arsenal becomes a three-column grid below 600px so complete tower names/cards fit alongside the command controls. At widths up to 360px it uses two columns and a taller dock to retain touch targets and complete artwork. Short landscape cards reserve 35px artwork and stay 91px tall. These rules are scoped to defensive cards; the troop picker retains its existing behavior.

`fortification-cards.html` renders the actual shared content at every rank and availability state. Browser assertions compare image/card/title/cost geometry across ranks and states, decode every image, check full title bounds, verify compact chevron count and semantic labels, and confirm overlay positioning/pointer behavior. Viewports: 1440×1000, 1024×768, 390×844, 320×844 and 844×390. Real game screenshots also check complete cards at desktop and phone sizes. Screenshots were visually reviewed.

Evidence is in `docs/qa/fortification-*.png`, `fortification-live-*.png` and `unlimited-browser-results.json`. No Safari or real touch-device engine was tested in this change. Existing grid touch tests remain in the regression suite.

## Browser performance and multiplayer checks

The real Phaser/React browser script constructs the seventh/eighth tower by map click, observes the same entities in a separate opponent context, purchases team MG upgrades through levels 2–4, verifies the overlay refresh, builds a new level-four tower and reconnects the opponent. It also constructs eight grid towers in a saved layout-5 arena and verifies opponent synchronization without fixed-slot controls. It then constructs 10, 25 and 50 paid towers **per team**, without duplicate sprites, and records existing Phaser metrics, requestAnimationFrame cadence and JS heap.

The Chrome headless measurements were about 60 FPS for 20/50/100 total towers. Texture allocation remained 101.7MB; JS heap measured 134.1/142.9/146.5MB at the three quantities (raw values in the JSON report). A separate synthetic replay requests 500 attack effects/second; existing pools limit concurrent rendered projectiles to 16 and damage labels to 24, without limiting gameplay entities or damage resolution. This effect replay does not simulate a networked battle and is explicitly marked synthetic. Backend combat timings and coverage limits are in `UNLIMITED_TOWER_CONSTRUCTION.md`.

## Reproduce

Use the dedicated disposable QA settings shipped with this change. They inherit the in-memory channel layer, disable scheduling and point SQLite at a dedicated temporary directory. They do not access a normal match database. Commands from the repository root:

```sh
cd backend
DJANGO_SETTINGS_MODULE=config.settings.unlimited_qa .venv/bin/python manage.py migrate --noinput
PYTHONPATH=. DJANGO_SETTINGS_MODULE=config.settings.unlimited_qa .venv/bin/python tests/seed_unlimited_browser.py
DJANGO_SETTINGS_MODULE=config.settings.unlimited_qa .venv/bin/daphne -b 127.0.0.1 -p 8199 config.asgi:application
```

In another terminal from the root:

```sh
API_PROXY_TARGET=http://127.0.0.1:8199 npm --prefix frontend run dev -- --host 127.0.0.1 --port 5199
```

With Chrome and Playwright available:

```sh
node frontend/tests/unlimited-fortification.browser.mjs
```

Set `NODE_PATH` to the installed Playwright node_modules directory if needed. The seed file stores disposable participant credentials only in `/private/tmp/unlimited-browser-rooms.json` with mode 0600; no credentials go into committed QA reports. Seed fresh rooms before repeating the browser script, because the script performs real paid builds and upgrades. The test writes screenshots and its structured report into `docs/qa/`. The standalone gallery is also available at `/tests/fixtures/fortification-cards.html` on the dev server.
