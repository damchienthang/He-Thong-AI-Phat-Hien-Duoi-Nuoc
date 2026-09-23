# CAM AI — Dashboard giám sát cứu hộ

Bản gọn theo bảng phân công: **3.2 Dashboard cứu hộ**. Giao diện nhận kết quả từ backend của Thành; không tự huấn luyện, nạp model hoặc phát hiện đuối nước.

Phạm vi triển khai là nhiệm vụ 3.2. Phần so sánh và thảo luận kết quả mô hình thuộc nhiệm vụ 3.4, ngoài phạm vi dashboard.

## Chạy

PowerShell tại `cam_ai`, dùng môi trường sẵn có:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Máy chưa có `.venv`: chạy `python -m venv .venv` trước. Mở http://localhost:8501. Dừng bằng Ctrl+C. Không cần cài YOLO/OpenCV/PyTorch cho phần giao diện.

## Cấu trúc

```text
cam_ai/
  app.py                  # Mở dashboard bằng Streamlit
  requirements.txt        # Chỉ Streamlit
  frontend/index.html     # UI giám sát, video, cảnh báo và WebSocket
  backend/                # Chờ FastAPI của Thành
  data/                   # Chờ dữ liệu Sinh/Sơn
  models/                 # Giữ trọng số; chờ model của Sinh/Thành
  results/                # Giữ chỗ dùng chung cho kết quả nghiên cứu
  docs/HANDOFF.md          # Hợp đồng bàn giao + việc đang chờ
  docs/TESTING.md          # Quy trình kiểm thử giao diện 3.2
  assets/                 # Video/âm thanh đã có
  uploads/                # Video upload cũ, giữ nguyên
  incidents/              # Incident cũ, giữ nguyên
  legacy_demo/            # Code demo cũ và tài liệu/test cũ để tham khảo
```

## Sử dụng

Giao diện theo mẫu dashboard nền tối: menu trái, Live Pool Monitor ở giữa, cảnh báo khẩn cấp/nhật ký bên phải, Pool Activity/AI Status/Alert Frequency/Detection Heatmap bên dưới. Cấu hình video, WebSocket và chuông nằm ở **Settings**. Nút **Chọn video** trên Dashboard mở file nhanh. Xem [ảnh giao diện](docs/dashboard-preview.png); video trong ảnh lấy từ nguồn có attribution ở `assets/demo/SOURCE.md` (Almanta, CC BY-SA 4.0).

1. Chọn video local: trình duyệt phát trực tiếp, có Play/Pause/tua; không gửi từng frame qua Streamlit nên tránh cách thay ảnh gây nhấp nháy trước đây.
2. Chưa có backend: xem được video, trạng thái AI là chưa kết nối, số đếm `—`. Video local chưa được gửi đi phân tích.
3. Thành cung cấp WebSocket: nhập URL → Kết nối. Dashboard nhận box xanh/vàng/đỏ, số người và cảnh báo. Chưa có API thật thì chưa thể khẳng định nhận diện người được.
4. Bật/tắt chuông và Thử chuông. Nút cứu hộ gửi yêu cầu qua WebSocket; chỉ hiện thành công sau phản hồi backend. Nhật ký cục bộ tải được JSON; CSDL dùng chung thuộc backend.
Nút **Báo động giả** cũng gửi yêu cầu tới backend, chỉ thành công khi nhận ACK đúng hành động; cần Thành hỗ trợ `action=false_alarm`. Biểu đồ tần suất và heatmap chỉ tính từ dữ liệu WebSocket đã nhận, không tạo sẵn số liệu. Heatmap thể hiện mật độ tâm box theo hình ảnh, không thể hiện khu vực nguy hiểm. Tài liệu bàn giao đã cập nhật các quy ước này.

Video và AI cần cùng nguồn/thời điểm; box lệch thời gian sẽ bị ẩn. Quy ước cảnh báo vàng 10 s/đỏ 20 s do backend thực hiện theo yêu cầu bất động của nhóm trưởng. Xem `docs/HANDOFF.md` để bàn giao với Thành.

Code cũ được lưu để tham khảo, không tự động chạy từ entry point mới. Giữ `.venv` hiện tại để tiện chạy; các thư viện AI cũ chưa bị gỡ khỏi môi trường. Không đưa `.venv`, video cá nhân hoặc incident cá nhân vào gói gửi nhóm nếu không cần.

## Kiểm tra bản gọn

Kiểm tra entry point bằng Streamlit AppTest và giao diện bằng Edge headless: video thật, điều hướng desktop/mobile, WebSocket bằng fixture, xác nhận cứu hộ/báo động giả chỉ sau ACK và hết hạn dữ liệu. Chưa kiểm thử với backend thật của Thành hoặc xác nhận chuông nghe được trên máy người dùng. Các biểu đồ trên Dashboard là thống kê giám sát, không phải đánh giá mô hình.

Kiểm tra lại tùy chọn: cài `playwright`, rồi chạy `python docs/check_dashboard.py` khi máy có Microsoft Edge. Đây là công cụ kiểm thử, không thuộc dependency để chạy dashboard.

Thực hiện theo [docs/TESTING.md](docs/TESTING.md). Đầu ra bàn giao: source dashboard, ảnh chụp trạng thái hoạt động cho Chương 3, bảng kiểm thử giao diện và quy ước kết nối với backend.
