import sys, io, os, json, time, numpy as np

# Redirect tất cả output ra file log để theo dõi
LOG_FILE = r"c:\Nam 4 ki 1\Phuong phap luan nghien cuu khoa hoc\WebDemo\backend\train_log.txt"
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

print(f"=== Training started at {time.strftime('%H:%M:%S')} ===")

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix

# ── Config ──────────────────────────────────────────────────────
BASE    = r"c:\Nam 4 ki 1\Phuong phap luan nghien cuu khoa hoc"
NPY_DIR = os.path.join(BASE, "BaoCao3.1", "processed_npy_dataset", "processed_npy_dataset")
OUT_DIR = os.path.join(BASE, "WebDemo", "backend", "models")
os.makedirs(OUT_DIR, exist_ok=True)

BATCH = 64; EPOCHS = 50; LR = 1e-3; DROP = 0.4
CNN_CH = 64; LSTM_H = 128; LSTM_L = 2; PATIENCE = 10

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {device}")

# ── Load ─────────────────────────────────────────────────────────
print("Loading data...")
def load(name):
    X = np.load(os.path.join(NPY_DIR, f"X_{name}.npy")).astype(np.float32)
    y = np.load(os.path.join(NPY_DIR, f"y_{name}.npy")).astype(np.int64)
    N, T, K, C = X.shape
    return X.reshape(N, T, K*C), y

X_tr, y_tr = load("train")
X_va, y_va = load("val")
X_te, y_te = load("test")

NC = int(y_tr.max()) + 1
F  = X_tr.shape[2]
print(f"Classes={NC}, Features={F}, Train={len(y_tr)}, Val={len(y_va)}, Test={len(y_te)}")
print(f"Class dist train: { {i: int((y_tr==i).sum()) for i in range(NC)} }")

def mk_loader(X, y, shuf=False):
    return DataLoader(TensorDataset(torch.tensor(X), torch.tensor(y)),
                      batch_size=BATCH, shuffle=shuf, num_workers=0)

tr_dl = mk_loader(X_tr, y_tr, True)
va_dl = mk_loader(X_va, y_va)
te_dl = mk_loader(X_te, y_te)

# ── Model ─────────────────────────────────────────────────────────
class CNNLSTM(nn.Module):
    def __init__(self, F, cch, lh, ll, nc, dr):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv1d(F, cch, 3, padding=1), nn.BatchNorm1d(cch), nn.GELU(), nn.Dropout(dr*.5),
            nn.Conv1d(cch, cch*2, 3, padding=1), nn.BatchNorm1d(cch*2), nn.GELU(), nn.Dropout(dr*.5),
        )
        self.lstm = nn.LSTM(cch*2, lh, ll, batch_first=True,
                            dropout=dr if ll>1 else 0, bidirectional=True)
        H = lh*2
        self.attn = nn.Sequential(nn.Linear(H,32), nn.Tanh(), nn.Linear(32,1))
        self.clf  = nn.Sequential(nn.LayerNorm(H), nn.Linear(H,128), nn.GELU(),
                                  nn.Dropout(dr), nn.Linear(128, nc))
    def forward(self, x):
        c = self.cnn(x.permute(0,2,1)).permute(0,2,1)
        o, _ = self.lstm(c)
        w = torch.softmax(self.attn(o), 1)
        return self.clf((w*o).sum(1))

model = CNNLSTM(F, CNN_CH, LSTM_H, LSTM_L, NC, DROP).to(device)
npar  = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"Params: {npar:,}")

cnt  = np.bincount(y_tr, minlength=NC).astype(np.float32)
wts  = torch.tensor((cnt.sum()/NC)/cnt).to(device)
crit = nn.CrossEntropyLoss(weight=wts, label_smoothing=0.05)
opt  = optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
sch  = optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, epochs=EPOCHS,
                                      steps_per_epoch=len(tr_dl), pct_start=0.2)

# ── Train loop ────────────────────────────────────────────────────
print(f"\n{'Ep':>4} {'TrL':>7} {'VaL':>7} {'TrAcc':>6} {'VaAcc':>6} {'VaF1':>6} {'s':>5}")
print("-"*50)

best_f1 = best_ep = no_imp = 0
CLASS_NAMES = ["Normal","Drowning","Distress"][:NC]

for ep in range(1, EPOCHS+1):
    t0 = time.time()
    model.train()
    tl = tc = tn = 0
    for Xb, yb in tr_dl:
        Xb, yb = Xb.to(device), yb.to(device)
        opt.zero_grad()
        loss = crit(model(Xb), yb)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sch.step()
        tl += loss.item()*len(yb)
        tc += (model(Xb).argmax(1)==yb).sum().item()
        tn += len(yb)

    model.eval()
    vl = vp = vt = 0
    vp_list = []; vt_list = []
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

    star = ""
    if vf > best_f1:
        best_f1 = vf; best_ep = ep; no_imp = 0
        torch.save({
            "epoch":ep, "val_f1":vf, "val_acc":va,
            "model_state": model.state_dict(),
            "config": {"input_size":F,"cnn_ch":CNN_CH,"lstm_h":LSTM_H,
                       "lstm_layers":LSTM_L,"num_classes":NC,"dropout":DROP},
            "class_names": CLASS_NAMES
        }, os.path.join(OUT_DIR, "cnn_lstm_best.pth"))
        star = " *BEST"
    else:
        no_imp += 1

    print(f"{ep:4d} {tl_:7.4f} {vl_:7.4f} {ta:6.3f} {va:6.3f} {vf:6.3f} {dt:5.1f}{star}")

    if no_imp >= PATIENCE:
        print(f"Early stop at {ep}, best={best_ep}")
        break

# ── Test ──────────────────────────────────────────────────────────
print(f"\n=== TEST RESULTS (best epoch={best_ep}) ===")
ckpt = torch.load(os.path.join(OUT_DIR,"cnn_lstm_best.pth"), map_location=device, weights_only=False)
model.load_state_dict(ckpt["model_state"])
model.eval()

tp=[]; tt=[]
with torch.no_grad():
    for Xb,yb in te_dl:
        out = model(Xb.to(device))
        tp += out.argmax(1).cpu().tolist()
        tt += yb.tolist()

acc = accuracy_score(tt,tp)
f1  = f1_score(tt,tp,average='weighted',zero_division=0)
cm  = confusion_matrix(tt,tp)
print(f"Accuracy : {acc:.4f} ({acc*100:.2f}%)")
print(f"F1-Score : {f1:.4f}")
print(f"Confusion Matrix:\n{cm}")
print(classification_report(tt,tp,target_names=CLASS_NAMES,zero_division=0))

results = {
    "accuracy":float(acc),"f1_score":float(f1),
    "confusion_matrix":cm.tolist(),
    "best_epoch":best_ep,"best_val_f1":float(best_f1),
    "num_params":npar,"num_classes":NC,"class_names":CLASS_NAMES,
    "train_samples":len(y_tr),"val_samples":len(y_va),"test_samples":len(y_te)
}
with open(os.path.join(OUT_DIR,"test_results.json"),"w",encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(f"\n=== DONE! Acc={acc*100:.2f}%  F1={f1:.4f}  Best epoch={best_ep} ===")
log_f.close()
