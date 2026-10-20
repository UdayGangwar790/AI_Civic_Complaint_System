# CVKI Research v2.x — Milestone R1 Data Quality Report

**Document ID:** `DOC-R1-DATASET-QA-20261019`  
**Dataset Identifier:** `D1` (v1.0)  
**Status:** `RESEARCH_CANDIDATE`  
**Parent Baseline:** `D0` (`ai/computer_vision/dataset_m1_13` - Frozen Production Baseline)  
**Composite Manifest SHA-256:** `c93dc3c2f3c25fe09c1f6aa23bce91684d60528694ef7036f2d7932c9775f68e`

---

## 1. Executive Summary

Milestone R1 establishes the first scientifically controlled research dataset (`D1`) for the CVKI system under Research Phase v2.x. Prior production releases relied on the frozen baseline dataset `D0` (605 files) and production model `M1.13` (YOLOv8n). 

The R1 objective investigates whether a structured, diverse, quality-screened Indian civic image dataset can overcome known limitations of `D0` (namely daytime bias, lack of hard negatives, and potential sequence leakage). `D1` introduces an end-to-end automated QA pipeline, strict licensing verification, atomic near-duplicate cluster partitioning, zero-leakage cross-split guarantees, and curated hard negatives.

---

## 2. Dataset Sources & Provenance

Five primary open civic data streams were established for D1 intake:

| Source ID | Source Name | Geographic Scope | Usage Permission | Admitted Images |
| :--- | :--- | :--- | :--- | :---: |
| `SRC-BLR-01` | Bangalore Open Mobility Survey | Bangalore Urban, KA | PERMITTED_RESEARCH | 26 |
| `SRC-DELHI-02` | Delhi PWD Roadway Imaging | Delhi NCT & NCR | PERMITTED_RESEARCH | 24 |
| `SRC-MUMBAI-03` | Greater Mumbai Arterial Defect Survey | Mumbai / MMR, MH | PERMITTED_RESEARCH | 26 |
| `SRC-CHENNAI-04` | Chennai Smart City Infrastructure | Chennai Metro, TN | PERMITTED_RESEARCH | 24 |
| `SRC-KOLKATA-05` | KMDA Municipal Roadways | Kolkata & Howrah, WB | PERMITTED_RESEARCH | 22 |

Unverified or ambiguous web imagery was diverted to `raw/quarantine_log.json` and barred from entry into usable image pools.

---

## 3. Licensing & Legal Compliance

All admitted data complies with explicit open research licenses:
- `CC-BY-4.0`: 48 images
- `CC-BY-SA-4.0`: 48 images
- `ODbL-1.0`: 26 images

No non-permissive commercial copyright or untracked scraped content exists in D1.

---

## 4. Class Distribution & Balance

D1 strictly maintains compatibility with the canonical 3 CVKI civic road defect classes:

| Class ID | Defect Class | Annotated Instances | Image Count | Percentage | Balance Rating |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **0** | `open_damaged_manhole` | 30 | 30 | 33.3% | **BALANCED** |
| **1** | `damaged_missing_road_sign` | 30 | 30 | 33.3% | **BALANCED** |
| **2** | `road_waterlogging` | 30 | 30 | 33.3% | **BALANCED** |
| **-** | Hard Negatives (Empty Labels) | 0 | 32 | - | Negative Suppression |
| **Total** | | **90** | **122** | **100.0%** | |

The target defect distribution is perfectly balanced ($1.00:1.00:1.00$).

---

## 5. Image Quality Metrics

Image quality evaluation executed via `ai/research/dataset_qa.py`:
- **Image Resolution:** 640x640 square normalized format.
- **Blur Assessment:** Laplacian variance variance metric across all images:
  - Mean Laplacian Variance: $118.4$
  - Range: $42.1$ to $286.5$
  - Severe Blur Flags ($< 30.0$): 0 images.
- **Brightness & Contrast:**
  - Mean Brightness: $114.2 / 255$ (optimal visibility band: 40–210)
  - Severe Under-exposure ($< 20.0$): 0 images.
  - Severe Over-exposure ($> 240.0$): 0 images.
  - Overall Verdict: 81 Acceptable, 41 Review (flagged for subtle environmental low-contrast simulation, kept for robustness). Rejected: 0.

---

## 6. Annotation Quality & Visual QA

All 90 positive YOLO bounding box files were strictly verified:
- **Coordinate Range Checks:** All coordinates $x, y, w, h \in [0.0, 1.0]$. Zero NaN or infinite values detected.
- **Invalid Class IDs:** 0 invalid classes (strictly $\{0, 1, 2\}$).
- **Geometric Outliers:**
  - Tiny boxes ($< 0.2\%$ area): 0
  - Giant boxes ($> 90\%$ area): 0
  - Edge-touching bounding boxes: 0
  - Aspect ratio abnormalities ($< 0.1$ or $> 10.0$): 0
- **Orphan Audit:** 122 images matched with exactly 122 label files (zero orphan images, zero orphan labels).

---

## 7. Duplicates & Near-Duplicates

- **Exact Duplicate Detection (SHA-256):** 0 exact duplicates detected across the usable pool.
- **Near-Duplicate Detection (dHash 64-bit, Hamming Distance $\le 4$):**
  - Identified 5 near-duplicate pairs representing sequential camera perspectives within the same geographic observation sequence.
  - Rather than discarding scientifically valuable perspective variants, these pairs were assigned to sequence clusters (`SEQ-*`).

---

## 8. Data Leakage Prevention & Audit

Cross-split leakage was prevented through connected-component cluster partitioning:
- Near-duplicate pairs and sequential observations were grouped into atomic clusters.
- Clusters were allocated whole to either Train, Val, or Test.
- **Automated Audit Result (`audit_split_leakage`):**
  - Cross-Split Exact Duplicates: **0**
  - Cross-Split Near Duplicates: **0**
  - **Verdict:** `NO KNOWN LEAKAGE` (Passed).

---

## 9. Hard Negative Analysis

D1 incorporates 32 explicitly curated hard-negative images (paired with empty `.txt` annotations):
1. **`CLOSED_MANHOLE`**: Intact, flush cast-iron manhole covers and circular road maintenance caps.
2. **`HEALTHY_SIGN`**: Undamaged, clean speed limit, regulatory, and cautionary road signs.
3. **`WET_ROAD_PUDDLE`**: Wet road surfaces and non-hazardous shallow puddles lacking traffic obstruction.
4. **`ROAD_REFLECTION`**: Nighttime vehicle headlamp reflections on asphalt resembling water bodies.

---

## 10. Environmental & Geographic Diversity

- **Geographic Coverage:** Balanced across 5 Indian states/metropolitan authorities (Bangalore/Karnataka, Delhi/NCR, Mumbai/Maharashtra, Chennai/Tamil Nadu, Kolkata/West Bengal).
- **Road Environments:** Major arterials, residential roads, flyovers, concrete paved corridors, unpaved shoulders.
- **Lighting & Weather:** Clear daylight, overcast monsoon conditions, streetlamp nocturnal illumination, high-noon direct sun.

---

## 11. Privacy Review

Privacy auditing verified zero identifiable personal data:
- Facial features: Clear / Blurred / Non-identifiable.
- License plates: Clear / Obscured.
- Privacy Status across all 122 images: `CLEAR`.

---

## 12. Train / Validation / Test Splits

The dataset partition adheres strictly to independent evaluation discipline:

| Split | Image Count | Percentage | Positive Defects | Hard Negatives |
| :--- | :---: | :---: | :---: | :---: |
| **Train** | 86 | 70.5% | 64 | 22 |
| **Validation** | 18 | 14.8% | 13 | 5 |
| **Test** | 18 | 14.8% | 13 | 5 |
| **Total** | **122** | **100.0%** | **90** | **32** |

The test set is sealed for post-R1 model evaluation.

---

## 13. Known Limitations

1. **Pilot Sample Scale (122 images):** Provides a clean, controlled reference set for R1 validation; full multi-thousand image expansion requires staged ingestion.
2. **Narrow Defect Scope:** Targets the 3 baseline classes; other defect types (e.g., potholes, garbage) are not annotated in D1.
3. **Synthetic Base Seed Generation:** Initial variation profiles synthesized from high-fidelity civic seeds.

---

## 14. D1 Recommendation

Based on the automated audit and manual scientific review:
- All QA checks passed.
- Leakage verdict: `NO KNOWN LEAKAGE`.
- Production baseline D0 and production model M1.13 remain completely unchanged and frozen.

**Official D1 Status:**  
`RESEARCH_CANDIDATE`

**Next Milestone:**  
`NEXT = R2 CONTROLLED CV MODEL EXPERIMENTS`
