# Grid tower placement design

## Coordinates and footprints

New rooms use `tower_placement_version:1` and arena layout 7. Stored configurations without the flag default to legacy version 0. The configuration serializer rejects mixed legacy/grid layout pairs. Layout 6 remains unchanged for saved rooms. Layout 7 keeps the same graph topology and generates no fixed tower-slot nodes. Three-team arenas use a 4.2 layout scale, shorten the second branch by 10% and extend the third branch by 12% to balance projected routes and roadside build areas. The river is routed 250 projected pixels away from the green team's corridor, then steered farther from roads it would follow in parallel to preserve wider tower-building corridors; road crossings stay near-perpendicular. The exact path is shared in placement metadata so terrain, water exclusions and vegetation clearances agree. Layouts 3–6 retain their existing coordinates and graph coverage.

The authoritative square grid is in projected battlefield artwork coordinates, independent of camera position: origin (0,0), cell size 32, columns `floor(arena.width/32)`, rows `floor(arena.height/32)`. Row/column identify the top-left of the footprint. All three supported defensive structures use the same 94px sprite and banner; each reserves 4×4 cells (128×128). The sprite anchor is footprint center plus (0,32). The whole artwork/input rectangle fits. Unknown tower types are rejected until a footprint is configured.

The server converts the anchor to graph coordinates by subtracting `(arena.width/2, arena.height/2+60)`, undoing scales (1.5,.86), and undoing rotation -135°. The JSON `simulation_state.world_position` stores that graph position; `grid_placement` stores row, col, dimensions and anchor offset. `current_node_id` is a nearby passable spatial bucket, not the tower's displayed or combat position.

## Buildable areas

The server caches a cell-owner mask for each immutable arena. Eligible cells lie wholly in one exclusive radial team sector and within the defensive annulus (140–420 times layout scale). Each complete multi-cell footprint must belong to the purchaser's sector. Team order is the existing created_at/id order.

Cells exclude conservative base artwork/input rectangles, all full navigation staging bounds plus 12px, barrier radii, the procedural river including banks, straight troop routes, sampled quadratic painted roads and their bridges/intersections. Road clearance includes the cell circumscribed radius plus 57.1px. This keeps both vehicle bodies and the current bounded crowd offsets off tower footprints; no route graph edge is removed or rerouted. Road exclusion also protects bridge crossings and lane entry. Decorative vegetation remains passable scenery; it is neither removed nor added to gameplay collision.

The API serializes allowed cells as horizontal runs `[row,startCol,endColExclusive,teamIndex]`. Clients decode once into a WeakMap-cached byte mask. A candidate checks only its 16 cells and active structures. The scene draws one reusable ghost, one small local grid graphic, one label and one range graphic. There are no permanent objects for grid cells and no full-grid pointer scans.

## Atomic occupancy and limits

Construction locks Match, then Team, using the same order as combat and team upgrades. Under that lock it checks actor ownership, phase, type, unlock, capacity, coins, grid ownership and complete footprint collision. Existing active, queued and disabled TOWER/SPECIAL entities reserve occupancy, including legacy world-position/artwork rectangles. Destruction releases occupancy, following the previous destroyed-slot policy.

The lock serializes all construction in a match, including different teams and overlapping cells, and combat destruction. Validation, debit, entity creation, durable idempotency action and event share one transaction. A rejected request never debits. Retries return the original entity; conflicting requests using the same team/key fail. Existing `max_towers_per_team` (default six), costs, unlocks and live-build phase rules remain authoritative.

Match-wide locking is deliberately used instead of a second cell reservation table: it is already the synchronization boundary for this engine. Production requires PostgreSQL row locks. SQLite tests cover deterministic logic; the isolated browser database uses SQLite IMMEDIATE transactions. Real overlapping requests are tested separately against PostgreSQL.

## API and realtime

POST `/api/v1/matches/{id}/actions/build/`:

```json
{"unit_type_code_or_id":"cannon_tower","grid_row":30,"grid_col":40,"idempotency_key":"unique-command-id"}
```

Coordinates must be actual integers, including through WebSocket. Arbitrary client world positions are ignored. Legacy matches still accept `node_id`; grid matches require grid coordinates. WebSocket `BUILD_REQUEST` uses `tower_code`, row, col and key. Both call ConstructionService.

`TOWER_BUILT` keeps its existing identifiers, stats, coins and node fields and adds `grid_row`, `grid_col`, `simulation_state:{world_position,grid_placement}`. Events broadcast after commit. REST entities, snapshots and COMBAT_TICK retain both position fields. The existing entity-ID upsert prevents duplicates across REST, events and recovery snapshots. Destruction and upgrade events keep their existing schemas.

New towers use the current team level. For a grid tower, combat distance uses actual map positions divided by the existing 80-unit reference hop; the unchanged Cannon range 2 is 160 map units, drawn as a matching projected ellipse. Grid towers participate in continuous and explicitly enabled legacy-round targeting. Legacy slot towers retain graph coverage. Catalog base damage is 20; Lv.1–4 damage is 20/22/24/27 with unchanged modifiers, applied once.

## Interaction priority

Modal → build → entity selection → navigation. Build clicks do not select troops, target bases or inspect entities. Drag pans; wheel and pinch zoom; neither constructs. Escape/right-click/cancel leave build mode. Touch requires a deliberate second tap on the same footprint. Changing type clears touch confirmation. Invalid match/team state removes active build mode. Client colors are preliminary: the server always revalidates after pointer selection.
