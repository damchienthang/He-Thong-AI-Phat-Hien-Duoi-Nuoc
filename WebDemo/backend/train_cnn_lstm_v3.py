"""
train_cnn_lstm_v3.py - Training cải tiến đúng hướng
Phân tích lỗi v2: velocity=0 vì dữ liệu ảnh tĩnh lặp 30 frame
→ Giải pháp: vẫn dùng 34 features, cải tiến model + training tricks

Cải tiến so với v1:
  1. In-memory augmentation: flip, jitter, scale, rotation (mỗi epoch khác nhau)
  2. CNN_CH=96, LSTM_H=160 (to hơn v1: 64/128) nhưng vẫn nhanh
  3. Label smoothing = 0.05 (giống v1)
  4. Epochs=80, Patience=15, LR=1e-3
  5. OneCycleLR
  6. Mixup alpha=0.15
"""
import sys, io, os, json, time
import numpy as np

LOG_FILE = r"c:\Nam 4 ki 1\Phuong phap luan nghien cuu khoa hoc\WebDemo\backend\train_v3_log.txt"
log_f = open(LOG_FILE, "w", encoding="utf-8", buffering=1)

class Tee:
    def __init__(self, *files): self.files = files
    def write(self, s):
        for f in self.files:
            try: f.write(s); f.flush()
            except: pass
    def flush(self):
        for f in self.files:
            try: f.flush()
            except: pass

sys.stdout = Tee(sys.__stdout__, log_f)
sys.stderr = sys.stdout

print(f"=== Training V3 started at {time.strftime('%H:%M:%S')} ===")

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix

# ── Config ────────────────────────────────────────────────────────────────────
BASE    = r"c:\Nam 4 ki 1\Phuong phap luan nghien cuu khoa hoc"
NPY_DIR = os.path.join(BASE, "BaoCao3.1", "processed_npy_dataset", "processed_npy_dataset")
OUT_DIR = os.path.join(BASE, "WebDemo", "backend", "models")
os.makedirs(OUT_DIR, exist_ok=True)

BATCH       = 128
EPOCHS      = 50     # ~30 phut tren CPU (~35s/epoch)
LR          = 1e-3
DROP        = 0.4
CNN_CH      = 72     # v1 dùng 64 → to hơn chút xíu
LSTM_H      = 128    # giống v1 để giữ tốc độ
LSTM_L      = 2
PATIENCE    = 12
MIXUP_ALPHA = 0.15
NUM_WORKERS = 0
FEAT_DIM    = 34     # KHÔNG dùng velocity (v2 đã chứng minh vô ích)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {device}")

# ── In-memory augmentation ────────────────────────────────────────────────────
def augment_seq(seq_34):
    """
    seq_34: (T, 34) → augmented (T, 34)
    Augment trên keypoints, áp dụng đồng nhất cho tất cả T frames
    """
    T = seq_34.shape[0]
    kpts = seq_34.reshape(T, 17, 2)
    r = np.random.random()

    if r < 0.20:
        # Horizontal flip
        kpts = kpts.copy(); kpts[:, :, 0] = -kpts[:, :, 0]
    elif r < 0.40:
        # Gaussian jitter
        kpts = kpts + np.random.normal(0, 0.04, kpts.shape).astype(np.float32)
    elif r < 0.55:
        # Scale jitter
        s = np.random.uniform(0.80, 1.20)
        kpts = (kpts * s).astype(np.float32)
    elif r < 0.70:
        # Rotation
        deg = np.random.uniform(-20, 20)
        th  = np.radians(deg)
        R   = np.array([[np.cos(th), -np.sin(th)],
                        [np.sin(th),  np.cos(th)]], dtype=np.float32)
        kpts = np.einsum('ij,tkj->tki', R, kpts)
    elif r < 0.80:
        # Flip + jitter
        kpts = kpts.copy(); kpts[:, :, 0] = -kpts[:, :, 0]
        kpts = kpts + np.random.normal(0, 0.02, kpts.shape).astype(np.float32)
    # else: no augmentation (20% chance keep original)

    return kpts.reshape(T, 34).astype(np.float32)

# ── Dataset ────────────────────────────────────────────────────────────────────
class PoseDataset(Dataset):
    def __init__(self, X_raw, y, augment=False):
        if X_raw.ndim == 4:
            N, T, K, C = X_raw.shape
            X_raw = X_raw.reshape(N, T, K*C)
        self.X   = X_raw.astype(np.float32)  # (N, T, 34)
        self.y   = y
        self.aug = augment

    def __len__(self): return len(self.y)

    def __getitem__(self, idx):
        seq = self.X[idx].copy()
        if self.aug:
            seq = augment_seq(seq)
        return torch.tensor(seq), torch.tensor(self.y[idx], dtype=torch.long)

# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading dataset...")
def load(name):
    X = np.load(os.path.join(NPY_DIR, f"X_{name}.npy"))
    y = np.load(os.path.join(NPY_DIR, f"y_{name}.npy")).astype(np.int64)
    return X, y

X_tr, y_tr = load("train")
X_va, y_va = load("val")
X_te, y_te = load("test")

NC = int(max(y_tr.max(), y_va.max(), y_te.max())) + 1
print(f"Classes={NC}, Features={FEAT_DIM}, Train={len(y_tr)}, Val={len(y_va)}, Test={len(y_te)}")
print(f"Class dist train: { {i: int((y_tr==i).sum()) for i in range(NC)} }")

tr_ds = PoseDataset(X_tr, y_tr, augment=True)
va_ds = PoseDataset(X_va, y_va, augment=False)
te_ds = PoseDataset(X_te, y_te, augment=False)

tr_dl = DataLoader(tr_ds, batch_size=BATCH, shuffle=True,  num_workers=NUM_WORKERS)
va_dl = DataLoader(va_ds, batch_size=BATCH, shuffle=False, num_workers=NUM_WORKERS)
te_dl = DataLoader(te_ds, batch_size=BATCH, shuffle=False, num_workers=NUM_WORKERS)

# ── Model: CNN-BiLSTM v3 (34 features, slightly larger than v1) ───────────────
class CNNLSTM_v3(nn.Module):
    """
    Tối ưu so với v1:
    - 3 Conv layers thay vì 2 → học pattern phức tạp hơn
    - CNN_CH=72 thay vì 64 (nhỏ hơn chút để nhanh trên CPU)
    - LSTM_H=128 giống v1
    - Augmentation + Mixup là cải tiến chính
    """
    def __init__(self, F=34, cch=72, lh=128, ll=2, nc=3, dr=0.4):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv1d(F, cch, 3, padding=1),     nn.BatchNorm1d(cch),   nn.GELU(), nn.Dropout(dr*0.4),
            nn.Conv1d(cch, cch, 3, padding=1),   nn.BatchNorm1d(cch),   nn.GELU(), nn.Dropout(dr*0.4),
            nn.Conv1d(cch, cch*2, 3, padding=1), nn.BatchNorm1d(cch*2), nn.GELU(), nn.Dropout(dr*0.4),
        )
        self.lstm = nn.LSTM(cch*2, lh, ll, batch_first=True,
                            dropout=dr if ll > 1 else 0, bidirectional=True)
        H = lh * 2
        self.attn = nn.Sequential(nn.Linear(H, 48), nn.Tanh(), nn.Linear(48, 1))
        self.clf  = nn.Sequential(
            nn.LayerNorm(H),
            nn.Linear(H, 128), nn.GELU(), nn.Dropout(dr),
            nn.Linear(128, nc)
        )

    def forward(self, x):
        c = self.cnn(x.permute(0, 2, 1)).permute(0, 2, 1)  # (B,T,cch*2)
        o, _ = self.lstm(c)                                  # (B,T,H)
        w = torch.softmax(self.attn(o), dim=1)               # (B,T,1)
        return self.clf((w * o).sum(dim=1))

model = CNNLSTM_v3(F=FEAT_DIM, cch=CNN_CH, lh=LSTM_H, ll=LSTM_L, nc=NC, dr=DROP).to(device)
npar  = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"Model params: {npar:,}")

# ── Loss / Optimizer / Scheduler ──────────────────────────────────────────────
cnt  = np.bincount(y_tr, minlength=NC).astype(np.float32)
wts  = torch.tensor((cnt.sum() / NC) / cnt).to(device)
crit = nn.CrossEntropyLoss(weight=wts, label_smoothing=0.05)

opt = optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
sch = optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, epochs=EPOCHS,
                                     steps_per_epoch=len(tr_dl), pct_start=0.2)

# ── Mixup ─────────────────────────────────────────────────────────────────────
def mixup(x, y, alpha=MIXUP_ALPHA):
    lam = np.random.beta(alpha, alpha) if alpha > 0 else 1.0
    idx = torch.randperm(x.size(0), device=x.device)
    return lam*x + (1-lam)*x[idx], y, y[idx], lam

def mixup_loss(crit, pred, ya, yb, lam):
    return lam * crit(pred, ya) + (1 - lam) * crit(pred, yb)

# ── Train loop ─────────────────────────────────────────────────────────────────
print(f"\n{'Ep':>4} {'TrL':>7} {'VaL':>7} {'TrAcc':>6} {'VaAcc':>6} {'VaF1':>6} {'s':>5}")
print("-" * 55)

CLASS_NAMES = ["Normal", "Drowning", "Distress"][:NC]
best_f1 = best_ep = no_imp = 0

for ep in range(1, EPOCHS + 1):
    t0 = time.time()
    model.train()
    tl = tc = tn = 0

    for Xb, yb in tr_dl:
        Xb, yb = Xb.to(device), yb.to(device)
        Xm, ya, yb2, lam = mixup(Xb, yb)
        opt.zero_grad()
        out = model(Xm)
        loss = mixup_loss(crit, out, ya, yb2, lam)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sch.step()
        tl += loss.item() * len(yb)
        tc += (out.argmax(1) == yb).sum().item()
        tn += len(yb)

    model.eval()
    vl = 0; vp_list = []; vt_list = []
    with torch.no_grad():
        for Xb, yb in va_dl:
            Xb, yb = Xb.to(device), yb.to(device)
            out = model(Xb)
            vl += crit(out, yb).item() * len(yb)
            vp_list += out.argmax(1).cpu().tolist()
            vt_list += yb.cpu().tolist()

    ta  = tc / tn
    tl_ = tl / tn
    va  = accuracy_score(vt_list, vp_list)
    vf  = f1_score(vt_list, vp_list, average='weighted', zero_division=0)
    vl_ = vl / len(vt_list)
    dt  = time.time() - t0

    star = ""
    if vf > best_f1:
        best_f1 = vf; best_ep = ep; no_imp = 0
        torch.save({
            "epoch": ep, "val_f1": vf, "val_acc": va,
            "model_state": model.state_dict(),
            "config": {
                "input_size": FEAT_DIM, "cnn_ch": CNN_CH, "lstm_h": LSTM_H,
                "lstm_layers": LSTM_L, "num_classes": NC, "dropout": DROP
            },
            "class_names": CLASS_NAMES,
        }, os.path.join(OUT_DIR, "cnn_lstm_v3_best.pth"))
        star = " *BEST"
    else:
        no_imp += 1

    print(f"{ep:4d} {tl_:7.4f} {vl_:7.4f} {ta:6.3f} {va:6.3f} {vf:6.3f} {dt:5.1f}{star}")

    if no_imp >= PATIENCE:
        print(f"Early stop at ep {ep}, best={best_ep}")
        break

# ── Test ───────────────────────────────────────────────────────────────────────
print(f"\n=== TEST RESULTS (best epoch={best_ep}) ===")
ckpt = torch.load(os.path.join(OUT_DIR, "cnn_lstm_v3_best.pth"),
                  map_location=device, weights_only=False)
model.load_state_dict(ckpt["model_state"])
model.eval()

tp, tt = [], []
with torch.no_grad():
    for Xb, yb in te_dl:
        out = model(Xb.to(device))
        tp += out.argmax(1).cpu().tolist()
        tt += yb.tolist()

acc = accuracy_score(tt, tp)
f1  = f1_score(tt, tp, average='weighted', zero_division=0)
cm  = confusion_matrix(tt, tp)
print(f"Accuracy : {acc:.4f} ({acc*100:.2f}%)")
print(f"F1-Score : {f1:.4f}")
print(f"Confusion Matrix:\n{cm}")
print(classification_report(tt, tp, target_names=CLASS_NAMES, zero_division=0))

# So sánh với v1
print(f"\nSo sanh:")
print(f"  V1 (goc): Acc=56.94%  F1=0.5785")
print(f"  V3 (moi): Acc={acc*100:.2f}%  F1={f1:.4f}")
print(f"  Cai thien: {(acc-0.5694)*100:+.2f}% Acc, {(f1-0.5785):+.4f} F1")

results = {
    "accuracy": float(acc), "f1_score": float(f1),
    "confusion_matrix": cm.tolist(),
    "best_epoch": best_ep, "best_val_f1": float(best_f1),
    "num_params": npar, "num_classes": NC, "class_names": CLASS_NAMES,
    "feature_dim": FEAT_DIM,
    "train_samples": len(y_tr), "val_samples": len(y_va), "test_samples": len(y_te)
}
with open(os.path.join(OUT_DIR, "test_results_v3.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(f"\n=== DONE! Acc={acc*100:.2f}%  F1={f1:.4f}  Best epoch={best_ep} ===")
log_f.close()
