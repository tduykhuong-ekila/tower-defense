# Roadside tower clearance adjustment

Implemented 25 October 2026. This supersedes the clearance and rally mask in `ROADSIDE_TOWER_PLACEMENT_REFINEMENT.md` for new purchases.

## Cause and scope

The grid is 32 px per cell. All three defensive towers reserve a 3×3 cell, 96×96 px footprint, containing the complete 94×94 px tower texture. On grid arenas (layout 6), the bright sand road is 70 px wide, with 80 px and 92 px underlayers. The static tower placement corridor is 92 px wide, down from the full 142 px swept formation envelope; this leaves the outermost 25 px on each side outside the tower-placement reservation. Troop positions, bodies, spawn points and graph routes stay unchanged. Older arenas with fixed tower positions retain their original 43/49/57 px road layers.

The other excess was the staging exclusion: one large rectangle enclosed every possible vehicle parking slot per team. That rectangle blocked empty pockets between the actual straight approaches from a parking slot to the road patch. The new mask sweeps the largest troop body along all parking-slot approaches. Six extreme crowd goals cover the full 5×3 goal patch, and validation tests all 15 actual goals. Staging keeps the existing 1.72 px gap. The road and tower footprint test uses closed intersection with zero extra troop-to-tower padding, so a touching or overlapping footprint remains blocked. The complete painted road and its curve tolerance remain protected.

Saved unusual parking approaches and crowd offsets are checked dynamically by Django. The Phaser preview uses the server-authored static mask and the same live-unit corridors and staging paths; route nodes and staging entry distance are included in public entity state for an exact staging endpoint. Existing placed towers keep their saved coordinates and footprint dimensions. Layout 6 maps advertise `geometryRevision: 6` and an `-grid-v1-r6` cache key. Three-team layout 7 maps advertise `geometryRevision: 9`; their wider-corridor river path is shared with Phaser, vegetation and placement clearance. Django placement clearance reads the same outer road width sent to Phaser.

## Measurements

Team 1 on each representative layout. Valid origins can overlap, so these are placement choices, not simultaneous tower capacity. Gap is from the full 94 px tower texture to the outside road layer, not from the tower center. Revision 5 values are compared with the current revision 6 mask in `qa/roadside-closer-geometry.json`.

| Teams | Revision 5 valid origins | Revision 6 valid origins | Change | Revision 5 minimum gap | Revision 6 minimum gap | Former staging rectangle origins within 64 px of road |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 2,710 | 2,730 | +20 | 1.03 px | 1.11 px | 11 |
| 4 | 1,119 | 1,139 | +20 | 1.03 px | 1.11 px | 11 |
| 8 | 244 | 262 | +18 | 1.03 px | 1.11 px | 12 |
| 20 | 689 | 735 | +46 | 1.12 px | 1.20 px | 12 |

The narrower road and placement mask open additional cells along the lanes; the troop sprites and routes themselves are unchanged. A tower placed at the new limit can overlap up to 25 px of the outer formation envelope. Tower construction remains outside the 92 px reserved corridor and the 92 px outer road layer.

## Verification

- `test_roadside_ranks.py` checks every reopened staging-side footprint against all 40 parking slots and all 15 unchanged crowd goals per team, plus every straight troop edge and painted road segment on 2/4/8/20 team maps.
- `test_roadside_refinement.py` moves mixed Infantry, Tanks and Artillery through turns, retargets and retreats, checks saved approaches and offsets, and checks owned buildable positions and connected routes for every team count 2–20.
- The backend owns the build transaction, full-footprint and territory checks, normal cost, unlock rules and idempotency. The frontend consumes the same static mask; unit tests check grid snapping, preview eligibility, occupancy and dynamic staging paths.
- The Chrome browser acceptance script passed on 2/4/8/20 teams: new near-road tower previews were green and built, road overlaps were red, zoom/pan snapping worked, both clients synchronized, and all three troop types moved through retarget and Retreat All. Results: `qa/roadside-stars-browser.json`.
- The two-client load script passed with 25 and 50 towers per team and about 100 deployed Infantry, with 60 fps measured in that local run. Results: `qa/roadside-stars-load.json`. Browser fixtures use a disposable database; the ordinary game database is not changed.
- Revision 3 verification: backend 535 tests passed, 23 skipped; frontend 126 tests passed; the production build and Chrome placement/load runs passed. Revision 5 and revision 6 each passed all 40 roadside geometry and movement tests, all 126 frontend tests, the production build, Ruff and Django migration check. The full backend suite and Chrome acceptance/load runs have not been repeated after the width changes.

No tower cap, balance, upgrade, combat, pathfinding or formation rule was changed.
