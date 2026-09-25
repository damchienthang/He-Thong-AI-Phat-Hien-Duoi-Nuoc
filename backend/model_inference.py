"""
model_inference.py - CNN-LSTM Drowning Detection (v2)
Hỗ trợ cả model v1 (34 features) và v2 (68 features với velocity)
"""
import os
import numpy as np
import torch
import torch.nn as nn


# ── Architecture v1 (34 features) ───────────────────────────────────────────
class CNN_LSTM(nn.Module):
    """Kiến trúc v1 - 34 features, dùng khi load cnn_lstm_best.pth"""
    def __init__(self, input_size, cnn_ch=64, lstm_h=128,
                 lstm_layers=2, num_classes=3, dropout=0.4):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv1d(input_size, cnn_ch, kernel_size=3, padding=1),
            nn.BatchNorm1d(cnn_ch),
            nn.GELU(),
            nn.Dropout(dropout * 0.5),
            nn.Conv1d(cnn_ch, cnn_ch * 2, kernel_size=3, padding=1),
            nn.BatchNorm1d(cnn_ch * 2),
            nn.GELU(),
            nn.Dropout(dropout * 0.5),
        )
        self.lstm = nn.LSTM(
            input_size=cnn_ch * 2, hidden_size=lstm_h,
            num_layers=lstm_layers, batch_first=True,
            dropout=dropout if lstm_layers > 1 else 0.0,
            bidirectional=True
        )
        lstm_out_size = lstm_h * 2
        self.attn = nn.Sequential(
            nn.Linear(lstm_out_size, 32), nn.Tanh(), nn.Linear(32, 1)
        )
        self.clf = nn.Sequential(
            nn.LayerNorm(lstm_out_size),
            nn.Linear(lstm_out_size, 128), nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(128, num_classes)
        )

    def forward(self, x):
        cnn_out  = self.cnn(x.permute(0, 2, 1))
        lstm_in  = cnn_out.permute(0, 2, 1)
        lstm_out, _ = self.lstm(lstm_in)
        attn_w   = torch.softmax(self.attn(lstm_out), dim=1)
        context  = (attn_w * lstm_out).sum(dim=1)
        return self.clf(context)


# ── Architecture v2 (68 features, improved) ─────────────────────────────────
class ImprovedCNNLSTM(nn.Module):
    """Kiến trúc v2 - 68 features, multi-head attention, dùng khi load cnn_lstm_v2_best.pth"""
    def __init__(self, F, cnn_ch=128, lstm_h=256,
                 lstm_layers=2, num_classes=3, dropout=0.4, nhead=4):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv1d(F, cnn_ch, 3, padding=1),       nn.BatchNorm1d(cnn_ch),   nn.GELU(),
            nn.Dropout(dropout * 0.4),
            nn.Conv1d(cnn_ch, cnn_ch, 3, padding=1),   nn.BatchNorm1d(cnn_ch),   nn.GELU(),
            nn.Dropout(dropout * 0.4),
            nn.Conv1d(cnn_ch, cnn_ch*2, 3, padding=1), nn.BatchNorm1d(cnn_ch*2), nn.GELU(),
            nn.Dropout(dropout * 0.4),
        )
        self.lstm = nn.LSTM(cnn_ch*2, lstm_h, lstm_layers, batch_first=True,
                            dropout=dropout if lstm_layers > 1 else 0, bidirectional=True)
        H = lstm_h * 2

        self.mha = nn.MultiheadAttention(embed_dim=H, num_heads=nhead,
                                          dropout=dropout*0.5, batch_first=True)
        self.norm = nn.LayerNorm(H)
        self.attn_pool = nn.Sequential(nn.Linear(H, 64), nn.Tanh(), nn.Linear(64, 1))
        self.clf = nn.Sequential(
            nn.LayerNorm(H),
            nn.Linear(H, 256), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(256, 64), nn.GELU(), nn.Dropout(dropout * 0.5),
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        c = self.cnn(x.permute(0, 2, 1)).permute(0, 2, 1)
        o, _ = self.lstm(c)
        o2, _ = self.mha(o, o, o)
        o = self.norm(o + o2)
        w = torch.softmax(self.attn_pool(o), dim=1)
        ctx = (w * o).sum(dim=1)
        return self.clf(ctx)


# ── DrowningClassifier ────────────────────────────────────────────────────────
class DrowningClassifier:
    """
    Wrapper inference cho mô hình CNN-LSTM đã huấn luyện.
    Tự động phát hiện v1 (34 features) hay v2 (68 features).
    """
    CLASS_NAMES = ["Out of Water", "Drowning", "Swimming"]
    RISK_MAP    = {"Out of Water": 0.05, "Drowning": 0.95, "Swimming": 0.10}

    def __init__(self, model_path: str, device=None):
        self.device = device or torch.device(
            'cuda' if torch.cuda.is_available() else 'cpu'
        )
        self.model       = None
        self.config      = None
        self.class_names = self.CLASS_NAMES
        self.feature_dim = 34   # default v1
        self.use_velocity = False

        if os.path.exists(model_path):
            self._load(model_path)
        else:
            print(f"[DrowningClassifier] Model not found: {model_path} – using rule-based fallback")

    def _load(self, path: str):
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        cfg  = ckpt["config"]
        self.config = cfg

        self.class_names = self.CLASS_NAMES
        self.feature_dim = cfg.get("input_size", 34)
        self.use_velocity = (self.feature_dim >= 68)

        if self.use_velocity:
            # V2 model
            self.model = ImprovedCNNLSTM(
                F           = cfg["input_size"],
                cnn_ch      = cfg.get("cnn_ch", 128),
                lstm_h      = cfg.get("lstm_h", 256),
                lstm_layers = cfg.get("lstm_layers", 2),
                num_classes = cfg["num_classes"],
                dropout     = cfg.get("dropout", 0.4),
            ).to(self.device)
        else:
            # V1 model
            self.model = CNN_LSTM(
                input_size  = cfg["input_size"],
                cnn_ch      = cfg.get("cnn_ch", 64),
                lstm_h      = cfg.get("lstm_h", 128),
                lstm_layers = cfg.get("lstm_layers", 2),
                num_classes = cfg["num_classes"],
                dropout     = cfg.get("dropout", 0.4),
            ).to(self.device)

        self.model.load_state_dict(ckpt["model_state"])
        self.model.eval()
        version = "v2 (velocity+MHA)" if self.use_velocity else "v1"
        print(f"[DrowningClassifier] Loaded {version} model from {path}")
        print(f"  Features  : {self.feature_dim}")
        print(f"  Classes   : {self.class_names}")
        print(f"  Val F1    : {ckpt.get('val_f1', '?')}")
        print(f"  Val Acc   : {ckpt.get('val_acc', '?')}")

    @property
    def is_ready(self) -> bool:
        return self.model is not None

    # ── Keypoint normalization ───────────────────────────────────────────────
    @staticmethod
    def _normalize_kpts(kpts: np.ndarray) -> np.ndarray:
        """(17,2) → normalized (17,2)"""
        hip_center = (kpts[11] + kpts[12]) / 2.0
        if np.all(np.abs(hip_center) < 1e-6):
            hip_center = np.mean(kpts, axis=0)
        shifted = kpts - hip_center
        shoulder_center = (kpts[5] + kpts[6]) / 2.0
        torso_size = np.linalg.norm(shoulder_center - hip_center)
        scale = torso_size if torso_size > 1e-4 else 1.0
        return shifted / scale

    # ── Build sequence ───────────────────────────────────────────────────────
    def _build_seq(self, norm_kpts: np.ndarray, num_frames: int = 30) -> np.ndarray:
        """
        (17,2) → (1, num_frames, feature_dim)
        V1: feature_dim=34 (position only)
        V2: feature_dim=68 (position + velocity)
        """
        # pos: (T, 17, 2)
        pos_seq = np.repeat(norm_kpts[np.newaxis, :, :], num_frames, axis=0)
        pos_flat = pos_seq.reshape(num_frames, 34)   # (T, 34)

        if self.use_velocity:
            vel_seq = np.zeros_like(pos_seq)
            vel_seq[1:] = pos_seq[1:] - pos_seq[:-1]
            vel_flat = vel_seq.reshape(num_frames, 34)
            seq = np.concatenate([pos_flat, vel_flat], axis=1)  # (T, 68)
        else:
            seq = pos_flat  # (T, 34)

        return seq[np.newaxis, :, :].astype(np.float32)  # (1, T, F)

    # ── Public API ───────────────────────────────────────────────────────────
    def predict_single_frame(self, keypoints_xy: np.ndarray) -> dict:
        """
        Dự đoán từ 1 frame keypoints (17, 2).
        """
        if not self.is_ready:
            return {"label": "Unknown", "risk_score": 0.0, "probabilities": {}}

        norm_kpts = self._normalize_kpts(keypoints_xy)
        seq = self._build_seq(norm_kpts)   # (1, 30, F)
        return self._infer(seq)

    def predict_sequence(self, keypoints_seq: np.ndarray) -> dict:
        """
        Dự đoán từ chuỗi keypoints.
        Args:
            keypoints_seq: (30, 17, 2) hoặc (30, 34) hoặc (30, 68)
        """
        if not self.is_ready:
            return {"label": "Unknown", "risk_score": 0.0, "probabilities": {}}

        seq = keypoints_seq
        if seq.ndim == 3:          # (T, 17, 2) → (T, 34)
            seq = seq.reshape(seq.shape[0], -1)
        if seq.ndim == 2:          # (T, F)
            seq = seq[np.newaxis, ...]   # (1, T, F)

        return self._infer(seq.astype(np.float32))

    def _infer(self, x: np.ndarray) -> dict:
        """Internal inference"""
        tensor = torch.tensor(x).to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
            probs  = torch.softmax(logits, dim=1)

        probs_np = probs[0].cpu().numpy()
        pred_idx = int(probs_np.argmax())

        p_outofwater = float(probs_np[0])
        p_drowning   = float(probs_np[1])
        p_swimming   = float(probs_np[2]) if len(probs_np) > 2 else 0.0

        if pred_idx == 1:
            pred_lbl   = "Drowning"
            risk_score = p_drowning
            status     = "NGUY HIỂM" if risk_score > 0.5 else "CẢNH BÁO"
        elif pred_idx == 2:
            pred_lbl   = "Swimming"
            risk_score = min(p_drowning, 0.20)
            status     = "AN TOÀN"
        else:
            pred_lbl   = "Out of Water"
            risk_score = min(p_drowning, 0.15)
            status     = "AN TOÀN"

        return {
            "label":         pred_lbl,
            "label_idx":     pred_idx,
            "risk_score":    float(risk_score),
            "probabilities": {
                name: float(p)
                for name, p in zip(self.class_names, probs_np)
            },
            "status": status
        }


# ── Singleton: dùng v1 (tốt nhất hiện tại) ───────────────────────────────────
# V3 (augmentation+mixup) = 46% — tệ hơn v1 do domain shift
# V2 (velocity features)  = 51% — tệ hơn v1 do velocity=0 trên static images
# V1 (gốc)                = 57% — tốt nhất với dữ liệu static image hiện tại
_BASE       = r"c:\Nam 4 ki 1\Phuong phap luan nghien cuu khoa hoc\WebDemo\backend\models"
_MODEL_PATH = os.path.join(_BASE, "cnn_lstm_best.pth")   # V1 - best model
classifier  = DrowningClassifier(_MODEL_PATH)


if __name__ == "__main__":
    print("Testing DrowningClassifier...")
    kpts = np.random.randn(17, 2).astype(np.float32)
    result = classifier.predict_single_frame(kpts)
    print("Result:", result)
