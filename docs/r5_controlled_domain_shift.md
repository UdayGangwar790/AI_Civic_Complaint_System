# CVKI Research R5 — Controlled Domain-Shift & Robustness

**Experiment:** `CVR2-CV-016`  
**Status:** `PARTIALLY_VALIDATED`  
**Study type:** controlled synthetic perturbations of internal research evaluation images  
**External real-world dataset:** none  
**Production integration:** `FALSE`  
**Evaluation timestamp:** `2026-10-19T17:27:51.881532+00:00`

## 1. Objective

Measure the frozen R3 model's behavior under predeclared changes to illumination, contrast, blur, sensor-like noise, JPEG compression, synthetic shadow, and synthetic rain overlays. Keep the D1 held-out test images and labels as the source for every condition. Do not retrain, tune per condition, or claim that transformed copies are independent real-world data.

## 2. Research Question

How do fixed R3 predictions change across three deterministic severity levels of controlled visual perturbations, at fixed confidence thresholds? Which effects can be described for the class actually represented in the held-out images?

The planned crop/viewpoint condition was evaluated for label validity before generation and excluded: a D1 test box has a minimum border margin of 0.0078, requiring at least 0.9844 retained image dimension to avoid truncating the annotation. That permits at most a 1.56% total centered crop, too small to define three meaningful severity levels. Stronger crops would invalidate the box.

## 3. Frozen References

| Reference | Frozen value | R5 verification |
|---|---|---|
| D0 | `ai/computer_vision/dataset_m1_13`, 605 files | Count assertion in R5 tests |
| M1.13 checkpoint | SHA-256 `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3` | SHA assertion in R5 tests |
| R3 checkpoint | `ai/research/experiments/R3/CVR2-CV-006/weights/best.pt`; SHA-256 `72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28` | SHA assertion in R5 tests |
| R3 operating thresholds | confidence `0.100` primary; `0.250` secondary; IoU `0.50` | Recorded and asserted for every condition |

R5 performed inference only. It did not alter D0, M1.13, R3 weights, production code, APIs, or thresholds.

## 4. Experimental Design

- **Hypothesis:** stronger controlled visual shifts may be associated with degraded fixed-threshold detection performance and/or prediction confidence. This is a within-source perturbation comparison, not a causal or external-domain claim.
- **Model:** `R3-YOLO-ROBUST-BASE`, frozen `CVR2-CV-006` checkpoint.
- **Source:** D1 `test` split, 18 images, 15 boxes; 3 images have empty labels.
- **Conditions:** clean reference plus seven perturbation families at L1/L2/L3: 22 total conditions.
- **Seeds:** master seed `20261019`; deterministic per-image/per-transformation/per-severity seed derived from SHA-256 of the master seed, source image SHA, transformation, and severity.
- **Selection:** transformations and severity parameters were fixed before evaluating model performance.
- **Statistical design:** repeated transformations of the same 18 source images; conditions are paired and not independent samples. No significance testing or confidence intervals are asserted.

## 5. Transformation Definitions

| Transformation | L1 | L2 | L3 | Label handling |
|---|---|---|---|---|
| Brightness | factor 0.80 | factor 0.60 | factor 0.40 | Boxes unchanged |
| Contrast | factor 0.80 | factor 0.60 | factor 0.40 | Boxes unchanged |
| Gaussian blur | radius 0.5 px | radius 1.0 px | radius 2.0 px | Boxes unchanged |
| Additive Gaussian noise | sigma 5 | sigma 12 | sigma 24 | Boxes unchanged |
| JPEG compression | quality 75 | quality 45 | quality 20 | Boxes unchanged |
| Synthetic shadow | alpha 0.12, 6-point polygon, blur 24 px | alpha 0.27, blur 18 px | alpha 0.45, blur 12 px | Boxes unchanged |
| Synthetic rain-like streak overlay | 35 streaks/640 px, length 12 px, alpha 45 | 70, length 20 px, alpha 70 | 120, length 30 px, alpha 100, width 2 px | Boxes unchanged |
| Crop/viewpoint | **Excluded** | **Excluded** | **Excluded** | Meaningful levels truncate at least one existing GT box |

Rain and shadow are procedural overlays, not physical weather or camera-scene measurements. “Brightness,” “noise,” and other names refer only to the specified image transforms.

## 6. Dataset Generation

The generated dataset is `ai/research/datasets/R5_controlled_shift/`. It contains 18 exact clean copies plus 378 transformed copies (18 images × 7 transformations × 3 severities), for **396 image/label pairs**. All labels are copied unchanged because all included transforms preserve geometry. Each output-manifest row binds source image and label paths/hashes, source split, output paths/hashes, transformation, severity, parameters, seed, dimensions, and generation timestamp.

The output manifest SHA-256 is:

`d36bd0f653c5650f628ad26d9397b5e843154931f23177918235b94b2f899f0e`

D1's recorded composite checksum is `c93dc3c2f3c25fe09c1f6aa23bce91684d60528694ef7036f2d7932c9775f68e`; the D1 dataset-manifest file SHA-256 and R5 evaluation-code SHA-256 are separately recorded in `experiment.json` and `metrics.json`.

R5 uses D1 only as the stated internal source of image bytes. It does **not** claim an external real-world evaluation dataset. R4 previously identified conflicting R1/D1 provenance descriptions; these data limitations remain applicable, so no new licensing, geographic, or real-world-source claim is made here.

## 7. Evaluation Protocol

- Fixed point-estimate operating thresholds: confidence `0.100` and `0.250`; box-matching IoU `0.50`.
- No condition-specific threshold selection or tuning.
- Inference candidate floor: confidence `0.001`; NMS IoU `0.70`; maximum 300 detections/image; image size 640; CPU.
- TP/FP/FN and thresholded precision, recall, and F1 use confidence-ranked one-to-one box matches at IoU `0.50`.
- mAP50 and mAP50-95 use the installed Ultralytics `8.4.149` `DetectionValidator`, with confidence floor `0.001` and NMS IoU `0.70`, separately for each 18-image condition. AP uses the same floor and NMS policy for all conditions; it is not a second score at confidence `0.100` or `0.250`.
- Latency is the mean inference time per image reported by the model prediction results; batch wall-time/image is also retained in machine-readable metrics.
- Confidence summaries are recorded both for detections above the operating threshold and for candidate predictions above the AP floor. Thus a null operating-point confidence summary means there were no detections above that threshold, not missing data.

## 8. Results

All rows below use confidence `0.100`, IoU `0.50`, D1 test (`18 images`, `15 GT boxes`). `Delta F1` is condition F1 minus clean F1 (`0.8824`). AP uses the validator protocol above.

| Condition | Severity | Precision | Recall | F1 | mAP50 | mAP50-95 | Delta F1 | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Clean | — | 0.789 | 1.000 | 0.882 | 0.991 | 0.792 | 0.000 | 4 | 0 |
| Brightness | L1 | 0.882 | 1.000 | 0.938 | 0.991 | 0.807 | +0.055 | 2 | 0 |
| Brightness | L2 | 0.882 | 1.000 | 0.938 | 0.995 | 0.821 | +0.055 | 2 | 0 |
| Brightness | L3 | 0.938 | 1.000 | 0.968 | 0.995 | 0.802 | +0.085 | 1 | 0 |
| Contrast | L1 | 0.882 | 1.000 | 0.938 | 0.987 | 0.778 | +0.055 | 2 | 0 |
| Contrast | L2 | 0.875 | 0.933 | 0.903 | 0.973 | 0.755 | +0.021 | 2 | 1 |
| Contrast | L3 | 1.000 | 0.733 | 0.846 | 0.971 | 0.709 | -0.036 | 0 | 4 |
| Blur | L1 | 0.875 | 0.933 | 0.903 | 0.987 | 0.749 | +0.021 | 2 | 1 |
| Blur | L2 | 0.900 | 0.600 | 0.720 | 0.927 | 0.629 | -0.162 | 1 | 6 |
| Blur | L3 | 0.000 | 0.000 | 0.000 | 0.205 | 0.115 | -0.882 | 4 | 15 |
| Noise | L1 | 0.000 | 0.000 | 0.000 | 0.787 | 0.520 | -0.882 | 0 | 15 |
| Noise | L2 | 0.000 | 0.000 | 0.000 | 0.922 | 0.593 | -0.882 | 0 | 15 |
| Noise | L3 | 0.000 | 0.000 | 0.000 | 0.237 | 0.126 | -0.882 | 0 | 15 |
| JPEG | L1 | 0.833 | 1.000 | 0.909 | 0.995 | 0.757 | +0.027 | 3 | 0 |
| JPEG | L2 | 0.933 | 0.933 | 0.933 | 0.987 | 0.735 | +0.051 | 1 | 1 |
| JPEG | L3 | 1.000 | 0.400 | 0.571 | 0.953 | 0.625 | -0.311 | 0 | 9 |
| Shadow | L1 | 0.789 | 1.000 | 0.882 | 0.991 | 0.795 | +0.000 | 4 | 0 |
| Shadow | L2 | 0.833 | 1.000 | 0.909 | 0.991 | 0.765 | +0.027 | 3 | 0 |
| Shadow | L3 | 0.824 | 0.933 | 0.875 | 0.967 | 0.814 | -0.007 | 3 | 1 |
| Rain-like overlay | L1 | 0.882 | 1.000 | 0.938 | 0.991 | 0.817 | +0.055 | 2 | 0 |
| Rain-like overlay | L2 | 0.833 | 1.000 | 0.909 | 0.991 | 0.769 | +0.027 | 3 | 0 |
| Rain-like overlay | L3 | 0.714 | 1.000 | 0.833 | 0.995 | 0.810 | -0.049 | 6 | 0 |

For every condition, TP + FN = 15. Full-precision values, secondary-threshold metrics, confidence distributions, per-class records, latency, and error cases are in `ai/research/experiments/R5/metrics.json`.

At the clean reference, macro precision/recall/F1 are `0.7895 / 1.0000 / 0.8824`; micro precision/recall are `0.7895 / 1.0000`. Macro values reflect only the class with valid support; classes without GT support remain insufficient-sample rather than being interpreted as measured failures.

## 9. Per-Class Results

The clean test split contains **15 `road_waterlogging` boxes**, **0 `open_damaged_manhole` boxes**, and **0 `damaged_missing_road_sign` boxes**. Every perturbation preserves that support. The supported class's clean metrics at confidence `0.100` are precision 0.7895, recall 1.0000, F1 0.8824, mAP50 0.99125, and mAP50-95 0.79248. At all three noise severities it has TP 0, FP 0, FN 15 at confidence `0.100`.

`open_damaged_manhole` and `damaged_missing_road_sign` are `INSUFFICIENT_SAMPLE` in every condition. Therefore the strongest/weakest affected class comparison is also `INSUFFICIENT_SAMPLE`; this experiment cannot determine which of the three classes is most vulnerable. Class-wise FP/FN and confidence deltas are retained in the JSON records.

## 10. Error Analysis

Errors are automated unmatched predictions or ground-truth boxes at confidence `0.100` and IoU `0.50`. The three generated images below were visually inspected; descriptions are limited to visible appearance and do not assert a physical cause or reinterpret labels.

- `images/d1_road_waterlogging_015.jpg`, noise L1/L2/L3: class-2 GT box `[110.976, 291.008, 505.984, 593.984]` is unmatched at the operating threshold; recorded as a false negative. The transformed image visibly has heavy fine-grained noise over a low-detail oval shape; no real-world scene interpretation is made.
- `images/d1_hn_healthy_sign_006.jpg`, blur L3: unmatched class-2 prediction at confidence approximately `0.1034`, box `[120.607, 0, 640, 293.721]`, against an empty label; recorded as a false positive. The image shows a small blue square sign on a vertical pole; the model's unmatched box is much larger than that visible sign.
- `images/d1_road_waterlogging_016.jpg`, JPEG L3: class-2 GT box `[138.016, 170.976, 573.024, 482.976]` is unmatched at the operating threshold; recorded as a false negative. The transformed image shows a blue oval-like object over a textured background with a vertical light line; its physical meaning is not inferred.

These are representative model-output observations and cautious visual descriptions, not verified image-cause explanations.

## 11. Robustness Findings

- On the fixed 18-image sample, noise had the largest mean F1 reduction across its three predeclared levels (`-0.8824`); at the fixed primary threshold all 15 waterlogging boxes were missed at L1–L3. At the AP candidate floor, noise L1 candidates had mean confidence about `0.00327` and maximum about `0.05398`; noise L2 maximum was about `0.09095`. These candidate scores were below the fixed `0.100` threshold. This describes the observed thresholded outputs; it is not a causal or general robustness claim.
- Blur L3 also had no TP at the primary threshold, with 4 FP and 15 FN. JPEG L3 had recall `0.400` and 9 FN. Contrast L3 had precision `1.000` but recall `0.733` and 4 FN.
- The largest mean F1 among the seven transformation families was brightness (`+0.0652` mean difference vs clean). This means least degraded / numerically higher F1 in these exact perturbations, not that brightness improves real-world performance.
- Rain-like L3 was associated with 2 more FP than clean while retaining recall 1.0. Synthetic shadow L3 had 1 FN.
- There is no aggregate robustness score. Ranking uses only the descriptive arithmetic mean of the three within-family F1 differences at the fixed primary threshold.
- At the secondary confidence `0.250`, the largest primary-versus-secondary F1 difference was JPEG L3 (`0.5714`), followed by blur L2 (`0.4847`). Threshold sensitivity is visible in the detailed metrics; thresholds were not adjusted.
- Mean per-image inference time across conditions was about 160 ms on the recorded CPU environment. Latency here is a local research runtime observation only.

## 12. Limitations

- Only 18 images and 15 boxes, all from one class; no conclusion for the other classes.
- All conditions reuse the same small test source, so paired transformations are not independent observations and estimates are unstable.
- D1 provenance descriptions are inconsistent as documented in R4; R5 cannot verify real-world provenance or licensing from the image bytes. R5 makes no such claim.
- Noise/blur behavior and AP can differ: noise candidate ranking retained measurable AP at some levels, while all candidate confidences were below the fixed operating threshold. Do not treat AP as thresholded operating precision/recall.
- Procedural shadow and rain-like streaks do not reproduce complete physical weather, illumination, sensor, or viewpoint processes.
- Crop/viewpoint is excluded because meaningful levels break a source annotation.
- No significance tests, confidence intervals, or causal inference were performed. Visual failure patterns were not manually reviewed.

## 13. Reproducibility

Run from the repository root with the project environment:

```powershell
.venv\Scripts\python.exe -m ai.research.r5_controlled_shift
.venv\Scripts\python.exe -m pytest backend\tests\test_research_r5.py -q
```

The generator refuses to overwrite an existing R5 dataset or experiment directory. The deterministic transformation source is `ai/research/r5_controlled_shift.py`; the source-to-output `manifest.json`, `MANIFEST.SHA256`, experiment configuration, metrics, and environment are retained under `ai/research/`. Every condition records the output-manifest SHA-256. AP is cross-checked with the installed Ultralytics `DetectionValidator`.

## 14. Scientific Conclusion

**`PARTIALLY_VALIDATED`.** This controlled study successfully generated and evaluated deterministic synthetic perturbations of the frozen D1 test images at fixed thresholds. Under this small sample, noise and severe blur showed the largest observed losses at confidence `0.100`; brightness had the highest mean F1 difference relative to clean. D1's test set supports only road-waterlogging metrics, so class comparison is insufficient. These results do not establish external generalization, physical robustness, or causes of failure.

## 15. Test Results

- R0–R5 research regression: **79 passed, 0 failed** across `test_research_r0.py`, `test_research_r1.py`, `test_research_r2.py`, `test_research_r21.py`, `test_research_r3.py`, `test_research_r4.py`, and `test_research_r5.py`.
- Relevant M8–M12 regression: **61 passed, 0 failed** across the selected epistemic-safety, security-hardening, end-to-end, batch-integration, production-readiness, product, config-hardening, and resilience-recovery test files.
- Combined: **140 passed, 0 failed**. Deprecation warnings were emitted by existing Pydantic/Starlette dependencies; no test failures resulted.

## 16. Research-Only Statement

**R5 IS RESEARCH ONLY.** These transformed images are controlled synthetic perturbations, not an independent real-world dataset. No production integration, deployment, threshold change, M1.13 change, D0 change, or R3 retraining occurred.

---

**No git commit. No git push. Stop after R5.**
