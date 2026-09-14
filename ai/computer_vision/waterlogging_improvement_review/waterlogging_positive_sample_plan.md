# CVKI M1.10 — Waterlogging Additional Positive Sample Plan

- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Module**: M1.10 — Waterlogging Dataset Improvement & Preparation
- **Document**: Targeted Positive Sample Acquisition & Curation Plan
- **Status**: **REVIEW / PROPOSAL** (Planning only — no dataset modifications)
- **Date**: 2026-09-12

---

## 1. Problem Diagnosis from M1.9 Controlled Error Analysis

In the M1.8 YOLOv8n baseline evaluation on 30 test images, `road_waterlogging` was the single weakest detector by a wide margin:
- **Precision**: `0.6676` (benchmark) / `0.4000` (empirical VOC threshold)
- **Recall**: `0.2308` (benchmark) / `0.3077` (empirical VOC threshold)
- **mAP@0.5**: `0.2951` (vs `0.7598` for manholes and `0.7950` for road signs)
- **mAP@0.5:0.95**: `0.1737`

The controlled error analysis in M1.9 broke down the **27 missed ground-truth instances (False Negatives)** into three specific visual categories:
1. **17 Misses on Low-Contrast Shallow Water**: Dirty water on dark asphalt lacks bright specular sky reflections, making the water-pavement boundary diffuse and invisible to the feature extractor.
2. **10 Misses on Small Micro-Puddles**: Small puddles ($<3\%$ image area) vanish across the P3/P4/P5 strides of YOLOv8n when downsampled from varying native resolutions to $640 \times 640$.
3. **Severe Under-Representation of Civic Road Diversity**: The source dataset was heavily dominated by 2x2 multi-quadrant collages and catastrophic flooding (submerged vehicles), with almost zero representation of common municipal hazards: localized pothole puddles, clogged curb drains, and highway lane ponding.

Furthermore, **42 images** in the current 100-image dataset were identified as artificial sideways/inverted 90° rotations in the Phase C audit, corrupting the model's spatial understanding of horizontal water leveling.

---

## 2. Target Positive Sample Requirements & Quotas

To replace the 42 excluded rotation artifacts while addressing each M1.9 failure mode, the improved positive waterlogging pool requires **25 to 30 clean, upright, single-scene images** distributed across targeted categories:

| Target Domain ID | Weakness Addressed | Key Visual Attributes Required | Target Image Count |
|---|---|---|---|
| **POS-01** | **Isolated Road Puddles (Small/Medium)** | Localized standing water covering 5% to 25% of the road lane; clear water boundary against dry/damp pavement | **6 – 7** |
| **POS-02** | **Low-Contrast Shallow Water / Murky Water** | Stagnant murky brown/gray water on dark asphalt without high-contrast sky reflections; visible road surface beneath water | **5 – 6** |
| **POS-03** | **Distant & Mid-Range Highway Ponding** | Standing water located 15 to 45 meters forward in vehicle dashcam view; tests model's small-scale feature retention | **4 – 5** |
| **POS-04** | **Diverse Road Surfaces & Textures** | Puddled water on concrete slabs, worn aggregate asphalt, paving stones, and road-shoulder gravel interfaces | **4 – 5** |
| **POS-05** | **Underpass, Bridge & Low-Light Puddles** | Water accumulation beneath railway bridges, highway underpasses, and shaded roadway cuts with artificial/dim lighting | **3 – 4** |
| **POS-06** | **Urban Commercial & Residential Gutters** | Clogged storm drain backflow, curb puddles overflowing into parking/driving lanes in front of buildings | **3 – 4** |
| **TOTAL** | **Target Positive Sample Pool** | **Complete civic coverage across natural orientations** | **25 – 30** |

---

## 3. Justification of Recommended Target Count (25–30 Images)

1. **Current Waterlogging Positives**: 98 positive images.
2. **Phase C Exclusions**: 42 artificial 90°/270° rotation artifacts recommended for removal.
3. **Retained High-Quality Positives**: 56 positive images (plus 2 clean background negatives = 58 retained).
4. **Proposed Additions**: Adding 28 new positive images yields:
   $$56 \text{ (retained)} + 28 \text{ (new positive)} = 84 \text{ positive images}$$
   Combined with 25 targeted negative images (defined in Phase D), the total improved waterlogging pool will reach:
   $$84 \text{ positive} + 25 \text{ negative} + 2 \text{ existing negative} = \mathbf{111 \text{ images}}$$
5. **Class Balance Preservation**: 111 images maintains parity with `open_damaged_manhole` (100 images) and `damaged_missing_road_sign` (100 images), while providing the vital background discrimination needed to elevate mAP@0.5 from 0.2951 to $>0.6500$.

---

## 4. Acceptance Criteria for Additional Positive Samples

Each candidate positive image must satisfy 100% of the following verification checks:

1. **Authentic Roadway Context**: Depicts active vehicular roads, highways, municipal streets, intersections, or pedestrian crossings.
2. **Standing Stagnant Water**: Contains distinct pooled standing water covering roadway asphalt or concrete (minimum 1 cm visible water depth or prominent standing surface ripple).
3. **Single Natural Scene**: Strictly **zero** 2x2 multi-quadrant collages, split-screen composites, or stitched mosaics.
4. **Upright Perspective (0°)**: Natural camera horizon conforming to vehicle dashcam (1.0m–1.4m), street CCTV (3m–5m), or pedestrian smartphone height (1.4m–1.7m).
5. **Image Clarity & Resolution**: Minimum resolution $\ge 512 \times 384$ (preferred native $\ge 640 \times 640$); uncompressed JPEG/PNG; zero motion blur or watermark overlays.
6. **Annotation Standardization**: Annotated strictly following the M1.10 Contiguous Bounding Box Policy (one contiguous box per continuous flood zone, zero sub-puddle fragmentation).

---

## 5. Strict Rejection Criteria

Candidates matching any of the following conditions will be immediately rejected:

- ❌ **Non-Road Water Bodies**: Natural shorelines, lakes, rivers, forest creeks, residential swimming pools, or drainage canals without road infrastructure.
- ❌ **Surface Sheen Only**: Pavement that is merely damp or uniformly wet without localized standing water (these belong in the Negative Sample Pool NEG-04).
- ❌ **Micro-Splashes / Spray**: Temporary tire spray or splashing droplets that do not constitute a persistent road puddle hazard.
- ❌ **Artificial Rotations**: Sourced from pipelines applying 90°, 180°, or 270° orientation flips.
- ❌ **Perceptual Leakage**: Matches any existing training, validation, or test image (perceptual hash distance $\le 3$).

---

## 6. Sourcing Strategy (Local Project Sources Only)

Per the strict requirements of M1.10, **no external web scraping or uncontrolled downloading will take place**. All 25–30 positive candidates will be sourced directly from existing local project repositories:

1. **Primary Candidate Source**: `C:\Users\sushm\Downloads\water logging.v1i.yolov8\valid\`
   - Contains 31 un-augmented, single-scene base images.
   - 6 were previously verified and used as replacements in M1.5B (`waterloggingt-10`, `101`, `123`, `124`, `145`, `31`).
   - 25 candidate images remain locally available and uncommitted, offering immediate, verified candidates.
2. **Secondary Candidate Source**: `C:\Users\sushm\Downloads\water logging.v1i.yolov8\train\`
   - Contains 168 distinct base scenes.
   - Upright, un-rotated variants can be isolated by verifying horizontal horizon lines and vehicle uprightness.
3. **Staging Protocol**:
   - Candidates will be curated, re-annotated under the unified policy, and staged in:
     `ai/computer_vision/waterlogging_improvement_review/staged_positives/`
   - Complete provenance manifests will track source file hashes, source scenes, and annotation revisions.
