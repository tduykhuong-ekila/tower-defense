# Tower Defense: Protect the Base

[![CI Pipeline](https://github.com/example/tower_defense/actions/workflows/ci.yml/badge.svg)](https://github.com/example/tower_defense/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)
![Django 5](https://img.shields.io/badge/django-5.1-green.svg)
![Channels](https://img.shields.io/badge/channels-4.0-darkgreen.svg)
![React 18](https://img.shields.io/badge/react-18.3-cyan.svg)
![Phaser 3](https://img.shields.io/badge/phaser-3.88-orange.svg)
![Coverage](https://img.shields.io/badge/coverage-91.2%25-brightgreen.svg)

**Tower Defense: Protect the Base** is a real-time multiplayer browser strategy game designed for team-building and Mentor–Mentee activities. Two to twenty teams compete simultaneously on a scalable symmetric star-ring map, answering technical quizzes to earn coins, unlock advanced military technology, deploy combat units, build defensive towers, and protect their base.

---

## 🚀 Quickstart Guide (≤ 3 Steps)

### Option 1: Docker Compose (Production Ready)

```bash
# 1. Clone repository & configure environment
cp .env.example .env

# 2. Build and launch all services in detached mode
docker compose -f docker-compose.prod.yml up -d --build

# 3. Seed demo match (Room code: DEMO24), standard units, and 64 questions
docker compose -f docker-compose.prod.yml exec backend python manage.py seed_demo --reset
```

- **Web Application:** [http://localhost](http://localhost) (Nginx reverse proxy on port 80)
- **Host Console:** [http://localhost/#/host](http://localhost/#/host)
- **Participant Access:** Enter room code `DEMO24` on the landing page.
- **Backend Health Check:** [http://localhost:8000/api/v1/health/](http://localhost:8000/api/v1/health/)

---

### Option 2: Local Development

```bash
# 1. Start Postgres & Redis containers
docker compose up -d postgres redis

# 2. Setup Backend (Terminal 1)
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo --reset
daphne -b 0.0.0.0 -p 8000 config.asgi:application

# 3. Setup Frontend (Terminal 2)
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

---

## 🧪 Testing & Verification

The codebase includes backend domain, multiplayer integration and frontend regression tests:

```bash
# Backend unit, integration, and coverage suite (≥90% target achieved)
cd backend
.venv/bin/pytest --cov=apps.rewards --cov=apps.economy --cov=apps.units --cov=apps.combat --cov-report=term-missing

# Backend lint check
.venv/bin/ruff check .

# Frontend typecheck & unit tests
cd frontend
npx tsc --noEmit
npm test
npm run build
```

Automatic turn-based combat, phase timing, pause/recovery, real PostgreSQL concurrency
checks and a disposable browser battle are documented in [Round lifecycle and verification](docs/ROUND_LIFECYCLE.md).
The later-round action investigation, fixes and repeatable full-match browser checks are
in [Full gameplay audit](docs/FULL_GAMEPLAY_FLOW_AUDIT.md) and
[Full gameplay implementation](docs/FULL_GAMEPLAY_FLOW_IMPLEMENTATION.md).
Rebuild existing backend/frontend Docker images after updating the source.

---

## 🛠 Database Operations & Maintenance

Automated scripts for PostgreSQL database backup and restore are available in `scripts/`:

```bash
# Create a timestamped, gzipped database backup
./scripts/backup_db.sh ./backups

# Restore from a backup dump
./scripts/restore_db.sh ./backups/db_backup_20261016_140000.sql.gz --force
```

---

## 📚 Technical Documentation

Complete documentation is located in the `docs/` directory:

- 🏗 [Architecture & System Design Guide](file:///Users/admin/Desktop/Ekila/tower_defense/docs/architecture.md) — Service topology, realtime sequence protocol, 12-step combat pipeline.
- 📖 [Setup & Deployment Guide](file:///Users/admin/Desktop/Ekila/tower_defense/docs/setup_guide.md) — Clean machine setup, environment configuration, Docker deployment.
- 📋 [Host & Tournament Runbook](file:///Users/admin/Desktop/Ekila/tower_defense/docs/host_runbook.md) — T-60m tournament checklist, in-match controls, troubleshooting.
- 📊 [QA Test Execution & Verification Report](file:///Users/admin/Desktop/Ekila/tower_defense/docs/test_report.md) — Real execution results, coverage breakdown, Scenario A–H matrix.
- 🎮 [Game Design Document & PRD](file:///Users/admin/Desktop/Ekila/tower_defense/docs/GDD_PRD.md) — Core mechanics, formulas, balance guidelines.
- 🏛 [Design Decisions (D1–D14)](file:///Users/admin/Desktop/Ekila/tower_defense/docs/design_decisions.md) — Authoritative architectural decisions.


## Woodland battlefield graphics

The battlefield now uses original cartoon illustrations, a Phaser woodland map, compact responsive HUD, server-confirmed unit/tower placement, graph-range previews and combat playback. See [implementation and verified checks](docs/GAME_GRAPHICS_IMPLEMENTATION.md), [architecture](docs/GAME_GRAPHICS_ARCHITECTURE.md), [audit](docs/GAME_GRAPHICS_AUDIT.md) and [asset manifest](docs/GAME_ASSET_MANIFEST.md). Rebuild existing Docker images to include these changes.

## Expanded multiplayer arena

Mentee and mentor can select an existing team or create and join their own team during initial join. Once in the lobby, only the host can create additional teams. Team members can copy a team invitation link that preselects the room and team for the recipient. See [participant teams and verification](docs/PARTICIPANT_TEAMS.md). Rebuild backend and frontend together; no new migration is needed.

Hosts can configure 2–20 teams while retaining shared mentor/mentee resources and existing four-team matches. See [implementation](docs/ARENA_20_TEAMS_IMPLEMENTATION.md), [multiplayer guide](docs/MULTIPLAYER_20_TEAMS.md), [map format](docs/ARENA_MAP_FORMAT.md) and [measured performance](docs/ARENA_PERFORMANCE_REPORT.md).

For a local preview that survives sessions, follow the [persistent preview commands](docs/MULTIPLAYER_20_TEAMS.md#persistent-local-preview). The dedicated database lives in `backend/.local/`; seed with `manage.py seed_arena --settings=config.settings.preview --teams 20 --near-capacity`.


## Continuous battles and realtime recovery

New rooms use 3 major rounds by default (host can choose 2), with preparation
120/180/180 seconds and 300-second continuous battles. The backend simulates at
5 Hz, persists partial road progress/cooldowns, and Phaser interpolates live
movement and attacks. New Infantry have 80 HP, move concurrently at speed 6,
and have unlimited paid deployment. Vehicles retain 100 HP, speed 4 and their
existing capacity/traffic rules. Movement uses the existing
hops/round-to-map-units/second conversion; per-hit damage remains at 0.5. Deploy/build/target actions
are available during Battle. Tower damage is retained; new matches award +30 coins for a correct-answer coin claim.

Apply backend migrations and rebuild/restart both applications before using the
new mode. Existing stored rooms retain their legacy rules. Production needs
PostgreSQL and a shared Redis channel layer; the SQLite preview uses one process.
See [implementation, configuration and measured verification](docs/REALTIME_COMBAT_IMPLEMENTATION.md),
[architecture](docs/CONTINUOUS_BATTLE_ARCHITECTURE.md), [events](docs/REALTIME_EVENT_CONTRACT.md)
and [balancing](docs/COMBAT_BALANCING.md).


The earlier [live Battle gameplay implementation](docs/LIVE_BATTLE_GAMEPLAY_IMPLEMENTATION.md)
and [audit](docs/LIVE_BATTLE_GAMEPLAY_AUDIT.md) document formation spacing, spawn
congestion, 100-HP migration without healing, Battle-time purchases and measured
multiplayer verification. Apply the new units data migration before restarting.


The earlier [formation and realtime update](docs/FORMATION_REALTIME_IMPLEMENTATION.md) added
compact body-based spacing, heartbeat/watchdog reconnection,
versioned snapshot recovery and measured two-client checks with 4/8/20 teams.
Rebuild and restart backend and frontend together to use the update.

The earlier [independent troop movement update](docs/TROOP_MOVEMENT_COMBAT_IMPLEMENTATION.md)
and [audit](docs/TROOP_MOVEMENT_COMBAT_AUDIT.md) describe free staging, the exact
previous speed setting of 2, independent combat, safe passing, saved-state compatibility,
and current backend/frontend/browser verification. No additional database migration is required.


The earlier [spawn, tower combat and realtime implementation](docs/SPAWN_TOWER_REALTIME_IMPLEMENTATION.md)
and [confirmed-cause audit](docs/SPAWN_TOWER_REALTIME_AUDIT.md) set speed to **4**,
use a compact rally area with one ordered exit per team, correct Infantry range
along tower-covered road spans, and restore a complete snapshot when entering
battle through an existing lobby socket. Both deployment orders, construction,
missed events and reconnect are verified with independent browser clients.
Rebuild/restart backend and frontend together; no new database migration is needed.


The current [Infantry gameplay update](docs/INFANTRY_GAMEPLAY_UPDATE.md) removes Infantry departure/leader queues and quantity caps, sets speed to **6** and new HP to **80**, preserves existing entity HP, and adds large-snapshot delivery and crowd rendering. Apply `units/0006_infantry_hp` and rebuild/restart both applications. The report includes 20-team tests at 400/1,000/2,000 Infantry and the measured server tick-budget limitations.

## Excel question banks and continuous team quizzes

Hosts can upload the supplied Vietnamese XLSX format, validate rows and preview answers
before creating a room. Uploaded rooms draw questions in random order without repeats
for each team, with independent persistent team progress. Answering and choosing +30 coins or a free unlock
are available throughout Preparation and Battle, without pausing combat.
Install the new backend dependencies, apply the questions/matches migrations and rebuild
both applications. See [implementation and verification](docs/QUESTION_BANK_IMPLEMENTATION.md),
[Excel schema](docs/QUESTION_BANK_EXCEL_SCHEMA.md), [API](docs/QUESTION_BANK_IMPORT_API.md)
and [continuous quiz rules](docs/CONTINUOUS_QUIZ_GAMEPLAY.md).

## Artillery, six defensive foundations and batch deployment

Long-Range Artillery now deploys with **70 HP** and **1.5-hop range** (previously 100 HP / 3 hops). Every 2–20-team arena has six validated defensive foundations, with six towers allowed by default. The battle panel supports troop quantities, total-cost previews and Max; the server commits each batch atomically with one debit and idempotent retries. Existing artillery instances retain their HP and range. Apply `units/0007_artillery_balance_and_six_slots` and rebuild/restart both applications. See [implementation, API, verification and measured limits](docs/ARTILLERY_TOWER_SLOTS_BATCH_DEPLOYMENT.md).

## Cannon range, parallel troops and roadside foundations

The latest update sets new Cannon Towers to **2-hop range**, new Artillery to **80 HP / speed 5** while retaining its **1.5-hop range**, and lets all mobile troops depart and advance independently. New rooms use six foundations per team moved closer to roads; existing rooms retain their versioned layout and built tower positions. Apply `units/0008_cannon_artillery_and_layout_version` before reseeding, then rebuild/restart both applications. See [implementation, compatibility and actual verification](docs/COMBAT_BALANCE_AND_TOWER_LAYOUT_UPDATE.md).

## Team upgrades, persistent quiz countdown and natural scenery

The NÂNG CẤP panel purchases team-wide levels 1–4 for Infantry, Tanks, Artillery and
all three defensive tower types. Existing and future entities share the level,
retain their HP percentage, and gain distinct equipment. The server validates
unlock, price, expected level and idempotency under the combat transaction lock.

A question starts on its first explicit opening. Its deadline continues after
closing or disconnecting. Reopening preserves the same question, including expired
results; only the separate Continue action advances it. Correct answers still grant
30 coins or one unlock, with existing earned/configured reward amounts preserved.
Seeded natural vegetation fills the expanded terrain while keeping roads, bases,
rallies and all six tower foundations clear.

Apply all backend migrations (`python manage.py migrate`) before restarting the
updated applications. See [upgrade design](docs/TEAM_WIDE_UPGRADE_DESIGN.md),
[implementation and QA](docs/TEAM_WIDE_UPGRADE_IMPLEMENTATION.md),
[quiz lifecycle](docs/QUIZ_COUNTDOWN_LIFECYCLE.md), and
[vegetation](docs/MAP_VEGETATION_UPDATE.md).


### Grid tower placement and stable upgrades

New rooms use server-authoritative square-grid construction with road, water, base, rally and territory protection; defensive tower quantity is now unlimited within affordable, valid owned space. Saved rooms retain legacy slots. Cannon Tower base damage is 20 (Lv.1–4: 20/22/24/27). Apply database migration `units.0012_cannon_damage` on deployment.

See [audit](docs/GRID_TOWER_PLACEMENT_AUDIT.md), [design](docs/GRID_TOWER_PLACEMENT_DESIGN.md), [implementation and test results](docs/GRID_TOWER_PLACEMENT_IMPLEMENTATION.md), and [upgrade modal fix](docs/UPGRADE_MODAL_STABILITY_FIX.md).


### Unlimited defensive towers and compact fortification cards

Defensive construction has no team-count cap or round quota. Every tower still costs its normal price and needs an unlocked type and valid, unoccupied owned footprint. Old numeric cap settings are ignored. Compact rank badges overlay reserved artwork space in CÔNG SỰ cards, with stable dimensions across levels and states. Physical targeting now uses a spatial broad phase while retaining exact range checks.

See [audit](docs/UNLIMITED_TOWERS_FORTIFICATION_AUDIT.md), [construction rules and measured QA](docs/UNLIMITED_TOWER_CONSTRUCTION.md), and [card redesign](docs/FORTIFICATION_CARD_REDESIGN.md). Earlier six-foundation/cap sections above describe historical versions; saved legacy layouts retain their positions. Deploy backend and frontend together. No additional migration is required for this change.

### Closer roadside towers and star level cards

New defensive towers reserve 96×96 pixels on the existing 32-pixel grid. Straight troop corridors and painted road curves now have separate clearance checks; saved reservations and exceptional vehicle offsets remain protected. Tower construction remains unlimited within valid owned space.

QUÂN ĐỘI and CÔNG SỰ share stable artwork, 1–3 filled SVG stars, name and price rows. Realtime team upgrade data updates cards without reopening a popup.

See [roadside clearance adjustment](docs/ROADSIDE_TOWER_CLEARANCE_ADJUSTMENT.md), [roadside refinement](docs/ROADSIDE_TOWER_PLACEMENT_REFINEMENT.md), and [card layout and visual QA](docs/ARMY_FORTIFICATION_CARD_LAYOUT_FIX.md).

### Three-star upgrades

Team-wide upgrades now stop at Level 3. See [Three-star upgrade system](docs/THREE_STAR_UPGRADE_SYSTEM.md) and [Level 4 data migration](docs/UPGRADE_LEVEL_MIGRATION.md). Deploy backend and frontend together, apply migrations, and reconnect active clients.


### Hướng dẫn người chơi bằng slide HTML

Mở [bộ slide Mentor & Mentee](docs/player-guide/index.html) để xem hướng dẫn tiếng Việt từ vào phòng, lập đội đến câu hỏi, xây dựng, chỉ huy và kết quả. File tự chứa ảnh chụp game có đánh dấu, dùng được offline. Xem [cách sử dụng](docs/player-guide/README.md).
