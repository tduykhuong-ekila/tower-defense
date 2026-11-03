# Team-wide upgrade design

Each Team belongs to one Match. `TeamUnitUpgrade(team, unit_type)` therefore uniquely identifies a match/team/type upgrade. Database uniqueness and level 1–4 constraints enforce ownership and bounds. Missing rows mean level 1. All six existing types are eligible; additional catalog TOWER types may use the same rules and fallback art.

## Balance

The canonical base values are recorded in TEAM_UPGRADE_QUIZ_MAP_AUDIT.md. Upgrade modifiers apply after existing balance conversions, preserving the 0.5 live troop damage reduction, Infantry 1.5 fire-rate bonus, current movement and range snapshots.

| Level | HP | Damage | Attack rate |
|---|---:|---:|---:|
| 1 | 1.00 | 1.00 | 1.00 |
| 2 | 1.15 | 1.10 | 1.05 |
| 3 | 1.30 | 1.20 | 1.10 |
| 4 | 1.50 | 1.35 | 1.20 |

| Type | 1→2 | 2→3 | 3→4 |
|---|---:|---:|---:|
| Infantry | 50 | 100 | 180 |
| Tank | 80 | 160 | 280 |
| Artillery | 90 | 180 | 320 |
| Any tower | 70 | 140 | 250 |

Tables live in `apps/units/upgrades.py`. Costs may be overridden in a server-owned match configuration's `team_upgrade_costs[unit_code]` array. Prices are deliberately greater than deployment prices: one payment affects unlimited current and future Infantry. These starting prices need live playtesting for long-match pacing.

`effective_stats` calculates max HP with round-half-up, damage, unchanged range/speed, cooldown and inspection values. Continuous troops retain fractional damage carry; towers and legacy round damage retain integer flooring. Continuous cooldown divides the original interval by level attack rate. Legacy round combat has no sub-round fire-rate simulation, so only HP and damage apply there. Shield generator output remains 40 shield; its upgrade increases structural HP and equipment. It gains no active gun.

An alive entity keeps its HP percentage, rounded half up and clamped to 1..new maximum. Destroyed/zero-HP entities are excluded. Motion state, attack target, fractional damage carry and current attack cooldown remain intact. New entities read the team level while holding the match lock.

One `TEAM_UNIT_UPGRADED` event describes type, new level and effective stats. Clients reconcile matching entities without replacing roots or movement tracks. The next snapshot restores exact persisted HP/stats. A durable action plus expected_current_level prevents retry charges, stale teammate requests and skipped levels.
