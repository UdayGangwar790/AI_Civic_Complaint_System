# CVKI M1.8 — YOLOv8n Baseline Training Report

- **Run Name**: `yolov8n_baseline_300`
- **Date**: 2026-09-12
- **Execution Device**: CPU (Intel Core i5-1235U CPU)
- **Status**: **COMPLETE / VERIFIED**

---

## 1. Executive Summary

Module 1.8 executed the baseline training run for the **Civic Vision & Knowledge Intelligence (CVKI)** project on the 300-image civic defect dataset. Training was conducted strictly on CPU using YOLOv8n pretrained weights (`yolov8n.pt`). All training outputs, checkpoints, and evaluations are isolated inside `ai/computer_vision/training/runs/yolov8n_baseline_300/`.

Following training, the best checkpoint (`best.pt`) was evaluated against the strictly held-out test split (30 images, 10 per class). The dataset was verified 100% untouched before and after execution.

---

## 2. Dataset & Ontology

- **Dataset Configuration**: `C:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/dataset/data.yaml`
- **Total Images**: 300 (Train: 210, Val: 60, Test: 30)
- **Ontology**:
  - `0`: `open_damaged_manhole`
  - `1`: `damaged_missing_road_sign`
  - `2`: `road_waterlogging`

---

## 3. Environment & Hardware

| Parameter | Value |
|---|---|
| **OS** | Windows 11 64-bit |
| **Python** | 3.13.1 |
| **PyTorch** | 2.14.0+cpu |
| **Ultralytics** | 8.4.149 |
| **Compute Device** | CPU |
| **CPU Spec** | Intel(R) Core(TM) i5-1235U (10 cores, 12 threads) |
| **CUDA Available** | False |

---

## 4. Hyperparameters & Execution Settings

| Hyperparameter | Planned / Configured | Actual Used |
|---|---|---|
| **Model** | `yolov8n.pt` | `yolov8n.pt` |
| **Input Resolution (`imgsz`)** | 640 | 640 |
| **Batch Size (`batch`)** | 16 | 16 |
| **Epochs Requested** | 100 | 100 |
| **Epochs Completed** | — | 100 |
| **Early Stopping Patience** | 20 | 20 |
| **Seed** | 42 | 42 |
| **Deterministic Mode** | True | True |
| **Workers** | 2 | 2 |
| **Training Duration** | — | 4:33:21 (16401.1s) |
| **Best Epoch** | — | Epoch 85 |

---

## 5. Training Loss & Optimization Progress

| Metric | Epoch 1 | Best Epoch (85) | Final Epoch (100) |
|---|---|---|---|
| **Train Box Loss** | 1.78726 | 0.87928 | 0.76307 |
| **Train Class Loss** | 3.57694 | 0.82162 | 0.76332 |
| **Train DFL Loss** | 1.76166 | 1.08712 | 1.00464 |
| **Val Box Loss** | 1.54484 | 1.44239 | 1.43433 |
| **Val Class Loss** | 4.07622 | 1.62801 | 1.76862 |
| **Val DFL Loss** | 1.68411 | 1.63136 | 1.63378 |

---

## 6. Validation Performance (60 Validation Images)

- **Validation Precision**: `0.6329`
- **Validation Recall**: `0.6570`
- **Validation mAP@0.5**: `0.6485`
- **Validation mAP@0.5:0.95**: `0.4620`

---

## 7. Held-Out Test Set Evaluation (30 Test Images)

Evaluation conducted on strictly held-out test split using `best.pt`:

| Metric | Overall Test Value |
|---|---|
| **Precision** | `0.7797` |
| **Recall** | `0.5660` |
| **mAP@0.5** | `0.6166` |
| **mAP@0.5:0.95** | `0.4279` |

### Per-Class Test Set Breakdown

| Class ID | Class Name | Precision | Recall | mAP@0.5 | mAP@0.5:0.95 |
|---|---|---|---|---|---|
| 0 | `open_damaged_manhole` | 0.8420 | 0.6671 | 0.7598 | 0.5113 |
| 1 | `damaged_missing_road_sign` | 0.8294 | 0.8000 | 0.7950 | 0.5987 |
| 2 | `road_waterlogging` | 0.6676 | 0.2308 | 0.2951 | 0.1737 |

---

## 8. Artifacts & Saved Models

- **Best Model Checkpoint**: [`C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\training\runs\yolov8n_baseline_300\weights\best.pt`](file:///C:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/training/runs/yolov8n_baseline_300/weights/best.pt)
- **Last Model Checkpoint**: [`C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\training\runs\yolov8n_baseline_300\weights\last.pt`](file:///C:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/training/runs/yolov8n_baseline_300/weights/last.pt)
- **Results CSV**: `results.csv`
- **Plots Generated**:
  - `results.png` (Training & validation loss curves and metrics)
  - `confusion_matrix.png` & `confusion_matrix_normalized.png`
  - `PR_curve.png` & `F1_curve.png`
  - `P_curve.png` & `R_curve.png`
  - Test evaluation outputs in `test_eval/`

---

## 9. Limitations & Next Steps

1. **CPU Training**: Completed in 4:33:21. Sufficient for small baseline (300 images), but larger backbones or higher resolutions will benefit from GPU acceleration.
2. **Class Imbalance / Negative Examples**: Road signs contain 48% negative images in training, which suppresses false positives on healthy signs. Waterlogging and manholes have high density per image.
3. **Recommendations for Next Phase (M1.9+)**:
   - Evaluate fine-tuning with learning rate scheduling adjustments.
   - Benchmark inference latency on edge / CPU devices.
   - Test data augmentation tuning (e.g. mosaic, scale, perspective) for waterlogging scenes.
