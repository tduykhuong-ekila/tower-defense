# Phase 1 — Domain Model & Match Lifecycle

> Nguồn: `GDD_PRD.md` §3, §4, §11, §13 (FR-01, FR-02 phần cơ bản), §19.1–19.3, §20 (Matches), §22.
> Phụ thuộc: Phase 0.

## 1. Mục tiêu

Host tạo được phòng, các đội và người chơi tham gia, và match chạy qua vòng đời trạng thái cơ bản. **Deliverable:** *teams can join a room and start a match.*

## 2. Backend

### 2.1. Models (UUID primary key)
- [x] `Match`: `id, room_code, name, status, phase, configuration (JSON), started_at, ended_at, created_by, created_at, updated_at`.
- [x] `Team`: `id, match, name, initial_base_hp, base_hp, base_shield, coins, score, status, created_at`.
- [x] `TeamMember`: `id, team, user (nullable) / guest participant id, display_name, role (MENTOR | MENTEE | HOST | SPECTATOR), joined_at, token_hash`.
- [x] Ràng buộc DB: `room_code` unique trong các match đang active (partial unique index), `base_hp >= 0`, `coins >= 0`, mỗi đội tối đa 1 Mentor.
- [x] Enum trạng thái: Match `LOBBY, ACTIVE, PAUSED, FINISHED`; Phase `LOBBY, PREPARATION, BUILD_AND_SCOUT, WAR, FINAL_ASSAULT, RESULTS`; Team `ACTIVE, ELIMINATED`.

### 2.2. Match Configuration
- [x] Schema cấu hình có validate (Pydantic hoặc DRF serializer) chứa toàn bộ giá trị §4.1 và §7.4: số đội, người/đội, base HP, coins khởi đầu, thời lượng phase, max questions, coin reward, passive income, giới hạn tower/unit, scoring weights, grace period reward (15s), `round_duration_seconds`, `fallback_policy`, visibility cho spectator, danh sách special action bật/tắt.
- [x] Default config nằm ở module backend riêng (`matches/defaults.py`), **không** hardcode trong frontend.
- [x] Validate toàn bộ config trước khi cho start (§7.4): không âm, min ≤ max, tổng thời lượng hợp lý.

### 2.3. `MatchService`
- [x] `create_match`, `generate_room_code` (ngắn, dễ đọc, tránh ký tự nhầm lẫn như `O/0`).
- [x] `create_team`, `assign_member`, `remove_member` (chỉ khi chưa start), `set_ready`.
- [x] `start_match` — kiểm tra đủ số đội tối thiểu, các đội ready, config hợp lệ; khởi tạo `base_hp`, `coins` từ config.
- [x] `pause_match`, `resume_match`, `end_match` (hook cho Phase 6).
- [x] State machine chuyển phase (`Lobby → Preparation → Build and Scout → War → Final Assault → Results`), từ chối chuyển không hợp lệ.
- [x] Mọi thay đổi trạng thái chạy trong `transaction.atomic`.

### 2.4. Authentication & Authorization (§22)
- [x] Host: tài khoản Django (session/JWT) hoặc host token riêng khi tạo match.
- [x] Guest participant: cấp token ngẫu nhiên không đoán được khi join, validate trên mọi request bảo vệ. **Room code một mình không được cấp quyền admin.**
- [x] Permission classes: `IsMatchHost`, `IsTeamMember`, `IsParticipantOfMatch`, `NotSpectatorForWrite`.
- [x] Participant không join được khi match đã khoá nhận người (trừ khi cấu hình cho phép).

### 2.5. API (`/api/v1/`)
- [x] `POST /matches/` — tạo match.
- [x] `GET /matches/{id}/` — metadata (ẩn dữ liệu nhạy cảm).
- [x] `POST /matches/{id}/join/` — join bằng room code + display name, trả participant token.
- [x] `POST /matches/{id}/start/`, `/pause/`, `/resume/`, `/end/` — chỉ host.
- [x] Endpoint quản trị lobby: tạo/sửa đội, gán/xoá thành viên, đổi role, cập nhật config (chỉ host, chỉ khi `LOBBY`).
- [x] Mọi endpoint ghi trạng thái kiểm tra role, team membership, status, phase.
- [x] `MatchEvent` tối thiểu cho lifecycle change (đầy đủ ở Phase 5).

## 3. Frontend (chức năng cơ bản, chưa realtime)

- [x] **Landing Page** (§14.1): Create Match, Join Match, How to Play.
- [x] **Join Match** (§14.2): room code, display name, trạng thái kết nối, thông báo lỗi.
- [x] **Lobby** (§14.3): room code, team cards, participant list, nhãn Mentor/Mentee, ready status, config summary, nút Start (chỉ host). Tạm thời dùng polling, thay bằng WebSocket ở Phase 5.
- [x] `services/api.ts` (client có auth header), `types/match.ts`.
- [x] Lưu participant token an toàn ở client (sessionStorage), xử lý token hết hạn.

## 4. Tests

- [x] Room code unique trong active rooms.
- [x] User không phải host không sửa được lobby / không start được match.
- [x] Host xoá được participant trước khi start; không xoá được sau khi start.
- [x] Join bị từ chối khi match đã đóng nhận người.
- [x] Start bị từ chối khi config không hợp lệ hoặc thiếu đội.
- [x] Chuyển phase không hợp lệ bị từ chối.
- [x] Guest token sai/hết hạn bị từ chối.

## 5. Tiêu chí hoàn thành

- [x] Host tạo match, nhận room code; ≥ 4 đội join và hiển thị trong lobby.
- [x] Host start thành công; match chuyển `ACTIVE` + `PREPARATION`; team có `base_hp`/`coins` đúng config.
- [x] Migration chạy sạch từ DB rỗng; test Phase 1 xanh (đã thực thi).
- [x] Dự án vẫn chạy được bằng `docker compose up`.
