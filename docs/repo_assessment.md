# Repository Assessment & Environment Baseline

> Thực hiện trong khuôn khổ **Phase 0 — Repository Inspection, Scaffolding & Design Decisions**.
> Thời điểm thực hiện: 2026-10-15

## 1. Hiện trạng Repository

- **Trạng thái ban đầu:** Greenfield repository (kho lưu trữ mới hoàn toàn).
- **Cấu trúc trước triển khai:** Chỉ có thư mục `docs/` chứa tài liệu thiết kế trò chơi:
  - `docs/GDD_PRD.md`: Tài liệu đặc tả Game Design Document & Product Requirements Document hoàn chỉnh (Version 1.0).
  - `docs/phase_0.md` đến `docs/phase_7.md`: Kế hoạch chia 8 giai đoạn triển khai chi tiết.
- **Mã nguồn:** Chưa có source code Backend, Frontend hay tệp cấu hình Docker/CI nào.

## 2. Thẩm định Môi trường Kỹ thuật (Host Environment)

Sau khi kiểm tra trực tiếp trên máy chủ / trạm làm việc phát triển:

| Thành phần | Phiên bản phát hiện | Ghi chú & Đánh giá |
|---|---|---|
| **OS** | macOS (Darwin ARM64 / Apple Silicon) | Môi trường Unix tiêu chuẩn, tương thích tốt với POSIX shell |
| **Python** | Python 3.12.3 (`/Users/admin/.pyenv/shims/python3.12`) & Python 3.14.4 hệ thống | Sử dụng Python 3.12.3 theo đúng tiêu chuẩn đặc tả tại GDD §15 |
| **Node.js** | v20.11.0 (LTS) | Đáp ứng tốt yêu cầu Vite, React, Phaser 3 |
| **npm** | 10.2.4 | Trình quản lý gói chuẩn của Node |
| **Docker Engine** | 29.1.3 | Docker daemon đang hoạt động |
| **Docker Compose** | v2.40.3-desktop.1 | Docker Compose v2 tiêu chuẩn |

### Phát hiện Xung đột Cổng (Port Conflicts) trên Host:
- **Port 5432:** Đang có một tiến trình PostgreSQL cục bộ (PID 574) chiếm dụng.
- **Port 6379:** Đang có một container Redis khác (`turisvpn-redis`) chiếm dụng `0.0.0.0:6379`.
- **Port 8000 & 5173:** Hoàn toàn trống.

**Giải pháp phân bổ cổng (Port Mapping Strategy):**
- Trong `docker-compose.yml`:
  - PostgreSQL container: Cổng nội bộ container là `5432`, ánh xạ ra host tại `5433:5432` (hoặc dùng `5432` trong mạng docker).
  - Redis container: Cổng nội bộ container là `6379`, ánh xạ ra host tại `6380:6379`.
  - Backend: Cổng `8000:8000`.
  - Frontend: Cổng `5173:5173`.
- Nhờ vậy, khi chạy cả chế độ Docker lẫn chạy Local trực tiếp đều không bị đụng độ cổng với các dịch vụ đang có trên máy.

## 3. Rủi ro & Giả định Kiến trúc (Risks & Assumptions)

1. **Server-authoritative Game Engine:**
   - *Nguyên tắc:* Mọi logic tính toán (xác thực câu hỏi, coin, mở khóa, di chuyển, tầm bắn, sát thương, thắng thua) bắt buộc chạy 100% trên Backend Django. Frontend (React + Phaser) chỉ là presentation layer.
2. **Phaser Canvas vs React UI:**
   - Phaser 3 chỉ đảm nhiệm hiển thị map chiến trường và animation hoạt cảnh (di chuyển, bắn, nổ).
   - Tất cả các modal (Question, Reward, Deploy, Upgrades), bảng điều khiển Host, thanh trạng thái, kết quả đều viết bằng React component tiêu chuẩn.
3. **Quản lý Balance & Config:**
   - Toàn bộ chỉ số (HP, damage, coin rewards, timers, slot giới hạn) phải lưu trữ trong Match Configuration / Database, tuyệt đối không hardcode trong frontend client.
4. **Idempotency & Concurrency:**
   - Các hành động trừ coin, chọn thưởng, deploy quân cần có `idempotency_key` và bọc trong database transaction (`select_for_update`) để tránh race condition khi nhiều người chơi trong cùng đội hoặc mạng chập chờn click nhiều lần.
