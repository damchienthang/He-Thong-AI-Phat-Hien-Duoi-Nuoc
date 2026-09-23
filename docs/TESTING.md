# Quy trình kiểm thử nhiệm vụ 3.2 — Dashboard cứu hộ

Kiểm thử video, hiển thị trạng thái, WebSocket, âm thanh và thao tác cứu hộ. Không bao gồm đánh giá Accuracy/F1 hoặc thảo luận 3.4; không thay kiểm thử điều kiện nhiễu 3.3 của V.Thắng.

## 1. Chạy app

PowerShell tại `cam_ai`:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Mở http://localhost:8501. Dùng MP4 H.264/WebM, ví dụ `assets/demo/outdoor_pool.webm`. Ghi ngày thử, phiên bản code, trình duyệt và máy thử.

## 2. Kiểm tra thủ công ngay, chưa cần backend

| Mã | Thao tác | Kết quả cần đạt |
|---|---|---|
| UI-01 | Mở app chưa kết nối AI | Chưa kết nối, số đếm `—`, không box giả |
| UI-02 | Chuyển Dashboard / Alert History / Settings | Đúng trang, không mất video/kết nối do chuyển menu |
| VID-01 | Chọn video → Play/Pause/tua | Video phát bằng trình duyệt, không nhấp nháy do thay ảnh qua Streamlit |
| VID-02 | Chọn video có codec không hỗ trợ | Báo lỗi dễ hiểu, trang không crash |
| AUDIO-01 | Bật âm → Thử chuông | Nghe tiếng; mở quyền âm thanh trình duyệt nếu bị chặn |
| AUDIO-02 | Tắt âm → Thử chuông | Không phát tiếng |
| WS-01 | Kết nối khi backend chưa chạy | Báo không kết nối được, không tự có kết quả AI |
| UI-03 | Thu chiều ngang cửa sổ khoảng 390 px | Bố cục gọn, không tràn ngang toàn trang |
| LOG-01 | Alert History → tải JSON | Đúng nhật ký cục bộ; chưa phải CSDL chung |

Video local chưa tự gửi tới backend. Không có box khi chưa kết nối AI là đúng.

## 3. Chạy test tự động với WebSocket giả lập

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe docs/check_dashboard.py
```

Máy cần Microsoft Edge và video `assets/demo/outdoor_pool.webm`. Edge chạy ẩn, script in `PASS: ...` khi đạt; có lỗi thì giữ traceback để sửa. Không cần backend thật hoặc model.

Script kiểm tra: menu chỉ có phần 3.2, video thực sự phát, layout desktop/mobile, nhận cảnh báo, gửi cứu hộ/báo động giả, chỉ hiện thành công sau ACK, hết hạn dữ liệu và biểu đồ. Test cập nhật ảnh `docs/dashboard-preview.png` từ video thật, không prediction giả trong ảnh xem trước.

Đây là kiểm thử frontend bằng fixture, không chứng minh AI nhận diện đuối nước đúng và không xác nhận loa thực sự phát tiếng.

## 4. Kiểm tra tích hợp cùng Thành khi backend sẵn sàng

Thống nhất schema ở `HANDOFF.md`, URL video/WebSocket, cùng stream_id và thời điểm. Upload/start/stop/tua từ frontend chưa điều khiển backend; cần thống nhất API nếu nhóm muốn có các thao tác này.

| Mã | Đầu vào/thao tác | Kết quả frontend cần đạt |
|---|---|---|
| INT-01 | Kết nối API thật | Hiện đã kết nối; số đếm chỉ hiện sau frame hợp lệ |
| INT-02 | Backend gửi NORMAL | Đúng ID, box xanh, số người khớp payload |
| INT-03 | Backend gửi WARNING | Box/trạng thái vàng, log ghi sự kiện |
| INT-04 | Backend gửi CRITICAL nhiều frame cùng incident | Box/trạng thái đỏ, chuông chỉ trigger lần đầu |
| INT-05 | Tắt âm khi có CRITICAL | Không phát âm thanh mới, cảnh báo hình ảnh vẫn có |
| INT-06 | Xác nhận cứu hộ | Gửi đúng ID/action; thành công sau ACK, Thành kiểm tra bản ghi CSDL |
| INT-07 | Báo động giả | Gửi false_alarm; cần ACK đúng action; không tự kết luận an toàn |
| INT-08 | Không nhận ACK | Sau 5 s cho thử lại, không báo thành công |
| INT-09 | Ngắt socket / dừng gửi frame quá 3 s | Ẩn box/số đếm hiện tại, báo mất kết nối/dữ liệu cũ |
| INT-10 | Backend gửi persons rỗng | Số người 0; khác với mất kết nối dùng `—` |
| INT-11 | JSON, confidence hoặc box không hợp lệ | Từ chối và báo lỗi, trang không crash |
| INT-12 | Video lệch thời gian AI quá 0.5 s | Ẩn box, báo lệch thời gian |
| INT-13 | Cùng event_id/state gửi lại nhiều lần | Không nhân bản log cảnh báo hoặc tăng tần suất mỗi frame |
| INT-14 | Kết nối lại / nhận nguồn khác | Không trộn heatmap của nguồn trước |

Backend của Thành quyết định bất động 10 giây/20 giây. Phụ trách giao diện kiểm tra trạng thái hiển thị khớp backend gửi, không tự huấn luyện hay thay logic AI.

## 5. Ghi minh chứng và bàn giao

| Mã ca | Ngày/môi trường | Dữ liệu thật/giả lập | Kết quả thực tế | Đạt/Chưa đạt/Chưa chạy | Minh chứng/lỗi |
|---|---|---|---|---|---|
| UI-01 | Điền khi thử | Không backend | Điền khi thử | Chưa chạy | Link ảnh |

Lưu ảnh/video các trạng thái: chưa kết nối, bình thường, vàng, đỏ, mất kết nối, xác nhận cứu hộ. Ảnh dùng fixture phải ghi rõ kiểm thử giả lập. Khi Thành chưa bàn giao, ghi các INT là **Chưa chạy với backend thật**.

Đầu ra bàn giao: source dashboard, hướng dẫn chạy, hợp đồng kết nối, bảng test có kết quả và ảnh các trạng thái đưa vào Chương 3. Chuyển hệ thống tích hợp cho V.Thắng kiểm thử 3.3; bên phụ trách giao diện hỗ trợ sửa lỗi UI. Tổng hợp/thảo luận 3.4 thuộc phần kết quả nghiên cứu.
