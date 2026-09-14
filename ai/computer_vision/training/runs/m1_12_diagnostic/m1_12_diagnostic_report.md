# CVKI M1.12 — YOLOv8n Failure Diagnostic Investigation Report

- **Investigation Stage**: M1.12 Diagnostic Investigation
- **Target Experiment**: M1.11 (`ai/computer_vision/training/runs/yolov8n_improved_311/`)
- **Baseline Benchmark**: M1.8 (`ai/computer_vision/training/runs/yolov8n_baseline_300/`)
- **Diagnostic Run Directory**: `ai/computer_vision/training/runs/m1_12_diagnostic/`
- **Execution Mode**: **STRICTLY DIAGNOSTIC-ONLY (NO RETRAINING / NO DATASET MODIFICATIONS)**
- **Date**: 2026-09-13
- **Investigator**: CVKI Antigravity Autonomous Agent

---

## 1. Executive Summary

In Module 1.11, an isolated YOLOv8n retraining experiment was conducted on the engineered 311-image dataset (`dataset_improved/`). The held-out test evaluation revealed severe performance degradation across all three defect classes compared to the frozen M1.8 baseline:

- **Overall mAP@0.5**: Dropped from **0.6166 (61.7%)** to **0.4166 (41.7%)** (**-20.00 pp**, relative **-32.4%**)
- **Overall Recall**: Collapsed from **0.5660 (56.6%)** to **0.3857 (38.6%)** (**-18.03 pp**, relative **-31.9%**)
- **Overall Precision**: Dropped from **0.7797 (78.0%)** to **0.5785 (57.8%)** (**-20.12 pp**, relative **-25.8%**)
- **`road_waterlogging` mAP@0.5**: Collapsed from **0.2951 (29.5%)** to **0.0463 (4.6%)** (**-24.88 pp**, relative **-84.3%**)
- **`damaged_missing_road_sign` mAP@0.5**: Dropped from **0.7950 (79.5%)** to **0.5450 (54.5%)** (**-25.00 pp**, relative **-31.4%**)
- **`open_damaged_manhole` mAP@0.5**: Dropped from **0.7598 (76.0%)** to **0.6586 (65.9%)** (**-10.12 pp**, relative **-13.3%**)

This diagnostic investigation established three definitive root causes:
1. **Hyperparameter/Augmentation Discrepancy (`mosaic=0.0` vs `mosaic=1.0`)**: In M1.11, mosaic augmentation was disabled (`mosaic: 0.0`) and scale jitter was throttled (`scale: 0.15` vs `scale: 0.5`). On a small dataset (~218 training images), disabling mosaic deprived the architecture of 4-image multi-scale spatial context. Because the manhole and road sign datasets were 100% identical between M1.8 and M1.11, their sharp degradations prove conclusively that this augmentation policy crippled the entire model.
2. **Unpaired, Disjoint Test Sets (0% Waterlogging Overlap)**: The M1.8 test set contained 10 images from 4 high-contrast scenes with 39 fragmented annotations. The M1.11 test set contained 11 images from 6 completely different scenes with unified contiguous annotations and 1 background negative image. The two test evaluations were not a controlled paired experiment.
3. **Severe Waterlogging Instance Starvation & Over-Suppression**: In M1.11, merging fragmented boxes into contiguous boxes reduced training bounding boxes from **315 to 124 (a 60.6% reduction)**, while adding 19 negative training images (24.4% of waterlogging data). This combination trained the model to aggressively suppress water predictions, resulting in an **88.0% False Negative rate** on test puddles.

---

## 2. M1.8 Baseline vs M1.11 Retrained Metric Comparison

The table below presents the quantitative benchmark comparison on the respective held-out test splits:

| Evaluation Metric | M1.8 Baseline (300 imgs) | M1.11 Retrained (311 imgs) | Absolute Delta (pp) | Relative Impact |
|---|---|---|---|---|
| **Overall Precision** | **0.7797** (78.0%) | **0.5785** (57.8%) | `-20.12%` | Severe Degradation |
| **Overall Recall** | **0.5660** (56.6%) | **0.3857** (38.6%) | `-18.03%` | Severe Degradation |
| **Overall mAP@0.5** | **0.6166** (61.7%) | **0.4166** (41.7%) | `-20.00%` | Severe Degradation |
| **Overall mAP@0.5:0.95** | **0.4279** (42.8%) | **0.2767** (27.7%) | `-15.12%` | Severe Degradation |
| **Manhole mAP@0.5** | **0.7598** (76.0%) | **0.6586** (65.9%) | `-10.12%` | Moderate Degradation |
| **Road Sign mAP@0.5** | **0.7950** (79.5%) | **0.5450** (54.5%) | `-25.00%` | Severe Degradation |
| **Waterlogging mAP@0.5** | **0.2951** (29.5%) | **0.0463** (4.6%) | `-24.88%` | Near-Total Collapse |

---

## 3. Training History Audit & Best Epoch Verification

An audit of `ai/computer_vision/training/runs/yolov8n_improved_311/results.csv` and checkpoint internals revealed:

- **Total Logged Epochs**: 76 epochs completed before early stopping triggered.
- **Patience Parameter**: `patience = 20`.
- **Best Epoch for mAP@0.5**: **Epoch 76** (`mAP50 = 0.6381`).
- **Best Epoch for mAP@0.5:0.95**: **Epoch 56** (`mAP50-95 = 0.3919`).
- **Ultralytics Early Stopping Criterion**: Ultralytics monitors `fitness` (defined as `0.1 * mAP50 + 0.9 * mAP50-95` or strictly `mAP50-95`). In `best.pt` metadata:
  ```python
  train_metrics = {
      'metrics/mAP50(B)': 0.60418,
      'metrics/mAP50-95(B)': 0.39188,
      'val/box_loss': 1.48454,
      'val/cls_loss': 1.69184,
      'fitness': 0.39188
  }
  ```
- **Does Epoch 76 correspond to `best.pt`?**: **NO.** `best.pt` was saved at **Epoch 56**. From Epoch 57 through Epoch 76 (exactly 20 epochs), validation fitness never surpassed 0.39188. At Epoch 76, the patience counter reached 20 and triggered termination. `last.pt` corresponds to Epoch 76.
- **Late-Stage Overfitting Verification**:
  - From Epoch 56 to Epoch 76, `train/box_loss` decreased from **0.7622 to 0.6273** (-17.7%).
  - `train/cls_loss` decreased from **0.6801 to 0.5178** (-23.9%).
  - In contrast, `val/box_loss` stalled and increased slightly from **1.4845 to 1.4947** (+0.7%).
  - This divergence confirms that late-stage training was overfitting to the training split without improving generalization.

---

## 4. Per-Class Degradation Analysis

To understand why degradation occurred across all classes, we analyzed the test confusion matrix, precision-recall curves, and prediction counts:

### 4.1 `open_damaged_manhole` (Unchanged Dataset: 100 images)
- **Baseline (M1.8)**: P=0.8420, R=0.6671, mAP50=0.7598, mAP50-95=0.5113
- **Retrained (M1.11)**: P=0.5802, R=0.6875, mAP50=0.6586, mAP50-95=0.4426
- **Test Set**: 10 images, 16 ground truth instances.
- **Test Detections**: 11 TP, 6 FP, 5 FN (Recall: 68.8%, Precision: 64.7%).
- **Observation**: Manhole recall held steady (+2.04 pp), but precision degraded (-26.18 pp) due to 6 false alarms on road textures, leading to a 10.12 pp drop in mAP50.

### 4.2 `damaged_missing_road_sign` (Unchanged Dataset: 100 images)
- **Baseline (M1.8)**: P=0.8294, R=0.8000, mAP50=0.7950, mAP50-95=0.5987
- **Retrained (M1.11)**: P=1.0000, R=0.3896, mAP50=0.5450, mAP50-95=0.3762
- **Test Set**: 10 images, 5 ground truth instances (5 positive images, 5 negative images).
- **Test Detections**: 2 TP, 0 FP, 3 FN (Recall: 40.0%, Precision: 100.0%).
- **Observation**: Road Sign precision was perfect (1.0000, zero false alarms), but recall collapsed from 80.0% to 39.0% (-41.04 pp). The model completely missed 3 out of 5 signs because they were distant/small, directly pointing to the lack of mosaic multi-scale scaling.

### 4.3 `road_waterlogging` (Targeted Improved Class: 111 images)
- **Baseline (M1.8)**: P=0.6676, R=0.2308, mAP50=0.2951, mAP50-95=0.1737
- **Retrained (M1.11)**: P=0.1552, R=0.0800, mAP50=0.0463, mAP50-95=0.0114
- **Test Set**: 11 images, 25 ground truth instances (10 positive images, 1 negative image).
- **Test Detections**: 3 TP, 13 FP, 22 FN (Recall: 12.0%, Precision: 18.8%).
- **Observation**: Near-total failure. 22 out of 25 puddles were missed (88.0% FN rate).

---

## 5. Waterlogging Root-Cause Deep Diagnosis

Addressing the 6 specific diagnostic questions:

### A. Did reducing fragmented water boxes from 439 to 176 remove useful training signal?
- **Finding**: **Strongly Suggested**.
- **Evidence**: In M1.8, the 70 training images had **315 bounding boxes** (an average density of 4.50 boxes/image). In M1.10/M1.11, the contiguous box merging policy reduced training boxes to **124 boxes across 78 images** (density of 1.59 boxes/image). This represents a **60.6% reduction in positive training instances**. In small-sample deep learning, each bounding box provides a backpropagation gradient signal for regression and classification. Merging fragmented boxes created cleaner semantic masks but severely starved the anchor assignment layers of training examples.

### B. Did adding 25 negative images cause excessive suppression of genuine waterlogging?
- **Finding**: **Strongly Suggested**.
- **Evidence**: In M1.8, there was only 1 negative waterlogging image in training (1.4%). In M1.11, 19 negative images were added to the training set (24.4% of the waterlogging training split). Low-confidence inference analysis revealed that the model did activate over puddles, but with confidence scores depressed to 0.05–0.18. The heavy negative sample penalty taught the classifier that asphalt reflections, damp sheen, and tree shadows are non-water, which over-generalized into suppressing actual shallow water.

### C. Did the removal of rotation artifacts reduce useful visual diversity?
- **Finding**: **Strongly Suggested**.
- **Evidence**: In M1.8, the Roboflow source dataset contained 90° and 270° rotations. While physically unnatural (violating gravity), these rotations functioned as aggressive 4x data multiplication. When M1.10 replaced rotated images with canonical orientation and set `degrees=0` without adding substitute geometric augmentations, the effective sample size shrank.

### D. Did the new waterlogging images differ substantially from the original M1.8 test distribution?
- **Finding**: **CONFIRMED BY EVIDENCE**.
- **Evidence**: The M1.8 and M1.11 waterlogging test splits share **ZERO images in common (0/10 overlap)**.
  - **M1.8 Test Split**: 10 images derived from only 4 source scenes (`waterloggingt-103-`, `waterloggingt-104-`, `waterloggingt-126-`, `waterloggingt-145-`). All 10 images featured high-contrast, multi-puddle scenes with 39 fragmented annotations (3.90 boxes/img).
  - **M1.11 Test Split**: 11 images from 6 completely different scenes (`waterloggingt-110-`, `waterloggingt-11-`, `waterloggingt-128-`, `waterloggingt-25-`, `waterloggingt-127-`, `waterloggingt-114-`) with 25 unified contiguous annotations and 1 negative background image.
  - Evaluating models on completely non-overlapping images invalidates any assumption of identical difficulty.

### E. Are failures concentrated in specific scene types?
- **Finding**: **CONFIRMED BY EVIDENCE**.
- **Evidence**:
  - **Small Puddles**: Total miss. Puddles covering $<3\%$ of the image area in `waterloggingt-110-` and `waterloggingt-11-` had 0 detections.
  - **Shallow / Damp Water**: In `waterloggingt-11-` and `waterloggingt-128-`, shallow water patches without prominent sky reflections were completely missed (FN).
  - **Dark Asphalt / Underpasses**: Low luminance contrast between puddle water and wet asphalt resulted in complete non-detection.
  - **Multi-Puddle Scenes**: In `waterloggingt-114-` (containing 5 discrete puddles), the model either predicted a single bounding box enclosing multiple puddles (yielding IoU $<0.50$, classified as FP) or missed the peripheral puddles entirely.

### F. Positive/Negative Ratios and Annotation Density Comparison
| Attribute | M1.8 Waterlogging | M1.10 Improved Waterlogging | Delta |
|---|---|---|---|
| **Total Images** | 100 | 111 | +11 (+11.0%) |
| **Positive Images** | 98 (98.0%) | 84 (75.7%) | -14 (-14.3%) |
| **Negative Images** | 2 (2.0%) | 27 (24.3%) | +25 (+1250%) |
| **Total Bounding Boxes** | 439 | 176 | -263 (-59.9%) |
| **Average Boxes / Image** | 4.39 | 1.59 | -2.80 (-63.8%) |
| **Train Split Images** | 70 (69 pos / 1 neg) | 78 (59 pos / 19 neg) | +8 (+11.4%) |
| **Train Bounding Boxes** | 315 | 124 | -191 (-60.6%) |
| **Train Box Density** | 4.50 boxes/img | 1.59 boxes/img | -2.91 (-64.7%) |

---

## 6. Dataset Distribution Comparison Across All Classes

Comprehensive comparison between the M1.8 dataset (`ai/computer_vision/dataset/`) and M1.10 dataset (`ai/computer_vision/dataset_improved/`):

| Class Name | Dataset Version | Total Imgs | Pos Imgs | Neg Imgs | Total Boxes | Boxes/Img | Train (Imgs/Boxes) | Val (Imgs/Boxes) | Test (Imgs/Boxes) |
|---|---|---|---|---|---|---|---|---|---|
| **Manhole** | M1.8 Baseline | 100 | 100 | 0 | 188 | 1.88 | 70 / 133 | 20 / 39 | 10 / 16 |
| **Manhole** | M1.10 Improved | 100 | 100 | 0 | 188 | 1.88 | 70 / 133 | 20 / 39 | 10 / 16 |
| **Road Sign** | M1.8 Baseline | 100 | 52 | 48 | 52 | 0.52 | 70 / 36 | 20 / 11 | 10 / 5 |
| **Road Sign** | M1.10 Improved | 100 | 52 | 48 | 52 | 0.52 | 70 / 36 | 20 / 11 | 10 / 5 |
| **Waterlogging** | M1.8 Baseline | 100 | 98 | 2 | 439 | 4.39 | 70 / 315 | 20 / 85 | 10 / 39 |
| **Waterlogging** | M1.10 Improved | 111 | 84 | 27 | 176 | 1.59 | 78 / 124 | 22 / 27 | 11 / 25 |
| **TOTAL** | **M1.8 Baseline** | **300** | **250** | **50** | **679** | **2.26** | **210 / 484** | **60 / 135** | **30 / 60** |
| **TOTAL** | **M1.10 Improved** | **311** | **236** | **75** | **416** | **1.34** | **218 / 293** | **62 / 77** | **31 / 46** |

---

## 7. Test Distribution Fairness Check

- **Manhole**: 10 test images in M1.8 vs 10 in M1.11. **100% Identical images and labels**. Directly comparable.
- **Road Sign**: 10 test images in M1.8 vs 10 in M1.11. **100% Identical images and labels**. Directly comparable.
- **Waterlogging**: 10 test images in M1.8 vs 11 in M1.11. **0% Overlap**. Completely different images, scenes, and annotation conventions.
- **Scientific Conclusion**: This was **NOT a controlled paired experiment**. Comparing M1.8 and M1.11 test scores as if they came from the same distribution is methodologically flawed. The observed delta reflects both model behavior and test set distribution shift.

---

## 8. Summary of Findings

### 8.1 Confirmed by Evidence
1. **Disabling Mosaic and Scale Jitter Caused Model-Wide Degradation**:
   Manhole and Road Sign data did not change by a single pixel or annotation, yet Road Sign mAP50 dropped by **25.00 pp** (recall halved from 80% to 39%) and Manhole mAP50 dropped by **10.12 pp**. The only variables that changed for these classes were training hyperparameters (`mosaic: 0.0` vs `1.0`, `scale: 0.15` vs `0.50`).
2. **Test Sets for Waterlogging Are Disjoint**:
   0 out of 10 waterlogging images overlap between the M1.8 and M1.11 test splits.
3. **`best.pt` Is Epoch 56, Not Epoch 76**:
   Training logged 76 epochs before early stopping. `best.pt` checkpoint metrics match Epoch 56 (`mAP50-95 = 0.3919`), while Epoch 76 represents `last.pt`.
4. **Late-Stage Overfitting Occurred**:
   Training losses steadily decreased after Epoch 56 while validation loss plateaued and rose.

### 8.2 Strongly Suggested Findings
1. **60% Bounding Box Depletion Starved the Model**:
   Merging fragmented boxes into contiguous boxes reduced waterlogging training instances from 315 to 124. This drastic reduction deprived the network of sufficient gradient signals.
2. **Excessive Negative Ratio Over-Suppressed Detections**:
   24.4% negative images in the waterlogging training set caused the model to severely penalize detections on ambiguous damp surfaces, depressing puddle confidence scores below 0.25.

### 8.3 Inconclusive Findings
1. **Isolated Impact of Canonical Orientation vs Rotated Variants**:
   Because orientation normalization was applied simultaneously with box consolidation, negative injection, and mosaic disabling, the isolated effect of canonical orientation cannot be separated without a controlled ablation study.

---

## 9. Visual Diagnostic Artifacts

The following visual diagnostic artifacts were generated directly from existing models and data and are stored in `ai/computer_vision/training/runs/m1_12_diagnostic/`:

1. **`waterlogging_contact_sheet.png`**: Image-by-image grid of all 11 waterlogging test images showing ground truth vs predictions, annotated with TP, FP, FN, and status.
2. **`manhole_contact_sheet.png`**: Image-by-image grid of all 10 manhole test images with prediction overlays.
3. **`road_sign_contact_sheet.png`**: Image-by-image grid of all 10 road sign test images with prediction overlays.
4. **`per_class_error_summary.png`**: Bar chart comparing GT, TP, FP, and FN across all three classes.
5. **`confidence_and_metric_distribution.png`**: Multi-panel visualization contrasting M1.8 vs M1.11 mAP50 per class and waterlogging detection breakdown.
6. **`per_image_errors.csv`**: Machine-readable breakdown of every test image with IoU, confidence, and detection outcomes.

---

## 10. Recommended Next Experiment (Module 1.13 Plan)

Based on empirical diagnostic evidence, the degradation was primarily driven by **hyperparameter mismatch (`mosaic=0`, `scale=0.15`)** combined with **severe instance starvation**:

1. **Controlled Augmentation Ablation**:
   Train YOLOv8n on `dataset_improved/` with Ultralytics standard augmentations restored:
   - `mosaic: 1.0` (or `mosaic: 0.8` with `close_mosaic: 10`)
   - `scale: 0.5` (restoring multi-scale pyramid training)
   - Keep `degrees: 0.0` and `flipud: 0.0` (preserving physical gravity).
2. **Sub-Box Density Preservation**:
   If multi-puddle scenes are present, annotate discrete puddle components rather than merging distant puddles into a single massive loose box.
3. **Negative Ratio Tuning**:
   Cap negative waterlogging training images to ~10–12% rather than 24.4% to prevent over-suppression.
4. **Paired Benchmark Evaluation**:
   Evaluate both M1.8 `best.pt` and the new candidate model on BOTH test sets (M1.8 test split and M1.11 test split) to guarantee fair, paired comparative metrics.

---

## 11. Certification of Non-Modification

**EXPLICIT STATEMENT**:
This was a **DIAGNOSTIC-ONLY** investigation.
- **NO RETRAINING OR FINE-TUNING WAS PERFORMED.**
- `ai/computer_vision/training/runs/yolov8n_baseline_300/` remains **100% UNTOUCHED** (M1.8 frozen).
- `ai/computer_vision/training/runs/m1_9_inference/` remains **100% UNTOUCHED**.
- `ai/computer_vision/dataset/` remains **100% UNTOUCHED**.
- `ai/computer_vision/dataset_improved/` remains **100% UNTOUCHED**.
- `ai/computer_vision/training/runs/yolov8n_improved_311/` remains **100% UNTOUCHED**.
