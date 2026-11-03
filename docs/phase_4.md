# Phase 4 — Combat Engine, Map, Victory & Scoring

> Nguồn: `GDD_PRD.md` §9, §10, §12, §13 (FR-07), §19.12–19.13, §28 (Scenario F, H).
> Phụ thuộc: Phase 1, 2, 3.

## 1. Mục tiêu

Xây engine chiến đấu theo lượt, **thuần server, deterministic**, mô phỏng được một trận hoàn chỉnh. **Deliverable:** *a complete server-authoritative battle can be simulated.*

Engine nên là domain logic thuần (không phụ thuộc WebSocket/HTTP) để test và mô phỏng headless được.

## 2. Backend

### 2.1. Map định nghĩa (`combat/map.py` hoặc `MapDefinition`)
- [x] Fixed-lane graph cho 4–8 đội: node, edge (lane), base node + spawn point mỗi đội, tower placement nodes theo lãnh thổ, central arena/shared lane section, node impassable (§9.1).
- [x] Map sinh theo số đội (template cho 4, 6, 8 đội hoặc generator đối xứng) và lưu trong config/JSON có validate.
- [x] Hàm tiện ích: `path(from, to)` xác định trước (không pathfinding phức tạp), `distance(node_a, node_b)`, `nodes_in_range(node, range)`, `attack_position(base)`.
- [x] Test map: mọi base reachable từ mọi spawn; không có node mồ côi.

### 2.2. `CombatEngine` (`combat/engine.py` + `movement.py`, `targeting.py`, `damage.py`, `scoring.py`)
- [x] Hàm chính `resolve_round(match_state) -> RoundResult` **thuần**, input là snapshot + action đã khoá, output là state mới + danh sách event.
- [x] Chuỗi xử lý đúng §10.1:
  1. Đóng planning phase (khoá action).
  2. Validate các action đã queue.
  3. Trừ coin cho action được chấp nhận (hoặc xác nhận khoản đã reserve ở Phase 3).
  4. Spawn unit mới.
  5. Áp dụng movement hợp lệ.
  6. Tower tấn công.
  7. Combat unit tấn công.
  8. Shield + base damage.
  9. Loại bỏ unit/structure bị phá.
  10. Kiểm tra elimination & victory.
  11. Passive income.
  12. Publish authoritative state (trả về event; broadcast ở Phase 5).
- [x] **Deterministic**: thứ tự xử lý cố định (sort theo team id, entity id, sequence); không dùng random hay thời gian thực trong engine; mọi tie-break có quy tắc (D5).
- [x] Ghi tài liệu các ngoại lệ cho ranged attack (Artillery range 3).

### 2.3. Movement (§9.2)
- [x] Unit đi theo predefined path tới target đã chọn; tốc độ = `movement` node/round.
- [x] Bị chặn bởi unit địch trên đường (blocking rule được định nghĩa rõ); không đi qua node impassable hay bỏ qua topology.
- [x] Target hợp lệ trong suốt hành trình: khi target bị phá/invalid → theo `fallback_policy` (idle hoặc retarget).

### 2.4. Targeting & Damage (§10.2–10.4)
- [x] Công thức: `final_damage = max(1, floor(base_damage * multiplier))`; multiplier mặc định 1.0, tower nâng cấp 1.25.
- [x] Tower: ưu tiên unit **gần base được bảo vệ nhất**, tie-break deterministic, chỉ bắn trong range, 1 lần/round; không bắn khi bị EMP.
- [x] Unit tấn công trong range của nó; Artillery không bắn xuyên barrier trừ khi map cho phép.
- [x] Không có armor/crit/splash/damage types (ngoài MVP).
- [x] Unit chạm attack position của base → gây damage cho base rồi **bị loại khỏi chiến trường** (§10.4).
- [x] Damage lên base: trừ **shield trước** rồi tới HP; HP không bao giờ < 0; HP = 0 → `ELIMINATED`.
- [x] **Shield Generator**: tạo shield 40 cho base, cooldown 2 round, không tạo mới khi shield cũ còn hiệu lực, duration cấu hình được.
- [x] Unit/structure bị phá không thể tấn công ở round sau.
- [x] Theo dõi `base_damage_dealt` và `bases_destroyed` cho từng đội (phục vụ scoring).

### 2.5. Round Scheduler
- [x] Vòng lặp round do server điều khiển: mở planning window → khoá → resolve → publish → income (task nền, ví dụ Celery/asyncio task hoặc management loop; chọn một cách và ghi quyết định).
- [x] Phase scheduler theo §11: Preparation 3', Build & Scout 7', War 12', Final Assault 5', Results 3'; host chỉnh được.
- [x] Pause: dừng timer, không resolve round, không phát passive income; resume tiếp tục đúng thời gian còn lại.
- [x] Idempotent: một round chỉ resolve một lần (khoá bằng row lock/số round).
- [x] Xử lý reconnect/duplicate message không làm đổi kết quả round đã khoá (§10.5).

### 2.6. Victory & Scoring (§12)
- [x] **Elimination victory**: chỉ còn một đội active → thắng ngay. Nhiều base bị phá cùng round → áp dụng simultaneous-elimination rule mặc định (so score → base HP → coins).
- [x] **Score victory** khi hết giờ, các trọng số lấy từ config: enemy base destroyed +100; mỗi 100 HP damage +10; mỗi 100 HP base còn lại +5; mỗi câu đúng +3; mỗi tower sống +5; mỗi 10 coin +1.
- [x] Không cộng trùng điểm destroy + damage cho cùng phần damage (có cap tuỳ cấu hình).
- [x] Tie-break: score → số base phá → base HP → coins → đồng hạng (§12.3).
- [x] Đội bị loại chuyển spectator, **vẫn nằm trong leaderboard** (§12.4).
- [x] `ScoringService.finalize_match` tạo `MatchResult` **immutable snapshot** (§19.13), chỉ tạo một lần.
- [x] `MatchEvent` lưu mọi event quan trọng với `sequence_number` tăng đơn điệu (§19.12).

### 2.7. Simulation tooling
- [x] Management command `simulate_match` chạy trận headless (bot ngẫu nhiên có seed) để kiểm tra tính ổn định và cân bằng.
- [x] Xuất log/JSON để so sánh deterministic giữa hai lần chạy với cùng seed.

## 3. Frontend (chuẩn bị cho Phase 5)

- [x] Định nghĩa types `combat.ts` (RoundResult, events, entity snapshot).
- [x] Trang debug nhẹ hiển thị kết quả `COMBAT_RESOLVED` dạng bảng/log để kiểm tra thủ công (có thể bỏ ở Phase 5).

## 4. Tests

- [x] Movement: đúng số node/round, bị chặn, không đi qua node impassable.
- [x] Attack range: không đánh ngoài range; destroyed unit không tấn công round sau.
- [x] Damage formula + multiplier 1.25; tối thiểu 1.
- [x] Shield absorption: shield trước, HP sau; HP không < 0; Shield cooldown.
- [x] Base destruction + elimination; simultaneous elimination.
- [x] Target invalid không nhận damage; fallback policy.
- [x] Scoring: từng thành phần + không double count + tie-break.
- [x] **Scenario F**: A deploy → di chuyển → tower B bắn → HP cập nhật → unit chết → base nhận damage.
- [x] **Scenario H**: base bị phá hoặc hết giờ → finalize → result snapshot duy nhất.
- [x] Determinism: cùng state + config chạy 100 lần → cùng kết quả.
- [x] Round resolve idempotent (gọi hai lần không nhân đôi hiệu ứng).
- [x] Pause không tăng passive income.

## 5. Tiêu chí hoàn thành

- [x] `simulate_match` chạy một trận đầy đủ 4–8 đội đến khi có winner mà không lỗi.
- [x] Kết quả deterministic và khớp với kỳ vọng thủ công ở Scenario F.
- [x] Test engine bao phủ mọi rule trong FR-07; tất cả đã chạy và xanh.
- [x] Không có luật chiến đấu nào nằm trong frontend hay consumer.
