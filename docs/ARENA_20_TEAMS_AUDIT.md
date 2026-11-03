# Arena expansion audit

The repository already supports a variable number of teams, rather than exactly four. The API and graph cap that number at 12; the combat engine silently clamps it to 12. The renderer has 12 team textures and a fixed 1600 × 1040 world. These are the actual capacity limits.

Teams already have independent UUIDs, shared balances, unlocks and mentor/mentee membership. There is no database constraint on match team count, so no schema migration or membership redesign is needed. Creation order plus UUID is the existing stable index; elimination must never renumber it.

The authoritative graph is a single connected radial arena: one branch, spawn and three defensive slots per team, a connected inner ring and a central junction. Movement and range use graph hops, not pixel distance. Expanding visual distances without changing edges preserves movement, tower ranges and four-team matches. Existing node identifiers must remain stable.

Other findings:

- Match creation and lobby inputs cap minimum teams at 12 and do not expose maximum capacity.
- Snapshot serialization performs per-team member, entity-count and unlock queries.
- Combat persistence searches querysets repeatedly and saves each entity individually.
- A match row lock alone does not deduplicate two requests for the same round.
- Team banners and native target selectors become difficult to use with 20 entries.
- The scene keeps entity objects by ID, but lacks distance detail, minimap, bounded visual effects and performance telemetry.
- Victory/scoring already iterate dynamic teams; result tables need bounded scrolling.

Implementation order: explicit 2–20 validation; deterministic arena metadata and geometry; indexed/batched backend work and expected-round replay; 20 visual identities and dynamic camera/terrain; searchable team navigation and interactive minimap; capacity controls; tests, reproducible measurements and documentation.

Compatibility risks: index ordering, graph-hop balance, private snapshot fields, concurrent round retries, texture memory on large maps, camera legibility and saved four-team node positions. Tests and measurements must cover these explicitly. Existing default minimum four and default maximum eight remain compatible; hosts can configure any valid range within 2–20.
