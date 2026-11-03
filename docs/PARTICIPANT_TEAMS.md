# Chọn đội, tự tạo đội và mời đồng đội

Mentee và mentor có thể chọn đội khi vào phòng, hoặc chọn **Tạo đội mới và tham gia** rồi nhập tên đội. Tạo đội và tham gia được xử lý trong cùng giao dịch; thao tác thất bại không để lại đội rỗng hay thành viên mới.

Người tham gia **chỉ được tạo đội ở bước join ban đầu**. Khi đã vào phòng chờ, mentee và mentor không có nút tạo đội và API tạo đội trả về 403 với token người chơi, kể cả khi chưa được gán đội. Gửi lại yêu cầu join để tạo đội bằng token đã tham gia chính phòng đó cũng bị chặn. Chỉ host được tạo thêm đội trong phòng chờ. Người chơi vẫn có thể chọn **Tham gia đội này** và mời người khác vào đội của mình. Khi có người vào hoặc đổi đội/vai trò, các đội liên quan phải xác nhận sẵn sàng lại.

Thành viên dùng nút **Mời vào đội** trên thẻ đội của mình để sao chép liên kết và gửi cho người khác. Liên kết có dạng `/join?code=ROOMCODE&team=TEAM_UUID`, không chứa thông tin xác thực. Người nhận thấy sẵn mã phòng và đội, rồi tự nhập tên, chọn vai trò và xác nhận tham gia. Đây là lời mời qua liên kết chia sẻ; ứng dụng không tự gửi thông báo hoặc email. Nếu đội không còn tồn tại, giao diện báo rõ để người nhận tự chọn đội khác.

Máy chủ vẫn kiểm tra giới hạn số đội, số thành viên, tên đội trùng (không phân biệt hoa/thường), tối đa một mentor trong mỗi đội, phòng đã khóa và trạng thái trận. Khán giả không có quyền tạo đội hoặc tự đổi sang vai trò chơi. Việc đổi đội của người chơi không được dùng quyền override của host. Host vẫn quản lý cấu hình, xóa đội, loại thành viên và bắt đầu trận.

## API

- `POST /api/v1/matches/{id}/join/`: thêm trường tùy chọn `new_team_name` (1–50 ký tự). Không được gửi cùng `team_id`, và chỉ dùng với `MENTEE` hoặc `MENTOR`. Phản hồi vẫn gồm `member`, `participant_token`, `match`.
- `POST /api/v1/matches/{id}/teams/`: chỉ host được gọi trong lobby; token người chơi luôn nhận 403. Host tạo đội mà không tự tham gia.
- `POST /api/v1/matches/{id}/members/{member_id}/assign/`: người chơi chỉ tự chọn đội/vai trò mentee hoặc mentor trong lobby; quyền override chỉ dành cho host.

Không cần migration mới. Cập nhật đồng thời backend và frontend. Với môi trường Docker local của repository, chạy `docker compose up -d --build backend frontend` để sử dụng bản mới.

## Kiểm tra ngày 27/10/2026

- 57 kiểm thử backend thành công: tạo đội khi join, chặn tạo đội trong lobby và gọi lại join bằng token đã tham gia, rollback khi lỗi, phân quyền, sức chứa và mentor.
- 142 kiểm thử frontend thành công; TypeScript và production build thành công. Vite vẫn báo cảnh báo dung lượng bundle chiến trường lớn.
- Ruff thành công cho các tệp Python đã sửa.
- Kiểm tra trình duyệt với backend/database riêng và nhiều phiên Chrome: mentee/mentor tạo đội khi join; không có nút tạo đội khi vào lobby và các API chặn yêu cầu tạo thêm; host vẫn tạo đội trong lobby; sao chép lời mời; mentor tham gia từ điện thoại; chặn mentor thứ hai; mentee nhận lời mời vào đúng đội; đội đầy khóa nút mời; lời mời tới đội không tồn tại hiển thị cảnh báo. Không có lỗi JavaScript.

Mã kiểm tra: `backend/tests/test_participant_teams.py`, `frontend/tests/team-joining.test.ts`, `frontend/tests/participant-teams.browser.mjs`.

Kết quả và ảnh: [browser report](qa/participant-teams-browser.json), [tạo đội](qa/participant-team-create.png), [lobby điện thoại](qa/participant-team-mobile.png).

Chạy kiểm tra trình duyệt với `TEST_BASE_URL` trỏ tới frontend/backend kiểm thử riêng; script tạo một phòng và thành viên kiểm thử. Cần Playwright/Chrome, có thể dùng thư viện Playwright đi kèm runtime qua `NODE_PATH`. Chạy script từ thư mục `frontend`.
