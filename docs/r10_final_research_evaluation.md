# R10: Final CVKI Research v2.x Evaluation

**Final verdict: INSUFFICIENT_EVIDENCE**  
**Research-only: TRUE**  
**Production integration: FALSE**

## Objective and verdict

R10 integrates the evidence recorded in R0, R1, R2, R2.1, R3, R4, R5, R6, R7,
R8, and R9 without adding uncontrolled experiments. The overall verdict is
**INSUFFICIENT_EVIDENCE**: internal CV measurements exist, but source
independence is unresolved, the held-out test is small and class-imbalanced,
independent D2 is unavailable, and no legitimate multimodal civic cases were
admitted.

## Frozen baselines

| Baseline | Frozen reference |
|---|---|
| Production M1.13 | SHA-256 `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3` |
| Production D0 | 605 files; R10 tree fingerprint recorded in the experiment manifest |
| Research R3 checkpoint | SHA-256 `72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28` |
| R3 primary / secondary | Confidence 0.100 / 0.250; IoU 0.50 |
| R5 / R6 | Frozen manifests and metrics are hash-pinned in R8-R10 audits |
| R7 / R8 / R9 | Frozen research records; R8 and R9 artifact hashes are checked by downstream tests |

No baseline, threshold, model, or dataset was changed for R10.

## Final evaluation table

| Experiment | Research question | Dataset | Sample size | Model/checkpoint | Threshold | Metrics | Validation status | Main finding | Main limitation |
|---|---|---|---:|---|---|---|---|---|---|
| R0 | Are research registries/configuration/identity and baseline safeguards functional? | Infrastructure tests | N/A | Registry references | N/A | Framework tests | Validated for tested infrastructure | Safeguard code paths are exercised | Not a model evaluation |
| R1 | Can D1 be built and QA-audited? | D1 | 122 images; 86/18/18 | None | N/A | QA and split leakage reports | Partially validated | Structured small CV candidate exists | Provenance and source/license claims conflict across records |
| R2 | What are baseline, hard-negative, and augmentation effects? | D1; mostly 18-image test | 18 images / 15 boxes | R2 models and M1.13 reference | Mixed; R2.1 identifies 0.001 vs 0.25 mismatch | R2.1 reports 0.9649 vs 0.5714 mAP50 for conservative vs strong augmentation | Partially validated | Aggressive augmentation degraded the recorded result; hard-negative causal benefit unsupported | Small data, early threshold inconsistency; R2 experiment status remains PLANNED despite completed metrics |
| R2.1 | Are R2 claims and metrics consistent? | R2 artifacts | 18 test images; 3 negative scenes cited | R2 candidate checkpoints | Reconciled operating points | At 0.25 both negative-scene arms had 0 detections | Partially validated | Hard-negative suppression statement not supported by the comparison | Audit inherits D1 limitations |
| R3 | What does the robust baseline do on test, corruption, negative, geographic and failure slices? | D1 | 18 test images / 15 boxes; all 15 are class 2 | R3/CVR2-CV-006 | 0.100/0.250; IoU 0.50 | At 0.100 P=.7895, R=1.0000, F1=.8824; at .250 P=1.0000, R=.7333, F1=.8461 | Partially validated | Fixed-threshold within-split observations are recorded | No test support for classes 0/1; source/geography not independent |
| R4 | Does R3 generalize across an independent dataset/geography? | D2 unavailable | 0 admitted | No D2 inference | 0.100/0.250 planned only | None | Not available | No cross-dataset claim can be made | Provenance/independence admission gate failed |
| R5 | How do controlled visual perturbations affect R3? | Synthetic controlled transforms of D1 test | 18 source images, 15 boxes; 396 outputs/22 conditions | Frozen R3 | 0.100/0.250; IoU .50 | Clean primary P=.7895, R=1.0, F1=.8824, mAP50=.99125; condition results retained | Partially validated | Performance changes under fixed synthetic shifts; severe blur/noise produce failures | Repeated small source set; procedural transforms are not real weather |
| R6 | How stable are detections under controlled temporal sequences? | Synthetic frames from D1 test stills | 18 source images, 90 sequences, 900 frames | Frozen R3 | 0.100/0.250; IoU .50 | Quality-degradation primary P=.8828, R=.8533, F1=.8678; other families in R6 metrics | Partially validated | Controlled frame-level and temporal-rule behavior measured | No real-world video; repeated/altered still images; only class 2 represented |
| R7 | Does independent civic context improve multimodal evidence? | No eligible case set | 0 | No inference | Frozen refs only | No case metrics | Not validated | Available R5/R6 artifacts lack case-linked civic modalities | No citizen/location/authority/environment evidence |
| R8 | Can legitimate multimodal cases be obtained and audited? | R8_civic_cases | 0 admitted | No training | N/A | Provenance and independence audit | Case dataset not available | Schema and audit protocol created; source admissions stopped | D1 source/license lineage unreconciled |
| R9 | Does civic evidence fusion improve consistency/completeness/explainability? | Frozen R8, empty | 0 | No empirical inference | Frozen protocol only | No case metrics | Not validated | Protocol and epistemic safeguards evaluated only | Cannot rank baselines or estimate any empirical effect |

All CV metrics above are measurements on the stated research split, not
physical truth, severity, or guarantees of performance in deployment. R5/R6
variants are not independent observations.

## Claim audit

| Claim | Classification | Evidence-based assessment |
|---|---|---|
| Recorded R3 detections on D1/test | PARTIALLY_SUPPORTED | Fixed-threshold results exist, but 18 images/15 boxes and a single supported class constrain inference. |
| Conservative augmentation outperformed strong augmentation in recorded R2 comparison | PARTIALLY_SUPPORTED | Controlled configuration and R2.1 audit support this within the tested D1 conditions only. |
| Hard negatives caused fewer false positives | NOT_SUPPORTED | Both arms had zero detections at the cited 0.25 negative-scene threshold; a causal benefit is not isolated. |
| Independent cross-dataset generalization | NOT_EVALUATED | R4 did not admit D2 or run the evaluation. |
| Robustness to tested fixed synthetic perturbations | PARTIALLY_SUPPORTED | R3/R5 record controlled outcomes, including failures; no external-domain claim follows. |
| Temporal robustness on real-world videos | NOT_EVALUATED | R6 explicitly has no real video data. |
| Multimodal agreement/evidence fusion improves assessment | NOT_EVALUATED | R7/R8/R9 have zero eligible cases. |
| Authority evidence establishes maintenance/legal responsibility | NOT_EVALUATED | No verified case-linked authority evidence; no statutory responsibility study. |
| Geographic generalization | NOT_SUPPORTED | Small D1 geography slices use unverified source/location labels; no external geographic evaluation. |
| Synthetic rain-like R5 transform establishes weather/rainfall | NOT_SUPPORTED | It is a procedural image overlay, not meteorological evidence. |
| Broad real-world civic applicability | NOT_EVALUATED | No field, independent-dataset, or civic-case outcome study. |
| CV confidence is severity or verified truth | NOT_SUPPORTED | Confidence is a model output; no severity or truth ground truth is established here. |

The machine-readable classifications and citations are in
`ai/research/experiments/R10/claim_audit.json`.

## Reproducibility audit

M1.13, D0, R3, R5, R6, and the frozen R7-R9 research records have pinned
checksums and focused tests. R2/R3 experiment IDs, configuration, metrics,
environment, and seeds are present; per-file SHA-256 values are summarized
in `reproducibility_audit.json`.

Known gaps remain: R2 `experiment.json` files say `PLANNED` while their
`metrics.json` files say `COMPLETED`; R2 metrics use different confidence
protocols, addressed by R2.1; no standalone R0/R1 experiment dossier is
present; and D1 source-to-asset licenses cannot be independently checked.
No D2/R8 case checksum exists because no case assets were admitted.

## Data leakage and independence

D1's prior QA report records zero exact and zero near cross-split pairs. R10
recomputed 41 sequence groups with no split crossing, and compared 122 D1
images to 300 D0 images with zero exact SHA-256 and zero dHash matches at
Hamming distance <=4. These checks do not prove source legitimacy or semantic
independence. R5/R6 are known derivatives of D1 test images and are not
independent cases. Because D1 source identity/license provenance is
unreconciled, overall source independence remains **INCONCLUSIVE**.

## Epistemic audit

Protocol-level invariants remain: model output, user reports, and system
derivations are not verified physical truth; CV confidence is not severity;
weather and traffic are not causal proof; government status is not automatic
CVKI resolution; field audit is not physical truth; recommendations are not
government orders; and multimodal agreement is not ground truth. Human review
remains required. Since R8/R9 have no cases, empirical violation rates are
unavailable.

## Limitations

- D1 is only 122 images; its provenance/license and real-versus-simulated
  source claims conflict.
- Test positives are only 15 instances, all road_waterlogging; class-specific
  class-0 and class-1 test performance is unavailable.
- D2 is unavailable, so cross-dataset and verified geographic generalization
  were not tested.
- R5 transforms and R6 sequences are synthetic derivatives of D1 test data.
- R7/R9 have no independent multimodal case dataset; R8 did not admit cases.
- Language methods and geographic labels do not establish verified citizen
  meaning or jurisdiction here.
- 2D image detections do not measure physical depth, severity, causation, or
  legal responsibility.
- Government integration and statutory authority are not established by the
  research benchmark.
- Local CPU latency is environment-specific and not a field performance claim.

## Final regression and integrity

The full R0-R10 research regression (including R2.1) and relevant M8-M12
regression ran across **45 test files**: **569 passed, 0 failed, 0 errors,
13 warnings**. Warnings are dependency/API deprecations (Pydantic config,
Starlette/httpx TestClient, and the deprecated HTTP 422 constant); no tests
failed or errored. Exact counts are also recorded in
`ai/research/experiments/R10/experiment.json` and `metrics.json`.

## Final verdict and project state

**INSUFFICIENT_EVIDENCE.** Internal observations and synthetic robustness
measurements do not establish independent generalization, real-world civic
performance, or multimodal evidence-fusion benefit.

| Required state | Final value |
|---|---|
| D0 | FROZEN |
| M1.13 | FROZEN |
| R3 | FROZEN |
| R5 | FROZEN |
| R6 | FROZEN |
| R7 | FROZEN RESEARCH RECORD |
| R8 | FROZEN RESEARCH RECORD |
| R9 | FROZEN RESEARCH RECORD |
| R10 | FINAL RESEARCH RECORD |
| Production integration | FALSE |
| Model replacement | NONE |
| Git commit | NONE |
| Git push | NONE |
