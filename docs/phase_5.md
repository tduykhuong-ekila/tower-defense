# Phase 5 — Realtime Synchronization & Game Board

> Nguồn: `GDD_PRD.md` §13 (FR-02, FR-08), §14.4, §16.3, §21, §22, §25, §28 (Scenario G).
> Phụ thuộc: Phase 1–4.

## 1. Mục tiêu

Nhiều đội chơi cùng một trận qua trình duyệt theo thời gian thực. **Deliverable:** *multiple teams can play the same match in realtime.*

## 2. Backend — Django Channels

### 2.1. Hạ tầng
- [x] Cấu hình ASGI (`ProtocolTypeRouter`, `URLRouter`), Channels layer Redis.
- [x] Route `/ws/matches/{match_id}/` (`realtime/routing.py`).
- [x] Group: `match.{id}` (broadcast công khai), `match.{id}.team.{team_id}` (thông tin riêng đội), `match.{id}.host`.

### 2.2. Authentication & Authorization cho WebSocket
- [x] Xác thực bằng participant token/host session khi connect (middleware); từ chối kết nối không hợp lệ.
- [x] Xác định role + team của kết nối; spectator chỉ nhận, không gửi action ghi trạng thái.
- [x] Thông tin riêng đội (coin, câu hỏi, pending reward) chỉ gửi vào group của đội đó.
- [x] Chống giả mạo `team_id`/`actor` trong message — luôn lấy từ credential đã xác thực.

### 2.3. Event system (`realtime/events.py`, `RealtimeService`)
- [x] Envelope chuẩn (§21): `event_id, match_id, event_type, sequence_number, server_timestamp, payload`.
- [x] `sequence_number` tăng đơn điệu theo match, lấy từ `MatchEvent` (một nguồn sự thật, ghi DB **trước** khi broadcast, dùng `transaction.on_commit`).
- [x] Server messages: `MATCH_STATE_SNAPSHOT, MATCH_PHASE_CHANGED, QUESTION_ASSIGNED, ANSWER_RESULT, REWARD_OPTIONS, REWARD_APPLIED, ACTION_ACCEPTED, ACTION_REJECTED, UNIT_DEPLOYED, TOWER_BUILT, COMBAT_RESOLVED, ENTITY_DESTROYED, BASE_DAMAGED, BASE_DESTROYED, COINS_UPDATED, LEADERBOARD_UPDATED, MATCH_PAUSED, MATCH_RESUMED, MATCH_ENDED`.
- [x] Client messages: `STATE_SYNC_REQUEST, ANSWER_SUBMITTED, REWARD_SELECTED, DEPLOY_REQUEST, BUILD_REQUEST, UPGRADE_REQUEST, REPAIR_REQUEST, TARGET_SELECTED, READY_CHANGED`.
- [x] **Consumer chỉ là adapter mỏng**: parse → xác thực → gọi service Phase 2–4 → trả `ACTION_ACCEPTED/REJECTED`. Không đặt luật game trong consumer (§16.2).
- [x] Mọi action ghi trạng thái nhận `idempotency_key`; trùng key → trả kết quả cũ, không tác dụng phụ.
- [x] HTTP vẫn là kênh fallback chuẩn cho action quan trọng; WebSocket và HTTP dùng chung service.
- [x] Gọi `RealtimeService` từ các service ở Phase 1–4 (phase change, answer result, reward, coin, deploy, build, combat, elimination, pause/resume, end).

### 2.4. Snapshot & Reconnection (§25)
- [x] `build_snapshot(match, viewer)`: dữ liệu theo quyền người xem (đội mình đầy đủ, đội khác chỉ phần công khai theo cấu hình visibility), kèm `sequence_number` hiện tại.
- [x] Reconnect: xác thực lại → kiểm tra membership → gửi snapshot → tiếp tục stream từ sequence hiện tại → khôi phục câu hỏi/pending reward nếu có.
- [x] Endpoint HTTP `GET /matches/{id}/events/?after_sequence=N` cho client bù event bị thiếu.
- [x] Mất kết nối không tự động pause trận; server vẫn sở hữu state (§25). Presence (online/offline) hiển thị trên Host dashboard.

## 3. Frontend

### 3.1. WebSocket client (`services/websocket.ts`)
- [x] Kết nối + auto-reconnect với exponential backoff, gửi `STATE_SYNC_REQUEST` sau khi reconnect.
- [x] Phát hiện **khoảng trống sequence** → yêu cầu snapshot mới (§21).
- [x] Loại bỏ event trùng bằng `event_id`/`sequence_number`; hiệu ứng UI không phát hai lần.
- [x] Hàng đợi action chờ kết nối; không replay action cũ sau reconnect.
- [x] Hiển thị trạng thái kết nối (connected / reconnecting / offline).

### 3.2. Store (`stores/matchStore.ts`)
- [x] Store đơn nguồn: `snapshot` + reducer áp dụng event theo thứ tự sequence.
- [x] Chỉ phản ánh state do server gửi; không tự tính kết quả (§10.5).

### 3.3. Battle Page (`BattlePage.tsx`, §14.4)
- [x] **Top bar**: match timer (đồng bộ theo server time), phase, tên đội, coin, base HP + shield.
- [x] **Center**: `PhaserGame.tsx` — battlefield, bases, fixed lanes, units di chuyển, towers, hiệu ứng tấn công/damage.
- [x] **Side panel**: chi tiết entity chọn, unit/tower khả dụng, construction, target selection, special actions.
- [x] **Bottom panel**: `CombatLog`, trạng thái câu hỏi, lịch sử action, mục tiêu hiện tại.
- [x] `TeamStatus`, `Leaderboard` component (FR-02): coin, HP, câu hỏi còn lại, unit/tower, target & trạng thái combat.
- [x] Question Modal + Reward Modal (Phase 2) nhận dữ liệu qua WebSocket.

### 3.4. Phaser
- [x] Scenes: `BootScene` (load asset), `BattleScene` (render theo snapshot), tách biệt khỏi React qua event bus/props.
- [x] Entities: base, tower, unit; sprite/animation di chuyển node-to-node, tấn công, nổ khi bị phá, thanh HP.
- [x] Hiển thị shield, highlight node xây hợp lệ, chọn target bằng click.
- [x] Hoạt ảnh phát lại từ `COMBAT_RESOLVED` (tween theo thứ tự event); trạng thái cuối luôn khớp snapshot server.
- [x] Chế độ **Spectator / màn hình lớn** (read-only, chữ lớn, độ tương phản cao) cho chiếu (§14.4, §3.4).
- [x] Responsive trên desktop và màn hình chiếu; asset được tạo/chọn thực tế, không placeholder.

### 3.5. Lobby realtime
- [x] Thay polling bằng WebSocket: thành viên join, ready, host start hiện tức thì.

## 4. Tests

- [x] WebSocket auth: token sai bị từ chối; spectator không gửi được action ghi.
- [x] Đội A không nhận được dữ liệu riêng của đội B.
- [x] Event có `sequence_number` tăng đều, không trùng; broadcast sau commit.
- [x] Duplicate message / idempotency key → không nhân đôi hiệu ứng.
- [x] **Scenario G**: đội mất kết nối, các đội khác tiếp tục; reconnect → snapshot đúng, không replay action cũ.
- [x] Phát hiện gap sequence → yêu cầu snapshot (frontend unit test).
- [x] Test integration: 4 client WebSocket (ví dụ `channels.testing.WebsocketCommunicator`) chơi một round và nhận cùng `COMBAT_RESOLVED`.
- [x] Frontend: typecheck, lint, test reducer của store.

## 5. Tiêu chí hoàn thành

- [x] ≥ 4 trình duyệt chơi cùng trận; thay đổi coin/HP/combat đồng bộ trong < 1s trên mạng nội bộ.
- [x] Refresh/đóng mở tab giữa trận khôi phục đúng trạng thái.
- [x] Battlefield Phaser hiển thị đúng state server, animation không làm lệch state.
- [x] Test Phase 5 đã chạy và xanh.
