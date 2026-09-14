"""
CVKI Module 1.8 Post-Training Analysis Script
Reads existing results.csv and evaluation outputs from yolov8n_baseline_300,
generates clean, publication-ready analysis plots, and verifies all metrics.
"""

import os
import csv
import shutil
import numpy as np
import matplotlib.pyplot as plt

# Set publication style
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['xtick.labelsize'] = 10
plt.rcParams['ytick.labelsize'] = 10
plt.rcParams['legend.fontsize'] = 10
plt.rcParams['figure.titlesize'] = 14

RUN_DIR = r"c:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\training\runs\yolov8n_baseline_300"
TEST_EVAL_DIR = os.path.join(RUN_DIR, "test_eval")
ANALYSIS_DIR = os.path.join(RUN_DIR, "analysis")
os.makedirs(ANALYSIS_DIR, exist_ok=True)

RESULTS_CSV = os.path.join(RUN_DIR, "results.csv")

def load_results():
    with open(RESULTS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            rows.append({k.strip(): float(v.strip()) for k, v in r.items() if v.strip()})
    return rows

def main():
    rows = load_results()
    epochs = [int(r["epoch"]) for r in rows]
    
    # Losses
    train_box = [r["train/box_loss"] for r in rows]
    val_box = [r["val/box_loss"] for r in rows]
    train_cls = [r["train/cls_loss"] for r in rows]
    val_cls = [r["val/cls_loss"] for r in rows]
    train_dfl = [r["train/dfl_loss"] for r in rows]
    val_dfl = [r["val/dfl_loss"] for r in rows]
    
    # Metrics
    precision = [r["metrics/precision(B)"] for r in rows]
    recall = [r["metrics/recall(B)"] for r in rows]
    map50 = [r["metrics/mAP50(B)"] for r in rows]
    map50_95 = [r["metrics/mAP50-95(B)"] for r in rows]
    lr = [r["lr/pg0"] for r in rows]
    
    # Verify Best Epoch
    best_map50_idx = np.argmax(map50)
    best_map50_95_idx = np.argmax(map50_95)
    
    # Ultralytics fitness = 0.1 * mAP50 + 0.9 * mAP50-95
    fitness = [0.1 * m50 + 0.9 * m95 for m50, m95 in zip(map50, map50_95)]
    best_fitness_idx = np.argmax(fitness)
    
    print(f"Total Epochs in results.csv: {len(epochs)}")
    print(f"Best by mAP50: Epoch {epochs[best_map50_idx]} (mAP50: {map50[best_map50_idx]:.4f}, mAP50-95: {map50_95[best_map50_idx]:.4f})")
    print(f"Best by mAP50-95: Epoch {epochs[best_map50_95_idx]} (mAP50: {map50[best_map50_95_idx]:.4f}, mAP50-95: {map50_95[best_map50_95_idx]:.4f})")
    print(f"Best by Fitness (0.1*mAP50 + 0.9*mAP50-95): Epoch {epochs[best_fitness_idx]} (Fitness: {fitness[best_fitness_idx]:.4f}, mAP50: {map50[best_fitness_idx]:.4f}, mAP50-95: {map50_95[best_fitness_idx]:.4f})")
    print(f"Epoch 85: mAP50={map50[84]:.4f}, mAP50-95={map50_95[84]:.4f}, Fitness={fitness[84]:.4f}")
    
    # -------------------------------------------------------------
    # Plot A: Box Loss
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(epochs, train_box, label="Train Box Loss", color="#1f77b4", linewidth=2)
    ax.plot(epochs, val_box, label="Validation Box Loss", color="#ff7f0e", linewidth=2)
    ax.axvline(x=epochs[best_fitness_idx], color="#2ca02c", linestyle="--", alpha=0.7, label=f"Best Checkpoint (Epoch {epochs[best_fitness_idx]})")
    ax.set_title("Training vs Validation Box Loss vs Epoch", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Bounding Box Loss")
    ax.legend(frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(ANALYSIS_DIR, "loss_box.png"))
    plt.close()
    
    # -------------------------------------------------------------
    # Plot B: Classification Loss
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(epochs, train_cls, label="Train Classification Loss", color="#1f77b4", linewidth=2)
    ax.plot(epochs, val_cls, label="Validation Classification Loss", color="#d62728", linewidth=2)
    ax.axvline(x=epochs[best_fitness_idx], color="#2ca02c", linestyle="--", alpha=0.7, label=f"Best Checkpoint (Epoch {epochs[best_fitness_idx]})")
    ax.set_title("Training vs Validation Classification Loss vs Epoch", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Classification Loss")
    ax.legend(frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(ANALYSIS_DIR, "loss_classification.png"))
    plt.close()

    # -------------------------------------------------------------
    # Plot C: DFL Loss
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(epochs, train_dfl, label="Train DFL Loss", color="#1f77b4", linewidth=2)
    ax.plot(epochs, val_dfl, label="Validation DFL Loss", color="#9467bd", linewidth=2)
    ax.axvline(x=epochs[best_fitness_idx], color="#2ca02c", linestyle="--", alpha=0.7, label=f"Best Checkpoint (Epoch {epochs[best_fitness_idx]})")
    ax.set_title("Training vs Validation Distribution Focal Loss (DFL) vs Epoch", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("DFL Loss")
    ax.legend(frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(ANALYSIS_DIR, "loss_dfl.png"))
    plt.close()

    # -------------------------------------------------------------
    # Plot D: Precision vs Epoch
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(epochs, precision, label="Validation Precision", color="#2ca02c", linewidth=2)
    ax.axvline(x=epochs[best_fitness_idx], color="#d62728", linestyle="--", alpha=0.7, label=f"Best Checkpoint (Epoch {epochs[best_fitness_idx]})")
    ax.set_title("Validation Precision vs Epoch", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Precision (B)")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(ANALYSIS_DIR, "precision_curve.png"))
    plt.close()

    # -------------------------------------------------------------
    # Plot E: Recall vs Epoch
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(epochs, recall, label="Validation Recall", color="#ff7f0e", linewidth=2)
    ax.axvline(x=epochs[best_fitness_idx], color="#d62728", linestyle="--", alpha=0.7, label=f"Best Checkpoint (Epoch {epochs[best_fitness_idx]})")
    ax.set_title("Validation Recall vs Epoch", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Recall (B)")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(ANALYSIS_DIR, "recall_curve.png"))
    plt.close()

    # -------------------------------------------------------------
    # Plot F: mAP@0.5 vs Epoch
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(epochs, map50, label="Validation mAP@0.5", color="#1f77b4", linewidth=2)
    ax.axvline(x=epochs[best_fitness_idx], color="#2ca02c", linestyle="--", alpha=0.7, label=f"Best Checkpoint (Epoch {epochs[best_fitness_idx]})")
    ax.scatter([epochs[best_map50_idx]], [map50[best_map50_idx]], color="#d62728", s=60, zorder=5, label=f"Max mAP@0.5 ({map50[best_map50_idx]:.4f} @ Ep {epochs[best_map50_idx]})")
    ax.set_title("Validation mAP@0.5 vs Epoch", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("mAP@0.5")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(ANALYSIS_DIR, "map50_curve.png"))
    plt.close()

    # -------------------------------------------------------------
    # Plot G: mAP@0.5:0.95 vs Epoch
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(epochs, map50_95, label="Validation mAP@0.5:0.95", color="#9467bd", linewidth=2)
    ax.axvline(x=epochs[best_fitness_idx], color="#2ca02c", linestyle="--", alpha=0.7, label=f"Best Checkpoint (Epoch {epochs[best_fitness_idx]})")
    ax.scatter([epochs[best_map50_95_idx]], [map50_95[best_map50_95_idx]], color="#d62728", s=60, zorder=5, label=f"Max mAP@0.5:0.95 ({map50_95[best_map50_95_idx]:.4f} @ Ep {epochs[best_map50_95_idx]})")
    ax.set_title("Validation mAP@0.5:0.95 vs Epoch", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("mAP@0.5:0.95")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(ANALYSIS_DIR, "map50_95_curve.png"))
    plt.close()

    # -------------------------------------------------------------
    # Plot H: Learning Rate vs Epoch
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(epochs, lr, label="Learning Rate (lr/pg0)", color="#8c564b", linewidth=2)
    ax.set_title("Learning Rate Schedule vs Epoch", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Learning Rate")
    ax.legend(frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(ANALYSIS_DIR, "learning_rate_curve.png"))
    plt.close()

    # -------------------------------------------------------------
    # Copy evaluation figures to analysis dir with standard names
    # -------------------------------------------------------------
    # Test set evaluation figures
    src_cm = os.path.join(TEST_EVAL_DIR, "confusion_matrix.png")
    src_cmn = os.path.join(TEST_EVAL_DIR, "confusion_matrix_normalized.png")
    src_pr = os.path.join(TEST_EVAL_DIR, "BoxPR_curve.png")
    src_f1 = os.path.join(TEST_EVAL_DIR, "BoxF1_curve.png")
    
    if os.path.exists(src_cm):
        shutil.copy2(src_cm, os.path.join(ANALYSIS_DIR, "confusion_matrix.png"))
    if os.path.exists(src_cmn):
        shutil.copy2(src_cmn, os.path.join(ANALYSIS_DIR, "confusion_matrix_normalized.png"))
    if os.path.exists(src_pr):
        shutil.copy2(src_pr, os.path.join(ANALYSIS_DIR, "pr_curve.png"))
    if os.path.exists(src_f1):
        shutil.copy2(src_f1, os.path.join(ANALYSIS_DIR, "f1_confidence_curve.png"))

    print("All plots generated and saved in:", ANALYSIS_DIR)
    print("Files in analysis dir:", os.listdir(ANALYSIS_DIR))

if __name__ == "__main__":
    main()
