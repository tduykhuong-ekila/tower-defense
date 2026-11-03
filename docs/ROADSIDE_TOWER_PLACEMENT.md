# Roadside tower placement

## Geometry audit

The game uses projected artwork coordinates, not camera pixels. The existing grid has 32-pixel cells and 4×4-cell (128×128) tower reservations. The anchor is 32 pixels below the footprint center, containing the tower's occupied artwork bounds `(-54,-90,54,25)`. The previous road mask marked cell centers within `57.1 + 32/√2 ≈ 79.73` pixels of every straight route and sampled painted curve. This added a full cell circumradius to a symmetric clearance regardless of the actual cell orientation or movement needs.

Painted roads have outer width 57 pixels and quadratic controls offset by 8% of chord length. Combat movement follows the straight graph, with 15 projected crowd slots ranging ±44 horizontally and ±16 vertically. Existing physical bodies are Infantry 34×38 at y=-20, Tank 54×44 at y=-27, and Artillery 54×50 at y=-27. Their full combined swept envelope is `[-71,-68,71,15]` relative to the route anchor. The old symmetric radius was unnecessarily restrictive on some edges and did not explicitly model these bodies.

## New rule

`backend/apps/units/placement.py` derives the protected movement envelope directly from `SPRITE_BODIES` and `crowd_offset`. It retains all troop positions and physical body sizes. Optional clearance is the existing minimum formation gap projected into artwork space: `2 × 0.86 = 1.72` pixels.

For each cell:

1. Expand its rectangle by the reflected movement envelope and safety gap; use a closed segment/AABB slab test to reject any swept-body intersection.
2. Independently compute exact segment-to-rectangle distance to protect the painted road's 28.5-pixel half-width plus gap.
3. Add the bounded quadratic sampling residual `.04 × longest_chord / 16²` so the actual curve, not only its sampled chords, stays clear.

`backend/apps/combat/build_geometry.py` supplies robust segment/AABB intersection and segment/rectangle distance helpers. They handle crossings, endpoints, degenerate segments, corner distances and tangencies. The legacy fixed-slot generator is unchanged. Grid arenas never regain the old six fixed construction positions.

Some cells can become more restrictive where the actual upper/side troop envelope requires it. Additional safe near-road 128×128 placements for team 1, compared with the previous road mask under otherwise identical exclusions:

| Teams | Newly valid footprint origins |
| --- | --- |
| 2 | 4 |
| 4 | 4 |
| 8 | 3 |
| 20 | 10 |

Counts are overlapping candidate origins, not additional tower capacity. The team tower cap remains unchanged.

## Authority and preview

The server serializes its cell ownership mask as existing `buildableRuns`, with additive `roadClearance` audit metadata. The Phaser ghost and TypeScript placement validator continue to read this exact mask and check every cell in the selected footprint. There is no second approximation to drift from the server. Grid snapping and explicit clicked-cell confirmation are unchanged; the cursor is never silently relocated.

Territory corners, base bounds, rally polygons with their existing 12-pixel padding, barriers, river width/slope exclusion and occupied foundations retain their rules. Every passable graph edge and sampled painted road is protected, including reverse routes, intersections and bridges. Water still excludes construction on bridges. Attack range, speed and damage are untouched: Cannon base damage remains 20 and range remains 2; Artillery range remains 1.5. Troop speed/HP, deployment batches and retreat logic are unchanged.

Decorative vegetation does not participate in collision masks. BattleScene hides cosmetic images whose actual sprite bounds overlap an accepted grid foundation. It recomputes visibility only when occupancy changes, restores plants after destruction, and never removes real barrier obstacles. All clients use the same authoritative occupancy state.

ConstructionService still locks the match and team, validates against all live structures, debits coins and creates the entity in the existing atomic transaction. No new client placement authority was introduced. A green preview may still lose a genuine simultaneous build race, be denied after elimination, or become unaffordable before purchase.

## Verification and limitations

- Exact distance edge cases and every standard physical body/crowd slot are tested.
- 2/4/8/20-team tests prove added roadside origins, full footprint clearance against all route/curve segments, connected routes, six disjoint buildable foundations per team, and territory/base/rally/water exclusions.
- Regenerated server fixtures feed frontend mask, snapping, ownership and occupancy parity tests.
- Real browser ghost previews and purchases at newly available roadside origins are exercised on all four arena sizes, with two-client occupancy on the two-team arena.
- Existing movement/Retreat All/batch/combat/quiz/WebSocket tests run with the full backend suite. PostgreSQL tests exercise concurrent overlap and purchase debits with real row locks.
- A separate post-build browser check found no visible vegetation overlapping any occupied footprint on all four maps; the two- and four-team roadside builds each hid one decorative tree. See `docs/qa/rank-vegetation-results.json`.
- QA screenshots: `docs/qa/rank-roadside-{2,4,8,20}.png`; browser report: `docs/qa/rank-roadside-results.json`.

This geometry models standard current bodies and the bounded standard crowd patch. Arbitrary manually edited legacy world positions/offsets are not separately revalidated or relocated. Existing saved towers also remain in place; new rules apply when validating new construction. No claim is made about cross-process Redis delivery beyond the existing backend tests; browser QA uses the isolated in-process channel layer. The authoritative mask should be refreshed by clients when deploying changed server geometry; ordinary reconnect/snapshot loading already fetches it.

Final validation: backend **469 passed, 19 skipped**; frontend **121 passed**; **4 PostgreSQL concurrency regressions passed**; TypeScript/production build passed; Chrome interaction report **PASS**. See `docs/qa/rank-roadside-validation.json` for commands and scope.
