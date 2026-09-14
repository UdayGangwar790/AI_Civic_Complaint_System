# CVKI — Computer Vision Model Training (Module 1.7 / 1.8)

This directory houses the model training infrastructure, hyperparameter configurations, execution scripts, and output runs for the Civic Vision & Knowledge Intelligence (CVKI) project.

---

## 1. Environment Architecture

- **Operating System**: Windows 11 64-bit
- **CPU**: Intel(R) Core(TM) i5-1235U (10 physical cores, 12 threads)
- **RAM**: 16 GB Physical Memory
- **Target Device**: `cpu` (no discrete NVIDIA CUDA GPU present)
- **Python**: Python 3.14.2 (64-bit)
- **Package Requirements** (to be installed in M1.8):
  - `torch`, `torchvision`
  - `ultralytics`

---

## 2. Dataset Overview

The dataset used for training is the certified, verified 3-class CVKI dataset at `ai/computer_vision/dataset/`:
- **Total Images**: 300
- **Total Labels**: 300 (100% paired, 0 orphans)
- **Train Set**: 210 images (70 Manhole, 70 Road Sign, 70 Waterlogging)
- **Validation Set**: 60 images (20 Manhole, 20 Road Sign, 20 Waterlogging)
- **Test Set**: 30 images (10 Manhole, 10 Road Sign, 10 Waterlogging)
- **Leakage Prevention**: All 38 waterlogging base scenes and 8 road-sign augmented scenes are partitioned atomically with zero cross-split leakage.

---

## 3. Class Ontology

| Class ID | Class Name | Description | Positive / Negative Breakdown |
|---|---|---|---|
| **0** | `open_damaged_manhole` | Open, missing, broken, or dislodged sewer/drain manholes | 100 positive images, 188 bounding boxes |
| **1** | `damaged_missing_road_sign` | Bent, faded, vandalized, or missing traffic/road signs | 52 positive images (52 boxes), 48 negative healthy signs |
| **2** | `road_waterlogging` | Stagnant, hazardous standing water pooling on roads, underpasses, and intersections | 98 positive images (439 boxes), 2 negative sheen images |

---

## 4. Planned Model Architecture

- **Baseline Architecture**: `yolov8n.pt` (YOLOv8 Nano pretrained on COCO)
- **Rationale**:
  1. Small footprint (3.2M parameters) matches the initial 300-image dataset without immediate severe overfitting.
  2. Highly efficient execution speed on 12th-Gen Intel Core CPU.
  3. Establishes a clean, reliable baseline to compare against subsequent models (YOLOv8s, YOLOv9, YOLOv11).

---

## 5. Baseline Hyperparameter Configuration

Configuration file located at: `configs/yolov8n_baseline.yaml`

```yaml
model: yolov8n.pt
data: C:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/dataset/data.yaml
epochs: 100
imgsz: 640
batch: 16
patience: 20
seed: 42
deterministic: true
device: cpu
workers: 4
project: C:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/training/runs
name: cvki_yolov8n_baseline
save: true
plots: true
val: true
```

---

## 6. How Training Will Be Started (Milestone 1.8)

Training is strictly disabled during M1.7. When approved in M1.8, training can be initiated via:

```bash
# Navigate to training scripts
cd C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\training\scripts

# Run with default baseline configuration
python train_yolov8.py

# Or run with explicit configuration file
python train_yolov8.py --config ../configs/yolov8n_baseline.yaml

# Or override parameters via CLI
python train_yolov8.py --epochs 50 --batch 16 --device cpu
```

---

## 7. Storage of Outputs & Checkpoints

All training artifacts, logs, and weights will be stored exclusively in:
`ai/computer_vision/training/runs/cvki_yolov8n_baseline/`

Output files will include:
- `weights/best.pt`: Checkpoint achieving the highest validation mAP50-95
- `weights/last.pt`: Checkpoint from the final training epoch
- `results.csv`: Per-epoch metrics (train loss, val loss, precision, recall, mAP)
- `confusion_matrix.png`: Normalized and unnormalized prediction confusion matrices
- `F1_curve.png`, `PR_curve.png`, `P_curve.png`, `R_curve.png`: Performance curves
- `val_batch0_labels.jpg` & `val_batch0_pred.jpg`: Visual validation sample comparisons

> [!IMPORTANT]
> The final dataset directory (`ai/computer_vision/dataset/`) is read-only. No training outputs will ever be written to `dataset/`.

---

## 8. Evaluation Metrics to be Collected

During and after training, the following metrics will be evaluated on the 60 validation images:
1. **Precision (P)**: Proportion of detected defect bounding boxes that are true positives.
2. **Recall (R)**: Proportion of actual ground-truth defects detected by the model.
3. **mAP@0.5**: Mean Average Precision at IoU threshold 0.50 across all 3 classes.
4. **mAP@0.5:0.95**: Primary benchmark metric across IoU thresholds from 0.50 to 0.95.
5. **Per-Class Breakdown**:
   - `open_damaged_manhole`: P, R, AP50, AP50-95
   - `damaged_missing_road_sign`: P, R, AP50, AP50-95
   - `road_waterlogging`: P, R, AP50, AP50-95
6. **Loss Convergence**:
   - `train/box_loss`, `train/cls_loss`, `train/dfl_loss`
   - `val/box_loss`, `val/cls_loss`, `val/dfl_loss`
