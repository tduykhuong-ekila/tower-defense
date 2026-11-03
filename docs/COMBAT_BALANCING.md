# Combat balancing

> Current (2026-10-22): Infantry uses `INFANTRY_MOVEMENT_SPEED=6` and new spawn HP `80`; vehicles retain speed 4 and HP 100. Infantry no longer waits for friendly traffic or consumes a deployment slot. Existing Infantry retain stored current/max HP. [Implementation, migration and measurements](INFANTRY_GAMEPLAY_UPDATE.md). The speed-4 discussion below describes the prior shared setting and the retained vehicle baseline.

> Previous update (2026-10-21): `TROOP_MOVEMENT_SPEED = 4` replaces 2 in the same authoritative unit, with one rally gate per team and bidirectional snapshot recovery. See [implementation and verification](SPAWN_TOWER_REALTIME_IMPLEMENTATION.md).

`apps/combat/balance.py` is the single backend conversion boundary. Raw UnitType stats, HP, shields, prices, rewards, towers and camera/projectile speeds remain unchanged. New continuous rooms apply these constants once; existing legacy rooms keep legacy combat.

| Mobile type | Original movement (hops/round) | Original damage/hit | Effective damage/hit |
|---|---:|---:|---:|
| Infantry | 1 | 10 | 5 |
| Tank | 1 | 25 | 12.5 average |
| Artillery | 1 | 40 | 20 |

`TROOP_MOVEMENT_SPEED=4`, `TROOP_DAMAGE_MULTIPLIER=0.5`.

Movement previously jumped integer graph hops per combat round (30 seconds by default). For the initial assigned route, compute actual physical length `L` and edge count `N`; persist `reference_hop_length=L/N` once. Baseline speed is `movement × (L/N) / movement_baseline_round_seconds`. Current speed is baseline × 4. Thus uninterrupted road travel takes `N × baseline_round_seconds / (movement × 4)` seconds, half the time of the previous speed-2 setting. Rally approach and traffic can add travel time. Tick discretization contributes at most one tick. Do not recalculate from the shortening route each tick or halve stored state after reload. Target fallback keeps the existing physical speed. `80` is only a fallback reference for standalone calculation without an assigned route; normal deployed-route simulation computes the real reference before moving. Actual movement consumes the exact length of every consecutive edge, including short spawn edges and enlarged 20-team lanes.

Integer HP is retained. Multiply troop base damage by the balance factor and then its existing 1.25 level multiplier. Carry the fractional remainder per attacker in `simulation_state.damage_remainder`; floor only the final accumulated damage. Tank attacks alternate 12 and 13; ten unupgraded attacks total 125 rather than 250. Very small custom damage can produce zero-damage hits while accumulating the remainder. Tower damage retains floor-once behavior: MG 15, cannon 30, upgraded 18/37. No balance factor is applied to towers, serializers' raw base_stats, or Phaser damage effects. Catalog damage reports the effective average in continuous rooms; hit labels use actual backend damage/HP absorption.

Default attack cooldown is 2 seconds; the Machine Gun Tower uses 1.8 seconds. This is a new continuous pacing default, independent of the legacy movement time baseline and tick interval. Reducing per-hit damage does not mean half the old turn-based DPS. Shield generators retain 40 shield, two baseline rounds of lifetime/cooldown in seconds; EMP lasts one baseline round of battle time. Preparation suspends these timers and does not heal/reset shields.

Automated checks cover all mobile types, sequential route traversal, speed-4 complete-route time, odd-damage carry, shield absorption, unchanged tower hits, troop/tower destruction, repeated base attacks, simultaneous elimination and persisted winner results.
