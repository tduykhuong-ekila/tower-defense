# Continuous battle architecture

> Current update (2026-10-21): `TROOP_MOVEMENT_SPEED = 4` replaces 2 in the same authoritative unit, with one rally gate per team and bidirectional snapshot recovery. See [implementation and verification](SPAWN_TOWER_REALTIME_IMPLEMENTATION.md).

New rooms default to `gameplay_mode=CONTINUOUS`. Persisted configurations without that key remain `LEGACY`; starting an existing lobby also preserves its missing-mode legacy contract. No running room is silently migrated. The old round resolver rejects continuous rooms, preventing manual double damage. In continuous rooms, troops remain in their rally area and cannot attack during the first preparation; simulation ticks continue through preparation between later rounds so surviving troops and towers do not freeze. The final 15/20/30 seconds of rounds 1/2/final form a climax with defensive towers taking 1/1.5 incoming damage and 10% faster Infantry and Tank fire.

## Lifecycle

`LOBBY → PREPARATION → WAR → PREPARATION → WAR [→ PREPARATION → WAR] → RESULTS`.

`current_round` identifies one of 2/3 major rounds. Existing `WAR`, `PLANNING`, `MATCH_PHASE_CHANGED`, `ROUND_STARTED`, `MATCH_ENDED` contracts are reused; `round_phase=BATTLE` identifies continuous combat. Each phase has persisted `phase_started_at`/`phase_ends_at`. The phase deadline is authoritative. The HUD reads that deadline; a browser never advances time. Survivors retain node, partial-edge progress, cooldown, HP/shield, ownership and targets. Economy, unlocks, scores and eliminations persist. Income is credited once per completed battle, including the final battle. Early elimination victory uses existing winner/ranking precedence and shared-rank tie rules.

Preparation permits eligible purchases, repair, upgrades, questions and reward claims. Battle permits deployment, construction and target changes through the common server policy, plus camera and inspection. It closes unanswered/pending questions. Questions still grant exactly 20 coins when coins are selected; duplicate claims remain idempotent. This deliberately closes question/reward actions at battle start instead of allowing a late grace claim during battle.

## Simulation

`ScheduledMatchApplication` owns a server task, polling every 100 ms, independently of connected players. Daphne starts it on the first request (production health checks supply this after restart); lifespan-capable servers start it on startup. `MatchScheduler.advance_due` locks the match row, and `ContinuousCombatService.tick` rechecks the exact persisted `next_tick_at`. A duplicate/stale tick is a no-op. State and the next tick deadline commit together. A restart reloads committed positions/cooldowns and resumes without repeating damage. Up to 25 deadlines are processed per visit; excess lag is retained for subsequent visits. No ticks or elapsed damage are discarded. A pause shifts phase/tick/match deadlines by its elapsed duration.

Each tick uses the configured fixed timestep, not wall-clock jitter. Processing order:

1. Activate queued troops; decrement cooldowns and EMP/shield timers in seconds.
2. Resolve target fallback with existing nearest-base/IDLE rules.
3. Move over consecutive passable graph edges using physical map lengths. Stop for eligible enemy targets in range. Persist `next_node_id` and fractional `edge_progress`.
4. Towers select threats closest to their defended base; IDs break ties. Commit simultaneous tower intents before troop attacks.
5. Surviving troops use configurable UNIT/TOWER priority (TOWER first by default), then distance and stable IDs. At the base attack position, an in-range tower is attacked before the base; base damage resumes after no eligible tower remains in range. Resolve simultaneous troop/base intents with shields first.
6. Destroy entities, eliminate bases and their entities, attribute damage/destruction, evaluate victory.
7. Batch only changed entity fields and teams; checkpoint tick, persist COMBAT_TICK delta after commit. Refresh scores on combat events and periodically using an aggregate question query.

Continuous base attacks repeat on cooldown; troops survive reaching a base. This is an intentional change from legacy one-shot base impact. Towers retain their original per-hit damage and upgrade behavior. Attack frequency is separately configurable; damage-per-second is therefore not presented as half the old turn-based DPS.

A spatial node index limits candidate scans. General range remains graph hops with fractional-edge distances, including opposing troops on the same edge. A tower connected to both endpoints covers the intervening span at range 1; troops need not land exactly on a waypoint to attack it. Cached range sets and existing map route caches are shared by team count. ORM updates group entities by changed fields instead of rewriting six fields for every unit.

## Rendering and recovery

The Zustand store upserts self-describing tick updates by entity ID. Each team has a compact rally patch; admission through its spawn gate follows durable formation order. Only admission is sequenced; road traffic and combat remain independent. Phaser uses one `MotionTrack` per moving troop, one tick of render delay, and its frame loop. The buffered polyline includes road corners; correction routes use passable graph paths. Late data never extrapolates through terrain; a long gap snaps to authoritative state. Live attacks use existing bounded projectile/hit pools and do not lock the scene for a replay. Death visuals last 180 ms and movement stops immediately. Preparation/pause stops motion at the authoritative position. React does not render sprite positions per animation frame.

Full snapshots serialize with the same match row lock. Socket gaps buffer newer deltas pending repair, discard duplicate/stale sequences, and reconcile snapshots without overwriting newer state. A periodic 30-second snapshot repairs silent final-packet loss. Reconnect receives a fresh snapshot with partial-edge state. The durable event outbox retries transport failures; snapshots remain the recovery authority.

## Deployment and limits

Apply migrations, then restart/rebuild backend and frontend. Production requires PostgreSQL row locks plus Redis Channels shared between processes. SQLite/InMemory is a single-process local preview. The default 5 Hz is measured locally for one room, not a guarantee for many simultaneous rooms or regional connections. Event logs are finite for configured match duration but can be large: plan retention/archive for completed matches. Outbox delivery is at least once; duplicates are intentional and safe.
