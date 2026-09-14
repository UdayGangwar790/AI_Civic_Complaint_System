# CVKI M1.11 — Improved YOLOv8n Training Report

- **Run Name**: `yolov8n_improved_311`
- **Date**: 2026-09-13
- **Duration**: 3:31:33
- **Best Checkpoint**: `weights/best.pt` (Epoch 76)
- **Dataset**: `dataset_improved/` (311 images: 218 train, 62 val, 31 test)
- **Status**: **COMPLETE / VERIFIED**

---

## 1. Executive Summary

Module 1.11 executed the isolated retraining experiment on the newly engineered 311-image civic dataset. Training was initialized from scratch using pretrained `yolov8n.pt` weights and executed under strict gravity-preserving augmentation constraints (`mosaic=0`, `degrees=0`, `flipud=0`).

### Held-Out Test Split Metrics (31 Images)
- **Precision**: `0.5785`
- **Recall**: `0.3857`
- **mAP@0.5**: `0.4166`
- **mAP@0.5:0.95**: `0.2767`

---

## 2. Integrity Confirmation
- M1.8 Baseline: 100% UNTOUCHED
- M1.8 Weights: 100% UNTOUCHED
- M1.9 Artifacts: 100% UNTOUCHED
- M1.10 Dataset: 100% UNTOUCHED
