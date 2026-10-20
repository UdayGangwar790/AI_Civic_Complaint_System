# R8 — Legitimate Civic-Case Acquisition & Provenance

**Status: CASE_DATASET_NOT_AVAILABLE.** R8 is a data/provenance audit only:
no model was trained and no production data was used.

## Finding

There are zero admitted R8 civic cases. D1 provides research CV images and
labels, not case-linked multimodal records. Its metadata claims four licensed
institutional source streams, but its descriptions and source scopes conflict
with other dataset records; the R4 admission audit also records unresolved
conflicts between synthesized/simulated lineage and real-world source/license
claims. Per-asset original capture records and grants were not available to
reconcile those claims. Accordingly, none of the four claimed source streams
was admitted to R8. The web-scraping candidate remains quarantined.

R5 perturbations and R6 temporal frames are derived from D1 test images. They
are not independent real-world cases, weather observations, or recorded video.
R7 likewise contains zero eligible civic cases.

## Audit results

- A nullable research case schema was created; absent fields remain explicit
  and no complete set of fields is required.
- Source records include a reference, license claim, provenance, modality,
  geographic and temporal scope claims, limitations, and audit status.
- No source cases were acquired, so privacy exposure in R8 case records is
  zero. Existing D1 QA's 122/122 privacy-clear result is reported but was not
  independently re-reviewed in R8.
- D1's existing QA reports zero exact and zero near-duplicate cross-split
  pairs; five internal near-duplicate pairs are reported. R8 recomputed zero
  sequence groups crossing splits (41 groups), zero exact D1-to-D0 image
  overlaps, and zero D1-to-D0 dHash matches at Hamming distance <= 4.
- These image-level checks do not resolve D1's source provenance and do not
  establish independent civic-case evidence.

## Freeze and reproduction

`freeze_manifest.json` pins the R8 file hashes. `dataset_manifest.json`
records the empty dataset and source-inventory checksum. R8 tests verify the
frozen M1.13/R3 references, D0 count and fingerprint, R5/R6 integrity, R7
frozen-record hashes, R8 file hashes, case absence, source-license audit
fields, privacy safeguards, and independence results.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_research_r8.py
```

No production integration, commit, or push was performed.
