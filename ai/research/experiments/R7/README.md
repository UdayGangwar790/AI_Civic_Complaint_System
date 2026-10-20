# R7: Multimodal Civic Context & Evidence Fusion

**Disposition: NOT_VALIDATED; research-only; zero eligible multimodal cases.**

R7 asks whether independently represented civic context can improve the
consistency, interpretability, and evidence quality of a CVKI civic-issue
assessment without turning context into physical ground truth.

## Evidence audit

The audited R5 and R6 inputs are controlled computer-vision research artifacts
derived from D1 test images. R5 uses controlled image perturbations; R6 uses
controlled synthetic temporal sequences and explicitly lacks real-world video.
These records are not citizen reports and do not contain case-linked GPS,
jurisdiction, road ownership, authority, builder, weather, rainfall, traffic,
case-history, or authority-update observations. The available CV metrics are
aggregate research results, not case-level detections linked to civic reports.

Consequently, `case_set.json` contains zero cases. This is an explicit
insufficient-sample result, not a synthetic substitute. No synthetic context
was promoted to evidence. No alignment, conflict, fusion, or ablation metric
was calculated.

## Experiment sequence

`experiment.json` records all ten experiments in the required order, with
reproducible definitions and outcome status. Experiments requiring unavailable
case-level evidence are marked `NOT_AVAILABLE` or `INSUFFICIENT_SAMPLE`.
`config.yaml` specifies eligibility, frozen CV thresholds, modality states,
conflict policy, the descriptive E0-E5 evidence-quality scheme, and the six
ablation arms. Evidence levels are not probabilities.

`comparison.json` defines the CV-only, CV+citizen, CV+location, CV+authority,
CV+environment, and all-available arms. All share zero eligible cases, so no
comparative result is reported. `metrics.json` uses null values where a
case-level metric cannot be calculated. It does not substitute zero, a
confidence score, or a generic multimodal accuracy claim.

## Epistemic and operational safeguards

- A model observation, user report, or system-derived value remains in its
  distinct epistemic state; none becomes verified physical truth.
- GPS does not establish jurisdiction; proximity does not establish road
  ownership.
- Builder attribution requires explicit tender, contract, concession, or
  project evidence.
- Weather, rainfall, and traffic are contextual observations only; causal
  claims are prohibited by this study.
- Modality conflict is preserved for human review. No modality wins
  automatically, and disagreement does not establish model failure.
- CV confidence is not severity. Evidence quality is not probability.
- Human review remains required. R7 does not change complaint lifecycle,
  dispatch, resolution, or production behavior.

## Reproduction and integrity

Run the focused acceptance tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_research_r7.py
```

The tests verify the frozen M1.13 and R3 checkpoint SHA-256 values, D0 count
and R7 tree fingerprint, and carried-forward R5/R6 manifest and metrics
hashes. The D0 fingerprint is computed from sorted relative file paths and each
file's SHA-256 using the algorithm in `test_research_r7.py`; it supplements the
605-file count as an R7 integrity reference.

The R7 experiment outputs and report are descriptive research records only.
No model was retrained, no frozen artifact was modified, and no production
integration, lifecycle mutation, commit, or push was performed.

## Final state

| Reference | State |
|---|---|
| D0 | FROZEN (605 files) |
| M1.13 | FROZEN |
| R3 | FROZEN |
| R5 | FROZEN |
| R6 | FROZEN |
| R7 | RESEARCH ONLY |
| Production integration | FALSE |
| Git commit | NONE |
| Git push | NONE |
