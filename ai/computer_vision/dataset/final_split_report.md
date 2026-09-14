# CVKI M1.5C — Final Dataset Merge & 70/20/10 Split Report

- **Execution Date**: 2026-09-12
- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Module**: M1.5C — Final Dataset Merge & Group-Aware Split
- **Random Seed**: 42
- **Status**: **PASS — 100% COMPLETE & VERIFIED**

---

## 1. Final Dataset Summary

The final 3-class CVKI YOLO object detection dataset has been assembled and partitioned into a group-aware, leakage-free 70/20/10 split.

| Metric | Target | Final Count | Status |
|---|---|---|---|
| **Total Images** | 300 | **300** | **100% MATCH** |
| **Total Labels** | 300 | **300** | **100% MATCH** |
| **Train Set** | 210 (70%) | **210 (70.0%)** | **EXACT MATCH** |
| **Validation Set** | 60 (20%) | **60 (20.0%)** | **EXACT MATCH** |
| **Test Set** | 30 (10%) | **30 (10.0%)** | **EXACT MATCH** |
| **Total Target Bounding Boxes** | N/A | **679** | **100% Valid YOLO** |
| **Orphan Files** | 0 | **0** | **Clean 1:1 Pairing** |
| **Corrupt Files** | 0 | **0** | **100% Readability** |
| **Scene Group Leakage** | 0 | **0** | **ZERO LEAKAGE** |

---

## 2. Source & Replacement Contribution

| Class Name | Class ID | Approved Prepared Source | Replacement Staging | Final Total Images | Total Bounding Boxes |
|---|---|---|---|---|---|
| `open_damaged_manhole` | 0 | 100 (`prepared_sources/manhole_cvki`) | 0 | **100** | 188 |
| `damaged_missing_road_sign` | 1 | 99 (`prepared_sources/road_sign_cvki`) | 1 (`replacement_sources/road_sign_replacement`) | **100** | 52 |
| `road_waterlogging` | 2 | 94 (`prepared_sources/waterlogging_cvki`) | 6 (`replacement_sources/waterlogging_replacement`) | **100** | 439 |
| **Total** | **All 3** | **293** | **7** | **300** | **679** |

### Replacement Details:
- **Road Sign Replacement (1 image)**:
  - Original File: `IMG_8655_jpg.rf.45544adfcdd97c94f9db3407648a52a1.jpg`
  - Final File: `roadsign_IMG_8655_jpg.rf.45544adfcdd97c94f9db3407648a52a1.jpg`
  - Bounding Box: `1 0.529328125 0.499828125 0.728296875 0.80321875` (remapped to Class 1)
  - Split: `train`
- **Waterlogging Replacements (6 images)**:
  - `waterlogging_waterloggingt-10-_jpg.rf.6907c533b135a400dc53b46585bb1ed4.jpg` (2 boxes) -> `val`
  - `waterlogging_waterloggingt-101-_jpg.rf.8e414c06e616a1356b33962850a7a4f6.jpg` (3 boxes) -> `train`
  - `waterlogging_waterloggingt-123-_jpg.rf.caafec34b2c9f23b90ebaa43223ffb59.jpg` (3 boxes) -> `train`
  - `waterlogging_waterloggingt-124-_jpg.rf.db98b0141ebde1e782c5ae2ba94df6b7.jpg` (1 box) -> `train`
  - `waterlogging_waterloggingt-145-_jpg.rf.c3dabb8c32e8535b5bec3381d1f18c86.jpg` (2 boxes) -> `test`
  - `waterlogging_waterloggingt-31-_jpg.rf.3856f69d93858c8e57d49bfead20d9d9.jpg` (2 boxes) -> `val`

---

## 3. Split Distribution Matrix

### 3.1 Images Per Class Across Splits

| Class Name | Class ID | Train (70%) | Val (20%) | Test (10%) | Total Images | Positive Images | Negative Images |
|---|---|---|---|---|---|---|---|
| `open_damaged_manhole` | 0 | 70 | 20 | 10 | **100** | 100 | 0 |
| `damaged_missing_road_sign` | 1 | 70 | 20 | 10 | **100** | 52 | 48 |
| `road_waterlogging` | 2 | 70 | 20 | 10 | **100** | 98 | 2 |
| **Total Images** | - | **210** | **60** | **30** | **300** | **250** | **50** |

### 3.2 Bounding Boxes Per Class Across Splits

| Class Name | Class ID | Train Boxes | Val Boxes | Test Boxes | Total Boxes |
|---|---|---|---|---|---|
| `open_damaged_manhole` | 0 | 129 | 37 | 22 | **188** |
| `damaged_missing_road_sign` | 1 | 36 | 11 | 5 | **52** |
| `road_waterlogging` | 2 | 312 | 81 | 46 | **439** |
| **Total Annotations** | - | **477** | **129** | **73** | **679** |

---

## 4. Class ID Remapping Verification

All source annotations were deterministically remapped to the unified 3-class CVKI ontology:

| Source Domain | Source Class ID | Final Class ID | Final Class Name | Transformation Rule |
|---|---|---|---|---|
| Manhole | 0 | **0** | `open_damaged_manhole` | `0 -> 0` |
| Road Sign | 0 | **1** | `damaged_missing_road_sign` | `0 -> 1` |
| Road Sign | 1 (healthy) | None | Background Negative | Retained as empty `.txt` label |
| Waterlogging | 0 | **2** | `road_waterlogging` | `0 -> 2` |
| Waterlogging | 1 (sheen) | None | Excluded | Removed from target labels |

> [!IMPORTANT]
> **Strict Verification**: Every single non-empty label row in the final dataset contains exclusively class `0`, `1`, or `2`. No source class `1` from road signs or waterlogging leaked into positive labels.

---

## 5. Waterlogging Scene-Group Leakage Prevention

Waterlogging contains 38 distinct base scenes:
- 31 base scenes with 3 rotation variants (0°, 90°, 270°) = 93 images
- 7 base scenes with 1 image = 7 images
- Total = 100 images.

### Mathematical Partitioning:
- **Train (70 images)**: 22 scenes of 3 images (66 images) + 4 scenes of 1 image (4 images) = **70 images**
- **Val (20 images)**: 6 scenes of 3 images (18 images) + 2 scenes of 1 image (2 images) = **20 images**
- **Test (10 images)**: 3 scenes of 3 images (9 images) + 1 scene of 1 image (1 image) = **10 images**
- **Total**: (22+6+3 = 31 scenes of 3) + (4+2+1 = 7 scenes of 1) = **38 scenes (100 images)**.

### Scene Assignment Roster:
- **Train Scenes (26 scenes, 70 images)**:
  `waterloggingt-1-_jpg`, `waterloggingt-100-_jpg`, `waterloggingt-101-_jpg`, `waterloggingt-105-_jpg`, `waterloggingt-106-_jpg`, `waterloggingt-107-_jpg`, `waterloggingt-108-_jpg`, `waterloggingt-109-_jpg`, `waterloggingt-11-_jpg`, `waterloggingt-110-_jpg`, `waterloggingt-111-_jpg`, `waterloggingt-112-_jpg`, `waterloggingt-113-_jpg`, `waterloggingt-114-_jpg`, `waterloggingt-115-_jpg`, `waterloggingt-116-_jpg`, `waterloggingt-12-_jpg`, `waterloggingt-121-_jpg`, `waterloggingt-123-_jpg`, `waterloggingt-124-_jpg`, `waterloggingt-125-_jpg`, `waterloggingt-127-_jpg`, `waterloggingt-129-_jpg`, `waterloggingt-13-_jpg`, `waterloggingt-131-_jpg`, `waterloggingt-14-_jpg`
- **Val Scenes (8 scenes, 20 images)**:
  `waterloggingt-10-_jpg`, `waterloggingt-102-_jpg`, `waterloggingt-117-_jpg`, `waterloggingt-119-_jpg`, `waterloggingt-122-_jpg`, `waterloggingt-128-_jpg`, `waterloggingt-130-_jpg`, `waterloggingt-31-_jpg`
- **Test Scenes (4 scenes, 10 images)**:
  `waterloggingt-103-_jpg`, `waterloggingt-104-_jpg`, `waterloggingt-126-_jpg`, `waterloggingt-145-_jpg`

> [!NOTE]
> **Leakage Check**: Intersection of Train, Val, and Test scene sets is **strictly EMPTY (0 leaking scenes)**. Every scene group is 100% contained within a single split.

---

## 6. Road Sign & Manhole Group Integrity

### Road Sign:
- 8 Roboflow multi-image base scenes (2 variants each) were assigned atomically:
  - `train`: `IMG_8087`, `IMG_8106`, `IMG_8121`, `IMG_8128`, `IMG_8162`, `IMG_8669`, `IMG_8776`, `IMG_9029`
  - `val`: None (multi-image scenes kept in train to satisfy quota balance)
  - `test`: None
- All 84 single-image scenes distributed deterministically with seed 42.

### Manhole:
- All 100 images represent independent real-world captures (0 duplicates).
- Stratified by bounding box density:
  - Single-object: 30 train, 9 val, 4 test = 43 images
  - Multi-object: 40 train, 11 val, 6 test = 57 images

---

## 7. Automated QA Checklist

- [x] **300 images total** in `dataset/images/`
- [x] **300 label files total** in `dataset/labels/`
- [x] **210 train images / 210 train labels**
- [x] **60 val images / 60 val labels**
- [x] **30 test images / 30 test labels**
- [x] **100 Manhole images (70 train / 20 val / 10 test)**
- [x] **100 Road Sign images (70 train / 20 val / 10 test)**
- [x] **100 Waterlogging images (70 train / 20 val / 10 test)**
- [x] **Correct final class IDs (0, 1, 2 only)**
- [x] **100% 1:1 image-label stem matching**
- [x] **Zero corrupt or unreadable images (PIL verified)**
- [x] **Zero malformed label rows (all exactly 5 numeric tokens)**
- [x] **Zero coordinates out of [0, 1] range; width > 0, height > 0**
- [x] **Zero exact duplicate leakage (SHA-256 verified)**
- [x] **Zero waterlogging scene-group leakage**
- [x] **Source datasets remain 100% untouched**
- [x] **Manual-review files excluded**
- [x] **Orphan files excluded**
- [x] **Replacements correctly included (1 road sign, 6 waterlogging)**
- [x] **`data.yaml` correctly configured**
- [x] **`dataset_manifest.json` generated with full provenance**
- [x] **Split reproducible with seed 42**
- [x] **Zero YOLO training executed**

---

## 8. Status Conclusion

**FINAL STATUS: PASS**

The final CVKI dataset is fully assembled, verified, and ready for model training in M1.6.
