# Bàn giao và tích hợp dashboard

Phạm vi: **3.2 — Dashboard giám sát cứu hộ**. Đánh giá mô hình và thảo luận H1/H2/H3 thuộc nhiệm vụ 3.4, ngoài phạm vi giao diện.

Đây là hợp đồng **đề xuất**, chưa phải API đã được Thành xác nhận. Khi nhận API thật chỉ sửa `frontend/index.html`; giao diện không nạp model hoặc chạy AI.

## Video và WebSocket

- Thành cung cấp URL video HTTP(S) mà trình duyệt phát được (khuyến nghị MP4 H.264) hoặc video gốc để chọn local; video phải đúng với `stream_id` của backend.
- URL WebSocket mặc định `ws://localhost:8000/ws/monitor`, sửa trực tiếp trên giao diện.
- Backend gửi frame message v1 bên dưới. Tọa độ box chuẩn hóa [0,1], theo frame video gốc.
- Backend quyết định trạng thái theo bất động: WARNING 10 s, CRITICAL 20 s theo phân công. Dashboard chỉ hiển thị; không suy ra bất động từ confidence.
- Chỉ vẽ box khi `video.currentTime` lệch `video_time` không quá 0.5 s. Sau 3 s không có frame mới: trạng thái dữ liệu cũ, ẩn số đếm/box. Tua video local không điều khiển backend; cần đồng bộ nguồn/thời điểm khi tích hợp.
- `is_demo=true` phải được hiển thị; không xem prediction demo là bằng chứng nghiên cứu.

```json
{
  "type": "frame", "version": 1, "stream_id": "pool-01",
  "video_time": 12.4, "model": "CNN-LSTM", "is_demo": false,
  "persons": [{
    "id": 3, "label": "drowning", "confidence": 0.91,
    "state": "WARNING", "duration": 10.2,
    "box": [0.1, 0.2, 0.3, 0.7], "event_id": "incident-001"
  }]
}
```

Ví dụ trên chỉ minh họa schema, không tự nạp vào dashboard. `persons: []` là backend không có người theo dõi; mất kết nối dùng dấu `—`, không số 0. State: NORMAL/WARNING/CRITICAL/WARMING_UP. Label: drowning/swimming/out_of_water/warming_up. Không có box thì gửi null. `event_id` ổn định trong một sự cố và đổi khi có sự cố mới, bắt buộc cho WARNING/CRITICAL.

Dashboard gửi:

```json
{"type":"acknowledge","version":1,"stream_id":"pool-01","event_id":"incident-001","person_id":3,"action":"rescue_dispatched","client_time":"ISO-8601"}
```

Backend lưu CSDL và trả:

```json
{"type":"acknowledged","version":1,"stream_id":"pool-01","event_id":"incident-001","person_id":3}
```

Chỉ khi nhận phản hồi mới hiện xác nhận thành công. Sau 5 s không có phản hồi, cho thử lại. Backend xử lý idempotent theo stream_id/event_id/action. Xác nhận nghĩa là cứu hộ đã triển khai, không khẳng định nạn nhân an toàn. Chuông chỉ phát một lần khi nhận CRITICAL cho mỗi incident.

### Nút Báo động giả

Giao diện có thêm nút **Báo động giả** theo mẫu dashboard. Gửi cùng message `acknowledge`, nhưng `action: "false_alarm"`. Backend phải phản hồi `type: "acknowledged"` kèm đúng `stream_id`, `event_id`, `person_id` và **`action: "false_alarm"`**. ACK cũ không có action chỉ được chấp nhận cho `rescue_dispatched`, không được hiểu nhầm là xác nhận báo động giả. Đây là phần hợp đồng đề xuất bổ sung, cần Thành hỗ trợ. Frontend không tự đổi trạng thái cảnh báo thành an toàn sau khi bấm nút.

### Biểu đồ dashboard

- Alert Frequency: số lần nhận WARNING/CRITICAL mới, phân biệt bằng stream_id/event_id/state; biểu đồ 15 phút, theo phút nhận ở trình duyệt. Không phải lịch sử toàn hệ thống hay số liệu đánh giá model.
- Detection Heatmap: tâm box của các người đang theo dõi; tối đa một lần lấy mẫu mỗi giây video, giữ tối đa 5.000 điểm của nguồn hiện tại. Tọa độ tương đối với hình ảnh, không phải tọa độ mặt bằng hồ bơi. Màu nóng là mật độ xuất hiện, không phải nguy cơ đuối nước.
- Reset biểu đồ khi kết nối lại; khi đổi stream_id, reset các điểm/vị trí và dữ liệu tần suất của nguồn trước. Không có dữ liệu: hiện trạng thái chờ.
- Dữ liệu demo được ghi nhãn trong thẻ AI Status và từng cảnh báo; không dùng các biểu đồ này làm metrics nghiên cứu.

## Phần còn chờ

- Nhóm trưởng: duyệt giao diện theo mẫu và quy trình thao tác cứu hộ.
- Thành: URL stream, schema xác nhận, API/video synchronization và CSDL thật.
- Sinh/Sơn: chuyển dữ liệu/model cho backend; dashboard không phụ thuộc trực tiếp vào dataset/trọng số.
- Phụ trách giao diện: kiểm tra tích hợp với backend, chụp trạng thái hoạt động và bàn giao dashboard.
- V.Thắng: nhận hệ thống tích hợp để kiểm thử 3.3; chuyển lỗi UI cho bên phụ trách giao diện.
- Phụ trách kết quả nghiên cứu: tổng hợp/thảo luận 3.4 riêng, không phải điều kiện để chạy dashboard.

Quy trình kiểm thử giao diện: `TESTING.md`.
