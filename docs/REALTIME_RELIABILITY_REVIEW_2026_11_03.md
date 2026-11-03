# Rà soát lỗi thiếu đơn vị đối thủ — 03/11/2026

**Cập nhật:** các đề xuất P1 dưới đây đã được triển khai sau rà soát. Kết quả và giới hạn kiểm thử nằm trong `docs/REALTIME_RECOVERY_FIX_2026_11_03.md`. Ba probe ban đầu đã được thay bằng acceptance test trong `frontend/tests/realtime-resilience.test.ts`; phần dưới giữ lại mô tả hành vi trước sửa.

## Phạm vi và kết luận

Đã đọc luồng Django Channels → WebSocketClient → Zustand → Phaser; kiểm tra container đang chạy và chạy test chẩn đoán. Chưa bắt được một phiên người chơi đang bị lỗi để xác định nguyên nhân trực tiếp của lần báo cáo này. Các phát hiện dưới đây là lỗ hổng hiện hữu, không phải khẳng định tất cả đã xảy ra trên phiên đó.

- Docker frontend/backend đang chạy ở cổng host 5175/8005; PostgreSQL và Redis báo healthy tại thời điểm kiểm tra.
- Checksum `consumers.py`, `realtime/services.py`, `settings/base.py` trong backend khớp source local.
- Hai bundle JS trong frontend container khớp bản `frontend/dist` local. Điều này không xác minh bundle trong bộ nhớ/cache của từng người chơi, hoặc mọi file source đều đã được build.
- Log backend đã đọc trong cửa sổ 45 phút gần nhất chỉ có startup/migration, chưa thấy lỗi Redis/broadcast. Không có log chi tiết đủ để chứng minh mọi client nhận được mọi sự kiện.
- Browser có tab game cũ ở localhost:5173 và tab hướng dẫn qua ngrok. Không có listener local ở 5173 khi kiểm tra; chưa xác minh đích của tunnel hay phiên người chơi gặp lỗi. Không thay đổi các tab.
- Chưa sửa logic game, restart container hoặc thay đổi dữ liệu trận đấu.

## Các hành vi đã tái hiện

Script ban đầu: `docs/qa/realtime-reliability-probes.test.ts` (đã được thay bằng acceptance test sau sửa). Đây là các probe xác nhận hành vi lỗi trước sửa; test pass lúc rà soát không có nghĩa lỗ hổng đã được sửa ở thời điểm đó.

### 1. Nhận sự kiện được tính như đã áp dụng thành công

`frontend/src/services/websocket.ts` tăng `lastSequenceNumber` trước khi dispatch; `emit()` chỉ log rồi nuốt exception của listener. `dispatch()` cũng đánh dấu `event_id` đã thấy trước khi biết store có cập nhật được không.

Probe: snapshot version 1 → listener xử lý TOWER_BUILT version 2 ném lỗi → PONG báo server version 2. Client vẫn giữ cursor 2 và không yêu cầu sửa trạng thái. Vì vậy phát hiện thiếu sequence không bao phủ lỗi áp dụng dữ liệu. Repair định kỳ có thể chữa lại nếu snapshot áp dụng thành công; không nên kết luận lỗi này luôn kéo dài vô hạn.

### 2. Snapshot lỗi vẫn được ghi nhận là phục hồi thành công

Nhánh MATCH_STATE_SNAPSHOT xóa trạng thái chờ, cập nhật cursor và `lastSnapshotAt` trước khi listener áp dụng snapshot. Probe cố tình làm listener snapshot lỗi: client vẫn hết pending, cập nhật thời gian đồng bộ và không yêu cầu phục hồi qua PONG cùng version.

Hai probe exception chứng minh cơ chế xử lý lỗi có vấn đề. Chưa chứng minh reducer đang ném exception trong trận thực tế.

### 3. Đồng bộ định kỳ chặn cả sự kiện liên tục hợp lệ

Mặc định cứ khoảng 30 giây client yêu cầu snapshot. `syncPending` dùng chung cho khởi tạo, mất sequence và repair định kỳ; khi bật, mọi delta có sequence được buffer, kể cả TOWER_BUILT/UNIT_DEPLOYED liên tục, không thiếu sự kiện.

Probe: snapshot 1 → requestSync → build 2 → deploy 3. Listener chưa nhận build/deploy, nhưng trạng thái vẫn connected. Khi snapshot 2 tới, snapshot thay thế build 2 và deploy 3 mới được phát. Đây là hành vi chờ phục hồi, không phải tự nó gây mất dữ liệu; snapshot chậm làm map đứng tạm thời. Timeout mặc định 8 giây dẫn tới reconnect nếu snapshot không tới, còn status chỉ báo trạng thái transport.

## Khoảng trống phục hồi và quan sát

- Backend đã có GET `/api/v1/matches/{id}/snapshot/` trả envelope có version và phân quyền. Frontend hiện không sử dụng endpoint này. Khi snapshot WebSocket timeout, client chỉ đóng và kết nối lại cùng transport; chưa có đường HTTP độc lập.
- Snapshot backend khóa row trận, tải graph, entities và dữ liệu viewer. Mỗi snapshot được BattlePage nhận còn kích hoạt REST refresh match/map/catalog/team state. Nhiều người chơi đồng bộ gần nhau có thể tạo tải lặp và tranh chấp lock; chưa đo được mức độ trên trận thực tế.
- Phaser bỏ qua entity nếu không tìm thấy `current_node_id` trong graph. Chưa có tín hiệu chẩn đoán gắn entity ID/node ID để phân biệt store có entity nhưng scene không tạo visual. Chưa tái hiện lỗi node không hợp lệ.
- Chưa có báo cáo đồng thời version server/transport/store, lý do sync, tuổi snapshot, buffer và các entity không có visual. Vì vậy test phục hồi hiện tại pass vẫn chưa đủ chẩn đoán lỗi người chơi.

## Đề xuất theo ưu tiên

### P1 — Áp dụng trạng thái có xác nhận

Đặt một bộ áp dụng authoritative state duy nhất ngoài lifecycle trang React. Chỉ tăng applied cursor và đánh dấu event thành công sau khi reducer hoàn tất. Tách observer/UI effect khỏi bước cập nhật store; lỗi animation không được chặn dữ liệu trận.

Nếu áp dụng thất bại: ghi match/event/version, giữ trạng thái cần phục hồi và yêu cầu snapshot có giới hạn retry. Snapshot chỉ được đánh dấu thành công sau khi store chấp nhận. Không dùng việc socket OPEN hoặc PONG cùng version để kết luận store đã đồng bộ.

### P1 — Phục hồi HTTP có version

Khi WebSocket snapshot timeout hoặc áp dụng lỗi, gọi endpoint snapshot hiện có với cùng thông tin xác thực, một request đang chạy cho mỗi trận, timeout/backoff và kiểm tra match ID. Đưa envelope HTTP qua cùng bộ áp dụng và điều phối cursor/buffer của WebSocket; không chỉ gọi `store.applySnapshot()` riêng lẻ, vì hai cursor có thể lệch nhau. Từ chối snapshot cũ, replay các delta mới hơn liên tục và hủy kết quả của trận đã rời.

### P1 — Tách đồng bộ thường kỳ khỏi phục hồi thiếu dữ liệu

Giữ buffer khi chưa có baseline hoặc thật sự thiếu sequence. Với kiểm tra thường kỳ, tiếp tục áp dụng delta liên tục; snapshot cũ hơn applied cursor phải được bỏ qua hoặc thay bằng kiểm tra nhẹ, tuyệt đối không rollback. Hiển thị trạng thái đang đồng bộ khi có baseline chưa hoàn tất, gap hoặc applied error.

### P2 — Giảm tải và phát hiện lệch map

- Thêm jitter cho kiểm tra định kỳ; tránh đồng loạt tải snapshot toàn bộ trận.
- Tránh gọi lại match/map/catalog sau mọi snapshot nếu metadata không đổi. Dùng version riêng cho map/catalog khi cần.
- Ghi telemetry có giới hạn: server/received/applied version, last successful snapshot, sync reason/duration, reconnect, buffer, lỗi reducer và entity thiếu node/visual. Không ghi token, câu trả lời hay thông tin riêng của đối thủ.
- Đối chiếu tập entity trong store với scene theo cùng revision, loại trừ đối tượng đang chết và vật thể bị ẩn có chủ đích. Entity thiếu visual cần reconcile lại; thiếu node cần kiểm tra/refetch map. Chỉ so số lượng tổng sẽ bỏ sót trường hợp số lượng bằng nhau nhưng ID khác.
- Nếu thêm manifest/hash board từ server, so sánh tại cùng version để tránh báo lệch giả trong lúc quân đang di chuyển.

## Kiểm chứng cần có trước triển khai

1. Chuyển ba probe thành acceptance test sau sửa: lỗi listener/snapshot phải phục hồi, đồng bộ thường kỳ không chặn build/deploy liên tục.
2. Hai client độc lập, cả hai thứ tự A/B xây/tạo quân, không có hành động tiếp theo; kiểm tra store và visual IDs của cả hai phía.
3. WebSocket còn mở nhưng cố tình không trả snapshot; HTTP vẫn hoạt động: board phải tự phục hồi mà không reload. Test thêm HTTP lỗi, snapshot cũ và chuyển trận khi request còn đang chạy.
4. Store có entity nhưng scene thiếu visual hoặc thiếu node: phân biệt được hai trường hợp và phục hồi phù hợp.
5. Chạy 4/8/20 đội qua nhiều chu kỳ repair, idle, tab nền/quay lại và mạng chập chờn. Đo p95 độ trễ build→store→visual, thời gian phục hồi, số snapshot và lock wait; mục tiêu ban đầu phục hồi trong 5 giây khi HTTP còn hoạt động, cần xác nhận bằng tải thực tế.

Đã chạy: `cd frontend && node --import tsx --test tests/realtime-recovery.test.ts ../docs/qa/realtime-reliability-probes.test.ts` — 12 test recovery hiện có và 3 probe đều pass. Không chạy lại browser multiplayer trong đợt rà soát này; các báo cáo browser cũ không được coi là bằng chứng cho phiên hiện tại.
