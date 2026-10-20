# R7: Multimodal Civic Context & Evidence Fusion Study

**Overall status: NOT_VALIDATED**  
**Evaluation type: DESCRIPTIVE_ONLY**  
**Eligible case count: 0**  
**R7: RESEARCH ONLY; production integration: FALSE**

## 1. Research objective

Assess whether independently represented civic context can improve
consistency, interpretability, and evidence quality in CVKI civic-issue
assessment without allowing contextual signals to become physical ground truth.

## 2. Research questions

The planned comparisons ask whether citizen language, geographic evidence,
authority records, or environmental observations agree with a CV observation;
whether modalities disagree; whether a deterministic synthesis improves
traceability and completeness; and whether disagreement can be preserved
without automatically selecting a winner.

## 3. Frozen references

| Reference | Recorded value | R7 check |
|---|---|---|
| M1.13 | SHA-256 `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3` | Exact checkpoint hash |
| D0 | 605 files | File count and R7 tree fingerprint |
| R3 checkpoint | SHA-256 `72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28` | Exact checkpoint hash |
| R3 primary threshold | 0.100 | Recorded; no new inference performed |
| R3 secondary threshold | 0.250 | Recorded; no new inference performed |
| R3 IoU | 0.50 | Recorded |
| R5 manifest / metrics | SHA-256 recorded in the R7 experiment and provenance records | Verified |
| R6 manifest / metrics | SHA-256 recorded in the R7 experiment and provenance records | Verified |

R7 reads but does not modify any of these references. The D0 tree fingerprint
is an R7 integrity reference formed from sorted relative paths and file
SHA-256 values; it does not replace the frozen-reference count.

## 4. Available modalities

R5 provides checksummed controlled perturbation artifacts of D1 test images.
R6 provides checksummed controlled synthetic temporal sequences and aggregate
CV metrics. These establish only the lineage and results of prior CV research.
The R6 record states that real-world video evaluation is unavailable.

Aggregate CV research artifacts exist, but no individual CV observations are
linked to independently sourced civic cases. Thus CV observation is
`INSUFFICIENT_SAMPLE` for this case-level study.

## 5. Unavailable modalities

No legitimate case-linked records were found for citizen language, GPS, road
identity, jurisdiction, road owner, maintenance authority, builder or
contractor, weather, rainfall, traffic, case history, or authority updates.
No synthetic values were introduced to fill these gaps.

## 6. Dataset and case construction

The case inclusion rule requires a legitimate case-linked CV observation and
independent provenance for every additional modality. R5/R6 benchmark
observations do not meet that rule. The evaluation set therefore contains
**zero cases**, explicitly represented in `ai/research/experiments/R7/case_set.json`.
The available research artifacts are listed separately in
`ai/research/experiments/R7/provenance.json` and are not treated as civic
case evidence.

## 7. Provenance

The R7 provenance record lists source paths, SHA-256 values, and the limited
role of each source. R5 and R6 files are classified as controlled CV research,
not actual weather, citizen, authority, or location evidence. With no case
records, case-level provenance completeness is not measurable.

## 8. CV-language consistency

**NOT_AVAILABLE.** No legitimate citizen-language examples linked to
case-level CV observations were available. No `ALIGNED`, `PARTIAL`, `CONFLICT`,
or `AMBIGUOUS` labels were assigned.

## 9. Geographic consistency

**NOT_AVAILABLE.** No case-linked GPS, road, or jurisdiction records were
available. No road ownership was inferred from proximity.

## 10. Authority evidence consistency

**NOT_AVAILABLE.** No case-linked ownership or maintenance-authority evidence
was available. Builder/contractor attribution remains unsupported and requires
explicit tender, contract, concession, or project evidence.

## 11. Environmental context

**NOT_AVAILABLE.** No case-linked real weather, rainfall, or traffic
observations were available. The study makes no causal claims. In particular,
rainfall is not evidence that rain caused waterlogging, and traffic is not
evidence of road damage.

## 12. Cross-modal conflicts

**INSUFFICIENT_SAMPLE.** No independent case modalities were available for
comparison. The preregistered policy preserves all observations and emits
`CONFLICT_REQUIRES_REVIEW` when a supported conflict is present; it never
selects a winning modality automatically.

## 13. Evidence-quality synthesis

The deterministic descriptive scale is defined in `config.yaml`:

- **E0** — no usable evidence
- **E1** — single weak observation
- **E2** — single structured observation
- **E3** — multiple independent observations
- **E4** — corroborated evidence
- **E5** — verified official evidence

This scale is neither probability nor confidence. No case received an E0-E5
score because there were no eligible cases. Any future output must identify
contributing, agreeing, conflicting, verified, missing, and uncertain
modalities individually.

## 14. Ablation

Six arms are reproducibly defined in `comparison.json`: CV only; CV plus
citizen language; CV plus location; CV plus authority; CV plus environmental
context; and all available modalities. The common case count is zero, so
consistency, conflict detection, completeness, explanation quality, and
uncertainty preservation cannot be compared. No arm was optimized or ranked.

## 15. Explainability

The explanation schema is evidence-traceable by design: observed CV output,
supporting context, authority evidence, conflicts, uncertainty, provenance,
and required human review. **INSUFFICIENT_SAMPLE:** no case explanation was
generated because no case evidence was available.

## 16. Security and epistemic validation

The dedicated R7 tests enforce the frozen hashes and D0 integrity reference,
R5/R6 checksums, provenance references, modality state preservation,
non-causal treatment of weather/rainfall/traffic, explicit builder evidence,
conflict preservation, explicit unavailable status, human review, no lifecycle
mutation, and no production integration.

## 17. Metrics

All case-level metrics are either `NOT_AVAILABLE` or `DESCRIPTIVE_ONLY` with
null values and explicit reasons in `metrics.json`. Agreement, conflict
detection, completeness, unsupported-inference rate, traceability, and
human-review rates were not calculated. There is no suitable ground truth for
precision, recall, or F1. No generic multimodal-accuracy value or fabricated
confidence percentage is reported.

## 18. Limitations

This is an evidence-availability and protocol audit, not an empirical
multimodal comparison. Controlled computer-vision benchmarks cannot establish
real civic context. The absence of eligible data cannot establish that any
modality would be useful or not useful, and the study does not represent all
Indian civic environments.

## 19. Reproducibility

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_research_r7.py
```

Experiment definitions and outcomes are in `ai/research/experiments/R7/`.
Frozen checkpoint hashes and the carried-forward R5/R6 checksums are pinned in
the experiment record and checked by the tests.

## 20. Scientific conclusion

**NOT_VALIDATED.** The available evidence does not answer whether multimodal
civic context improves assessment consistency, interpretability, or evidence
quality. The only supported conclusion is that the R5/R6 research artifacts
do not supply case-linked independent civic modalities for this evaluation.
Any future analysis requires legitimate provenance-bearing cases and must
retain the epistemic boundaries and human-review requirement.

## Final state

| Required state | Value |
|---|---|
| D0 | FROZEN |
| M1.13 | FROZEN |
| R3 | FROZEN |
| R5 | FROZEN |
| R6 | FROZEN |
| R7 | RESEARCH ONLY |
| Production integration | FALSE |
| Git commit | NONE |
| Git push | NONE |
