# CVKI M1.12 — Test Error Summary & Image-by-Image Breakdown

- **Model Checkpoint**: M1.11 `weights/best.pt`
- **Test Split**: 31 Held-Out Images (`ai/computer_vision/dataset_improved/images/test`)
- **Evaluation Settings**: Confidence Threshold $\ge 0.25$, IoU Threshold $\ge 0.50$
- **Date**: 2026-09-13

---

## 1. Class-Wise Detection & Error Summary

| Class Name | Ground Truth Instances | Model Predictions | True Positives (TP) | False Positives (FP) | False Negatives (FN) | Empirical Precision | Empirical Recall |
|---|---|---|---|---|---|---|---|
| **`open_damaged_manhole`** | 16 | 17 | 11 | 6 | 5 | 0.6471 | 0.6875 |
| **`damaged_missing_road_sign`** | 5 | 2 | 2 | 0 | 3 | 1.0000 | 0.4000 |
| **`road_waterlogging`** | 25 | 16 | 3 | 13 | 22 | 0.1875 | 0.1200 |
| **TOTAL** | 46 | 35 | 16 | 19 | 30 | 0.4571 | 0.3478 |

---

## 2. Image Outcome Distribution

| Outcome Category | Count | Description |
|---|---|---|
| **PERFECT MATCH** | 6 | All ground-truth targets detected with $\ge 0.50$ IoU and 0 false alarms |
| **CLEAN NEGATIVE** | 5 | Background negative images with 0 false positive detections |
| **FALSE ALARM** | 1 | Negative images triggering background false positives |
| **PARTIAL MATCH** | 9 | At least one target detected, but with some misses or false positives |
| **TOTAL MISS** | 10 | Positive defect images where the model detected 0 true defects |

---

## 3. Waterlogging Breakdown (Key Failure Class)
- Total Waterlogging Test Images: 11
- Positive Waterlogging Images: 10 (containing 25 ground-truth puddle targets)
- Background Negative Images: 1
- **Detected True Positives**: **3 / 25 (12.0%)**
- **Missed Targets (False Negatives)**: **22 / 25 (88.0%)**
- **False Positive Detections**: **13**
