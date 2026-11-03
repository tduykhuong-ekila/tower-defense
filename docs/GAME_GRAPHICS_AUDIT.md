# Graphics audit — 2026-10-16

## Existing architecture

React 18 / TypeScript / Vite, Zustand, Phaser 3 (declared ^3.85.2; current lockfile 3.90.0) and Lucide are already installed. Django 5 / DRF / Channels own match phases, fixed-node combat, coins, unlocks, questions and rewards. SQLite is available locally; production uses PostgreSQL and Redis. No replacement framework or database is needed.

## Reuse and refactor

Reuse REST actions, question/reward services, combat engine, session tokens, lobby, host console, results and the WebSocket envelope. Refactor BattlePage, BootScene, BattleScene and their synchronization bridge. Existing textures are generated triangles and squares; there are no illustrated game assets to preserve.

## Defects found

- Frontend has four hardcoded bases, two slots per team and `node-base-alpha` identifiers. Server uses 2–12 radial branches, three slots and `node_base_t1` identifiers. Deployed entities therefore cannot be positioned reliably.
- Phaser initialization listens for game readiness before the battle scene is guaranteed to be created, captures stale React props, and lacks explicit teardown of resize listeners.
- Match store appends duplicate entities, invents HP defaults, and does not apply combat movement/damage/destruction events.
- WebSocket connect overwrites matchId before checking the old connection; changing rooms can keep the previous socket. Sequence and deduplication state survive room changes.
- BattlePage chooses the first team when the viewer has no team, duplicates authoritative state and does not reconcile all combat changes.
- Pending-reward snapshots reference nonexistent `UnitType.tier` and use a different question/reward shape from REST, causing disconnection and malformed modal state.
- Reward modal keeps its processing state after a successful claim, preventing a later question's reward.
- No camera gestures, placement previews, click-versus-drag protection, illustrated entities or proper inspection panel.

## Server capabilities and constraints

The server already supports deploy/build/upgrade/repair/scout/EMP, phase restrictions, atomic economy, one reward per question and deterministic combat. Deployment is at the team's server-selected spawn; arbitrary free placement is not a supported rule. Range is graph hops, not Euclidean pixels. Round resolution requires the existing host/scheduler flow. Pause is host-only. Existing map JSON export is available internally but has no frontend endpoint; expose it additively and include it in snapshots. Enrich deploy/build events with actual entity HP rather than guessing on the client.

## Implementation strategy

First align map IDs and authoritative state, then implement a playable infantry/tower slice using existing actions. Add original illustrated SVG assets, rasterized by Phaser, with layered terrain, forests, river and bridges. Keep React responsible for compact HUD/modals and use a typed bridge for scene commands and pointer events. Add deterministic map tests, real store regression tests and backend integration tests. Verify build and browser interaction against local services. No gameplay or reward rules are changed.
