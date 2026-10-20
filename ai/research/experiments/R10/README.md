# R10 — Final CVKI Research v2.x Evaluation

**Final verdict: INSUFFICIENT_EVIDENCE.**  
**Production integration: FALSE.**

R10 synthesizes the existing R0–R9 record only. It introduces no model,
training, data acquisition, or uncontrolled performance experiment.

## Result

The record supports narrow observations on the small D1 test split and
controlled synthetic image/sequence perturbations. At R3's primary threshold
(0.100, IoU 0.50), the recorded D1 test metrics are P=0.7895, R=1.0000,
F1=0.8824 on 18 images and 15 positive boxes; every positive test box is
road_waterlogging. At 0.250, P=1.0000 and R=0.7333 on the same cases. These
are small within-corpus measurements, not broad generalization claims.

R4 could not construct D2. R5 and R6 share D1 test sources and use controlled
synthetic transforms/sequences; they are not independent real-world weather
or video evidence. R7 found zero eligible multimodal cases, R8 admitted no
case sources because D1 provenance/license claims remain unreconciled, and R9
performed protocol validation only. Consequently, multimodal evidence fusion,
authority attribution, geographic generalization, real-world video, and broad
field applicability are not validated.

## Claim and integrity audits

- `claim_audit.json` classifies key claims as supported, partially supported,
  descriptive-only, not supported, or not evaluated, with evidence and
  limitations.
- `reproducibility_audit.json` pins model/data/study checksums and records
  missing or inconsistent records, including stale R2 experiment statuses.
- `leakage_audit.json` distinguishes reported split checks from recomputed
  hashes and marks source independence INCONCLUSIVE.
- `epistemic_audit.json` lists the required epistemic invariants and makes
  protocol-level versus empirical validation explicit.
- `metrics.json` contains the stage-by-stage evaluation table and final
  regression summary.

## Reproduction

Run R0-R10 research tests (including R2.1) and the relevant M8-M12 regression
suites from the repository root:

```powershell
$paths = @()
$paths += Get-ChildItem -LiteralPath 'backend\tests' -File -Filter 'test_research_r*.py' | ForEach-Object { $_.FullName }
$paths += Get-ChildItem -LiteralPath 'backend\tests' -File -Filter 'test_m*.py' | ForEach-Object { $_.FullName }
$names = @('test_cv_m113_parity.py','test_cv_m113_provider.py','test_cv_model_registry.py','test_cv_provider_abstraction.py','test_cv_runtime.py','test_cv_standardized_contract.py','test_cv_provenance_kg.py','test_multimodal_spi_m91.py','test_cross_modal_consistency_m92.py','test_active_clarification_m93.py','test_vernacular_normalizer_m94.py','test_visual_resolution_auditor_m95.py')
foreach ($name in $names) {
    $file = Join-Path 'backend\tests' $name
    if (Test-Path -LiteralPath $file) { $paths += (Resolve-Path -LiteralPath $file).Path }
}
$paths = $paths | Sort-Object -Unique
& '.\.venv\Scripts\python.exe' -m pytest $paths -q --tb=short
```

The exact pass/fail/error/warning counts are recorded in `experiment.json`,
`metrics.json`, and the final report after regression execution.

## Final state

D0, M1.13, R3, R5, R6, R7, R8, and R9 remain frozen. R10 is the final
research record. No production integration, model replacement, commit, or
push occurred.
