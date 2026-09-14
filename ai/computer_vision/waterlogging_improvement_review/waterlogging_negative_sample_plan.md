# CVKI M1.10 — Waterlogging Negative Sample Plan

- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Module**: M1.10 — Waterlogging Dataset Improvement & Preparation
- **Document**: Negative Sample Acquisition & Curation Plan
- **Status**: **REVIEW / PROPOSAL** (Planning only — no dataset modifications)
- **Date**: 2026-09-12

---

## 1. Problem Diagnosis from M1.9 Inference & Error Analysis

In the M1.8 YOLOv8n baseline evaluation and M1.9 controlled inference stage, `road_waterlogging` produced **18 False Positives** across the 10 held-out test images at confidence $\ge 0.25$ (and up to 27 false alarms across background regions at lower confidence thresholds).

Visual inspection of false positive prediction overlays revealed distinct, recurring failure modes:
1. **Tree Canopy Shadows**: Dappled sunlight filtering through roadside trees creates irregular high-contrast dark patches on dry asphalt that closely resemble water puddle boundaries.
2. **Bridge & Overpass Structural Shadows**: Sharp, linear cast shadows beneath highway overpasses and underpass portals mimic deep standing water pools.
3. **Fresh Asphalt Patches & Tar Crack-Seals**: Resurfaced, dark black asphalt patches embedded in weathered gray asphalt create smooth, low-luminance zones with sharp borders, triggering high-confidence waterlogging detections (conf $0.70 - 0.92$).
4. **Uniform Wet Asphalt / Rain Sheen**: Roads wet from recent rainfall without stagnant standing water reflect sky luminance, which the model confuses with hazardous road flooding.
5. **Damp Road Gutters**: Dry pavement transitioning into dark damp road shoulders triggers false puddle alarms.

### Benchmark Contrast: Road Sign Class
In the baseline dataset, `damaged_missing_road_sign` included **48 negative images** (healthy road signs and empty road scenes) in the training split. As a result, the baseline model achieved **0.8000 empirical recall and 0.7950 mAP@0.5** with only 2 false positives on the test set. 

By contrast, `road_waterlogging` contained only **2 negative images** (2% of the waterlogging dataset), leaving the YOLO feature extractor without explicit training on what *dry or merely damp road surfaces* look like.

---

## 2. Required Negative Sample Categories

To systematically eliminate these false positives, the improved waterlogging training distribution must incorporate 5 targeted categories of negative images:

| Category ID | Negative Category Name | Target False Positive Mechanism Addressed | Target Count |
|---|---|---|---|
| **NEG-01** | **Tree Canopy Shadows on Dry Asphalt** | Dappled, irregular sunlight-and-shadow leaf patterns on dry roadways | **6** |
| **NEG-02** | **Bridge & Overpass Structural Shadows** | Deep, dark, sharp geometric shadows cast across roadway lanes | **5** |
| **NEG-03** | **Dark Patched Asphalt & Bitumen Sealant** | Fresh black asphalt repair patches and tar crack-seal ribbons | **5** |
| **NEG-04** | **Uniform Wet Roadway / Rain Sheen** | Completely wet road surface without standing puddles or water depth | **5** |
| **NEG-05** | **Damp Curbs, Gutters & Drainage Inlets** | Dark roadside drainage gutters without roadway lane flooding | **4** |
| **TOTAL** | **Targeted Negative Images** | **Complete background discriminative coverage** | **25** |

---

## 3. Justification of Target Count (25 Images)

1. **Current Waterlogging Split**: Currently 100 images (98 positive, 2 negative = 2.0% negative ratio).
2. **Proposed Improved Waterlogging Split**: Target size of ~110–115 images (85–90 positive, 25 negative).
3. **Negative Ratio**: 25 / 111 $\approx$ **22.5%**.
4. **Alignment with Best Practices**: In Ultralytics YOLO guidelines, background negative images representing 15% to 25% of the total dataset are recommended to suppress background false positives without diluting bounding box gradient updates.
5. **Statistical Parity**: 25 negatives distributed as 18 in Train, 5 in Val, and 2 in Test ensures every split can rigorously evaluate background false alarm rates.

---

## 4. Diversity & Environmental Requirements

All negative candidate images must satisfy rigorous civic environmental diversity criteria:

- **Lighting Conditions**:
  - Harsh direct sunlight (high-contrast shadow edges)
  - Diffused overcast / midday flat lighting (low-contrast patches)
  - Golden hour / low-angle sun (long elongated shadows)
  - Night / artificial roadway sodium-vapor / LED illumination
- **Roadway Geometries**:
  - Multi-lane urban arterial boulevards with lane divider markings
  - Two-lane undivided rural asphalt highways
  - Residential neighborhood streets with curbs and sidewalks
  - Concrete highway road sections with expansion joints
  - Intersections and pedestrian crosswalks
- **Surface Textures**:
  - Aged, weathered gray asphalt with aggregate exposure
  - Smooth freshly rolled black bitumen
  - Grooved or polished concrete surfaces
  - Interlocking paving stones / brick road shoulders

---

## 5. Formal Acceptance Criteria

To be accepted into the improved dataset staging area, a candidate negative image must pass 100% of the following requirements:

1. **Zero Standing Water**: Must contain verifiably **zero** pooled, stagnant, or standing water deeper than surface moisture film.
2. **Authentic Roadway Context**: Must depict a legitimate civic driving or pedestrian surface (street, road, highway, bridge, intersection).
3. **Upright Perspective**: Must be captured from natural vehicle dashcam, driver eye-level (1.0m–1.5m), or pedestrian curb perspective. Zero 90°/180°/270° rotations.
4. **Zero Collages / Mosaics**: Must be a single, un-tiled, continuous photograph. No 2x2 multi-quadrant grids.
5. **Image Quality**: Minimum resolution of $640 \times 640$ pixels (or scaled from native aspect ratio $\ge 512 \times 384$). No severe blur, digital watermark stamps, or artificial compression artifacts.
6. **Annotation Integrity**: Accompanied by a strictly empty label file (0 bytes, 0 rows).

---

## 6. Strict Rejection Criteria

Any candidate sample matching any of the following rules will be rejected immediately:

- ❌ **Puddle Presence**: Contains any isolated water puddle with visible depth $>5$ mm or distinct surface ripple reflections.
- ❌ **Non-Road Context**: Depicts off-road locations (open fields, agricultural soil, dirt hiking trails, indoor garages, rooftops, manicured lawns).
- ❌ **Artificial Rotations**: Sourced from Roboflow or other pipelines with 90°, 180°, or 270° orientation flips.
- ❌ **Watermark / Text Clutter**: Contains prominent stock-photo watermarks, timestamps, or artificial framing borders.
- ❌ **Perceptual Duplication**: Exhibits perceptual hash similarity (Hamming distance $\le 3$) to any existing project image.

---

## 7. Sourcing & Isolation Protocol

1. **Local Project Discovery First**: Candidates will be sought exclusively from already-existing project directories, local downloads, and civic repository archives (`C:\Users\sushm\Downloads\`, etc.).
2. **Zero Web Scraping**: No automated bulk scrapers or random web image downloads.
3. **Isolated Staging Directory**: All accepted negative samples will be staged in:
   `ai/computer_vision/waterlogging_improvement_review/staged_negatives/`
   before any dataset compilation.
4. **Frozen Baseline Safeguard**: No staged negative files will be copied into `ai/computer_vision/dataset/` until approved by the user.
