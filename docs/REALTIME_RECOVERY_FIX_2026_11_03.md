# Khắc phục mất cập nhật đơn vị đối thủ — 03/11/2026

## Thay đổi

- `frontend/src/services/websocket.ts`: một bộ cập nhật Zustand được đăng ký trên singleton, hoạt động cả khi trang battle chưa gắn listener. Chỉ tăng cursor/deduplicate sau khi cập nhật store thành công. Listener giao diện và hiệu ứng chạy sau bước này, không thể làm mất sự kiện authoritative.
- Snapshot chỉ kết thúc phục hồi sau khi áp dụng thành công. Lỗi áp dụng qua WebSocket hoặc HTTP chuyển client sang trạng thái cần phục hồi; không đánh dấu version đã hoàn tất.
- Nếu chờ snapshot quá 2,5 giây, gọi GET snapshot qua HTTP với xác thực hiện có. Lỗi áp dụng kích hoạt HTTP ngay, trong giới hạn retry. HTTP có timeout 5 giây, một request đang chạy, khoảng cách retry tối thiểu 5 giây và hủy khi rời trận. Timeout/hủy cũng giải phóng request nếu loader không xử lý abort.
- Snapshot HTTP dùng chung kiểm tra match/version, cursor và buffer với WebSocket. Bỏ qua response của trận cũ và snapshot bị live events vượt qua. Response HTTP cũ không kết thúc một đợt phục hồi thiếu sequence mới hơn. Snapshot định kỳ bị vượt qua chỉ kết thúc lần kiểm tra, không gây reconnect thừa.
- Phân biệt chờ baseline/gap với kiểm tra định kỳ. Kiểm tra định kỳ tiếp tục áp dụng build/deploy đúng thứ tự, có jitter 27–33 giây. Gap thật chuyển sang buffer cho tới khi có baseline đầy đủ.
- `BattlePage.tsx`: chỉ quan sát dữ liệu đã cập nhật, bỏ lần áp dụng reducer trùng; không gọi lại cả nhóm REST match/map/catalog/team state sau mỗi snapshot. Hiển thị “Đang đồng bộ” khi baseline/gap chưa được khôi phục.
- `matchStore.ts`: snapshot của trận mới được phép thay thế store trận trước; các delta khác trận vẫn bị loại.
- `getDiagnostics()` cung cấp applied sequence, tuổi snapshot, buffer, trạng thái HTTP và số lỗi áp dụng; không xuất token hoặc payload riêng tư.
- Helper backend test `until()` được bổ sung ghép JSON_CHUNK, vì snapshot 20 đội vượt giới hạn frame đơn. Không thay đổi mã backend production hoặc schema database.

## Kiểm chứng

### Frontend

Lần chạy focused cuối: **37/37 pass**, gồm 13 acceptance test mới trong `tests/realtime-resilience.test.ts` và các regression store/recovery/continuous/socket.

Các trường hợp mới bao gồm: reducer lỗi; snapshot lỗi; observer animation lỗi; repair định kỳ không giữ build/deploy; gap trong lúc repair; mất snapshot WebSocket và HTTP khôi phục; HTTP cũ, sai cấu trúc, timeout hoặc phản hồi sau khi chuyển trận; snapshot HTTP áp dụng lỗi; snapshot trận mới không phụ thuộc listener trang.

Build cuối: `npm run build` pass (TypeScript + Vite). Vẫn có advisory kích thước bundle Phaser.

Lần chạy toàn bộ frontend trước acceptance test HTTP cuối: **180/184 pass**, bốn lỗi artwork trong `star-level.test.ts` (ba cấp) và `team-upgrades-vegetation.test.ts` (một test). Các test này kỳ vọng shield_generator SVG, trong khi `entityArtwork.ts` hiện dùng PNG. Những file artwork và selector đó không được sửa trong tác vụ này. Không tuyên bố toàn bộ test suite xanh.

### Backend

Sáu test transport/snapshot/build/deploy liên quan pass, gồm hai thứ tự tạo quân, xây tháp và reconnect với **4/8/20 đội** sau khi helper test hỗ trợ chunked frame.

Hai test bổ sung cũng pass: endpoint HTTP snapshot có version/phân quyền viewer và event 2 MB ghép chunk giữ nguyên phân quyền. Tổng cộng **8 test backend liên quan pass**.

Đợt chạy rộng ban đầu có các lỗi kỳ vọng chuyển động/range trong test formation/spawn hiện có, ngoài phần production code đã thay đổi. Không điều chỉnh cân bằng, đường đi hoặc artwork để làm các test đó pass.

### Trình duyệt thực

Dùng CUA trên hai phiên người chơi riêng cho mỗi trận, backend/database SQLite tạm và frontend dev riêng tại 8017/5177. Fixture tái sử dụng: `frontend/tests/fixtures/realtime-recovery.html`. Chỉ dùng fixture trên backend kiểm thử.

- **4 đội:** tạo bộ binh và tháp ở cả hai phía. Chủ động chặn snapshot WebSocket phía A, yêu cầu sync rồi tạo tiếp đơn vị. A khôi phục qua HTTP; so tập ID server/store/Phaser đều PASS, 4 entity tại version 31. Sau một lỗi reducer được chèn: cả hai PASS, 5 entity tại version 34; A ghi nhận một application error và hai lần HTTP recovery.
- **20 đội:** hai client nhận baseline lớn và tiếp tục hoạt động. Chặn snapshot WebSocket phía A, xây tháp và tạo bộ binh; cả hai PASS với 2 entity tại version 72. Sau lỗi reducer được chèn: cả hai PASS với 3 entity tại version 75; A ghi nhận một application error, không còn buffer/pending và tự về connected. Các bộ đếm HTTP bao gồm cả baseline chậm và repair định kỳ; không dùng chúng làm số lượng sự cố mạng.
- Các kiểm tra trên đối chiếu ID, không chỉ số lượng. Không reload trong các kịch bản phục hồi; không có page error/unhandled rejection. Lỗi reducer có chủ đích được cơ chế recovery ghi console theo thiết kế.
- Screenshot: `docs/qa/realtime-recovery-2026-11-03.png`.

Browser verification dùng các trận ở pha preparation, chưa phải benchmark tải chiến đấu kéo dài hoặc kiểm chứng đường truyền ngrok của người chơi. Không khẳng định mọi điều kiện mạng đều phục hồi trong một thời gian cố định.

## Áp dụng

Chỉ frontend production cần build lại; backend đã có endpoint snapshot. Container frontend local được cập nhật riêng bằng `docker compose up -d --no-deps --build frontend`. Trang đã mở với bundle cũ cần tải lại một lần để nhận bản sửa. Sau đó việc phục hồi các tình huống đã kiểm thử diễn ra tự động.
