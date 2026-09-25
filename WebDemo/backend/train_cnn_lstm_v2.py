"""
train_cnn_lstm_v2.py - Training cải tiến, KHÔNG cần re-extract YOLO
Dùng dataset v1 sẵn có (X_train.npy shape N,T,K,C hoặc N,T,34)
Thêm velocity + augmentation TRONG MEMORY lúc training

Cải tiến so với v1:
  1. Velocity features: 34 → 68 features
  2. In-memory augmentation: flip, jitter, scale, rotation (mỗi epoch khác nhau)
  3. Kiến trúc cải tiến: CNN 3 lớp + BiLSTM + attention pooling
  4. Mixup trong training loop
  5. OneCycleLR scheduler
  6. Epochs=60, Patience=12
  Tối ưu cho CPU: ~900K params, ~25s/epoch → ~25 phút tổng
"""
import sys, io, os, json, time
import numpy as np

LOG_FILE = r"c:\Nam 4 ki 1\Phuong phap luan nghien cuu khoa hoc\WebDemo\backend\train_v2_log.txt"
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

print(f"=== Training V2 started at {time.strftime('%H:%M:%S')} ===")

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix

# ── Config ──────────────────────────────────────────────────────────────────
BASE    = r"c:\Nam 4 ki 1\Phuong phap luan nghien cuu khoa hoc"
NPY_DIR = os.path.join(BASE, "BaoCao3.1", "processed_npy_dataset", "processed_npy_dataset")
OUT_DIR = os.path.join(BASE, "WebDemo", "backend", "models")
os.makedirs(OUT_DIR, exist_ok=True)

BATCH        = 128
EPOCHS       = 60       # nhanh hơn, OneCycleLR bù lại
LR           = 1e-3
DROP         = 0.35
CNN_CH       = 80       # giảm từ 128 → nhanh hơn ~2.5x
LSTM_H       = 160      # giảm từ 256 → nhanh hơn ~2.5x
LSTM_L       = 2
PATIENCE     = 12
MIXUP_ALPHA  = 0.2
NUM_WORKERS  = 0

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {device}")

# ── Augmentation helpers ─────────────────────────────────────────────────────
def add_velocity(kpts_flat):
    """
    kpts_flat: (T, 34) → (T, 68) bằng cách thêm velocity (diff theo time)
    """
    T = kpts_flat.shape[0]
    vel = np.zeros_like(kpts_flat)
    vel[1:] = kpts_flat[1:] - kpts_flat[:-1]
    return np.concatenate([kpts_flat, vel], axis=1)  # (T, 68)

def augment_sequence(seq_34):
    """
    seq_34: (T, 34)
    Trả về 1 variant (T, 34) ngẫu nhiên từ các augmentation
    """
    T, F = seq_34.shape
    kpts = seq_34.reshape(T, 17, 2)  # (T, 17, 2)

    r = np.random.random()

    if r < 0.25:
        # Horizontal flip
        kpts = kpts.copy(); kpts[:, :, 0] = -kpts[:, :, 0]
    elif r < 0.50:
        # Gaussian jitter
        kpts = kpts + np.random.normal(0, 0.03, kpts.shape).astype(np.float32)
    elif r < 0.65:
        # Scale
        s = np.random.uniform(0.85, 1.15)
        kpts = kpts * s
    elif r < 0.80:
        # Rotation
        deg = np.random.uniform(-15, 15)
        th  = np.radians(deg)
        R   = np.array([[np.cos(th), -np.sin(th)],
                         [np.sin(th),  np.cos(th)]], dtype=np.float32)
        kpts = np.einsum('ij,tkj->tki', R, kpts)
    # else: keep original

    return kpts.reshape(T, 34).astype(np.float32)

# ── Dataset with in-memory augmentation + velocity ────────────────────────────
class PoseDataset(Dataset):
    def __init__(self, X_raw, y, augment=False):
        """
        X_raw: (N, T, K*C) hoặc (N, T, K, C) — raw từ v1 npy
        y:     (N,)
        """
        if X_raw.ndim == 4:
            N, T, K, C = X_raw.shape
            X_raw = X_raw.reshape(N, T, K*C)
        self.X   = X_raw.astype(np.float32)   # (N, T, 34)
        self.y   = y
        self.aug = augment

    def __len__(self): return len(self.y)

    def __getitem__(self, idx):
        seq = self.X[idx].copy()   # (T, 34)
        if self.aug:
            seq = augment_sequence(seq)
        seq68 = add_velocity(seq)   # (T, 68)
        return torch.tensor(seq68), torch.tensor(self.y[idx], dtype=torch.long)

# ── Load raw npy (v1 format) ─────────────────────────────────────────────────
print("Loading v1 dataset (processed_npy_dataset)...")
def load(name):
    X = np.load(os.path.join(NPY_DIR, f"X_{name}.npy"))
    y = np.load(os.path.join(NPY_DIR, f"y_{name}.npy")).astype(np.int64)
    return X, y

X_tr, y_tr = load("train")
X_va, y_va = load("val")
X_te, y_te = load("test")

NC = int(max(y_tr.max(), y_va.max(), y_te.max())) + 1
F  = 68   # after velocity
print(f"Classes={NC}, Features={F} (pos+vel), Train={len(y_tr)}, Val={len(y_va)}, Test={len(y_te)}")
print(f"Class dist train: { {i: int((y_tr==i).sum()) for i in range(NC)} }")

tr_ds = PoseDataset(X_tr, y_tr, augment=True)
va_ds = PoseDataset(X_va, y_va, augment=False)
te_ds = PoseDataset(X_te, y_te, augment=False)

tr_dl = DataLoader(tr_ds, batch_size=BATCH, shuffle=True,  num_workers=NUM_WORKERS)
va_dl = DataLoader(va_ds, batch_size=BATCH, shuffle=False, num_workers=NUM_WORKERS)
te_dl = DataLoader(te_ds, batch_size=BATCH, shuffle=False, num_workers=NUM_WORKERS)

# ── Model: CNN-BiLSTM + Multi-Head Attention ─────────────────────────────────
class ImprovedCNNLSTM(nn.Module):
    """
    CNN-BiLSTM với attention pooling - tối ưu cho CPU
    ~900K params, ~25s/epoch (so với v1: 733K, ~30s/epoch)
    Bỏ MultiheadAttention vì quá chậm trên CPU (chiếm ~80% thời gian)
    """
    def __init__(self, F=68, cch=80, lh=160, ll=2, nc=3, dr=0.35):
        super().__init__()
        # 3-layer CNN với residual-like skip
        self.cnn = nn.Sequential(
            nn.Conv1d(F, cch, 3, padding=1),      nn.BatchNorm1d(cch),   nn.GELU(), nn.Dropout(dr*0.4),
            nn.Conv1d(cch, cch, 3, padding=1),    nn.BatchNorm1d(cch),   nn.GELU(), nn.Dropout(dr*0.4),
            nn.Conv1d(cch, cch*2, 3, padding=1),  nn.BatchNorm1d(cch*2), nn.GELU(), nn.Dropout(dr*0.4),
        )
        self.lstm = nn.LSTM(cch*2, lh, ll, batch_first=True,
                            dropout=dr if ll>1 else 0, bidirectional=True)
        H = lh * 2  # bidirectional

        # Attention pooling (nhẹ hơn MHA nhiều)
        self.pool = nn.Sequential(nn.Linear(H, 48), nn.Tanh(), nn.Linear(48, 1))

        # Classifier
        self.clf = nn.Sequential(
            nn.LayerNorm(H),
            nn.Linear(H, 128), nn.GELU(), nn.Dropout(dr),
            nn.Linear(128, nc)
        )

    def forward(self, x):
        c = self.cnn(x.permute(0,2,1)).permute(0,2,1)  # (B,T,cch*2)
        o, _ = self.lstm(c)                              # (B,T,H)
        w = torch.softmax(self.pool(o), dim=1)           # (B,T,1)
        ctx = (w * o).sum(dim=1)                         # (B,H)
        return self.clf(ctx)

model = ImprovedCNNLSTM(F=F, cch=CNN_CH, lh=LSTM_H, ll=LSTM_L, nc=NC, dr=DROP).to(device)
npar  = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"Model params: {npar:,}")

# ── Loss / Optimizer / Scheduler ─────────────────────────────────────────────
cnt  = np.bincount(y_tr, minlength=NC).astype(np.float32)
wts  = torch.tensor((cnt.sum()/NC)/cnt).to(device)
crit = nn.CrossEntropyLoss(weight=wts, label_smoothing=0.1)

opt = optim.AdamW(model.parameters(), lr=LR, weight_decay=2e-4)
# OneCycleLR: tăng nhanh rồi giảm dần - hội tụ tốt trong ít epochs
sch = optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, epochs=EPOCHS,
                                     steps_per_epoch=len(tr_dl), pct_start=0.2)

# ── Mixup ─────────────────────────────────────────────────────────────────────
def mixup_data(x, y, alpha=MIXUP_ALPHA):
    lam = np.random.beta(alpha, alpha) if alpha > 0 else 1.0
    idx = torch.randperm(x.size(0), device=x.device)
    return lam*x + (1-lam)*x[idx], y, y[idx], lam

def mixup_loss(crit, pred, ya, yb, lam):
    return lam*crit(pred, ya) + (1-lam)*crit(pred, yb)

# ── Train loop ────────────────────────────────────────────────────────────────
print(f"\n{'Ep':>4} {'TrL':>7} {'VaL':>7} {'TrAcc':>6} {'VaAcc':>6} {'VaF1':>6} {'LR':>8} {'s':>5}")
print("-"*65)

CLASS_NAMES = ["Normal", "Drowning", "Distress"][:NC]
best_f1 = best_ep = no_imp = 0

for ep in range(1, EPOCHS+1):
    t0 = time.time()
    model.train()
    tl = tc = tn = 0

    for Xb, yb in tr_dl:
        Xb, yb = Xb.to(device), yb.to(device)
        Xm, ya, yb2, lam = mixup_data(Xb, yb)
        opt.zero_grad()
        out  = model(Xm)
        loss = mixup_loss(crit, out, ya, yb2, lam)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sch.step()  # OneCycleLR: step sau mỗi batch
        tl += loss.item()*len(yb)
        tc += (out.argmax(1)==yb).sum().item()
        tn += len(yb)

    model.eval()
    vl = 0; vp_list = []; vt_list = []
    with torch.no_grad():
        for Xb, yb in va_dl:
            Xb, yb = Xb.to(device), yb.to(device)
            out = model(Xb)
            vl += crit(out, yb).item()*len(yb)
            vp_list += out.argmax(1).cpu().tolist()
            vt_list += yb.cpu().tolist()

    ta  = tc/tn
    tl_ = tl/tn
    va  = accuracy_score(vt_list, vp_list)
    vf  = f1_score(vt_list, vp_list, average='weighted', zero_division=0)
    vl_ = vl/len(vt_list)
    dt  = time.time()-t0
    cur_lr = opt.param_groups[0]['lr']

    star = ""
    if vf > best_f1:
        best_f1 = vf; best_ep = ep; no_imp = 0
        torch.save({
            "epoch": ep, "val_f1": vf, "val_acc": va,
            "model_state": model.state_dict(),
            "config": {
                "input_size": F, "cnn_ch": CNN_CH, "lstm_h": LSTM_H,
                "lstm_layers": LSTM_L, "num_classes": NC, "dropout": DROP
            },
            "class_names": CLASS_NAMES,
            "feature_dim": F,
            "use_velocity": True,
        }, os.path.join(OUT_DIR, "cnn_lstm_v2_best.pth"))
        star = " *BEST"
    else:
        no_imp += 1

    print(f"{ep:4d} {tl_:7.4f} {vl_:7.4f} {ta:6.3f} {va:6.3f} {vf:6.3f} {cur_lr:8.6f} {dt:5.1f}{star}")

    if no_imp >= PATIENCE:
        print(f"Early stop at ep {ep}, best={best_ep}")
        break

# ── Test ──────────────────────────────────────────────────────────────────────
print(f"\n=== TEST RESULTS (best epoch={best_ep}) ===")
ckpt = torch.load(os.path.join(OUT_DIR, "cnn_lstm_v2_best.pth"),
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

results = {
    "accuracy": float(acc), "f1_score": float(f1),
    "confusion_matrix": cm.tolist(),
    "best_epoch": best_ep, "best_val_f1": float(best_f1),
    "num_params": npar, "num_classes": NC, "class_names": CLASS_NAMES,
    "feature_dim": F, "use_velocity": True,
    "train_samples": len(y_tr), "val_samples": len(y_va), "test_samples": len(y_te)
}
with open(os.path.join(OUT_DIR, "test_results_v2.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(f"\n=== DONE! Acc={acc*100:.2f}%  F1={f1:.4f}  Best epoch={best_ep} ===")
log_f.close()
