# CVKI — M6.4 Production Evidence Provenance Engine

## 1. Executive Summary & Epistemological Core

The **Evidence Provenance Engine** (M6.4) establishes strict, end-to-end traceability for every civic intelligence claim asserted across CVKI.

> **Epistemological Disclaimer**:
> Provenance establishes traceability of system claims; it does not automatically establish the truth of every external source. Provenance establishes that a given system claim was grounded in a specific data source at a specific observation time; it does not replace statutory ground inspections, nor do environmental correlations establish physical causality.

### Core Provenance Traversal

```
CLAIM 
  → EVIDENCE 
  → SOURCE 
  → SOURCE TYPE 
  → MATCHED ATTRIBUTE 
  → RETRIEVED/OBSERVED TIME 
  → FRESHNESS 
  → VERIFICATION STATE 
  → EXPLANATION 
  → DETERMINISTIC FINGERPRINT (SHA-256)
```

---

## 2. Frozen Components & Anti-Regression Invariants

As mandated by CVKI core safety guidelines:
- **CV Model**: M1.13 YOLOv8n weights (`ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`) remain frozen.
  - Required SHA-256: `602160D4851E0D79C34CB23B828BDE474FC4C164EAF1A1C2A884CFB372F4BDA3`
  - Verified SHA-256: `602160D4851E0D79C34CB23B828BDE474FC4C164EAF1A1C2A884CFB372F4BDA3` (Exact match).
- **Computer Vision & Dataset**: `ai/computer_vision/` and `dataset/` directories remain completely untouched.
- **M5.2 / M5.3 / M6.1 / M6.2 / M6.3**: Zero redesigns or duplicate verification logic. Reusable integration points are utilized.

---

## 3. Normalized Provenance Model

### `EvidenceRecord` Schema

Located at [provenance.py](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/schemas/provenance.py):

| Field | Type | Description |
|---|---|---|
| `evidence_id` | `str` | Unique record identifier (`ev_<uuid16>`) |
| `case_reference` | `Optional[str]` | Associated CVKI complaint reference ID |
| `claim_type` | `ClaimType` | Categorical classification of the claim |
| `matched_attribute` | `Optional[str]` | The specific data attribute grounded by the evidence |
| `source` | `str` | Human-readable title of provider or registry |
| `source_type` | `SourceType` | Normalized source classification enum |
| `source_url` | `Optional[str]` | Safe official HTTPS portal URL (subject to SSRF validation) |
| `provider` | `Optional[str]` | Subsystem or organization delivering the evidence |
| `observed_at` | `Optional[datetime]` | Timestamp when the phenomenon was recorded at the source |
| `retrieved_at` | `datetime` | Timestamp when CVKI ingested or verified the evidence |
| `expires_at` | `Optional[datetime]` | Cache expiration / freshness invalidation threshold |
| `freshness` | `str` | `live`, `fresh`, `cached_fresh`, `cached_stale`, `stale` |
| `status` | `str` | Lifecycle state (`active`, `stale`, `invalidated`, `superseded`) |
| `verification_state` | `VerificationState` | Deterministic verification status |
| `explanation` | `str` | Human-readable audit explanation grounded in evidence |
| `evidence_hash` | `str` | 64-character SHA-256 deterministic fingerprint |
| `version` | `int` | Sequential evidence version number (v1, v2...) |
| `invalidation_reason` | `Optional[str]` | Recorded justification when evidence is invalidated |
| `metadata` | `dict[str, Any]` | Normalized contextual details (minimized, no PII/secrets) |
| `created_at` | `datetime` | System record creation timestamp |

---

## 4. Claim Types

The engine supports 15 normalized claim types (`ClaimType` enum):
1. `detection`: CV model detection results and confidence values.
2. `location`: GPS and physical coordinates.
3. `road_identity`: Road corridor, classification, and corridor name.
4. `jurisdiction`: Administrative district, municipal ward, or boundary.
5. `road_owner`: Statutory entity owning the road asset.
6. `maintenance_authority`: Statutory agency responsible for roadway maintenance.
7. `builder_or_contractor`: Explicit concessionaire or contractor executing civil works.
8. `weather_context`: Ambient temperature, humidity, and atmospheric conditions.
9. `rainfall_context`: Precipitation accumulation and precipitation intensity.
10. `traffic_context`: Congestion metrics, delays, and traffic conditions.
11. `recurrence`: Spatial-temporal pattern of recurring complaints along corridor.
12. `hotspot_context`: Cluster density and unresolved backlog within localized radius.
13. `priority`: Triage risk score and contributing multi-factor breakdown.
14. `complaint_submission_readiness`: Evaluation of complaint package completeness for government dispatch.
15. `resolution_evidence`: Documented post-repair validation and work notes.

---

## 5. Source Types & Allowlist

The system enforces 15 validated source types (`SourceType` enum):
- `cv_model`
- `gps`
- `geocoder`
- `road_registry`
- `government_registry`
- `tender_registry`
- `concession_registry`
- `weather_provider`
- `traffic_provider`
- `open_data`
- `cvki_case_history`
- `citizen_report`
- `authority_update`
- `admin_update`
- `system_derived`

Arbitrary, unvalidated string sources are strictly rejected during schema validation.

---

## 6. Verification State Model

Deterministic verification states (`VerificationState` enum):
- `verified`: Grounded in official statutory registry, verified live provider, or confirmed repair receipt.
- `partially_verified`: Source confirmed, but high-precision boundary or attribute match is pending or approximate.
- `not_verified`: Data unconfirmed by authoritative source, or builder claim without explicit tender record.
- `stale`: Historical evidence whose TTL or validity window has lapsed.
- `unavailable`: External provider or registry offline or non-responsive.
- `system_derived`: Algorithmic CVKI inferences (recurrence, triage priority, hotspot clustering). Explicitly flagged as internal intelligence rather than statutory evidence.

*Strict Invariant*: Zero artificial numerical confidence percentages are fabricated for non-statistical evidence. CV confidence represents model detection confidence; official verification represents source provenance.

---

## 7. Deterministic Hashing Strategy

Evidence records calculate a deterministic SHA-256 fingerprint:
```python
raw = f"{claim_type}:{matched_attribute or ''}:{source}:{source_type}:{normalized_payload}"
fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()
```
- Deduplication: Identical evidence payloads yield identical fingerprints.
- Auditability: Any alteration of source, attribute, or value produces a distinct hash.
- Immutability: Historical records preserve their original content fingerprint.

---

## 8. Safety & Integrity Rules

### A. Client Claim Protection
- Clients cannot supply or override `verification_state`, `source`, `source_type`, or `evidence_hash`.
- All provenance records are generated, verified, and signed server-side.

### B. Builder Evidence Safety
- Builder or contractor attribution cannot be inferred from road ownership or municipal authority names.
- Unless backed by `tender_registry` or `concession_registry`, builder claims are automatically downgraded to `not_verified` with a cautionary note:
  > *"Safety Rule: Builder or contractor attribution cannot be inferred from maintenance authority or road owner; requires explicit tender or concession registry verification."*

### C. Non-Causal Environmental Language Invariant
- Environmental context (weather, rainfall, traffic) is strictly framed as contextual observation.
- Causal verbs ("caused", "causing", "responsible for", "due to") are automatically stripped and replaced with:
  > *"Weather conditions are consistent with recent rainfall (contextual observations only; does not establish causation)."*

### D. Source URL SSRF Protection
- All evidence URLs are checked against the M6.1 official domain allowlist and SSRF validator (`is_safe_official_url`).
- URLs targeting private IP subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.1`), cloud metadata (`169.254.169.254`), or non-HTTP schemes are stripped.

---

## 9. Evidence Versioning & Invalidation Lifecycle

1. **Append-Oriented Invalidation**: When a municipal boundary changes or evidence is superseded, `invalidate_evidence()` marks the record as `status="invalidated"` and `verification_state="not_verified"`, recording the `invalidation_reason`.
2. **Audit Integration**: All evidence invalidations trigger asynchronous audit events (`action="evidence_invalidated"`) via CVKI's `AuditService`.
3. **Historical Versioning**: Updated claims increment the `version` field (v1, v2, ...), allowing complete audit inspections of past states.

---

## 10. API Specification

### Endpoint: `GET /api/v1/provenance/cases/{reference_id}`
*(Also mapped under `/api/v1/complaint/cases/{reference_id}/provenance`)*

#### Access Control Matrix (RBAC):
- **Unauthenticated**: `401 Unauthorized`.
- **Citizen**: Allowed for own case. Sensitive metadata (internal user IDs, reviewer emails) is automatically scrubbed. Attempting to view another citizen's case returns `403 Forbidden`.
- **Authority**: Allowed for cases assigned to their account. Attempting to view unassigned cases returns `403 Forbidden`.
- **Admin**: Full access across all cases.

#### Sample Response:
```json
{
  "reference_id": "CVKI-20261014-AUTH",
  "case_reference": "CVKI-20261014-AUTH",
  "generated_at": "2026-10-14T15:15:00Z",
  "summary_verification_state": "verified",
  "claims": [
    {
      "evidence_id": "ev_be46cff7e5c943e1",
      "case_reference": "CVKI-20261014-AUTH",
      "claim_type": "detection",
      "matched_attribute": "issue_category",
      "source": "YOLOv8 M1.13 Detection Model",
      "source_type": "cv_model",
      "observed_at": "2026-10-14T15:00:00Z",
      "retrieved_at": "2026-10-14T15:00:00Z",
      "freshness": "fresh",
      "status": "active",
      "verification_state": "verified",
      "explanation": "Computer vision model detected 'pothole' with 88% confidence.",
      "evidence_hash": "cf86785138a3b26ce1fe4946860be503b53a8fb6276b9a293a4169f7e12b5e05",
      "version": 1,
      "metadata": {
        "confidence": 0.88,
        "model_version": "M1.13-yolov8n"
      }
    },
    {
      "evidence_id": "ev_0f845a76e2d19b4a",
      "case_reference": "CVKI-20261014-AUTH",
      "claim_type": "maintenance_authority",
      "matched_attribute": "maintenance_authority",
      "source": "BBMP Official Road Register",
      "source_type": "government_registry",
      "source_url": "https://bbmp.gov.in/roads",
      "freshness": "fresh",
      "status": "active",
      "verification_state": "verified",
      "explanation": "Maintenance authority verified as 'Bruhat Bengaluru Mahanagara Palike (BBMP)' (municipal_corporation).",
      "evidence_hash": "88a09fb2e05739dc62a1498b584092b7cfae4f885f81e3a2c4e511b8b73ad61a",
      "version": 1
    }
  ],
  "limitations": [
    "Provenance establishes traceability of system claims to underlying data sources; it does not replace statutory ground verification.",
    "Builder attribution requires explicit concession/tender documentation and cannot be assumed from road ownership.",
    "Environmental data provides contextual background and does not establish causation."
  ]
}
```

---

## 11. Frontend Implementation

- **API Service**: [provenanceApi.js](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/frontend/src/services/provenanceApi.js) provides authenticated calls to `/api/v1/provenance/cases/{referenceId}`.
- **Component**: [EvidenceProvenancePanel.jsx](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/frontend/src/components/EvidenceProvenancePanel.jsx) renders in both the Citizen Case Detail modal and the Staff/Admin Case Management modal.
- **Features**:
  - Verification state badges with curated accessible color coding.
  - Safe "View Official Source" outbound links.
  - Non-causal environmental context notices.
  - Technical inspector button for staff displaying SHA-256 fingerprints, versioning, and evidence IDs.
- **Styling**: Tailored CSS in [App.css](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/frontend/src/App.css) matching CVKI design language.

---

## 12. Performance Measurements (Local Benchmark)

Benchmarked with 200 operations under `benchmark_m64.py`:
- **Evidence Record Creation**: `0.053 ms / op`
- **Case Provenance Chain Build**: `0.439 ms / op`
- **Case Provenance Retrieval**: `77.786 ms / op`
- **Evidence History Retrieval**: `27.217 ms / op`

---

## 13. Test Results & Validation Summary

### Focused M6.4 Test Suite (`test_evidence_provenance_m64.py`):
32 tests covering requirements A through AF — **32/32 PASSED (100%)**:
- **A**: `test_a_provenance_schema` (PASSED)
- **B**: `test_b_evidence_creation` (PASSED)
- **C**: `test_c_evidence_fingerprint` (PASSED)
- **D**: `test_d_source_type_validation` (PASSED)
- **E**: `test_e_claim_type_validation` (PASSED)
- **F**: `test_f_verification_state_validation` (PASSED)
- **G**: `test_g_client_verification_override_rejection` (PASSED)
- **H**: `test_h_authority_evidence_provenance` (PASSED)
- **I**: `test_i_builder_evidence_safety` (PASSED)
- **J**: `test_j_geospatial_provenance` (PASSED)
- **K**: `test_k_match_quality_provenance` (PASSED)
- **L**: `test_l_weather_provenance` (PASSED)
- **M**: `test_m_rainfall_provenance` (PASSED)
- **N**: `test_n_non_causal_wording` (PASSED)
- **O**: `test_o_recurrence_provenance` (PASSED)
- **P**: `test_p_hotspot_provenance` (PASSED)
- **Q**: `test_q_priority_provenance` (PASSED)
- **R**: `test_r_resolution_evidence_provenance` (PASSED)
- **S**: `test_s_evidence_staleness` (PASSED)
- **T**: `test_t_evidence_invalidation` (PASSED)
- **U**: `test_u_evidence_versioning_history` (PASSED)
- **V**: `test_v_citizen_access` (PASSED)
- **W**: `test_w_authority_access` (PASSED)
- **X**: `test_x_admin_access` (PASSED)
- **Y**: `test_y_cross_user_denial` (PASSED)
- **Z**: `test_z_audit_integration` (PASSED)
- **AA**: `test_aa_source_url_security` (PASSED)
- **AB**: `test_ab_no_secret_leakage` (PASSED)
- **AC**: `test_ac_m61_regression` (PASSED)
- **AD**: `test_ad_m62_regression` (PASSED)
- **AE**: `test_ae_m63_regression` (PASSED)
- **AF**: `test_af_m52_regression` (PASSED)

### Regression Test Suite:
- **Full Backend Pytest**: **495 passed**, 0 failed.
- **Frontend Oxlint**: 0 errors, 5 warnings.
- **Frontend Vite Build**: 0 errors.
- **Git Diff Whitespace Check**: 0 errors.
