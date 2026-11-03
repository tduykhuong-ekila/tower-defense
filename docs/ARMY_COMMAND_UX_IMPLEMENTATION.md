# Cập nhật UX xuất lính và chỉ huy quân

Ngày: 30/10/2026. Triển khai nhóm cải tiến chính trong `ARMY_COMMAND_UX_RESEARCH_PROPOSAL.md`.

**Cập nhật mới nhất:** phần Chỉ huy đã chuyển sang chọn quân trực tiếp trên map và một hàng Lệnh / Đích đến / Thực hiện. Các mô tả thẻ chọn nhóm và bộ lọc bên dưới là lịch sử triển khai; xem `MAP_FIRST_ARMY_COMMANDS.md` cho hành vi và kiểm tra hiện tại.

## Giao diện và hành vi

- Hai ngữ cảnh Xuất lính / Xây dựng và Chỉ huy trong một khu vực lệnh phía dưới; có thu gọn/mở lại. Không còn bảng điều khiển quân thường trực ở sidebar.
- Mục tiêu xuất lính (`deploymentTargetId`), mục tiêu lệnh đang soạn (`commandTargetId`) và căn cứ đang xem (`inspected`) độc lập. Khi đang chọn một loại lính để xuất, bấm căn cứ đối thủ còn sống từ bản đồ, minimap, sidebar hoặc danh sách đội sẽ cập nhật mục tiêu cho lính mới. Giữ nguyên tiêu đề/thông số triển khai; không phát lệnh cho quân đang có. Bấm căn cứ mình, căn cứ bị loại hoặc xem căn cứ khi chưa chọn lính không thay mục tiêu.
- Bộ chọn đối thủ chung cho cả hai ngữ cảnh: chỉ đối thủ đang ACTIVE và có HP, thứ tự ổn định, tìm tên, hiện HP và lựa chọn hiện tại. Có khóa focus, Escape đóng và khôi phục focus. Chọn đối thủ chưa phát lệnh.
- Mục tiêu ban đầu vẫn theo vòng đội hiện có để giữ phân bố tấn công; khi mục tiêu bị loại thì xóa lựa chọn và yêu cầu chọn lại, không tự chuyển sang đối thủ khác.
- Thẻ Tất cả / Bộ binh / Xe tăng / Pháo binh với số lượng toàn đội. Chọn nhiều thêm/bỏ cả loại hoặc từng quân bằng chạm, không cần phím bổ trợ. Kéo khung bằng chuột vẫn là một chế độ riêng; chế độ chọn nhiều không biến kéo camera thành kéo khung.
- Bộ lọc trạng thái Toàn đội / Đang tấn công / Đang rút / Đã tập kết nằm trong phần mở rộng. Nhãn vùng chọn ghi rõ phạm vi; thay bộ lọc không âm thầm thay nhóm đang chọn.
- Rút nhóm phát lệnh ngay. Rút toàn quân mở một xác nhận có số lượng, chụp danh sách ID lúc mở; quân xuất sau không bị ảnh hưởng. Không hồi máu, vẫn chịu sát thương trên đường, có thể tấn công lại bằng RETARGET.
- Request luôn có danh sách ID không rỗng, không có fallback từ rút nhóm sang rút toàn quân. Kiểm tra lại quân còn sống trước gửi và đồng bộ khi lỗi; thông báo số quân dựa trên ACK server.
- Nút xuất ghi rõ số lượng, loại quân và đối thủ. Theo điều chỉnh giao diện mới nhất, chọn mục tiêu và nút xuất nằm trong khung Sẵn sàng triển khai: cột trái chỉnh số lượng và tổng xu; cột phải chọn đối thủ và xuất quân. Các ô chọn và nút xuất dùng chiều cao 32px; khung Quân đội giữ kích thước cố định theo viewport, dành sẵn chỗ cho khung triển khai khi chưa chọn quân để không nhảy bố cục khi chọn/bỏ chọn/đổi loại. Đã bỏ các nút chọn nhanh 1/5/10/Max; vẫn có nút trừ/cộng và ô nhập trực tiếp. Giữ hai cột trên desktop, điện thoại dọc và ngang.
- Minimap tự thu gọn trên màn hình nhỏ; người chơi vẫn có thể mở lại. Ẩn thẻ thông tin nổi trong chế độ chọn nhiều để tránh che thao tác cảm ứng.
- Giữ API, luật chiến đấu, quyền điều khiển và điều kiện theo pha hiện có. Chưa thêm hệ squad lưu sẵn. Chọn mục tiêu bằng cách bấm căn cứ chỉ áp dụng khi đang chọn lính mới; ngoài ngữ cảnh đó, bấm căn cứ vẫn chỉ xem thông tin.

## File chính

- `frontend/src/pages/BattlePage.tsx`: tách trạng thái, tích hợp dock và lệnh an toàn.
- `frontend/src/components/game/AttackTargetPicker.tsx`: bộ chọn chung.
- `frontend/src/components/game/ArmyCommandPanel.tsx`: chọn nhóm, lọc và ra lệnh.
- `frontend/src/components/arena/ArenaNavigation.tsx`: danh sách chỉ xem và minimap thu gọn.
- `frontend/src/game/armySelection.ts`: chọn nhóm, lọc trạng thái, chốt request không rỗng.
- `frontend/src/game/game.css`: bố cục theo màn hình và vùng hành động luôn hiển thị.

## Kiểm tra

- `npm run build`: pass, còn cảnh báo bundle lớn từ Vite.
- 27 test liên quan ở `army-control`, `default-attack-target`, `batch-deployment`, `live-battle`, `upgrade-level-selection`: pass.
- Bộ test frontend tổng: 159/163 pass. Bốn lỗi nằm trong các kiểm tra asset/đường dẫn artwork hiện có: ba trường hợp `star-level.test.ts`, một trường hợp `team-upgrades-vegetation.test.ts`. Các file implementation về artwork/sao không được thay đổi trong bản cập nhật này. Không coi bộ test tổng là pass.
- Browser integration: pass trên 1440×1000, 390×844 và 844×390, không có lỗi JavaScript. Tạo và kết thúc phòng QA riêng trên backend local, có nhập ngân hàng câu hỏi mẫu và mở khóa xe tăng qua API thật.
- Kiểm chứng tách mục tiêu xem/xuất/chỉ huy; chỉ xe tăng đổi hướng, bộ binh giữ đích; rút nhóm trực tiếp; tấn công lại; chọn nhiều bằng touch; hủy modal giữ nhóm; rút toàn quân dùng ID đã chụp; focus trap; mục tiêu bị loại chặn xuất quân. Trường hợp bị loại được mô phỏng bằng update vào store thật của trang sau các lệnh HTTP/WebSocket.
- Kiểm tra khung dock/dialog nằm trong viewport, không tràn ngang, nút xuất quân nằm trong viewport mà không cần cuộn. Các viewport được thay đổi trên trang thật; đây chưa phải nghiên cứu usability với người chơi mới.

Kết quả: `docs/qa/army-command-ux-browser.json`, `army-command-ux-targeted-tests.txt`, `army-command-ux-frontend-tests.txt`, `army-command-ux-build.txt`. Ảnh: `army-command-ux-{1440,390,844}.png`, `army-target-picker-{1440,390,844}.png`, `army-deployment-ux-{1440,390,844}.png`.
