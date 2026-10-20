# R9 — Multimodal Civic-Case Evaluation

**Empirical evaluation: NOT_VALIDATED.**  
**Dataset status: CASE_DATASET_NOT_AVAILABLE.**  
**Protocol validation: PARTIALLY_VALIDATED.**

R9 is restricted to the frozen R8 case dataset. R8 contains zero admitted
cases because no civic source corpus with reconciled per-asset provenance,
permission, and independent source evidence was available. Therefore R9
performs protocol and infrastructure validation only. It creates no cases,
labels, explanations, metrics, or synthetic evidence.

## Frozen protocol

The six comparison arms (CV only; CV+citizen; CV+location; CV+authority;
CV+environment; all available modalities), consistency labels, E0-E5
descriptive evidence levels, explicit conflict handling, authority evidence
requirements, environmental non-causality, and evidence-traceable explanation
fields are recorded in `config.yaml` and `comparison.json`.

The baseline arms are not ranked or assumed better. Agreement does not imply
correctness. Conflicts remain visible and require human review.

## Results

`case_results.json` has zero records. Case-level metrics are null with
`NOT_AVAILABLE` or `DESCRIPTIVE_ONLY` statuses and reasons. No generic
multimodal accuracy or confidence percentages are reported. Empirical
consistency, completeness, explanation quality, ablation effects, and
ground-truth metrics remain unevaluated.

## Reproduction and freeze

R9 provenance pins the R8 freeze manifest, empty dataset manifest, M1.13/R3,
and R5/R6 references. The R9 freeze manifest records hashes of every R9
research file. Tests verify these inputs and the epistemic, conflict,
uncertainty, no-fabrication, and research-only boundaries.

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_research_r9.py
```

No production integration, lifecycle change, commit, or push was performed.
