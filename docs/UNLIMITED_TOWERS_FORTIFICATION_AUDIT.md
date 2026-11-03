# Unlimited towers and fortification audit

Audited 2026-10-24 before implementation.

## Confirmed quantity restrictions

- `backend/apps/matches/action_policy.py::require_purchase` counts ACTIVE/QUEUED/DISABLED towers and rejects at `configuration.max_towers_per_team` (default six). Both REST and WebSocket construction call this policy.
- `matches/defaults.py`, `matches/serializers.py`, `units/serializers.py`, `units/views.py` publish/default/validate the same cap. Stored old configuration values can also impose smaller caps.
- `frontend/src/game/actionAvailability.ts::purchaseAvailability` rejects tower selection using this configuration cap. `BattlePage.tsx` independently blocks placement using the team-state maximum, and displays a current/maximum tower counter.
- No additional round quota was found. `max_tower_placements_per_action` describes one command's batch size; construction itself creates one tower per command, with no round counter.
- Arena layout 6 / placement version 1 is already slot-free. Layouts 3–5 are saved-map compatibility modes with historical foundations. They must retain their coordinates; changing a running saved arena would change troop paths and existing positions.

## Existing authoritative protections

`ConstructionService.build_tower` locks Match then Team inside a database transaction, checks actor ownership even on retries, validates phase, tower catalog/unlock, balance and geometry, debits through EconomyService, creates entity/action and records after-commit events. Combat uses the same Match lock. PostgreSQL is required for cross-worker row-lock guarantees; SQLite preview is single process.

`PlacementGrid` caches server geometry by immutable arena. Each 32px cell checks all corners against deterministic team sectors and an annulus, then excludes roads/bridges/intersections plus swept troop envelopes, base rectangles, rallies, barriers and river terrain. Every cell of the 4×4 footprint must be owned and buildable. Existing ACTIVE/QUEUED/DISABLED TOWER/SPECIAL rectangles block overlap; destroyed entities release space. Neutral terrain is not buildable. Existing roadside margin is derived from troop bodies and stays unchanged.

Tower builds resolve team upgrade level at creation. Public entity serialization, TOWER_BUILT, snapshots and client reducers already preserve grid/world positions and deduplicate entity IDs. Upgrade events update only matching team/type, with the catalog refreshed by BattlePage. Build mode uses a reusable snapped ghost. No combat or quiz reset is required.

## Confirmed card root causes

The CÔNG SỰ picker is `BattlePage.tsx`'s `.arsenal-card`, not the separate map-inspection `TowerCard.tsx`. Its image, no-wrap title (including an inline 18×27px rank SVG), stats and cost share a 113px flex column aligned to the bottom. Responsive rules reduce cards to 106px or 91px while still reserving 61px/51px images. The badge increases title line height and width; added tower stats further exceed the available vertical budget. Flex shrinking and horizontal overflow displace artwork and titles. Selected borders also change content space. No stable artwork wrapper exists.

`entityArtwork.ts` supplies individual generated SVG previews with level equipment, not sprite-sheet crops. Their intrinsic viewBox and transparent margins must be contained, not cropped. Rank metadata already has the four requested Vietnamese accessible labels. Full badges remain appropriate in detail views/modals.

## Scale investigation

Placement currently materializes full GameEntity rows and linearly scans every structure in the match for each build. Static grid masks are cached. Combat already indexes entities by node, but physical grid-tower range uses a separate global scan. Client ghost collision is linear over current structures. Phaser maintains visuals by entity ID rather than recreating the scene; effects and offscreen visibility have existing pooling/LOD behavior. Benchmark actual construction, collision, combat, snapshot bytes, browser frame cadence and heap before deciding whether to change these paths. Do not add quantity caps.

## Final compatibility correction

Removing only the count policy would have left saved layout 3–5 arenas restricted to their old foundation UI. The final implementation publishes cached grid masks for those original geometries too, accepts row/column builds there, returns empty picker slot lists and suppresses unused foundation art. Existing legacy entities and graph routes remain in place; old node-only service commands remain compatible. Tests cover all legacy layouts at 2/4/8/20 teams, mixed old/grid occupants, unchanged positions/routes and valid extra construction where real space remains. Compact old maps may genuinely be full.
