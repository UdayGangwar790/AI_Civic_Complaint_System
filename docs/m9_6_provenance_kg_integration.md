# CVKI — Module 9.6: Provenance & Knowledge Graph Integration

## 1. Executive Summary & Architecture

Module 9.6 integrates the outputs of **M9.4 (Multilingual Vernacular Normalizer)** and **M9.5 (Before/After Visual Resolution Auditor)** into CVKI's foundational trust and relationship engines:
1. **M6.4 Evidence Provenance Engine**: Provides immutable, content-addressed, cryptographic traceability for every multimodal transformation and comparative visual inspection.
2. **M6.5 Civic Knowledge Graph**: Organizes normalized vernacular civic entities, detection events, before/after comparative audits, and physical infrastructure assets into a structured, queryable knowledge network.

M9.6 is strictly an **integration layer**. It does NOT independently assert ground truth, does NOT declare that external citizen claims are true, and does NOT promote statistical visual non-detection into physical government repair confirmation.

```
 Citizen Input / Vernacular Text (M9.4)           Before / After Visual Audit (M9.5)
                   │                                                │
                   ▼                                                ▼
       VernacularNormalizationResult                  VisualResolutionAuditResult
                   │                                                │
 ┌─────────────────┴────────────────────────────────────────────────┴────────────────┐
 │                      Module 9.6: Provenance & KG Integration                      │
 ├─────────────────────────────────────────┬─────────────────────────────────────────┤
 │ M6.4 Evidence Provenance Subsystem      │ M6.5 Civic Knowledge Graph Subsystem    │
 │ - ClaimType.VERNACULAR_NORMALIZATION    │ - NodeType.VERNACULAR_NORMALIZATION     │
 │ - ClaimType.VISUAL_RESOLUTION_AUDIT     │ - NodeType.VISUAL_RESOLUTION_AUDIT      │
 │ - Deterministic SHA-256 fingerprinting  │ - RelationType.HAS_VERNACULAR_NORMALIZ. │
 │ - Strict Epistemic State preservation   │ - RelationType.NORMALIZED_AS            │
 │ - Audit history & invalidation ledger   │ - RelationType.VISUAL_AUDIT_OF          │
 │                                         │ - RelationType.BEFORE/AFTER_OBSERVATION │
 └─────────────────────────────────────────┴─────────────────────────────────────────┘
```

---

## 2. M9.4 Vernacular Normalization Provenance

When raw vernacular text (e.g. Hindi, Hinglish, regional colloquialisms) is processed by M9.4, an immutable evidence record is created in M6.4:
- **ClaimType**: `ClaimType.VERNACULAR_NORMALIZATION`
- **SourceType**: `SourceType.SYSTEM_DERIVED` (original user statement remains `SourceType.CITIZEN_REPORT` with `USER_REPORTED` semantics).
- **VerificationState**:
  - `VerificationState.SYSTEM_DERIVED` for affirmative, non-negated mappings.
  - `VerificationState.NOT_VERIFIED` for negated (`AssertionType.NEGATED`) or uncertain expressions.
  - **CRITICAL**: Never promoted to `VERIFIED` automatically.
- **Payload Metadata**:
  - `original_text`, `normalized_text`, `detected_language`, `script`
  - `canonical_civic_concepts`: e.g. `["open_damaged_manhole"]`
  - `assertion_type`: `ASSERTED`, `NEGATED`, `UNCERTAIN`, `QUESTION`
  - `lexical_normalization_confidence`: statistical text confidence.
  - `confidence_type`: Explicitly labeled `"lexical_confidence"` (NOT physical defect probability, NOT CV confidence, NOT repair confirmation).
  - `normalization_engine_identity`: e.g. `m9_4_vernacular_normalizer`.

---

## 3. M9.5 Visual Resolution Audit Provenance

When pre- and post-repair imagery are evaluated by M9.5, an immutable evidence record is cataloged in M6.4:
- **ClaimType**: `ClaimType.VISUAL_RESOLUTION_AUDIT`
- **SourceType**: `SourceType.SYSTEM_DERIVED`
- **VerificationState**:
  - `VerificationState.SYSTEM_DERIVED` for `DEFECT_PERSISTS` or `DEFECT_NOT_OBSERVED`.
  - `VerificationState.NOT_VERIFIED` for `INCONCLUSIVE` or `INSUFFICIENT_EVIDENCE`.
  - **CRITICAL**: Never promoted to `VERIFIED` automatically.
- **Payload Metadata**:
  - `case_reference`, `issue_category`, `outcome`
  - `before_observation`, `after_observation`
  - `evidence_quality`, `temporal_consistency`, `spatial_consistency`
  - `before_model_identity`, `after_model_identity`
  - `model_hash`: `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3`
  - `thresholds`, `explanation`, `limitations`
  - `is_repair_confirmed`: `False` (Explicitly bounded: visual absence of defect does not constitute ground truth confirmation).

---

## 4. Epistemic Mapping & Safety Rules

Every M9 output adheres to a four-tier epistemic state hierarchy:

| Tier | Category | Semantics | M9 Mapping |
| :--- | :--- | :--- | :--- |
| **Tier 1** | `USER_REPORTED` | Citizen claims, unfiltered text | Citizen vernacular input |
| **Tier 2** | `MODEL_OBSERVATION` | CV bounding boxes, detection events | Before/after detection observations |
| **Tier 3** | `SYSTEM_DERIVED` | Normalized taxonomy, alignment scores, comparative audits | M9.4 normalized output, M9.5 audit reports |
| **Tier 4** | `VERIFIED_EVIDENCE` | Multi-source official ground inspection confirmation | **NEVER generated automatically by M9** |

### Hard Safety Constraints:
1. `DEFECT_NOT_OBSERVED` != `REPAIR_CONFIRMED`.
2. Negated vernacular ("manhole khula nahi hai") must produce `VerificationState.NOT_VERIFIED` and NEVER generate positive defect assertions.
3. Inconclusive or insufficient image comparisons must produce `VerificationState.NOT_VERIFIED`.

---

## 5. Cryptographic Fingerprinting

M9.6 employs CVKI's standardized SHA-256 evidence hashing (`calculate_evidence_hash`) to produce deterministic, content-addressed fingerprints without storing sensitive payloads or internal filesystem references:
```python
evidence_hash = calculate_evidence_hash(
    claim_type=claim_type.value,
    matched_attribute="vernacular_normalization" | "visual_resolution_audit",
    source=source_identifier,
    source_type=source_type.value,
    value=canonical_fingerprint_dict,
)
```
- **Deduplication**: Identical semantic claims for the same case reuse existing active records, preventing log spam and graph bloat.
- **Zero Tampering**: Changes in normalized concepts or audit outcomes produce distinct cryptographic hashes.

---

## 6. Invalidation & Audit Versioning

M9 evidence supports full invalidation without data loss:
1. When evidence is invalidated via `invalidate_m9_evidence(evidence_id, reason)`:
   - Historical record is preserved with `status = "invalidated"`.
   - Verification state drops to `VerificationState.NOT_VERIFIED`.
   - `invalidation_reason` and actor ID are permanently recorded.
   - Original `evidence_hash` is retained for audit traceability.
2. Downstream Knowledge Graph safeguard:
   - In `explain_relationship`, if any supporting evidence record has `status == "invalidated"` or `verification_state == NOT_VERIFIED`, the edge's effective verification state is immediately downgraded to `VerificationState.NOT_VERIFIED`.
   - An explanatory limitation note is appended: `"Supporting evidence was invalidated; this edge cannot support a verified conclusion."`

---

## 7. Knowledge Graph Node Model

M9.6 defines two canonical node types in M6.5:
1. **`NodeType.VERNACULAR_NORMALIZATION`**:
   - Canonical key: `vernacular_norm:<case_ref>:<norm_id>`
   - Metadata: `detected_language`, `script`, `canonical_civic_concepts`, `assertion_type`, `lexical_confidence`, `epistemic_state`.
2. **`NodeType.VISUAL_RESOLUTION_AUDIT`**:
   - Canonical key: `visual_audit:<case_ref>:<audit_id>`
   - Metadata: `outcome`, `evidence_quality`, `temporal_consistency`, `spatial_consistency`, `model_hash`, `is_repair_confirmed: False`.

---

## 8. Knowledge Graph Relationship Model

```
 Case Node (NodeType.CASE)
   │
   ├──────► HAS_VERNACULAR_NORMALIZATION ──► Vernacular Normalization Node
   │                                              │
   │                                              ├──► NORMALIZED_AS ──► Civic Issue Node
   │                                              └──► SUPPORTED_BY ──► Evidence Node
   │
   └──────► VISUAL_AUDIT_OF ───────────────► Visual Resolution Audit Node
                                                  │
                                                  ├──► BEFORE_OBSERVATION ──► Before Detection Node
                                                  ├──► AFTER_OBSERVATION ──► After Detection Node
                                                  └──► SUPPORTED_BY ──► Evidence Node
```

### Prohibited Edges:
Under no circumstances will M9.6 create:
- `REPAIRED`
- `FIXED`
- `REPAIR_CONFIRMED`
These concepts are statutory conclusions reserved strictly for authorized civic processes (e.g. M7.6 citizen verification or official inspection).

---

## 9. RBAC & Multi-Tenant Isolation

Access to M9 provenance and knowledge graph structures adheres to CVKI role boundaries:
- **Citizen**: Restricted strictly to their own case provenance chains (`case.user_id == authenticated_user.id`). Internal reviewer IDs and system notes are redacted.
- **Authority**: Restricted to complaints within assigned jurisdictions.
- **Admin**: Full audit visibility including invalidated history and version iterations.

---

## 10. Security & Privacy Guarantees

1. **No Internal Path Exposure**: Absolute paths (e.g., `best.pt`, Windows drive letters, local cache directories) are never embedded into evidence records, graph nodes, or edge metadata.
2. **PII Sanitization**: Phone numbers, emails, and sensitive keys are stripped prior to hashing and graph persistence.
3. **No Dynamic Network Calls**: Operates entirely offline with zero external web APIs or uncontrolled URL lookups.

---

## 11. Test Coverage & Verification Matrix

The test suite (`backend/tests/test_m96_provenance_kg.py`) validates all 25 mandated requirements:

| # | Test Name | Focus | Result |
| :--- | :--- | :--- | :--- |
| 1 | `test_01_m94_result_creates_provenance` | M9.4 produces valid EvidenceRecord | **PASS** |
| 2 | `test_02_m95_result_creates_provenance` | M9.5 produces valid EvidenceRecord | **PASS** |
| 3 | `test_03_deterministic_fingerprint` | SHA-256 fingerprint determinism | **PASS** |
| 4 | `test_04_provenance_contains_epistemic_state` | Explicit lexical confidence & non-ground-truth tags | **PASS** |
| 5 | `test_05_m94_remains_user_reported_system_derived` | Rejects unearned promotion to VERIFIED | **PASS** |
| 6 | `test_06_m95_remains_model_observation_system_derived` | Bounded model observation state | **PASS** |
| 7 | `test_07_no_automatic_verified_evidence` | DEFECT_NOT_OBSERVED != VERIFIED | **PASS** |
| 8 | `test_08_invalidation_works` | State transition to NOT_VERIFIED with reason | **PASS** |
| 9 | `test_09_invalidated_evidence_cannot_support_verified_state` | Graph explanation downgrades invalidated edges | **PASS** |
| 10 | `test_10_m94_kg_node_creation` | Canonical VERNACULAR_NORMALIZATION node | **PASS** |
| 11 | `test_11_m95_kg_node_creation` | Canonical VISUAL_RESOLUTION_AUDIT node | **PASS** |
| 12 | `test_12_correct_kg_relationships` | Topology & prohibition of REPAIRED edges | **PASS** |
| 13 | `test_13_no_dangling_edges` | Referential integrity across nodes and edges | **PASS** |
| 14 | `test_14_relationship_explanation_works` | M6.5 explain_relationship exposes M9 provenance | **PASS** |
| 15 | `test_15_citizen_ownership_isolation` | Tenant isolation across complaint cases | **PASS** |
| 16 | `test_16_authority_assignment_isolation` | Case-level authority isolation | **PASS** |
| 17 | `test_17_admin_access` | Multi-version historical access | **PASS** |
| 18 | `test_18_no_pii_leakage` | PII sanitization in record metadata | **PASS** |
| 19 | `test_19_no_credential_leakage` | Token/secret masking | **PASS** |
| 20 | `test_20_deterministic_rebuild` | Idempotent rebuild_case_graph | **PASS** |
| 21 | `test_21_duplicate_evidence_prevention` | Deduplication by content hash | **PASS** |
| 22 | `test_22_no_duplicate_kg_nodes` | Idempotent ensure_node enforcement | **PASS** |
| 23 | `test_23_m64_regression` | Backward compatibility with core provenance | **PASS** |
| 24 | `test_24_m65_regression` | Backward compatibility with core KG engine | **PASS** |
| 25 | `test_25_m91_to_m95_regression` | Integration integrity with M9.1–M9.5 | **PASS** |

---

## 12. Local Engineering Performance Baseline

Benchmarked across 100 warmup-stabilized iterations (`backend/tests/benchmark_m96_provenance_kg.py`):

| Operation | Sample Count | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M9.4 Provenance Record Creation** | 100 | 1.3916 | 1.3275 | 0.1221 | 3.4660 |
| **M9.5 Provenance Record Creation** | 100 | 0.0751 | 0.0687 | 0.0653 | 0.1976 |
| **M9.6 Graph Insertion (Vernacular)** | 100 | 3.2009 | 2.9462 | 2.4446 | 7.8353 |
| **M9.6 Subgraph Retrieval (depth=2)** | 100 | 13.8278 | 12.9023 | 11.0478 | 78.1706 |
| **M9.6 Graph Rebuild** | 100 | 12.4798 | 12.1913 | 6.5873 | 27.8389 |
| **M9.6 Relationship Explanation** | 100 | 0.0927 | 0.0875 | 0.0789 | 0.2824 |

*Note: Measured as a local engineering baseline under Python 3.13 on Windows; not claimed as production scale.*

---

## 13. Limitations

1. **Local Graph Storage**: In-memory repository fallback is utilized during unit testing; MongoDB deployment requires index maintenance on `canonical_key` and `canonical_edge_key`.
2. **Lexical Scope**: Normalization provenance reflects lexicon dictionary mappings and does not infer conversational subtleties outside predefined civic domains.
3. **No Direct Ground Truth**: Audit records reflect comparative detector absence and camera angle alignment, which cannot substitute for physical engineering certification.

---

## 14. M9.7 Validation Boundary

M9.6 completes the data linkage pipeline for CVKI M9. Module 9.7 serves as the **End-to-End System Validation and Sign-Off Gate**, exercising the entire chain from Citizen Input -> Vernacular Normalization -> CV Output -> Consistency Engine -> Active Clarification -> Visual Audit -> Provenance -> Knowledge Graph, without introducing any new product functionality.
