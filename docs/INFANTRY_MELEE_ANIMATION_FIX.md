# Hoạt ảnh kiếm của Lính bộ

Lính bộ dùng hình kiếm và khiên nhưng `BattleScene.animateEvent()` đưa các đơn vị
không có tháp xoay vào cùng nhánh giật thân và phóng đạn. Vì vậy sự kiện đánh của
Lính bộ được hiển thị như bắn súng.

## Thay đổi

- Thêm 5 khung động tác kiếm: lấy đà, giơ kiếm, chém, hạ kiếm và thu kiếm.
  Giữ màu của đủ 20 đội và trang bị của cả 3 cấp nâng cấp.
- Lính quay về phía mục tiêu, vung tay cầm kiếm và hiện một cung chém ngắn tại
  tầm vươn của kiếm. Không có viên đạn bay hoặc vụ nổ của phát bắn.
- Dịch nhẹ sprite khi ra đòn; vị trí gốc vẫn theo dữ liệu máy chủ.
- Hoạt ảnh đi bộ tạm nhường cho động tác đánh rồi tiếp tục sau khi thu kiếm.
  Hủy động tác khi bỏ qua phát lại, nâng cấp, chết hoặc tái sử dụng đối tượng.
- Các sự kiện đánh lính, đánh tháp, đánh căn cứ và phát lại trận đều dùng nhánh
  kiếm. Tháp và xe tiếp tục dùng hệ thống ngắm/bắn hiện có.

Sát thương, tầm đánh, tốc độ di chuyển và thời gian giữa các đòn trên máy chủ
được giữ nguyên. Đây là thay đổi cách thể hiện các sự kiện chiến đấu.

## Tệp và tái tạo

- `frontend/src/game/rendering/infantryMelee.ts`: điều khiển động tác và cung chém.
- `frontend/src/game/scenes/BootScene.ts`: nạp và chia các khung hình kiếm.
- `frontend/src/game/scenes/BattleScene.ts`: chọn hiệu ứng theo loại quân.
- `frontend/scripts/generate-infantry-melee.py`: tạo 60 SVG spritesheet từ hình
  gốc đang có, gồm các biến thể nâng cấp. Chạy sau hai script tạo hình hiện có:

```sh
python3 frontend/scripts/generate-infantry-melee.py
```

## Xác minh

Kiểm tra kiểu dữ liệu, toàn bộ 142 bài kiểm thử frontend và build production.
Kiểm thử trình duyệt độc lập tại `frontend/tests/infantry-melee.browser.mjs`
chạy cảnh Phaser thật, không cần thay đổi dữ liệu trận:

```sh
cd frontend
npm run dev -- --host 127.0.0.1 --port 5199
# Ở terminal khác; Playwright cần có trong môi trường Node/NODE_PATH:
node tests/infantry-melee.browser.mjs
```

Kết quả và ảnh kiểm tra nằm trong `docs/qa/infantry-melee/`. Các trường hợp gồm
hai hướng đánh, ba cấp lính, khôi phục đi bộ, đánh căn cứ, phát lại, bỏ qua hiệu
ứng, đối tượng tái sử dụng, giới hạn số hiệu ứng và tháp súng vẫn bắn bình thường.
