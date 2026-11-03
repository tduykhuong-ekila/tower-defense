# 2–20-team arena implementation

The existing game now accepts every integer team count from 2 to 20. The work extends the current Django/Channels + React/Zustand + Phaser implementation. Default minimum four / maximum eight remains compatible; hosts explicitly configure larger rooms. Existing mentor/mentee sharing, +20 default correct-answer reward, paid deployment, unlocks, timers, HP, shields, targeting, victory and scoring remain in place.

Implemented areas:

| Area | Result |
|---|---|
| Capacity | API validation 2–20, creation and lobby maximum controls, reject a 21st team and capacity below existing teams |
| Authoritative arena | One deterministic scaled radial arena, actual team count, stable IDs, sorted export, cached BFS and indexed range lookup |
| Compatibility | Four-team coordinates and graph hops retained, old payload world fallback, indices survive elimination |
| Identity | Twenty generated texture sets, twenty colors, stable numbers and symbols on bases, lobby and scoreboard |
| Navigation | Search/filter/sort all twenty teams, route preview, target selection, base/placement focus, pan/pinch/wheel and interactive minimap |
| Rendering | Incremental ID containers, bounded terrain texture, culling, paused offscreen animation, overview stacks, bounded unit stacks and pooled effects |
| Combat | Batched ordered playback within roughly fourteen seconds per large event batch, queue/skip, final reconciliation from server state |
| Persistence | Dictionary lookups and bulk writes for teams, entities, actions and income ledger |
| Round retries | Explicit expected round, match-row lock, persisted response replay and whole-transaction SQLite lock retry |
| Live state | Batched permission-scoped snapshots, question UUID JSON fix, coalesced in-flight recovery requests |
| Data boundaries | Public match details omit live balances; public nested combat/deploy balances are projected per viewer; host keeps full events; unlock events use team-private routing |
| Results | All teams and shared ranks retained in a bounded scrollable table |
| Measurement | Reproducible service/ASGI benchmark, browser fixtures, opt-in `?performance=1` counters |

Files are grouped in `backend/apps/combat/`, `backend/apps/matches/`, `backend/apps/realtime/`, `backend/apps/questions/serializers.py`, `backend/apps/units/map.py`, `frontend/src/game/`, `frontend/src/components/arena/`, relevant pages and tests. Original artwork remains generated from `frontend/scripts/generate-art.py`; see the updated asset manifest.

Two regressions surfaced during real browser testing and were fixed: standard Channels JSON could not encode the canonical question serializer's raw foreign-key UUID values; and the pure engine's paused single-team fixture must freeze before any arena validation or round work. Neither fix changes normal combat balance.

Validation includes 2–20 topology/determinism/fairness checks, odd capacities, mentor/mentee start validation, API contracts, duplicate same-round workers and income, a 20-team answer/reward/combat/victory/results scenario, active-question reconnect, 80 players plus two spectators and host, private delivery, spectator read-only enforcement, and twenty-team frontend projection/assets/scoreboard/socket tests. Commands and final results are recorded in the performance report.

No team-capacity schema change is required. The migration consistency check also found an existing economy choices drift: `ADMIN_OVERRIDE` already existed in the model but not migration state. `economy/0003_sync_transaction_choices.py` aligns that declared choice list; it adds no column or new economy rule and preserves existing data. Apply migrations through the normal deployment process.

Operational limits: the original hub remains a shared combat choke point, graphical detail is reduced at overview zoom, the largest terrain texture trades fine grass detail for bounded memory, and the benchmark uses SQLite/InMemoryChannelLayer rather than a deployed PostgreSQL/Redis cluster. Hardware-specific FPS and network capacity must be measured on the intended deployment. The report distinguishes these boundaries and contains actual measurements rather than a fixed 60-FPS claim.

Read alongside:

- `ARENA_20_TEAMS_AUDIT.md`
- `ARENA_SCALING_ARCHITECTURE.md`
- `ARENA_MAP_FORMAT.md`
- `MULTIPLAYER_20_TEAMS.md`
- `ARENA_PERFORMANCE_REPORT.md`

Resume verification on 2026-10-17 added persistent preview settings and `seed_arena`, including safe database scoping, reusable fixtures, the demo question bank and owner-only local credential receipts. The original temporary preview database had been cleared; a fresh preview was created through the real services. Two new tests verify the preview guard and reuse behavior.

Final responsive QA also corrected large-arena overview framing to keep bases clear of HUD panels. Mobile overview collapses the minimap; desktop framing reserves its sidebar. Two frontend regressions cover unobstructed world bounds and unchanged four-team overview, bringing the current totals to 136 backend and 30 frontend tests.

The persistent preview was also verified through its live HTTP/WebSocket path on 2026-10-17: PREPARATION → BUILD_AND_SCOUT → WAR, then combat round 1 with 1,221 events and exactly one +10 passive-income award for the player team. Mobile team search returned team 19 and selected its base correctly; the expired-question overlay was checked. The final desktop and mobile overview screenshots show all twenty bases inside the usable camera area.
