# Hướng dẫn người chơi Mentor & Mentee

Mở `index.html` bằng Chrome, Edge, Safari hoặc Firefox. File HTML tự chứa toàn bộ ảnh và mã, không cần mạng hoặc chạy backend.

- **← / →**, **PageUp / PageDown**: chuyển slide.
- **Home / End**: đầu / cuối bộ slide.
- **M**: mở mục lục; **F**: toàn màn hình.
- Bấm ảnh để phóng lớn; **Esc** để đóng ảnh/mục lục.
- **In / PDF**: in toàn bộ slide hoặc lưu PDF bằng trình duyệt.
- Liên kết `index.html#12` mở trực tiếp slide 12.

Nội dung đối chiếu với mã nguồn hiện tại của JoinMatchPage, LobbyPage, BattlePage, ResultsPage, QuestionModal, RewardSelectionModal, TeamUpgradeModal, ArmyCommandPanel, BattleScene và ArenaNavigation. Tập trung vào chế độ CONTINUOUS của phòng mới; có ghi chú về phòng LEGACY.

Ảnh trong `assets/` được chụp từ giao diện React/Phaser thật với database thử nghiệm riêng, không dùng phòng của người chơi. Các mã phòng, tên, xu và thời gian trong ảnh là dữ liệu minh họa. Các khung vàng trong slide là lớp chú thích, không phải nút trong game.

Để dựng lại HTML sau khi sửa nội dung hoặc ảnh:

```bash
python3 docs/player-guide/build.py
```

`build.py` chứa nội dung 28 slide, bố cục, điều hướng, chế độ in và cách nhúng ảnh, gồm quy tắc thắng, cách tính Tổng điểm và xu thưởng khi tiêu diệt lính/tháp. `assets/regions.json` chứa vùng đánh dấu theo ảnh 1600 × 1000.
