# Infantry fire rate, speed 7 and animation stability

Implemented after the [pre-change audit](INFANTRY_ANIMATION_AUDIT.md). Existing Phaser graphics and server-authoritative multiplayer combat remain in use.

## Gameplay

- Infantry uses `INFANTRY_MOVEMENT_SPEED = 5.5` directly instead of 6. Map distance/second remains `catalog movement × persisted reference hop length / movement baseline seconds × 5.5`. No extra multiplier, departure queue or Infantry cap was added. Independent movement, centralized rally offsets and waypoint polylines are retained.
- Infantry's effective configured attack cooldown is divided by **1.5**: the default changes from **2 s to 1⅓ s**, or **0.5 to 0.75 shots/second**. Both entity overrides and the match fallback go through `combat.balance.attack_cooldown`.
- Fractional overshoot is carried to the next eligible simulation boundary, avoiding a 1.4-second rounded cooldown at the default 200 ms tick. If a custom Infantry cooldown permits multiple shots in one tick, each receives its own server intent, damage application and event. Idle time does not bank overdue shots. Cooldown seconds remain in each entity's persisted `simulation_state.attack_remaining`.
- Unupgraded Infantry damage stays **5 HP/shot**, HP **80**, cost **15**. Tank, Artillery and tower cooldowns/damage retain their original policy. Global tick duration is unchanged. This applies to continuous mode; legacy round combat is retained.

## Rendering and synchronization

Removed the moving screen-grid visibility sampler that repeatedly hid living Infantry. Walking uses authoritative movement state plus remaining interpolated motion, and recognizes paused animations. A packet boundary does not force idle. Snapshots no longer stop live walking through the legacy replay cleanup path. Shot events retain weapon recoil, projectiles and impacts; they do not write root coordinates or reset motion history.

Each live entity keeps one registry entry and sprite. Existing pooling is limited to legitimate removals. Viewport and overview culling retain objects and pause/resume animation phase. Snapshot payloads now include the persisted simulation checkpoint timestamp and tick interval; the store attaches these to restored entities. A rejected older interpolation sample cannot consume a later valid sample's signature. Existing sequence, duplicate, chunking and listener recovery rules remain in place.

After measuring a drop to 29 FPS in one 2,000-Infantry viewer when drawing every overlapping body, large scenes (200+ visuals) now omit only fully coincident Infantry bodies. Groups use **exact authoritative world coordinates**, team, target, movement state, level and HP/shield; coordinates are never rounded or bucketed into moving screen cells. Previous representative IDs persist as the group moves and new units arrive. Every distinct position is rendered, selected units remain visible, and all IDs/HP/motion tracks stay in the registry. This is cosmetic overdraw reduction, not a deployment limit. Effects retain their existing bounded pools.

## Verification

- Full SQLite backend suite: **290 passed, 8 PostgreSQL-only tests skipped**.
- Frontend: **75 passed**, TypeScript and production build pass. The existing Phaser bundle-size warning remains.
- Ruff on changed runtime Python and the new fire-rate tests, Django system checks, and migration drift checks pass. No database migration is required.
- Deterministic combat: **45 Infantry shots in 60 seconds**, previously 30, at 100/200/500/1000 ms steps, against troops, towers and bases. Each event applies one unchanged 5-HP hit. JSON restoration occurs after every step. Real committed-tick retry and snapshot tests retain cooldowns and apply no repeated damage. Tank, Artillery and tower controls retain 30 attacks/60 seconds; tower hits remain 15 HP. Short custom cooldowns also retain distinct shots at coarse tick boundaries.
- Movement checks cover speed 7 relative to prior speed 6, fixed-step equivalence, persisted reference lengths, route corners, independent Infantry movement, live paid deployment, HP/cost and vehicle capacity.
- Real two-team Infantry browser combat: both clients observed all ten live deployments moving, attacks from both teams, **32 attack events and two deaths**. Every shot retained 5 damage, surviving HP/positions/cooldowns matched the paused server snapshot, sprite identities were not replaced, and shot effects never changed root positions. Death sprites were compared after their legitimate 180 ms fade.
- Existing two-client movement/combat regression passes, including a stopped Artillery attacker with independently moving Infantry, live towers, exact pause/reload recovery and next-round survivors.
- The animation probe verifies zero in-viewport visibility changes and one walk start per Infantry, explicit live sync, offscreen resume and a 500 ms packet gap. It also includes a controlled 300-entity render fixture to exercise coincident-body culling independently of server cadence.

Evidence: [animation before](qa/infantry-animation-before.json), [animation after](qa/infantry-animation-after.json), [two-team Infantry combat](qa/infantry-combat.json), [movement/combat](qa/troop-movement-browser.json), [load before overdraw reduction](qa/infantry-animation-load-before-occlusion.json), [final twenty-team load](qa/infantry-browser.json).

## Reproduction

Use disposable databases; the browser server never modifies `backend/db.sqlite3`.

```sh
# backend/
.venv/bin/pytest -q
TEST_SCHEDULER=1 TEST_BACKEND_PORT=8021 .venv/bin/python tests/browser_preview.py

# frontend/, separate terminal
API_PROXY_TARGET=http://127.0.0.1:8021 npm run dev -- --port 5181 --host 127.0.0.1
npm test
npm run build
node tests/infantry-animation.browser.mjs
node tests/infantry-combat.browser.mjs
TEST_BASE_URL=http://127.0.0.1:5181 node tests/troop-movement.browser.mjs
TEST_BASE_URL=http://127.0.0.1:5181 node tests/infantry.browser.mjs
```

Browser checks require Playwright (`NODE_PATH` can point to the bundled runtime) and Chrome. `INFANTRY_AUDIT_BASELINE=1` skips fixed-behavior assertions; reproduce historical measurements using the pre-change sources.

## Capacity limits

Unlimited Infantry is a purchase rule, not unlimited server throughput. Full entity checkpoints, snapshots and per-viewer delivery still scale with army size. The largest browser scenarios can spend much of their recovery window applying snapshots rather than individual ticks; rendering FPS alone does not establish sustained 5 Hz simulation. Production PostgreSQL/Redis, twenty simultaneously connected viewers, internet latency and many-room capacity were not validated here. PostgreSQL-only tests require a disposable PostgreSQL service. No gameplay cap or dropped authoritative unit was used to conceal these limits.

## Measured twenty-team browser load

Two authenticated viewers per room. All scenarios retain exact authoritative state, zero duplicate sprites, bidirectional paid live purchases and successful reconnects. The counts include the two live purchases. Times are local samples; server cadence and concurrent test activity affect delivery.

| Infantry/team | Final entities | Before overlap culling, median FPS A/B | Final median FPS A/B | Final accepted ticks A/B | Visible bodies A/B |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 402 | 60/60.0 | 60/60 | 5/8 | 22/40 |
| 50 | 1002 | 59/50 | 60.0/60.0 | 4/5 | 32/50 |
| 100 | 2002 | 37.0/29.0 | 60.0/60 | 2/1 | 36/50 |

Low individual tick acceptance at large sizes remains a server/transport capacity limitation, even with stable 60 FPS drawing and accurate recovery snapshots. These measurements do not establish sustained 5 Hz authoritative movement at 2,000 units. Unchanged full entity checkpoint/delivery costs are described in the earlier Infantry report.
