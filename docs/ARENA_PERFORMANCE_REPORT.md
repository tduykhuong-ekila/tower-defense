# Arena performance report

Measured locally on 2026-10-16. Raw measurements: `docs/arena-benchmark.json`. These are observed development results, not production capacity guarantees.

Environment: macOS-26.5.2-x86_64-i386-64bit. Python 3.12, Django 5.1, SQLite file database, one process and InMemoryChannelLayer. Five sequential combat rounds per scenario; real service paths create teams, mentor/mentee members, towers and units. The browser/backend build and QA share this machine, so timings include ordinary local contention.

Normal load uses five infantry and three towers per team. Near capacity uses thirty infantry and the three legal tower slots per team. The configurable twenty-tower ceiling does not create additional legal slots. Twenty near-capacity teams therefore create 660 entities. The existing unit limit of 30 is preserved.

| Teams | Players | Entities | Load | Init ms / SQL | Round median / max ms | Round SQL max | Snapshot ms / SQL | Snapshot bytes | Event bytes max |
|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 4 | 8 | 32 | normal | 792.51 / 970 | 38.65 / 107.47 | 14 | 16.79 / 6 | 20614 | 12584 |
| 4 | 8 | 132 | near | 2155.64 / 3370 | 146.44 / 218.62 | 15 | 18.2 / 6 | 39420 | 66832 |
| 8 | 16 | 64 | normal | 1376.09 / 1894 | 64.97 / 122.49 | 14 | 16.99 / 6 | 38135 | 25044 |
| 8 | 16 | 264 | near | 5088.81 / 6694 | 254.17 / 369.71 | 17 | 15.92 / 6 | 75742 | 136564 |
| 12 | 24 | 96 | normal | 1403.92 / 2818 | 82.43 / 125.29 | 14 | 11.36 / 6 | 56963 | 37220 |
| 12 | 24 | 396 | near | 4876.1 / 10018 | 372.27 / 575.27 | 18 | 31.55 / 6 | 113809 | 201862 |
| 16 | 64 | 128 | normal | 1991.89 / 3998 | 121.57 / 165.64 | 15 | 16.35 / 6 | 76154 | 49878 |
| 16 | 64 | 528 | near | 6847.04 / 13598 | 551.89 / 1200.15 | 20 | 34.0 / 6 | 152262 | 267058 |
| 20 | 80 | 160 | normal | 2601.05 / 4986 | 145.67 / 238.15 | 15 | 16.79 / 6 | 93131 | 62856 |
| 20 | 80 | 660 | near | 9405.42 / 16986 | 735.14 / 1391.16 | 21 | 58.17 / 6 | 188483 | 336872 |

Query counts include transaction statements. Fixtures start with a valid host-configured 10,000 coins per team to fill the board through real purchase services. Snapshot milliseconds measure ORM reads and payload construction; connection timings also include JSON encoding. Snapshot reads remain six queries in these timed fixtures (which have no active/pending-reward question) rather than growing per team. Active questions and reward eligibility can add serializer queries; active-question recovery is tested separately. Bulk writes split into extra statements at SQLite parameter limits. Snapshot bytes are uncompressed UTF-8 JSON for one team viewer. The map is included; snapshots are recovery messages and events are the regular update stream.

| Teams / load | Clients | Initial snapshot median / max ms | In-process fanout median / max ms | CPU seconds (whole scenario) | Process peak RSS MiB |
|---|---:|---:|---:|---:|---:|
| 4 / normal | 11 | 99.95 / 143.35 | 5.54 / 5.66 | 0.993 | 84.9 |
| 4 / near | 11 | 164.01 / 249.47 | 5.6 / 5.72 | 2.727 | 87.6 |
| 8 / normal | 19 | 160.84 / 257.66 | 7.6 / 7.98 | 1.69 | 88.4 |
| 8 / near | 19 | 233.53 / 436.51 | 7.72 / 7.99 | 5.198 | 94.9 |
| 12 / normal | 27 | 233.93 / 402.27 | 8.33 / 9.41 | 2.205 | 98.1 |
| 12 / near | 27 | 472.37 / 810.68 | 9.1 / 9.5 | 7.256 | 105.8 |
| 16 / normal | 67 | 947.79 / 1583.23 | 20.33 / 21.8 | 4.004 | 110.3 |
| 16 / near | 67 | 1439.88 / 2657.55 | 16.19 / 17.79 | 11.766 | 110.3 |
| 20 / normal | 83 | 1026.67 / 1875.71 | 24.78 / 26.7 | 5.144 | 112.1 |
| 20 / near | 83 | 2036.88 / 3840.14 | 19.91 / 21.94 | 15.408 | 116.9 |

Connection measurements use real authenticated ASGI consumers via `WebsocketCommunicator`. They include snapshot generation and JSON serialization. Fanout is the elapsed time from recording a public event to all connected consumers receiving it. It excludes TCP, TLS, Redis and external network latency. CPU time includes fixture creation, five rounds and connection tests; peak RSS is cumulative for the benchmark process, not per-client memory.

Twenty normal teams resolve well within the default thirty-second combat window. At 660 entities, the measured sub-second round cost is higher and reconnect storms take seconds because snapshot work queues. Deployments should stagger reconnects (the existing client uses jitter), use PostgreSQL/Redis and repeat this test against their own hardware. No 60-FPS guarantee or internet-scale latency claim follows from these measurements.

Reproduce against a disposable database configured with the test InMemoryChannelLayer:

```sh
cd backend
python manage.py migrate --settings=your_disposable_settings
python manage.py benchmark_arena --settings=your_disposable_settings --output ../docs/arena-benchmark.json
```

The command creates measurement matches and deletes those matches after each successful sample. `--teams 20 --keep` retains fixtures for browser inspection. Do not point it at a production database. Browser measurements and visual QA are recorded below after running the actual battle page.

## Browser measurements

Raw DOM telemetry: `arena-browser-measurements.json`. Those timing samples were captured on 2026-10-16, before the 2026-10-17 overview-framing adjustment; the table is a dated baseline, not a new timing run of that camera adjustment. The reproducible dev fixture is `frontend/tests/fixtures/performance.html?code=ROOMCODE&width=1280&height=720`. It joins through the real spectator endpoint, embeds the real battle page and contains no tokens. Measurements below use a 1280×720 in-app Chromium canvas, one active game scene and near-capacity fixtures before combat. FPS is actual scene update count per wall-clock second. Frame p95/max are raw wall-clock intervals in that sampling window; slow frames count intervals over 33.4 ms since scene creation. These are sampled observations, not a sustained performance certification.

| Teams | Entities retained | Visible individual entities | FPS sample | Frame p95 / max ms | Slow frames since load | Scene objects | RGBA texture estimate MiB |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 132 | 132 | 99 | 11.4 / 15.9 | 1 | 524 | 11.1 |
| 8 | 264 | 264 | 100 | 11 / 11.1 | 1 | 861 | 14.9 |
| 12 | 396 | 36 | 100 | 11 / 11.3 | 5 | 1200 | 14.5 |
| 16 | 528 | 48 | 100 | 11.4 / 13.2 | 1 | 1474 | 14.3 |
| 20 | 660 | 60 | 100 | 10.9 / 13.2 | 4 | 1864 | 14.2 |

Low zoom replaces troops with stack badges from 12 teams upward in these viewport fits; this is why the visible sprite count drops while all entities remain in state. Scene objects include top-level containers, static scenery and overlays, not every nested child. Texture memory estimates source width × height × four bytes and excludes GPU driver overhead, mipmaps and internal text allocations.

An exploratory central combat sample with two simultaneously rendering test scenes fell to 37–41 FPS and accumulated long frames. It is retained in the raw observations rather than hidden. Use a single active scene for comparisons, and validate dense central combat on target hardware; the steady overview samples do not establish a sustained 60-FPS combat guarantee. Actual local HTTP rounds were also played with 1,221 / 621 / 1,301 / 547 events across rounds 1–4, including real movement, damage and destruction.

Validation: 136 backend tests and 30 frontend tests pass (rechecked on 2026-10-17); TypeScript and production build pass, Ruff passes, migration-state check reports no changes. The Phaser battle bundle is about 1.58 MB raw / 370 KB gzip and remains lazy-loaded; Vite reports its existing large-chunk warning. The game artwork directory is about 532 KiB on disk.

Responsive QA on 2026-10-17 covers the real page at 390×844 and 1366×900. Expanded-arena overview framing reserves the HUD area and desktop minimap space; mobile overview collapses the minimap to expose the main map. Camera bounds include the requested offset so Phaser cannot clamp the arena back under those panels. The legacy four-team framing is retained and regression tested. Saved proof is under `docs/screenshots/arena-20-mobile*.png` and `arena-20-desktop.png`.
