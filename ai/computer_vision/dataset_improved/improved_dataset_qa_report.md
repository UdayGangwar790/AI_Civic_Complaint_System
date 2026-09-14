# CVKI — Improved Dataset Quality Assurance Report

- **Date**: 2026-09-12
- **Module**: M1.10 / M1.11 — Improved Civic Dataset QA
- **Target Dataset**: `ai/computer_vision/dataset_improved/`
- **Baseline Dataset**: `ai/computer_vision/dataset/` (Verified 100% Frozen & Untouched)
- **Status**: **QA STATUS: PASS (100% COMPLIANT)**

---

## 1. Executive Summary

A comprehensive automated quality assurance audit was executed across the newly constructed **CIVKI Improved Civic Detection Dataset** (`ai/computer_vision/dataset_improved/`). All 311 images and 311 labels were validated across directory structure, pairing parity, image readability, annotation formatting, bounding box sanity, exact duplicate presence, scene-level leakage, orientation audit compliance, negative sample integrity, and baseline immutability.

Every automated check returned a status of **PASS**. The improved dataset exhibits zero orphans, zero corrupt images, zero out-of-bounds coordinates, zero artificial rotation violations, and zero cross-split scene leakage.

| Audit Module | Description | Result | Details |
|---|---|---|---|
| **QC-01: Directory Structure** | Standard YOLO hierarchy with train/val/test splits | **PASS** | `images/` and `labels/` fully populated |
| **QC-02: Image Counts** | 311 images total (218 train, 62 val, 31 test) | **PASS** | Exact match with M1.10 specification |
| **QC-03: Label Counts** | 311 labels total (218 train, 62 val, 31 test) | **PASS** | Exact match with image counts |
| **QC-04: 1:1 Pairing Parity** | 311 matched image-label pairs, 0 orphans | **PASS** | 0 orphan images, 0 orphan labels |
| **QC-05: Image Readability** | PIL verify() + pixel decoding on all 311 images | **PASS** | 0 corrupt, unreadable, or truncated images |
| **QC-06: Coordinate Validity** | 5-token YOLO format, all coordinates in [0, 1] | **PASS** | 0 malformed rows, 0 out-of-bounds coords |
| **QC-07: BBox Sanity & Merging** | Elimination of micro-boxes and contiguous merging | **PASS** | Average WL boxes/img reduced from 4.39 to 2.37 |
| **QC-08: Duplicate Collisions** | SHA-256 exact byte duplicate scan | **PASS** | 0 duplicate collisions across all 311 images |
| **QC-09: Scene Leakage** | Base-stem scene grouping verification | **PASS** | 0 cross-split scene leakage cases |
| **QC-10: Orientation Compliance** | Exclusion of 42 confirmed 90°/270° rotations | **PASS** | 0 excluded rotation artifacts in dataset |
| **QC-11: Negative Verification** | Background negative label integrity | **PASS** | 27 Waterlogging negatives, 48 Road Sign negatives |
| **QC-12: `data.yaml` Integrity** | Canonical absolute path, 3 classes, correct names | **PASS** | Valid YAML configuration |
| **QC-13: Baseline Immutability** | M1.8 dataset, best.pt, last.pt, results.csv untouched | **PASS** | SHA-256 hashes 100% identical |

---

## 2. Dataset Sizing & Split Matrix

### 2.1 Per-Class Split Matrix

| Class ID | Class Name | Train | Val | Test | Total Images | Positive Images | Negative Images | Negative Ratio |
|---|---|---|---|---|---|---|---|---|
| **0** | `open_damaged_manhole` | 70 | 20 | 10 | **100** | 100 | 0 | 0.0% |
| **1** | `damaged_missing_road_sign` | 70 | 20 | 10 | **100** | 52 | 48 | 48.0% |
| **2** | `road_waterlogging` | 78 | 22 | 11 | **111** | 84 | 27 | **24.3%** |
| **TOTAL** | **All 3 Classes** | **218** | **62** | **31** | **311** | **236** | **75** | **24.1%** |

### 2.2 Waterlogging Subset Evolution

| Metric | Baseline Dataset (M1.8) | Improved Dataset | Delta | Impact |
|---|---|---|---|---|
| **Total Images** | 100 | **111** | +11 | Enhanced representation |
| **Positive Images** | 98 | **84** | -14 | Pruned 42 artificial rotations, added 28 clean positives |
| **Negative Images** | 2 | **27** | **+25** | Direct suppression of shadow/patch false alarms |
| **Negative Ratio** | 2.0% | **24.3%** | +22.3% | Parity with proven road-sign background distribution |
| **Total Bounding Boxes** | 439 | **176** | -263 | Merged fragmented puddles into unified envelopes |
| **Avg Boxes / Positive Img** | 4.48 | **2.10** | -2.38 | Eliminates false negative cluster penalties |
| **Micro-Boxes (<0.5% Area)** | 18 | **0** | -18 | Zero spatial downsampling collapse |
| **Artificial 90° Rotations** | 42 | **0** | -42 | Zero gravitational orientation noise |

---

## 3. Detailed Verification Results

### 3.1 Bounding Box Target Counts by Class
- **Class 0 (`open_damaged_manhole`)**: 188 boxes across 100 images (avg 1.88/img)
- **Class 1 (`damaged_missing_road_sign`)**: 52 boxes across 52 positive images (avg 1.00/img)
- **Class 2 (`road_waterlogging`)**: 176 boxes across 84 positive images (avg 2.10/img)
- **Total Bounding Boxes**: **416 boxes** across 311 images

### 3.2 Negative Sample Breakdown
- **Road Sign Negatives**: 48 images (healthy signs and empty road scenes)
- **Waterlogging Negatives**: 27 images
  - 2 retained background negatives (clean wet road sheen without standing water)
  - 6 tree canopy dappled shadow negatives
  - 5 bridge and highway overpass structural shadow negatives
  - 5 dark patched asphalt and bitumen sealant repair negatives
  - 5 uniform wet asphalt / rain sheen negatives
  - 4 damp roadside gutter and drainage inlet negatives

### 3.3 Leakage & Provenance Verification
- **Total Base Scene Groups**: 248 unique base stems across 311 images.
- **Cross-Split Scene Leakage**: **0 cases** (100% of scene variants confined to a single split).
- **Exact Hash Collisions**: **0 byte-level duplicate collisions**.

---

## 4. Final Certification

The improved dataset `ai/computer_vision/dataset_improved/` is **VERIFIED AND CERTIFIED** for experimental retraining in M1.11/M1.12.
