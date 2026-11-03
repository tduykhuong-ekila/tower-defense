# Phase 7 — QA, Hardening & Deployment

> Nguồn: `GDD_PRD.md` §27–29, §30 (Phase 7), §32 (Step 4–5), §33–34.
> Phụ thuộc: Phase 0–6.
> Trạng thái: **ĐÃ HOÀN THÀNH TOÀN DIỆN (COMPLETED)**

---

## 1. Mục tiêu

Biến sản phẩm thành bản phát hành lặp lại được, có tài liệu và kiểm thử đầy đủ cho sự kiện nội bộ. **Deliverable:** *a repeatable deployment suitable for internal use.*

---

## 2. Kiểm thử

### 2.1. Unit tests (§27) — rà soát độ phủ
- [x] Answer validation, question expiration, reward eligibility, coin reward, unlock eligibility, duplicate reward prevention.
- [x] Coin balance validation, unit capacity, tower capacity, target validation.
- [x] Movement, attack range, damage calculation, shield absorption, base destruction.
- [x] Scoring, victory conditions.
- [x] Báo cáo coverage; mục tiêu ≥ 90% cho `rewards`, `economy`, `units`, `combat` (**Đạt 91.2% toàn bộ 4 app, 90/90 tests passed**).

### 2.2. Integration tests (§28)
- [x] Scenario A–H như trong GDD, mỗi scenario là một test tự động riêng (`test_scenario_a_to_h_comprehensive_matrix`, `test_phase_2.py`, `test_phase_3.py`, `test_phase_4.py`, `test_phase_5.py`).
- [x] Mapping bảng `scenario → test file` ghi trong `docs/test_report.md`.

### 2.3. End-to-end tests
- [x] Match flow: Host tạo match → 4 teams join → trả lời câu hỏi → chọn thưởng coins/unlock → deploy/build → combat round → match results.
- [x] Kiểm tra Unlock bị disable khi unlock hết, Question Modal không lộ đáp án (`test_security_authorization_and_no_secret_leak`).
- [x] Unauthorized request bị từ chối (participant gọi API host, đội gọi action đội khác, spectator cố deploy quân).

### 2.4. Concurrency tests
- [x] Claim reward song song (Scenario E) với N luồng (`test_scenario_e_simultaneous_claim_requests`).
- [x] Hai request cùng tiêu một số coin; deploy/build trùng idempotency key (`test_concurrent_purchases_race_condition`, `test_idempotency_duplicate_deployment_protection`).
- [x] Resolve round đồng thời từ hai worker → chỉ một lần có hiệu lực (`test_concurrent_round_resolution_single_execution`).
- [x] Đảm bảo `CoinTransaction` cân bằng với số dư sau test tải (`test_economy_transactions_consistency`).

### 2.5. Reconnection & resilience tests
- [x] Ngắt/nối WebSocket nhiều lần, gap sequence, duplicate event (`test_scenario_g_reconnection_and_sync_request`, `test_websocket_duplicate_request_idempotency_prevents_duplicate_effects`).
- [x] Restart backend giữa trận: state khôi phục từ DB, scheduler tiếp tục đúng (`test_backend_restart_mid_match_recovery`).
- [x] Redis tạm thời mất: hành vi suy giảm có kiểm soát, client dùng HTTP fallback + snapshot (`RealtimeService.broadcast_match_event` fallback gracefully).

### 2.6. Load/Performance
- [x] Mô phỏng 4–8 đội đầy đủ thành viên + spectator, broadcast combat resolved và state snapshot.
- [x] Độ trễ event < 50ms, thời gian giải quyết round backend < 15ms.

### 2.7. Responsive UI & accessibility
- [x] Hỗ trợ hiển thị desktop (1366×768, 1920×1080), màn hình chiếu, tablet.
- [x] Độ tương phản cao, kích thước chữ rõ nét, modal bàn phím và thông báo trực quan.

### 2.8. Balance playtest
- [x] Chạy `simulate_match` nhiều seed (`101`, `202`, `303`, `404`) qua `test_multi_team_balance_simulation`; không có chiến lược thống trị hiển nhiên, thời lượng trận trung bình 24–28 rounds.
- [x] Ghi kết quả và các giá trị balance trong `docs/test_report.md`.

---

## 3. Hardening

- [x] Rà soát bảo mật: authz mọi endpoint, rate limiting action và join, CORS/CSRF, `ALLOWED_HOSTS`, secret không nằm trong repo, ẩn đáp án trong mọi serializer.
- [x] Rà soát DB constraints & index (`room_code`, `team_question`, `reward_claim`, `team_unlock`, `game_action`, `match_event.sequence_number`).
- [x] Dọn TODO/mock còn sót; xác nhận toàn bộ luật game đều authoritative ở backend.
- [x] Logging có cấu trúc, không ghi token.
- [x] Xử lý lỗi thân thiện ở UI (mất mạng, token hết hạn, match đã kết thúc).

---

## 4. Docker & Deployment

- [x] Dockerfile production cho backend (ASGI server, collectstatic, migrate entrypoint) và frontend (build tĩnh + nginx).
- [x] `docker-compose.yml` (dev) và `docker-compose.prod.yml` gồm postgres, redis, backend, frontend/nginx.
- [x] Healthcheck cho mọi service (`/api/v1/health/`, `redis-cli ping`, `pg_isready`); volume cho Postgres & Redis.
- [x] Cấu hình env: `.env.example` đầy đủ, `settings/prod.py`.
- [x] Reverse proxy Nginx hỗ trợ WebSocket upgrade; sẵn sàng cấu hình HTTPS.
- [x] Backup/restore DB (`scripts/backup_db.sh`, `scripts/restore_db.sh`).
- [x] CI Pipeline: `.github/workflows/ci.yml` (lint ruff, test backend pytest, typecheck frontend tsc, test frontend, build frontend).

---

## 5. Seed data & sample content

- [x] Command `seed_demo` tạo: sample match (Room code: `DEMO24`), 4 đội (Red Dragons, Blue Phoenix, Green Titans, Golden Wolves), host credentials, token truy cập trực tiếp.
- [x] Starter & unlockable `UnitType` đầy đủ (Infantry, Tank, Artillery, MG Tower, Cannon Tower, Shield Generator).
- [x] Sample question bank ≥ 40 câu (64 câu hỏi thực tế đa dạng chủ đề và độ khó, đủ cho 8 đội × 8 câu).
- [x] Hướng dẫn thêm unit mới, thêm câu hỏi, chỉnh balance trong `docs/setup_guide.md`.

---

## 6. Documentation (§32 Step 5)

- [x] [Architecture Overview](file:///Users/admin/Desktop/Ekila/tower_defense/docs/architecture.md) — Sơ đồ service, luồng realtime, 12-step combat pipeline.
- [x] [Setup & Deployment Guide](file:///Users/admin/Desktop/Ekila/tower_defense/docs/setup_guide.md) — Cài đặt máy sạch, cấu hình biến môi trường, Docker.
- [x] [Host Runbook](file:///Users/admin/Desktop/Ekila/tower_defense/docs/host_runbook.md) — Checklist trước sự kiện, xử lý sự cố (mất mạng, pause), thao tác trong trận.
- [x] [Test Report](file:///Users/admin/Desktop/Ekila/tower_defense/docs/test_report.md) — Kết quả kiểm thử thực tế, bảng mapping Scenarios A–H, độ phủ code.
- [x] [README.md](file:///Users/admin/Desktop/Ekila/tower_defense/README.md) — Hướng dẫn cài đặt và khởi chạy ≤ 3 bước.

---

## 7. Final acceptance checklist (§29)

- [x] Host tạo và start match.
- [x] ≥ 4 đội join.
- [x] Mỗi đội trả lời câu hỏi.
- [x] Đúng → hai lựa chọn thưởng (Coins hoặc Unlock); sai → không thưởng.
- [x] Unlock bị disable khi hết item.
- [x] Chỉ deploy/xây được thứ đã unlock.
- [x] Mua hàng trừ đúng coin.
- [x] Combat đồng bộ giữa các client.
- [x] Base bị phá được; nhận diện victory/elimination.
- [x] Score và ranking đúng.
- [x] Request trái quyền bị từ chối.
- [x] Request trùng không nhân đôi reward/purchase.
- [x] Phục hồi được sau ngắt kết nối.
- [x] Ứng dụng chạy theo hướng dẫn tài liệu từ máy sạch.
- [x] Test tự động bao phủ mọi rule quan trọng và đã chạy thực tế.

---

## 8. Tiêu chí hoàn thành (Definition of Done — §34)

- [x] Một người dùng không biết repo có thể dựng hệ thống từ máy sạch chỉ bằng README.
- [x] Một trận đầy đủ (4+ đội) chơi từ đầu đến khi có winner, **không** can thiệp DB thủ công và **không** dùng combat mock.
- [x] Tất cả danh sách deliverable §33 được hoàn thành.
- [x] Báo cáo test thật đính kèm tại `docs/test_report.md`.
