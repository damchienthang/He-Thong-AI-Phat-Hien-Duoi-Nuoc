"""
Tính toán đầy đủ các chỉ số đánh giá mô hình CNN-LSTM
Nhóm 7 – PPLNCKH 2026
"""
import os, json, sys, io
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report,
    roc_auc_score, average_precision_score,
    matthews_corrcoef, cohen_kappa_score,
    balanced_accuracy_score, top_k_accuracy_score
)
from sklearn.preprocessing import label_binarize

# ── Load model & data ──────────────────────────────────────────────────────────
BASE    = r"c:\Nam 4 ki 1\Phuong phap luan nghien cuu khoa hoc"
NPY_DIR = os.path.join(BASE, "BaoCao3.1", "processed_npy_dataset", "processed_npy_dataset")
OUT_DIR = os.path.join(BASE, "WebDemo", "backend", "models")
LOG     = os.path.join(BASE, "WebDemo", "backend", "eval_metrics.txt")

from model_inference import CNN_LSTM

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Load checkpoint
ckpt = torch.load(os.path.join(OUT_DIR, "cnn_lstm_best.pth"), map_location=device, weights_only=False)
cfg  = ckpt["config"]
CLASS_NAMES = ckpt.get("class_names", ["Normal","Drowning","Distress"])
NC = cfg["num_classes"]

model = CNN_LSTM(cfg["input_size"], cfg["cnn_ch"], cfg["lstm_h"],
                 cfg["lstm_layers"], NC, cfg["dropout"]).to(device)
model.load_state_dict(ckpt["model_state"])
model.eval()

# Load test data
X_te = np.load(os.path.join(NPY_DIR, "X_test.npy")).astype(np.float32)
y_te = np.load(os.path.join(NPY_DIR, "y_test.npy")).astype(np.int64)
N,T,K,C = X_te.shape
X_te = X_te.reshape(N, T, K*C)

from torch.utils.data import DataLoader, TensorDataset
loader = DataLoader(TensorDataset(torch.tensor(X_te), torch.tensor(y_te)),
                    batch_size=64, shuffle=False)

# Inference
all_preds, all_true, all_probs = [], [], []
with torch.no_grad():
    for Xb, yb in loader:
        out   = model(Xb.to(device))
        probs = torch.softmax(out, dim=1)
        all_preds.extend(out.argmax(1).cpu().numpy())
        all_true.extend(yb.numpy())
        all_probs.extend(probs.cpu().numpy())

y_true  = np.array(all_true)
y_pred  = np.array(all_preds)
y_probs = np.array(all_probs)   # (N, NC)

# Binarize for multi-class AUC
y_bin = label_binarize(y_true, classes=list(range(NC)))

# ── Tính các chỉ số ────────────────────────────────────────────────────────────
results = {}

# 1. Accuracy
results["accuracy"]          = float(accuracy_score(y_true, y_pred))
results["balanced_accuracy"] = float(balanced_accuracy_score(y_true, y_pred))

# 2. Precision / Recall / F1 (macro & weighted)
for avg in ["macro", "weighted"]:
    results[f"precision_{avg}"] = float(precision_score(y_true, y_pred, average=avg, zero_division=0))
    results[f"recall_{avg}"]    = float(recall_score(y_true, y_pred, average=avg, zero_division=0))
    results[f"f1_{avg}"]        = float(f1_score(y_true, y_pred, average=avg, zero_division=0))

# 3. ROC-AUC (OvR)
try:
    results["roc_auc_macro"]    = float(roc_auc_score(y_bin, y_probs, multi_class="ovr", average="macro"))
    results["roc_auc_weighted"] = float(roc_auc_score(y_bin, y_probs, multi_class="ovr", average="weighted"))
except Exception as e:
    results["roc_auc_macro"] = results["roc_auc_weighted"] = f"N/A ({e})"

# 4. Average Precision (PR-AUC)
ap_per_class = {}
for i, name in enumerate(CLASS_NAMES):
    ap = float(average_precision_score(y_bin[:, i], y_probs[:, i]))
    ap_per_class[name] = ap
results["avg_precision_per_class"] = ap_per_class
results["avg_precision_macro"]     = float(np.mean(list(ap_per_class.values())))

# 5. Matthews Correlation Coefficient
results["mcc"] = float(matthews_corrcoef(y_true, y_pred))

# 6. Cohen's Kappa
results["cohen_kappa"] = float(cohen_kappa_score(y_true, y_pred))

# 7. Confusion Matrix
cm = confusion_matrix(y_true, y_pred)
results["confusion_matrix"] = cm.tolist()

# 8. Per-class: TP, FP, FN, TN, Specificity, Sensitivity
per_class = {}
for i, name in enumerate(CLASS_NAMES):
    tp = int(cm[i, i])
    fp = int(cm[:, i].sum() - tp)
    fn = int(cm[i, :].sum() - tp)
    tn = int(cm.sum() - tp - fp - fn)
    sensitivity = tp / (tp + fn) if (tp+fn) > 0 else 0.0  # = Recall
    specificity = tn / (tn + fp) if (tn+fp) > 0 else 0.0
    ppv = tp / (tp + fp) if (tp+fp) > 0 else 0.0           # = Precision
    npv = tn / (tn + fn) if (tn+fn) > 0 else 0.0
    f1c = 2*ppv*sensitivity/(ppv+sensitivity) if (ppv+sensitivity) > 0 else 0.0
    per_class[name] = {
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "Sensitivity_Recall": round(sensitivity, 4),
        "Specificity":        round(specificity, 4),
        "Precision_PPV":      round(ppv, 4),
        "NPV":                round(npv, 4),
        "F1":                 round(f1c, 4),
        "AP_PR_AUC":          round(ap_per_class[name], 4),
    }
results["per_class"] = per_class

# 9. Top-2 Accuracy
results["top2_accuracy"] = float(top_k_accuracy_score(y_true, y_probs, k=2))

# 10. Model info
results["model_info"] = {
    "best_epoch":  ckpt["epoch"],
    "val_f1":      round(float(ckpt["val_f1"]), 4),
    "val_acc":     round(float(ckpt["val_acc"]), 4),
    "num_params":  sum(p.numel() for p in model.parameters()),
    "architecture":"CNN-1D + BiLSTM + Attention",
    "num_classes": NC,
    "class_names": CLASS_NAMES,
    "input_shape": "(N, 30, 34)",
    "device": str(device),
}

# ── In kết quả ────────────────────────────────────────────────────────────────
lines = []
lines.append("=" * 65)
lines.append("  CHỈ SỐ ĐÁNH GIÁ MÔ HÌNH CNN-LSTM – NHÓM 7")
lines.append("=" * 65)

lines.append(f"\n[Model] CNN-1D + BiLSTM + Attention  |  Params: {results['model_info']['num_params']:,}")
lines.append(f"        Best epoch: {results['model_info']['best_epoch']}  |  Val F1: {results['model_info']['val_f1']}")

lines.append("\n── Chỉ số tổng quát ─────────────────────────────────────────")
lines.append(f"  Accuracy             : {results['accuracy']:.4f}  ({results['accuracy']*100:.2f}%)")
lines.append(f"  Balanced Accuracy    : {results['balanced_accuracy']:.4f}  ({results['balanced_accuracy']*100:.2f}%)")
lines.append(f"  Top-2 Accuracy       : {results['top2_accuracy']:.4f}  ({results['top2_accuracy']*100:.2f}%)")
lines.append(f"  Matthews CC (MCC)    : {results['mcc']:.4f}")
lines.append(f"  Cohen's Kappa (κ)    : {results['cohen_kappa']:.4f}")

lines.append("\n── Precision / Recall / F1 ──────────────────────────────────")
lines.append(f"  {'Metric':<22} {'Macro':>8}  {'Weighted':>10}")
lines.append(f"  {'-'*44}")
for m in ["precision","recall","f1"]:
    lines.append(f"  {m.capitalize():<22} {results[f'{m}_macro']:>8.4f}  {results[f'{m}_weighted']:>10.4f}")

lines.append("\n── ROC-AUC (One-vs-Rest) ────────────────────────────────────")
lines.append(f"  ROC-AUC Macro        : {results['roc_auc_macro']}")
lines.append(f"  ROC-AUC Weighted     : {results['roc_auc_weighted']}")

lines.append("\n── PR-AUC (Average Precision) ───────────────────────────────")
for name, ap in ap_per_class.items():
    lines.append(f"  AP [{name:<10}]     : {ap:.4f}")
lines.append(f"  AP Macro             : {results['avg_precision_macro']:.4f}")

lines.append("\n── Chỉ số theo từng lớp ─────────────────────────────────────")
lines.append(f"  {'Class':<12} {'Sens/Recall':>11} {'Spec':>7} {'Prec/PPV':>9} {'NPV':>7} {'F1':>7} {'AP':>7}  TP  FP  FN  TN")
lines.append(f"  {'-'*85}")
for name, m in per_class.items():
    lines.append(f"  {name:<12} {m['Sensitivity_Recall']:>11.4f} {m['Specificity']:>7.4f} "
                 f"{m['Precision_PPV']:>9.4f} {m['NPV']:>7.4f} {m['F1']:>7.4f} "
                 f"{m['AP_PR_AUC']:>7.4f}  {m['TP']:>3} {m['FP']:>3} {m['FN']:>3} {m['TN']:>3}")

lines.append("\n── Ma trận nhầm lẫn (Confusion Matrix) ─────────────────────")
lines.append(f"  {'':12} " + "  ".join(f"{n:>10}" for n in CLASS_NAMES) + "  ← Predicted")
for i, name in enumerate(CLASS_NAMES):
    row = "  ".join(f"{cm[i,j]:>10}" for j in range(NC))
    lines.append(f"  {name:<12} {row}")

lines.append("\n── Classification Report ────────────────────────────────────")
lines.append(classification_report(y_true, y_pred, target_names=CLASS_NAMES, zero_division=0))
lines.append("=" * 65)

output = "\n".join(lines)

# Lưu file text
with open(LOG, "w", encoding="utf-8") as f:
    f.write(output)

# Lưu JSON
with open(os.path.join(OUT_DIR, "full_metrics.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(output)
print(f"\nDa luu:\n  {LOG}\n  {os.path.join(OUT_DIR, 'full_metrics.json')}")
