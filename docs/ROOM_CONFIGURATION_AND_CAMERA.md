# Room configuration, team membership and smooth camera

Implemented 2026-10-17 following the supplied prompt. The existing React/Phaser rendering,
Django services, team economy and authoritative combat were extended in place.

## Audit and compatibility decisions

- The existing default was 4 competing teams, capacity 8 and 2 players per team.
  These were configurable JSON fields, not database membership constraints.
- The mentor constraint only limits a team to one mentor; no mentor/mentee pair is required.
- New rooms now use a fixed default start rule of 2 competing teams, maximum 4 teams and
  minimum 1 player per team. Hosts select maximum capacity from 2 through 20.
- Existing rooms retain their saved `min_teams` and `max_teams`. The old API minimum-team
  field remains accepted for compatibility, but is absent from the creation UI and its
  TypeScript request contract. Legacy rooms requiring four teams still require four.
- A saved `min_players_per_team: 2` no longer prevents solo participation. Validation,
  REST detail and WebSocket snapshots expose the effective minimum of 1. At start/save,
  the existing compatibility field is normalized. No migration or mass database edit is needed.
- A valid player is a mentor or mentee whose membership belongs to the same match/team.
  Hosts, spectators and inconsistent foreign-match membership do not satisfy this minimum.
  Network presence is not a new start requirement: reconnect behavior remains unchanged.
- Existing ready flags, host permissions, maximum team-member capacity, unique mentor,
  shared coins/unlocks and the once-per-question +20 reward are preserved.

## Room and lobby implementation

`GET /api/v1/matches/constraints/` supplies `min_teams_to_start`, `max_teams`,
`default_max_teams` and `min_members_per_team` from backend constants. One reusable
`MaximumTeamsSelect` generates both creation and lobby-edit options from these values.
It is disabled while constraints load; creation is blocked if they cannot be loaded.

The existing payload shape remains:

```json
{"name":"Battle Arena","configuration":{"max_teams":20}}
```

The lobby shows `Teams: joined / maximum`, total playing members, readiness and a full-room
message. New-team creation is disabled at capacity; joining existing teams remains available
within their capacity rules. The edit form cannot select capacity below existing teams or
its saved start minimum. Polling no longer overwrites an open configuration form.

## Camera implementation

`SmoothCameraController` owns one `targetZoom`. Wheel, zoom buttons and pinch update that
target; focus, minimap and fit actions additionally set a target world center. The scene calls
`update(delta)` each frame with exponential damping:

```text
alpha = 1 - exp(-18 * deltaMilliseconds / 1000)
```

This closes approximately 95% of the gap in 167 ms and 99% in 256 ms. It does not create
camera tweens or update React on each frame. Repeated input accumulates against the target.

Configuration is in `frontend/src/game/camera/SmoothCameraController.ts`:

- Button step: multiplicative `exp(±0.12)`.
- Wheel sensitivity: `0.0012`, with per-event delta capped at ±240.
- Minimum zoom: the existing fit-to-arena zoom, derived from viewport/world dimensions.
- Maximum zoom: the existing `max(1.5, fitZoom * 2.7)`.

Each interpolated wheel/pinch frame compensates scroll around its screen anchor using
Phaser's unscaled viewport and origin convention. Buttons anchor at viewport center.
Fit/focus interpolate zoom and center together. Bounds blend from HUD-aware overview
margins into normal arena bounds; letterboxing handles worlds smaller than the viewport.
Dragging cancels automatic focus while pending zoom can finish. Initial layout/resizes may
fit immediately; normal user actions always animate. Scene shutdown removes the registered
pointer, wheel, keyboard and resize handlers and clears controller targets.

Browser testing also exposed existing offset hitboxes on tower/base containers. Their
custom hit rectangles now account for Phaser's container display origin, aligning selection
with the artwork at every zoom. Server map/entity coordinates are untouched.

## Files changed

Backend:

- `backend/apps/matches/defaults.py`: authoritative constraints/defaults.
- `backend/apps/matches/serializers.py`: capacity validation and effective membership minimum.
- `backend/apps/matches/services.py`: active-player start validation and capacity defaults.
- `backend/apps/matches/views.py`, `urls.py`: public constraints endpoint.
- `backend/apps/realtime/services.py`: effective minimum in legacy-room snapshots.
- `backend/tests/test_room_configuration.py`: 22 new backend cases.
- `backend/tests/browser_preview.py`: disposable SQLite browser-test server.

Frontend:

- `frontend/src/components/MaximumTeamsSelect.tsx`: shared select and constraint loading.
- `frontend/src/types/match.ts`, `services/api.ts`: constraints and creation request contract.
- `frontend/src/pages/LandingPage.tsx`, `LobbyPage.tsx`, `JoinMatchPage.tsx`: forms,
  membership indicators, start checks, optional mentor messaging and capacity handling.
- `frontend/src/game/teamMembership.ts`: shared playing-member validation.
- `frontend/src/game/camera/SmoothCameraController.ts`: camera controller.
- `frontend/src/game/scenes/BattleScene.ts`: camera integration, cleanup and hitbox correction.
- `frontend/src/game/PhaserGame.tsx`, `pages/BattlePage.tsx`,
  `components/arena/ArenaNavigation.tsx`: zoom buttons and ref bridge.
- `frontend/tests/room-camera.test.ts`: six component/membership/controller tests.
- `frontend/tests/room-camera.browser.mjs`, `tests/fixtures/camera.html`: real browser regression.

## Validation results

- Complete backend suite: **158 passed**.
- Membership/realtime suite after legacy snapshot normalization: **31 passed**.
- Complete frontend suite: **36 passed**.
- Ruff over backend apps/tests: passed.
- TypeScript check and production build: passed.
- `makemigrations --check --dry-run`: no changes detected.
- Chrome headless: real creation default/options/save, six solo teams starting a room of 20,
  visible battle zoom controls, wheel cursor anchoring, buttons, rapid mixed input, real
  two-touch pinch, tower/base selection during/after zoom, drag, desktop/phone fit, authoritative
  state/HP reconciliation and listener cleanup all passed.
- Cursor anchor error was approximately **0.0013 world units** in the browser measurement.
- Visual inspection of the real battle page confirmed that its existing artwork is retained.

Reproduce unit/build checks from the respective directories:

```sh
# backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check apps tests
DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python manage.py makemigrations --check --dry-run

# frontend
node --import tsx --test tests/*.test.ts
npm run lint
npm run build
```

For browser tests, start these in separate terminals:

```sh
# backend: temporary database, removed when the server exits normally
.venv/bin/python tests/browser_preview.py

# frontend
API_PROXY_TARGET=http://127.0.0.1:8011 npm run dev -- --host 127.0.0.1 --port 5174
```

Then run from `frontend` with Playwright available in the environment and Chrome installed:

```sh
node tests/room-camera.browser.mjs
```

If Playwright is provided by a bundled runtime rather than project dependencies, set
`NODE_PATH` to that runtime's `node_modules`. `TEST_BASE_URL` and `TEST_BROWSER_CHANNEL`
can override localhost:5174 and Chrome. No new application dependency was added.

## Limits

Touch was tested with Chrome's touch emulation, not a physical phone. The camera test uses
real Phaser scenes and server maps with a synthetic visual tower; existing backend tests
cover authoritative construction, economy, rewards and realtime behavior. The build still
reports Vite's large-chunk warning for the Phaser bundle. Docker services were not rebuilt
or restarted; runtime browser checks used separate local servers and a disposable database.
