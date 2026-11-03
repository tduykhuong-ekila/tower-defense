# Star levels in Army and Fortification selection cards

> Historical implementation record. The current maximum is Level 3 and stars now appear across the game; see [THREE_STAR_UPGRADE_SYSTEM.md](THREE_STAR_UPGRADE_SYSTEM.md) and [UPGRADE_LEVEL_MIGRATION.md](UPGRADE_LEVEL_MIGRATION.md).

Implemented 24 October 2026. This supersedes chevron/shield badges **inside the QUÂN ĐỘI and CÔNG SỰ pickers**. Existing map insignia, inspection details and the team equipment modal retain their current presentation and upgrade behavior.

## Component and meaning

`frontend/src/components/game/UnitLevelStars.tsx` is the single star renderer, shared by all troop and tower picker content and the older detailed UnitCard component. It renders filled Lucide SVG stars, never emoji:

| Authoritative level | Filled SVG stars |
| --- | ---: |
| 1 | 1 |
| 2 | 2 |
| 3 | 3 |
| 4 | 4 |

Its props accept `level` and optional `size: "compact" | "normal"`. Missing/invalid display values are clamped to 1–4. Compact icons are 11 px, normal icons 13 px, with a restrained warm gold color, 2 px gaps, no background pill and no animation. The outer accessible image is labelled `Cấp N trên 4`; individual SVGs are hidden from assistive technology.

The picker places stars in a dedicated centered 16 px region **below** the artwork. One through four stars occupy the same row height and cannot resize the image, name or cost. The card name does not contain a badge or leave space for a removed badge. Lock, selection, disabled action and affordability states remain separate from level.

## Authoritative realtime data

`matchStore.teamUpgradeLevels` consumes the existing server snapshot's `team_upgrades` map and `TEAM_UNIT_UPGRADED` events, keyed by **team ID and unit code**. BattlePage derives picker levels from this map before falling back to the REST catalog. This updates a teammate's stars immediately even if no matching entities exist or the REST catalog refresh is delayed. Older sequenced snapshots/events cannot overwrite newer state; reset clears previous-room levels.

The backend upgrade transaction is unchanged: all live matching entities inherit the purchased team level with their HP ratio preserved, future purchases use that level, other teams remain independent and level 4 is still the maximum. Entity rendering continues to use the existing level-specific equipment assets. Stars do not change prices, range, speed, stats or the upgrade confirmation flow.

## Verification

- `star-level.test.ts` renders the real React components to static markup for all four levels and six types, checking SVG count, Vietnamese accessibility labels, artwork paths, region order and absence of old rank tags.
- State tests cover team isolation, upgrades without deployed entities, stale snapshots and room reset. Existing upgrade reducer regressions remain enabled.
- Browser QA covers 1–4 stars, both categories, six availability/selection states, five viewport sizes and 100%/125% page scaling. It checks actual SVG counts and fixed internal row geometry.
- Three authenticated browser clients verify a teammate sees Cannon upgrades 2/3/4 immediately, the opponent's cards retain level 1, existing tower entities update, newly constructed Cannons inherit level 4/damage 27, and reconnect restores stars and locations.

See `qa/roadside-stars-browser.json`, `qa/roadside-stars-validation.json`, and the `qa/stars-army-*.png`, `qa/stars-fortification-*.png`, `qa/stars-live-*.png` screenshots. Chrome is the verified browser engine; cross-browser font rendering is not separately certified.
