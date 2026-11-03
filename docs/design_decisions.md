# Architectural & Design Decisions (ADR)

> Tài liệu ghi nhận các quyết định thiết kế kiến trúc và giải quyết các điểm chưa đồng nhất trong GDD/PRD.
> Phê duyệt áp dụng cho toàn bộ các Phase từ Phase 0 đến Phase 7.

## Bảng Quyết Định Thiết Kế (D1 — D12)

| Mã | Vấn đề / Câu hỏi | Hiện trạng trong GDD | Quyết định Chuẩn hoá | Cơ sở / Lý do |
|:---|:---|:---|:---|:---|
| **D1** | **Giới hạn số đội trong trận** | §2.1 nêu 4–12 đội; §4.1 nêu 4–8 đội | **Mặc định 4–8 đội. Cho phép Host cấu hình tối đa lên đến 12 đội.** | Map fixed-lane ban đầu tối ưu cho 4–8 đội để hiển thị rõ ràng trên màn hình chiếu, nhưng schema backend hỗ trợ dynamic topology lên đến 12 đội. |
| **D2** | **Cơ cấu thành viên mỗi đội** | §2.1: 1 Mentor + 1–3 Mentee; §4.1: 2–4 người/đội | **1 Mentor + từ 1 đến 3 Mentee (Tổng: 2–4 thành viên/đội).** | Hai mệnh đề này hoàn toàn tương thích và bổ trợ cho nhau. |
| **D3** | **Thời lượng Combat Round** | GDD chỉ định nghĩa phase lớn (Preparation 3m, War 12m...) mà chưa cố định nhịp tick của combat round | **Mỗi combat round gồm 1 planning window (mặc định 30 giây) + thời điểm Server Resolve tức thời.** | Thông số `round_duration_seconds` nằm trong Match Configuration (mặc định 30s, Host có thể chỉnh từ 15s - 60s). |
| **D4** | **Thời điểm phân phối câu hỏi** | Khi nào thì đội nhận câu hỏi? | **Câu hỏi được phân phối trong phase `BUILD_AND_SCOUT` và `WAR`.** | Phase Preparation dành cho thảo luận chiến lược ban đầu. Đội có thể nhận câu hỏi tiếp theo sau khi hoàn thành câu hỏi trước đó và đã nhận thưởng, cho đến khi chạm mốc `max_questions_per_team` (mặc định 8 câu). |
| **D5** | **Quy tắc ưu tiên mục tiêu của Tháp (Tower Targeting)** | "Enemy unit closest to the defended base" (§10.3) | **Khoảng cách = Số node di chuyển còn lại của lính địch tới căn cứ được bảo vệ.** | Đơn vị nào còn ít node hơn thì bị nhắm bắn trước. Tie-break: Nếu bằng khoảng cách, ưu tiên đơn vị có `entity.id` nhỏ hơn (tính tất định - deterministic). |
| **D6** | **Xử lý triệt hạ đồng thời (Simultaneous Elimination)** | Nhiều căn cứ bị phá huỷ trong cùng một round giải quyết (§12.1) | **Thứ tự tie-break: Điểm tích lũy cao hơn > HP còn lại trước khi chết > Số coin còn lại.** | Đảm bảo kết quả xếp hạng công bằng và có quy tắc xác định rõ ràng, không phụ thuộc vào thứ tự xử lý trong DB. |
| **D7** | **Thời lượng Giáp bảo vệ (Shield Duration)** | Shield Generator tạo khiên 40 HP, cooldown 2 round (§8.3) | **Khiên tồn tại trong 2 combat round hoặc cho đến khi bị phá huỷ hoàn toàn.** | Giá trị `shield_duration_rounds` được lưu trong config (mặc định = 2). |
| **D8** | **Chính sách khi mục tiêu bị phá hủy (Fallback Policy)** | Lính đang đi tới một base địch mà base đó bị đội khác phá trước (§9.4) | **Mặc định: `IDLE` (Đứng chờ tái chỉ định ở round kế tiếp) hoặc `RETARGET_NEAREST` (Tự chuyển hướng sang căn cứ địch gần nhất còn sống).** | Cấu hình qua trường `fallback_policy` trong match configuration. Mặc định `RETARGET_NEAREST` để trận đấu tiếp tục sôi động. |
| **D9** | **Xác thực người chơi vãng lai (Guest Authentication)** | Không có hệ thống tài khoản cố định (§22) | **Cấp `participant_token` ngẫu nhiên (UUIDv4/cryptographic token) khi Join qua Room Code.** | Token này được lưu hash trong database và truyền qua Authorization header / query string khi kết nối WebSocket. Room code đơn thuần chỉ dùng để gia nhập phòng, không cấp quyền quản trị. |
| **D10** | **Thời gian giai đoạn Lobby** | Lobby có tính vào 30 phút trận đấu không? | **Không tính. Đồng hồ 30 phút trận đấu chỉ bắt đầu tính khi Host bấm "Start Match" (bắt đầu phase Preparation).** | Đảm bảo các đội có đủ thời gian chuẩn bị và ổn định nhân sự mà không bị mất thời gian thi đấu. |
| **D11** | **Giới hạn điểm sát thương (Damage Dealt Cap)** | Điểm sát thương lên căn cứ địch có bị farm vô hạn không? (§12.2) | **Chỉ tính điểm trên sát thương thực tế gây ra lên Base HP (và Shield), tối đa bằng tổng Base HP khởi tạo của các đối thủ.** | Không thể gây nhiều sát thương hơn lượng máu tối đa của căn cứ. Giúp ngăn chặn việc lạm dụng điểm số. |
| **D12** | **Kênh truyền thông: HTTP API vs WebSocket** | Phân định vai trò giữa REST API và WebSocket (§16.3, §21) | **REST API là kênh chính thống tiếp nhận các Command ghi trạng thái (State-changing actions). WebSocket dùng để stream broadcast events và state snapshots.** | Kiến trúc này đảm bảo tính bền vững (idempotency, transaction rollback), dễ debug, bảo mật cao và client có thể fallback qua HTTP nếu WebSocket bị lag. WebSocket vẫn có thể nhận command nhanh nhưng luôn dùng chung service layer với REST API. |
| **D13** | **Thời điểm trừ coin khi gửi Action (Coin Debit Timing)** | Trừ coin ở bước 3 (§10.1) hay trừ ngay khi accept? (§10.1 vs Phase 3 §2.4) | **Trừ/khóa coin ngay khi server chấp nhận Action (`ACCEPTED`). Hoàn tiền (`REFUND`) nếu action bị hủy hoặc reject khi resolve.** | Đảm bảo tính nhất quán trên UI (số dư hiển thị tức thời, ngăn chặn việc đặt nhiều lệnh vượt quá số dư trong cùng một planning window), đồng thời audit trail truy vết minh bạch qua `CoinTransaction`. |
| **D14** | **Công thức tính giải thưởng vinh danh (Optional Awards)** | FR-10 nêu 5 awards nhưng chưa cố định công thức | **Xác định công thức chuẩn hoá cho 5 giải thưởng (Best Strategist, Best Defense, Best Comeback, Knowledge Champion, Mentor–Mentee Synergy). Mặc định chỉ trình bày tôn vinh (presentation-only), không làm thay đổi điểm số chính thức trừ khi cấu hình `enable_award_bonus_score=True`.** | Tôn vinh các khía cạnh khác nhau của tinh thần đồng đội và chiến thuật theo đúng tinh thần team-building sự kiện. |
| **D15** | **Can thiệp hành chính & Audit Logging (Admin Overrides)** | §26 yêu cầu ghi log administrative override khi xử lý sự cố | **Mọi can thiệp của Host (skip phase, kick/đổi đội khi trận đang chạy, đóng câu hỏi kẹt, điều chỉnh coin) bắt buộc phải ghi `MatchEvent` loại `ADMINISTRATIVE_OVERRIDE` kèm `reason`. Không bao giờ log secret/token.** | Đảm bảo tính minh bạch, công bằng và có thể truy vết toàn bộ sự cố trong trận đấu thực tế. |

---

## Chuẩn Hóa Mô Hình Dữ Liệu & Ràng Buộc Khóa (Database Constraints)

1. `Match.room_code`: Ký tự in hoa + số dễ phân biệt (ví dụ loại bỏ `O`, `0`, `I`, `1`), độ dài 6 ký tự. Partial unique index trên các match có trạng thái `LOBBY` hoặc `ACTIVE`.
2. `TeamQuestion`: Unique constraint trên `(match_id, team_id, sequence_number)` và `(match_id, team_id, question_id)`.
3. `RewardClaim`: Unique constraint trên `team_question_id`. Đảm bảo 100% không bao giờ xảy ra double-claim.
4. `TeamUnlock`: Unique constraint trên `(team_id, unit_type_id)`.
5. `GameAction`: Unique constraint trên `(team_id, idempotency_key)` giúp chống trùng lệnh thao tác mạng.

---

## Chi Tiết Công Thức Giải Thưởng Vinh Danh (D14 — Optional Awards)

Theo FR-10 và §13, các giải thưởng này được tự động tính toán khi trận đấu kết thúc (`RESULTS` phase) và xuất hiện trên Màn hình Kết Quả (`ResultsPage`). Mặc định giải thưởng là presentation-only (không cộng điểm chính thức). Nếu trong match configuration bật `enable_award_bonus_score: True`, mỗi danh hiệu có thể thưởng thêm một lượng điểm cấu hình (ví dụ +25 điểm).

1. **Best Strategist (Bậc Thầy Chiến Thuật)**:
   - *Mục đích:* Tôn vinh khả năng tấn công và triệt hạ đối phương.
   - *Chỉ số đánh giá:* $P_{\text{strat}} = (\text{bases\_destroyed} \times 1000) + (\text{base\_damage\_dealt} \times 2) + (\text{correct\_answers} \times 10)$.
   - *Quy tắc:* Đội có $P_{\text{strat}}$ cao nhất sẽ nhận giải. Tie-break: Điểm tổng kết thúc trận.

2. **Best Defense (Bức Tường Kiên Cố)**:
   - *Mục đích:* Tôn vinh đội bảo toàn căn cứ và duy trì hệ thống phòng thủ tháp bền vững nhất.
   - *Chỉ số đánh giá:* $P_{\text{def}} = (\text{remaining\_base\_hp} \times 2) + (\text{surviving\_towers} \times 50)$.
   - *Quy tắc:* Đội có $P_{\text{def}}$ cao nhất. Tie-break: Đội có số lượng lính địch bị tiêu diệt bởi tháp cao hơn hoặc ít bị mất máu nhất.

3. **Best Comeback (Màn Lội Ngược Dòng Ngoạn Mục)**:
   - *Mục đích:* Tôn vinh đội gặp nguy hiểm (máu căn cứ tụt xuống thấp nhất hoặc tỷ lệ máu còn lại $\le 40\%$) nhưng vẫn kiên cường phản công và giành thứ hạng cao (Top 50% hoặc sống sót với điểm số ấn tượng).
   - *Quy tắc:* Trong số các đội có $\text{base\_hp} \le 40\%$ máu khởi đầu tại một thời điểm hoặc kết trận, chọn đội có thứ hạng chung cuộc cao nhất (hoặc gây sát thương phản công lớn nhất). Nếu không có đội nào bị xuống máu thấp, giải trao cho đội xếp thứ nhì.

4. **Knowledge Champion (Nhà Thông Thái Trí Tuệ)**:
   - *Mục đích:* Tôn vinh đội trả lời xuất sắc các câu hỏi chuyên môn team-building.
   - *Chỉ số đánh giá:* $P_{\text{know}} = (\text{correct\_answers} \times 100) + \text{remaining\_coins}$.
   - *Quy tắc:* Đội có số câu trả lời đúng nhiều nhất. Tie-break: Số coin tích luỹ còn lại.

5. **Mentor–Mentee Synergy (Hiệp Đồng Tác Chiến Hoàn Hảo)**:
   - *Mục đích:* Tôn vinh sự phối hợp nhịp nhàng giữa Mentor (định hướng chiến thuật, điều phối tháp/lính) và Mentee (trả lời câu hỏi, tạo tài nguyên).
   - *Chỉ số đánh giá:* $P_{\text{syn}} = \min(\text{tactical\_actions}, \text{questions\_answered}) \times 30 + (\text{correct\_answers} \times 15)$.
   - *Quy tắc:* Đội có sự cân bằng cao nhất giữa số action chiến thuật do Mentor kích hoạt và số câu hỏi Mentee trả lời.

---

## Quy Tắc Can Thiệp Sự Cố & Audit Trail (D15)

1. **Sự cố người chơi (Disconnect / Kẹt mạng):** Host có quyền chuyển đổi đội (`reassign_member`) hoặc loại người chơi (`kick_member`) trong lúc trận đang diễn ra qua cờ `is_override=True`. Hành động này lập tức ghi `MatchEvent` loại `ADMINISTRATIVE_OVERRIDE`.
2. **Sự cố câu hỏi kẹt:** Nếu một câu hỏi bị treo do lỗi kết nối client hoặc hết giờ mà không tự động chuyển trạng thái, Host có quyền gọi `override_close_stuck_question` để chuyển `TeamQuestion` sang `EXPIRED`, giải phóng trạng thái chờ của đội.
3. **Điều chỉnh coin bất thường:** Host có quyền bù/trừ coin qua `override_adjust_coins` để hoàn tác reward bị lỗi mạng.
4. **Không log Secret:** Tuyệt đối mọi bản ghi sự kiện `MatchEvent` không chứa `participant_token`, `host_token_hash`, mật khẩu hay chuỗi bí mật.

