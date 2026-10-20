# CVKI Research R4 — Cross-Dataset Generalization

**Status:** `RESEARCH_ONLY`  
**Primary result:** `CROSS_DATASET_EVALUATION_NOT_AVAILABLE`  
**Dataset:** D2 was not created; no D2 evaluation was run.  
**Frozen model:** R3 `CVR2-CV-006`, SHA-256 `72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28`  
**Primary operating point:** confidence `0.100`, IoU `0.50`; secondary reference confidence `0.250`  
**Report timestamp:** 2026-10-19

## 1. Executive Summary

R4 stopped at `CVR2-CV-011` because the reviewed R1 records do not establish a traceable, independently sourced and licensed dataset from which to construct D2. D2 was not manufactured, no D2 manifest was frozen, and R3 was not evaluated on D2. The cross-dataset result is therefore **unavailable**, not a negative model result.

The D1 records also conflict about source inventories and whether the images are sourced observations or synthesized/simulated examples. With no defensible source-to-asset chain and no evidence excluding shared source imagery, the D1-to-D2 independence requirement cannot pass. `CVR2-CV-012` through `CVR2-CV-015` were not run.

All three requested classes have zero admitted D2 samples and are marked `INSUFFICIENT_SAMPLE`. R4 makes no claim about class performance, generalization, geographic effects, production readiness, or comparative superiority.

## 2. Research Question

The planned question was whether frozen R3 performance generalizes to independent, class-balanced civic imagery and whether aggregate performance is mainly driven by `road_waterlogging`. This question remains unanswered because there is no admissible D2 evaluation set.

## 3. Frozen Artifact Verification

The integrity gate supplied for this task reported all three frozen checks as passed:

| Artifact | Supplied verified value | R4 handling |
|---|---:|---|
| M1.13 SHA-256 | `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3` | Recorded, not recomputed |
| D0 file count | 605 | Recorded, not recomputed |
| R3 checkpoint SHA-256 | `72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28` | Recorded, not recomputed |

R4 did not modify M1.13, D0, the R3 checkpoint, the production provider/APIs, or the production threshold. D1 is read-only under R4; the R4 test suite checks the asset hashes against the existing D1 manifests and its documented composite checksum.

## 4. D2 Construction

The approved target was 30 images per class (90 total), with no manufactured balancing. The actual number of D2 assets admitted was **zero**. No D2 directory, annotations, manifest, or evaluation split was created. This is an intentional provenance stop, not a claim that no suitable public research data exists anywhere.

## 5. Provenance & Licensing

The D1 card, R1 report, source registry, image manifest, and dataset registry were inspected. The source card/report claim five streams, while `metadata/sources.json` lists four permitted source IDs and one quarantined candidate. Source names and scopes differ across those records. The dataset registry further describes D1 as containing “scientifically synthesized and controlled real-world simulated samples,” while per-image manifest entries assign particular real-world source IDs and licenses.

These records do not reconcile the claims or supply an independently auditable source-to-image capture record and license grant for constructing an independent D2. R4 therefore admitted no imagery and records D2 source, license, and geography as unknown/unverified. D1's metadata assertions were not promoted into verified evidence.

## 6. D2 QA

No D2 assets or annotations exist to validate. Image format, dimensions, annotation coordinates, orphan files, class distribution, and box counts are **not applicable**. `dataset_construction_audit.json` records this explicitly rather than treating absent material as a passed QA audit.

## 7. Leakage/Duplicate Audit

Exact duplicates, near duplicates, sequence relationships, transformed copies, and shared source imagery could not be audited without admitted D2 assets. Those checks are recorded as `NOT_RUN_NO_D2_ASSETS` or `NOT_ESTABLISHED`; independence is **not established**. No cross-dataset independence claim is made.

## 8. CVR2-CV-011 — D2 Dataset Construction & Audit

**Status:** `D2_NOT_AVAILABLE`. The source/provenance contradictions described above prevented admission. No D2 checksum can be calculated. D2 has zero admitted assets; this must not be interpreted as an evaluated class distribution.

## 9. CVR2-CV-012 — Class-Balanced R3 Evaluation

**Status:** `NOT_RUN_NO_VALID_D2`. No final evaluation manifest or inference run was created. The planned confidence thresholds remain 0.100 (primary) and 0.250 (secondary), with IoU 0.50; neither threshold was evaluated on D2 or tuned against D2.

## 10. CVR2-CV-013 — Cross-Dataset Generalization

**Status:** `CROSS_DATASET_EVALUATION_NOT_AVAILABLE`. Since D2 is absent and independence from D1 cannot be established, no D1-vs-D2 generalization result exists.

## 11. CVR2-CV-014 — Geographic / Source Domain Generalization

**Status:** `NOT_RUN_NO_VALID_D2`. No verified D2 source or geographic labels exist. No geographic slice analysis or causal geographic interpretation was performed.

## 12. CVR2-CV-015 — Class-Specific Failure Analysis

**Status:** `NOT_RUN_NO_VALID_D2`. D2 counts are zero for all three required classes; each is marked `INSUFFICIENT_SAMPLE`:

| Class ID | Class | D2 sample status |
|---:|---|---|
| 0 | `open_damaged_manhole` | `INSUFFICIENT_SAMPLE` |
| 1 | `damaged_missing_road_sign` | `INSUFFICIENT_SAMPLE` |
| 2 | `road_waterlogging` | `INSUFFICIENT_SAMPLE` |

The key question—whether R3's aggregate performance is mainly driven by road-waterlogging—remains unanswered.

## 13. D1 vs D2

| Dataset / split | Images | GT boxes | Confidence | IoU | Result | Macro / micro |
|---|---:|---:|---:|---:|---|---|
| D1 / R3 held-out test (historical CVR2-CV-006 report) | 18 | 15 | 0.100 | 0.50 | Precision 0.7895; Recall 1.0000; F1 0.8824; mAP50 0.9912; mAP50-95 0.7925; TP 15; FP 4; FN 0 | Not recorded in the historical R3 report |
| D2 / test (R4) | N/A | N/A | 0.100 planned | 0.50 planned | Not evaluated; D2 unavailable | N/A |

The historical D1 row is reported only as context from R3, not as a result of R4. It is not an independent cross-dataset comparison. R4 macro/micro results are unavailable.

## 14. Macro vs Micro Metrics

No R4 metrics were computed. Precision, recall, F1, mAP50, mAP50-95, TP, FP, FN, macro precision/recall/F1, and micro precision/recall are all **N/A** for D2. Image count and GT box count are likewise N/A. The threshold metadata is recorded in each experiment record; absence of evaluation is not represented as a zero score.

## 15. Class-Specific Results

There are no D2 class-specific results. All three classes have `INSUFFICIENT_SAMPLE` because there are no admitted D2 samples. No aggregate or historical R3 result is used to mask this limitation.

## 16. Error Analysis

There were no R4 model predictions, so there are no R4 TP/FP/FN cases or visual model errors to categorize. The blocking issue is evidence quality and provenance reconciliation, not an observed model failure.

## 17. Statistical Limitations

No R4 evaluation sample exists. Rates, uncertainty intervals, significance tests, and class comparisons cannot be estimated. The small historical D1 R3 test set is not a substitute for an independent D2 sample.

## 18. Threats to Validity

- R1 source metadata and dataset narratives conflict.
- D1 source-to-asset licensing/provenance cannot be independently confirmed from the reviewed records.
- The source imagery may overlap D1, and no D2 sample exists to conduct duplicate/sequence checks.
- No verified geographic strata or class-balanced evaluation data are available.
- Historical R3 D1 metrics do not answer independent cross-dataset performance.

## 19. What Was Proven

- The supplied frozen-artifact gate reported D0, M1.13, and R3 checks passed; R4 recorded those values without rerunning the gate.
- Reviewed R1 records were insufficient to establish D2 provenance and independence under the stated admission rules.
- No D2 assets or evaluation results were created or claimed.
- R4 records thresholds, model identity, checkpoint digest, statuses, and unknown provenance fields.

## 20. What Was NOT Proven

R4 did not prove universal generalization, geographic causation, robustness in any under-sampled class, superiority over M1.13, or production readiness. It did not prove that suitable external data do not exist. It did not convert model observations into verified evidence or confidence into physical severity.

## 21. Next Research Milestone

No R5 work is started or authorized here. A future R4 continuation would first require independently verifiable, licensed source assets with per-asset provenance and an explicit D1 independence audit. Any further evaluation would need a new, documented approval and a frozen dataset/model/threshold/evaluation-code manifest before inference.

## 22. Tests

`backend/tests/test_research_r4.py`: **9 passed**. It checks frozen-reference attestations without rerunning the upstream artifact gate, verifies D1 asset hashes and composite checksum, ensures D2 and annotations are not fabricated, checks leakage/class/threshold/provenance records, protects final evaluation, checks TP + FN = GT whenever counts are present, and enforces research-only isolation.

## 23. Full Regression

| Regression group | Result |
|---|---:|
| R0, R1, R2, R2.1, R3, R4 research tests | **68 passed, 0 failed** |
| Relevant M8–M12 CV, multimodal, production-safety, and end-to-end suites | **394 passed, 0 failed** |

The runs emitted dependency/deprecation warnings only. No R4 model evaluation is included in regression.

## 24. Frozen Artifact Integrity

Final status follows the supplied gate: **D0 = FROZEN; M1.13 = FROZEN; R3 = FROZEN RESEARCH CHECKPOINT**. No integrity values were recalculated by the R4 dataset-admission work.

## 25. Files Created/Modified

Created:

- `ai/research/experiments/R4/experiments.json`
- `ai/research/experiments/R4/dataset_construction_audit.json`
- `ai/research/experiments/R4/frozen_reference_attestation.json`
- `backend/tests/test_research_r4.py`
- `docs/r4_cross_dataset_generalization.md`

No existing R1/R2/R3 data, production code, production APIs, model weights, or thresholds were intentionally modified.

---

**D0 = FROZEN**  
**M1.13 = FROZEN**  
**R3 = FROZEN RESEARCH CHECKPOINT**  
**D2 = RESEARCH EVALUATION ONLY (NOT CREATED)**  
**R4 = RESEARCH ONLY**  
**PRODUCTION INTEGRATION = FALSE**  
**NO GIT COMMIT = TRUE**  
**NO GIT PUSH = TRUE**
