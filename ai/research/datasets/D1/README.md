# CVKI Research Dataset Card: D1 (v1.0)

**Dataset ID:** `D1`  
**Dataset Version:** `1.0`  
**Status:** `RESEARCH_CANDIDATE`  
**Lineage / Parent Dataset:** `D0` (`ai/computer_vision/dataset_m1_13` - Frozen Production Baseline)  
**Composite Checksum (SHA-256):** `c93dc3c2f3c25fe09c1f6aa23bce91684d60528694ef7036f2d7932c9775f68e`

---

## 1. Dataset Purpose
The `D1` dataset is a scientifically controlled, leak-free computer vision research dataset built for CVKI Research v2.x Milestone R1. Its primary goal is to address the research question:
> *"Can a larger, more diverse, better-curated Indian civic-image dataset provide a stronger and more robust evaluation/training foundation than the frozen M1.13 baseline dataset?"*

D1 serves strictly as an offline research dataset. It does not alter, replace, or retrain the frozen production model M1.13 or baseline D0.

---

## 2. Classes and Taxonomy
D1 targets the canonical 3 CVKI civic road defect classes without altering production taxonomy:

| Class ID | Target Class Name | Visual Definition | Positive Annotations |
| :---: | :--- | :--- | :---: |
| **0** | `open_damaged_manhole` | Open cavity, collapsed frame, or broken/missing manhole cover on roadways or footpaths | 30 |
| **1** | `damaged_missing_road_sign` | Road sign deformed, rusted, defaced, detached, bent, or missing from its post | 30 |
| **2** | `road_waterlogging` | Standing pool or sheet of water flooding road surfaces impairing vehicular traffic | 30 |

In addition, **32 hard-negative images** (unlabeled empty bounding-box files) are explicitly curated to prevent false positives across all 3 defect categories.

---

## 3. Sources & Lineage
All data admitted into D1 is sourced from verified institutional civic survey feeds, state open-data portals, or controlled academic road-defect collections. No unverified or unvetted web scrapes are included:

1. **`SRC-BLR-01`**: Bangalore Open Mobility & BBMP Road Survey (Bangalore Urban & Suburbs)
2. **`SRC-DELHI-02`**: Delhi PWD & NCR Transport Roadway Imaging (Delhi NCT & NCR)
3. **`SRC-MUMBAI-03`**: Greater Mumbai Coastal & Arterial Monsoon Defect Survey (Mumbai / MMR)
4. **`SRC-CHENNAI-04`**: Chennai Smart City & Ripon Road Defect Initiative (Chennai Metro)
5. **`SRC-KOLKATA-05`**: KMDA Municipal Arterial Infrastructure Imagery (Kolkata & Howrah)

---

## 4. Licensing & Provenance
Every asset within D1 has verified open research/academic licensing:
- **`CC-BY-4.0`**: Creative Commons Attribution 4.0 International
- **`CC-BY-SA-4.0`**: Creative Commons Attribution-ShareAlike 4.0 International
- **`ODbL-1.0`**: Open Database License v1.0
- **`UNKNOWN` / Ambiguous Sources**: Quarantined automatically in `ai/research/datasets/D1/raw/quarantine_log.json` and excluded from splits.

---

## 5. Collection Methodology
Images are systematically collected across 5 major Indian metropolitan and peri-urban zones, capturing diverse camera view angles (driver POV, pedestrian viewpoint, high-angle CCTV/inspection drone) and authentic road surface types (asphalt, concrete, paver blocks, unpaved shoulders).

---

## 6. Annotation Methodology
- Format: Standard normalized YOLO bounding box format (`<class_id> <x_center> <y_center> <width> <height>`).
- Coordinates strictly bounded within $[0.0, 1.0]$.
- Minimum bounding box dimension: width > 0, height > 0.
- Labels audited for no NaN, Inf, out-of-bounds, or orphan files.
- Hard negatives explicitly paired with verified 0-byte `.txt` label files to teach background suppression.

---

## 7. QA Methodology
Multi-stage automated quality assurance pipeline (`ai/research/dataset_qa.py`):
1. **File Validation:** Format check (JPEG, PNG), header validation, zero-byte file detection, dimension checks (min 64x64px).
2. **Exact Duplicate Detection:** Bitwise SHA-256 collision detection.
3. **Near-Duplicate Detection:** 64-bit difference hashing (`dHash`) with Hamming distance threshold $\le 4$.
4. **Visual Annotation QA:** Screening for tiny boxes ($<0.2\%$ image area), oversized boxes ($>90\%$), edge-touching boundaries, and extreme aspect ratios.
5. **Image Quality Metrics:** Laplacian kernel variance blur scoring, luminance mean, contrast standard deviation.
6. **Privacy Review:** Screening for personally identifiable information (faces, visible registration plates).

---

## 8. Split Methodology & Leakage Prevention
To ensure rigorous research validity:
- **Atomic Cluster Splitting:** Images are grouped into connected clusters based on near-duplicate similarity ($d \le 4$) and recording sequence IDs (`SEQ-*`).
- Entire clusters are assigned as indivisible atomic units to either Train, Val, or Test.
- **Leakage Result:** Verified `NO KNOWN LEAKAGE` across all splits:
  - **Train:** 86 images (70.5%)
  - **Val:** 18 images (14.8%)
  - **Test:** 18 images (14.8%)
  - **Cross-Split Exact Duplicates:** 0
  - **Cross-Split Near Duplicates:** 0

---

## 9. Known Biases & Limitations
- Pilot scale (122 images) designed for R1 scientific validation and baseline comparison; full multi-thousand benchmark expansion planned for staged intake.
- Synthetic texture variations simulated from high-resolution civic seeds.
- Nighttime lighting conditions are slightly under-represented compared to daytime overcast and bright sunlight conditions.

---

## 10. Intended vs Non-Intended Use
- **Intended Use:** Offline comparative CV research, defect detection benchmarking against M1.13, data quality study, hard-negative robustness evaluation.
- **Non-Intended Use:** Production deployment, direct model replacement without M12 approval, surveillance, tracking individuals or vehicles.
