# Khảo sát và đề xuất UX xuất lính / chỉ huy / rút quân

Ngày: 30/10/2026. Phạm vi: khảo sát tài liệu chính thức của game tương tự, đọc code hiện tại và ảnh QA có sẵn; chưa chạy phiên chơi thử hay đo hành vi người dùng. Đây là đề xuất, chưa thay đổi gameplay hoặc giao diện.

## 1. Vấn đề hiện tại

| Quan sát từ code | Hệ quả UX dự kiến |
| --- | --- |
| `BattlePage.tsx` dùng chung `target` cho xuất lính, bộ chọn đổi hướng, danh sách đội và minimap. Bấm căn cứ để xem cũng gọi `setTarget`. | Người chơi xem đối thủ có thể vô tình thay mục tiêu cho lần xuất quân tiếp theo; khó phân biệt xem, chọn và đã ra lệnh. |
| Xuất lính dùng drawer `TeamDirectory`, đổi mục tiêu dùng native select trong `ArmyCommandPanel`. | Cùng một việc chọn đội nhưng có hai cách thao tác và lượng thông tin khác nhau. |
| Drawer mặc định hiển thị tất cả đội, sắp xếp HP giảm dần, gồm cả đội mình và đội bị loại. | Phù hợp tra cứu hơn chọn mục tiêu tấn công; tăng thao tác khi nhiều đội. |
| Chọn thêm lính cần Shift/Ctrl/⌘; kéo chọn cần bật chế độ riêng. | Khó chọn một nhóm trên cảm ứng; người chơi phải nhớ kéo đang di chuyển camera hay chọn quân. |
| Bảng quân đội và dock mua quân là hai vùng điều khiển riêng. | Phải chuyển sự chú ý qua lại; trên màn hình nhỏ các bảng có thể tranh không gian với bản đồ. |
| Rút nhóm và rút toàn quân đều mở hộp thoại. | Lệnh chiến thuật khẩn cấp bị ngắt; hai phạm vi tác động cần phân cấp rõ hơn. |
| Rút quân đi về spawn/rally; `RETREAT` chuyển sang `AT_RALLY`, HP không tự hồi. | Cụm “về căn cứ / giữ nguyên HP” dễ bị hiểu thành an toàn hoặc miễn sát thương. Cần nói “không hồi máu; vẫn chịu sát thương trên đường”. |

Các hệ quả trên là đánh giá thiết kế, cần kiểm chứng bằng chơi thử. Ảnh `docs/qa/army-controls-battle.png` và `battlefield-deployment-mobile.png` là ảnh lịch sử; không dùng để khẳng định bố cục runtime mới nhất.

## 2. Game tham khảo

| Game / nguồn chính thức | Cơ chế được tài liệu xác nhận | Bài học đề xuất cho dự án |
| --- | --- | --- |
| [Age of Empires II DE – Controls](https://www.ageofempires.com/learn-to-play/controlling-your-empire-gathering-resources-xbox/) | Chọn đơn vị rồi ra lệnh theo ngữ cảnh; có chọn nhiều và chọn cùng loại. Đây là hướng dẫn Xbox. | Hiển thị hành động theo nhóm đang chọn; cung cấp chọn theo loại quân, không bắt người dùng bấm từng sprite. |
| [Boom Beach – Squad Leaders](https://boombeach.supercell.com/en/news/blog/storm-after-the-calm/) | Tài liệu bản cập nhật mô tả Squad Flare tác động riêng một squad, kích hoạt từ icon đơn vị phía dưới. Đây là tính năng được mô tả để thử nghiệm, không khẳng định có trong mọi chế độ hiện tại. | Gắn lệnh với thẻ nhóm và ghi rõ phạm vi: “12 quân đã chọn”. |
| [Kingdom Rush Battles – Battle-Mecha T200](https://support.ironhidegames.com/support/solutions/articles/4000223646-battle-mecha-t200-skills-breakdown-mobile-artillery-in-kingdom-rush-battles) | Mecha được điều khiển bằng rally point. | Đánh dấu đích đến rõ trên bản đồ để người chơi hiểu quân sẽ đi đâu. Nguồn này nói về Mecha cụ thể. |
| [Travian Kingdoms – Rally Point](https://support.kingdoms.com/en/articles/78-rally-point) | Một điểm quản lý mục tiêu, quân gửi đi, loại hành động, di chuyển và thu hồi viện binh. | Một nơi thống nhất cho quản lý quân; tách xem đội, chọn quân và phát lệnh. Travian có nhịp chơi khác nên chỉ tham khảo cấu trúc thông tin. |

Các bài học ở cột cuối là đề xuất của khảo sát này, không phải tuyên bố rằng các game có đúng UI đề xuất bên dưới.

## 3. Phương án khuyến nghị

### A. Một dock với hai ngữ cảnh rõ ràng

- **Xuất lính:** loại quân, số lượng, tổng xu, mục tiêu cho đợt xuất mới, nút xuất.
- **Chỉ huy:** nhóm quân hiện có, số lượng, trạng thái và lệnh đổi mục tiêu/rút quân.
- Trên mobile, dùng hai tab trong cùng dock; vùng tác vụ có thể thu gọn và mở thêm chi tiết. Ưu tiên giữ khoảng 60% chiều cao cho chiến trường ở trạng thái thao tác thông thường; đây là mục tiêu thiết kế cần kiểm chứng ở portrait và landscape.
- Khi chưa chọn quân, chỉ hiện chọn nhanh và tổng quân. Khi đã chọn, mới hiện lệnh tương ứng. Không để bảng chỉ huy dài thường trực cạnh dock.
- Chọn loại quân để mua chuyển sang ngữ cảnh Xuất lính; chọn quân hiện có chuyển sang Chỉ huy. Khi chuyển, xóa lựa chọn tác vụ còn dang dở và thể hiện trạng thái mới rõ ràng.

### B. Chọn mục tiêu xuất lính

Luồng: **chọn loại quân → chỉnh số lượng → chọn đối thủ nếu cần → xuất**.

- Giữ mục tiêu xuất lính người chơi đã chủ động chọn cho đợt sau; xem đối thủ khác không đổi mục tiêu này.
- Bộ chọn chỉ liệt kê đối thủ còn sống, có tên/số đội, HP căn cứ và nhãn “đang chọn”. Có tìm kiếm khi nhiều đội; không đảo thứ tự khi HP cập nhật realtime.
- Dùng cùng component chọn đối thủ cho xuất lính và đổi hướng. Mỗi lần mở ghi rõ ngữ cảnh: “Mục tiêu cho lính mới” hoặc “Đổi mục tiêu cho 12 quân”.
- Chạm một dòng chọn mục tiêu và đóng bộ chọn; thao tác đó chưa xuất quân hay đổi hướng quân đang có.
- Cho chọn trên bản đồ như một đường tắt sau khi bấm “Chọn trên bản đồ”. Căn cứ hợp lệ sáng lên, có nút Hủy; chạm căn cứ chỉ cập nhật bản xem trước.
- Khi chọn xong, hiện tên đích và tuyến dự kiến. Không ép camera nhảy sang đối thủ mỗi lần chọn; tách nút “Xem căn cứ”.
- Nút thực thi: **“Xuất 5 Bộ binh → Đội 3”**; tổng xu hiển thị ngay cạnh. Không thêm bước xác nhận thường xuyên.
- Nếu mục tiêu bị loại: xóa mục tiêu không hợp lệ, hiện yêu cầu chọn lại; không âm thầm chuyển sang đội khác rồi cho xuất.

### C. Chọn quân hiện có

- Chọn nhanh bằng các thẻ **Tất cả / Bộ binh / Xe tăng / Pháo binh**, mỗi thẻ có số quân còn sống trong phạm vi đã ghi rõ. Mặc định phạm vi toàn đội, không chỉ camera.
- Tách chip chọn nhóm khỏi bộ lọc trạng thái. Bộ lọc “Đang tấn công / Đang rút / Đã tập kết” thu hẹp tập quân; chip loại quân chọn trong tập đó. Nhãn phải ghi rõ, ví dụ “Xe tăng · đang tấn công · 6”.
- Mobile có nút **Chọn nhiều**: trong chế độ này chạm quân/thẻ để thêm hoặc bỏ; kéo một ngón vẫn di chuyển bản đồ, chụm vẫn zoom. Không dùng nhấn giữ làm cách duy nhất.
- Desktop giữ Shift-click và kéo khung như đường tắt; chế độ kéo chọn có trạng thái nổi bật và Esc để thoát. Không thay đổi hành vi kéo camera một cách ngầm định.
- Hiện “Đã chọn 12 quân” cùng số lượng từng loại, vòng chọn rõ và biểu tượng tương ứng. Không chỉ dùng màu để phân biệt.
- Chạm nền để bỏ chọn khi ở chế độ duyệt thường; trong chế độ chọn mục tiêu thì chạm nền không làm mất nhóm đang ra lệnh.

### D. Đổi mục tiêu và rút quân

Luồng đổi hướng: **chọn nhóm → Đổi mục tiêu → chọn đối thủ → Tấn công Đội 3 · 12 quân**.

- Bấm căn cứ bình thường chỉ xem; chỉ thao tác trong chế độ chọn mục tiêu mới thay mục tiêu đang soạn.
- Lệnh chỉ áp dụng cho quân đã chọn. Mục tiêu xuất lính mới là trạng thái độc lập; trong bản đầu không thêm checkbox gộp hai phạm vi.
- Nhãn **“Rút 12 quân về tập kết”** phát lệnh ngay để phản ứng nhanh; hiển thị ngắn “Không hồi máu · vẫn chịu sát thương trên đường”.
- **“Rút toàn quân…”** là nút phụ riêng, mở xác nhận một lần với số quân và thông tin lính xuất sau đó không bị ảnh hưởng. Không dùng nút giữ lâu làm cách duy nhất trên cảm ứng.
- Sau phản hồi server: “Đã ra lệnh rút cho 12 quân”; trên quân hiện “Đang rút”, đến nơi hiện “Đã tập kết”. Không báo “rút thành công” khi quân chưa tới.
- Quân ở điểm tập kết dùng **“Tấn công lại”**, thực chất chọn mục tiêu và gửi RETARGET hiện có. Nếu đang rút, đổi hướng trở lại cũng là một lệnh mới, không gọi là Hoàn tác vì thời gian và sát thương đã diễn ra.

Ví dụ nội dung dock, số liệu minh họa:

```text
[Xuất lính] [Chỉ huy · 24]

Xuất lính:
Bộ binh   [−] 5 [+]       Tổng: 75 xu
Mục tiêu: Đội 3 · 320 HP  [Đổi]
[Xuất 5 Bộ binh → Đội 3]

Chỉ huy:
[Tất cả 24] [Bộ binh 12] [Xe tăng 8] [Pháo 4]
Đã chọn 12 quân · Đang tấn công Đội 2
[Đổi mục tiêu] [Rút 12 quân] [Bỏ chọn]
Rút toàn quân…
```

## 4. Hướng triển khai

**P0 – sửa nhầm phạm vi và thao tác:** tách `inspectedTeamId`, `deploymentTargetId`, `commandTargetDraft`; bỏ tác dụng đổi mục tiêu khỏi thao tác xem/minimap thông thường; dùng một bộ chọn đối thủ; thêm chọn nhanh theo loại và chọn nhiều trên mobile; chuyển chỉ huy vào dock; phân cấp rút nhóm/rút toàn quân và sửa mô tả tập kết.

**P1 – tăng tốc thao tác:** chọn đích trực tiếp trên bản đồ, tuyến xem trước, lọc trạng thái quân, phím tắt desktop, thẻ nhóm tự lưu nếu chơi thử cho thấy có nhu cầu. Chưa cần xây hệ squad mới hay target một lính địch cụ thể: API hiện tại nhận `target_team_id`, đây là chọn đội/căn cứ chiến lược.

Điểm sửa chính: `frontend/src/pages/BattlePage.tsx`, `components/game/ArmyCommandPanel.tsx`, `components/arena/ArenaNavigation.tsx`, `game/armySelection.ts`, `game/scenes/BattleScene.ts`, `game/game.css`.

API hiện có đủ cho đổi mục tiêu và rút nhóm bằng `unit_ids`; không cần thay luật chiến đấu cho P0. Tài liệu cũ `TACTICAL_ARMY_COMMANDS.md` có đoạn mô tả rút quân không còn khớp code: `backend/apps/units/commands.py` hiện đã nhận danh sách quân cho lệnh rút.

Lưu ý khi triển khai: danh sách chọn rỗng tuyệt đối không được rơi vào lệnh rút toàn quân; chụp danh sách ID khi phát lệnh, khóa gửi lặp, chỉ báo số quân theo ACK server. Backend hiện từ chối cả lệnh nếu có quân không hợp lệ: khi quân chết giữa lúc chọn và gửi cần đồng bộ, cập nhật số lượng và cho thử lại; không âm thầm thay phạm vi. Giữ khóa theo pha, quyền điều khiển và trạng thái kết nối hiện có. Nút mobile mục tiêu tối thiểu 44×44 CSS px; tên dài phải có cách đọc đầy đủ.

## 5. Kiểm chứng đề xuất

Chơi thử với 5–8 người mới trên desktop và điện thoại, ở trận 2, 8 và 20 đội. Đo lần đầu làm các tác vụ: xuất 5 quân vào đội được chỉ định; xem đội khác rồi xuất tiếp; chỉ chọn xe tăng và đổi hướng; rút một nhóm; rút toàn quân; cho quân đã tập kết tấn công lại.

Mục tiêu thử nghiệm: ít nhất 90% hoàn thành không cần chỉ dẫn; không phát sinh lệnh sang đội khác khi chỉ xem bản đồ; rút nhóm trong tối đa hai lần chạm sau khi đã chọn nhóm; đổi hướng trong ba lần chạm sau khi đã chọn nhóm. Đây là tiêu chí đề xuất, chưa phải kết quả đo.

Kiểm tra thêm mục tiêu bị loại khi bộ chọn đang mở, quân được chọn chết, disconnect/reconnect, chuyển pha, nhiều người cùng đội ra lệnh, tên dài, camera zoom xa và màn hình ngang thấp. Xác nhận đổi mục tiêu nhóm không đổi đích lính mới, rút nhóm không lan sang quân ngoài nhóm, và không có thao tác chọn/chuyển camera nào tự phát lệnh.
