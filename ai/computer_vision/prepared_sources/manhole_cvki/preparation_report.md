# CVKI M1.2 — Manhole Dataset Preparation Report

- **Execution Timestamp**: `1789191893.1650789`
- **Module**: M1.2 — Isolated Manhole Dataset Preparation
- **Source Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\Manhole`
- **Target Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\manhole_cvki`

---

## 1. Preparation Summary

| Metric | Source Count | Prepared Count | Status |
|---|---|---|---|
| **Images** | 100 | 100 | 100% Copied & Verified |
| **Labels** | 100 | 100 | 100% Copied & Verified |
| **Matched Pairs** | 100 | 100 | 100% Matched |
| **Orphaned Images** | 0 | 0 | None |
| **Orphaned Labels** | 0 | 0 | None |
| **Total Annotations** | 188 | 188 | 100% Preserved |
| **Corrupt Images** | 0 | 0 | None |
| **Exact Duplicate Images** | 0 | 0 | None (100 unique SHA-256) |
| **Manual Review Items** | 0 | 0 | Clean (Empty) |

---

## 2. Class Mapping & Conversion

- **Source Class**: `0` = open/damaged manhole
- **Target Class**: `0` = `open_damaged_manhole`
- **Conversion Rule**: `0 -> 0`
- **All annotations** retained class `0` in standard YOLO format: `<class_id> <x_center> <y_center> <width> <height>`.

---

## 3. Detailed Validation Results

| Validation Check | Expected | Actual | Result |
|---|---|---|---|
| Exactly 5 YOLO fields | 188 / 188 | 188 / 188 | **PASS** |
| Class ID = 0 | 188 / 188 | 188 / 188 | **PASS** |
| x_center in [0, 1] | 188 / 188 | 188 / 188 | **PASS** |
| y_center in [0, 1] | 188 / 188 | 188 / 188 | **PASS** |
| width > 0, height > 0 | 188 / 188 | 188 / 188 | **PASS** |
| Bounding box inside image boundary | 188 / 188 | 188 / 188 | **PASS** (float precision < 1e-5) |
| Image Readability (PIL verify) | 100 / 100 | 100 / 100 | **PASS** |
| Image Format | 100 JPEG | {'JPEG': 100} | **PASS** |
| Image Dimensions | 100 (720x720) | {'720x720': 100} | **PASS** |
| Color Modes | 100 RGB | {'RGB': 100} | **PASS** |
| Empty Labels | 0 | 0 | **PASS** |
| Malformed Labels | 0 | 0 | **PASS** |

---

## 4. Final Dataset Statistics

- **Total Images**: 100
- **Total Labels**: 100
- **Total Bounding Boxes**: 188
- **Box Width**:
  - Minimum: `0.0458` (approx. 33.0 px)
  - Maximum: `0.7111` (approx. 512.0 px)
  - Average: `0.2365` (approx. 170.3 px)
- **Box Height**:
  - Minimum: `0.0236` (approx. 17.0 px)
  - Maximum: `0.5125` (approx. 369.0 px)
  - Average: `0.1659` (approx. 119.5 px)
- **Object Density Breakdown**:
  - Images with exactly 1 object: **43**
  - Images with multiple objects (>1): **57**
  - Detailed breakdown: `{1: 43, 2: 39, 3: 10, 4: 4, 5: 3, 6: 1}`

---

## 5. Duplicate Check

- **Prepared Images SHA-256 Analysis**: 100 unique SHA-256 hashes across 100 images.
- **Exact Duplicates Detected**: **0**.

---

## 6. Manual Review Directory

- **Path**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\manhole_cvki\manual_review`
- **Contents**: `images/` (0 files), `labels/` (0 files).
- **Status**: Clean. No problematic or ambiguous samples required quarantine.

---

## 7. Source Integrity Confirmation

- **Source Folder**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset_source\Manhole`
- **SHA-256 Pre/Post Verification**: **100% MATCH**.
- **Confirmation**: Zero files were modified, renamed, moved, overwritten, or deleted in `dataset_source/Manhole/`.

---

## 8. Output Files & Artifacts Created

1. `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\manhole_cvki\images`: 100 JPEG images (`img-1.jpg` .. `img-100.jpg`)
2. `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\manhole_cvki\labels`: 100 YOLO label files (`img-1.txt` .. `img-100.txt`)
3. `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\manhole_cvki\manual_review\images`: Empty directory
4. `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\manhole_cvki\manual_review\labels`: Empty directory
5. `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\manhole_cvki\data.yaml`: Isolated single-class dataset configuration
6. `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\manhole_cvki\preparation_report.md`: Preparation and validation report
