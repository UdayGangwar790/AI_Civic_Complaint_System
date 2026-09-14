# CVKI M1.13 — Controlled YOLOv8n Training Report

- **Experiment**: `yolov8n_m1_13`
- **Date**: 2026-09-13
- **Duration**: 4:36:08
- **Completed Epochs**: 81
- **Best Epoch**: Epoch 61 (Peak Validation Fitness: 0.4400)
- **Dataset**: `dataset_m1_13/` (300 images: 207 train, 62 val, 31 test)
- **Status**: **COMPLETE / VERIFIED**

---

## 1. Executive Summary

Module 1.13 successfully executed the controlled correction experiment, incorporating the four core findings from the M1.12 failure diagnosis:
1. Re-enabled multi-scale mosaic augmentation (`mosaic: 1.0`, `close_mosaic: 10`) and restored scale jitter (`scale: 0.5`).
2. Preserved physical gravity orientation priors (`degrees: 0.0`, `flipud: 0.0`).
3. Recalibrated waterlogging training negatives from 19 (24.4%) to 8 (11.9%) across 5 civic failure categories.
4. Maintained clean contiguous bounding box puddle annotations.

The resulting detector achieved the highest overall mAP@0.5 and recall recorded in the CVKI project to date.

---

## 2. Quantitative Evaluation Results

### Validation Split (62 Images, dataset_m1_13)
- **Precision**: `0.7260`
- **Recall**: `0.5900`
- **mAP@0.5**: `0.6430`
- **mAP@0.5:0.95**: `0.4170`

### Original M1.8 Held-Out Test Set (30 Images)
- **Precision**: `0.8380`
- **Recall**: `0.6120`
- **mAP@0.5**: `0.6540`
- **mAP@0.5:0.95**: `0.4870`
- **Waterlogging mAP@0.5**: `0.3520` (vs M1.8 baseline: 0.2951)

### Improved M1.11 Held-Out Test Set (31 Images)
- **Precision**: `0.6500`
- **Recall**: `0.5700`
- **mAP@0.5**: `0.5680`
- **mAP@0.5:0.95**: `0.4230`
- **Waterlogging mAP@0.5**: `0.0841` (vs M1.11: 0.0463)

---

## 3. Frozen Baseline Safeguard
- M1.8 Baseline: 100% UNTOUCHED
- M1.9 Artifacts: 100% UNTOUCHED
- M1.10 Dataset: 100% UNTOUCHED
- M1.11 Artifacts: 100% UNTOUCHED
