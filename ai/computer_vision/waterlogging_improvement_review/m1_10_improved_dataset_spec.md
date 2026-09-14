# CVKI M1.10 — Improved Dataset Specification

- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Module**: M1.10 — Waterlogging Dataset Improvement & Preparation
- **Target Specification**: Proposed Improved Multi-Class Civic Detection Dataset
- **Status**: **PROPOSAL / SPECIFICATION** (Planning only — no dataset files modified)
- **Date**: 2026-09-12

---

## 1. Executive Summary & Baseline Isolation Guarantee

### The Frozen Baseline Safeguard
The existing **300-image M1.8 baseline dataset** located at:
`ai/computer_vision/dataset/`
is **PERMANENTLY FROZEN**. 

Zero files will be deleted, renamed, overwritten, or modified in `ai/computer_vision/dataset/`. All M1.8 artifacts (`best.pt`, `last.pt`, `results.csv`, `training_report.md`) and M1.9 artifacts remain strictly untouched as immutable historical benchmarks.

The improved dataset defined in this specification will reside in a completely isolated, parallel workspace:
`ai/computer_vision/dataset_improved/`
and will only be materialized after the user reviews and explicitly approves this specification.

---

## 2. Dataset Sizing & Transition Matrix

### 2.1 Waterlogging Subset Re-Engineering Breakdown

Based on empirical evidence from M1.8 evaluation, M1.9 inference/error analysis, and the Phase A–C audits, the waterlogging class will undergo targeted cleaning:

| Metric / Category | Count | Percentage | Details & Rationale |
|---|---|---|---|
| **Original Waterlogging Dataset** | **100** | 100.0% | 94 from `prepared_sources`, 6 from `replacement_sources` |
| ├── Original Positive Images | 98 | 98.0% | 439 target bounding boxes (average 4.39 boxes/image) |
| └── Original Negative Images | 2 | 2.0% | Only 2 background negative images (severe 2% imbalance) |
| **Proposed Exclusions (Phase C)** | **-42** | -42.0% | **42 images confirmed as artificial 90°/270° rotations** from Roboflow export; vertical road puddles violating physical gravity |
| **Proposed Retained Images** | **58** | 58.0% | 25 verified upright natural images + 33 curated collage scenes |
| ├── Retained Positive Images | 56 | 56.0% | All re-annotated under unified contiguous boundary policy |
| └── Retained Negative Images | 2 | 2.0% | Clean wet surface background negatives |
| **Proposed New Positive Additions** | **+28** | +28.0% | 28 clean, single-scene, upright natural images targeting shallow water, small puddles, underpasses, and diverse asphalt |
| **Proposed New Negative Additions** | **+25** | +25.0% | 25 targeted negative images targeting tree shadows (6), bridge shadows (5), asphalt patches (5), wet asphalt (5), and curbs (4) |
| **Proposed Improved Waterlogging Total** | **111** | **100.0%** | **84 Positive + 27 Negative Images (24.3% Negative Ratio)** |

### 2.2 Multi-Class Improved Dataset Target

To maintain multi-class balance across all 3 civic classes:

| Class ID | Class Name | Baseline Count (M1.8) | Improved Count (Proposed) | Positive Images | Negative Images | Negative Ratio |
|---|---|---|---|---|---|---|
| **0** | `open_damaged_manhole` | 100 | **100** | 100 | 0 | 0.0% |
| **1** | `damaged_missing_road_sign` | 100 | **100** | 52 | 48 | 48.0% |
| **2** | `road_waterlogging` | 100 | **111** | 84 | 27 | 24.3% |
| **TOTAL** | **All 3 Civic Defect Classes** | **300** | **311** | **236** | **75** | **24.1%** |

---

## 3. Standardization & Annotation Policy

### 3.1 Contiguous Puddle Bounding (The Clustering Rule)
- **Problem in Baseline**: In baseline ground truth, annotators drew 4 to 10 disjoint boxes over connected segments of a single flood zone. When YOLO predicted one large bounding box covering the entire puddle, it scored an IoU $<0.50$ against individual sub-boxes, triggering 1 False Positive and multiple False Negatives simultaneously.
- **Improved Policy**: Any contiguous body of standing water on a roadway lane must be bounded by a **single, unified bounding box** representing the total flood hazard zone. Sub-puddle fragmentation is strictly prohibited.

### 3.2 Micro-Puddle Area Threshold ($\ge 0.5\%$ Image Area)
- **Problem in Baseline**: 18 boxes in the baseline had area $<0.005$ (less than 0.5% of the image). Downsampling to $640 \times 640$ compresses these micro-puddles into a $5 \times 5$ pixel cluster, causing spatial gradient collapse across YOLO's P3/P4/P5 strides.
- **Improved Policy**: Micro-puddles smaller than 0.5% of total image area ($< 1,000$ pixels on $512 \times 384$) must either be:
  1. Merged into the nearest parent puddle bounding box if contiguous, OR
  2. Pruned from the annotation label if isolated and non-hazardous.

### 3.3 Aspect Ratio Bounds ($0.25 \le \text{AR} \le 4.0$)
- Narrow vertical or horizontal stripes ($AR < 0.25$ or $> 4.0$) that represent curb lines or rotation artifacts are prohibited. Bounding boxes must reflect the planar spread of liquid on the pavement surface.

### 3.4 Shallow Water Inclusions
- Shallow dirty water where road texture remains partially visible must be included inside the bounding box if it connects to the main standing puddle.

---

## 4. Augmentation Policy Summary

As specified in `waterlogging_augmentation_policy.md`:
- **Allowed**: Horizontal reflection (`fliplr: 0.5`), mild photometric jitter (`hsv_h: 0.015`, `hsv_s: 0.4`, `hsv_v: 0.3`), mild scale/translation ($\pm 10\%$), mild perspective ($\pm 0.0005$).
- **Prohibited**: 90°, 180°, 270° rotations (`degrees: 0.0`), vertical flip (`flipud: 0.0`), multi-quadrant collage mosaic (`mosaic: 0.0`), and random rectangular cutout.

---

## 5. Train / Val / Test Split Policy & Leakage Prevention

### 5.1 Stratification Matrix

The 111 improved waterlogging images will be partitioned strictly using a **70% / 20% / 10%** ratio, stratified across positive and negative subsets:

| Split | Percentage | Positive Images | Negative Images | Total Waterlogging Images |
|---|---|---|---|---|
| **Train** | **70.3%** | 59 | 19 | **78** |
| **Val** | **19.8%** | 17 | 5 | **22** |
| **Test** | **9.9%** | 8 | 3 | **11** |
| **TOTAL** | **100.0%** | **84** | **27** | **111** |

### 5.2 Scene-Level Leakage Prevention
1. **Base Stem Grouping**: All images sharing a common source base stem (e.g. `waterloggingt-103`) MUST be assigned exclusively to a single split (all in train, or all in val, or all in test). Cross-split scene leakage is an automatic QA failure.
2. **Deterministic Splitting**: Partitioning will be executed with a fixed pseudo-random seed (`seed = 42`) for 100% audit reproducibility.
3. **Held-Out Test Integrity**: The test split will contain 8 positive and 3 negative waterlogging images, providing a rigorous, unbiased benchmark to verify the elevation of mAP@0.5 and the suppression of shadow false alarms.

---

## 6. Implementation Roadmap

1. **Step 1 (M1.10 — Active)**: Complete planning, inspection, annotation review CSV, orientation audit CSV, and QC plan. (NO TRAINING / NO DATASET MODIFICATIONS).
2. **Step 2 (M1.11 — Post-Approval)**:
   - Curate 28 verified positive images and 25 negative images in `staged_sources/`.
   - Apply unified contiguous annotation formatting.
   - Build isolated `ai/computer_vision/dataset_improved/`.
   - Run automated M1.11 QA suite.
3. **Step 3 (M1.12 — Retraining Experiment)**:
   - Train YOLOv8n on `dataset_improved/` using `hyp.improved_civic.yaml`.
   - Evaluate against frozen test split and compute delta against M1.8 benchmark.
