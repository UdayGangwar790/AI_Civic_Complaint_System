# CVKI M1.4 — Waterlogging Dataset Preparation Report

- **Execution Timestamp**: `1789196614.3332033`
- **Module**: M1.4 — Isolated Waterlogging Dataset Preparation
- **Source Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\waterlogging`
- **Target Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\waterlogging_cvki`

---

## 1. Source Dataset Information & Audit Overview

- **Source Path**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\waterlogging`
- **Source Images**: 100 (all 512x384, RGB, grayscale CRT phosphor format)
- **Source Labels**: 100 (100% matched pairs)
- **Source Classes**:
  - Class `0`: `water` (453 annotations across 98 images)
  - Class `1`: `wet surface` (111 annotations across 49 images)
  - Total Source Annotations: 564

---

## 2. Visual Context Review & Classification (Task 3)

Every image was systematically reviewed for civic road/street context:

| Category | Classification Criteria | Image Count | Scene Groups Represented | Target Action |
|---|---|---|---|---|
| **A. Valid Road Waterlogging** | Clear stagnant/pooled water affecting asphalt, road, street, underpass, or roadway intersection. | **92** | 32 scenes | Mapped to target Class 0 (`road_waterlogging`). Removed Class 1 sheen. |
| **B. Negative / Not Road Waterlogging** | Contains zero stagnant water (0 Class 0); shows only wet asphalt sheen (Class 1). | **2** | 2 scenes (`waterloggingt-105`, `waterloggingt-128`) | Preserved as background negatives with empty label files. |
| **C. Ambiguous / Manual Review** | Natural shoreline/creek water or ambiguous non-road context in mosaic quadrant. | **6** | 2 scenes (`waterloggingt-118`, `waterloggingt-120`) | Quarantined to `manual_review/` without label fabrication. |
| **Total** | All source images accounted for | **100** | **34 unique scenes** | **100% complete** |

### Details of Quarantined Ambiguous Scenes:
1. **`waterloggingt-118-_jpg`** (3 images: `9f5101c9...`, `c6597fc1...`, `e8e2d340...`):
   - **Visual Content**: Shows natural shoreline / lake / riverbank with driftwood, mud banks, and mountain scenery. Lacks clear roadway or vehicular infrastructure.
   - **Annotations Quarantined**: 12 Class 0 ('water') + 2 Class 1 ('wet surface').
2. **`waterloggingt-120-_jpg`** (3 images: `7760ee1f...`, `87dd967a...`, `fc92afe5...`):
   - **Visual Content**: Contains a 2x2 mosaic where the top-right quadrant is a natural woodland creek/trail through a forest with trees submerged in water, rather than a paved road.
   - **Annotations Quarantined**: 15 Class 0 ('water') + 7 Class 1 ('wet surface').

---

## 3. Class Mapping & Conversion Summary (Task 4)

- **Target Class**: `0 = road_waterlogging`
- **Source Class 0 ('water')** on valid road images -> **Mapped to Target Class 0** (**426 bounding boxes**).
- **Source Class 1 ('wet surface')** -> **Excluded from positive annotations**:
  - **102 Class 1 annotations removed** (102 from valid positive images + 8 from negative images).
  - Rationale: Surface wetness sheen does not constitute civic roadway flooding or hazardous waterlogging.

---

## 4. Duplicate & Augmentation Scene-Group Analysis (Task 6)

- **Exact Image Duplicates (SHA-256)**: **0** across all 100 images.
- **Unique Base Scene Groups**: **34 unique scenes**.
- **Roboflow Augmentation Pattern**: 33 scenes possess 3 rotated variations each (90° rotations: 0°, 90°, 270° = 99 images) + 1 scene has 1 image (`waterloggingt-131`).
- **Leakage Prevention**: All scene groups are indexed in `provenance_manifest.json` to ensure that future train/val/test splits group by base stem rather than splitting rotated variants across splits.

---

## 5. Final Prepared Dataset Counts & Verification

| Metric | Count | Details |
|---|---|---|
| **Prepared Images** | **94** | 100% paired with labels |
| **Prepared Labels** | **94** | 100% paired with images |
| **Positive Images (Valid Road Waterlogging)** | **92** | Contain Class 0 target bounding boxes |
| **Negative Images (Background Negatives)** | **2** | Clean empty label files |
| **Manual Review Quarantined Images** | **6** | Stored in `manual_review/images/` |
| **Manual Review Quarantined Labels** | **6** | Stored in `manual_review/labels/` |
| **Target Bounding Boxes (Class 0)** | **426** | All Class 0 (`road_waterlogging`) |
| **Removed Class 1 Annotations** | **102** | Non-target wet surface annotations |
| **Corrupt / Unreadable Images** | **0** | Verified via PIL |
| **Malformed Label Rows** | **0** | Exactly 5 numeric tokens per row |
| **Invalid Class IDs** | **0** | Only Class 0 exists |

---

## 6. Bounding Box Statistics (Target Class 0: `road_waterlogging`)

- **Total Target Boxes**: 426
- **Average Boxes per Positive Image**: 4.63 (range: 1 to 10)
- **Box Width** (normalized & px on 512x384):
  - Minimum: `0.0215` (approx. 11.0 px)
  - Maximum: `0.7402` (approx. 379.0 px)
  - Average: `0.1881` (approx. 96.3 px)
- **Box Height** (normalized & px on 512x384):
  - Minimum: `0.0260` (approx. 10.0 px)
  - Maximum: `0.7891` (approx. 303.0 px)
  - Average: `0.2775` (approx. 106.5 px)

---

## 7. Source Integrity Confirmation

- **Source Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\waterlogging`
- **SHA-256 Pre/Post Verification**: **100% IDENTICAL** across all 100 images and 100 labels.
- **Confirmation**: Zero files were modified, moved, renamed, overwritten, or deleted in `dataset_source/waterlogging/`.

---

## 8. Recommendations & Stop Condition Analysis for M1.5

1. **Volume Status**: We have **92 verified positive road waterlogging images** in the active prepared set (and 2 verified negatives).
2. **Mosaic Characteristic**: The source images in this dataset are 2x2 collage mosaics created prior to Roboflow export. While bounding boxes accurately enclose pooled water on road surfaces, the model learns from multi-pane scenes.
3. **Sufficiency for M1.5**: With 92 positive images and 426 target bounding boxes across 32 distinct traffic scenes, the dataset provides strong representation for Class 2 (`road_waterlogging`).
4. **Split Grouping Rule**: In M1.5, train/val splits MUST be grouped by base scene stem to avoid data leakage from the 3x rotated variants.
