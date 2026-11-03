> Current update (2026-10-21): `TROOP_MOVEMENT_SPEED = 4` replaces 2 in the same authoritative unit, with one rally gate per team and bidirectional snapshot recovery. See [implementation and verification](SPAWN_TOWER_REALTIME_IMPLEMENTATION.md).

# Independent troop movement and combat

Implemented 2026-10-21. The [pre-change audit](TROOP_MOVEMENT_COMBAT_AUDIT.md) includes an actual reproduction of the entire column advancing zero behind a stationary leader. This update changes server simulation, deployment, public state and Phaser rendering together. Existing artwork, damage, cooldown configuration, HP, prices, economy and reward rules are retained.

## Staging and road entry

`formation.initialize_spawn` assigns the first physically clear deterministic staging slot near the team's spawn. There are 35 bounded candidate slots for the supported maximum of 30 active troops. Candidates account for the actual projected sprite bodies, keep the outgoing lane clear and are reused as troops leave. A purchase never changes the existing troops' positions. Both deployment events and saved snapshots carry the actual map coordinates. A truly full physical staging area rejects the deployment transaction instead of charging for a stacked or invisible troop.

Spatial `movement_zone` is STAGING or ROUTE. `combat_state` is IDLE or ATTACKING independently: a troop shooting on a road remains in ROUTE. The authoritative per-unit JSON also stores movement state, current position, attack target, cooldown, route progress and any private approach/bypass path.

Staging has no front-to-back formation dependency or road minimum-arc-gap rule. Each troop chooses an available merge point on the first outgoing road, navigates around physical bodies, and follows the remaining ordered road waypoints after entry. Occupied entries can be replaced with another valid nearby entry. Local swept collision checks, replanning and sideways yielding prevent a stationary crowd from closing all entrances. These are physical collision decisions per troop, rather than a shared marching lock.

Saved negative-distance queues are upgraded in place on their next simulation step: their existing physical locations become independent staging approaches. The server preserves their position and HP, bounds their inherited approach, and spends ordinary movement budget to reach the new road entry. There is no instant rearrangement or healing. Existing round-based LEGACY gameplay remains supported.

## Exact speed value and unit

`apps/combat/balance.py` now contains one authoritative setting:

```python
TROOP_MOVEMENT_SPEED = 2
```

The existing balancing unit is a **dimensionless multiplier**, replacing 1.5. Catalog movement remains hops per legacy round. The continuous conversion remains:

```text
map-coordinate units / second
  = catalog movement × stored reference hop length / baseline round seconds × 2
```

For catalog movement 1, reference hop length 80 and baseline 30 seconds, the resulting physical speed is 5.3333 map units/second. A real two-team route stores reference hop length approximately 85.1380 and therefore travels at approximately 5.6759 map units/second under the default baseline. Existing explicit catalog movement differences remain effective. The value 2 is neither pixels/frame nor a second multiplication of the old speed. The old movement multiplier constant is removed; projection's 1.5 horizontal scale remains a geometric transform.

Every path segment, including sideways passing and staging movement, consumes the same physical-distance budget. Reconnection and major rounds retain the stored reference length. The client only interpolates received positions. Tests compare fixed steps of 50/100/200 ms, all three standard mobile types and a restored next-round state. Mobile maximum HP remains 100; troop damage multiplier remains 0.5, with the existing fractional carry. Tower damage, costs and attack cooldown configuration are unchanged.

## Independent road traffic and combat

The existing `FormationTraffic` still controls compact single-file marching and deterministic junction priorities. Its moving-leader constraints remain useful on normal roads. `navigation.move_independently` handles physical admission and local bypass paths around stationary combat blockers. Each path stays within a bounded road shoulder and rejoins its assigned route. New bodies entering an existing bypass trigger replanning from the current actual position.

All living units receive their own movement/combat evaluation each fixed tick. A valid attack target stops that particular troop. Other troops keep their own budget, route, target and cooldown. If another troop subsequently acquires its own target, its own attack policy applies. No animation determines simulation progress.

Collision handling uses the existing SVG body sizes, anchor offsets and isometric projection. It checks swept segments against body rectangles and already reserved motion, including high-speed movement through corners. It clips at the first physical collision rather than tunneling, teleporting or ignoring bodies. Ordinary marching stays compact; exceptional passing can temporarily widen the formation.

Destination occupancy still limits a finite one-file road. Troops cannot pass beyond their base-attack destination. A road full of bodies can delay further physical admission; all staged units continue receiving independent simulation turns. The 30-troop admission stress test explicitly releases terminal arrivals, separating staging liveness from finite destination capacity. Existing graph-hop targeting and opposing-team combat rules are retained.

## Realtime and Phaser

The existing transactional checkpoints, match locks, durable event versions, outbox retries and WebSocket recovery are reused. The public simulation-state allowlist now includes actual 2D position, movement trail, spatial zone, movement state, combat state, attack target and remaining cooldown. Deployment, COMBAT_TICK and reconnect snapshots therefore describe the same server-owned positions and combat state.

`formationPosition.ts` projects those actual coordinates; older node/edge progress still works as a fallback. Each Phaser entity retains its own `MotionTrack`. The server's within-tick physical trail supplies interpolation corners for roads and bypasses, avoiding corner cutting or forced movement back to the road center during an attack. Attack effects continue independently. Staging boundary metadata uses the existing terrain palette; no sprite or artwork asset is replaced.

## Verification

The final check results are recorded in [troop-movement-tests.json](qa/troop-movement-tests.json): **229 backend tests passed**, with six PostgreSQL-only tests skipped in that suite and then **all six passed separately on PostgreSQL 17**; **67 frontend tests passed**; Ruff, Django system checks, TypeScript and the production build passed. Commands:

```sh
# backend/
.venv/bin/pytest -q
.venv/bin/ruff check apps/combat/{balance,continuous,formation,map,navigation}.py apps/units/services.py tests/{test_continuous_combat,test_formation_realtime,test_live_battle_gameplay,test_troop_movement_combat}.py
.venv/bin/python manage.py check --settings=config.settings.test
# Disposable PostgreSQL only; provide its DATABASE_URL:
.venv/bin/pytest tests/test_round_concurrency.py --ds=config.settings.test_postgres -q

# frontend/
npm test
npm run build
```

New deterministic and service tests cover five free staging troops plus a sixth without reordering, 2/4/8/20-team maps, 30-troop admission as downstream space clears, actual body clearance, ordinary Infantry ranges, a stopped ranged attacker safely passed by followers, multiple independent cooldowns, resuming after target destruction, speed budgets, saved queue upgrade and snapshot/delta agreement. Existing live deploy/build, twenty-team, reward, economy, unlock, base destruction and victory tests remain in the full suite.

Browser tests use a disposable backend and two independent authenticated Chrome contexts:

- [troop-movement-browser.json](qa/troop-movement-browser.json): six staging positions; five simultaneous frames with a stopped artillery attacker and moving Infantry; movement received for all five Infantry on both clients; exact positions/zones/targets/cooldowns after full reload; surviving troops across the next major round; +20 reward claimed once despite retries. Zero page errors.
- [formation-realtime-browser.json](qa/formation-realtime-browser.json): rooms with 4, 8 and 20 teams; live Infantry/Tank deployment and tower construction; idempotent concurrent commands; HP/death/movement agreement; a real offline client and a deliberately delayed combat frame; final snapshot agreement with zero divergent entities or duplicate sprites. Zero page errors.
- [live-battle-capacity.json](qa/live-battle-capacity.json): 30 distinct staging positions, all 100/100 HP; the last troop remains pannable, visible and selectable. Camera bounds include actual staging coordinates and inherited off-map approaches rather than relying on the old queue-distance field.
- Visual checks: [staging](qa/troop-staging.png) and [independent combat](qa/troop-independent-combat.png).

To repeat browser checks, start `TEST_SCHEDULER=1 TEST_BACKEND_PORT=8017 .venv/bin/python tests/browser_preview.py` from backend/, and `API_PROXY_TARGET=http://127.0.0.1:8017 npm run dev -- --port 5177 --host 127.0.0.1` from frontend/. Run `TEST_BASE_URL=http://127.0.0.1:5177 node tests/troop-movement.browser.mjs` and `node tests/formation-realtime.browser.mjs`. Playwright and Chrome must be available; the local run used bundled Playwright via NODE_PATH. Existing databases are not migrated, flushed or seeded by this disposable test server.

## Deployment and measurement limits

Rebuild/restart backend and frontend together. No new schema migration is required; apply any already-existing migrations normally. The old position format remains readable while saved queues are converted on a tick.

Two browser clients in a 20-team room are not 20 simultaneous browser clients or a production soak test. Browser transport checks use one ASGI process, SQLite and InMemory Channels; the six PostgreSQL locking tests run separately. Production still needs shared Redis and PostgreSQL. Dense staging can cost more simulation time than ordinary marching; these bounded checks do not establish a 600-unit production load SLA. The production frontend build retains its existing large Phaser chunk warning.
