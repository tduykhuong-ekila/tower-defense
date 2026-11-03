# Troop movement and combat audit

Recorded before implementation on 2026-10-21.

## Actual runtime

- `apps/units/services.py:deploy_unit` creates troops immediately as QUEUED and calls `formation.initialize_spawn` in CONTINUOUS mode. The map has one spawn node per team connected to lane 2; it has no staging polygon or independent spawn slots.
- `formation.initialize_spawn` allocates successively negative `route_distance` values behind the spawn. `synchronize_position` exports `approach_node_id`/`staging_distance`. This is an unbounded single-file approach, not a free staging area. A purchase does not reshuffle existing troops.
- Routes are ordered graph waypoints from deterministic shortest paths. Movement is continuous arc distance using actual edge lengths. `FormationTraffic` computes a frame before applying it, with directed per-team leader constraints, junction priorities, projected sprite-body clearance and bend reservations.
- Reproduction with five Infantry: initial arc distances are approximately 0, -31.41, -62.82, -94.23, -125.65. Setting the first troop's movement to zero makes all five advance zero in the next tick. This reproduces the blocking traffic dependency independently of animation.
- `ContinuousEngine.step` already evaluates every troop. It collects individually stopped IDs when an enemy is in range. There is no global attack flag, shared animation promise or early return from the troop loop. However, `FormationTraffic.move` recursively limits every follower by its leader, including stationary attacking leaders. This propagates a combat stop through the column.
- Cooldown (`attack_remaining`), route progress and simulation state are already per entity. Target acquisition is recomputed per attack; target/combat/movement states are not explicitly published.

## Speed unit

Catalog `movement` is graph hops per legacy round (standard mobile types: 1). Continuous movement converts this to map-coordinate units/second: `catalog movement * stored reference_hop_length / movement_baseline_round_seconds * TROOP_MOVEMENT_MULTIPLIER`. The existing authoritative balancing value is a dimensionless multiplier, currently **1.5**. Default reference 80 / baseline 30 gives 4 map units/second. Routes store their mean hop length once; reconnects and rounds do not multiply it again. The frontend has no authoritative movement multiplier. The requested value 2 will replace 1.5 at this boundary, using the existing multiplier unit, not pixels/frame or a second multiplication by two.

## Rendering and synchronization

- `formationPosition.ts` projects server edge/staging progress. `BattleScene` owns a separate `MotionTrack` per entity. The tracks interpolate fixed server timestamps over finite road polylines; attack effects are independent visual effects.
- Existing rendering cannot represent authoritative off-center staging/passing positions. It draws long approach roads for negative staging progress. New physical positions must travel through both public deltas and snapshots and be projected consistently.
- `ContinuousCombatService.tick` locks match/team/entity rows, checkpoints JSON simulation state and emits durable versioned COMBAT_TICK deltas. Its public allowlist currently omits combat state/cooldown and any 2D position.
- Deployment events and snapshot serializers include persisted simulation state. WebSocket sequence buffering, heartbeat, stale-snapshot rejection, reconnect and outbox recovery already exist and should be reused.

## Scope of correction

Introduce bounded deterministic staging slots and explicit spatial zones separate from combat. Retain ordinary compact road traffic. Give troops a server-driven local path around a stationary combat blocker, with swept body collision checks and the same distance budget for lateral motion. Publish actual position and per-unit states through existing event sequencing. Preserve 100 mobile HP, damage/cooldowns, economy, unlocks, rewards, round lifecycle and map artwork.
