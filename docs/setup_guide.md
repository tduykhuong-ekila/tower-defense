# Tower Defense — Setup & Deployment Guide

> Target Audience: Developers, DevOps engineers, and Tournament Organizers.
> Source: `GDD_PRD.md` §30, §32, §33.

---

## 1. System Prerequisites

Before starting, ensure your system has the following installed:

| Tool | Minimum Version | Recommended | Purpose |
|------|-----------------|-------------|---------|
| **Docker & Docker Compose** | 24.0+ | Docker Desktop / Engine 26+ | Containerized runtime |
| **Python** (for local dev) | 3.12.0+ | 3.12.3+ | Backend runtime & testing |
| **Node.js** (for local dev) | 20.0.0+ | 20.12+ (LTS) | Frontend React & Vite build |
| **Git** | 2.30+ | Latest | Version control |

---

## 2. Quickstart Option A: Docker Compose (Recommended)

This single command spins up PostgreSQL, Redis, Daphne ASGI backend, and Nginx frontend in isolated containers:

### Step 1: Clone Repository & Configure Environment
```bash
git clone <repo-url> tower_defense
cd tower_defense

# Copy environment variables
cp .env.example .env
```

### Step 2: Launch Production Stack
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Step 3: Seed Sample Content & Demo Match
```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py seed_demo --reset
```

### Step 4: Access Applications
- **Web Application (Nginx):** [http://localhost](http://localhost) (or port 80)
- **Host Dashboard Direct:** [http://localhost/#/host](http://localhost/#/host)
- **Participant Access:** Enter room code `DEMO24` on the landing page.
- **Backend API Docs:** [http://localhost:8000/api/v1/health/](http://localhost:8000/api/v1/health/)

---

## 3. Quickstart Option B: Local Development Setup

If you prefer running backend and frontend locally for development:

### Step 1: Start Infrastructure Services
Use Docker to run PostgreSQL and Redis with non-conflicting host ports:
```bash
docker compose up -d postgres redis
```
*(Postgres will be available on `localhost:5433`, Redis on `localhost:6380`)*

### Step 2: Setup Backend Virtual Environment
```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements-dev.txt

# Run migrations
python manage.py migrate

# Seed standard units, questions bank, and demo match
python manage.py seed_demo --reset

# Start ASGI Daphne server
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

### Step 3: Setup Frontend
In another terminal:
```bash
cd frontend
npm install

# Start Vite dev server
npm run dev
```
Open [http://localhost:5173](http://localhost:5173).

---

## 4. Database Backup & Restore

Automated shell scripts are provided in `scripts/`:

### Creating a Backup
```bash
./scripts/backup_db.sh ./backups
```
Produces a compressed file: `./backups/db_backup_YYYYMMDD_HHMMSS.sql.gz`.

### Restoring a Backup
```bash
./scripts/restore_db.sh ./backups/db_backup_20261016_140000.sql.gz --force
```

---

## 5. Running Automated Tests

### Backend Tests & Coverage Report
```bash
cd backend
source .venv/bin/activate

# Run all 90 tests with code coverage report
pytest --cov=apps.rewards --cov=apps.economy --cov=apps.units --cov=apps.combat --cov-report=term-missing
```

### Frontend Unit Tests & Typecheck
```bash
cd frontend
npx tsc --noEmit
npm test
npm run build
```

---

## 6. Environment Variables Reference

| Variable | Default Value | Description |
|----------|---------------|-------------|
| `DEBUG` | `True` (dev) / `False` (prod) | Django debug mode |
| `SECRET_KEY` | *(Random string)* | Cryptographic signing secret |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Permitted HTTP host headers |
| `DATABASE_URL` | `postgres://...` | PostgreSQL connection URL |
| `REDIS_URL` | `redis://...` | Redis channel layer URL |
| `CORS_ALLOWED_ORIGINS`| `http://localhost:5173` | Permitted browser origins |
| `COLLECT_STATIC` | `1` (prod) | Automatically run collectstatic on boot |
| `ENABLE_HTTPS` | `false` | Enforce SSL redirect & HSTS when behind HTTPS domain |
