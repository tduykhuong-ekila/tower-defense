# Phase 6 — Host Console & Results

> Nguồn: `GDD_PRD.md` §3.1, §13 (FR-09, FR-10), §14.8–14.9, §26.
> Phụ thuộc: Phase 1–5.

## 1. Mục tiêu

Host vận hành được toàn bộ trận đấu thật và mọi người xem được kết quả cuối. **Deliverable:** *the game can be operated during an actual team-building event.*

## 2. Backend

### 2.1. Host controls (FR-09)
- [x] Start / pause / resume / end qua API và WebSocket (dùng lại `MatchService`), mọi hành động được kiểm tra quyền host và ghi log.
- [x] Pause: dừng timer phase, question timer, round scheduler, passive income; đóng câu hỏi đang mở theo §11; resume khôi phục thời gian còn lại chính xác.
- [x] End sớm: finalize match, sinh `MatchResult` snapshot.
- [x] Skip/advance phase thủ công (admin override), có ghi `Administrative override` trong audit log.
- [x] Xử lý sự cố theo quy tắc được ghi nhận: kick/đổi đội participant, đóng câu hỏi bị kẹt, hoàn tác reward lỗi (nếu có, chỉ qua override có log).

### 2.2. Giám sát
- [x] Endpoint/WS feed cho host: team status table (coin, HP, shield, score, #unit/#tower), số câu hỏi còn lại, pending reward, online/offline từng đội, phase hiện tại.
- [x] `GET /matches/{id}/events/` hỗ trợ lọc theo `event_type`, phân trang theo `sequence_number`.
- [x] Combat log đọc từ `MatchEvent`.

### 2.3. Config trước trận
- [x] API cập nhật config (chỉ khi `LOBBY`), validate đầy đủ (§7.4), preview thay đổi cân bằng.
- [x] Quản lý câu hỏi và `UnitType` (giá, stats, bật/tắt unit/special action) qua API/Django admin cho host.
- [x] Preset cấu hình (ví dụ "Quick 15 phút", "Standard 30 phút", "Blitz 10 phút").

### 2.4. Results (FR-10)
- [x] `GET /matches/{id}/results/` trả `MatchResult` đã finalize: final rank, score, remaining base HP, enemy bases destroyed, damage dealt, correct answers, coins còn lại, surviving towers, match duration.
- [x] Kết quả chỉ được tạo một lần và không sửa (immutable).
- [x] Công bố `LEADERBOARD_UPDATED` / `MATCH_ENDED` kèm kết quả.
- [x] **Optional awards** (chỉ trình bày, không đổi điểm chính thức trừ khi bật config): Best Strategist, Best Defense, Best Comeback, Knowledge Champion, Mentor–Mentee Synergy. Định nghĩa rõ công thức mỗi award trong `docs/design_decisions.md`.
- [x] Rematch / return-to-lobby: tạo match mới giữ nguyên đội & config, hoặc reset trạng thái.

### 2.5. Audit logging (§26)
- [x] Ghi: match lifecycle, question assignment/result, reward claim, coin credit/debit, deploy, build, combat result, base destruction, administrative override.
- [x] Không log secret hay participant token.

## 3. Frontend

### 3.1. Host Dashboard (`HostDashboardPage.tsx`, §14.8)
- [x] Match controls (start/pause/resume/end), hiển thị phase & timer.
- [x] Team status table realtime, remaining questions, pending reward selections, coin, base HP.
- [x] Combat log/event log có lọc và tìm kiếm.
- [x] Panel cấu hình match (chỉ chỉnh khi lobby), preset.
- [x] Final result summary; xác nhận hai bước cho hành động nguy hiểm (end match, override).
- [x] Trạng thái online/offline mỗi đội.

### 3.2. Results Screen (`ResultsPage.tsx`, §14.9)
- [x] Thông báo đội thắng (hiệu ứng ăn mừng), bảng xếp hạng, score breakdown từng đội, thống kê, award badges, nút Rematch/Return to Lobby.
- [x] Phiên bản trình chiếu màn hình lớn.
- [x] Đội bị loại vẫn xuất hiện trong bảng xếp hạng.

### 3.3. Spectator
- [x] Giao diện spectator đầy đủ: bản đồ, leaderboard, event log; không có control thay đổi state.
- [x] Đội bị loại chuyển sang chế độ xem (§12.4).

## 4. Tests

- [x] Chỉ host điều khiển được lifecycle; participant bị từ chối.
- [x] Pause không làm timer/passive income/combat tiến; resume chạy tiếp đúng.
- [x] End sớm sinh đúng một `MatchResult`; gọi lại không tạo bản sao.
- [x] Ranking đúng thứ tự tie-break; đội bị loại vẫn có trong ranking.
- [x] Awards không đổi điểm chính thức khi config tắt.
- [x] Audit log có bản ghi cho mọi hành động host/override, không chứa token.
- [x] Frontend: render Host Dashboard/Results từ dữ liệu mẫu, typecheck, lint.

## 5. Tiêu chí hoàn thành

- [x] Host tổ chức trọn một trận mẫu (4 đội) chỉ bằng UI, không chỉnh DB thủ công.
- [x] Results screen và leaderboard khớp `MatchResult` đã lưu.
- [x] Test Phase 6 đã chạy và xanh.
