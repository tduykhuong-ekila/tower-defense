# Sửa đơn vị đối thủ có dữ liệu nhưng không hiển thị — 03/11/2026

## Nguyên nhân đã tái hiện

`BattleScene.createEntity()` tạo root với `alpha=0`, rồi tween lên 1 trong 300 ms.
Ba đường xử lý khác hủy toàn bộ tween của root: sửa vị trí trong `reconcile()`,
replay `UNIT_MOVED`, và `finishPlayback()` khi nhận snapshot/quay lại tab ngoài
live battle. Nếu xảy ra trước frame đầu tiên của hiệu ứng xuất hiện, root giữ
`alpha=0` mãi. Entity vẫn có trong store và `visuals`; snapshot tiếp theo không
tạo lại root, nên so ID hoặc số lượng đơn thuần không phát hiện được lỗi này.

Fixture Phaser thật đã tái hiện `alpha=0` trên cả sáu loại: bộ binh, xe tăng,
pháo, tháp súng máy, tháp đại bác và máy tạo giáp. Không khẳng định đây là
nguyên nhân duy nhất của mọi phiên người chơi từng báo lỗi.

## Bản sửa

Ba đường ngắt animation dùng chung `stopRootAnimation()`: sau khi hủy tween,
đối tượng còn sống trở về opacity/scale/angle hợp lệ. Giữ nguyên tween chết đang
chạy để callback dọn visual và trả bộ binh về pool hoàn tất. Snapshot live vẫn
giữ animation di chuyển như trước.

## Kiểm chứng

- Mở `frontend/tests/fixtures/entity-visibility.html` qua Vite: **8/8 PASS** trên
  Chrome, kiểm tra từng ID cùng root active/visible/alpha, scale và texture.
  Bao gồm snapshot ngắt xuất hiện; sửa root đã trong suốt; sửa vị trí; replay;
  snapshot live; pan ra/vào; dọn đối tượng chết khi pause/snapshot; tái dùng pool.
- Trước sửa, fixture xác nhận snapshot để cả sáu loại ở `alpha=0`; sửa vị trí
  và replay cũng làm xe/trụ bị trong suốt. Sau sửa không còn ID thiếu hiển thị.
- Nhóm test realtime recovery/resilience, store, continuous, infantry và movement:
  **43/43 PASS**.
- Toàn bộ `npm test`: **181/185 PASS**. Bốn lỗi artwork ở `star-level.test.ts`
  (3 test) và `team-upgrades-vegetation.test.ts` (1 test), cùng nhóm đã được ghi
  nhận trong báo cáo recovery trước; các file đó không thuộc bản sửa này.
- `npm run build`: PASS; `git diff --check`: PASS.

Fixture không cần backend hoặc dữ liệu trận thật. Đây là kiểm thử hiển thị trong
Phaser, không phải một lượt kiểm thử multiplayer qua ngrok hay benchmark mạng.

## Áp dụng local

Đã chạy `docker compose up -d --no-deps --build frontend`. Container frontend
đang Up ở cổng 5175; kiểm tra HTTP trong container xác nhận bundle
`BattlePage-DdXE0sdo.js` chứa `stopRootAnimation`. Trang đã mở cần tải lại một
lần để nhận bundle mới.
