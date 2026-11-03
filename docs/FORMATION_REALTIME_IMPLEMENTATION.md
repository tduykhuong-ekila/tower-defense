# Compact formations, 2× movement and realtime recovery

Implemented 2026-10-21. The baseline and end-to-end investigation are in [FORMATION_REALTIME_AUDIT.md](FORMATION_REALTIME_AUDIT.md).

## Changes and causes

Formation spacing previously combined the full transparent texture square, a diagonal safety factor, inverse minimum projection scale, and a gap of 12. Infantry centers were 82.71 world units apart. The updated engine uses occupied body bounds at the existing render sizes: Infantry 34×38 px, Tank 54×44 px, Artillery 54×50 px. Decorative weapons/plumes and soft shadows may slightly overlap; body bounds stay separate. Sprite anchor offsets match Phaser's existing origin (0.5, 0.89).

Positions and ordering remain authoritative arc distances along the road. The minimum arc separation is `(front minimum footprint + rear minimum footprint)/2 + 2 world units`, with minimum footprint `min(body width, body height)/1.5`. The actual separation also has to clear the projected body bounds. Projection uses the same -135° rotation and 1.5/.86 scales as frontend projectMap. This supplies the direction-dependent footprint instead of inflating every direction to a texture diagonal. Projected visual margin is 1.72 px at world zoom 1; the arc minimum can add a little more on some directions.

A swept-body check reserves upcoming bends, preventing the front unit from turning into its stationary follower. It tests the next body-length-scale road polyline with exact segment/box intersections. This can open a small temporary gap at sharp bends; straight roads remain compact. Formation groups, deterministic admission order, junction priority and combat targeting are retained. New troops are inserted at the nearest safe rear progress using a deterministic body-clearance search, including negative staging progress. Existing derived footprint metadata is recalculated without moving/healing old units. Other lanes/teams and opposing traffic keep their existing independent rules.

Measured same-spawn center spacing: Infantry/Infantry **31.41** world units (39.83 projected px), Tank/Infantry **40.21**, Tank/Tank **49.00**. See [raw speed and spacing measurements](qa/formation-speed.json).

## Exact speed conversion

One authoritative constant changed: `TROOP_MOVEMENT_MULTIPLIER`, **0.75 → 1.5**. Effective speed is still `catalog movement × stored mean route hop length / configured baseline seconds × multiplier`. There is no additional per-round or frontend multiplier.

| Mobile type | Reference old speed | Reference new speed | Catalog damage | Max HP |
| --- | ---: | ---: | ---: | ---: |
| Infantry | 2 world units/s | 4 world units/s | 10 | 100 |
| Tank | 2 world units/s | 4 world units/s | 25 | 100 |
| Artillery | 2 world units/s | 4 world units/s | 40 | 100 |

Reference values use hop length 80 and baseline 30 s. Real route-specific hop length remains stored across reconnect and major rounds. Measured on the same unobstructed 595.966-world-unit route with a test baseline of 1 s: all three types changed **63.8535 → 127.7071 world units/s**, traversal **9.34 → 4.68 s**, ratio **0.50107** at 20 ms measurement resolution. The test runs the actual engine with the recorded old and new constants. Existing troop damage multiplier 0.5, fractional damage carry, tower damage, cooldowns, tick frequency, projectile/camera speeds and base HP remain unchanged.

## Authoritative synchronization

REST and WebSocket commands continue to share the transaction services. Match row locks serialize live deploy/build, ticks, event sequence allocation and snapshot generation; Team locks serialize wallet changes. Stable GameAction keys prevent duplicate charges/entities. Every event is persisted before its on_commit broadcast; failed publications retain broadcasted_at=null for the existing scheduler outbox retry.

The common match group still carries all durable sequence positions, with private payloads redacted for other viewers. This prevents privacy filtering from looking like a lost sequence. Event IDs are persisted UUIDs; `sequence_number` is the match cursor and also exposed as `state_version`. Event creation and broadcast attempt/failure logs carry match/group/type/sequence/entity identity. Failure logs include tracebacks, never player credentials.

The consumer subscribes before building its consistent snapshot. New **GET /api/v1/matches/{id}/snapshot/** returns the same versioned, permission-scoped envelope over HTTP. Unauthenticated viewers receive public state; verified members receive their own economy/unlocks; hosts retain full access. No new event replay database/infrastructure was needed: the existing outbox and authoritative snapshots cover durable recovery.

## Connection and reconciliation behavior

- Initial live deltas are buffered until a full snapshot, including reconnects. Snapshots discard covered deltas and drain any contiguous newer tail. Gaps coalesce into one in-flight repair; buffer capacity is 500 envelopes.
- Sync requests are only marked pending when a socket is open. Connection/snapshot timeout is **8 s**. A stalled request or handshake closes and replaces the transport instead of wedging recovery permanently.
- Heartbeat interval is **5 s**. Consumer PONG reports the durable cursor and renews match group membership. A newer server cursor triggers recovery even when the missing message was the last event. No received messages for **20 s** triggers socket replacement.
- Reconnect uses exponential backoff with jitter, capped at about 10 s, without the old eight-attempt cutoff. Online/visible wake events recover after network changes and browser sleep. Explicit unmount/disconnect cancels timers/listeners; authentication failures stop automatic retries. Old socket callbacks cannot mutate a newer room connection.
- A bounded full-state repair every **30 s** remains as a backstop; no frame-by-frame polling. Timing can be configured through SocketHealthOptions.
- Snapshots older than the current cursor are rejected, including cursor zero. Unknown live entity references request recovery. Stable entity IDs reconcile into the existing Phaser registry, preserving the map/camera/selection.
- Latest state is applied at scene readiness; up to 500 pending live effects are buffered until then. Motion signatures include simulation time. MotionTrack uses server simulation timestamps mapped into its local render clock, so receive jitter does not stretch server movement intervals. Older motion samples are ignored; road-corner interpolation remains finite and does not extrapolate through missing data.

## Main files changed

- Backend: apps/combat/{balance,formation}.py; apps/units/services.py; apps/realtime/{events,services,consumers}.py; apps/matches/{services,views,urls}.py.
- Frontend: src/services/websocket.ts; src/types/realtime.ts; src/stores/matchStore.ts; src/pages/BattlePage.tsx; src/game/PhaserGame.tsx; src/game/scenes/BattleScene.ts; src/game/systems/interpolation.ts.
- Tests: new backend/tests/test_formation_realtime.py and frontend/tests/{realtime-recovery.test.ts,formation-realtime.browser.mjs}; updated existing speed/socket/interpolation expectations and continuous browser fixture.

Paths above are relative to backend/ or frontend/ as indicated. Existing art is retained. No schema migration is added by this change. Rebuild and restart **both** applications together; apply existing migrations normally if the deployment is behind.

## Verification and limits

Executed against the final code:

- Backend full suite: **216 passed, 6 skipped** (the six require PostgreSQL).
- Those six PostgreSQL concurrency tests separately: **6 passed**, using a disposable PostgreSQL 17 cluster. Covers duplicate deployments/rewards, competing ticks, and live commands racing a tick with correct wallet/entity counts.
- Frontend: **64 passed**; TypeScript check and production build passed. Vite retains the existing large Phaser chunk warning.
- Ruff for every edited Python source/test: passed. Django system check: passed.
- Existing live-battle.browser.mjs: **PASS**, including actual UI build/deploy during Battle, pause centerline alignment, next major round, reconnect, unchanged tower damage 15 and +20 reward exactly once.
- New formation-realtime.browser.mjs: **PASS** for **4, 8, 20 teams**, with two independent Chrome sessions per room. Covers Infantry/Tank visibility, live build, concurrent idempotent retries, wallet deduction once, movement/HP/death convergence, actual offline disconnect and automatic recovery, plus deliberately delaying a real combat frame until after newer messages/snapshot recovery. **Zero page errors**.

| Teams | Attack events observed | Destroy events observed | Reconnect recovery | Event latency p95 A/B | Final entities | Divergent entities / duplicate sprites |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 40 | 1 | 592 ms | 84 / 99 ms | 21 | 0 / 0 |
| 8 | 96 | 1 | 599 ms | 35 / 37 ms | 37 | 0 / 0 |
| 20 | 360 | 1 | 617 ms | 33 / 29 ms | 85 | 0 / 0 |

Raw retransmissions were actually observed: A/B duplicate envelope counts were 1/1, 6/6, 2/2 respectively, with no duplicate entities/sprites. Each intentionally disconnected viewer had 8 missing raw sequence positions across the measured session; snapshots recovered the complete final board. The delayed-frame test injects one additional application-level delayed frame per room and confirms a recovery snapshot plus rejection of the eventual old frame. These are not claims of zero packet loss: final authoritative state and Phaser IDs were compared after pausing each server room. Frame samples were approximately 60 fps; raw frame/latency/cursor data is in [formation-realtime-browser.json](qa/formation-realtime-browser.json). The screenshot is [formation-realtime.png](qa/formation-realtime.png).

Test databases and browser rooms were disposable; no existing room/database was migrated or flushed.

The browser harness uses two independent Chrome contexts per room with actual HTTP commands, WebSocket delivery, Zustand state and Phaser sprites. Room sizes 4/8/20 do not mean 20 simultaneous browser clients. Local test transport is one ASGI process with SQLite and InMemory Channels; PostgreSQL row-lock tests are separate. Production still requires shared Redis and PostgreSQL. These bounded local tests are not a production soak test or a guarantee against every network/provider failure.


## Repeat the checks

From backend/: `.venv/bin/pytest -q`; configure a disposable PostgreSQL DATABASE_URL and run `.venv/bin/pytest tests/test_round_concurrency.py --ds=config.settings.test_postgres -q`.

From frontend/: `npm test` and `npm run build`.

For browser verification, start a temporary backend from backend/ with `TEST_SCHEDULER=1 TEST_BACKEND_PORT=8017 .venv/bin/python tests/browser_preview.py`. From frontend/, start `API_PROXY_TARGET=http://127.0.0.1:8017 npm run dev -- --port 5177 --host 127.0.0.1`, then run `TEST_BASE_URL=http://127.0.0.1:5177 node tests/formation-realtime.browser.mjs` and `TEST_BASE_URL=http://127.0.0.1:5177 node tests/live-battle.browser.mjs`. Playwright and Chrome must be installed; this execution used bundled Playwright via NODE_PATH. Keep source files unchanged while measuring to avoid Vite HMR reloading the instrumented fixture.
