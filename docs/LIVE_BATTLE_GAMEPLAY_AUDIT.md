# Live battle gameplay audit — 2026-10-21

## Confirmed baseline

- `combat/balance.py`: troop movement multiplier 0.5; damage multiplier 0.5 with persisted fractional remainder. Physical speed is route mean edge length × movement / legacy baseline seconds × 0.5. Update the existing speed factor to **0.75**, leaving damage/cooldowns/tick interval unchanged.
- `units/seeds.py`: Infantry 40 HP, Tank 120, Artillery 45. Deployment copies raw hp into both entity fields. Per-entity max_hp is persisted and snapshots/events include it. New mobile types also need the 100-HP invariant, beyond changing three seeds.
- `combat/continuous.py`: individual path movement, no friendly following-distance constraints. Friendly troops can share logical positions. Movement is authoritative and persists partial edges in simulation_state.
- `BattleScene.reconcile`: units sharing a logical node receive a 6-column visual offset, so existing rendering actively spreads formations off the road. Remove these offsets for continuous formation units; retain the existing legacy rendering.
- `matches/action_policy.py` and frontend `actionAvailability.ts` reject all continuous Battle actions through broad PREPARATION/PLANNING gates. Narrow the exception to deploy/build/target; questions/rewards and other special actions retain their existing eligibility.
- Purchases, target changes and ticks already lock the same match row and commit events after mutations. Reuse this transaction order; no second ingestion pipeline or browser-authoritative simulation is needed.
- Tick snapshots currently project only next_node_id/edge_progress from simulation_state. Formation/staging position must also be included in spawn events and live deltas so all clients render identical positions.

## Planned implementation

1. Central speed factor 0.75 and mobile HP 100. A data migration updates troop catalogs and existing entity maxima; current HP is preserved, clamped to [0,100], never healed. Tower/base HP remain untouched.
2. A pure server formation controller persists assigned routes, arc progress, footprint and monotonic admission order. Friendly same-direction shared lanes have safe following gaps; front units resolve first. Deterministic merge priority prevents concurrent admission/overtaking. Different teams/opposing traffic do not share a global queue.
3. Congested spawns use a server-defined single-file approach to the spawn road: new entities receive an ordered negative approach distance rather than overlapping at the spawn. Clients render that explicit centerline approach and draw its road. Staged units enter combat as physical room becomes available; no arbitrary construction delay is added.
4. Open deploy/build/target in PLANNING preparation and BATTLE war only. Keep coins, unlocks, capacity, placement, eliminated/read-only/pause/finished checks. Tick deadlines are not changed by a purchase.
5. Remove formation lateral offsets, interpolate authoritative approach/road positions, and verify actual services, two browser contexts, PostgreSQL concurrency and 20-team movement.

## Compatibility risks

- Existing overlapping troops cannot be separated without a discontinuity. They retain positions while leaders pull away; new deployments are spaced at admission. Existing damaged troops are not healed.
- Formation applies to continuous matches. The legacy resolver retains its movement model; catalog/spawn HP changes apply to mobile troops in both modes.
- Large configurable spawn queues require an extended approach road; this is explicit server geometry, not an invisible/random rendering offset. Measure normal five-troop limits and document larger-limit coverage separately.
