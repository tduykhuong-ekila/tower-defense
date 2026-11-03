# CODEX IMPLEMENTATION PROMPT
# Tower Defense: Protect the Base — Scale Multiplayer Arena from 4 to 20 Teams

**Target model:** GPT-6.1 Sol — Extra High  
**Project type:** Existing multiplayer 2D Tower Defense game  
**Task:** Extend the existing playable 4-team arena to support up to 20 competing teams in one match  
**Priority:** Preserve existing functionality, gameplay rules, visual quality, and server-authoritative architecture.

---

# 1. ROLE & MISSION

You are a Senior Multiplayer Game Engineer, Phaser 3 Specialist, Backend Architect, Game Systems Designer, and Performance Optimization Engineer.

The existing Tower Defense: Protect the Base project has already been implemented with an interactive 2D cartoon battlefield inspired by Kingdom Rush.

Currently, the game supports a maximum of 4 competing teams.

Your mission is to **extend the existing implementation to support configurable multiplayer matches with up to 20 competing teams simultaneously**.

This is an enhancement to an existing project, NOT a request to rebuild the game.

You must inspect the actual repository, understand its current implementation, identify all assumptions that limit the game to 4 teams, and implement the changes necessary to support up to 20 teams.

Do not stop at an implementation plan. Implement and test the changes.

## Core objectives

1. Support 2–20 teams in a single match.
2. Preserve existing 4-team matches.
3. Dynamically generate or select battle arenas appropriate to the configured team count.
4. Support 20 independently controlled bases.
5. Allow every active team to attack other valid teams.
6. Keep the graphical battlefield interactive, readable, and visually attractive.
7. Optimize Phaser rendering for a larger number of troops, towers, and effects.
8. Maintain consistent game state across multiplayer clients.
9. Preserve existing coin, unlock, question, combat, and victory rules unless changes are necessary and explicitly documented.
10. Prevent unfair spawn positions, unreachable bases, and server-side performance bottlenecks.

**Critical principle:** Increasing the team count must not introduce 20 independent copies of the existing 4-team map.

The game needs a coherent multi-team battlefield architecture.

---

# 2. TERMINOLOGY & EXISTING GAME RULES

Distinguish carefully between:

- **Participant:** Individual connected player.
- **Team:** A group of participants sharing one base, coin balance, unlock state, and game actions.
- **Base:** A team's defensive headquarters.
- **Match:** A game session involving multiple competing teams.
- **Arena:** Shared battlefield hosting the match.
- **Lane:** A route through which units travel.
- **Node:** A logical movement or placement location.
- **Game entity:** A troop, tower, base, projectile state, or other supported game object.

The user requests support for **up to 20 competing teams**, with one base per team, while preserving mentor–mentee team functionality.

If the repository currently uses a one-player-per-team model, identify and document this distinction. Do not unnecessarily redesign team membership.

## Preserve these existing gameplay rules

- Teams answer questions to receive rewards.
- Correct answers allow choosing between coins and unlocking a unit or structure.
- Receiving coins grants exactly **20 coins per correctly answered question**.
- Each team's question reward can be claimed only once.
- Unlocking is free; deployment or construction requires coins.
- No Action Token system.
- Coin balances and unlock states are team-scoped.
- Combat remains server-authoritative.
- Existing phase, timer, and round mechanics remain in effect.
- Existing win conditions and scoring are preserved unless they fail under the expanded format.

Do not replace the existing gameplay with a new game mode without justification.

---

# 3. PHASE 0 — COMPLETE CODEBASE AUDIT

Before editing code, inspect:

- Frontend framework and its existing organization.
- Phaser scenes.
- Game object managers.
- Map renderer.
- Camera system.
- Interaction system.
- Deployment logic.
- Tower construction logic.
- Combat playback logic.
- WebSocket event processing.
- Backend match models.
- Team and participant models.
- Match creation APIs.
- Match serialization.
- Match state lifecycle.
- Combat engine.
- Pathfinding or graph-based routing.
- Coin and reward systems.
- Scoring and win conditions.
- Tests and fixtures.
- Game configuration and environment variables.

Search the entire project for hardcoded assumptions such as:

```text
MAX_TEAMS = 4
team_count <= 4
range(4)
teams.slice(0, 4)
teamColors[teamIndex]
basePositions[teamIndex]
spawnPoints[teamIndex]
fixedArena4
team_1 / team_2 / team_3 / team_4
```

Also look for equivalent assumptions in:

- Python loops.
- TypeScript types.
- Validation schemas.
- Database constraints.
- Phaser object factories.
- API serializers.
- CSS grid layouts.
- Frontend HUD panels.
- Game initialization.
- Team elimination logic.
- Match results and rankings.
- Spectator UI.
- Test data.

Do not blindly replace all occurrences of the number 4.

Some values may describe unrelated gameplay constraints.

## Deliverable

Create:

`docs/ARENA_20_TEAMS_AUDIT.md`

Document:

1. Current limitations.
2. Existing map structure.
3. Current team-count constraints.
4. Data model compatibility.
5. Backend changes required.
6. Frontend changes required.
7. Potential performance bottlenecks.
8. Backward compatibility risks.
9. Proposed implementation order.

Then proceed with implementation.

---

# 4. CONFIGURABLE MATCH CAPACITY

Remove hardcoded 4-team assumptions.

Use configurable match limits.

Proposed configuration:

```ts
const ARENA_CONFIG = {
  MIN_TEAMS: 2,
  MAX_TEAMS: 20,
  DEFAULT_TEAMS: 4,
};
```

Adapt these constants to the current project conventions.

## Match creation

Allow the match host to configure the number of teams.

Supported values:

- 2 teams
- 3 teams
- 4 teams
- ...
- 20 teams

Do not restrict implementation to multiples of four.

Examples to validate:

- 4 teams
- 5 teams
- 7 teams
- 8 teams
- 12 teams
- 16 teams
- 19 teams
- 20 teams

## Lobby

Lobby must display:

- Current number of teams.
- Maximum allowed teams.
- Team name.
- Team color.
- Members.
- Ready status, if supported.
- Match capacity.

Example:

```text
Tower Defense Lobby

Teams: 17 / 20

Team 01 — Ready
Team 02 — Ready
Team 03 — Ready
...
Team 17 — Waiting

[Create Team] [Join Team]
```

Respect existing permissions for creating teams, joining teams, and starting matches.

## Start validation

Before starting a match, validate:

- Team count within configured limits.
- Every participating team has a valid base assignment.
- Spawn positions are unique.
- Every active team has valid movement routes.
- Team ownership configuration is valid.
- Required map resources have loaded or are available.
- Existing start conditions are satisfied.

Return clear backend errors if validation fails.

---

# 5. DYNAMIC ARENA ARCHITECTURE

## 5.1 Main problem

The current 4-team map may contain exactly four fixed bases and a limited road network.

Placing 20 bases on the same map is not acceptable if it causes:

- Overlapping bases.
- Unreachable positions.
- Excessive visual clutter.
- Unfair travel distances.
- Invalid tower placement.
- Spawn trapping.
- Unbalanced attack opportunities.

Introduce a scalable arena layout strategy.

## 5.2 Recommended arena model

Use a **radial multi-region battlefield with a central shared conflict area**, or adapt an existing graph-based map if it provides better backward compatibility.

Suggested structure for 20 teams:

- One shared arena.
- Up to 20 team base regions.
- An interconnected road network.
- Multiple attack routes.
- Central strategic connections.
- Controlled spawn and tower placement locations.
- Organic forest, grass, road, river, and bridge visuals.

Use five logical regions with up to four bases per region as a possible default for 20 teams.

These are logical sectors, not isolated sub-matches.

Every team must remain part of the same multiplayer match.

## 5.3 Map concept

```text
                    NORTH REGION
                   T01 T02 T03 T04
                         |
              +----------+----------+
              |                     |
        NORTHWEST REGION      NORTHEAST REGION
          T17 T18 T19 T20       T05 T06 T07 T08
              |                     |
              +---- CENTRAL HUB ----+
              |                     |
        SOUTHWEST REGION      SOUTHEAST REGION
          T13 T14 T15 T16       T09 T10 T11 T12
              |                     |
              +----------+----------+
```

This is a logical concept, not a mandatory geometric map.

The graphical map should have organic curved paths, forests, roads, and environmental decorations.

Do not simply draw straight lines connecting twenty rectangles.

## 5.4 Preserve visual quality

The expanded arena must follow the existing game's hand-drawn cartoon art direction:

- Detailed forest.
- Grass variations.
- Curved roads.
- Water and bridges where appropriate.
- Stone bases.
- Defensive towers.
- Cartoon troops.
- Soft shadows.
- Animated combat.
- Readable team indicators.

The result should resemble one coherent, professionally designed Tower Defense battlefield.

Avoid creating an empty giant terrain with randomly distributed bases.

## 5.5 Different team counts

Implement an arena strategy that supports varying team counts.

Preferred approach:

- Reuse the existing 4-team arena for small matches if compatible.
- Use medium arena configurations for intermediate team counts.
- Use a large arena configuration for 13–20 teams.

The exact capacity thresholds should be determined from actual map dimensions and gameplay constraints, not arbitrary hardcoding.

Possible profiles:

```ts
type ArenaProfile =
  | "SMALL"
  | "MEDIUM"
  | "LARGE";
```

Each profile should define:

- Supported team count range.
- Base slots.
- Spawn points.
- Paths.
- Tower slots.
- Visual map dimensions.
- Camera boundaries.
- Region metadata.

Do not require an individually hardcoded map for every number from 2 through 20.

## 5.6 Deterministic arena assignment

Arena generation or slot assignment must be deterministic.

Given:

- Match ID.
- Arena configuration.
- Team count.
- Stable seed where appropriate.

The same inputs must produce the same layout or base assignment.

Do not let individual frontend clients independently generate different authoritative layouts.

Prefer backend-generated or backend-selected arena configuration.

Clients should receive authoritative map configuration and render it.

---

# 6. BASE PLACEMENT & TEAM OWNERSHIP

Every participating team requires:

- One unique base.
- One valid base position.
- Unique team identifier.
- Recognizable ownership indicator.
- Base HP.
- Spawn access.
- Defensible build locations.
- Valid routes to opponents.

## Base placement requirements

- No overlapping bases.
- No bases located on impassable terrain.
- No bases disconnected from the movement graph.
- No immediate spawn trapping.
- Comparable starting access to strategic routes.
- No unintended base placement inside another team's controlled area.

## Ownership indicators

With 20 teams, colors alone are insufficient.

Use:

- Team color.
- Team number.
- Team abbreviation or name.
- Distinctive banner/flag.
- Selection highlight.

Colorblind users must still be able to identify teams.

Do not rely exclusively on hue.

## Team colors

Create 20 distinguishable combinations of:

- Color.
- Symbol.
- Label.

Avoid using twenty visually similar shades.

Use readable ownership markers and labels at multiple zoom levels.

## Base interaction

Clicking a base must show:

- Team name.
- Team number.
- Base HP.
- Shield status.
- Elimination status.
- Relevant attack/inspection actions.

Permission-sensitive actions must respect the current user's team.

---

# 7. MOVEMENT NETWORK & ATTACK ROUTING

This is a critical architectural requirement.

The 20-team game must not allow only neighboring teams to fight unless such a restriction is already defined by the GDD.

Every active team must have a valid path to every other active team's base.

## 7.1 Graph-based routing

Represent the logical movement network using nodes and edges.

Example:

```ts
interface ArenaNode {
  id: string;
  x: number;
  y: number;
  type: "ROAD" | "BASE" | "SPAWN" | "JUNCTION";
}

interface ArenaEdge {
  from: string;
  to: string;
  weight: number;
}
```

Adapt to existing models where possible.

The game should support:

- Team spawn nodes.
- Base destination nodes.
- Shared junctions.
- Multiple possible paths.
- Movement constraints.
- Valid target selection.

## 7.2 Pathfinding

Reuse the existing movement algorithm when possible.

If missing, implement a suitable graph-routing algorithm such as Dijkstra or A*.

However:

- Do not add unnecessary continuous physics navigation.
- Preserve the existing node-based movement rules.
- Do not compute authoritative movement independently on the client.
- Do not force every unit to re-run pathfinding every animation frame.

Use cached routes when safe and invalidate them when topology changes.

## 7.3 Attack target selection

When deploying an attacking troop, the player should be able to select an enemy base if existing game rules support target selection.

Suggested interaction:

1. Select troop.
2. Select valid deployment point.
3. Select enemy target base.
4. Preview intended path.
5. Display expected coin cost.
6. Confirm deployment.
7. Send command to backend.
8. Backend validates route and action.
9. Server creates the unit with destination metadata.
10. Clients animate troop movement.

For 20 teams, target selection must be convenient.

Provide:

- Click-on-enemy-base targeting.
- Searchable or scrollable team list.
- Highlight selected destination.
- Path preview.
- Invalid target feedback.

Do not allow targeting your own base unless a specific defensive mechanic permits it.

## 7.4 Routing fairness

Calculate and inspect:

- Shortest path between bases.
- Maximum travel distances.
- Average travel distance.
- Number of available paths.
- Network connectivity.
- Potential chokepoints.
- Region advantages.

Avoid major structural disadvantages based solely on spawn position.

If different routes have significantly different distances, introduce a fair assignment strategy or rebalance the graph.

Do not silently modify existing movement speed or unit costs to compensate.

Document balance decisions.

---

# 8. PHASER RENDERING FOR 20 TEAMS

The expanded map will have more entities than the current implementation.

Optimize the renderer.

## 8.1 Dynamic entity registry

Use stable entity IDs.

Suggested structure:

```ts
Map<string, GameEntityView>
```

Do not track entities using fixed arrays indexed from 0 to 3.

Support dynamic:

- Bases.
- Troops.
- Vehicles.
- Towers.
- Projectiles.
- Damage effects.
- Team indicators.

## 8.2 Incremental updates

When receiving server state updates:

- Create newly added entities.
- Update existing entities.
- Remove deleted entities.
- Avoid recreating the entire scene.
- Avoid rebuilding the whole map after a coin update.
- Avoid reloading all textures on every round.

Implement reconciliation by entity ID.

## 8.3 Rendering optimization

Use:

- Texture atlases.
- Sprite reuse.
- Object pooling.
- Camera culling.
- Depth sorting.
- Particle limits.
- Animation reuse.
- Event batching.
- Efficient entity lookup.

Pay special attention to troop crowding near the central junction.

## 8.4 Level of Detail

Introduce zoom-aware presentation where useful.

At low zoom:

- Simplify HP bars.
- Hide minor decoration labels.
- Reduce particle density.
- Show grouped team indicators.
- Preserve strategic visibility.

At medium zoom:

- Show troops, towers, and HP indicators.
- Show important attack effects.

At high zoom:

- Show detailed sprites.
- Show entity selection.
- Show attack ranges.
- Show damage indicators.

Do not make gameplay information disappear in a way that creates unfair information asymmetry.

## 8.5 Camera

Implement or update:

- Pan.
- Zoom.
- Fit whole arena.
- Focus on own base.
- Focus on selected enemy base.
- Focus on combat.
- Reset camera.

Ensure that users can efficiently navigate a large map.

## 8.6 Minimap

For 20 teams, implement an interactive minimap.

Minimap must show:

- Arena boundaries.
- Team bases.
- Eliminated bases.
- Own base.
- Camera viewport.
- Selected destination.
- Major combat activity where available.

Interactions:

- Click minimap to pan camera.
- Highlight selected team.
- Navigate to base.

Do not render a second full Phaser scene at full detail just to implement the minimap.

Prefer a simplified minimap renderer.

---

# 9. UI/UX FOR 20 TEAMS

A four-team HUD will not scale automatically to twenty teams.

## 9.1 Team scoreboard

Implement a compact team scoreboard.

Each row:

- Team number.
- Team name.
- Ownership marker.
- Base HP.
- Score.
- Alive/eliminated status.

Provide:

- Collapsible panel.
- Scrollable list.
- Team search.
- Sort by score.
- Sort by remaining HP.
- Highlight own team.
- Click to focus base.

Do not occupy half the battlefield permanently.

## 9.2 Team selector

Attack target selection must work for twenty teams.

Provide a target selector with:

- Team labels.
- Alive/eliminated indicators.
- Distance or path metadata if available.
- Search.
- Confirmation feedback.

Do not expose unavailable or invalid targets as actionable.

## 9.3 Battlefield labels

At an overview zoom, show team number or short names above bases.

Avoid rendering lengthy labels for every troop.

Team identification should prioritize bases and selected units.

## 9.4 Match host panel

Host should be able to:

- Configure maximum teams up to 20.
- See all participating teams.
- See join/ready status.
- Start match according to existing rules.
- Monitor alive/eliminated teams.
- View match status.
- End or pause match if host controls already support it.

Do not introduce host privileges to normal players.

## 9.5 Results screen

The results screen must support up to twenty teams.

Show:

- Ranking.
- Team name.
- Score.
- Bases destroyed.
- Remaining HP.
- Correct answers.
- Relevant match statistics.
- Winner.

Preserve existing scoring semantics.

Use a scrollable table or responsive list rather than forcing all twenty cards onto one screen.

---

# 10. SERVER-SIDE SCALING

Backend must support twenty teams without fixed team assumptions.

## 10.1 Data model

Check whether existing models support:

- Dynamic team count.
- Dynamic base assignment.
- Arbitrary enemy targets.
- Team-scoped resources.
- Multiple concurrent actions.
- More game entities.
- Larger match event streams.

Prefer extending current models rather than replacing them.

## 10.2 Combat engine

Review:

- Turn processing.
- Unit movement.
- Tower targeting.
- Damage calculation.
- Base destruction.
- Elimination.
- Score updates.
- Victory checks.

Ensure loops operate on active teams and entities rather than fixed four-team structures.

## 10.3 Deterministic combat

Preserve deterministic server-side combat.

For simultaneous actions, define a stable ordering or a well-defined simultaneous resolution policy.

Do not use frontend animation order to determine damage.

## 10.4 Transactional economy

Coin spending must remain atomic.

Two concurrent deployment requests must not overspend the team balance.

The reward system must prevent duplicate claims.

Retain the rule:

**Correct answer + choose coins = +20 team coins, once per team's question.**

## 10.5 Database performance

Review:

- Query counts per round.
- N+1 queries.
- Match state serialization.
- Entity retrieval.
- Team leaderboard computation.
- Event history storage.
- Connection handling.

Add indexes or query optimizations only when justified.

Avoid making twenty separate database reads for data that can be retrieved in one query.

## 10.6 Round resolution

Measure the execution time of combat resolution with:

- 4 teams.
- 8 teams.
- 12 teams.
- 16 teams.
- 20 teams.

Test realistic and near-capacity entity counts.

Ensure one round is resolved once, even under retries or concurrent worker execution.

## 10.7 Concurrent client support

Do not assume twenty teams means twenty concurrent connected users.

If each team contains multiple mentor–mentee participants, the number of WebSocket connections may be much larger.

For load testing, assume at least:

- 20 competing teams.
- 2–4 participants per team.
- Up to 80 active participants.
- Additional spectators where currently supported.

This is a testing workload, not a requirement to change team membership rules.

---

# 11. REALTIME SYNCHRONIZATION

## 11.1 Event scope

All clients should receive the shared game events permitted by existing visibility rules.

Events must include enough information to identify:

- Match.
- Team.
- Entity.
- Event type.
- Sequence.
- Relevant state change.

## 11.2 State snapshots

Implement efficient initial and reconnect snapshots.

Avoid transmitting unnecessary rendering data if it can be derived from a shared map definition.

Separate:

- Static arena definition.
- Dynamic game state.
- Transient combat animation events.

## 11.3 Ordering and idempotency

Handle:

- Duplicate commands.
- Duplicate server events.
- Out-of-order delivery.
- Temporary disconnects.
- Reconnection.
- Missing event sequences.
- Stale match snapshots.

Use existing event sequence mechanisms where available.

## 11.4 Network optimization

Evaluate whether the current protocol sends full game state after every small change.

If so, consider:

- Incremental state events.
- Snapshot plus deltas.
- Event batching.
- Reduced redundant payloads.

Maintain correctness before optimizing.

Do not implement complex compression unless profiling proves it necessary.

---

# 12. GAME BALANCING FOR 20 TEAMS

Twenty-team combat can become chaotic.

Review existing game balance without arbitrarily replacing the GDD.

Potential issues:

- Early focus-fire elimination.
- Spawn position advantage.
- Units spending excessive rounds traveling.
- Central route congestion.
- Very long matches.
- Snowballing from early eliminations.
- Excessive towers at chokepoints.
- Too many simultaneous attacks against one base.

## Required analysis

Evaluate:

- Time to first attack.
- Average travel distance.
- Average survival time.
- Number of attacks per round.
- Match length.
- Base elimination rate.
- Dominance of central positions.

If changes are necessary, prefer configurable parameters.

Examples of optional adjustments:

- Arena-specific movement scaling.
- Balanced spawn regions.
- Alternative routes.
- Maximum active units per team.
- Existing tower limits.
- Round duration adjustments.

Do not add these changes without documenting the effects.

Do not introduce unrelated mechanics or new currencies.

---

# 13. ELIMINATION & VICTORY

The game must handle twenty participating teams.

## Elimination

When a team's base is destroyed:

- Mark the team eliminated.
- Stop its prohibited gameplay actions.
- Preserve match statistics.
- Update all clients.
- Update scoreboard.
- Update target selection availability.
- Handle active units according to existing GDD rules.
- Transition eliminated members to spectator behavior where supported.

## Victory

Preserve existing rules:

- Last surviving team wins when applicable.
- If the configured match timer expires, calculate ranking using existing scoring rules.

Validate:

- Multiple base destructions in the same round.
- Simultaneous elimination of the last remaining teams.
- Timeout with several surviving teams.
- Tied scores.
- Disconnected teams.
- Teams with no active units.
- Delayed combat event delivery.

Do not declare victory simply because a client visually plays an explosion.

Only backend-confirmed match state determines victory.

---

# 14. SECURITY & SERVER AUTHORITY

All important validations must occur on backend.

Validate:

- Match membership.
- Team membership.
- Participant permissions.
- Action eligibility.
- Available coins.
- Unlock state.
- Deployment position.
- Tower slot.
- Target team.
- Target base.
- Route validity.
- Match phase.
- Elimination state.
- Duplicate command IDs.

Do not trust:

- Client coin values.
- Client team IDs without authentication.
- Client damage values.
- Client entity ownership.
- Client-generated combat outcomes.

Prevent a participant in Team 01 from controlling Team 20.

Maintain existing host and spectator access restrictions.

---

# 15. BACKWARD COMPATIBILITY

The new implementation must not break existing four-team matches.

Required compatibility:

- Existing map configuration.
- Existing saved match data where supported.
- Existing API consumers.
- Existing multiplayer events where feasible.
- Existing unit and tower mechanics.
- Existing reward rules.
- Existing score calculations.
- Existing host controls.

Prefer versioned arena configurations if the new map data structure differs significantly.

Avoid data migrations that invalidate existing match history.

---

# 16. AUTOMATED TESTING

Create or extend tests.

## Match capacity

- Create 2-team match.
- Create 4-team match.
- Create 5-team match.
- Create 8-team match.
- Create 12-team match.
- Create 16-team match.
- Create 19-team match.
- Create 20-team match.
- Reject 21-team match.
- Reject duplicate base assignments.

## Arena validity

For each supported capacity:

- Exactly one base per team.
- No duplicate spawn positions.
- No overlapping base placements.
- Every base reachable from every other base under allowed routing rules.
- Every team has valid tower placement options.
- All assigned base IDs are unique.
- Deterministic layout generation.
- No disconnected graph components.

## Economy

- Team balances remain independent.
- Correct answer coin reward grants exactly 20.
- Duplicate claims do not grant more coins.
- Concurrent spending does not overspend.
- Team unlock state remains independent.

## Combat

- Units can attack valid enemy bases.
- Movement follows valid graph routes.
- Tower attack range remains correct.
- Twenty-team damage processing is consistent.
- Multiple simultaneous eliminations are handled.
- Victory is determined correctly.
- Existing four-team combat tests still pass.

## Realtime

- Twenty teams receive synchronized updates.
- Reconnect restores correct state.
- Event replay does not duplicate entities.
- Camera and UI state do not alter gameplay.
- Multiple members of one team see identical team resources.

## Rendering

- All twenty bases appear.
- All base indicators are readable.
- Camera can reach every base.
- Minimap contains all active bases.
- Selection works at different zoom levels.
- No sprite duplication after updates.
- No memory leaks after leaving and rejoining matches.

---

# 17. PERFORMANCE & LOAD TESTING

Create a reproducible performance benchmark.

## Scenarios

| Scenario | Teams | Connected players | Test objective |
|---|---:|---:|---|
| Baseline | 4 | 8 | Regression |
| Small | 8 | 16 | Intermediate scaling |
| Medium | 12 | 24 | Combat and rendering |
| Large | 16 | 48 | High concurrency |
| Maximum | 20 | 80 | Capacity validation |

Also test spectator connections if supported.

## Performance measurements

Backend:

- Match initialization time.
- Round resolution duration.
- Database query count.
- WebSocket event throughput.
- Snapshot serialization size.
- CPU and memory usage.

Frontend:

- Average FPS.
- Frame-time spikes.
- Sprite count.
- Texture memory.
- Combat playback delay.
- Camera interaction responsiveness.

Network:

- Average event payload size.
- Event processing latency.
- Reconnect restoration time.

## Initial targets

Aim for:

- 60 FPS on a typical modern desktop.
- Acceptable degradation on weaker devices.
- No persistent server/client state divergence.
- No duplicate reward claims.
- No lost actions after confirmed server execution.
- Combat round resolution within the configured round-processing budget.

Do not claim performance goals have been achieved without actual benchmark results.

Record hardware and test conditions.

---

# 18. IMPLEMENTATION PHASES

## PHASE 0 — Audit

- Inspect repository.
- Identify hardcoded four-team assumptions.
- Document architecture.
- Confirm backend and frontend contracts.

Deliverable:

`docs/ARENA_20_TEAMS_AUDIT.md`

## PHASE 1 — Dynamic Team Capacity

- Implement configurable 2–20 team capacity.
- Update match creation.
- Update lobby.
- Update validators.
- Update backend initialization.
- Add capacity tests.

Acceptance:

Twenty teams can join and start one match without duplicate assignments.

## PHASE 2 — Scalable Arena

- Implement arena profiles or equivalent strategy.
- Support twenty bases.
- Implement deterministic base assignment.
- Expand route graph.
- Add spawn and tower placement metadata.
- Validate reachability and fairness.

Acceptance:

A valid twenty-team arena exists and every team can reach every opposing base.

## PHASE 3 — Phaser Battlefield Rendering

- Render large map.
- Render twenty bases.
- Render dynamic entities.
- Implement camera controls.
- Implement minimap.
- Implement team ownership indicators.
- Add viewport/LOD optimizations.

Acceptance:

All twenty bases render correctly and can be inspected or selected.

## PHASE 4 — Combat & Interaction

- Update deployment flow.
- Update enemy target selection.
- Update route validation.
- Update combat engine to support twenty teams.
- Preserve economy.
- Preserve game phases.
- Handle elimination and victory.

Acceptance:

A twenty-team match can progress through a complete combat cycle.

## PHASE 5 — Multiplayer & UI

- Expand scoreboard.
- Expand lobby.
- Add team selection.
- Update host controls.
- Optimize state synchronization.
- Test reconnection.
- Update results screen.

Acceptance:

Players from different teams observe consistent shared match state.

## PHASE 6 — Optimization & QA

- Benchmark.
- Profile backend.
- Profile Phaser rendering.
- Fix performance bottlenecks.
- Verify existing four-team functionality.
- Test a complete twenty-team match.
- Update documentation.

Acceptance:

The system is playable and stable under a realistic twenty-team test workload.

---

# 19. DOCUMENTATION DELIVERABLES

Create or update:

```text
docs/
├── ARENA_20_TEAMS_AUDIT.md
├── ARENA_SCALING_ARCHITECTURE.md
├── ARENA_MAP_FORMAT.md
├── MULTIPLAYER_20_TEAMS.md
├── ARENA_PERFORMANCE_REPORT.md
└── ARENA_20_TEAMS_IMPLEMENTATION.md
```

Explain:

- How match capacity is configured.
- How arena profile selection works.
- How bases are assigned.
- How paths are defined.
- How to add a new arena.
- How attack target selection works.
- How Phaser renders large maps.
- How multiplayer snapshots and events work.
- How to run the twenty-team benchmark.
- Known limitations and remaining risks.

---

# 20. DEFINITION OF DONE

The implementation is complete when:

- [ ] A match can be configured for up to twenty teams.
- [ ] Twenty teams can join the same match.
- [ ] Every team has one unique base.
- [ ] The arena supports all twenty bases without overlap.
- [ ] Every team has a valid attack route to every other active team.
- [ ] Existing four-team matches continue working.
- [ ] All twenty bases render correctly in Phaser.
- [ ] Users can navigate the expanded map.
- [ ] Players can select enemy targets.
- [ ] Players can deploy troops and build towers.
- [ ] Server-side coin spending remains correct.
- [ ] Question rewards remain claimable only once.
- [ ] Combat results are calculated server-side.
- [ ] Animation playback works with twenty-team battles.
- [ ] Eliminated teams are handled correctly.
- [ ] Victory and ranking are calculated correctly.
- [ ] The lobby and scoreboard support twenty teams.
- [ ] Multiplayer reconnection works.
- [ ] Automated tests cover 2–20 team capacities.
- [ ] A full twenty-team gameplay test has been completed.
- [ ] Performance measurements are documented.
- [ ] Existing gameplay and graphics have not regressed.

---

# 21. IMPORTANT CODING INSTRUCTIONS

1. Inspect the current codebase before implementation.
2. Preserve existing architecture whenever practical.
3. Do not rewrite completed Phaser graphics unnecessarily.
4. Do not remove or simplify current animations.
5. Do not replace the current game with a static mockup.
6. Do not introduce a separate disconnected twenty-team demo.
7. Do not hardcode exactly twenty teams everywhere; support a configurable range.
8. Do not assume teams have exactly one player.
9. Do not duplicate coin or combat logic in the frontend.
10. Do not create twenty independent mini-games.
11. Do not change existing scoring rules without justification.
12. Prefer data-driven arena configuration.
13. Use deterministic server-side map assignment.
14. Ensure game actions are transactionally safe.
15. Avoid unnecessary new dependencies.
16. Follow repository coding conventions.
17. Add tests for critical new functionality.
18. Run existing regression tests.
19. Report incomplete requirements accurately.
20. Do not claim successful load testing without measured results.

---

# 22. EXECUTION DIRECTIVE

Start immediately by auditing the existing repository.

Focus on