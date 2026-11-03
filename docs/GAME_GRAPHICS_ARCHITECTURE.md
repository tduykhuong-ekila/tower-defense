# Woodland battlefield architecture

## Ownership

Django remains authoritative for all prices, HP, unlocks, legal actions, graph routing, damage, elimination and victory. React renders the lobby and compact game HUD, contextual information, questions, rewards and host controls. Phaser renders the battlefield and plays the ordered combat log. No rendering code grants coins or computes combat outcomes.

```
REST actions + WebSocket envelopes
              ↓
Zustand matchStore (sequence checks, entity upserts, combat reconciliation)
              ↓
SceneState / SceneCallbacks bridge → Phaser BattleScene
              ↑                          ↓
React action validation ← node / entity / base pointer events
```

`game/bridge.ts` defines the typed boundary. React passes data and commands; it never obtains a Phaser sprite. `PhaserGame.tsx` owns engine lifetime, waits for the scene's own readiness event, uses the latest props, queues combat received during boot and releases the engine/ResizeObserver on unmount.

## Map contract

Additive read-only endpoint: `GET /api/v1/matches/{match_id}/map/`. It returns the existing `GameMap.to_dict()` graph plus `team_ids` in the same `created_at, id` order used by combat. The identical graph is included as `map_data` in WebSocket snapshots. It contains no private economy or question data.

`game/map.ts` projects server x/y coordinates into a 1600 × 1040 woodland world. IDs such as `node_base_t1`, `node_spawn_t1`, and `node_tower_t1_slot3` are preserved. Deployment has one server-selected spawn per team; the UI never submits arbitrary coordinates. Tower placements use `TeamState.valid_tower_slots`. Range previews traverse graph edges in hops, matching combat semantics. Server node IDs are never derived from artwork pixels.

`rendering/terrain.ts` draws a deterministic painted ground texture once per graph. Roads use only passable edges; tower coverage edges are not roads. The river is scenery, with timber bridges at road intersections. Tree, bush, rock, crate and camp sprites are separate scenery objects, depth sorted by world Y. Bases, towers, units, HP and selection visuals are independent of the ground texture.

## State and transactions

The store ignores stale sequenced events, upserts deploy/build entities by ID, accepts server HP, and folds movement, attacks, destruction, shields, income and elimination from `COMBAT_RESOLVED`. Reconnection replaces entities from a fresh snapshot. The socket resets sequence/deduplication state on room changes. REST refreshes that are superseded by a socket event or a newer refresh do not overwrite newer state.

Interaction mode is explicit: `IDLE`, `DEPLOY`, `BUILD`, `INSPECT`, `WAITING`, `COMBAT`, `MODAL`. A synchronous ref locks each transaction before the first await, preventing double-click deployments. Modal/playing/pending/disconnected/spectator states block deployment and construction. Coins update only after server events/responses. Input and backend validation are both retained.

Question-assignment events contain metadata, not complete questions; the UI fetches the existing REST resource. Question/reward snapshots now include the REST serializer schema alongside legacy flattened question fields. Pending reward snapshots no longer reference the nonexistent `UnitType.tier` field. Reward claims remain unique per question; SQLite lock conflicts retry the complete atomic transaction, while PostgreSQL retains row locking. Idempotency keys are scoped to the same team and question.

## Combat playback

BattleScene receives the server event array in order. Movement interpolates between the event's actual nodes; infantry plays four walk frames. Attacks recoil the source, animate a projectile toward the actual target, show impact/damage, then apply server HP. Destruction fades/tilts the corresponding visual. Shields appear/expire from events. New rounds queue while a round is playing. Live state is retained during playback and reconciled afterward; skipping cancels queued playback, clears effects, and renders the latest authoritative state.

## Camera and accessibility

Drag/pinch/scroll act on the camera. Movement over seven screen pixels or a multi-touch gesture prevents a placement click. Fit and own-base controls are available. Mobile initially focuses the own base; team details move into the drawer. React buttons provide keyboard alternatives for deployment/building, and dialogs trap and restore focus. Esc cancels selection or closes the current panel. Audio feedback is optional and synthesized after a user gesture; text feedback is always present.
