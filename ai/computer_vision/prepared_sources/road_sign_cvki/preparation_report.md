# CVKI M1.3 — Damaged Road Sign Dataset Preparation Report

- **Execution Timestamp**: `1789192277.8525336`
- **Module**: M1.3 — Isolated Road Sign Dataset Preparation
- **Source Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\DamagedSign`
- **Target Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\road_sign_cvki`

---

## 1. Source Dataset Information & Initial Audit Counts

- **Active Source Path**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\DamagedSign`
- **Original Source Images**: 100
- **Original Source Labels**: 100
- **Matched Pairs in Source**: 99
- **Unmatched Orphan Files in Source**: 2
  - Orphaned Image (no label): `IMG_8903_jpg.rf.617150b5aba1f59762738a5d40af8395.jpg`
  - Orphaned Label (no image): `IMG_8293_jpg.rf.86fbdf8b1834f50ea9081a439ab6fbf5.txt` (contains Class 1)
- **Source Classes**:
  - `0`: Damaged signs (51 annotations across 51 images: 46 bounding boxes, 5 polygons)
  - `1`: Healthy signs (53 annotations across 49 files: all bounding boxes)

---

## 2. Image/Label Pairing & Manual Review Quarantine

- **Policy**: Strict isolation without fabrication. Do not pair disparate filenames.
- **Quarantined to `manual_review/`**:
  - `manual_review/images/`: 1 file (`IMG_8903_jpg.rf.617150b5aba1f59762738a5d40af8395.jpg`)
  - `manual_review/labels/`: 1 file (`IMG_8293_jpg.rf.86fbdf8b1834f50ea9081a439ab6fbf5.txt`)
- **Reason for Quarantine**: File stems differ. No deterministic metadata links `IMG_8903` to `IMG_8293`. Both preserved as unmatched source records.

---

## 3. Polygon Annotation Conversions (Task 3)

- **Total Polygons in Source**: 5 (all belonging to Class 0 / Damaged signs)
- **Polygons Successfully Converted to BBoxes**: **5 / 5 (100%)**
- **Polygons Sent to Manual Review**: **0**

| Source File | Source Class | Vertices | Calculated YOLO Bounding Box (`0 xc yc w h`) | Status |
|---|---|---|---|---|
| `IMG_8702_jpg.rf.06c73635e3a4fe0e5f612862ae8144e5.txt` | 0 | 9 pts | `0 0.390391 0.504768 0.685213 0.983016` | **SUCCESS** |
| `IMG_8725_jpg.rf.1c6802aebb5d2ae4eb86a86edc09054b.txt` | 0 | 4 pts | `0 0.479556 0.523019 0.673398 0.916871` | **SUCCESS** |
| `IMG_8744_jpg.rf.a9c09cbdcc2b228f62aa9ee3fb7ff8ae.txt` | 0 | 10 pts | `0 0.498906 0.490637 0.756274 0.981274` | **SUCCESS** |
| `IMG_8783_jpg.rf.2bc6dd1455e2aecfbe58df0958e86b63.txt` | 0 | 5 pts | `0 0.485622 0.460805 0.624176 0.747504` | **SUCCESS** |
| `IMG_9029_jpg.rf.cfced0352f72a57dadb7c273c636d444.txt` | 0 | 4 pts | `0 0.482296 0.398938 0.427407 0.672877` | **SUCCESS** |

---

## 4. Class Mapping & Negative Examples Policy

- **CVKI Isolated Target Class**: `0 = damaged_missing_road_sign`
- **Source Class 0 (Damaged signs)** -> Converted to Target Class `0` (**51 positive images**, 51 bounding boxes).
- **Source Class 1 (Healthy signs)** -> **Retained as Negative Background Examples** (**48 negative images**).
  - Healthy-sign images are preserved in `images/` with corresponding **empty label files** in `labels/`.
  - Rationale: Presenting healthy road signs as background negatives trains the object detector not to trigger false positives on normal signs.
  - No Class 1 annotations exist in the prepared dataset.

---

## 5. Final Prepared Dataset Counts & Verification

| Metric | Count | Details |
|---|---|---|
| **Prepared Images** | **99** | 100% matched with labels |
| **Prepared Labels** | **99** | 100% matched with images |
| **Positive Images (Damaged Signs)** | **51** | Exactly 1 bounding box each |
| **Negative Images (Healthy Background)** | **48** | Clean empty label files |
| **Total Target Bounding Boxes** | **51** | All Class 0 |
| **Orphan Images / Labels** | **0** | Perfect 1:1 stem matching |
| **Corrupt / Unreadable Images** | **0** | 100% verified via PIL |
| **Exact Duplicate Images (SHA-256)** | **0** | 99 unique hashes |
| **Malformed Label Rows** | **0** | Exactly 5 tokens per non-empty row |
| **Invalid Class IDs** | **0** | Only Class 0 present |
| **Coordinates Out of Bounds** | **0** | All xc, yc, w, h strictly in [0, 1] |

---

## 6. Bounding Box Statistics (Positive Damaged Signs)

- **Total Positive Boxes**: 51
- **Box Width** (on 640x640):
  - Minimum: `0.4274` (approx. 273.5 px)
  - Maximum: `1.0000` (approx. 640.0 px)
  - Average: `0.8079` (approx. 517.0 px)
- **Box Height** (on 640x640):
  - Minimum: `0.6270` (approx. 401.3 px)
  - Maximum: `1.0000` (approx. 640.0 px)
  - Average: `0.8772` (approx. 561.4 px)

---

## 7. Duplicate & Augmentation Analysis

- **Exact Duplicate Images (SHA-256)**: 0.
- **Roboflow Augmentation Groups**: 8 base image scenes have 2 augmented variations in the prepared set (`IMG_8087`, `IMG_8106`, `IMG_8121`, `IMG_8128`, `IMG_8162`, `IMG_8669`, `IMG_8776`, `IMG_9029`). Total unique base scenes: 91.

---

## 8. Source Integrity Confirmation

- **Source Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\DamagedSign`
- **SHA-256 Pre/Post Verification**: **100% IDENTICAL**.
- **Confirmation**: Zero files were modified, moved, renamed, overwritten, or deleted in `dataset_source/DamagedSign/`.

---

## 9. Limitations & Next Steps

1. This is the isolated single-class preparation for road signs (`nc: 1`).
2. The orphan image (`IMG_8903`) and orphan label (`IMG_8293`) remain in `manual_review/` awaiting manual human disposition.
3. If expanding to the full 1,339-image source dataset in later milestones, the Roboflow split imbalance (0 damaged signs in validation/test) must be re-stratified.
