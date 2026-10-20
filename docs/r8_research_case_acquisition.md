# R8: Legitimate Multimodal Civic Case Acquisition & Provenance

**Status: CASE_DATASET_NOT_AVAILABLE**  
**R8 is research-only. No model training or production data access occurred.**

## Objective and decision

R8 assessed whether the repository contains a legitimate, independently
auditable multimodal civic-case corpus suitable for R9. The result is **zero
admitted cases**. No case records were fabricated, and no external sources
were scraped or accessed.

## Sources and provenance

D1 contains 122 research CV images and labels, but it is not a civic-case
dataset. D1's source registry claims four permitted institutional streams and
per-asset licenses. The dataset card, source registry, manifests, and R4
dataset-construction audit do not reconcile source names/scopes or whether
assets are actual captures versus synthesized/controlled simulations. Original
per-asset acquisition records and license grants are unavailable. Therefore,
the source/license claims are recorded but not admitted as verified source
evidence. The unlicensed web-scrape candidate remains quarantined.

R5 consists of controlled perturbations of D1 test images. R6 consists of
synthetic temporal frames derived from D1 test stills and states real-world
video evaluation is unavailable. Neither is independent real-world civic
case data. R7 contains no eligible multimodal cases.

See `ai/research/experiments/R8/source_inventory.json` for source references,
license claims, scope, limitations, and audit decisions; see
`provenance.json` for audited local artifact hashes.

## Schema and privacy

`case_schema.json` permits missing optional modalities and requires provenance
and a verification state. It preserves evidence epistemic states and does not
make schema validity a truth claim. Privacy policy requires generalized
location and review/redaction of faces, plates, names, phone numbers, emails,
home addresses, and other identifiers. No case data was admitted. D1's
previous QA report states 122/122 images were privacy-clear, but R8 did not
independently re-review those images.

## Independence and leakage

The D1 QA record reports zero exact and zero near-duplicate cross-split pairs,
with five near-duplicate pairs inside D1. R8 recomputed 41 sequence groups and
found none spanning splits. It compared all 122 D1 images against 300 D0
images: zero exact SHA-256 matches and zero 64-bit dHash matches within
Hamming distance 4. These findings do not verify source independence or
resolve D1 license/provenance discrepancies.

R5/R6 source references establish known derivation from D1 test images; their
synthetic variants do not count as independent real-world cases. Overall
civic-case independence is **NOT_ESTABLISHED**.

## Reproducibility and freeze

The empty dataset, case schema, source inventory, provenance, privacy and
independence audits, metrics, configuration, and experiment record are pinned
by `ai/research/experiments/R8/freeze_manifest.json`.

Run focused checks:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_research_r8.py
```

## Conclusion

R8 establishes a reproducible intake schema and source-audit protocol, but
does not establish a legitimate civic-case dataset. The proper R8 outcome is
**CASE_DATASET_NOT_AVAILABLE**. R9 may validate its protocol and safeguards
only; it must not perform empirical multimodal case evaluation without
eligible R8 cases.

No production code, data, APIs, lifecycle behavior, or model weights were
modified. No commit or push was made.
