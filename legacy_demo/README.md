# CAM AI — Pool Safety Monitoring

Web demo local bằng Streamlit, OpenCV, YOLO/ByteTrack và PyTorch. Có hai pipeline thay model qua adapter, chạy CPU và tự chọn CUDA nếu PyTorch nhận GPU.

**DEMO MODEL – kết quả không phải kết quả mô hình đã huấn luyện.** Không dùng prediction kịch bản hay checkpoint random để báo cáo kết quả nghiên cứu. Hệ thống chưa được xác thực cho vận hành cứu hộ.

## Chạy trên Windows

Mở PowerShell tại thư mục `cam_ai` (khuyến nghị Python 3.11–3.14):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Với CMD dùng `.venv\Scripts\activate.bat`. Nếu PowerShell chặn activate, không cần đổi chính sách máy:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Mở http://localhost:8501. Trong bản đã cài tại workspace này có sẵn `.venv`, chỉ cần lệnh chạy cuối. Môi trường tại workspace dùng `--system-site-packages` để tận dụng thư viện đã có; khi gửi cho nhóm không gửi `.venv`, tạo mới bằng lệnh ở trên.

## Demo ngay

1. Giữ `Mode A · Frame` và `Use Demo Model`.
2. Chọn `Use Demo Pool Video` hoặc upload MP4/AVI/MOV/MKV/WebM (tối đa 500 MB).
3. Bấm **Test Alarm**, cho phép âm thanh trong trình duyệt nếu cần; bỏ Mute.
4. Bấm **Start / Restart**. Đợi video time tới 6 giây để có WARNING, 8 giây để có DANGER với ngưỡng mặc định.
5. **Stop** đóng video và mọi clip đang ghi. **Start / Restart** bắt đầu lại từ frame đầu, tạo tracker/buffer/alert mới.
6. Mở **RECENT INCIDENTS → Refresh incidents** để xem snapshot, metadata và tải clip. Cảnh báo demo có `is_demo: true` và chữ DEMO trên ảnh/clip.

Kịch bản demo lặp mỗi 20 giây theo thời gian video: 0–4 swimming, 4–15 drowning, 15–20 out_of_water; confidence 0.92 là giá trị mô phỏng. Mode A mock không phát hiện người, không tạo box hoặc ID người: ID 0 nghĩa là FRAME. Đây là cách thử UI và cảnh báo, không phải phân tích nội dung video.

## Mode A — frame

- Mock: chạy offline không cần YOLO/PyTorch để khởi tạo model.
- YOLO classification: mỗi frame có một class/confidence; alert có phạm vi toàn khung hình, không đếm người.
- YOLO detection: model phải được train với các class mục tiêu, box phải biểu diễn người; ByteTrack giữ ID để alert theo người. Model YOLO COCO chỉ có class person không thay thế drowning classifier.
- Chỉ các detection có tracking ID mới được đưa vào cảnh báo.

Thay model: đặt trọng số ở **`models/best.pt`**, bỏ chọn Use Demo Model, hoặc upload `.pt` qua sidebar. Có thể nhập đường dẫn model khác, không sửa source. Adapter: `models/adapters/yolo_adapter.py`.

Class mapping đọc từ **`config/class_mapping.json`**: key là tên class model, value là một trong `drowning`, `swimming`, `out_of_water`. Ví dụ tên `Drowning` trong model thì thêm `"Drowning": "drowning"`. Model sai task/class sẽ báo lỗi dễ đọc. Chỉ load checkpoint YOLO từ thành viên/nguồn tin cậy vì định dạng này có thể chứa Python objects.

## Mode B — pose + temporal

Video → YOLO pose pretrained → ByteTrack (`persist=True`) → buffer riêng theo ID → 30 pose COCO thật liên tiếp `(30,17,2)` → classifier temporal → AlertManager.

Chọn Mode B và `Use Demo Pool Video → Pose close-up (bơi ngoài trời)` để thử sequence trên người cận cảnh. Clip dài khoảng 5 giây; đặt warning 0.5 s / critical 1 s nếu muốn thử cảnh báo scripted. Góc `Pool overview` có người quá nhỏ/bị che khuất, pretrained pose có thể không phát hiện được; UI sẽ báo chưa có prediction, không tạo ID/pose giả.

Chọn Mode B. Ô **Pretrained pose model** mặc định `yolov8n-pose.pt`; file nằm ở `models/yolov8n-pose.pt`. Nếu thiếu, Ultralytics tải khi khởi động lần đầu và cần Internet. Có thể nhập đường dẫn model pose local. **YOLO Pose chỉ lấy pose; không phải model phát hiện đuối nước.**

- Use Demo Model: pose/tracking là thật; classifier temporal theo kịch bản demo.
- Bỏ Use Demo Model, chọn `models/demo_lstm.pth`: chạy LSTM PyTorch random weights và vẫn hiện DEMO/UNTRAINED. Confidence random thường không vượt ngưỡng; dùng scripted demo để thử alarm.
- Bỏ Use Demo Model, upload checkpoint nhóm hoặc nhập `models/checkpoint.pth`: chạy model thật nếu tương thích schema.
- UI hiển thị `warming_up` và số pose trước khi đủ sequence. Không copy một pose 30 lần. Mất ID/mất frame quan sát/pose không hợp lệ sẽ bỏ buffer cũ, phải tích lũy lại.
- Chuẩn hóa tọa độ theo khung hình: `(x / width, y / height)`; 17 keypoints theo thứ tự COCO, điểm thiếu do YOLO trả về giữ `(0,0)`. Model của nhóm phải dùng cùng quy ước. Khung hình inference giữ tỷ lệ, chiều ngang tối đa 960 px và chiều cao tối đa 640 px.
- Sequence length có thể chỉnh ở sidebar nhưng phải khớp checkpoint. FPS/cách lấy mẫu khi triển khai phải phù hợp lúc train. Hiện mỗi frame nguồn đóng góp một pose, không resample FPS và không bỏ frame để tăng tốc.
- ByteTrack có thể đổi ID khi che khuất/giao nhau; không bảo đảm định danh tuyệt đối. Buffer reset giúp tránh dùng đoạn ngắt, không khắc phục mọi lỗi tracking.

### Hợp đồng checkpoint LSTM

Không thể coi mọi `.pt/.pth` là cùng kiến trúc. Nhóm xuất checkpoint dictionary theo mẫu sau sau khi đã huấn luyện `models.temporal_lstm.TemporalLSTM`. Thứ tự classes phải đúng output lúc train:

```python
import torch
checkpoint = {
    "format_version": 1,
    "architecture": "TemporalLSTM",
    "hidden_size": 64,
    "num_layers": 1,
    "num_classes": 3,
    "sequence_length": 30,
    "keypoints": 17,
    "coordinates": 2,
    "normalization": "frame_xy_0_1",
    "classes": ["drowning", "swimming", "out_of_water"],
    "trained": True,  # chỉ True khi thực sự đã huấn luyện
    "state_dict": model.state_dict(),
}
torch.save(checkpoint, "models/checkpoint.pth")
```

Architecture: reshape `(B,T,17,2)` → `(B,T,34)` → unidirectional LSTM → hidden ở bước cuối → Linear(hidden_size,3). Adapter dùng `weights_only=True`, kiểm tra schema, sequence, class, shape tensor, finite logits và `load_state_dict(strict=True)`. Cờ `trained` là khai báo của người xuất model, không tự chứng minh chất lượng mô hình.

Nếu nhóm gửi đúng schema: **chỉ thay/upload file trọng số**. Nếu nhóm dùng kiến trúc khác (bidirectional, CNN-LSTM, attention…), cập nhật **`models/temporal_lstm.py`** và **`models/adapters/lstm_adapter.py`**, hoặc viết adapter khác với `predict_sequence(sequence,timestamp)`. Không cần đổi dashboard, recorder hay AlertManager. Nếu preprocessing khác, đổi bước chuẩn hóa trong **`core/pose_extractor.py`** theo hợp đồng train. Không tự đổi tên keys hoặc ép load một checkpoint khác kiến trúc.

Tạo lại checkpoint demo hợp lệ (random/untrained):

```powershell
python -c "from models.temporal_lstm import create_demo_checkpoint; create_demo_checkpoint('models/demo_lstm.pth')"
```

## Cảnh báo, âm thanh và incident

Mỗi ID phải liên tục có class drowning với confidence ≥ ngưỡng. NORMAL trước warning duration; SUSPICIOUS từ warning duration; DANGER từ critical duration. Không cảnh báo từ một frame. Chuyển sang class khác, confidence thấp hoặc mất người sẽ reset khoảng thời gian. Mốc thời gian là `frame_index / FPS` của video, không phải tốc độ xử lý CPU. FPS không hợp lệ dùng 25; video variable FPS được xem như FPS cố định do OpenCV báo.

- Mặc định confidence 0.70, warning 2 s, critical 4 s. Sidebar ràng buộc critical > warning.
- Âm thanh tự tạo `assets/sounds/alert.wav`, không dùng âm thanh có bản quyền. Trigger chỉ khi bước vào DANGER. Mute tắt âm cảnh báo/Test Alarm; trình duyệt có thể yêu cầu bấm Play để mở quyền âm thanh.
- Mỗi lần chuyển WARNING hoặc DANGER tạo một incident trong `incidents/incident_<UTC>_<uuid>/`.
- `metadata.json`: person_id, scope, class, confidence, timestamp UTC, video_seconds, duration, state, model, is_demo, source, clip_status.
- `snapshot.jpg`: ảnh có overlay tại sự kiện.
- `clip.mp4`: khoảng 2 s trước + frame sự kiện + 2 s sau (pre-roll tối đa 2 s gồm frame sự kiện), JPEG ring buffer giữ RAM gọn. Ghi tiếp từng frame lên disk. Đầu video có ít pre-roll hơn.
- Stop/EOF trước đủ post-roll: đóng writer, đánh dấu `clip_status: partial`. Codec MP4 không khả dụng: vẫn giữ metadata/snapshot, `codec_unavailable`. Clip MPEG-4 Part 2 có thể cần VLC thay vì bộ phát web; UI cung cấp download.
- Phần Recent incidents hiển thị 20 incident mới nhất trên disk, gồm cả phiên trước. Không tự xóa dữ liệu.

## Video và licenses

Đã kèm video hồ bơi thật `assets/demo/pool_demo.mp4` (khoảng 15 giây, 960×540) chuyển từ Wikimedia Commons, tác giả Almanta, **CC BY-SA 4.0**. Chi tiết nguồn, link license và thay đổi ở **`assets/demo/SOURCE.md`**. Giữ attribution khi chia sẻ footage/clip dẫn xuất. Đây là cảnh bơi thông thường, không có nhãn drowning và không dùng đánh giá model.

Nếu video không có trong bản clone/gói nhận: đặt video có quyền sử dụng vào `assets/demo/pool_demo.mp4`, hoặc Upload Video. UI báo rõ khi thiếu, không crash. `assets/demo/outdoor_pool.webm` là bản tải nguồn của demo mặc định; `pool_source.webm` là footage hồ bơi khác của FASTILY, chỉ giữ để tham khảo.

YOLO pose weights và Ultralytics có điều khoản riêng, xem **`models/SOURCE.md`**. Bản demo không huấn luyện model phát hiện đuối nước.

## Metrics thật

Tab MODEL EVALUATION mặc định **No evaluation results available**; mọi demo/untrained đều không hiển thị metrics. Với model thật, upload `metrics.json` hoặc đặt ở project root. App chỉ đọc số nhóm cung cấp, không tự đánh giá và không xác minh model/dataset. Các key bắt buộc `accuracy`, `precision`, `recall`, `f1`, mỗi giá trị số hữu hạn trong [0,1]. Không có file metrics giả trong dự án.

## Kiểm thử

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python -m tests.integration_smoke
```

Test dùng video fixture tổng hợp tạm để kiểm tra I/O; fixture không được trưng bày như video hồ bơi. Có kiểm thử alert/reset, snapshot, clip pre/post/stop, class mapping, per-ID sequence, checkpoint lỗi, UI thiếu video và demo end-to-end. Một số test adapter dùng fake output có chủ đích; kiểm tra tích hợp thực tế trên footage hồ bơi được ghi trong `VALIDATION.md`.

Nếu load model lỗi: đọc thông báo trong UI, kiểm tra task/class/schema/đường dẫn. Nếu thiếu DLL OpenCV/PyTorch trên Windows, cài Microsoft Visual C++ Redistributable phù hợp. CPU không cần CUDA; khi muốn GPU phải cài bản PyTorch CUDA phù hợp môi trường của nhóm. Khi chia sẻ dự án giữ assets/models cần thiết, không chia sẻ `.venv`, `uploads` hay incident cá nhân không cần thiết.

## Cấu trúc

```text
cam_ai/
  app.py
  requirements.txt / requirements-dev.txt
  README.md / VALIDATION.md
  .streamlit/config.toml
  config/settings.py / class_mapping.json
  core/
    video_processor.py / pose_extractor.py / tracker.py
    alert_manager.py / incident_recorder.py / clip_recorder.py / evaluation.py
  models/
    temporal_lstm.py / demo_lstm.pth / yolov8n-pose.pt / SOURCE.md
    adapters/base.py / loader.py / mock_adapter.py / yolo_adapter.py / lstm_adapter.py
  assets/demo/pool_demo.mp4 / outdoor_pool.webm / SOURCE.md
  assets/sounds/alert.wav
  incidents/
  tests/
```

Tài liệu API tham khảo: [Streamlit fragments](https://docs.streamlit.io/develop/concepts/architecture/fragments), [Streamlit audio](https://docs.streamlit.io/develop/api-reference/media/st.audio), [Ultralytics tracking](https://docs.ultralytics.com/modes/track/).
