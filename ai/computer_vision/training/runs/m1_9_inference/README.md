# CVKI Module 1.9 — Baseline Inference & Controlled Error Analysis

## Overview
Module 1.9 performs a controlled, read-only inference and error analysis on the **Civic Vision & Knowledge Intelligence (CVKI)** YOLOv8n baseline model (`weights/best.pt`, Epoch 85) across all 30 held-out test images.

The primary objective is to investigate the root causes of the recall deficit in the `road_waterlogging` class (Precision: 0.6676, Recall: 0.2308, mAP50: 0.2951) using visual ground-truth overlay comparisons.

---

## Directory Organization

```
m1_9_inference/
├── README.md               # This navigation document
├── predictions/            # All 30 annotated test images (GT vs Preds)
├── correct/                # Images containing confirmed True Positive detections (IoU >= 0.50)
├── missed/                 # Images containing missed defect instances (False Negatives)
├── false_positives/        # Images containing background false alarms (False Positives)
└── reports/
    ├── error_analysis.md   # Comprehensive qualitative and quantitative error report
    └── error_summary.json  # Machine-readable per-image and per-class error records
```

---

## Annotation Legend on Prediction Images
- **Green Box (`GT: <class>`)**: Ground-truth defect correctly matched by a prediction ($	ext{IoU} \ge 0.50$).
- **Bright Yellow Box (`MISSED GT: <class>`)**: Ground-truth defect missed by the model (False Negative).
- **Cyan/Green Box (`PRED (TP): <class> <conf>`)**: True Positive prediction matching ground truth.
- **Red Box (`PRED (FP): <class> <conf>`)**: False Positive prediction (background false alarm or duplicate detection).

---

## Key Findings
1. **Zero Cross-Class Confusion**: Manhole, road sign, and waterlogging classes are never confused with one another.
2. **Waterlogging Failure Modes**:
   - **Micro-Puddle Fragmentation**: Scattered small puddles (<3% image area) are frequently missed.
   - **Contiguous Box Merging**: Human annotators divided flooded roads into multiple sub-boxes, whereas the model detected a single large flood area (penalized by strict IoU).
   - **Low-Contrast Shallow Water**: Sheet water without strong specular reflection is missed as normal asphalt.
   - **Shadow False Alarms**: Asphalt shadows and dark patches trigger false positive puddle detections.
