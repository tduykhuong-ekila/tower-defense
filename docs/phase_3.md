# Phase 3 — Economy & Units

> Nguồn: `GDD_PRD.md` §7, §8, §9.3–9.4 (xác thực), §13 (FR-05, FR-06), §14.7, §19.7–19.11, §24, §28 (Scenario D).
> Phụ thuộc: Phase 1, Phase 2.

## 1. Mục tiêu

Đội có thể chi coin để deploy quân, xây trụ, nâng cấp, sửa chữa — tất cả được kiểm tra phía server. **Deliverable:** *teams can spend coins and prepare for combat.*

Chưa cần combat engine; các hành động tạo/ghi nhận trạng thái entity, sẵn sàng cho Phase 4 xử lý.

## 2. Backend

### 2.1. Models
- [x] `UnitType`: `code, name, category (UNIT | TOWER | SPECIAL), description, base_stats (JSON validated), cost, is_starter, is_unlockable, is_active, prerequisites`.
- [x] `GameEntity`: `match, team, unit_type, entity_kind, current_hp, current_shield, level, status, current_node_id, target_team_id, target_node_id, created_at, destroyed_at`.
- [x] `GameAction`: `match, team, actor, action_type, payload, status, idempotency_key, created_at, resolved_at, failure_reason`; unique `(team, idempotency_key)`.
- [x] `CoinTransaction`: `match, team, amount (+/−), transaction_type, reference_type, reference_id, balance_after, created_at`.
- [x] Ràng buộc DB: `coins >= 0` (CheckConstraint).

### 2.2. Seed `UnitType` theo §8 (toàn bộ giá trị là config, có thể chỉnh)
- [x] Starter: **Infantry** (15c, HP 40, DMG 10, move 1, range 1), **Machine Gun Tower** (25c, HP 100, DMG 15, range 2).
- [x] Unlockable units: **Tank** (35c, HP 120, DMG 25, range 1), **Artillery** (45c, HP 45, DMG 40, range 3).
- [x] Unlockable structures: **Cannon Tower** (40c, HP 150, DMG 30, range 3), **Shield Generator** (30c, HP 100, shield 40, cooldown 2 round).
- [x] Special actions: **Repair Base** (20c, +50 HP), **Upgrade Tower** (25c, +25% damage, 1 lần/tower), **Scout** (10c), **EMP** (30c, vô hiệu hoá 1 tower 1 round).
- [x] Khi match bắt đầu: tạo `TeamUnlock` cho các starter unit của mỗi đội (host có thể cấu hình starter khác).
- [x] Cho phép host bật/tắt từng special action và chỉnh giá/stats trong config match (§7.4).

### 2.3. `EconomyService`
- [x] `credit(team, amount, type, ref)` và `debit(team, amount, type, ref)` chạy `select_for_update` + `transaction.atomic`; ghi `CoinTransaction` với `balance_after`.
- [x] `debit` thất bại khi không đủ coin → không đổi số dư (§7.3).
- [x] Passive income (10 coin/round hoàn tất, kể cả khi hết câu hỏi); hàm `award_passive_income(match)` để Phase 4 gọi; bật/tắt theo config; không chạy khi match paused.
- [x] Không có API chuyển coin giữa các đội.
- [x] Hợp nhất reward coin của Phase 2 để đi qua `EconomyService.credit`.

### 2.4. `UnitService` & `ConstructionService`
- [x] `deploy_unit`: kiểm tra match active + phase cho phép, team chưa bị loại, unit đã unlock và `is_active`, đủ coin, chưa vượt **5 active unit**, tối đa **1 unit mỗi action**, target hợp lệ (§9.4: đội khác, còn active, reachable).
- [x] `build_tower`: kiểm tra node thuộc lãnh thổ đội, node trống, chưa vượt **3 tower**, đã unlock, đủ coin, phase cho phép xây (§9.3). Lỗi trả thông điệp rõ ràng, **không trừ coin**.
- [x] `upgrade_tower`: 1 lần/tower, tăng damage ×1.25, lưu `level`.
- [x] `repair_base`: +50 HP không quá max, 1 lần/đội/round.
- [x] `scout`, `emp`: triển khai dạng đã **gated** theo config; dữ liệu Scout chỉ gồm unlocked units + structures của đối thủ, không lộ câu hỏi đang chờ (§8.4). EMP chỉ nhắm tower, không nhắm base. *Triển khai sau cùng, chỉ khi các action lõi ổn định (§8.4).*
- [x] Entity bị phá không còn tính vào giới hạn capacity (§8.5).
- [x] Mọi action ghi `GameAction` và hỗ trợ `idempotency_key`: gửi lại cùng key không tạo entity hay trừ tiền lần hai.
- [x] Việc trừ coin + tạo entity nằm trong **một transaction**.
- [x] Action đã chấp nhận được xếp hàng cho round hiện tại (`QUEUED`); trừ coin theo bước 3 của chuỗi §10.1 hoặc trừ ngay khi accept — **chọn một cách và ghi vào `design_decisions.md`** (khuyến nghị: reserve/trừ ngay khi accept để UI hiển thị số dư đúng, hoàn tiền nếu action bị reject lúc resolve).
- [x] Map data tối thiểu để validate node: bảng/JSON `MapDefinition` (nodes, lanes, tower slots, ownership). Bản đầy đủ ở Phase 4.

### 2.5. API
- [x] `POST /matches/{id}/actions/deploy/`
- [x] `POST /matches/{id}/actions/build/`
- [x] `POST /matches/{id}/actions/upgrade/`
- [x] `POST /matches/{id}/actions/repair/`
- [x] `POST /matches/{id}/actions/scout/` *(tuỳ chọn, sau cùng)*
- [x] `POST /matches/{id}/actions/emp/` *(tuỳ chọn, sau cùng)*
- [x] `GET /matches/{id}/teams/{team_id}/state/` — trạng thái đội (coins, unlocks, entities, limits) chỉ cho thành viên đội.
- [x] Mỗi endpoint kiểm tra role, team membership, match status, phase, action eligibility.

## 3. Frontend

- [x] **Unit Selection** (§14.7): grid với icon, name, category, description, HP, damage, range, cost; phân biệt 6 trạng thái: *Locked, Available to unlock, Unlocked & affordable, Unlocked but unaffordable, Deployed/constructed, Destroyed*.
- [x] Side panel: danh sách unit/tower, chọn target, construction options, special actions.
- [x] Chọn node xây tower (tạm bằng grid/list; Phaser ở Phase 5).
- [x] Hiển thị số dư coin, lỗi từ server (insufficient coins, limit reached, invalid node…).
- [x] Types: `unit.ts`; client chỉ hiển thị giá do server cung cấp, **không tính giá phía client**.
- [x] Sinh idempotency key cho mỗi action; chống double-click.

## 4. Tests

- [x] Coin balance không âm; failed purchase giữ nguyên số dư.
- [x] Unit capacity (5) và tower capacity (3); unit chết giải phóng slot.
- [x] Locked unit không deploy được; node không hợp lệ/đã chiếm bị từ chối không trừ coin.
- [x] Target validation: không target đội mình, đội bị loại.
- [x] Repair không vượt max HP, tối đa 1 lần/round; upgrade tối đa 1 lần/tower.
- [x] **Scenario D**: thiếu coin → bị từ chối, không tạo unit, số dư giữ nguyên.
- [x] Duplicate request (cùng idempotency key) → không trừ hai lần/không tạo entity thứ hai.
- [x] Concurrent: hai request cùng tiêu một số coin → chỉ một thành công.
- [x] `CoinTransaction` tổng hợp khớp số dư (audit).
- [x] Passive income đúng một lần/round, không chạy khi pause.

## 5. Tiêu chí hoàn thành

- [x] Đội có thể unlock → mua → deploy/xây trong UI; số dư và giới hạn luôn do server quyết định.
- [x] Lịch sử `CoinTransaction` và `GameAction` truy vết đầy đủ.
- [x] Test Phase 3 chạy và xanh; không có rule bị để TODO/mock.
