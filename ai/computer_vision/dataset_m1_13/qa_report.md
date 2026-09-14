# CVKI M1.13 — Dataset QA Certification Report

- **Dataset Path**: `ai/computer_vision/dataset_m1_13/`
- **Total Images**: 300
- **Total Bounding Boxes**: 416
- **Audit Status**: **CERTIFIED PASS**
- **Date**: 2026-09-13

---

## 1. Split & Class Distribution

| Split | Manhole | Road Sign | Waterlogging (Pos) | Waterlogging (Neg) | Waterlogging Neg Ratio | Total Images |
|---|---|---|---|---|---|---|
| **Train** | 70 | 70 | 59 | 8 | **11.9%** (~10% target) | **207** |
| **Val** | 20 | 20 | 15 | 7 | 31.8% | **62** |
| **Test** | 10 | 10 | 10 | 1 | 9.1% | **31** |
| **TOTAL** | **100** | **100** | **84** | **16** | **16.0%** | **300** |

### Class Bounding Box Counts
- **Open Damaged Manhole (Class 0)**: 188 boxes
- **Damaged Missing Road Sign (Class 1)**: 52 boxes
- **Road Waterlogging (Class 2)**: 176 boxes
- **Total Bounding Boxes**: 416

---

## 2. Selected Waterlogging Train Negatives (8 Images)

The 8 representative waterlogging training negatives were specifically selected to cover all 5 civic false-positive categories without overwhelming the detector:

| Final Filename | Civic Negative Category | Justification |
|---|---|---|
| `waterlogging_negative_IMG_8080_jpg.rf.1372954eaaa1b7729dd3137086c621df.jpg` | Tree Canopy Shadow | High-contrast dappled tree shadow on dry pavement |
| `waterlogging_negative_IMG_8118_jpg.rf.2f48636bc3811382dcc0b61e658004af.jpg` | Tree Canopy Shadow | Irregular roadside foliage shadow |
| `waterlogging_negative_IMG_8103_jpg.rf.3e045aa4476f11f7ceeaf51f68676585.jpg` | Bridge/Overpass Shadow | Sharp geometric shadow beneath overpass structure |
| `waterlogging_negative_IMG_8084_jpg.rf.8384dc639784c2ec83763b45b671961c.jpg` | Bridge/Overpass Shadow | Low-luminance highway underpass shadow |
| `waterlogging_negative_IMG_8101_jpg.rf.54fc93e82f99572622d85e89925f203c.jpg` | Dark Patched Asphalt | Uniform dark bitumen patch on weathered pavement |
| `waterlogging_negative_IMG_8070_jpg.rf.440f012d444257140b9845a79cb7e5e2.jpg` | Dark Patched Asphalt | Smooth black road repair patch |
| `waterlogging_negative_IMG_8117_jpg.rf.0962bc1c5109d929cf3b5055e6ae2c54.jpg` | Damp Curb / Shoulder | Dark asphalt curb and drainage edge |
| `waterlogging_waterloggingt-105-_jpg.rf.c8c800d329a2fa4ad5b4bfc37baac5bf.jpg` | Baseline Dry Roadway | Original dry asphalt negative from baseline lineage |

---

## 3. QA Audit Verification Results

1. **Pairing Integrity**: **0 orphan images, 0 orphan labels**. Every image has an exact matching `.txt` label file.
2. **Annotation Coordinate Validity**: All normalized coordinates strictly satisfy $0.0 \le x, y, w, h \le 1.0$.
3. **Class ID Integrity**: 100% of labels strictly contain IDs in `{0, 1, 2}`.
4. **Scene Leakage Prevention**: **0 cross-split scene leakages**. All multi-frame scene variants reside strictly within their assigned split.
5. **Frozen Baseline Safeguard**: `dataset/` and `dataset_improved/` remain 100% unmodified.
