# CVKI Module 9.5 — Before/After Visual Resolution Auditing

## 1. Motivation & Purpose

When municipal authorities claim that a reported civic hazard has been repaired, independent visual auditing is required to evaluate whether the defect has genuinely ceased to be observable.

**M9.5 Before/After Visual Resolution Auditor** performs comparative analysis between pre-repair visual evidence and post-repair visual evidence. It operates as a model-independent, explainable, and epistemically bounded comparison engine.

> [!IMPORTANT]
> **Core Epistemic Principle:**
> Visual comparison produces an **EVIDENCE SIGNAL**, NOT **PHYSICAL GROUND TRUTH**.
> - `DEFECT_NOT_OBSERVED` denotes that the defect was not observed in the available after-image; it does **not** confirm that a repair is physically complete or structurally sound.
> - `DEFECT_PERSISTS` denotes visual evidence remains consistent with the previously reported defect; it does **not** assert municipal administrative failure.
> - M9.5 **never** generates `REPAIR_CONFIRMED`, `FULLY_REPAIRED`, or `COMPLETELY_FIXED`.
> - Epistemic state is strictly bounded to `EpistemicState.SYSTEM_DERIVED` or `EpistemicState.MODEL_OBSERVATION`.

---

## 2. Architecture & Pipeline Placement

M9.5 operates on standardized computer vision detection results (`StandardDetectionResult`) without importing deep learning frameworks directly:

```
[Before Detection Result] (M8 StandardDetectionResult)
            +
[After Detection Result]  (M8 StandardDetectionResult)
            ↓
[VisualResolutionAuditRequest] (Temporal, Spatial & Image Metadata)
            ↓
[M9.5 Visual Resolution Auditor]
      ├── 1. Completeness & Evidence Quality Check
      ├── 2. Temporal Consistency Verification (after > before)
      ├── 3. Spatial Distance Consistency Verification (<= 100m)
      └── 4. Threshold & Category Comparative Evaluation
            ↓
[VisualResolutionAuditResult] (DEFECT_PERSISTS / DEFECT_NOT_OBSERVED / INCONCLUSIVE / INSUFFICIENT_EVIDENCE)
            ↓
[Future M9.6 Provenance & Knowledge Graph Integration]
```

### Model-Independent Decoupling
M9.5 does **not** directly import PyTorch or Ultralytics. It evaluates outputs through the standardized M8 `StandardDetectionResult` contract, allowing seamless validation across M1.13 and future CV model versions.

---

## 3. Controlled Output States

M9.5 restricts comparative outcomes to four controlled states:

| Outcome State | Semantic Interpretation | Epistemic Bound |
| :--- | :--- | :--- |
| **`DEFECT_PERSISTS`** | Target defect is detected in after-image with confidence >= threshold. | Visual evidence remains consistent with previously reported defect. |
| **`DEFECT_NOT_OBSERVED`** | Target defect is not detected in the available after-image above threshold. | Defect was not observed in this specific image framing; does not prove physical ground truth. |
| **`INCONCLUSIVE`** | Marginal confidence, different defect observed, or temporal/spatial inconsistency. | Available signals are conflicting or inadequate to support a conclusive determination. |
| **`INSUFFICIENT_EVIDENCE`** | Missing before/after detection result, corrupt image, or degraded evidence quality. | Evidence was insufficient to baseline or conduct a valid audit. |

---

## 4. Temporal & Spatial Verification Rules

### Chronological Consistency
- `after_timestamp` must be strictly later than `before_timestamp`.
- Reversed or identical timestamps trigger `ConsistencyAssessmentState.INCONSISTENT` and return `INCONCLUSIVE` with an explicit chronological anomaly warning.

### Spatial Distance Consistency
- If GPS coordinates are available for both before and after evidence, great-circle distance is calculated using the Haversine formula.
- Tolerance: **<= 100.0 meters**.
- If distance exceeds 100 meters, spatial consistency is flagged as `INCONSISTENT`, and the outcome returns `INCONCLUSIVE` with an explainable distance report.
- If GPS is omitted, spatial consistency safely records `ConsistencyAssessmentState.UNKNOWN`.

---

## 5. Comparative Evaluation Policy

For a target issue category (e.g. `road_waterlogging`):
1. **Defect Persists:**
   - Before detection confidence >= threshold (default 0.25).
   - After detection of same category confidence >= threshold.
   - Outcome: `DEFECT_PERSISTS`.
2. **Defect Not Observed:**
   - Before detection confidence >= threshold.
   - Zero detections of target defect in after evidence.
   - Outcome: `DEFECT_NOT_OBSERVED`.
3. **Marginal Detection in After Evidence:**
   - After detection of target category is weak (confidence < threshold).
   - Outcome: `INCONCLUSIVE`.
4. **Different Category in After Evidence:**
   - Before detection was `road_waterlogging`; after detection shows `damaged_missing_road_sign`.
   - The engine does not assume the original defect was repaired.
   - Outcome: `INCONCLUSIVE` with explicit rationale.

---

## 6. Anti-Mutation & No Automatic Closure Guards

M9.5 contains hard architectural boundaries:
- **No Case Status Mutation:** Does not modify `ComplaintCase.status`.
- **No Government Status Mutation:** Does not mark official government tickets as closed.
- **No Automatic Escalation:** Does not trigger municipal penalties or automated citizen verification confirmation.
- **Audit-Only Result:** Emits `VisualResolutionAuditResult` for human operator inspection or downstream provenance recording.

---

## 7. Performance Benchmarks

Measured over 100 warmup-stabilized iterations on standard local environment:

| Benchmark Operation | Mean Latency | Median Latency | Min Latency | Max Latency | Sample Count |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M9.5 Visual Resolution Audit** | 0.0056 ms | 0.0054 ms | 0.0050 ms | 0.0120 ms | 100 |
| **Repeated Varied Audit Comparison** | 0.0051 ms | 0.0052 ms | 0.0038 ms | 0.0087 ms | 100 |

*All comparative audits complete in microsecond latency.*

---

## 8. Verification & Test Coverage

Validated across 25 test cases in `backend/tests/test_visual_resolution_auditor_m95.py`:
- Same issue persistence & defect non-observation
- Marginal after-confidence handling
- Missing before/after detection results
- Chronological timestamp ordering & reversal detection
- Haversine distance spatial consistency & thresholding
- Category mismatch handling
- Multi-detection handling & degraded quality metadata
- Absence of image hallucination
- Custom threshold validation & model-independence
- Epistemic safety & prevention of automatic case closure

---

## 9. Research Contribution

Framed as:
> *"Bounded multilingual civic-language normalization combined with model-independent visual resolution auditing."*

M9.5 demonstrates how civic intelligence systems can audit repair claims objectively and transparently without overclaiming ground truth or replacing responsible human governance.
