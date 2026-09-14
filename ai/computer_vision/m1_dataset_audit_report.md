# CVKI M1.1 — Dataset Audit Report

**Audit Execution Timestamp**: `2026-09-12T11:10:59.077182`  
**Project**: Civic Vision & Knowledge Intelligence (CVKI)  
**Stage**: M1.1 — Comprehensive Dataset Audit (Strictly Read-Only)  

---

## Executive Summary

| Dataset | Images | Labels | Matched Pairs | Orphans | Corrupt | Annotations | Polygons | Empty Labels | Classes Present |
|---|---|---|---|---|---|---|---|---|---|
| **DamagedSign** | 100 | 100 | 99 | 1 img, 1 lbl | 0 | 104 | 5 | 0 | 0: 51, 1: 53 |
| **Manhole** | 100 | 100 | 100 | 0 | 0 | 188 | 0 | 0 | 0: 188 |
| **waterlogging** | 100 | 100 | 100 | 0 | 0 | 564 | 0 | 0 | 0: 453, 1: 111 |
| **Active Total** | **300** | **300** | **299** | **2** | **0** | **856** | **5** | **0** | **-** |

---

## 1. Active Source Datasets Audit (`dataset_source/`)

### 1.1 Damaged Road Sign (`dataset_source/DamagedSign`)
- **Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\DamagedSign`
- **Total Images**: 100
- **Total Label Files**: 100
- **Matched Pairs**: 99
- **Orphaned Images (Images without Labels)**: 1
  - `IMG_8903_jpg.rf.617150b5aba1f59762738a5d40af8395.jpg`
- **Orphaned Labels (Labels without Images)**: 1
  - `IMG_8293_jpg.rf.86fbdf8b1834f50ea9081a439ab6fbf5.txt` (Annotation: Class 1 / Healthy sign)
- **Image Readability & Integrity**:
  - Corrupt / Unreadable Images: 0
  - Formats: `{'JPEG': 100}`
  - Color Modes: `{'RGB': 100}`
  - Dimensions: `{'640x640': 100}` (All images exactly 640x640)
- **Duplicates & Augmentations**:
  - Exact File Duplicates (SHA-256): 0
  - Unique Base Scenes: 92
  - Roboflow Augmentation Groups: 8 pairs of augmented variations (`IMG_8087`, `IMG_8106`, `IMG_8121`, `IMG_8128`, `IMG_8162`, `IMG_8669`, `IMG_8776`, `IMG_9029`)
- **Annotation Quality & Format**:
  - Total Annotation Rows: 104
  - Standard Detection BBoxes (5 tokens): 99
  - Polygon / Segmentation Annotations (>5 tokens): 5 (All 5 belong to Class 0 / Damaged signs)
    - `IMG_8702_jpg.rf.06c73635e3a4fe0e5f612862ae8144e5.txt` (line 1): class 0, 19 tokens (9 polygon vertices)
    - `IMG_8725_jpg.rf.1c6802aebb5d2ae4eb86a86edc09054b.txt` (line 1): class 0, 9 tokens (4 polygon vertices)
    - `IMG_8744_jpg.rf.a9c09cbdcc2b228f62aa9ee3fb7ff8ae.txt` (line 1): class 0, 21 tokens (10 polygon vertices)
    - `IMG_8783_jpg.rf.2bc6dd1455e2aecfbe58df0958e86b63.txt` (line 1): class 0, 11 tokens (5 polygon vertices)
    - `IMG_9029_jpg.rf.cfced0352f72a57dadb7c273c636d444.txt` (line 1): class 0, 9 tokens (4 polygon vertices)
  - Malformed Rows: 0
  - Empty Label Files: 0
  - Coordinates strictly < 0 or > 1: 0
  - BBox edge slight overshoot (float precision): 13 rows (max overshoot < 0.00001)
- **Class Distribution**:
  - Class 0 (Damaged signs): 51 annotations across 51 images (46 bbox + 5 polygon)
  - Class 1 (Healthy signs): 53 annotations across 49 images (all bbox)
  - Co-occurrence: 0 images contain both classes simultaneously

### 1.2 Open / Damaged Manhole (`dataset_source/Manhole`)
- **Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\Manhole`
- **Total Images**: 100
- **Total Label Files**: 100
- **Matched Pairs**: 100 (100% matched, `img-1` through `img-100`)
- **Orphaned Images / Labels**: 0
- **Image Readability & Integrity**:
  - Corrupt / Unreadable Images: 0
  - Formats: `{'JPEG': 100}`
  - Color Modes: `{'RGB': 100}`
  - Dimensions: `{'720x720': 100}` (All images exactly 720x720)
- **Duplicates & Augmentations**:
  - Exact File Duplicates (SHA-256): 0
  - Unique Base Scenes: 100
  - Roboflow Augmentations: None (independent real-world captures)
- **Annotation Quality & Format**:
  - Total Annotation Rows: 188
  - Standard Detection BBoxes (5 tokens): 188 (100%)
  - Polygon Annotations: 0
  - Malformed Rows: 0
  - Empty Label Files: 0
  - Coordinates strictly < 0 or > 1: 0
  - BBox edge slight overshoot (float precision): 3 rows (max overshoot < 0.000001)
- **Class Distribution**:
  - Class 0 (open_damaged_manhole): 188 annotations across 100 images
  - Multi-object frequency: Average 1.88 manholes/image (range: 1 to 8 manholes/image)

### 1.3 Waterlogging (`dataset_source/waterlogging`)
- **Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\waterlogging`
- **Total Images**: 100
- **Total Label Files**: 100
- **Matched Pairs**: 100 (100% matched)
- **Orphaned Images / Labels**: 0
- **Image Readability & Integrity**:
  - Corrupt / Unreadable Images: 0
  - Formats: `{'JPEG': 100}`
  - Color Modes: `{'RGB': 100}`
  - Dimensions: `{'512x384': 100}` (All images exactly 512x384)
- **Duplicates & Augmentations**:
  - Exact File Duplicates (SHA-256): 0
  - Unique Base Scenes: 34 unique scenes across 100 images
  - Roboflow 3x Augmentation: 33 scenes have 3 rotated versions each (99 files) + 1 scene has 1 version (1 file)
- **Annotation Quality & Format**:
  - Total Annotation Rows: 564
  - Standard Detection BBoxes (5 tokens): 564 (100%)
  - Polygon Annotations: 0
  - Malformed Rows: 0
  - Empty Label Files: 0
  - Coordinates strictly < 0 or > 1: 0
  - BBox edge overshoot: 0
- **Class Distribution**:
  - Class 0 ('water' / 'water_logging '): 453 annotations across 98 images
  - Class 1 ('wet surface' / 'water_logging'): 111 annotations across 49 images
  - Co-occurrence: 47 images contain both classes, 51 contain only Class 0, 2 contain only Class 1

---

## 2. Full Source Provenance & Split Analysis

### 2.1 Damaged Road Sign Full Source Dataset (`damaged signs Hind.v1i.yolov8`)
- **Source Provenance Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\road_sign_cvki\provenance\source_annotations`
- **`data.yaml` Metadata**:
  - `nc`: 2
  - `names`: `['Damaged signs', 'Healthy signs']` (0: 'Damaged signs', 1: 'Healthy signs')
  - Roboflow project: `damaged-signs-hind-vfpku`
- **Total Dataset Size**: 1,339 images/labels

| Split | Total Labels | Empty Labels | Class 0 (Damaged) | Class 1 (Healthy) | Total Annots | Polygons | BBoxes |
|---|---|---|---|---|---|---|---|
| **train** | 1070 | 17 | 640 | 450 | 1090 | 34 | 1056 |
| **valid** | 135 | 1 | 0 | 157 | 157 | 1 | 156 |
| **test** | 134 | 0 | 0 | 156 | 156 | 0 | 156 |
| **TOTAL** | **1339** | **18** | **640** | **763** | **1403** | **35** | **1368** |

> [!WARNING]
> **Critical Split Imbalance in Source Road-Sign Dataset**:
> In the original Roboflow export, the `valid` and `test` splits contain **ZERO instances of Class 0 (Damaged signs)**. All 640 damaged sign annotations are concentrated in the `train` split. Evaluation using the original Roboflow splits would yield 0 true positives for damaged signs. Re-stratification is essential before M1.2/M1.3 training.

- **Total Polygons across Full Road-Sign Dataset**: 35 (34 in train, 1 in valid, 0 in test)
- **Total Empty Labels across Full Road-Sign Dataset**: 18 (17 in train, 1 in valid, 0 in test)

### 2.2 Waterlogging Full Source Dataset (`water logging.v1i.yolov8`)
- **Source Directory**: `C:\Users\sushm\Downloads\water logging.v1i.yolov8`
- **`data.yaml` Metadata**:
  - `nc`: 2
  - `names`: `['water_logging ', 'water_logging']`
- **Total Exported Images**: 535 images (504 train, 31 valid) with 3x rotation augmentations (1,605 augmented images)
- **Annotation Breakdown in Full Export**:
  - **train**: 504 labels, 2713 annotations (Class 0: 2129, Class 1: 584), 0 polygons, 0 empty labels
  - **valid**: 31 labels, 68 annotations (Class 0: 68, Class 1: 0), 0 polygons, 0 empty labels

---

## 3. Cross-Dataset Duplicate & Overlap Analysis

- **Exact Cross-Dataset SHA-256 Duplicates**: 0
- **Conclusion**: Zero images are shared across DamagedSign, Manhole, and waterlogging. The three source domains are completely disjoint.

---

## 4. Semantic & Content Observations

1. **CVKI Target Class Mapping vs Source Classes**:
   - **CVKI Class 0 (`open_damaged_manhole`)**: Source Manhole dataset has 100 images with 188 annotations, all cleanly labeled as class 0. Ready for direct target class mapping.
   - **CVKI Class 1 (`damaged_missing_road_sign`)**: Source DamagedSign has two classes: 0 = 'Damaged signs' and 1 = 'Healthy signs'. Only source Class 0 represents our target CVKI class. Healthy signs (Class 1) must be handled deliberately (either as background negatives or excluded) in M1.2.
   - **CVKI Class 2 (`road_waterlogging`)**: Source waterlogging dataset has two classes: Class 0 ('water') and Class 1 ('wet surface'). Both are road water-related in this urban capture context, but Class 0 is actual standing water/waterlogging whereas Class 1 is wet pavement sheen.
2. **Polygon Format Conversion Required in M1.2**:
   - 5 annotations in active DamagedSign (and 35 in full road-sign) are polygon segmentation format (>5 tokens). YOLO object detection models require 5-token bounding boxes `[class, x_center, y_center, width, height]`. These polygons must be converted to bounding-box envelopes in M1.2 before training.
3. **Active Subset vs Full Source Volume**:
   - Currently, `dataset_source/` contains an exploratory sample of 100 images for DamagedSign, 100 images for Manhole, and 100 images for waterlogging.
   - Full source data exists for DamagedSign (1,339 images) and waterlogging (535 images / 1,605 augmented).

---

## 5. Overall M1 Readiness Assessment

### Strengths:
- 100% image readability across all datasets (zero corrupt or unreadable files).
- Consistent resolutions per dataset (640x640 for DamagedSign, 720x720 for Manhole, 512x384 for waterlogging).
- Zero malformed text rows or unparseable tokens in active labels.
- Disjoint source domains with zero cross-contamination.

### Issues to Address in M1.2 (Preparation & Cleaning):
1. **DamagedSign File Pair Mismatch**: Resolve orphaned image (`IMG_8903`) and orphaned label (`IMG_8293`).
2. **DamagedSign Polygons**: Convert the 5 polygon annotations to standard bounding boxes.
3. **Road Sign Class Filtering / Re-mapping**: Map source class 0 ('Damaged signs') -> CVKI Class 1 (`damaged_missing_road_sign`), and decide policy for source class 1 ('Healthy signs').
4. **Road Sign Split Re-stratification**: If expanding to full 1,339 source images, re-split so that valid and test sets have balanced damaged signs.
5. **Waterlogging Augmentation & Split Strategy**: 100 active waterlogging images represent 34 base scenes with 3x rotation variations. Train/val splitting must be scene-aware (grouped by base stem) to avoid data leakage.
6. **Manhole Class Re-mapping**: Source class 0 -> CVKI Class 0 (`open_damaged_manhole`).

> [!IMPORTANT]
> **M1.1 Status**: AUDIT COMPLETE. No files were modified, moved, deleted, or converted. Awaiting user approval before proceeding to M1.2.
