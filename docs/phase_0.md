# Phase 0 — Repository Inspection, Scaffolding & Design Decisions

> Nguồn: `GDD_PRD.md` §15–18, §30 (Phase 0), §31–32.
> Phụ thuộc: không có. Đây là phase nền tảng.

## 1. Mục tiêu

Chuẩn hoá nền tảng kỹ thuật trước khi viết logic game: đánh giá repo hiện tại, dựng khung backend/frontend/infra chạy được, và chốt các điểm mơ hồ trong GDD để các phase sau không bị chặn.

**Hiện trạng repo (đã kiểm tra):** thư mục `tower_defense/` chỉ chứa `docs/`. Chưa có backend, frontend, Docker, DB hay authentication → đây là **greenfield**, phải khởi tạo từ đầu theo stack ở §15.

## 2. Phạm vi

### 2.1. Repository assessment
- [x] Ghi lại hiện trạng (greenfield) vào `docs/repo_assessment.md`.
- [x] Liệt kê phiên bản công cụ đang có trên máy: Python, Node, Docker, PostgreSQL, Redis.
- [x] Liệt kê rủi ro và giả định (xem mục 4).

### 2.2. Khởi tạo Backend (`backend/`)
- [x] Python 3.12 + Django + Django REST Framework + Django Channels + `channels-redis` + ASGI server (Daphne).
- [x] Cấu trúc `config/settings/{base,dev,prod,test}.py`, `urls.py`, `asgi.py`.
- [x] Tạo các app rỗng: `accounts`, `matches`, `teams`, `questions`, `rewards`, `economy`, `units`, `combat`, `realtime` (theo §17).
- [x] Cấu hình biến môi trường qua `.env` (`django-environ`) + `.env.example`.
- [x] Cấu hình pytest + `pytest-django`, linter (ruff) và formatter.
- [x] Endpoint health-check `GET /api/v1/health/`.

### 2.3. Khởi tạo Frontend (`frontend/`)
- [x] React + TypeScript + Vite.
- [x] Cài Phaser 3 (chỉ dùng cho battlefield — §15).
- [x] Cấu trúc thư mục theo §18: `pages/`, `components/game/`, `game/`, `services/`, `stores/`, `types/`.
- [x] Router với các trang: Landing, JoinMatch, Lobby, Battle, HostDashboard, Results.
- [x] State management nhẹ (Zustand).
- [x] TypeScript strict typecheck (`tsc`), Vite build; proxy dev tới backend.

### 2.4. Infrastructure
- [x] `docker-compose.yml`: `postgres`, `redis`, `backend`, `frontend`.
- [x] Backend dùng PostgreSQL + Redis (Channels layer) qua biến môi trường.
- [x] `README.md` gốc: cách chạy local trong ≤ 5 lệnh.

### 2.5. Chốt quyết định thiết kế
- [x] Ghi nhận 12 quyết định thiết kế D1–D12 vào `docs/design_decisions.md`.

## 3. Deliverables

- [x] `docs/repo_assessment.md`, `docs/design_decisions.md`.
- [x] Skeleton `backend/` và `frontend/` chạy được.
- [x] `docker-compose.yml` + `.env.example` + `README.md`.
- [x] Bảng traceability: mỗi FR (FR-01…FR-10) → module backend, màn hình, model, endpoint, WS event, test (theo §32 Step 2). Lưu `docs/traceability.md`.

## 4. Rủi ro & giả định

- Máy dev cần Docker; nếu không có, fallback dùng Postgres/Redis cài local hoặc SQLite in-memory cho test.
- Đã giải quyết xung đột cổng host: Postgres 5433:5432, Redis 6380:6379.
- Phaser chỉ dùng cho canvas; UI còn lại là React thuần.
- Balance value chỉ là provisional → nằm trong config/DB, không hardcode ở frontend.

## 5. Tiêu chí hoàn thành (Definition of Done)

- [x] `docker compose config` hợp lệ, cấu hình sẵn 4 service không lỗi.
- [x] `GET /api/v1/health/` trả 200; frontend hiển thị trang Landing & routes.
- [x] Redis Channels layer kết nối được (test ping tự động qua pytest).
- [x] `pytest`, `ruff`, `tsc`, và `vite build` đều chạy thành công 100% (thực sự đã thực thi).
- [x] Các quyết định D1–D12 đã được ghi lại đầy đủ.

