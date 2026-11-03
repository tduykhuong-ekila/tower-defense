# Roadside tower placement refinement

The later clearance update is documented in `ROADSIDE_TOWER_CLEARANCE_ADJUSTMENT.md`.

Implemented 24 October 2026. Supersedes the geometry in `ROADSIDE_TOWER_PLACEMENT.md` for new purchases.

## Confirmed causes

- The square grid already has adequate 32 px resolution. The larger restriction was the **4×4 / 128×128 px reservation**, with its anchor 32 px below the center. It was sized around an old combined artwork, banner and input rectangle, rather than the current 94 px tower texture.
- `road_segments()` contains both straight graph edges and 16-segment quadratic painted curves. The previous mask swept the complete troop envelope along **both**, even though troops move along straight graph edges. This unnecessarily inflated the curved road exclusion.
- Vehicle deployment stores a widely spaced rally parking position. Previously its parking offset could remain attached to every road edge. A corridor based only on the standard crowd patch would not protect these saved offsets.

The audit also checked territory corners, bases, staging bounds, the river's width and slope, obstacles, bridge axes, sprite origins, frontend world projection, retarget/retreat routes, and server construction transactions. Those exclusions are not replaced by a reduced center-distance threshold.

## Geometry now

`apps/combat/build_geometry.py` exposes `movement_segments()` separately from painted `road_segments()`.

`apps/units/placement.py` uses:

- **New tower reservation:** 3×3 cells = **96×96 px**, anchor offset Y **36 px**. Relative to the anchor this is `[-48, -84, 48, 12]`, containing the entire 94×94 tower texture at origin `(0.5, 0.89)`. Side banners, rank sidecars and larger click targets are decorative/input elements and do not expand collision bounds. All three tower types use this footprint.
- **Protected troop envelope:** unchanged `[-71, -68, 71, 15]`, derived from all 15 projected crowd slots and the Infantry 34×38, Tank 54×44 and Artillery 54×50 bodies, including their vertical sprite anchors.
- **Movement clearance:** expand the complete candidate rectangle by the reflected troop envelope, retain the existing **1.72 px physical formation gap**, then use closed segment/AABB intersection against every straight passable edge. Tangencies are rejected.
- **Painted road clearance:** exact segment-to-rectangle distance against the 57 px painted road/bridge width, plus the physical gap and bounded curve sampling residual `0.04 × longest_chord / 16²`. Decorative curves do not carry the troop envelope.

Every cell of the whole tower footprint must pass the server mask. Adjacent cells at a road edge are allowed as soon as the full footprint clears both protected regions. Intersections union all incident corridors; bridge axes stay protected and water remains unbuildable. Routes are bidirectional, so the same masks protect forward movement, retargeting and retreat.

New vehicles deployed in grid-mode rooms approach the bounded road patch from their parking position within the protected rally. No leader queue, speed reduction or deployment cap is added. Saved troop states and legacy-mode deployment are not relocated. **Existing offsets outside the standard envelope add a dynamic swept-corridor exclusion on all passable edges**, using the actual troop type and authoritative `crowd_offset`. Both server validation and frontend preview apply this rule. Duplicate envelopes are checked once; normal standard offsets need no extra road check.

## Grid compatibility and authority

The cell size, origin, arena projection and saved row/column coordinates are unchanged. No database migration is needed. Existing `grid_placement` dictionaries retain their own width, height and anchor, including old 4×4 reservations. New towers cannot overlap any part of those saved reservations. Existing fixed foundations also retain their original coordinates and collision bounds.

The additive schema remains `version: 1`, with `geometryRevision: 2`; arena cache keys end in `-grid-v1-r2`. The server sends footprint dimensions, body metadata and `buildableRuns`. Phaser reads that exact mask and snaps the **tower anchor nearest the pointer**, after camera unprojection. The ghost highlights the complete reservation and uses green/red for valid/invalid candidates. Click and touch confirmation use the same conversion; it does not silently search for a different valid origin.

Frontend occupancy is indexed into a typed cell array once per authoritative entity-array update. Pointer motion then checks only the footprint's cells, saved fixed foundations and any exceptional legacy corridors. Normal mobile units are not treated as buildings. Existing combat spatial searches, culling, sprite pooling and bounded effects remain in place.

The server still locks the match/team, checks phase, authorization, unlock, full territory and collision, debits the normal cost and creates one idempotent action. **There is no per-team tower count cap.** Real simultaneous builds, changing coins or authorization can still invalidate an otherwise green preview.

## Measurements

Team 1, unobstructed static arena; candidate origins overlap and are **not** tower capacity:

| Teams | Previous valid origins | Refined valid origins | Previous minimum visible gap | Refined minimum visible gap |
| --- | ---: | ---: | ---: | ---: |
| 2 | 2,399 | 2,650 | 41.42 px | 23.05 px |
| 4 | 914 | 1,059 | 41.42 px | 23.05 px |
| 8 | 151 | 221 | 41.42 px | 23.05 px |
| 20 | 490 | 679 | 41.51 px | 23.14 px |

Visible gap measures the full 94 px texture rectangle to the painted edge, not the tower center. The remaining distance is grid quantization and the required movement envelope. It is not a new decorative exclusion margin. Source: `qa/roadside-refinement-geometry.json`.

## Verification

- `test_roadside_refinement.py`: prior/current masks; full texture containment; old 4×4 occupancy; saved vehicle offsets; swept Infantry/Tank/Artillery paths through turns, retargeting and retreat; owned placements and connected routes for **every team count 2–20**.
- Existing geometry, purchase, economy, upgrade, movement, combat, quiz, question-bank, realtime and saved-layout regressions remain in the backend suite. Saved layouts 3/4/5 are exercised at 2/4/8/20 teams.
- `grid-placement.test.ts` consumes regenerated backend fixtures, tests occupancy, destroyed release, invalid inputs, nearest-anchor conversion and the legacy offset guard.
- `roadside-stars.browser.mjs` tests actual green and red Phaser previews, purchases after zoom and pan, all four representative map sizes, two-team synchronization, reconnect and live mixed troop commands.
- `roadside-stars-load.browser.mjs` purchases 25 and 50 towers **per team**, deploys 100 Infantry and observes genuine combat WebSocket sequences and rendering in two clients.
- `benchmark_unlimited_towers.py` covers 2/4 teams at 50 towers each and 20 teams at 25 towers each, including construction, collision, snapshots and combat ticks. Results are in `qa/roadside-stars-performance.json`.
- Screenshots: `qa/refined-preview-{2,4,8,20}.png`, `qa/refined-roadside-{2,4,8,20}.png`, and `qa/stars-live-*.png`. Aggregate commands/results: `qa/roadside-stars-validation.json`.

## Deployment and limits

Deploy/restart backend and frontend together and refresh connected clients to load the new masks. This changes no balance values: Cannon damage 20/range 2, Infantry speed 7/HP 80, Artillery speed 5/HP 80, normal costs, upgrades, quizzes and batch commands remain intact.

Existing towers are never forcibly moved out of an old invalid location. Exceptional saved crowd offsets are protected conservatively across all graph edges. Manually corrupted positions without a corresponding offset or unsupported custom sprite bodies are outside this geometry contract. Browser QA uses Chrome, one local ASGI process and its in-process channel layer; PostgreSQL row-lock tests are separate, and this is not a production multi-worker Redis load certification.
