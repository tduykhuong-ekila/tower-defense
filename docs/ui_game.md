# CODEX IMPLEMENTATION PROMPT
# Tower Defense: Protect the Base — Interactive 2D Game Graphics Overhaul

## 1. ROLE & MISSION

You are a Senior Game Developer, Technical Game Artist, Frontend Architect, and Phaser 3 Specialist.

Your mission is to **redesign and rebuild the existing Tower Defense: Protect the Base game frontend into a visually polished, fully interactive 2D cartoon strategy game**.

The user has provided a reference screenshot showing the desired visual direction.

**The screenshot is the primary visual reference for the art direction, level composition, visual density, camera angle, and gameplay presentation.**

You MUST inspect and understand the current codebase before making architectural decisions.

This is an existing project, NOT a greenfield project.

### Primary goals

1. Replace the current unattractive or static game interface with a visually appealing battlefield.
2. Make battlefield objects interactive using mouse and touch input.
3. Render animated troops, towers, bases, projectiles, and combat effects.
4. Integrate all interactions with the existing backend and game mechanics.
5. Preserve the existing game rules, reward system, coin economy, multiplayer functionality, and gameplay state.
6. Produce a working, playable implementation rather than a static visual mockup.

**Definition of success:** Users can join a match, view a detailed animated battlefield, select and deploy units, construct towers, answer questions, receive rewards, and watch multiplayer combat occur on the game canvas.

---

## 2. REFERENCE IMAGE & ART DIRECTION

### 2.1 Visual reference

Analyze the attached screenshot carefully.

Important visual elements:

- Hand-painted cartoon terrain.
- Top-down 2.5D perspective.
- Organic forests consisting of overlapping tree canopies.
- Winding sandy roads with irregular edges.
- Flowing rivers with bridges.
- Detailed stone towers and defensive buildings.
- Small stylized cartoon soldiers.
- Visible character outlines and soft shadows.
- A colorful, readable battlefield.
- Compact fantasy-style HUD elements.
- Animated combat with projectiles, damage indicators, and impact effects.
- Layered terrain, scenery, structures, and characters.
- A large battlefield occupying most of the screen.

### 2.2 Target visual style

Use:

**Stylized Hand-Drawn Cartoon Fantasy Tower Defense**

Visual principles:

- Rich environmental detail.
- Colorful but harmonious palette.
- Slightly exaggerated proportions.
- Strong visual separation between terrain and playable objects.
- Organic silhouettes instead of rigid flat rectangles.
- Subtle shadows for depth.
- Crisp sprites at native rendering resolution.
- Smooth movement and feedback animations.
- Distinct team colors and ownership markers.

Avoid:

- Plain HTML grids as the battlefield.
- Emoji as final troop or tower graphics.
- Flat geometric shapes as permanent game assets.
- Basic colored circles representing soldiers.
- Generic dashboard aesthetics.
- Large empty areas with no environmental details.
- Full-screen static background images used as fake gameplay.
- Excessive glow, particle effects, or visual clutter.
- Pixel art unless existing approved assets require it.
- Photorealistic or realistic military rendering.

The final result should feel like a small commercial indie game.

### 2.3 Copyright and asset originality

The screenshot is a style reference, not an asset source.

Do not extract, trace, or reproduce copyrighted characters, UI artwork, towers, maps, or sprites directly from the screenshot.

Create or integrate original assets consistent with the desired visual direction.

If a licensed asset pack is used, document its source, license, attribution requirements, and redistribution restrictions.

---

## 3. EXISTING CODEBASE ASSESSMENT

Before implementation, inspect the repository.

Identify:

1. Current frontend framework and version.
2. Existing game UI architecture.
3. Current backend stack.
4. Existing game rules and GDD/PRD documentation.
5. Available REST API endpoints.
6. Existing WebSocket connections and event schemas.
7. Game state management.
8. Existing map data and coordinate systems.
9. Existing assets and their formats.
10. Existing troop, tower, base, question, and reward implementations.
11. Current deployment and combat mechanics.
12. Authentication and multiplayer session handling.

Read the existing project documentation and relevant source code.

Do not assume the codebase follows the proposed structure in this document.

### Required audit deliverables

Create:

`docs/GAME_GRAPHICS_AUDIT.md`

Include:

- Current architecture.
- Components that can be reused.
- Components that should be refactored.
- Missing game interactions.
- Missing backend capabilities.
- Existing asset inventory.
- Known technical constraints.
- Recommended implementation strategy.

### Important restrictions

- Do not rebuild the backend unnecessarily.
- Do not overwrite existing business logic.
- Do not redesign the database unless justified.
- Do not replace the frontend framework without a clear technical reason.
- Do not break currently functioning gameplay features.
- Do not silently invent new game rules or API contracts.
- Prefer incremental migration over a full rewrite.

---

## 4. RECOMMENDED TECHNOLOGY STACK

Use the following stack if compatible with the existing repository.

| Component | Technology |
|---|---|
| Game engine | Phaser 3 |
| UI framework | React + TypeScript |
| Build tool | Vite |
| Game map editor | Tiled |
| Game assets | PNG/WebP sprite atlases |
| UI state | Zustand, if compatible |
| UI animations | GSAP or existing animation solution |
| Audio | Phaser Audio or Howler.js |
| Communication | REST API + WebSocket |
| Backend | Existing backend |
| Persistence | Existing database |
| Multiplayer authority | Backend |

### Why Phaser 3

Phaser should own:

- The battlefield canvas.
- Game scene management.
- Sprites.
- Terrain and tilemaps.
- Render depth sorting.
- Pointer interactions.
- Camera controls.
- Animation playback.
- Particle effects.
- Projectile visualization.
- Sprite selection and targeting.

React should own:

- Lobby.
- Question modal.
- Reward modal.
- Team information.
- Coin counters.
- Unit selection panels.
- Construction panels.
- Match controls.
- Settings and results.
- Accessibility-friendly menus.

### Architecture requirement

React must not directly manipulate Phaser sprites.

Use a dedicated event bridge and game-state synchronization layer.

The backend is authoritative for:

- Coins.
- Unlocks.
- Deployment validity.
- Tower construction.
- Combat damage.
- Base HP.
- Elimination.
- Victory conditions.

Phaser is responsible for rendering and interaction, not authoritative game calculations.

---

## 5. VISUAL DESIGN SYSTEM

### 5.1 Color palette

Suggested environmental colors:

| Element | Colors |
|---|---|
| Grass | #79A94F, #91BD58 |
| Dark grass | #4D7B39 |
| Forest | #426E31, #618E3E |
| Dirt paths | #D9BC72, #E8CD8A |
| River | #4F99BE, #70B7D6 |
| River highlights | #B8E3EF |
| Stone buildings | #85857A, #B5B2A2 |
| Wood | #91663F, #BD8A53 |
| HUD background | #26231F |
| HUD borders | #B9A17A |
| Gold | #FFD166 |
| Danger | #D85F4C |
| Success | #7CC76D |

Treat these as initial design tokens, not mandatory colors.

Team ownership colors must be distinct and readable.

### 5.2 Art style requirements

All primary game objects must follow a consistent visual language:

- Bold but controlled outlines.
- Soft painted shadows.
- Highlights on important objects.
- Strong silhouettes.
- Consistent lighting direction.
- Consistent asset scale.
- Consistent camera projection.

Do not mix photorealistic, flat vector, and hand-painted art styles.

### 5.3 Sprite depth

Use logical rendering layers:

1. Ground terrain.
2. Ground decoration.
3. Road and river.
4. Bridges and environmental structures.
5. Ground shadows.
6. Towers and buildings.
7. Troops and vehicles.
8. Projectiles and combat effects.
9. Floating HP bars and damage text.
10. Interaction highlights and selection indicators.

Ensure units appear in front of or behind objects naturally based on their position.

Use depth sorting by world Y-coordinate where appropriate.

### 5.4 Rendering quality

Requirements:

- Support desktop browsers.
- Support responsive layouts.
- Preserve aspect ratio.
- Account for high-DPI displays.
- Use camera scaling instead of stretching sprites.
- Use texture atlases where appropriate.
- Provide appropriate texture filtering for the selected art style.
- Avoid excessive per-frame object creation.
- Avoid unnecessary React rerenders during Phaser animation frames.

---

## 6. BATTLEFIELD MAP SYSTEM

### 6.1 Goal

Build a detailed battlefield resembling the reference image in overall composition and atmosphere.

The battlefield must not look like a generic website layout.

It should look like a handcrafted strategy-game level.

### 6.2 Environmental elements

Include:

- Grass terrain.
- Multiple grass textures.
- Forest clusters.
- Individual trees.
- Dirt roads.
- Rocks and pebbles.
- Bushes.
- Flowers and environmental decorations.
- River.
- Wooden bridges.
- Wooden signs.
- Crates and barrels.
- Defensive structures.
- Team bases.

Environmental objects must not block the visual readability of playable entities.

### 6.3 Map layout

Use a node-based or lane-based logical battlefield, depending on the existing game rules.

Important:

**Do not invent free-roaming pathfinding if the current GDD defines fixed lanes and node-based movement.**

Visual paths may be curved, but the movement and combat logic must follow valid backend rules.

Separate:

- Visual map coordinates.
- Logical node coordinates.
- Spawn positions.
- Tower placement locations.
- Movement paths.
- Base locations.
- Attack targeting rules.

The map definition should allow multiple teams.

Support the existing 4–8 team game mode where implemented.

### 6.4 Tiled map integration

If suitable, use Tiled for map construction.

Recommended layers:

- Ground.
- Grass details.
- Roads.
- Water.
- Bridges.
- Forest background.
- Forest foreground.
- Decorations.
- Buildings.
- Spawn markers.
- Tower placement markers.
- Movement nodes.
- Base markers.
- Collision or interaction metadata.

Use object layers for metadata rather than encoding gameplay rules into visual pixels.

### 6.5 Map configuration

Avoid hardcoding one map directly into the Phaser scene.

Create a configurable map format that supports:

- Map identifier.
- World dimensions.
- Background layers.
- Lane definitions.
- Spawn locations.
- Tower slots.
- Base coordinates.
- Visual waypoints.
- Team ownership regions.

Prefer compatibility with existing backend map data.

### 6.6 Camera controls

Implement:

- Mouse drag to pan.
- Mouse wheel zoom.
- Touch drag to pan.
- Pinch zoom on supported touch devices.
- Camera movement boundaries.
- Fit-to-arena button.
- Focus-on-team-base button.

Camera input must not accidentally trigger building placement.

Distinguish click/tap from drag.

---

## 7. GAME ENTITIES & ANIMATIONS

### 7.1 Base

Every team has a recognizable base.

Base requirements:

- Distinct structure sprite.
- Team ownership color.
- HP bar.
- Optional shield indicator.
- Selected and unselected states.
- Damage feedback.
- Destruction animation.
- Elimination state.

Interactions:

- Click base to inspect.
- Display owner and HP.
- Display available defensive actions when permitted.
- Show its targeting/defense details if relevant.

### 7.2 Infantry

Required animations:

- Idle.
- Walk.
- Attack.
- Hit.
- Death.
- Spawn.

Infantry should be small, readable, and visually consistent with the screenshot.

It must not be represented by a static icon during normal gameplay.

### 7.3 Tank

Required animations:

- Idle.
- Move.
- Aim.
- Fire.
- Hit.
- Destroyed.

Tank movement must match the combat events provided by the backend.

### 7.4 Artillery

Required animations:

- Idle.
- Aim.
- Fire.
- Projectile flight.
- Explosion.
- Hit.
- Destroyed.

Use stylized cartoon projectiles.

### 7.5 Defensive towers

At minimum support the existing tower types:

- Machine Gun Tower.
- Cannon Tower.
- Shield Generator, if available in the current game.

Each tower should have:

- Idle state.
- Build animation.
- Selection state.
- Attack or activation animation.
- Damage state where relevant.
- Destruction animation.
- A visually distinct silhouette.

### 7.6 Entity visual component structure

Recommended:

- Entity root container.
- Shadow.
- Main sprite.
- Team indicator.
- HP bar.
- Status icons.
- Selection highlight.
- Optional attack range visualization.

Implement reusable visual components rather than duplicating logic across entity types.

---

## 8. FULLY INTERACTIVE GAMEPLAY

### 8.1 Interaction state machine

Use explicit interaction states.

Suggested states:

- IDLE
- SELECTING_UNIT
- SELECTING_DEPLOY_POSITION
- SELECTING_TOWER
- SELECTING_BUILD_SLOT
- INSPECTING_ENTITY
- WAITING_FOR_SERVER
- PLAYING_COMBAT
- QUESTION_OPEN
- REWARD_SELECTION

Only compatible interactions may occur at the same time.

A modal question must not accidentally allow battlefield deployment underneath it.

### 8.2 Unit deployment

Player flow:

1. Player opens the troop panel.
2. Player selects an unlocked troop.
3. Game highlights valid spawn positions.
4. Player moves the pointer over the battlefield.
5. Show a translucent ghost preview.
6. Valid positions appear highlighted.
7. Invalid positions show a warning indicator.
8. Player clicks or taps a valid deployment position.
9. Show a confirmation/transaction pending state if needed.
10. Send the deployment command to backend.
11. Wait for server acknowledgment or state event.
12. Show spawn animation only after server confirms.
13. Update coin counter from authoritative state.

Display:

- Troop name.
- Deployment cost.
- Current coins.
- HP.
- Damage.
- Movement.
- Range.

If coins are insufficient:

- Disable the deployment action.
- Show a readable message.
- Do not modify backend state.
- Do not render a committed troop.

Avoid duplicate deployment when a user double-clicks.

### 8.3 Tower construction

Player flow:

1. Open construction panel.
2. Select an unlocked tower.
3. Highlight available building slots.
4. Hover over a slot.
5. Show ghost tower preview.
6. Display attack radius.
7. Click to build.
8. Send server command.
9. On confirmation, play construction animation.
10. Replace the preview with the completed tower.

Invalid slots must not accept construction.

Possible invalid reasons:

- Slot already occupied.
- Insufficient coins.
- Tower not unlocked.
- Construction cap reached.
- Current match phase does not permit building.
- Team lacks permission to perform the action.

The specific rules must come from the backend.

### 8.4 Selection and inspection

Clicking an entity should show an appropriate contextual panel.

Troop:

- Name.
- Team.
- HP.
- Damage.
- Movement/range.
- Current status.

Tower:

- Name.
- Team.
- HP.
- Damage.
- Range.
- Upgrade information if supported.

Base:

- Team.
- Current HP.
- Maximum HP.
- Shield.
- Elimination status.

### 8.5 Interaction feedback

Provide:

- Hover highlights.
- Selection outlines.
- Valid/invalid placement indicators.
- Small UI animations.
- Sound feedback.
- Loading/pending states.
- Server rejection messages.
- Clear success confirmation.

Do not use sound as the only feedback channel.

---

## 9. GAMEPLAY HUD REDESIGN

### 9.1 Visual requirements

Create a compact fantasy-game HUD inspired by the reference screenshot.

The battlefield must occupy most of the viewport.

Do not surround the game with a large enterprise dashboard.

Suggested layout:

**Top-left**

- Team base HP.
- Coins.
- Current round.
- Match phase.

**Top-center**

- Round timer.
- Match status.
- Important event notifications.

**Top-right**

- Pause/settings, respecting host permissions.
- Sound on/off.
- Camera reset.
- Fullscreen toggle.

**Bottom-left**

- Unit selection.
- Tower construction.
- Optional special actions.

**Bottom-center**

- Selected troop/tower information.
- HP, attack, range, and cost.
- Deploy/build confirmation where appropriate.

**Bottom-right**

- Question access.
- Team details.
- Event log.
- Optional minimap if genuinely useful.

### 9.2 Visual consistency

HUD panels should use:

- Dark fantasy panels.
- Subtle metallic or wooden frames.
- Gold accents.
- Cartoon-style iconography.
- Legible text.
- Clear hierarchy.

Do not sacrifice readability to mimic decorative fantasy fonts.

### 9.3 Responsive behavior

Desktop:

- Full battlefield with persistent action bar.
- Contextual detail panels.

Tablet:

- Condensed HUD.
- Touch-friendly controls.

Mobile:

- Collapsible panels.
- Large touch targets.
- Camera gestures.
- Modal overlays with proper safe areas.

Do not assume all participants have desktop screens.

---

## 10. QUESTION & REWARD EXPERIENCE

Preserve the existing question-and-reward mechanic.

### 10.1 Question modal

When answering a question:

- Show a polished fantasy-style modal.
- Display question content.
- Show multiple-choice options where relevant.
- Display countdown timer if supported.
- Disable duplicate submissions.
- Show correct/incorrect feedback only when permitted by backend rules.
- Keep the battlefield visible behind a dimmed overlay.

### 10.2 Correct answer reward selection

After a correct answer, show two reward choices:

**Option A — Receive Coins**

- Add exactly 20 coins to the team.
- Reward can be claimed only once for that team's question.
- Use a short coin animation after successful server confirmation.

**Option B — Unlock New Unit/Structure**

- Show available unlockable troops or structures.
- Unlock itself costs no coins.
- Deployment/construction still costs coins.
- Once a reward has been claimed, the other choice is no longer available for that question.

If all available units and structures are already unlocked:

- Disable the unlock option.
- Keep the coin reward selectable while the reward remains unclaimed.

### 10.3 Security requirements

Do not grant rewards inside React or Phaser.

Backend must:

- Verify correct answers.
- Validate unclaimed reward state.
- Atomically grant coins or unlocks.
- Prevent duplicate reward claims.
- Enforce team-level ownership.

A repeated reward request must never grant another 20 coins.

### 10.4 Visual effects

Successful coin claim:

- Coin burst.
- Floating `+20`.
- Animated coin counter.
- Short positive sound.

Successful unlock:

- Unlock card reveal.
- New unit/tower illustration.
- Brief sparkle animation.
- New item appears in the appropriate action panel.

Server rejection:

- Show an informative message.
- No fake success animation.

---

## 11. COMBAT ANIMATION ENGINE

### 11.1 Combat architecture

The current game uses server-authoritative, turn-based combat.

Preserve this rule.

Do not silently convert the gameplay into realtime physics combat.

The client receives combat results or ordered events from the backend and visually replays them.

### 11.2 Event-driven playback

Support normalized combat events such as:

- UNIT_SPAWNED
- UNIT_MOVED
- TOWER_BUILT
- TOWER_FIRED
- UNIT_ATTACKED
- UNIT_DAMAGED
- BASE_DAMAGED
- SHIELD_ACTIVATED
- ENTITY_DESTROYED
- BASE_DESTROYED
- TEAM_ELIMINATED
- ROUND_COMPLETED

Adapt these names to the actual backend event contract.

### 11.3 Animation behavior

**Movement**

- Units follow visual paths corresponding to logical movement nodes.
- Use smooth position interpolation.
- Play walk or drive animation.
- Update sprite orientation.

**Tower attacks**

- Rotate or animate attack direction as appropriate.
- Show muzzle flash.
- Spawn visual projectile.
- Play impact effect.
- Animate HP changes.

**Damage**

- Flash the impacted sprite briefly.
- Show floating damage values.
- Shake affected entity slightly.
- Update HP bar from server-confirmed values.

**Death**

- Play short destruction/death animation.
- Remove the entity after animation.
- Clean up effects and event listeners.

**Base destruction**

- Play large destruction effect.
- Change base appearance.
- Show elimination feedback.
- Update team status.

### 11.4 Combat timeline

Implement a CombatPlaybackSystem capable of:

- Reading ordered backend events.
- Queueing visual animations.
- Grouping simultaneous actions when appropriate.
- Preserving causal order.
- Fast-forwarding.
- Skipping animations.
- Recovering after reconnection.
- Applying final authoritative state.

Rendering animation duration must not determine game rules.

If a client skips an animation, its game state must remain correct.

### 11.5 Deterministic visual playback

Given the same event sequence, clients should display equivalent gameplay results.

Random cosmetic particles may differ, but:

- Entity identities.
- Positions.
- Damage.
- HP.
- Death.
- Base destruction.

must match the server state.

---

## 12. MULTIPLAYER & SYNCHRONIZATION

### 12.1 Requirements

The game supports multiple mentor–mentee teams.

Each team should see the same shared battlefield state, subject to existing visibility and permission rules.

### 12.2 WebSocket integration

Reuse the existing WebSocket infrastructure.

The game client should subscribe to authoritative game-state events.

Important categories:

- MATCH_STATE_CHANGED
- TEAM_UPDATED
- COINS_UPDATED
- UNLOCK_UPDATED
- ENTITY_CREATED
- ENTITY_UPDATED
- ENTITY_REMOVED
- COMBAT_EVENTS
- ROUND_CHANGED
- MATCH_FINISHED

These are proposed categories, not mandatory backend endpoint names.

### 12.3 Reconnection

When a client reconnects:

1. Re-establish authentication.
2. Request authoritative match snapshot.
3. Restore team data.
4. Restore coins and unlocks.
5. Restore all visible entities.
6. Restore match phase and timer.
7. Resume event stream from a known sequence where supported.
8. Skip stale visual animations if necessary.

Do not duplicate existing units after reconnection.

### 12.4 Race condition prevention

Handle:

- Multiple members deploying simultaneously.
- Multiple members claiming the same reward.
- Concurrent coin spending.
- Duplicate WebSocket events.
- Delayed server responses.
- Out-of-order events.
- Disconnected users.

Use server-issued event IDs/sequence numbers and action IDs where supported.

Client-side optimistic previews must never become permanent state without server confirmation.

---

## 13. ASSET PRODUCTION & MANAGEMENT

### 13.1 Required minimum art assets

**Environment**

- Grass terrain variations.
- Dirt road segments.
- Water tiles/animation.
- Bridges.
- Trees.
- Bushes.
- Rocks.
- Barrels and crates.
- Decorative props.

**Buildings**

- Base.
- Machine Gun Tower.
- Cannon Tower.
- Shield Generator.

**Troops**

- Infantry.
- Tank.
- Artillery.

**Combat**

- Bullets.
- Shells.
- Explosion effects.
- Impact effects.
- Shield effect.
- Smoke.
- Damage feedback.

**UI**

- Coin icon.
- HP icon.
- Unit cards.
- Tower cards.
- Lock/unlock state.
- Construction indicator.
- Team markers.

### 13.2 Asset production workflow

First inspect existing assets.

Reuse suitable assets wherever possible.

If the project lacks artwork:

1. Identify missing assets.
2. Search for reusable assets that are legally compatible with the project, if permitted.
3. Generate or commission original visual assets through an appropriate artwork pipeline.
4. Normalize dimensions and visual scale.
5. Create sprite sheets or texture atlases.
6. Register assets in an asset manifest.
7. Integrate them into Phaser.

Do not claim that final artwork exists if only placeholders are available.

### 13.3 Asset manifest

Maintain a registry containing:

- Asset key.
- File path.
- Entity type.
- Frame dimensions.
- Animation frame information.
- Scale.
- Origin/anchor.
- Attribution/license information where needed.

Avoid hardcoded paths scattered across scene files.

### 13.4 Fallback assets

Temporary assets are acceptable during early implementation.

However:

- They must be visually distinct.
- They must support interaction testing.
- They must be clearly documented as placeholders.
- They must not be represented as finished commercial-quality graphics.

Do not complete the graphics phase while all major entities remain primitive shapes.

---

## 14. ANIMATION & PERFORMANCE

### 14.1 Target performance

Aim for:

- Smooth 60 FPS on a typical modern desktop.
- Graceful performance degradation on weaker devices.
- Stable gameplay with multiple teams.
- Low memory growth over extended matches.
- No large frame stalls during combat event playback.

Performance targets are acceptance goals, not guaranteed measurements.

### 14.2 Optimization

Apply:

- Sprite atlases.
- Texture reuse.
- Object pooling for projectiles and particles.
- Proper cleanup on entity destruction.
- Camera culling where useful.
- Limited particle counts.
- Reasonable texture dimensions.
- Controlled animation scheduling.
- React/Phaser render separation.

Avoid:

- Creating new textures every frame.
- React state updates for every sprite frame.
- Unbounded event listeners.
- Repeated loading of the same asset.
- Continuous recreation of all entities on every WebSocket event.

### 14.3 Audio

Add optional:

- Unit selection sound.
- Deploy sound.
- Construction sound.
- Projectile fire.
- Impact/explosion.
- Coin reward.
- Unlock reward.
- Victory/defeat.

Provide mute and volume controls.

Honor browser audio activation restrictions.

---

## 15. RECOMMENDED FRONTEND STRUCTURE

Adapt to the repository rather than force this exact structure.

```text
src/
├── game/
│   ├── core/
│   │   ├── GameManager.ts
│   │   ├── GameEventBridge.ts
│   │   ├── GameAssetLoader.ts
│   │   └── GameConfig.ts
│   │
│   ├── scenes/
│   │   ├── BootScene.ts
│   │   ├── PreloadScene.ts
│   │   └── BattleScene.ts
│   │
│   ├── map/
│   │   ├── MapRenderer.ts
│   │   ├── TerrainLayer.ts
│   │   ├── MapObjectFactory.ts
│   │   └── PlacementManager.ts
│   │
│   ├── entities/
│   │   ├── BaseSprite.ts
│   │   ├── InfantrySprite.ts
│   │   ├── TankSprite.ts
│   │   ├── ArtillerySprite.ts
│   │   ├── TowerSprite.ts
│   │   └── ProjectileSprite.ts
│   │
│   ├── systems/
│   │   ├── InteractionSystem.ts
│   │   ├── SelectionSystem.ts
│   │   ├── DeploymentSystem.ts
│   │   ├── ConstructionSystem.ts
│   │   ├── CameraSystem.ts
│   │   ├── CombatPlaybackSystem.ts
│   │   ├── EffectsSystem.ts
│   │   └── AudioSystem.ts
│   │
│   ├── animations/
│   ├── assets/
│   └── maps/
│
├── components/
│   └── game/
│       ├── GameCanvas.tsx
│       ├── GameHUD.tsx
│       ├── TeamStatus.tsx
│       ├── UnitPanel.tsx
│       ├── TowerPanel.tsx
│       ├── EntityDetails.tsx
│       ├── QuestionModal.tsx
│       ├── RewardModal.tsx
│       └── MatchResults.tsx
│
├── stores/
│   ├── gameStore.ts
│   └── uiStore.ts
│
├── services/
│   ├── gameApi.ts
│   └── gameSocket.ts
│
└── types/
    ├── game.ts
    ├── entities.ts
    └── events.ts
```

Separation of responsibilities is mandatory.

Do not put the entire game implementation in one large React component or one monolithic Phaser scene.

---

## 16. IMPLEMENTATION PLAN

Implement incrementally.

Do not attempt to deliver everything in one uncontrolled rewrite.

### PHASE 0 — Codebase Audit

Tasks:

- Inspect repository.
- Read GDD/PRD.
- Identify backend contracts.
- Identify current game behavior.
- Identify missing interactions.
- Review available visual assets.
- Create the audit document.

Deliverable:

`docs/GAME_GRAPHICS_AUDIT.md`

Acceptance:

- Existing code structure is understood.
- Reusable functionality is identified.
- Implementation approach is documented.

### PHASE 1 — Phaser Integration

Tasks:

- Integrate Phaser with the existing frontend.
- Build React-to-Phaser event bridge.
- Create initial scenes.
- Configure responsive canvas.
- Implement camera controls.
- Load initial assets.
- Ensure cleanup during component unmounting.

Acceptance:

- Phaser canvas renders within the existing application.
- No duplicate canvas or memory leaks after route changes.
- Camera pan and zoom work.
- Existing navigation continues to work.

### PHASE 2 — Battlefield Graphics

Tasks:

- Implement graphical terrain.
- Add grass, paths, forests, water, bridges, and decorations.
- Render bases.
- Render towers.
- Render troops.
- Implement sprite depth ordering.
- Apply consistent art direction.

Acceptance:

- Battlefield visually resembles a polished cartoon tower-defense environment.
- All important objects remain readable.
- Map is functional rather than a static background image.
- Camera controls work on the graphical map.

### PHASE 3 — Player Interactions

Tasks:

- Unit selection.
- Deployment preview.
- Placement validation.
- Deployment requests.
- Tower construction.
- Structure inspection.
- Entity selection.
- Range indicators.
- Server-confirmed coin updates.
- Error handling.

Acceptance:

- Players can deploy units through the battlefield interface.
- Players can construct towers through the battlefield interface.
- Invalid actions are rejected.
- Game state stays synchronized with backend.

### PHASE 4 — Combat Animation

Tasks:

- Movement animations.
- Attack animations.
- Projectiles.
- Explosion effects.
- Damage indicators.
- HP bar animations.
- Entity destruction.
- Combat event playback.
- Animation skipping.
- Reconnection state recovery.

Acceptance:

- Combat is visibly animated.
- Combat outcomes match authoritative backend events.
- Skipping animations does not change results.
- No duplicate entities appear after reconnecting.

### PHASE 5 — HUD & Reward Experience

Tasks:

- Redesign HUD.
- Implement fantasy-style action panels.
- Polish question modal.
- Polish reward selection modal.
- Add coin animations.
- Add unlock animations.
- Add team status panels.
- Polish results screen.

Acceptance:

- Interface matches the chosen game art direction.
- Game battlefield remains the primary focus.
- All existing reward rules remain correct.
- Claiming 20 coins more than once for one question is impossible.

### PHASE 6 — QA & Optimization

Tasks:

- Test multiplayer.
- Test desktop and touch controls.
- Test concurrent actions.
- Test WebSocket disconnection/reconnection.
- Test browser resizing.
- Test long matches.
- Test asset loading.
- Profile FPS and memory.
- Remove dead code and event listeners.
- Add appropriate tests.

Acceptance:

- The game is playable end-to-end.
- No critical gameplay regressions.
- Visual interactions are responsive.
- Rendering remains stable under realistic match load.

---

## 17. VERTICAL SLICE FIRST

Before implementing every unit and map feature, complete one playable vertical slice.

Minimum scenario:

- Two teams.
- One detailed battlefield.
- Two bases.
- One infantry type.
- One defensive tower type.
- Unit selection.
- Deployment placement.
- Coin deduction.
- Server-confirmed deployment.
- Animated movement.
- Animated tower attack.
- HP reduction.
- Unit death.
- Shared multiplayer state.

This scenario must work end-to-end before expanding the asset set and animations.

Do not build a beautiful but disconnected frontend.

---

## 18. TESTING REQUIREMENTS

Implement or update tests for:

### Interaction

- Valid deployment position.
- Invalid deployment position.
- Invalid build slot.
- Selecting an entity.
- Closing and reopening an action panel.
- Camera drag versus click.
- Double-click deployment prevention.

### Economy

- Correct answer and coin claim increases team balance by exactly 20.
- Duplicate reward request does not grant additional coins.
- Successful unlock does not also grant coins.
- Insufficient coins prevent deployment.
- Concurrent coin spending follows backend rules.

### State synchronization

- Created entities appear once.
- Updated HP values match backend.
- Destroyed entities are removed.
- Out-of-order events are handled safely.
- Reconnection restores accurate state.

### Combat

- Correct event ordering.
- Movement interpolation.
- Attack animation.
- Entity destruction.
- Skip animation functionality.
- Final state reconciliation.

### Rendering

- Assets load correctly.
- Canvas resizes without distortion.
- Mouse interactions work.
- Touch controls work.
- Scene teardown releases resources.
- Game does not recreate all sprites on every UI update.

Run available test, typecheck, lint, and build commands before reporting completion.

Do not claim a test passed without running it.

---

## 19. FINAL DELIVERABLES

The implementation should provide:

1. A redesigned graphical battlefield.
2. A fully functional Phaser game scene.
3. Original or properly licensed cartoon game assets.
4. Interactive unit deployment.
5. Interactive tower construction.
6. Animated combat playback.
7. React-based HUD.
8. Integrated question and reward flows.
9. Multiplayer synchronization.
10. Responsive desktop/tablet/mobile interaction.
11. Updated documentation.
12. Tests for critical gameplay flows.

Documentation files:

- `docs/GAME_GRAPHICS_AUDIT.md`
- `docs/GAME_GRAPHICS_ARCHITECTURE.md`
- `docs/GAME_ASSET_MANIFEST.md`
- `docs/GAME_GRAPHICS_IMPLEMENTATION.md`

Document:

- How to run the game.
- How to add a new unit sprite.
- How to add a new tower.
- How to define a new map.
- How animations consume backend events.
- How multiplayer state is synchronized.
- Which features remain incomplete.

---

## 20. DEFINITION OF DONE

The task is complete only when:

- [ ] The battlefield uses rich cartoon 2D graphics.
- [ ] The visual result is consistent with the reference image's art direction.
- [ ] The terrain, towers, bases, and troops are separate interactive entities.
- [ ] Users can interact with the battlefield through mouse or touch.
- [ ] Unit deployment works with the actual backend.
- [ ] Tower construction works with the actual backend.
- [ ] Troops move with visible animations.
- [ ] Towers attack with visible animations.
- [ ] Damage and destruction are visually represented.
- [ ] Coins and unlocks are synchronized with backend state.
- [ ] Correct-answer coin rewards are exactly 20 coins and claimable only once per team's question.
- [ ] Multiple users can observe the same match state.
- [ ] Reconnection works without duplicate entities.
- [ ] Existing gameplay logic is preserved.
- [ ] The project builds and critical tests pass.
- [ ] The implementation is not merely a graphical prototype.

---

## 21. CODING RULES

1. Inspect the repository before coding.
2. Follow existing project conventions.
3. Prefer strongly typed TypeScript.
4. Avoid unnecessary dependencies.
5. Keep Phaser rendering separate from business logic.
6. Do not duplicate backend authority in the frontend.
7. Never trust client-calculated damage, coins, or rewards.
8. Handle loading and error states.
9. Ensure all events and resources are properly cleaned up.
10. Write maintainable modular code.
11. Preserve existing functionality.
12. Do not create dead UI controls.
13. Avoid placeholder implementations for critical gameplay actions.
14. Do not claim unfinished visual assets are complete.
15. Document any assumptions and blockers.
16. Implement incrementally and verify after each phase.

---

## 22. EXECUTION INSTRUCTIONS

Start by analyzing the existing repository and the attached screenshot.

Then:

1. Produce the graphics audit.
2. Identify the smallest playable vertical slice.
3. Integrate Phaser into the existing architecture.
4. Implement the battlefield graphics.
5. Add real interaction and backend integration.
6. Implement event-driven combat animation.
7. Polish the user interface.
8. Run tests and validate gameplay.
9. Complete the remaining implementation phases.

Do not stop after writing an implementation plan.

Proceed with actual implementation when the repository and available tooling permit.

If an essential dependency, asset, API, or specification is missing, document the blocker precisely and continue with independent tasks that can be completed safely.

**Final objective: Transform the current Tower Defense project into a visually attractive, fully interactive, browser-based cartoon strategy game that feels like an actual playable indie game rather than a web dashboard.**