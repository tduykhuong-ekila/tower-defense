# Đề xuất đơn giản hóa phần Chỉ huy

Khảo sát ngày 30/10/2026. Đọc `ArmyCommandPanel.tsx`, phần tích hợp trong `BattlePage.tsx`, CSS và kết quả QA mới nhất; đối chiếu tài liệu chính thức của game tương tự. Đây là đánh giá thiết kế, chưa có thử nghiệm usability với người chơi mới. Chưa sửa giao diện game trong lần khảo sát này.

## Vấn đề còn lại

1. **Nhiều chế độ phải nhớ.** Chọn nhiều, kéo khung và bộ lọc trạng thái đều thay đổi ý nghĩa thao tác chọn. Cùng một thẻ Xe tăng có thể thay cả nhóm hoặc thêm/bỏ nhóm tùy chế độ trước đó.
2. **Chọn nhóm và lọc dữ liệu chưa tách rõ.** Bộ lọc làm đổi số lượng trên các thẻ nhưng không xóa quân đang chọn ngoài phạm vi. Người chơi có thể đang thấy nhóm “đang tấn công” nhưng lệnh vẫn áp dụng cả quân đã chọn trước đó.
3. **Phân cấp chọn bị mơ hồ.** Khi chọn toàn quân, thẻ Tất cả và mọi thẻ loại quân đều có thể hiện trạng thái được chọn. Người dùng phải tự hiểu đây là các tập hợp chồng lấn.
4. **Thông tin lặp lại.** Đã chọn N quân, toàn đội N quân, thành phần nhóm, mục tiêu hiện tại, mục tiêu lệnh và tên mục tiêu trong nút tấn công cùng xuất hiện. Dòng “Nhiều mục tiêu / trạng thái” trộn hai khái niệm.
5. **Vùng lệnh đổi cấu trúc.** Nút tấn công chỉ xuất hiện khi có mục tiêu lệnh. Sau lệnh thành công `commandTargetId` bị xóa, nên nút lại biến mất. Chọn nhóm khác cũng xóa mục tiêu đang soạn.
6. **Hai phạm vi rút quân đặt gần nhau.** Rút nhóm là lệnh chiến thuật, rút toàn quân là hành động diện rộng. Cả hai cùng hiện thường trực làm phần quan trọng khó nổi bật.
7. **Không nhất quán với xuất lính.** Xuất lính vừa hỗ trợ bấm căn cứ để chọn mục tiêu, nhưng khi chỉ huy nhóm quân hiện có thì thao tác đó mới chỉ xem căn cứ.

## Đối chiếu game

- [Age of Empires II DE – Controls & Command Menu](https://www.ageofempires.com/learn-to-play/control-resources-aoe2/): chọn quân rồi ra lệnh theo ngữ cảnh; bảng lệnh thay theo đối tượng được chọn; hỗ trợ chọn nhiều và cùng loại. Bài học: một phạm vi chọn rõ và một vùng hành động tương ứng, không đưa mọi thao tác nâng cao ra cùng lúc.
- [Company of Heroes 2 – Manual](https://www.feralinteractive.com/en/manuals/companyofheroes2/latest/linux/): có icon đơn vị để chọn trực tiếp, biểu tượng trạng thái và lệnh Retreat riêng cho nhóm đã chọn. Bài học: phân biệt chọn quân, xem trạng thái và phát lệnh rút. Chỉ tham khảo UX; không sao chép luật khóa điều khiển/tốc độ rút của game đó.
- [Boom Beach – Squad Leaders/Squad Flare, tài liệu bản cập nhật 2024](https://boombeach.supercell.com/en/news/blog/storm-after-the-calm/): mô tả lệnh Flare tác động riêng squad được gắn leader từ icon đơn vị. Đây là mô tả tính năng thử nghiệm trong bản cập nhật, không khẳng định có ở mọi chế độ hiện tại. Bài học: luôn thể hiện rõ lệnh đang áp dụng cho nhóm nào.

Các bài học là suy luận thiết kế cho dự án, không phải tuyên bố các game có chính xác giao diện đề xuất sau đây.

## Phương án khuyến nghị: hai cột, một luồng lệnh

**Luồng chính:** chọn nhóm → chọn căn cứ đối thủ → bấm Tấn công; hoặc chọn nhóm → bấm Rút N quân.

- Hàng chọn nhanh Toàn quân / Bộ binh / Xe tăng / Pháo. Mỗi lần bấm chọn đúng một phạm vi và thay nhóm trước; chỉ hiện một thẻ đang chọn. Không tự chọn toàn quân khi mở Chỉ huy. Nhóm tùy chỉnh chọn trên bản đồ được nhận diện riêng, không đánh dấu nhầm là toàn bộ một loại.
- Một dòng tiêu đề “Xe tăng · 4 quân” hoặc “Nhóm phối hợp · 12 quân”. Chỉ bổ sung thành phần chi tiết khi nhóm có nhiều loại; bỏ số tổng toàn đội lặp ở đầu bảng vì đã có trên thẻ Toàn quân.
- Cột trái cho phạm vi và trạng thái hiện tại; cột phải cho mục tiêu mới và hai lệnh Tấn công / Rút N quân. Tên đội nằm trong bộ chọn mục tiêu, không lặp thêm vào mọi nút.
- Cả hai nút luôn giữ nguyên vị trí. Khi chưa chọn quân/chưa chọn đích thì vô hiệu hóa với hướng dẫn ngắn. Khi tất cả quân đã tấn công đúng mục tiêu đó, không gửi lại lệnh vô nghĩa. Quân đang rút hoặc đã tập kết dùng nhãn Tấn công lại.
- Tách rõ trạng thái hiện tại khỏi mục tiêu mới. Ví dụ: “Hiện tại: tấn công Đội 2” và “Mục tiêu mới: Đội 3”. Chỉ sau ACK server mới cập nhật trạng thái thực tế. Không ghi “đã tấn công” khi mới chọn đích.
- Khi nhóm quân đang được chọn, bấm căn cứ đối thủ hợp lệ cập nhật mục tiêu lệnh của nhóm đó. Chưa phát lệnh ngay. Ngữ cảnh Xuất lính chỉ đổi `deploymentTargetId`; ngữ cảnh Chỉ huy chỉ đổi `commandTargetId`.
- Một mục Tùy chọn chứa Chọn phối hợp, Chọn quân đã tập kết, chọn trên bản đồ và Rút toàn quân. Chọn phối hợp dùng checkbox với phạm vi hiển thị cụ thể, thay cho nút bật/tắt Chọn nhiều toàn cục. Desktop vẫn giữ Shift-click/kéo khung như thao tác nâng cao; không âm thầm đổi kéo camera thành chọn quân trên cảm ứng.
- Rút nhóm thực hiện trực tiếp, có thông tin phụ về không hồi máu và vẫn chịu sát thương. Rút toàn quân nằm trong Tùy chọn và giữ xác nhận. Danh sách ID phải được chụp theo hành động, không để nhóm rỗng rơi vào rút toàn quân.
- Bộ lọc trạng thái hiện tại không còn là một chế độ ảnh hưởng ngầm đến thẻ chọn. Thay bằng hành động cụ thể như “Chọn quân đã tập kết” khi cần.
- Giữ khung và vị trí các vùng ổn định ở mọi trạng thái chọn, dùng chiều cao nút 32px theo giao diện vừa thống nhất. Dành trước vị trí cho cảnh báo ngắn để mất kết nối/quân chết không đẩy nút. Trên cảm ứng có thể tăng vùng nhận chạm bằng khoảng trống xung quanh.

## Phương án thay thế: từng bước

Chọn quân → Ra lệnh → Chọn mục tiêu/Tấn công hoặc Rút. Mỗi màn ít thành phần hơn, dễ hướng dẫn người mới. Đổi lại phải chuyển bước khi muốn đổi nhóm; phản ứng trong giao tranh chậm hơn. Không khuyến nghị làm mặc định cho dự án; có thể dùng làm chế độ hướng dẫn nếu chơi thử chứng minh cần thiết.

## Giới hạn và kiểm chứng

Bản phác thảo tương tác dùng số quân/HP minh họa và thao tác cục bộ, không nối backend. Không thêm hệ squad mới hoặc luật chiến đấu. Phần lớn cập nhật có thể giữ API hiện có; tập trung vào cách chọn, tóm tắt và bố trí lệnh.

Khi triển khai, kiểm tra: chuyển giữa chọn một/quân phối hợp/toàn quân; chọn căn cứ trong hai ngữ cảnh độc lập; nhóm chứa cả ATTACK/RETREAT/AT_RALLY; mục tiêu bị loại; quân chết trước khi gửi lệnh; reconnect; chuyển pha; ACK đến sau khi người dùng đổi nhóm. Không gửi lại lệnh tự động để “hoàn tác”.

Chơi thử đề xuất với 5–8 người mới ở desktop và mobile: chọn xe tăng đổi hướng, phối hợp hai loại, chỉ rút nhóm, rút toàn quân, cho quân tập kết ra trận. Đo lỗi chọn nhầm phạm vi, thời gian phát lệnh và việc phân biệt “đã chọn mục tiêu” với “đã gửi lệnh”. Mục tiêu thiết kế: ra lệnh thông thường không cần bật chế độ phụ, đổi hướng trong ba thao tác sau khi đã chọn nhóm, không nhầm lính mới với quân đang có. Chưa có kết quả đo usability.
