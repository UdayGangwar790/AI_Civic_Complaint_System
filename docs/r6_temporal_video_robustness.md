# R6 — Temporal / Video Robustness Study

**Overall status:** `PARTIALLY_VALIDATED`  
**Experiment IDs:** `CVR2-CV-017` through `CVR2-CV-024`  
**REAL_WORLD_VIDEO_EVALUATION:** `REAL_WORLD_VIDEO_EVALUATION_NOT_AVAILABLE`  
**Evaluation type:** `CONTROLLED_SYNTHETIC_TEMPORAL_EVALUATION`  
**R6:** research only; no production integration  
**Evaluation timestamp:** `2026-10-19T17:59:15.930630+00:00` (UTC)

## 1. Objective

Measure the frame-to-frame stability of frozen R3 detections on deterministic sequences generated from approved research still images. Compare unfiltered event detection with simple fixed temporal-persistence rules and controlled frame-sampling rates. No sequence is represented as recorded video or as independent real-world evidence.

## 2. Research Questions

The study addresses:

1. How often does a detection persist across the frames where its annotated object is visible?
2. Do two-frame, three-frame, or one-missing-frame rules suppress transient false detections, and what event-recall/delay trade-off is observed?
3. How do sampling every frame, every second frame, or every third frame change measured persistence and event metrics?
4. What is observed under small synthetic translation, a short synthetic occlusion, and controlled quality changes?

Temporal persistence is an output-stability observation; it does not establish that a physical civic defect exists.

## 3. Frozen References

| Artifact | Frozen reference | R6 guard |
|---|---|---|
| D0 | `ai/computer_vision/dataset_m1_13`, 605 files | File-count assertion |
| M1.13 weights | SHA-256 `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3` | SHA assertion |
| R3 checkpoint | `ai/research/experiments/R3/CVR2-CV-006/weights/best.pt`, SHA-256 `72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28` | SHA assertion |
| R5 manifest | SHA-256 `d36bd0f653c5650f628ad26d9397b5e843154931f23177918235b94b2f899f0e` | Freeze assertion |
| R5 metrics | SHA-256 `a07f0ac9271b5af85689346632e181201fb453918408539505ed23059c39b13e` | Freeze assertion |

R6 performed inference only. It did not retrain or modify M1.13/R3, modify D0/R5, tune thresholds, or activate a production path.

## 4. Real-Video Availability Audit

No video files (including MP4, AVI, MOV, MKV, WEBM, MPEG/MPG, or M4V) were found in the repository's research/data/artifact paths searched (`ai`, `data`, `runs`, `frontend`, `backend`, and `docs`). No source repository record was found documenting a usable, independently auditable real-world video dataset with video-level provenance, license, annotations, and checksum. R1 documentation describes still-image sources and licenses, not video.

R4 had already noted unresolved inconsistencies in the R1/D1 provenance descriptions. R6 therefore does not assign any unverified source/license/geographic facts to individual D1 frames. The source identity and checksums below refer to the local D1 research files only.

**Result:** `REAL_WORLD_VIDEO_EVALUATION_NOT_AVAILABLE`. The rest of this report is strictly a controlled synthetic temporal evaluation.

## 5. Synthetic Sequence Methodology

The source is the D1 `test` split: 18 still images, each used to make one sequence of each type, for 90 sequences and 900 ordered frames. The 18 images contain 15 annotated boxes, all class 2 (`road_waterlogging`); there are no test boxes for classes 0 or 1. The same source images and annotations are repeated across sequence types and frames; these repeated frames are not independent samples.

Each frame record in `ai/research/datasets/R6_controlled_sequences/manifest.json` stores source image and label paths/hashes, source split, sequence ID, frame ID/order, transformation parameters, deterministic seed, generation timestamp, output image/label paths and hashes, object IDs, dimensions, and manifest reference. The manifest SHA-256 is:

`2c793e05dbc068d0ea1907e466a352a06b0728330fef580cd20485464408b348`

R6 data are generated only under `ai/research/datasets/R6_controlled_sequences/`; results and per-experiment records are under `ai/research/experiments/R6/`. No video container was fabricated.

## 6. Sequence Types

All sequence lengths and transformation schedules were fixed before evaluating the model. Each sequence has 10 frames.

| Sequence type | Fixed generation rule | Annotation handling |
|---|---|---|
| `STATIC_SEQUENCE` | Repeat the decoded source image in ten ordered frames | Source labels retained |
| `SMALL_PERTURBATION_SEQUENCE` | Repeating brightness factors 0.98/1.00/1.02/0.99/1.01 and seeded RGB Gaussian noise sigma 0/1/2/1/0.5 | Geometry unchanged |
| `CAMERA_MOTION_SEQUENCE` | Per-frame translation: dx `[-8,-6,-4,-2,0,2,4,6,8,10]` pixels; dy `[-4,-3,-2,-1,0,1,2,3,4,5]` pixels | Boxes translated and clipped to visible image bounds; each frame revalidated |
| `OCCLUSION_SEQUENCE` | Local synthetic dark rectangle over normalized region `[0.38,0.34,0.62,0.66]`, opacity 0.82, frames 4 and 5 only | Full source boxes retained behind the artificial occluder |
| `QUALITY_DEGRADATION_SEQUENCE` | Symmetric ten-frame schedules of Gaussian blur (0–1.6 px), seeded Gaussian noise (sigma 0–4), and JPEG quality 95–55 | Geometry unchanged |

These are controlled image-sequence perturbations, not simulations of full physical camera, occlusion, weather, or motion processes.

## 7. Frame-Level Baseline

Predictions were made independently per frame using the frozen R3 checkpoint, prediction floor `0.001`, NMS IoU `0.70`, max detections 300, image size 640, CPU. Point metrics use fixed confidence thresholds `0.100` (primary) and `0.250` (secondary), with one-to-one class-consistent matching at IoU `0.50`. No threshold was tuned for any sequence.

Each type has 180 evaluated frames (18 sequences × 10 frames) and 150 ground-truth box instances across the repeated frames. Per-frame TP/FP/FN, precision, recall, F1, GT boxes/object IDs, and every detection above the primary threshold (class, confidence, box, match outcome) are retained in the `frame_level_records` of `metrics.json`.

### Primary operating point: confidence 0.100, IoU 0.50

| Sequence type | Frames | GT boxes | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Static | 180 | 150 | 150 | 30 | 0 | 0.8333 | 1.0000 | 0.9091 |
| Small perturbation | 180 | 150 | 150 | 27 | 0 | 0.8475 | 1.0000 | 0.9174 |
| Camera motion | 180 | 150 | 150 | 27 | 0 | 0.8475 | 1.0000 | 0.9174 |
| Occlusion | 180 | 150 | 150 | 42 | 0 | 0.7812 | 1.0000 | 0.8772 |
| Quality degradation | 180 | 150 | 128 | 17 | 22 | 0.8828 | 0.8533 | 0.8678 |

### Secondary operating point: confidence 0.250, IoU 0.50

| Sequence type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Static | 100 | 0 | 50 | 1.0000 | 0.6667 | 0.8000 |
| Small perturbation | 124 | 1 | 26 | 0.9920 | 0.8267 | 0.9018 |
| Camera motion | 107 | 0 | 43 | 1.0000 | 0.7133 | 0.8327 |
| Occlusion | 98 | 2 | 52 | 0.9800 | 0.6533 | 0.7840 |
| Quality degradation | 68 | 0 | 82 | 1.0000 | 0.4533 | 0.6239 |

For all conditions and thresholds, `TP + FN = GT`. Frame-level macro/micro measures are not used to imply broader class coverage: only road-waterlogging is represented.

### Measured inference latency

| Sequence type | Mean model inference time per frame (ms) |
|---|---:|
| Static | 146.5 |
| Small perturbation | 138.3 |
| Camera motion | 130.8 |
| Occlusion | 126.3 |
| Quality degradation | 125.0 |

These are local CPU inference timings from the 10-frame batched evaluation; they do not establish a real-time rate. Batch wall-clock measurements and per-frame values are retained in `metrics.json`.

## 8. Temporal Metrics and Matching Rules

- **Frame matching:** confidence-descending, greedy one-to-one matching; same class and IoU ≥ 0.50. A GT box can match at most one prediction per frame.
- **Detection persistence:** correctly matched object-frames divided by visible GT object-frames.
- **Track continuity:** adjacent sampled transitions where the same source object ID has a correct match in both frames divided by adjacent sampled transitions where that GT object is visible in both frames. Source annotations provide the object identity; this is not a learned tracker.
- **Detection gaps:** consecutive missing object detections after at least one detection. Reported gap lengths are in original frame units. Recovery rate is the fraction of such gaps followed by a correct re-detection before sequence end; sequences with no gaps have `null` recovery rate.
- **False-positive association:** class-consistent greedy highest-IoU box association at IoU ≥ 0.50, allowing one missing sampled frame for Rule C. Candidate ties are resolved deterministically.
- **Event definition:** each annotated source object in a source-image sequence is one GT event. Each unmatched prediction track is one false event if it passes the selected temporal rule.
- **Rule A / `NO_TEMPORAL_FILTER`:** any matched frame makes a GT event detected; any false-positive track is counted.
- **Rule B / `2_FRAME_PERSISTENCE`:** require at least two adjacent sampled detections.
- **Rule C / `3_FRAME_PERSISTENCE`:** require at least three adjacent sampled detections.
- **Rule D / `1_FRAME_GAP_TOLERANCE`:** require two same-object detections no more than two sampled positions apart.
- **Event precision/recall:** matched GT events over detected GT plus accepted FP events; detected GT events over all GT events. Detection delay is the first frame at which the rule is satisfied.

These deterministic rules are analysis baselines, not a validated tracking algorithm.

## 9. Temporal Filtering Experiments

Every result below uses stride 1 (all ten frames), confidence `0.100`, IoU `0.50`.

| Sequence type | Rule | Event precision | Event recall | Accepted FP events | Mean detection delay (frames) |
|---|---|---:|---:|---:|---:|
| Static | No filter | 0.833 | 1.000 | 3 | 0 |
| Static | 2-frame | 0.833 | 1.000 | 3 | 1 |
| Static | 3-frame | 0.833 | 1.000 | 3 | 2 |
| Static | 1-frame gap tolerance | 0.833 | 1.000 | 3 | 1 |
| Small perturbation | No filter | 0.577 | 1.000 | 11 | 0 |
| Small perturbation | 2-frame | 0.789 | 1.000 | 4 | 1 |
| Small perturbation | 3-frame | 0.833 | 1.000 | 3 | 2 |
| Small perturbation | 1-frame gap tolerance | 0.789 | 1.000 | 4 | 1 |
| Camera motion | No filter | 0.652 | 1.000 | 8 | 0 |
| Camera motion | 2-frame | 0.789 | 1.000 | 4 | 1 |
| Camera motion | 3-frame | 0.789 | 1.000 | 4 | 2 |
| Camera motion | 1-frame gap tolerance | 0.789 | 1.000 | 4 | 1 |
| Occlusion | No filter | 0.577 | 1.000 | 11 | 0 |
| Occlusion | 2-frame | 0.577 | 1.000 | 11 | 1 |
| Occlusion | 3-frame | 0.789 | 1.000 | 4 | 2 |
| Occlusion | 1-frame gap tolerance | 0.577 | 1.000 | 11 | 1 |
| Quality degradation | No filter | 0.625 | 1.000 | 9 | 0 |
| Quality degradation | 2-frame | 0.750 | 1.000 | 5 | 1 |
| Quality degradation | 3-frame | 0.824 | 0.933 | 3 | 3 |
| Quality degradation | 1-frame gap tolerance | 0.750 | 1.000 | 5 | 1 |

The 3-frame rule reduced false events in four synthetic types, but did not suppress persistent false detections in the static sequence. In the quality sequence it reduced accepted false events from 9 to 3 while one of 15 GT object-events failed the 3-frame rule. This is a direct observed precision/recall/delay trade-off; it does not establish the rule as suitable for deployment.

## 10. Frame-Sampling Experiment

Sampling is a post-hoc selection of already inferred frames, not a separate measured run at reduced cadence. Every sequence began with ten inferred frames; selected counts are 10, 5, and 4 at strides 1, 2, and 3. Projected cost is the sum of measured per-frame model inference times for selected indices, not observed end-to-end latency at that rate.

| Sequence type | Stride | Selected frames / 10 | Projected fraction of frame inference | No-filter event precision | No-filter event recall |
|---|---:|---:|---:|---:|---:|
| Static | 1 | 10 | 100% | 0.833 | 1.000 |
| Static | 2 | 5 | 50% | 0.833 | 1.000 |
| Static | 3 | 4 | 40% | 0.833 | 1.000 |
| Small perturbation | 1 | 10 | 100% | 0.577 | 1.000 |
| Small perturbation | 2 | 5 | 50% | 0.750 | 1.000 |
| Small perturbation | 3 | 4 | 40% | 0.750 | 1.000 |
| Camera motion | 1 | 10 | 100% | 0.652 | 1.000 |
| Camera motion | 2 | 5 | 50% | 0.682 | 1.000 |
| Camera motion | 3 | 4 | 40% | 0.750 | 1.000 |
| Occlusion | 1 | 10 | 100% | 0.577 | 1.000 |
| Occlusion | 2 | 5 | 50% | 0.600 | 1.000 |
| Occlusion | 3 | 4 | 40% | 0.833 | 1.000 |
| Quality degradation | 1 | 10 | 100% | 0.625 | 1.000 |
| Quality degradation | 2 | 5 | 50% | 0.682 | 1.000 |
| Quality degradation | 3 | 4 | 40% | 0.682 | 1.000 |

For the quality sequence, matched-frame persistence was 0.853 at stride 1, 0.840 at stride 2, and 0.867 at stride 3; track continuity was 0.785, 0.717, and 0.733, respectively. The non-monotone values and small repeated source set do not support a sampling-rate recommendation.

## 11. Controlled Camera-Motion Experiment

Translation used the predeclared horizontal/vertical offsets in §6, bilinear resampling, and a fixed neutral fill. Bounding boxes were translated and clipped to frame bounds before inference. The sequence retained 15 GT boxes per source image at all 10 frames (150 total for this condition), and annotations were validated.

At confidence `0.100`, camera motion yielded TP 150, FP 27, FN 0, precision 0.8475, recall 1.0000, F1 0.9174. At confidence `0.250`, it yielded TP 107, FP 0, FN 43, precision 1.0000, recall 0.7133, F1 0.8327. These values concern bounded synthetic translations of D1 stills only.

## 12. Class-Wise Results

Source test support is:

| Class ID | Class | Unique source GT boxes | R6 status |
|---:|---|---:|---|
| 0 | `open_damaged_manhole` | 0 | `INSUFFICIENT_SAMPLE` |
| 1 | `damaged_missing_road_sign` | 0 | `INSUFFICIENT_SAMPLE` |
| 2 | `road_waterlogging` | 15 | `VALID_SAMPLE` |

All reported valid class metrics are for road-waterlogging. Each synthetic frame repeats an annotation from those same 15 boxes; the 150 per-condition frame-level GT instances are not 150 independent objects. No temporal robustness conclusion is made for classes 0 or 1.

## 13. Temporal Error Analysis

Error types are assigned automatically from fixed-threshold frame matches and deterministic box associations; this is not a manually verified visual audit. Across the saved representative error records, there were 27 persistent FP tracks, 15 transient FP tracks, and 6 temporary FN cases. The sequence has no learned tracker, so identity switches are `NOT_ASSESSED`; duplicate event merges are also `NOT_ASSESSED`.

Representative observations:

- **Persistent false positive:** `static_sequence__d1_road_waterlogging_016`, class 2, frames 0–9. An unmatched prediction with confidence approximately 0.139 and box `[240.06,169.96,577.48,418.24]` persists across the sequence. Frame 0 also has a separate matched detection for the GT box `[138.02,170.98,573.02,482.98]`; the persistent box did not match a GT box at IoU 0.50.
- **Temporary false negatives:** `quality_degradation_sequence__d1_road_waterlogging_015`, class 2, object ID 0 is missed at frames 2, 3, 4, and 6, with GT box `[110.976,291.008,505.984,593.984]` on those frames. It is detected in other frames. The automatic association records missed frame IDs, GT box, class, and sequence.
- **Transient false positive:** representative single-frame unmatched detections are in the machine-readable `error_analysis` array with sequence/frame, class, confidence, box, rule, and empty matched-GT association.

These records describe model outputs under defined synthetic inputs; they do not assign a physical cause.

## 14. Limitations

- No legitimate, independently auditable real-world video dataset was available; therefore real-world temporal robustness was not evaluated.
- Only 18 unique D1 still images are used. Sequence/frame repetitions are correlated and are not independent samples.
- Only road-waterlogging has GT support; classes 0 and 1 are insufficient-sample.
- R1/D1 provenance discrepancies remain unresolved; R6 does not make a new claim about the original license, geography, or capture conditions.
- Synthetic occlusion, small perturbations, quality degradation, and translation are narrow deterministic image operations. They do not represent all physical scene changes or camera motion.
- Camera motion is a small translation, not a perspective change, rotation, rolling shutter, or moving camera capture.
- The sampling-rate “cost” is projected from model inference times on frames already processed at full rate; it is not a measured lower-rate pipeline run.
- No confidence intervals, significance tests, causal inference, or universal claims are made. Threshold sensitivity is visible in the primary/secondary results and no per-condition threshold was chosen.
- Physical defect presence cannot be verified by temporal persistence alone.

## 15. Reproducibility

Environment: Python 3.13.1, Windows 11, CPU, Ultralytics 8.4.149, NumPy 2.5.3, Pillow 12.3.0.

Generate the dataset and run the frozen R3 inference:

```powershell
.venv\Scripts\python.exe -m ai.research.r6_temporal_study
```

Re-evaluate an existing generated sequence manifest without regenerating frames:

```powershell
.venv\Scripts\python.exe -m ai.research.r6_temporal_study --evaluate-existing
```

The sequence manifest and `MANIFEST.SHA256`, frame-level results, experiment JSON records `CVR2-CV-017` through `CVR2-CV-024`, and top-level `experiment.json`/`metrics.json` are retained under `ai/research/`. Evaluation-code SHA-256: `478f91a1ebd70c818c44e0987424a215240f0a0576b44ea578a5d3510841b742`. Metrics SHA-256: `907fc80c19372d344f67b7eb9990169fd47d1315c812b98cdf743513feca7831`.

Regression verification: R0–R6 research suites **87 passed, 0 failed**; selected relevant M8–M12 suites **61 passed, 0 failed**. Combined: **148 passed, 0 failed**. Existing dependency deprecation warnings were observed.

## 16. Scientific Conclusions

**`PARTIALLY_VALIDATED`.** The deterministic sequence generation, label propagation/validation, frozen-model inference, frame-level metrics, sampling summaries, and prespecified temporal-rule comparisons completed on the available synthetic sequence set. Two- and three-frame filters were associated with fewer counted FP events in several synthetic conditions, but static persistent false positives remained, and the 3-frame rule missed one GT event in the quality-degradation condition. Sampling results were descriptive and post hoc on already inferred frames.

**`REAL_WORLD_VIDEO_EVALUATION_NOT_AVAILABLE`.** The study does not establish real-world video performance, general temporal robustness, physical truth, or a production-ready temporal filter.

---

**R6 is research only. No production integration. No commit. No push. Stop after R6.**
