# CVKI M1.5 — Final Dataset Selection & Split Planning Report

- **Date**: 2026-09-12
- **Module**: M1.5 — Final Dataset Selection & Split Planning
- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Status**: **BLOCKED — SHORTAGE DETECTED / READY FOR USER APPROVAL**

---

## 1. Target Counts vs Available Approved Inventory

| Class ID | Target Class Name | Original Desired Target | Available Approved Count | Net Shortage | Replacement Required | Status |
|---|---|---|---|---|---|---|
| **0** | `open_damaged_manhole` | 100 | **100** | 0 | 0 | **Fully Met (100%)** |
| **1** | `damaged_missing_road_sign` | 100 | **99** | 1 | **1** | **Shortage (1 file)** |
| **2** | `road_waterlogging` | 100 | **94** | 6 | **6** | **Shortage (6 files)** |
| **Total** | **All 3 Classes** | **300** | **293** | **7** | **7** | **Shortage: 7 Images** |

---

## 2. Prepared Sources Inventory & Class Balance

Every prepared source directory was systematically verified for images, labels, positive detections, background negatives, and annotation density.

```
ai/computer_vision/prepared_sources/
├── manhole_cvki/      --> 100 images, 100 labels,   0 manual review
├── road_sign_cvki/    -->  99 images,  99 labels,   1 orphan img, 1 orphan lbl in manual review
└── waterlogging_cvki/ -->  94 images,  94 labels,   6 ambiguous images in manual review
```

### Detailed Balance Matrix

| Metric | `manhole_cvki` | `road_sign_cvki` | `waterlogging_cvki` | Combined Approved Total |
|---|---|---|---|---|
| **Total Images** | 100 | 99 | 94 | **293** |
| **Total Labels** | 100 | 99 | 94 | **293** |
| **Positive Images** | 100 (100%) | 51 (51.5%) | 92 (97.9%) | **243 (82.9%)** |
| **Negative Images** | 0 (0.0%) | 48 (48.5%) | 2 (2.1%) | **50 (17.1%)** |
| **Total Target Annotations** | 188 | 51 | 426 | **665** |
| **Images with 0 Annotations** | 0 | 48 (healthy signs) | 2 (sheen-only) | **50** |
| **Images with 1 Annotation** | 43 | 51 | 0 | **94** |
| **Images with >1 Annotations** | 57 | 0 | 92 | **149** |
| **Average Boxes per Pos Image** | 1.88 | 1.00 | 4.63 | **2.74** |
| **Unique Base Scenes** | 100 | 91 | 32 | **223** |
| **Exact Duplicates (SHA-256)** | 0 | 0 | 0 | **0** |
| **Manual Review Quarantined** | 0 | 1 img, 1 lbl | 6 imgs, 6 lbls | **7 imgs, 7 lbls** |

> [!NOTE]
> **Negative Examples Policy**:
> - In `road_sign_cvki`, the 48 negative images represent healthy road signs. Keeping these as background negatives prevents false-positive detections on regular traffic signs.
> - In `waterlogging_cvki`, the 2 negative images represent wet asphalt sheen without pooled water. Keeping them prevents false-positive alerts on damp roads.
> - Negative examples are preserved with clean empty label files in accordance with YOLO best practices.

---

## 3. Road Sign 100th Image Investigation

- **Missing Item**: 1 image needed to reach 100.
- **Quarantined Files in `manual_review/`**:
  1. Orphan image: `IMG_8903_jpg.rf.617150b5aba1f59762738a5d40af8395.jpg` (no corresponding label in source)
  2. Orphan label: `IMG_8293_jpg.rf.86fbdf8b1834f50ea9081a439ab6fbf5.txt` (no corresponding image in source)
- **Pairing Rule**: Under CVKI zero-fabrication rules, these disparate stems cannot be paired.
- **Source Search**:
  - `dataset_source/DamagedSign` contains exactly 100 images and 100 labels (99 matched pairs + 1 orphan image + 1 orphan label).
  - No additional approved, unused, properly matched road-sign image exists in the project provenance.
- **Result**:
  ```
  ROAD SIGN REPLACEMENT REQUIRED = 1
  ```
  *No unverified replacement was imported or fabricated.*

---

## 4. Waterlogging Shortage Investigation

- **Missing Items**: 6 images needed to reach 100 (current approved count is 94: 92 positive, 2 negative).
- **Quarantined Files in `manual_review/`**:
  - 6 images (2 base scenes x 3 rotation variants):
    1. `waterloggingt-118-_jpg` (3 images: `9f5101c9...`, `c6597fc1...`, `e8e2d340...`):
       - Visual Context: Natural lake/river shoreline, mud banks, driftwood, mountain background. Zero civic roadway or vehicular infrastructure.
    2. `waterloggingt-120-_jpg` (3 images: `7760ee1f...`, `87dd967a...`, `fc92afe5...`):
       - Visual Context: 2x2 collage where the water quadrant is a woodland hiking trail/forest creek, not a public paved roadway.
- **Quarantine Rule**: Quarantined files must NOT be forced into the training dataset merely to satisfy the arbitrary 100-count round number.
- **Source Search**:
  - `dataset_source/waterlogging` contains exactly 100 images and 100 labels. All 100 images were evaluated during M1.4.
  - Exactly 94 were approved (92 positive, 2 negative) and 6 were quarantined.
  - No additional approved images exist in the project source.
- **Result**:
  ```
  WATERLOGGING REPLACEMENT REQUIRED = 6
  ```
  *No unverified external data was imported or fabricated.*

---

## 5. Shortage Decision & Stop Condition

In strict accordance with project directives:
- **DO NOT force 300 images.**
- **DO NOT fabricate images or labels.**
- **DO NOT pull unverified external data.**
- **DO NOT modify the final dataset directory until user approval.**

### Shortage Breakdown Summary
```
Target:             300
Currently Approved: 293
Net Shortage:         7

Breakdown:
- Manhole:          0
- Road Sign:        1
- Waterlogging:     6
```

---

## 6. Duplicate & Scene-Group Analysis

### 6.1 Manhole (`manhole_cvki`)
- **Total images**: 100
- **Exact Duplicates (SHA-256)**: 0
- **Near-Duplicates (dHash Hamming distance <= 10)**: 0
- **Conclusion**: 100 distinct, independent real-world captures.

### 6.2 Damaged Road Sign (`road_sign_cvki`)
- **Total images**: 99
- **Unique Base Scenes**: 91
- **Multi-Image Base Scenes (2 augmented variants each)**: 8 scenes (16 images total)
  - 3 Positive Scenes: `IMG_8669`, `IMG_8776`, `IMG_9029` (6 images)
  - 5 Negative Scenes: `IMG_8087`, `IMG_8106`, `IMG_8121`, `IMG_8128`, `IMG_8162` (10 images)
- **Single-Image Base Scenes**: 83 scenes (83 images: 45 positive, 38 negative)
- **Leakage Constraint**: All variants belonging to each of these 8 base scenes must be assigned atomically to the same split.

### 6.3 Road Waterlogging (`waterlogging_cvki`)
- **Total approved images**: 94
- **Unique Approved Base Scenes**: 32
- **Multi-Image Base Scenes (3 rotation variants: 0°, 90°, 270°)**: 31 scenes (93 images)
  - 29 Pure Positive Scenes (87 images)
  - 2 Mixed Scenes with 2 positive + 1 negative rotation: `waterloggingt-105-_jpg`, `waterloggingt-128-_jpg` (6 images)
- **Single-Image Base Scenes**: 1 scene (`waterloggingt-131-_jpg`, 1 positive image)
- **Leakage Constraint**: Splitting must occur at the **scene-group level**. No base scene group may span across multiple splits.

---

## 7. Split Planning (70 / 20 / 10)

### 7.1 Target Split Design (Ideal 300 Images — Once 7 Replacements Approved)

If 1 replacement road sign and 6 replacement waterlogging images (e.g. 2 scenes of 3) are provided:

| Class | Train (70%) | Val (20%) | Test (10%) | Total |
|---|---|---|---|---|
| **Manhole** | 70 | 20 | 10 | 100 |
| **Road Sign** | 70 (35 pos / 35 neg) | 20 (10 pos / 10 neg) | 10 (6 pos / 4 neg) | 100 |
| **Waterlogging** | 70 (23 scenes x 3 + 1 scene x 1) | 20 (~7 scenes) | 10 (~3 scenes) | 100 |
| **Total** | **210** | **60** | **30** | **300** |

---

### 7.2 Proposed Concrete Split for Currently Approved Dataset (293 Images)

Deterministic Seed: `20260912`.

| Split | Manhole (Pos/Neg) | Road Sign (Pos/Neg) | Waterlogging (Pos/Neg) | Total Images | Positive Imgs | Negative Imgs | Total Annotations |
|---|---|---|---|---|---|---|---|
| **Train** | 70 (70 / 0) | 69 (36 / 33) | 66 (65 / 1) | **205 (70.0%)** | 171 | 34 | **462** |
| **Val** | 20 (20 / 0) | 20 (10 / 10) | 19 (18 / 1) | **59 (20.1%)** | 48 | 11 | **127** |
| **Test** | 10 (10 / 0) | 10 (5 / 5) | 9 (9 / 0) | **29 (9.9%)** | 24 | 5 | **76** |
| **Total** | **100 (100 / 0)** | **99 (51 / 48)** | **94 (92 / 2)** | **293 (100%)** | **243** | **50** | **665** |

### 7.3 Scene Group Assignments for Currently Approved 293 Images

#### Waterlogging Scene Assignments (32 Scenes, 94 Images)
- **Train (22 scenes = 66 images)**:
  `waterloggingt-105-_jpg` (mixed: 2 pos, 1 neg), `waterloggingt-116-_jpg`, `waterloggingt-13-_jpg`, `waterloggingt-110-_jpg`, `waterloggingt-127-_jpg`, `waterloggingt-104-_jpg`, `waterloggingt-114-_jpg`, `waterloggingt-117-_jpg`, `waterloggingt-106-_jpg`, `waterloggingt-14-_jpg`, `waterloggingt-112-_jpg`, `waterloggingt-126-_jpg`, `waterloggingt-11-_jpg`, `waterloggingt-111-_jpg`, `waterloggingt-109-_jpg`, `waterloggingt-108-_jpg`, `waterloggingt-121-_jpg`, `waterloggingt-130-_jpg`, `waterloggingt-129-_jpg`, `waterloggingt-102-_jpg`, `waterloggingt-115-_jpg`, `waterloggingt-125-_jpg`
- **Val (7 scenes = 19 images)**:
  `waterloggingt-128-_jpg` (mixed: 2 pos, 1 neg), `waterloggingt-131-_jpg` (single: 1 pos), `waterloggingt-119-_jpg`, `waterloggingt-12-_jpg`, `waterloggingt-1-_jpg`, `waterloggingt-103-_jpg`, `waterloggingt-107-_jpg`
- **Test (3 scenes = 9 images)**:
  `waterloggingt-113-_jpg`, `waterloggingt-122-_jpg`, `waterloggingt-100-_jpg`

#### Road Sign Multi-Image Scene Assignments (8 Scenes, 16 Images)
- **Train**: `IMG_8776` (2 pos), `IMG_9029` (2 pos), `IMG_8669` (2 pos), `IMG_8162` (2 neg), `IMG_8128` (2 neg), `IMG_8087` (2 neg), `IMG_8106` (2 neg)
- **Val**: None (multi-image scenes kept in Train and Test to balance quotas)
- **Test**: `IMG_8121` (2 neg)
*(All 83 single-image scenes are distributed cleanly to hit exactly 69 train / 20 val / 10 test).*

#### Manhole Stratification (100 Images)
- Stratified by density to ensure balanced distribution of single-object (43 images) vs multi-object (57 images):
  - **Train**: 40 multi-object + 30 single-object = 70 images (128 boxes)
  - **Val**: 11 multi-object + 9 single-object = 20 images (38 boxes)
  - **Test**: 6 multi-object + 4 single-object = 10 images (22 boxes)

---

## 8. Leakage-Prevention Summary

1. **Scene Isolation**: Rotation and augmentation variants from the same base capture are NEVER partitioned across train/val/test splits.
2. **Negative Stratification**: Background negative images (healthy signs and wet sheen) are balanced across splits to prevent train/val domain shifts.
3. **Density Balance**: Dense multi-object scenes are distributed proportionally to prevent difficulty bias between validation and test sets.
4. **Disjoint Source Verification**: All SHA-256 hashes cross-verified; zero cross-dataset image overlap exists.

---

## 9. Final Dataset Directory & YOLO Status

- **`ai/computer_vision/dataset/`**: **UNMODIFIED & EMPTY**.
  - `dataset/images/train/`: empty (0 files)
  - `dataset/images/val/`: empty (0 files)
  - `dataset/images/test/`: empty (0 files)
  - `dataset/labels/train/`: empty (0 files)
  - `dataset/labels/val/`: empty (0 files)
  - `dataset/labels/test/`: empty (0 files)
- **YOLO Training**: **NOT PERFORMED**.

---

## 10. Final Recommendation & Next Actions

1. **Option A (Recommended — Proceed with Clean 293 Images)**:
   - Approve the 293-image dataset (100 Manhole, 99 Road Sign, 94 Waterlogging) with the proposed leakage-free split (205 Train / 59 Val / 29 Test).
   - This maintains 100% data integrity with zero fabrication and zero unverified images.
2. **Option B (Source 7 Verified Replacements Before Final Split)**:
   - Provide 1 verified positive road sign image/label and 6 verified civic road waterlogging images/labels (e.g. 2 traffic scenes x 3 rotations) to achieve the round 300-image target.
   - Run isolated preparation on the 7 replacements and incorporate them into the final split.

Awaiting user approval before proceeding to copy or split any files.
