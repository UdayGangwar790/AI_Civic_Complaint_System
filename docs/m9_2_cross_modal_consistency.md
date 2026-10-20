# CVKI — Module 9.2: Cross-Modal Evidence Consistency & Grounding Engine

## 1. Problem Statement
In existing civic defect reporting platforms, citizen textual reports and computer vision defect observations exist in separate silos. When a citizen submits a report, the computer vision model outputs bounding boxes and confidence scores, while the text is processed independently or filed as an unverified string.

This architectural disconnection creates three critical vulnerabilities:
1. **Misaligned Claims:** A citizen may upload an image of a damaged road sign while filing a complaint describing a flooded road (due to accidental photo attachment or confusion).
2. **Unsupported Exaggerations:** Reports may describe severe physical hazards (e.g., deep open sewers) while the visual evidence depicts an unrelated minor defect.
3. **Negated Statements:** A citizen might explicitly state "no waterlogging here, but please fix the pothole", which naive keyword matchers mistakenly categorize as a waterlogging report.

> **Critical Epistemic Boundary:**  
> *"M9.2 evaluates consistency among available evidence; it does not establish physical ground truth."*  
> An alignment result is strictly an **evidence consistency signal**, not an assertion that a defect exists or that a citizen's claim is false.

---

## 2. Architecture Overview
Module 9.2 introduces the deterministic `CrossModalConsistencyEngine` under `backend/app/services/multimodal/consistency_engine.py`:

```text
[Citizen Input (Text, Language, Civic Context)]
                       +
[M8 CV Result (StandardDetectionResult)]
                       │
                       ▼
    [CrossModalConsistencyEngine]
         ├── 1. Category & Negation Extraction
         │       └── Identifies reported & negated classes
         ├── 2. CV Evidence Extraction
         │       └── Filters detections by threshold (default: 0.25)
         ├── 3. Deterministic Set Comparison
         │       ├── Negation Check (negated in text + present in CV -> CONFLICTING)
         │       ├── Full Intersection (all reported present -> ALIGNED)
         │       ├── Partial Intersection (subset present -> PARTIALLY_ALIGNED)
         │       ├── Disjoint Sets (reported != observed -> CONFLICTING)
         │       └── Empty / Missing Sets -> INSUFFICIENT_EVIDENCE
         └── 4. Explanation Generation
                 └── Emits neutral, factual cross-modal summary
                       │
                       ▼
      [EvidenceAlignmentAssessment]
         ├── state: AlignmentState
         ├── matched_issue_category: Optional[IssueCategory]
         ├── conflicting_fields: list[str]
         ├── supporting_evidence: list[str]
         ├── missing_evidence: list[str]
         └── explanation: str
                       │
                       ▼
      [AmbiguityAssessment (Derived)]
         └── state: AmbiguityState (CLEAR / AMBIGUOUS / CONFLICTING_EVIDENCE / INSUFFICIENT)
```

---

## 3. Input Specification
The engine consumes the standardized `MultimodalInput` created in M9.1:
- `text`: Optional citizen complaint text.
- `language`: Optional language code hint (`en`, `hi`, `hinglish`).
- `cv_result`: Optional `StandardDetectionResult` from M8 CV runtime.
- `civic_issue_context`: Optional `CivicIssueContext` containing pre-declared `reported_class`.
- `location_context`: Optional `MultimodalLocationContext` providing spatial metadata.

The engine handles any permutation gracefully:
- **Text only:** `INSUFFICIENT_EVIDENCE` (no CV evidence to corroborate).
- **CV only:** `INSUFFICIENT_EVIDENCE` (no citizen claims to compare).
- **Text + CV:** Full cross-modal evaluation.
- **Text + CV + Civic Context:** Comprehensive multi-attribute evaluation.

---

## 4. Deterministic Reasoning Rules

| Scenario | Citizen Text / Context | CV Detection Observations | Evaluated State | Conflicting Fields | Explanation Summary |
|---|---|---|---|---|---|
| **Direct Match** | "Open manhole on 5th cross" | `open_damaged_manhole` (0.88) | `ALIGNED` | `[]` | Issue category matches available CV evidence. |
| **Category Conflict** | "Open manhole on 5th cross" | `road_waterlogging` (0.85) | `CONFLICTING` | `["issue_category"]` | Text reports manhole, while CV indicates waterlogging instead. |
| **Partial Match** | "Waterlogging and broken sign" | `road_waterlogging` (0.78) | `PARTIALLY_ALIGNED` | `["missing_issue_category"]` | Supports waterlogging; broken sign was not observed. |
| **Negation Conflict** | "No waterlogging here" | `road_waterlogging` (0.82) | `CONFLICTING` | `["negated_issue_category"]` | Negative statement contradicts observed CV defect. |
| **Low Confidence** | "Open manhole on street" | `open_damaged_manhole` (0.15) | `INSUFFICIENT_EVIDENCE` | `[]` | CV detection below evidence threshold (0.25). |
| **Extra Unrelated CV** | "Severe waterlogging" | `road_waterlogging` (0.85) + `open_damaged_manhole` (0.35) | `ALIGNED` | `[]` | Primary reported defect matched; extra detection does not penalize. |
| **Missing Evidence** | "The sky is blue today" | `open_damaged_manhole` (0.89) | `INSUFFICIENT_EVIDENCE` | `[]` | Text does not describe a recognizable civic issue. |

---

## 5. Alignment States (`AlignmentState`)
1. `ALIGNED`: All citizen-reported civic issue categories are supported by available computer vision detection evidence.
2. `PARTIALLY_ALIGNED`: Some reported categories are supported by CV evidence, while other reported components are unobserved.
3. `CONFLICTING`: The available CV evidence indicates an issue category distinctly different from the citizen's stated category, or contradicts a negative statement.
4. `INSUFFICIENT_EVIDENCE`: Input data lacks sufficient signals (no text, no CV, unmapped issue, or detections below threshold) to evaluate alignment.
5. `NOT_EVALUATED`: Default initial state prior to pipeline execution.

---

## 6. Partial Alignment & Causality Safeguards
When a citizen reports multiple issues (e.g. "an open manhole causing waterlogging") but the camera only captures water, the engine returns `PARTIALLY_ALIGNED`.

### Causality Safeguard
The engine **never infers causality**. Co-occurring detections or text asserting that defect A caused defect B are never turned into causal claims. Explanations strictly report observational presence or absence:
- *Allowed:* "CV evidence supports road_waterlogging, but the additional reported open_damaged_manhole issue was not observed."
- *Forbidden:* "The manhole caused the waterlogging."

---

## 7. Conflict Handling & Tone Standards
A `CONFLICTING` state indicates an observational discrepancy between available evidence sources. It is never phrased as an accusation against the citizen:
- *Standard tone:* "Citizen text reports open_damaged_manhole, while the available CV evidence indicates road_waterlogging instead."
- *Forbidden tone:* "The citizen lied" or "The report is fraudulent".

---

## 8. Insufficient Evidence Discipline
Missing data is strictly categorized as `INSUFFICIENT_EVIDENCE` rather than `CONFLICTING`:
- A report with an unreadable photo is not in conflict; it has insufficient evidence.
- A report with text describing a future civic concern without defect terms is not in conflict; it has insufficient evidence.

---

## 9. Negation Handling
Bounded proximity analysis detects negation particles (`no`, `not`, `neither`, `nor`, `never`, `nahi`, `nahin`, `nhi`) within a 3-word window preceding category keywords:
- "No waterlogging" -> Negates `ROAD_WATERLOGGING`.
- "Waterlogging nahi hai" -> Negates `ROAD_WATERLOGGING`.
- Defect descriptors like "without drain cover" or "bina dhakkan" explicitly do **not** trigger negation because "without lid" is a positive symptom of an open manhole.

---

## 10. Evidence Strength & Confidence Thresholds
CV confidence scores are treated strictly as **evidence strength indicators**, not calibrated real-world probabilities:
- `DEFAULT_EVIDENCE_THRESHOLD = 0.25`: Matches M1.13 production default. Detections below this threshold are excluded from evidence matching.
- `HIGH_EVIDENCE_THRESHOLD = 0.50`: Denotes high visual certainty.

If all detections fall below 0.25, the engine returns `INSUFFICIENT_EVIDENCE` with an explicit threshold explanation.

---

## 11. Ambiguity Derivation
The engine populates `AmbiguityAssessment` derived deterministically from the alignment state:
- `CONFLICTING` -> `AmbiguityState.CONFLICTING_EVIDENCE` (`requires_clarification=True`)
- `PARTIALLY_ALIGNED` -> `AmbiguityState.AMBIGUOUS` (`requires_clarification=True`)
- `INSUFFICIENT_EVIDENCE` -> `AmbiguityState.INSUFFICIENT_EVIDENCE` (`requires_clarification=False`)
- `ALIGNED` -> `AmbiguityState.CLEAR` (`requires_clarification=False`)

*Note: Generating the actual interactive clarification dialogue for the citizen is the explicit scope of Module 9.3.*

---

## 12. Security & Epistemic Controls
1. **Zero External Calls:** 100% local, deterministic Python execution. Zero reliance on external LLM/VLM APIs.
2. **Zero Code Injection:** No `eval()`, no dynamic imports, no client-supplied class names.
3. **PII Sanitization:** Text inputs pass through `sanitize_text_pii` before entity extraction and analysis.
4. **Epistemic State Clamping:** The output `epistemic_state` is always `MODEL_OBSERVATION` and cannot be forged as `VERIFIED_EVIDENCE`.
5. **No File Path Leakage:** Supporting evidence descriptors reference semantic class names and confidence levels; internal filesystem paths are never leaked.

---

## 13. Testing
The test suite `backend/tests/test_cross_modal_consistency_m92.py` covers 23 comprehensive unit tests:
- Direct matches across all 3 M1.13 classes (manhole, road sign, waterlogging).
- Conflicting detection pairings.
- Partial alignment on multi-issue reports.
- Proximity negation detection vs. defect descriptor handling ("without drain cover").
- Low-confidence detection threshold gating.
- Unrelated extra detections.
- Malformed/failed CV input handling.
- Deterministic repeated execution.
- Causality non-inference assertions.
- Ambiguity derivation.
- Structured civic context fallbacks.

Combined M9.1 + M9.2 tests: **39 PASSED / 0 FAILED**.

---

## 14. Performance
*Measured over 100 warmup-stabilized iterations on single-host CPU:*
- **Engine Initialization:** Mean: **0.0008 ms** | Median: **0.0005 ms**
- **Single Evaluation:** **0.3329 ms** (cold)
- **Repeated Evaluation (N=100):** Mean: **0.0231 ms** | Median: **0.0173 ms**
- **Full analyze() Pipeline (N=100):** Mean: **0.0381 ms** | Median: **0.0358 ms**

---

## 15. Limitations
In strict adherence to the M9.2 scope:
1. **No conversational dialogue:** Does not interactively prompt citizens with questions (Module 9.3).
2. **No vernacular translation:** Uses keyword matching for en/hi/hinglish; does not translate regional dialects (Module 9.4).
3. **No visual change detection:** Does not compare before/after repair photos (Module 9.5).
4. **No database persistence or provenance claims:** Operates as an in-memory decision-support service (Module 9.6).

---

## 16. Future M9.3 Dependency
Module 9.3 (Active Clarification & Ambiguity Resolver) will consume the `AmbiguityAssessment` and `EvidenceAlignmentAssessment` produced by M9.2:
- When M9.2 flags `requires_clarification=True` (due to `CONFLICTING_EVIDENCE` or `PARTIALLY_ALIGNED`), M9.3 will formulate targeted, non-leading follow-up questions to resolve the discrepancy with the citizen.
