# R9: Multimodal Civic-Case Evaluation

**Empirical status: NOT_VALIDATED**  
**Protocol status: PARTIALLY_VALIDATED**  
**Eligible cases: 0**

## Research question

Does combining independently represented civic evidence improve consistency,
completeness, and explainability of civic-issue assessment?

## Input and method

R9 uses only the frozen R8 dataset. R8's verified admission result is
`CASE_DATASET_NOT_AVAILABLE`, with zero admitted cases. R9 therefore validates
the preregistered protocol and safety requirements; it does not execute
empirical case-level inference.

The six baselines, modality states, consistency categories, E0-E5 descriptive
evidence levels, conflict preservation, builder-evidence requirements,
environmental-context boundaries, and explanation fields are defined in
`ai/research/experiments/R9/config.yaml`. E0-E5 are evidence categories, not
probabilities.

## Findings

No eligible cases exist for agreement, conflict detection, evidence
completeness, unsupported inference, traceability, or ablation comparisons.
Those metrics are null and explicitly marked unavailable or descriptive-only.
No multimodal accuracy, preferred baseline, case explanation, or fabricated
confidence was reported.

The protocol requires disagreements to remain explicit as
`CONFLICT_REQUIRES_REVIEW`; it does not select a winning modality. Weather,
rainfall, and traffic remain contextual observations, not causal proof.
Builder/contractor attribution requires explicit tender, contract,
concession, project-document, or official-registry evidence. Every future
explanation must trace to source records, preserve uncertainty, and state
`Human review: REQUIRED`.

## Conclusion

R9's empirical question is **NOT_VALIDATED** because its input dataset has zero
eligible cases. Protocol validation does not establish real-world effectiveness
or that any baseline is better than another. Use
`ai/research/experiments/R9/freeze_manifest.json` and the focused R9 tests to
reproduce the protocol-integrity check.

No production integration or lifecycle mutation occurred; no commit or push
was made.
