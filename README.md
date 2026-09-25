# HỆ THỐNG AI PHÁT HIỆN VÀ CẢNH BÁO NGUY CƠ ĐUỐI NƯỚC TẠI HỒ BƠI (NHÓM 7 - PPLNCKH)

> **Nhánh `webdemo`**: Cung cấp toàn bộ mã nguồn hệ thống Demo hoàn chỉnh tích hợp mô hình AI (YOLOv8n-pose + CNN-BiLSTM-Attention), Backend FastAPI và Giao diện Web giám sát thời gian thực.

---

## 🚀 Khởi chạy nhanh hệ thống WebDemo

### Cách 1: Chạy bằng file Batch (Khuyến nghị trên Windows)
Nhấp đúp chuột vào file **`CHAY_CHUONG_TRINH.bat`** tại thư mục gốc, hệ thống sẽ tự động khởi động server và mở trình duyệt tại:
👉 **http://localhost:8000**

### Cách 2: Khởi chạy thủ công bằng dòng lệnh

1. Cài đặt các thư viện phụ thuộc:
```bash
pip install -r requirements.txt
```

2. Khởi chạy Backend FastAPI:
```bash
cd WebDemo/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
Truy cập vào **http://localhost:8000** để sử dụng giao diện giám sát AI.

---

## 📁 Cấu trúc thư mục nhánh `webdemo`

- `CHAY_CHUONG_TRINH.bat`: Kịch bản 1-click khởi chạy toàn bộ server WebDemo trên Windows.
- `WebDemo/`:
  - `backend/`: Mã nguồn FastAPI xử lý luồng WebSocket và REST API phân tích ảnh/video.
    - `main.py`: Điểm vào chính của server FastAPI, quản lý WebSocket broadcast và tiền xử lý.
    - `model_inference.py`: Module tích hợp YOLOv8n-pose trích xuất 17 khớp xương và mô hình phân loại chuỗi thời gian CNN-LSTM.
    - `yolov8n-pose.pt`: Trọng số mô hình phát hiện dáng người YOLOv8n-pose.
    - `models/cnn_lstm_best.pth`: Trọng số mô hình học sâu CNN-BiLSTM phân loại hành vi đuối nước.
    - `train_cnn_lstm.py` / `evaluate_metrics.py`: Mã nguồn huấn luyện và đánh giá mô hình.
  - `frontend/`: Giao diện Dashboard HTML5/CSS/Vanilla JS giám sát trực quan thời gian thực.
    - `index.html`: Giao diện hiển thị camera / video, canvas vẽ khung xương và thanh rủi ro.
    - `app.js`: Xử lý giao tiếp WebSocket, tải video theo lô (batch preloading) và điều khiển âm thanh.
    - `style.css`: Bộ giao diện hiện đại với bảng điều khiển giám sát an ninh.

---

## CAM AI — Dashboard giám sát cứu hộ (Task 3.2 cũ)

Bản gọn theo bảng phân công: **3.2 Dashboard cứu hộ**. Giao diện nhận kết quả từ backend; không tự huấn luyện, nạp model hoặc phát hiện đuối nước.

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
