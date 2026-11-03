# Two-team build-slot correction

## Confirmed reproduction

A disposable two-team **version 4** match reproduced Red's base intersecting the rendered markers for `node_tower_t2_slot1` and `node_tower_t2_slot2`. This was measured from live Phaser base-art and marker bounds, not inferred from depth ordering. See `qa/army-map-browser.json` and the before/after images `qa/army-red-base-v4.png` / `qa/army-red-base-v5.png`.

The base SVG is 128×128, including its upper flag and padding. Phaser displays it at 137×137 with origin (0.5, 0.88), extending about 121 pixels above the node; input extends 120 pixels above it. The old 70-pixel circle around the node did not cover that asymmetric rectangle. Slot markers and backend node positions already agreed. Correcting depth or tooltip text would leave the real overlap.

## Version 5 geometry

`backend/apps/combat/build_geometry.py` validates projected coordinates matching `projectMap`:

- Base bounds: X ±75, Y −125..45, including artwork, input and the nearby HUD decoration.
- Tower/platform bounds: X ±54, Y −90..25, including 94-pixel tower artwork, side banner, marker touch area, and safety margins.
- Four-pixel separation between rendered structure rectangles.
- Foundation center clearance of at least 57.1 pixels from straight bridge/road axes and the rendered quadratic road curves.
- Barrier and arena-boundary clearance.

Version 5 starts with the existing roadside templates and their 15% roadward pull, then deterministically selects the nearest valid projected position when a footprint conflicts. Small arenas use a minimum layout scale of 1.4 to provide room for six full structure footprints per sector. Larger arenas retain the existing team-count scale. The shared validator operates on every team/orientation; there is no Red-only coordinate patch. Screen-upright artwork requires asymmetric clearance even where radial node templates are mirrored.

All slots retain their IDs, ownership, coverage links and construction rules. Passable graph topology and combat range in graph hops are unchanged. Validated positions are exported in the server map and consumed directly by markers, towers, map navigation and construction. Existing v3/v4 matches retain their exact layouts; their built towers are not migrated or moved. New matches default to v5. Clients/configuration schemas accept all three versions.

## Verification

- Geometry tests cover every integer team count 2–20, all six slots per team, road clearance, full footprint clearance and deterministic serialization round trips. All tested slot centers are within 190 projected pixels of a road.
- Browser reproduction compared v4 and v5 in two-team matches and found zero base/marker overlaps in corrected 2-, 4-, 8- and 20-team arenas.
- All twelve two-team towers were built by real Phaser pointer hit testing: mouse on one orientation and touch on the other.
- Browser checks constructed all six towers for every team in 2-, 4-, 8- and 20-team v5 matches (12, 24, 48 and 120 towers), using authoritative node IDs.
- Marker visibility and enabled hit targets were checked at zoom 0.6, 1.0 and 1.4 in those arenas.

Saved old layouts deliberately retain the original overlap. Start a new match to use the correction. No live-match migration is performed.
