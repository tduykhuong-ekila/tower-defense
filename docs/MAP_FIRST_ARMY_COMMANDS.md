# Chỉ huy quân trực tiếp trên bản đồ

Đã triển khai theo yêu cầu chọn một/vài quân hoặc kéo khung trên map, thay cho bước chọn loại quân thường trực.

## Luồng chính

1. Chọn quân trên map. Bấm quân của mình tự mở Chỉ huy, giữ nguyên các ID đã chọn.
2. Hàng đầu hiển thị tổng số quân, thành phần nhóm và Bỏ chọn.
3. Hàng sau gồm Lệnh / Đích đến / Thực hiện. Tấn công cần căn cứ đối thủ còn sống; Rút quân tự dùng điểm tập kết.
4. Bấm căn cứ đối thủ khi đã chọn nhóm chỉ điền mục tiêu và chuyển lệnh sang Tấn công, chưa phát lệnh. Chỉ Thực hiện mới gửi request. Mục tiêu lính mới được giữ riêng.
5. Chưa chọn quân: chỉ một hàng hướng dẫn và công cụ chọn. Không tự chọn toàn quân.

Không còn thẻ chọn nhóm, bộ lọc trạng thái hoặc bước chuyển màn trong vùng lệnh chính. Tùy chọn (…) giữ các shortcut chọn toàn quân/theo loại/đã tập kết, nâng cấp loại quân khi đang xem một quân hợp lệ và rút toàn quân. Thẻ thông tin nổi bị ẩn và đóng trong Chỉ huy để không che thao tác trên map hoặc xuất hiện lại trên ô mua quân khi chuyển ngữ cảnh.

## Thao tác map

| Thiết bị | Chọn quân | Di chuyển và thu phóng |
| --- | --- | --- |
| Chuột | Bấm chọn một; Shift/Ctrl/⌘ + bấm thêm hoặc bỏ từng quân. Trong ngữ cảnh Chỉ huy, kéo trái tạo khung chọn; modifier + kéo thêm vào nhóm. | Space + kéo trái hoặc kéo chuột giữa. Ngoài Chỉ huy, kéo map giữ hành vi cũ. |
| Cảm ứng | Chạm chọn một; bật Chọn thêm để chạm thêm/bỏ. Bật Khoanh vùng rồi kéo để chọn nhóm; chế độ này tự tắt sau khi chọn. | Kéo thường di chuyển; hai ngón vẫn thu phóng, kể cả khi đã bật Khoanh vùng. |

Escape hủy cả thao tác kéo chọn đang diễn ra. Map nhận focus khi bấm chuột để Space-pan không kích hoạt lại nút HUD trước đó. Pinch khởi tạo khoảng cách ngay lúc ngón thứ hai chạm xuống, không chờ mất lượt di chuyển đầu. Pinch và pan không được phát sinh click/chọn quân ngoài ý muốn. WAITING/MODAL không nhận lệnh chọn quân.

## Bố cục

- Thành phần lệnh chính cao 32px; vị trí không đổi khi chuyển Tấn công / Rút quân.
- Dock Chỉ huy có chọn quân: 116px desktop, 140px mobile dọc, 106px mobile ngang.
- Không chọn quân: 60px desktop, 54px mobile dọc, 50px mobile ngang.
- Thu gọn/mở lại vẫn hoạt động với mọi quy tắc grid/flex responsive.
- Đây là chiều cao dock; thanh chuyển ngữ cảnh và thanh trạng thái bên ngoài không tính vào số đo.

## An toàn lệnh và phạm vi

- Giữ API hiện có; không thay luật combat, tốc độ hoặc HP.
- Không gửi RETARGET nếu chưa chọn đích hoặc mọi quân đã có cùng lệnh tấn công đích đó.
- Nhóm đang rút/đã tập kết có thể nhận lệnh tấn công trở lại bằng cách chọn căn cứ và Thực hiện.
- Rút nhóm thực hiện trực tiếp. Rút toàn quân từ Tùy chọn hoặc chọn toàn bộ nhiều hơn một quân rồi Thực hiện lệnh Rút cần xác nhận.
- Xác nhận chụp danh sách ID tại lúc mở; quân xuất sau không chịu tác động. Nếu ID không còn hợp lệ thì đồng bộ và yêu cầu kiểm tra lại, không rơi về lệnh toàn quân.
- Giữ điều kiện theo pha: tập kết đầu trận cho đổi mục tiêu; giao tranh cho cả hai lệnh; tiếp tế các vòng sau chỉ cho rút. Backend vẫn kiểm tra quyền và điều kiện.

## Kiểm tra

- 34 test liên quan: army-control, room-camera, default-attack-target, batch-deployment, live-battle, upgrade-level-selection: PASS.
- Production build: PASS, còn cảnh báo kích thước bundle từ Vite.
- Browser integration với React/Phaser/API/WebSocket thật trên phòng QA riêng: PASS; không lỗi JavaScript. Phòng QA được kết thúc sau kiểm tra.
- Đã dùng mouse/touch thực tế để kiểm tra chọn một, thêm/bỏ bằng Shift, kéo khung, Space-pan, thêm/bỏ bằng chạm, pan, pinch và khoanh vùng cảm ứng tự thoát. Quân di chuyển trong lúc kéo, nên kiểm tra nhóm hỗn hợp hợp lệ thay vì giả định mọi quân còn ở vị trí trước gesture.
- Kiểm tra bấm căn cứ không phát lệnh ngay; chỉ nhóm được chọn đổi hướng/rút; hủy dialog giữ lựa chọn; quân mới xuất sau khi mở xác nhận không bị rút; không có request nhóm rỗng; tiếp tế vòng 2 chỉ cho rút.
- Đo bố cục trên 1440×1000, 390×844, 844×390: không tràn viewport/ngang, trường lệnh cao 32px và dock không đổi khi chuyển loại lệnh. Giữ kiểm tra không nhảy layout ở khung xuất lính đã cập nhật trước đó.
- Kết quả: `docs/qa/army-command-ux-browser.json`, `army-map-command-tests.txt`, `army-map-command-build.txt`.
- Ảnh: `docs/qa/army-map-command-1440.png`, `army-map-command-390.png`, `army-map-command-844.png`.

Không chạy lại toàn bộ test frontend ngoài phạm vi thay đổi này. Lần chạy tổng trước đó có bốn lỗi asset/hiển thị sao không thuộc phần Chỉ huy; bản này không sửa artwork hoặc sao.
