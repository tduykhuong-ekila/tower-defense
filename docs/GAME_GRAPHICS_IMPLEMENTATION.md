# Graphics implementation and verification

## Run

Use the existing README setup for Django/Channels, Redis/PostgreSQL and Vite. No database migration is added by this work.

```bash
cd frontend
npm install
npm run dev
```

Open `/join`, enter a room code, join a team, then open `/battle/{match_id}`. Start the match from the existing Host console. Units can deploy during PREPARATION, BUILD_AND_SCOUT, WAR and FINAL_ASSAULT; towers can build during PREPARATION, BUILD_AND_SCOUT and WAR, exactly matching existing server validation. Locked items are unlocked through correctly answered questions. Choosing coins normally grants exactly 20; each question has one exclusive reward. Host-configurable reward values remain a pre-existing server setting.

Combat continues through the existing host/scheduler mechanism. The Host console's next-round button now uses the common API authentication helper; it previously read an unrelated localStorage key. A server-authenticated host can also begin the next round from battlefield settings. The frontend does not introduce its own combat or phase timer authority. A countdown reaching zero waits for the host/scheduler's phase event.

`API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174` supports an alternate backend for isolated local QA. Default remains localhost:8000. Existing Docker images must be rebuilt to contain the updated source.

## Add illustrations or maps

- New unit: add an SVG named after the existing backend unit code, preload it in BootScene and adjust `BattleScene.texture()` if the animation needs a custom mapping. Add frame animations in BootScene. Keep the backend unit catalog as the source of cost/stats/unlock eligibility.
- New tower: use the same flow with a distinct SVG silhouette. It automatically uses legal slots and server construction rules. No free-coordinate placement is added.
- New map: update/extend the backend GameMap graph and export, preserving IDs and ordering. Adjust only the projection/artwork in `game/map.ts` and `rendering/terrain.ts`. Movement events remain tied to server nodes. Tiled is not required for the current generated radial graph.
- New combat event: add its typed shape, store reconciliation if it changes authoritative state, and a matching visual handler. Rendering must never calculate its damage or reward.

## Verification

Automated commands:

```bash
cd frontend
npm run lint
npm test
npm run build
cd ../backend
.venv/bin/ruff check .
.venv/bin/pytest
```

Verified results are recorded below after final execution. The frontend tests exercise real store/socket implementations, valid/invalid slots, pointer drag discrimination, 8-team projection, stale/duplicate events, movement/HP/death/shield/income reconciliation and room switching. Backend tests cover the existing economy, rewards, concurrent spending/claims, multiplayer, reconnect, combat and host permissions, with new graph/event/schema regression checks.

Browser QA uses a separate SQLite database under `/private/tmp`, an in-memory Channels layer in a single Daphne process, backend :8001 and frontend :5174. The user's original database and existing Docker services are not modified. In a real multi-process deployment retain Redis; the preview's in-memory channel layer is only for its one-process test server.

Observed browser checks:

- A real participant joined DEMO24, loaded the four-team arena and connected to WebSocket.
- Double-click deploy: one infantry, balance 60 → 45, unit count 3 → 4.
- Clicking an enemy tower slot: rejection feedback, balance unchanged.
- Clicking an own free slot on the canvas: one machine-gun tower, balance 45 → 20, tower count 1 → 2.
- Correct short answer: opened the reward flow. Double-click coin claim: balance 20 → 40 exactly once.
- REST-triggered combat appeared over WebSocket, disabled placement during playback, moved units, showed attacks/deaths, and reconciled income/remaining entities. Three consecutive rounds queued correctly; clicking Skip cleared the queue and restored action controls from the latest state.
- Phone camera initialization/resize preserves own-base focus, with centered bounds at fit zoom rather than clamping the entire map to the top.
- A real 390 × 844 iframe viewport exercised the same game and session, with condensed HUD, scrollable troop cards, camera controls and contextual details. The fixture is `frontend/tests/fixtures/viewport.html?width=390&height=844&match={id}` and is served only by the development server.

## Practical limits

This is an integrated playable graphics overhaul. Infantry has four walk frames; other animation states and vehicles use transforms, recoil, fading and effects rather than large authored directional sprite sheets. The level uses an original illustrated vector aesthetic rasterized to textures, rather than a purchased hand-painted atlas. There is no Tiled editor file or music track. Real-device pinch gestures, extended memory/FPS profiling and a full eight-client browser soak were not performed; 2/4/8-team graph contracts and four-client multiplayer are covered automatically. Large Phaser engine chunks are expected; the battlefield is loaded lazily so ordinary lobby pages do not download it first.

## Final executed checks

- `npm run lint`: passed (TypeScript noEmit).
- `npm test`: 15/15 passed.
- `npm run build`: passed. Main JavaScript 291.12 kB (82.66 kB gzip), separately loaded battlefield/Phaser approximately 1,566 kB (367 kB gzip). Vite reports the expected large-engine chunk warning.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/pytest`: 95/95 passed, including concurrent reward claims and pending-reward reconnection.
- No Git metadata is present in the supplied workspace, so no commit or branch was created.

Screenshots: [desktop](screenshots/woodland-desktop.png), [mobile viewport](screenshots/woodland-mobile.png).
