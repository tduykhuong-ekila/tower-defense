# Team upgrades, quiz countdown and vegetation audit

Audited 2026-10-24 before implementation. Existing application: Django 5.1 / Django REST Framework / Channels, PostgreSQL in deployment, Redis channel layer, React 18 / TypeScript / Zustand / Phaser 3. The local checkout has no Git metadata or AGENTS.md.

## Existing authority and balance

`apps/units/seeds.py` defines six types. `apps/combat/balance.py` applies current live-combat conversions; raw catalog damage is not live troop damage.

| Code | Category | Base HP | Catalog damage | Continuous damage / hit | Range (hops) | Speed multiplier | Deploy cost |
|---|---|---:|---:|---:|---:|---:|---:|
| infantry | UNIT | 80 | 10 | 5 | 1 | 5.5 | 15 |
| tank | UNIT | 110 | 25 | 12.5 with fractional carry | 1 | 4 | 35 |
| artillery | UNIT | 80 | 40 | 20 | 1.5 | 5 | 45 |
| mg_tower | TOWER | 100 | 15 | 15 | 2 | 0 | 25 |
| cannon_tower | TOWER | 150 | 30 | 30 | 2 | 0 | 40 |
| shield_generator | TOWER | 100 | 0 | 0 | 0 | 0 | 30 |

Default attack interval: 2 seconds, Infantry divided by 1.5 (1.333 seconds). Speed is converted from graph movement using reference hop length 80 / movement baseline round seconds 30. Entity range can be snapshotted in simulation_state and must remain unchanged by upgrades. Shield generators grant 40 base shield with their existing cooldown. UnitType.save normalizes mobile HP; no changes to that baseline are needed.

The normal economy starts with 100 team coins, provides 10 passive income per round, and rewards correct answers with 30 coins or one unlock. Older explicitly configured 20-coin rooms retain their own reward snapshot. Infantry and machine gun towers start unlocked; four other types require TeamUnlock. Infantry is uncapped subject to coins; other troops and towers retain configured capacity limits, six tower positions per team.

## Systems reused

- GameEntity already has `level`, HP, status and durable simulation_state. Previously only individual towers could reach level 2 for 25 coins and +25% damage. There was no team-type upgrade model.
- GameAction is unique on (team, idempotency_key). EconomyService records ledger entries and coin events. MatchService publishes persisted, sequenced events after commit.
- Deployment, construction, legacy round resolution and ContinuousCombatService.tick acquire the match row lock before team/entity changes. This is the shared serialization boundary for new upgrades.
- RealtimeService builds locked snapshots. MatchStore projects events; BattleScene keeps an entity registry, pooled Infantry, motion interpolation and health bars.
- Existing artwork is original project SVGs, 20 team colors and four Infantry walk frames. There were no level-specific equipment assets. React artwork and Phaser textures can use matching generated SVG variants.
- The current HUD uses illustrated arsenal cards, selected details, hover/pinned EntityInfoCard, a compact command dock and separate quiz/reward dialogs.

## Quiz and scenery findings

TeamQuestion already separates timer status, remaining_ms, expires_at, question status and rewards. QuestionService already prevents GET/reconnect/expiry from progressing; NEXT acknowledges a question ID. However viewing leases caused CLOSE and disconnection to pause the clock, and BattlePage advanced terminal questions when reopening them. Both behaviors require replacement.

Terrain uses server graph projection, deterministic grass/river/bridges, negative-origin expanded camera bounds and sparse decorations confined to the original arena. The old perimeter tree loop is already removed. Natural vegetation can use existing tree-0/1/2, bush and rock SVGs, with seeded clusters throughout expanded terrain and explicit exclusion zones. Decorative sprites have no physics or input handlers.
