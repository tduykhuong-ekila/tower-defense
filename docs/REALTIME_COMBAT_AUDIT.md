# Realtime combat audit — 2026-10-21

## Confirmed behavior and causes

- `units/services.py` already records UNIT_DEPLOYED/TOWER_BUILT with stable IDs and HP. `MatchService.record_match_event` already locks the match and broadcasts after commit to the correct Channels match group. Missing broadcasts are **not** the only explanation.
- `realtime/services.py` catches transport errors and only logs them. There is no delivery checkpoint/retry. An event lost after commit can remain invisible indefinitely until reconnect/reload.
- Private events consume the global sequence but are sent only to team/host groups. Other viewers interpret intentional omissions as packet loss and request snapshots. The socket advances its high-water mark before repair and dispatches newer deltas immediately; older deltas can then be discarded by the store. Snapshot reads are correctly serialized with writers.
- Phaser has a stable-ID visual registry. However `updateState` returns during round playback, delaying unrelated new entities by up to eight seconds. Reconciliation also creates replacement movement tweens; the movement event uses only its final node and can cut across intermediate waypoints.
- `MatchScheduler` polls once/second and `CombatService` runs a complete combat round only at each 30-second planning deadline. Movement is integer graph hops/round, attacks occur once/round, rounds increment indefinitely until phase/match expiry. This is the confirmed cause of discontinuous combat.
- Default mobile stats: infantry movement 1, damage 10; tank movement 1, damage 25; artillery movement 1, damage 40. HP is integer. Tower damage is 15/30; existing tower upgrades multiply by 1.25 and floor.
- The ASGI scheduler is independent of browsers and uses match row locks. Retain it with subsecond polling and persisted tick deadlines. Production uses Redis; SQLite/InMemory is only suitable for one local process.

## Implementation and ownership

- Visibility: durable MatchEvent dispatch checkpoint + retry, permission-projected sequence markers, ordered socket repair, periodic authoritative repair, stable-ID incremental Phaser rendering.
- Lifecycle: explicit CONTINUOUS gameplay mode for new rooms, 2/3 rounds, per-round preparation and battle deadlines. Existing stored rooms without that mode retain legacy behavior.
- Movement/targeting/damage: new pure fixed-step engine using existing map, targeting priorities, damage/shield functions; persistent per-entity edge progress/cooldown/fraction carry; batched DB bridge.
- Frequency/recovery: persisted simulation time and tick counter under the same match lock; bounded catch-up; no per-player loop.
- Completion: existing ScoringService, elimination winner and shared-rank rules.
- Frontend: store delta reconciliation, Phaser frame-loop interpolation of ordered movement samples, immediate attack effects, HUD and host configuration.

## Compatibility risks

- Continuous mode changes base impact from consuming a unit to repeated cooldown attacks; documented intentional migration for continuous battles. Legacy resolver remains available only to legacy rooms.
- Legacy movement has no physical speed. Baseline conversion uses the assigned route’s actual mean edge length divided by the configured legacy round duration. Store this reference once; apply the movement multiplier once. A complete uninterrupted route then takes twice the old hops/round travel time.
- Integer HP requires a persisted fractional damage remainder for odd damage. Never halve stored UnitType stats.
- Deploy/build/question/reward mutations are restricted to preparation in continuous mode; existing legacy phase policies remain.
- Database migrations and rebuilt frontend/backend images are required. Redis outages can delay delivery; snapshots and durable retries recover committed state.
- Twenty-team support is not equivalent to verified production performance; benchmark actual tick/query/network/render results separately.

## Additional reproduced preview issue

During the final two-browser run, a real deployment returned HTTP 500 while snapshots and the scheduler were active on the disposable SQLite preview. Deferred SQLite transactions can deadlock when concurrent readers upgrade to writers; PostgreSQL row-lock tests pass separately. Persistent preview and the disposable browser server now use Django SQLite transaction_mode=IMMEDIATE to acquire the writer lock at transaction start, with the existing 20-second timeout. This serializes preview writers; SQLite is still a single-process preview configuration.
