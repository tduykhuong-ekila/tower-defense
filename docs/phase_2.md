# Phase 2 — Questions & Rewards

> Nguồn: `GDD_PRD.md` §5, §6, §13 (FR-03, FR-04), §14.5–14.6, §19.4–19.8 (phần Question/Reward/Unlock), §24, §28 (Scenario A, B, C, E).
> Phụ thuộc: Phase 1.

## 1. Mục tiêu

Hoàn thiện vòng lặp **Answer Question → Select Reward**. **Deliverable:** *the complete question-to-reward loop works.*

> Không triển khai Action Token (rule §31.3). Trả lời đúng chỉ mở ra lựa chọn thưởng (coin hoặc unlock), không tự động tạo hành động chiến đấu.

## 2. Backend

### 2.1. Models
- [x] `Question`: `id, type, category, difficulty, content, options, answer_key, answer_validator_type, time_limit_seconds, explanation, is_active, created_at`.
- [x] `TeamQuestion`: `id, match, team, question, sequence_number, status, assigned_at, expires_at, submitted_at, is_correct`; unique `(match, team, sequence_number)` và unique `(match, team, question)`.
- [x] `RewardClaim`: `id, team_question, team, reward_type (COIN|UNLOCK), coin_amount, unlocked_unit_type, status, claimed_at`; **unique theo `team_question`**.
- [x] `UnitType` (khung tối thiểu để Unlock hoạt động; dữ liệu đầy đủ ở Phase 3) và `TeamUnlock` với unique `(team, unit_type)`.
- [x] Lưu ý: tích hợp `CoinTransaction` tối thiểu để thưởng coin được audit (đầy đủ ở Phase 3). Có thể tạo model ở phase này nếu thấy cần.

### 2.2. `QuestionService`
- [x] Gán câu hỏi theo từng đội (team-specific, độ khó tương đương), bảo đảm không trùng và công bằng giữa các đội.
- [x] Hỗ trợ loại: **multiple choice** và **short text**; kiến trúc validator mở rộng (`validators.py`) cho logic puzzle, memory challenge, decode.
- [x] Giới hạn `max_questions_per_team` (mặc định 8); từ chối giao thêm.
- [x] Mỗi câu chỉ được **một lần nộp** cuối cùng; hết giờ = sai (§5.3).
- [x] Timer độc lập với phase timer; đóng câu hỏi khi hết giờ hoặc khi host pause (§11).
- [x] Task nền/scheduler đóng câu hỏi hết hạn (`EXPIRED`) — không phụ thuộc client.
- [x] Serializer **không bao giờ** trả `answer_key`, `answer_validator_type` hay `explanation` trước khi nộp/đóng (§5.1, §19.4).
- [x] Ghi lịch sử câu hỏi (FR-03).

### 2.3. State machine thưởng (§6.5)
- [x] Trạng thái: `PENDING_QUESTION, ANSWER_SUBMITTED, ANSWER_CORRECT, ANSWER_INCORRECT, PENDING_REWARD, REWARD_CLAIMED, EXPIRED`.
- [x] Chỉ cho phép đúng các chuyển trạng thái trong §6.5; mọi chuyển khác ném lỗi.

### 2.4. `RewardService`
- [x] Sau đáp án đúng: tạo `PENDING_REWARD`, trả về `REWARD_OPTIONS` (số coin, danh sách unit eligible).
- [x] **Unlock eligibility** (§6.3): `is_unlockable`, không phải starter, chưa unlock, thoả prerequisite, có trong config match. Khi rỗng → option Unlock bị vô hiệu hoá (trả cờ `unlock_available=false` + thông điệp).
- [x] `claim_reward(team_question, reward_type, unit_type?, idempotency_key)`:
  - Chạy trong `transaction.atomic` với `select_for_update` trên `TeamQuestion`/`Team`.
  - Server tự xác định số coin; **bỏ qua mọi amount do client gửi**.
  - Từ chối: câu hỏi của đội khác, chưa trả lời đúng, đã claim, unlock không hợp lệ.
  - Gọi lại với cùng idempotency key hoặc claim lần 2 → không cấp thêm, trả kết quả cũ.
- [x] Reward grace period (mặc định 15s) khi phase kết thúc; hết hạn → `EXPIRED`, **không** tự cấp thưởng (§11).
- [x] Defeated/eliminated team không được trả lời hay claim (§12.4).

### 2.5. API
- [x] `GET /matches/{id}/questions/current/`
- [x] `POST /matches/{id}/questions/{question_id}/answer/`
- [x] `POST /matches/{id}/rewards/claim/` (body theo §20: `team_question_id`, `reward_type`, `unit_type_id`).
- [x] Mỗi request kiểm tra role, team membership, match status, phase.

### 2.6. Question bank & Admin
- [x] Django admin / API cho host quản lý câu hỏi (CRUD, bật/tắt).
- [x] Fixture/seed gồm ≥ 20 câu hỏi mẫu (multiple choice + text), phân loại độ khó.
- [x] Import câu hỏi từ JSON/CSV (tuỳ chọn).

## 3. Frontend

- [x] **Question Modal** (§14.5): nội dung, lựa chọn/ô nhập, countdown, Submit, trạng thái đang gửi, kết quả. Không hiển thị đáp án đúng trước khi nộp/hết hạn.
- [x] **Reward Selection Modal** (§14.6, §6.4): 2 card *Receive Coins* và *Unlock Unit*; Unlock bị disable + thông báo "All units unlocked. Receive coins to continue strengthening your base." khi không còn gì.
- [x] **Unlock Selection** (§6.4, §14.7): grid unit/structure eligible với name, icon, category, description, stats, vai trò chiến lược; chọn đúng 1 và xác nhận.
- [x] Chặn click lặp khi đang xử lý (disable + idempotency key sinh phía client).
- [x] Đồng hồ đếm ngược dựa trên `expires_at` từ server, đồng bộ lệch giờ client.
- [x] Types: `question.ts`, `reward.ts`.

## 4. Tests

- [x] Validate đáp án đúng/sai cho từng loại câu hỏi.
- [x] Câu hỏi hết hạn không thể trả lời; đã nộp không thể nộp lại.
- [x] Payload ban đầu không chứa đáp án (kiểm tra serializer).
- [x] Reward eligibility, unlock eligibility, tính coin reward.
- [x] **Scenario A**: đúng → chọn coin → +20 một lần, claim lại không cộng thêm.
- [x] **Scenario B**: đúng → unlock Tank → Tank unlocked, không trừ coin.
- [x] **Scenario C**: đã unlock hết → Unlock bị disable, coin vẫn nhận được; request unlock bị từ chối.
- [x] **Scenario E**: 2 request claim đồng thời → tối đa một reward (dùng `TransactionTestCase`/threads).
- [x] Claim thưởng của đội khác bị từ chối; vượt giới hạn câu hỏi bị từ chối.
- [x] Grace period: hết hạn không tự cấp thưởng.

## 5. Tiêu chí hoàn thành

- [x] Một đội nhận câu hỏi → trả lời → chọn thưởng → trạng thái cập nhật chính xác, qua UI.
- [x] Trả lời sai: không thưởng, không trừ coin, không unlock.
- [x] Các ràng buộc unique ở DB hoạt động (kiểm tra bằng test).
- [x] Toàn bộ test Phase 2 đã chạy và xanh.
