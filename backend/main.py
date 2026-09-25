"""
HỆ THỐNG PHÁT HIỆN ĐUỐI NƯỚC THÔNG MINH
Backend FastAPI - WebSocket Real-time Detection
Nhóm 7 - PPLNCKH
"""

import asyncio
import base64
import io
import json
import random
import time
import math
from datetime import datetime
from typing import List, Optional, Dict, Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
import uvicorn

# Try importing ultralytics - fallback to mock if not available
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
    print("[INFO] YOLOv8 model loaded successfully")
except ImportError:
    YOLO_AVAILABLE = False
    print("[WARNING] ultralytics not available, using mock detection mode")

# Try importing trained CNN-LSTM classifier
try:
    from model_inference import classifier as cnn_lstm_classifier
    CNN_LSTM_AVAILABLE = cnn_lstm_classifier.is_ready
    if CNN_LSTM_AVAILABLE:
        print("[INFO] CNN-LSTM classifier loaded – using trained model")
    else:
        print("[WARNING] CNN-LSTM model not found – using rule-based fallback")
except Exception as e:
    CNN_LSTM_AVAILABLE = False
    cnn_lstm_classifier = None
    print(f"[WARNING] CNN-LSTM import failed: {e}")

# ─── App Configuration ────────────────────────────────────────────────────────
app = FastAPI(
    title="Drowning Detection API",
    description="Hệ thống phát hiện đuối nước sử dụng YOLOv8-Pose và CNN-LSTM",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
import os
frontend_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"))
print(f"[INFO] Frontend dir: {frontend_dir} (exists={os.path.exists(frontend_dir)})")
if os.path.exists(frontend_dir):
    # Mount at /static AND also handle root-level asset requests
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    # Also mount assets directly at root for style.css, app.js etc.
    app.mount("/assets", StaticFiles(directory=frontend_dir), name="assets")


# ─── YOLO Model ──────────────────────────────────────────────────────────────
pose_model = None
if YOLO_AVAILABLE:
    try:
        pose_model = YOLO("yolov8n-pose.pt")
        print("[INFO] YOLOv8n-pose model ready")
    except Exception as e:
        print(f"[WARNING] Could not load YOLO model: {e}")
        YOLO_AVAILABLE = False

# ─── Detection State ─────────────────────────────────────────────────────────
COCO_KEYPOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle"
]

SKELETON_PAIRS = [
    (0, 1), (0, 2), (1, 3), (2, 4),  # Head
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # Arms
    (11, 12), (5, 11), (6, 12),  # Torso
    (11, 13), (13, 15), (12, 14), (14, 16)  # Legs
]

class DetectionState:
    def __init__(self):
        self.active_persons: Dict[int, Dict] = {}
        self.alert_history: List[Dict] = []
        self.frame_count = 0
        self.start_time = time.time()
        self.total_detections = 0
        self.total_alerts = 0
        self.zone_alerts: Dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
        
        # Spatial Grid for temporal filtering (thay thế ByteTrack)
        self.grid_cells: Dict[str, Dict] = {}  # cell_id -> {risk_score, frames_at_risk}
        self.ALERT_COOLDOWN = 10  # seconds - giãn thời gian thông báo
        self.last_alert_time: Dict[str, float] = {}
    
    def get_grid_cell(self, x: float, y: float, w: int = 640, h: int = 480) -> str:
        """Chia khung hình thành grid 4x3, trả về cell ID"""
        col = min(int(x / w * 4), 3)  # A, B, C, D
        row = min(int(y / h * 3), 2)  # 1, 2, 3
        return f"{chr(65 + col)}{row + 1}"
    
    def check_alert_cooldown(self, cell_id: str) -> bool:
        """Kiểm tra có được phép gửi cảnh báo không (giãn thời gian 10s)"""
        now = time.time()
        if cell_id not in self.last_alert_time:
            return True
        return (now - self.last_alert_time[cell_id]) >= self.ALERT_COOLDOWN
    
    def trigger_alert(self, cell_id: str, person_id: int, confidence: float):
        if self.check_alert_cooldown(cell_id):
            self.last_alert_time[cell_id] = time.time()
            zone_letter = cell_id[0]
            self.zone_alerts[zone_letter] = self.zone_alerts.get(zone_letter, 0) + 1
            self.total_alerts += 1
            alert = {
                "id": self.total_alerts,
                "time": datetime.now().strftime("%H:%M:%S"),
                "cell": cell_id,
                "zone": f"Khu vực {zone_letter}",
                "person_id": person_id,
                "confidence": round(confidence * 100, 1),
                "status": "NGUY HIỂM",
                "type": "drowning"
            }
            self.alert_history.insert(0, alert)
            if len(self.alert_history) > 50:
                self.alert_history.pop()
            return alert
        return None

detection_state = DetectionState()

# ─── WebSocket Manager ────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# ─── Detection Logic ──────────────────────────────────────────────────────────
def preprocess_frame(frame: np.ndarray, max_dim: int = 1280) -> tuple:
    """Resize ảnh nếu quá lớn để tối ưu anchor matching và tốc độ phát hiện"""
    h, w = frame.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        new_w = int(w * scale)
        new_h = int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return resized, scale
    return frame, 1.0

def normalize_keypoints(kpts: np.ndarray) -> np.ndarray:
    """Chuẩn hóa tọa độ keypoints theo trung tâm hông (hip-centric) an toàn chống NaN"""
    kpts = np.nan_to_num(kpts, nan=0.0, posinf=0.0, neginf=0.0)
    
    # 1. Hip center (trung tâm hông)
    if np.any(kpts[11] != 0) and np.any(kpts[12] != 0):
        hip_center = (kpts[11] + kpts[12]) / 2.0
    elif np.any(kpts[5] != 0) and np.any(kpts[6] != 0):
        # Fallback to shoulder center
        hip_center = (kpts[5] + kpts[6]) / 2.0
    else:
        nonzero = kpts[np.any(kpts != 0, axis=1)]
        hip_center = np.mean(nonzero, axis=0) if len(nonzero) > 0 else np.array([0.0, 0.0])
        
    shifted = kpts - hip_center
    
    shoulder_center = (kpts[5] + kpts[6]) / 2.0
    torso_size = np.linalg.norm(shoulder_center - hip_center)
    if torso_size < 1e-3:
        nonzero = kpts[np.any(kpts != 0, axis=1)]
        if len(nonzero) >= 2:
            torso_size = float(np.max(np.ptp(nonzero, axis=0)))
        if torso_size < 1e-3:
            torso_size = 1.0
            
    normed = shifted / torso_size
    return np.nan_to_num(normed, nan=0.0, posinf=0.0, neginf=0.0)

def compute_drowning_risk(kpts: np.ndarray, conf: np.ndarray) -> tuple:
    """
    Phân tích nguy cơ đuối nước.
    Ưu tiên: CNN-LSTM trained model > rule-based geometric fallback
    Trả về (risk_score, risk_factors)
    """
    # ── Phương pháp 1: CNN-LSTM trained model (ưu tiên) ──────────────────────
    if CNN_LSTM_AVAILABLE and cnn_lstm_classifier is not None:
        try:
            norm_kpts = normalize_keypoints(kpts)  # hip-centric normalize
            result    = cnn_lstm_classifier.predict_single_frame(norm_kpts)
            risk_score = result["risk_score"]
            label      = result["label"]
            probs      = result["probabilities"]

            risk_factors = []
            if label == "Drowning":
                risk_factors.append(f"CNN-LSTM: Phát hiện đuối nước ({probs.get('Drowning',0)*100:.0f}%)")
            elif label == "Swimming":
                risk_factors.append(f"CNN-LSTM: Bơi lội an toàn ({probs.get('Swimming',0)*100:.0f}%)")
            else:
                risk_factors.append(f"CNN-LSTM: Trên bờ / Ngoài nước ({probs.get('Out of Water',0)*100:.0f}%)")

            return min(risk_score, 1.0), risk_factors
        except Exception as e:
            print(f"[CNN-LSTM inference error] {e} – falling back to rule-based")

    # ── Phương pháp 2: Rule-based (fallback) ─────────────────────────────────
    risk_factors = []
    risk_score = 0.0

    # 1. Goc nghieng co the
    if conf[5] > 0.2 and conf[6] > 0.2:
        shoulder_vec = kpts[6] - kpts[5]
        angle = abs(math.degrees(math.atan2(shoulder_vec[1], shoulder_vec[0])))
        if angle > 30:
            tilt_risk = min((angle - 30) / 60, 1.0) * 0.35
            risk_score += tilt_risk
            if tilt_risk > 0.2:
                risk_factors.append(f"Nghiêng người ({angle:.0f}°)")

    # 2. Vi tri dau so voi than
    if conf[0] > 0.2 and conf[11] > 0.2 and conf[12] > 0.2:
        hip_y  = (kpts[11][1] + kpts[12][1]) / 2
        head_y = kpts[0][1]
        if head_y > hip_y:
            risk_score += 0.4
            risk_factors.append("Đầu dưới mực hông")

    # 3. Tay giang cao
    if conf[9] > 0.2 and conf[10] > 0.2 and conf[5] > 0.2 and conf[6] > 0.2:
        wrist_y    = min(kpts[9][1], kpts[10][1])
        shoulder_y = (kpts[5][1] + kpts[6][1]) / 2
        if wrist_y < shoulder_y - 20:
            risk_score += 0.25
            risk_factors.append("Tay giơ cao (cầu cứu)")

    # 4. Keypoints bi che khuat / chim duoi nuoc
    visible = np.sum(conf > 0.2)
    if visible < 8:
        risk_score += (8 - visible) / 8 * 0.3
        risk_factors.append(f"Tư thế mờ trong nước ({visible}/17 điểm)")

    return min(risk_score, 1.0), risk_factors

def run_yolo_detection(frame: np.ndarray) -> List[Dict]:
    """
    Chạy YOLOv8-pose và trả về danh sách person detections.
    Sử dụng 2-stage adaptive confidence:
      - Giai đoạn 1: Quét chuẩn (conf=0.20)
      - Giai đoạn 2: Quét nhạy môi trường nước (conf=0.10) nếu giai đoạn 1 chưa bắt được người chìm/khuất
    """
    detections = []
    
    if pose_model is None or not YOLO_AVAILABLE:
        return detections
    
    proc_frame, scale = preprocess_frame(frame, max_dim=1280)
    inv_scale = 1.0 / scale if scale > 0 else 1.0
    
    # Stage 1: Standard confidence (0.20)
    results = pose_model(proc_frame, verbose=False, conf=0.20)
    
    # Stage 2: Adaptive confidence for water (0.10) if no persons detected
    if not results or len(results[0].boxes) == 0:
        results = pose_model(proc_frame, verbose=False, conf=0.10)
    
    if not results or len(results) == 0:
        return detections
    
    result = results[0]
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return detections
    
    kps_all = result.keypoints
    has_kpts = kps_all is not None and len(kps_all) == len(boxes)
    
    for i in range(len(boxes)):
        try:
            box = boxes[i]
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy() * inv_scale
            bbox_conf = float(box.conf[0].cpu().numpy())
            
            if has_kpts:
                kpts_data = kps_all[i].data[0].cpu().numpy()
                kpts_xy = kpts_data[:, :2] * inv_scale
                kpts_conf = kpts_data[:, 2]
            else:
                kpts_xy = np.zeros((17, 2), dtype=np.float32)
                kpts_conf = np.zeros(17, dtype=np.float32)
            
            risk_score, risk_factors = compute_drowning_risk(kpts_xy, kpts_conf)
            
            # Nếu phát hiện ở mức nhạy nước và cơ thể bị che khuất nhiều
            if bbox_conf < 0.20 and len(risk_factors) == 0:
                risk_factors.append(f"Cơ thể chìm một phần trong nước (conf {bbox_conf*100:.0f}%)")
            
            cx = float((x1 + x2) / 2)
            cy = float((y1 + y2) / 2)
            cell_id = detection_state.get_grid_cell(cx, cy, frame.shape[1], frame.shape[0])
            
            detections.append({
                "id": i,
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "bbox_conf": bbox_conf,
                "keypoints": kpts_xy.tolist(),
                "kp_conf": kpts_conf.tolist(),
                "risk_score": float(risk_score),
                "risk_factors": risk_factors,
                "cell": cell_id,
                "center": [cx, cy],
                "status": "NGUY HIỂM" if risk_score > 0.5 else ("CẢNH BÁO" if risk_score > 0.3 else "AN TOÀN")
            })
        except Exception as e:
            print(f"[Detection error item {i}] {e}")
            continue
    
    return detections

def mock_detection(frame: np.ndarray, frame_count: int) -> List[Dict]:
    """
    Mock detection cho demo khi không có GPU/model.
    Tạo ra các detections giả lập realistic để test UI.
    """
    h, w = frame.shape[:2]
    detections = []
    
    # Số người ngẫu nhiên (1-3 người)
    num_persons = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
    
    for pid in range(num_persons):
        # Vị trí ngẫu nhiên nhưng có xu hướng
        t = frame_count / 30.0 + pid * 2.1
        cx = int(w * (0.25 + 0.5 * abs(math.sin(t * 0.3 + pid))))
        cy = int(h * (0.3 + 0.4 * abs(math.cos(t * 0.2 + pid * 1.3))))
        
        box_w, box_h = 80, 180
        x1, y1 = max(0, cx - box_w//2), max(0, cy - box_h//2)
        x2, y2 = min(w, cx + box_w//2), min(h, cy + box_h//2)
        
        # Risk score có dao động theo thời gian
        base_risk = 0.1 + 0.15 * pid
        cycle_risk = 0.3 * abs(math.sin(frame_count * 0.05 + pid * 1.5))
        risk_score = min(base_risk + cycle_risk + random.uniform(-0.05, 0.05), 1.0)
        
        # Generate mock keypoints (hình người đứng)
        keypoints = generate_mock_keypoints(cx, cy, box_w, box_h, risk_score)
        kp_conf = [random.uniform(0.5, 0.95) for _ in range(17)]
        
        risk_factors = []
        if risk_score > 0.5:
            risk_factors = random.sample([
                "Nghiêng người bất thường", "Đầu dưới mức hông",
                "Tay giơ cao (cầu cứu)", "Tư thế mờ"
            ], k=random.randint(1, 2))
        
        cell_id = detection_state.get_grid_cell(cx, cy, w, h)
        
        detections.append({
            "id": pid,
            "bbox": [float(x1), float(y1), float(x2), float(y2)],
            "bbox_conf": random.uniform(0.7, 0.95),
            "keypoints": keypoints,
            "kp_conf": kp_conf,
            "risk_score": risk_score,
            "risk_factors": risk_factors,
            "cell": cell_id,
            "center": [float(cx), float(cy)],
            "status": "NGUY HIỂM" if risk_score > 0.5 else ("CẢNH BÁO" if risk_score > 0.3 else "AN TOÀN")
        })
    
    return detections

def generate_mock_keypoints(cx, cy, bw, bh, risk_score):
    """Tạo keypoints giả lập hình người"""
    tilt = risk_score * 30  # nghiêng theo risk
    kpts = [
        [cx, cy - bh*0.45],  # 0: nose
        [cx-5, cy - bh*0.47], [cx+5, cy - bh*0.47],  # 1,2: eyes
        [cx-8, cy - bh*0.44], [cx+8, cy - bh*0.44],  # 3,4: ears
        [cx - bw*0.35, cy - bh*0.2],  # 5: left shoulder
        [cx + bw*0.35, cy - bh*0.2],  # 6: right shoulder
        [cx - bw*0.45, cy],  # 7: left elbow
        [cx + bw*0.45, cy],  # 8: right elbow
        [cx - bw*0.4, cy + bh*0.15],  # 9: left wrist
        [cx + bw*0.4, cy + bh*0.15],  # 10: right wrist
        [cx - bw*0.2, cy + bh*0.1],  # 11: left hip
        [cx + bw*0.2, cy + bh*0.1],  # 12: right hip
        [cx - bw*0.22, cy + bh*0.3],  # 13: left knee
        [cx + bw*0.22, cy + bh*0.3],  # 14: right knee
        [cx - bw*0.2, cy + bh*0.48],  # 15: left ankle
        [cx + bw*0.2, cy + bh*0.48],  # 16: right ankle
    ]
    # Apply tilt
    if risk_score > 0.4:
        rad = math.radians(tilt)
        cos_t, sin_t = math.cos(rad), math.sin(rad)
        kpts = [
            [cx + (p[0]-cx)*cos_t - (p[1]-cy)*sin_t,
             cy + (p[0]-cx)*sin_t + (p[1]-cy)*cos_t]
            for p in kpts
        ]
    return kpts

def draw_detections(frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
    """Vẽ bounding boxes, skeleton và risk indicators lên frame"""
    overlay = frame.copy()
    h, w = frame.shape[:2]
    
    # Nếu không phát hiện thấy người, vẽ thông báo rõ ràng lên màn hình
    if not detections or len(detections) == 0:
        notice = "AI SCAN HOÀN TẤT: 0 NGƯỜI PHÁT HIỆN"
        (nw, nh), _ = cv2.getTextSize(notice, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
        nx = max(15, (w - nw) // 2)
        ny = max(40, h // 12)
        cv2.rectangle(frame, (nx - 12, ny - nh - 10), (nx + nw + 12, ny + 10), (20, 24, 33), -1)
        cv2.rectangle(frame, (nx - 12, ny - nh - 10), (nx + nw + 12, ny + 10), (56, 189, 248), 2)
        cv2.putText(frame, notice, (nx, ny), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (56, 189, 248), 2)
        
        sub = "Hệ thống đã quét toàn bộ ảnh (không có người hoặc người bị chìm/khuất hoàn toàn)"
        (sw, sh), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        sx = max(15, (w - sw) // 2)
        sy = ny + 26
        cv2.rectangle(frame, (sx - 8, sy - sh - 6), (sx + sw + 8, sy + 6), (15, 20, 30), -1)
        cv2.putText(frame, sub, (sx, sy), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (148, 163, 184), 1)
    
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        risk = det["risk_score"]
        status = det["status"]
        
        # Màu theo mức độ nguy hiểm
        if risk > 0.5:
            color = (0, 0, 255)  # Đỏ - NGUY HIỂM
            bg_alpha = 0.3
        elif risk > 0.3:
            color = (0, 165, 255)  # Cam - CẢNH BÁO
            bg_alpha = 0.2
        else:
            color = (0, 200, 50)  # Xanh - AN TOÀN
            bg_alpha = 0.1
        
        # Vẽ bounding box
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.addWeighted(overlay, bg_alpha, frame, 1 - bg_alpha, 0, frame)
        overlay = frame.copy()
        
        # Vẽ skeleton
        kpts = det["keypoints"]
        kp_conf = det["kp_conf"]
        
        # Vẽ các đường xương
        for (a, b) in SKELETON_PAIRS:
            if a < len(kpts) and b < len(kpts):
                if kp_conf[a] > 0.15 and kp_conf[b] > 0.15:
                    pa = (int(kpts[a][0]), int(kpts[a][1]))
                    pb = (int(kpts[b][0]), int(kpts[b][1]))
                    cv2.line(frame, pa, pb, color, 2)
        
        # Vẽ các điểm khớp
        for k, (kx, ky) in enumerate(kpts):
            if kp_conf[k] > 0.15:
                cv2.circle(frame, (int(kx), int(ky)), 4, (255, 255, 255), -1)
                cv2.circle(frame, (int(kx), int(ky)), 4, color, 1)
        
        # Label
        label = f"#{det['id']} {status} {risk*100:.0f}%"
        label_y = max(y1 - 10, 20)
        
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(frame, (x1, label_y - lh - 5), (x1 + lw + 4, label_y + 2), color, -1)
        cv2.putText(frame, label, (x1 + 2, label_y - 2),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    
    # Watermark grid
    h, w = frame.shape[:2]
    for i in range(1, 4):
        cv2.line(frame, (w * i // 4, 0), (w * i // 4, h), (255, 255, 255), 1)
    for i in range(1, 3):
        cv2.line(frame, (0, h * i // 3), (w, h * i // 3), (255, 255, 255), 1)
    
    # Grid labels
    for col, letter in enumerate("ABCD"):
        for row in range(3):
            tx = w * col // 4 + 5
            ty = h * row // 3 + 18
            cv2.putText(frame, f"{letter}{row+1}", (tx, ty),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    
    # Timestamp
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(frame, ts, (10, h - 10),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    cv2.putText(frame, "AI Drowning Detection - Nhom 7",
               (w - 280, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    
    return frame

def frame_to_base64(frame: np.ndarray) -> str:
    """Chuyển frame OpenCV sang base64 JPEG"""
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buffer).decode('utf-8')

# ─── Demo Streaming State ─────────────────────────────────────────────────────
demo_cap = None
demo_running = False

# ─── API Endpoints ─────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    frontend_index = os.path.join(frontend_dir, "index.html")
    if os.path.exists(frontend_index):
        return FileResponse(frontend_index)
    return JSONResponse({"status": "ok", "message": "Drowning Detection API v1.0"})

@app.get("/api/status")
async def get_status():
    uptime = int(time.time() - detection_state.start_time)
    return {
        "status": "online",
        "mode": "YOLOv8-Pose + CNN-LSTM" if (YOLO_AVAILABLE and CNN_LSTM_AVAILABLE) else ("YOLOv8" if YOLO_AVAILABLE else "Demo (Mock)"),
        "cnn_lstm_active": CNN_LSTM_AVAILABLE,
        "uptime_seconds": uptime,
        "frame_count": detection_state.frame_count,
        "total_detections": detection_state.total_detections,
        "total_alerts": detection_state.total_alerts,
        "connected_clients": len(manager.active_connections),
        "alert_cooldown_seconds": detection_state.ALERT_COOLDOWN,
    }

@app.get("/api/metrics")
async def get_model_metrics():
    metrics_path = os.path.join(os.path.dirname(__file__), "models", "full_metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"status": "not_evaluated"}

@app.get("/api/alerts")
async def get_alerts():
    return {"alerts": detection_state.alert_history[:20]}

@app.get("/api/stats")
async def get_stats():
    uptime = int(time.time() - detection_state.start_time)
    fps_avg = detection_state.frame_count / max(uptime, 1)
    return {
        "frame_count": detection_state.frame_count,
        "total_alerts": detection_state.total_alerts,
        "total_detections": detection_state.total_detections,
        "zone_alerts": detection_state.zone_alerts,
        "fps_average": round(fps_avg, 1),
        "uptime": uptime,
        "mode": "YOLOv8-Pose + CNN-LSTM" if (YOLO_AVAILABLE and CNN_LSTM_AVAILABLE) else ("YOLOv8" if YOLO_AVAILABLE else "Mock Demo")
    }

@app.post("/api/detect/image")
async def detect_image(file: UploadFile = File(...)):
    """Upload ảnh và chạy detection"""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        return JSONResponse({"error": "Invalid image"}, status_code=400)
    
    if YOLO_AVAILABLE and pose_model:
        detections = run_yolo_detection(frame)
    else:
        detections = mock_detection(frame, detection_state.frame_count)
    
    result_frame = draw_detections(frame.copy(), detections)
    img_b64 = frame_to_base64(result_frame)
    
    alerts_triggered = []
    for det in detections:
        if det["risk_score"] > 0.5:
            alert = detection_state.trigger_alert(det["cell"], det["id"], det["risk_score"])
            if alert:
                alerts_triggered.append(alert)
    
    return {
        "detections": detections,
        "alerts": alerts_triggered,
        "processed_image": img_b64,
        "mode": "yolo" if YOLO_AVAILABLE else "mock"
    }

@app.websocket("/ws/video")
async def websocket_video(websocket: WebSocket):
    """
    WebSocket endpoint for real-time video streaming and detection.
    Client gửi frame base64, server trả về kết quả detection.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("type") == "frame":
                # Decode frame từ client
                img_data = base64.b64decode(msg["data"])
                nparr = np.frombuffer(img_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is None:
                    continue
                
                detection_state.frame_count += 1
                
                # Run detection
                if YOLO_AVAILABLE and pose_model:
                    detections = run_yolo_detection(frame)
                else:
                    detections = mock_detection(frame, detection_state.frame_count)
                
                detection_state.total_detections += len(detections)
                
                # Check alerts
                new_alerts = []
                for det in detections:
                    if det["risk_score"] > 0.5:
                        alert = detection_state.trigger_alert(det["cell"], det["id"], det["risk_score"])
                        if alert:
                            new_alerts.append(alert)
                
                # Draw and encode result
                result_frame = draw_detections(frame.copy(), detections)
                img_b64 = frame_to_base64(result_frame)
                
                await websocket.send_json({
                    "type": "result",
                    "frame": img_b64,
                    "detections": detections,
                    "new_alerts": new_alerts,
                    "frame_count": detection_state.frame_count,
                    "stats": {
                        "total_detections": detection_state.total_detections,
                        "total_alerts": detection_state.total_alerts,
                        "zone_alerts": detection_state.zone_alerts
                    }
                })
            
            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong", "time": time.time()})
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS Error] {e}")
        manager.disconnect(websocket)

@app.websocket("/ws/demo")
async def websocket_demo(websocket: WebSocket):
    """
    Demo WebSocket - tự tạo frame giả lập khi không có camera.
    Server chủ động gửi frames với mock detections.
    """
    await manager.connect(websocket)
    frame_idx = 0
    
    # Tạo background frame giả lập hồ bơi
    pool_bg = create_pool_background()
    
    try:
        while True:
            # Tạo frame với animation
            frame = animate_pool_frame(pool_bg.copy(), frame_idx)
            
            if YOLO_AVAILABLE and pose_model:
                detections = run_yolo_detection(frame)
            else:
                detections = mock_detection(frame, frame_idx)
            
            detection_state.frame_count += 1
            detection_state.total_detections += len(detections)
            frame_idx += 1
            
            # Check alerts
            new_alerts = []
            for det in detections:
                if det["risk_score"] > 0.5:
                    alert = detection_state.trigger_alert(
                        det["cell"], det["id"], det["risk_score"]
                    )
                    if alert:
                        new_alerts.append(alert)
            
            # Draw detections
            result_frame = draw_detections(frame, detections)
            img_b64 = frame_to_base64(result_frame)
            
            try:
                await websocket.send_json({
                    "type": "demo_frame",
                    "frame": img_b64,
                    "detections": detections,
                    "new_alerts": new_alerts,
                    "frame_count": detection_state.frame_count,
                    "stats": {
                        "total_detections": detection_state.total_detections,
                        "total_alerts": detection_state.total_alerts,
                        "zone_alerts": detection_state.zone_alerts,
                        "mode": "YOLOv8" if YOLO_AVAILABLE else "Mock Demo"
                    }
                })
            except Exception:
                break
            
            await asyncio.sleep(0.1)  # ~10 FPS demo
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Demo WS Error] {e}")
    finally:
        manager.disconnect(websocket)

def create_pool_background() -> np.ndarray:
    """Tạo background hồ bơi giả"""
    h, w = 480, 640
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    
    # Pool water - xanh dương
    frame[:] = (180, 120, 40)  # BGR - màu nước hồ
    
    # Pool lanes
    for i in range(0, w, 80):
        cv2.line(frame, (i, 0), (i, h), (200, 150, 60), 1)
    
    # Pool border
    cv2.rectangle(frame, (10, 10), (w-10, h-10), (220, 180, 100), 3)
    
    # Add some texture
    for _ in range(200):
        x, y = random.randint(0, w-1), random.randint(0, h-1)
        cv2.circle(frame, (x, y), random.randint(1, 3), (190, 135, 50), -1)
    
    return frame

def animate_pool_frame(frame: np.ndarray, frame_idx: int) -> np.ndarray:
    """Thêm hiệu ứng chuyển động nước"""
    h, w = frame.shape[:2]
    # Ripple effect
    for _ in range(10):
        t = frame_idx * 0.05
        x = int(w/2 + w*0.3 * math.sin(t + _ * 0.7))
        y = int(h/2 + h*0.2 * math.cos(t * 0.8 + _ * 0.5))
        r = int(5 + 3 * math.sin(t * 2 + _))
        cv2.circle(frame, (x, y), r, (200, 150, 70), 1)
    return frame

if __name__ == "__main__":
    print("=" * 60)
    print("  HỆ THỐNG PHÁT HIỆN ĐUỐI NƯỚC - NHÓM 7")
    print("  Backend API: http://localhost:8000")
    print("  Demo mode:", "YOLOv8" if YOLO_AVAILABLE else "Mock (no GPU model)")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
