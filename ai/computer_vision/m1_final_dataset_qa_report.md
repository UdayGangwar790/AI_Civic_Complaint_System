# CVKI M1.6 — Final Dataset Quality Assurance Audit Report

- **Execution Date**: 2026-09-12
- **Module**: M1.6 — Final Dataset Quality Assurance (Read-Only Audit)
- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Target Dataset**: `ai/computer_vision/dataset/`
- **Audit Mode**: STRICTLY READ-ONLY (Zero files modified, overwritten, or deleted)
- **Final Audit Status**: **M1.6 STATUS: PASS**

---

## 1. Executive Summary

A comprehensive, read-only quality assurance audit was conducted across the completed 3-class CVKI YOLO object detection dataset (`ai/computer_vision/dataset/`). All 300 images and 300 label files were inspected and validated across directory structure, image readability, annotation integrity, class assignment, bounding box geometry, near/exact duplicate presence, base scene group leakage, manifest parity, configuration syntax, and upstream source integrity.

Every automated check passed with 100% compliance. The dataset exhibits zero orphan files, zero corrupt images, zero malformed labels, zero coordinates out of bounds, and zero cross-split scene leakage.

| Audit Category | Checked Items | Result | Severity |
|---|---|---|---|
| **1. Directory Structure** | Standard YOLO hierarchy + config/manifests | **PASS** | None |
| **2. Image Counts** | 300 total (210 train, 60 val, 30 test) | **PASS** | None |
| **3. Label Counts** | 300 total (210 train, 60 val, 30 test) | **PASS** | None |
| **4. 1:1 Image-Label Pairing** | 300 matched pairs, 0 orphans | **PASS** | None |
| **5. Class Balance** | 100 per class (70 train, 20 val, 10 test) | **PASS** | None |
| **6. Image Readability** | PIL verify + dimensions on 300 images | **PASS** | None |
| **7. Label Formatting** | 5-token YOLO numeric format, valid bounds | **PASS** | None |
| **8. Class Remapping** | Classes strictly in {0, 1, 2} | **PASS** | None |
| **9. Duplicate Analysis** | SHA-256 exact + dHash perceptual checks | **PASS** | None |
| **10. Scene Leakage** | 38 Waterlogging + 8 Road Sign multi-scenes | **PASS** | None |
| **11. Manifest Consistency** | 300 disk files match manifest entries | **PASS** | None |
| **12. `data.yaml` Integrity** | Canonical paths, class count, class names | **PASS** | None |
| **13. Source Integrity** | Source and prepared datasets 100% untouched | **PASS** | None |
| **14. Reproducibility** | Fixed random seed 42, deterministic split | **PASS** | None |

---

## 2. Directory Structure Verification

The dataset directory conforms strictly to Ultralytics YOLOv8 specifications:

```
ai/computer_vision/dataset/
├── images/
│   ├── train/            --> 210 JPEG images
│   ├── val/              -->  60 JPEG images
│   └── test/             -->  30 JPEG images
├── labels/
│   ├── train/            --> 210 YOLO text labels
│   ├── val/              -->  60 YOLO text labels
│   └── test/             -->  30 YOLO text labels
├── data.yaml             --> Root configuration file
├── dataset_manifest.json --> Machine-readable provenance & image metadata
└── final_split_report.md --> Merged split documentation
```

- **Expected Top-Level Items**: `images`, `labels`, `data.yaml`, `dataset_manifest.json`, `final_split_report.md`
- **Unexpected Files/Folders**: None (0)
- **Missing Files/Folders**: None (0)

---

## 3. Image & Label Counts

### 3.1 Split Breakdown

| Split | Images | Labels | Target Images | Delta | Status |
|---|---|---|---|---|---|
| **Train** | 210 | 210 | 210 | 0 | **EXACT MATCH** |
| **Val** | 60 | 60 | 60 | 0 | **EXACT MATCH** |
| **Test** | 30 | 30 | 30 | 0 | **EXACT MATCH** |
| **Total** | **300** | **300** | **300** | **0** | **100% COMPLETE** |

### 3.2 Per-Class Split Matrix

| Class ID | Class Name | Train (70%) | Val (20%) | Test (10%) | Total Images |
|---|---|---|---|---|---|
| **0** | `open_damaged_manhole` | 70 | 20 | 10 | **100** |
| **1** | `damaged_missing_road_sign` | 70 | 20 | 10 | **100** |
| **2** | `road_waterlogging` | 70 | 20 | 10 | **100** |
| **Total** | **All 3 Classes** | **210** | **60** | **30** | **300** |

---

## 4. Image-Label Pairing Quality Assurance

Every image in the dataset was cross-verified against the corresponding label file in the identical split:
- **Total Matched Pairs**: **300 / 300 (100.0%)**
- **Orphan Images (image without label)**: **0**
- **Orphan Labels (label without image)**: **0**
- **Filename Collision Check**: Deterministic namespace prefixes (`manhole_`, `roadsign_`, `waterlogging_`) ensure zero filename collisions.

---

## 5. Image Format & Integrity Validation

All 300 images were inspected using PIL (`verify()` and full pixel loading):

| Metric | Details |
|---|---|
| **Corrupt / Unreadable Images** | **0** |
| **Truncated Image Files** | **0** |
| **Image Formats** | JPEG: 300 (100%) |
| **Color Modes** | RGB: 300 (100%) |
| **Minimum Dimensions** | 512 x 384 px (`waterlogging` captures) |
| **Maximum Dimensions** | 720 x 720 px (`manhole` captures) |
| **Unique Resolutions** | `720x720`: 100 images (Manhole)<br>`640x640`: 100 images (Road Sign)<br>`512x384`: 100 images (Waterlogging) |

---

## 6. Label Validation & Class Consistency

Every non-empty row across all 300 label files was parsed and verified:
- **Total Label Rows Parsed**: **679**
- **Malformed Rows**: **0** (all rows have exactly 5 tokens)
- **Non-Numeric Tokens**: **0**
- **Invalid Class IDs**: **0** (strictly {0, 1, 2})
- **Center Coordinates Out of Bounds (`xc, yc ∉ [0, 1]`)**: **0**
- **Box Dimensions Out of Bounds (`w, h ∉ (0, 1]`)**: **0**
- **Negative Dimensions**: **0**
- **NaN / Infinity Values**: **0**

### Label Breakdown:
- **Empty Label Files (Negative Background Examples)**: **50**
  - Road Sign Class 1: 48 images (healthy signs as background negatives)
  - Waterlogging Class 2: 2 images (wet surface sheen without pooled water)
- **Single-Object Files**: **96**
- **Multi-Object Files**: **154**

---

## 7. Bounding-Box Statistics

| Metric | Class 0: `open_damaged_manhole` | Class 1: `damaged_missing_road_sign` | Class 2: `road_waterlogging` | Overall Dataset |
|---|---|---|---|---|
| **Total Boxes** | 188 | 52 | 439 | **679** |
| **Positive Images** | 100 | 52 | 98 | **250** |
| **Negative Images** | 0 | 48 | 2 | **50** |
| **Boxes / Total Image** | 1.88 | 0.52 | 4.39 | **2.26** |
| **Boxes / Positive Image** | 1.88 | 1.00 | 4.48 | **2.72** |
| **Width (Min / Avg / Max)** | 0.0458 / 0.2365 / 0.7111 | 0.4274 / 0.8063 / 1.0000 | 0.0215 / 0.1960 / 0.9922 | **0.0215 / 0.2541 / 1.0000** |
| **Height (Min / Avg / Max)** | 0.0236 / 0.1659 / 0.5125 | 0.6270 / 0.8757 / 1.0000 | 0.0260 / 0.2758 / 0.8125 | **0.0236 / 0.2917 / 1.0000** |
| **Area (Min / Avg / Max)** | 0.0013 / 0.0477 / 0.3220 | 0.2876 / 0.7131 / 0.9880 | 0.0023 / 0.0545 / 0.8062 | **0.0013 / 0.1031 / 0.9880** |

### Geometry Observations:
- **Extremely Tiny Boxes (`area < 0.001`)**: **0** (smallest box is area 0.0013, approximately 17x40 px on manhole images, fully legible).
- **Large Boxes (`area > 0.50`)**: **44** (primarily prominent road signs and large panoramic flood pools).
- **Boundary-Touching Boxes**: 304 (typical for waterlogging where floodwaters extend off-camera, and large road signs cropped close to the sign perimeter).

---

## 8. Duplicate & Leakage Analysis

### 8.1 Exact SHA-256 Duplicates
- **Duplicate Image Pairs Across Dataset**: **0**
- **Duplicate Image Pairs Across Splits**: **0**
- Every image has a globally unique SHA-256 hash.

### 8.2 Perceptual / Near-Duplicate Analysis
- A perceptual difference hash (`dHash`, 64-bit) was computed across all 300 images.
- All pairwise cross-split Hamming distances were calculated:
  - Pairs with distance `<= 3` across different splits: **0**
  - **Cross-Split Near-Duplicate Leakage**: **0**

---

## 9. Waterlogging Scene Leakage Verification

Waterlogging contains 38 distinct base scenes (31 scenes with 3 rotation variants = 93 images; 7 single-image scenes = 7 images):

| Metric | Count | Details |
|---|---|---|
| **Total Waterlogging Images** | 100 | 98 positive, 2 negative |
| **Total Base Scenes** | 38 | 31 scenes of 3, 7 scenes of 1 |
| **Train Scenes** | **26** | 22 scenes of 3 (66 imgs) + 4 scenes of 1 (4 imgs) = **70 images** |
| **Val Scenes** | **8** | 6 scenes of 3 (18 imgs) + 2 scenes of 1 (2 imgs) = **20 images** |
| **Test Scenes** | **4** | 3 scenes of 3 (9 imgs) + 1 scene of 1 (1 img) = **10 images** |
| **Cross-Split Leaking Scenes** | **0** | **Zero scene groups span multiple splits** |

Every base scene group is 100% contained within a single split.

---

## 10. Road Sign & Manhole Leakage Verification

- **Road Sign Multi-Image Scenes**: All 8 Roboflow augmented scene pairs (`IMG_8087`, `IMG_8106`, `IMG_8121`, `IMG_8128`, `IMG_8162`, `IMG_8669`, `IMG_8776`, `IMG_9029`) are assigned atomically to `train` (0 variants cross into `val` or `test`).
- **Manhole**: 100 unique independent captures with zero duplicate leakage.
- **Cross-Domain Leakage**: 0 images shared across the three civic defect classes.

---

## 11. Manifest Consistency Verification

`dataset/dataset_manifest.json` was cross-checked against actual filesystem contents:
- **Manifest Entries**: **300**
- **Files on Disk**: **300**
- **SHA-256 Mismatches**: **0**
- **Missing or Extra Entries**: **0**
- **Class / Split Metadata Parity**: **100% match**

---

## 12. `data.yaml` Configuration Validation

The configuration file `dataset/data.yaml` was parsed and validated:

```yaml
path: C:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/dataset

train: images/train
val: images/val
test: images/test

nc: 3

names:
  0: open_damaged_manhole
  1: damaged_missing_road_sign
  2: road_waterlogging
```

- Canonical root path uses standard forward slashes.
- Relative split paths (`images/train`, `images/val`, `images/test`) resolve correctly.
- Number of classes (`nc: 3`) matches length of `names`.
- Class names and indices match ontology perfectly.

---

## 13. Upstream Source Integrity Verification

Original source and staging directories were audited for accidental modifications:

| Directory Path | Expected Count | Current Count | Status |
|---|---|---|---|
| `dataset_source/Manhole/images` | 100 | 100 | **Untouched** |
| `dataset_source/DamagedSign/images` | 100 | 100 | **Untouched** |
| `dataset_source/waterlogging/images` | 100 | 100 | **Untouched** |
| `prepared_sources/manhole_cvki/images` | 100 | 100 | **Untouched** |
| `prepared_sources/road_sign_cvki/images` | 99 | 99 | **Untouched** |
| `prepared_sources/waterlogging_cvki/images` | 94 | 94 | **Untouched** |
| `replacement_sources/road_sign_replacement/images` | 1 | 1 | **Untouched** |
| `replacement_sources/waterlogging_replacement/images` | 6 | 6 | **Untouched** |

Zero files were added, deleted, renamed, or modified in any upstream directory.

---

## 14. Reproducibility Confirmation

The entire split process is recorded with:
- **Deterministic Random Seed**: `42`
- **Algorithm**: Group-Aware Stratified Partitioning
- **Reproducibility**: 100% reproducible via `dataset_manifest.json` and split metadata.

---

## 15. Problems Found

**Zero critical or non-critical defects found.**
- Corrupt images: 0
- Malformed labels: 0
- Out-of-bounds coordinates: 0
- Orphan files: 0
- Duplicate leakage: 0
- Scene leakage: 0

---

## 16. Final Recommendation

The dataset at `ai/computer_vision/dataset/` has achieved a perfect QA score across all verification vectors. It is fully certified, standardized, and immediately ready for model training in Milestone M1.7.

**FINAL STATUS: M1.6 STATUS: PASS**
