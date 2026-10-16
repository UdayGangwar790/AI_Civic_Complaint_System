# Module M7.1: Government Integration Foundation

## 1. Executive Summary & Epistemological Disclaimer

> **Core System Principle:**
> *"M7.1 provides the integration foundation. It does not establish that CVKI is connected to any government portal unless an official adapter is actually configured and confirmed."*

Module M7.1 establishes the foundational server-side architecture required for safe, auditable, government-facing closed-loop integrations. 

### Epistemological Integrity Requirements:
- **No Simulation Masquerading as Official:** CVKI never fabricates external government reference IDs, simulated portal acceptances, or dummy acknowledgment stamps in production.
- **Safe Default (`NOT_CONFIGURED`):** In any default, unconfigured, or pre-production deployment, all integration attempts resolve honestly to `NOT_CONFIGURED`.
- **Truthful Disclosure Notice:** When an integration is not configured, the server returns the mandatory truthful disclosure:
  > *"Government portal integration is not configured. CVKI has prepared the structured complaint package but has not submitted it to a government system."*
- **Authoritative Separation:** Internal CVKI case lifecycles (`draft`, `submitted_to_cvki`, `under_review`, `assigned`, `in_progress`, `resolved`, `closed`) are decoupled from and strictly protected against being overwritten by external portal submission states.

---

## 2. Architectural Design & Separation of Concerns

```
                     ┌──────────────────────────────────────────┐
                     │          CVKI Core Case Engine           │
                     │  (draft -> submitted_to_cvki -> etc.)    │
                     └────────────────────┬─────────────────────┘
                                          │
                                          ▼
                     ┌──────────────────────────────────────────┐
                     │  Government Submission Package Builder   │
                     │  (Schema validation, authority routing)  │
                     └────────────────────┬─────────────────────┘
                                          │
                                          ▼
                     ┌──────────────────────────────────────────┐
                     │    Government Integration Service        │
                     │  (Idempotency, State Machine, Security)   │
                     └───────┬──────────────────────────┬───────┘
                             │                          │
                             ▼                          ▼
              ┌──────────────────────────┐  ┌──────────────────────────┐
              │ Government Registry      │  │ Submission State Machine │
              │ - Capability flags       │  │ - PENDING_VALIDATION     │
              │ - SSRF protection        │  │ - SUBMITTING             │
              │ - Staging / Prod states  │  │ - SUBMITTED / ACCEPTED   │
              └──────────────┬───────────┘  │ - UNKNOWN_OUTCOME / REC  │
                             │              └──────────────────────────┘
                             ▼
              ┌──────────────────────────┐
              │ Abstract Adapter Engine  │
              │  - MockGovernmentAdapter │
              │  - Production Adapters   │
              └──────────────┬───────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │ Cross-Module Intelligence│
              │ - M6.4 Provenance Engine │
              │ - M6.5 Knowledge Graph   │
              │ - RBAC Audit Event Logger│
              └──────────────────────────┘
```

The system preserves strict separation between:
1. **Internal Complaint Case Record (`ComplaintCase`):** Owned and managed solely by the CVKI platform.
2. **Government Submission Package (`GovernmentSubmissionPackage`):** An immutable, prepared data contract containing detected coordinates, verified authority details, confidence metrics, and citizen descriptions.
3. **Government Submission Record (`GovernmentSubmissionRecord`):** Dedicated persistence entity tracking the deterministic external submission lifecycle, idempotency key, submission attempts, reconciliation logs, and raw payloads.

---

## 3. Abstract Adapter Architecture (`GovernmentIntegrationAdapter`)

All government portal integrations implement the strict abstract base class defined in [`backend/app/services/government_adapter.py`](file:///C:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/services/government_adapter.py):

```python
class GovernmentIntegrationAdapter(ABC):
    @property
    @abstractmethod
    def integration_id(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    async def validate_submission(self, case: ComplaintCase, package: GovernmentSubmissionPackage) -> list[str]: ...

    @abstractmethod
    async def submit(self, case: ComplaintCase, package: GovernmentSubmissionPackage, idempotency_key: str) -> AdapterSubmissionResult: ...

    @abstractmethod
    async def check_status(self, external_reference_id: str, case_reference_id: str) -> AdapterStatusResult: ...

    @abstractmethod
    def normalize_status(self, raw_status: str) -> NormalizedGovernmentStatus: ...

    @abstractmethod
    async def reconcile(self, submission_record: GovernmentSubmissionRecord) -> AdapterStatusResult: ...
```

### 3.1 Adapter Capabilities Contract
Every adapter declares its capabilities via `AdapterCapabilities`:
- `supports_sync`: Whether real-time outbound push is supported.
- `supports_status_check`: Whether external polling is available.
- `supports_reconciliation`: Whether idempotency search or status retrieval can resolve in-flight unknowns.
- `supports_attachments`: Whether visual evidence / photos can be attached.
- `supported_issue_categories`: Specific civic issues allowed (e.g. `pothole`, `open_damaged_manhole`).
- `submission_format`: `JSON`, `FORM_MULTIPART`, `SOAP_XML`.

---

## 4. Government Integration Registry & SSRF Defense

Managed by [`GovernmentServiceRegistry`](file:///C:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/services/government_registry.py), the registry acts as a single server-authoritative catalog of available integration definitions:

### 4.1 Integration States
- `NOT_CONFIGURED`: Default state. No active government link.
- `CONFIGURED_STAGING`: Integration enabled against an approved sandbox/staging portal.
- `CONFIGURED_PRODUCTION`: Full production connectivity with validated official endpoints.
- `DEGRADED`: Integration experiencing elevated timeout rates or gateway errors.
- `DISABLED`: Manually decommissioned by system administration.

### 4.2 SSRF Protection & Safe Official Endpoints
Every target endpoint registered must pass strict SSRF validation via `is_safe_official_url`:
- Validates scheme (`https://` required for non-test endpoints).
- Prohibits loopback (`127.0.0.1`, `localhost`), link-local (`169.254.0.0/16`), and private IP spaces (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- Requires official government domains (e.g., `.gov.in`, `.nic.in`) or approved sandbox domains in development/test.
- Prohibits internal port targeting and credentials embedded in URLs.

---

## 5. Deterministic Submission Lifecycle State Machine

The state machine [`SubmissionStateMachine`](file:///C:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/services/government_state_machine.py) governs every transition of a government submission:

### 5.1 Permitted State Transitions
```
                ┌───────────────────────────────────┐
                │          NOT_SUBMITTED            │
                └─────────────────┬─────────────────┘
                                  │
                                  ▼
                ┌───────────────────────────────────┐
                │        PENDING_VALIDATION         │
                └───────┬───────────────────┬───────┘
                        │                   │ Validation error
                        │                   ▼
                        │     ┌───────────────────────────┐
                        │     │      FAILED_TERMINAL      │
                        │     └───────────────────────────┘
                        │
                        ▼
                ┌───────────────────────────────────┐
                │            SUBMITTING             │
                └───────┬─────────────┬─────────────┘
          Timeout / 5xx │             │
                        ▼             ▼
  ┌─────────────────────────┐   ┌─────────────────────────┐
  │     UNKNOWN_OUTCOME     │   │        SUBMITTED        │
  └─────────────┬───────────┘   └─────────────┬───────────┘
                │                             │
    Reconcile   ▼                             ▼
  ┌─────────────────────────┐   ┌─────────────────────────┐
  │       RECONCILED        │   │        ACCEPTED         │
  └─────────────────────────┘   └─────────────┬───────────┘
                                              │
                                              ▼
                                ┌─────────────────────────┐
                                │   REJECTED / TERMINAL   │
                                └─────────────────────────┘
```

1. `NOT_SUBMITTED` -> `PENDING_VALIDATION`
2. `PENDING_VALIDATION` -> `SUBMITTING`, `FAILED_TERMINAL`, `NOT_SUBMITTED`
3. `SUBMITTING` -> `SUBMITTED`, `ACCEPTED`, `REJECTED`, `UNKNOWN_OUTCOME`, `FAILED_TERMINAL`
4. `SUBMITTED` -> `ACCEPTED`, `REJECTED`, `FAILED_TERMINAL`
5. `UNKNOWN_OUTCOME` -> `SUBMITTING`, `SUBMITTED`, `ACCEPTED`, `REJECTED`, `FAILED_TERMINAL`
6. `ACCEPTED` -> `REJECTED`, `FAILED_TERMINAL`

Any illegal transition raises `InvalidStateTransitionError` and blocks state tampering.

---

## 6. Idempotency & The UNKNOWN_OUTCOME Protocol

### 6.1 Idempotency Contract
To prevent accidental duplicate filings:
- **Idempotency Key Generation:** Derived deterministically via `SHA-256(reference_id + integration_id + prepared_at)`.
- **In-Flight Lock:** If a submission for the given case is currently in `SUBMITTING` or `UNKNOWN_OUTCOME`, subsequent attempts are rejected with error code `DUPLICATE_ACTIVE_SUBMISSION`.
- **Cached Replay:** If an exact duplicate request is received after successful submission, the system returns the existing `GovernmentSubmissionRecord` without re-executing outbound network calls.

### 6.2 The UNKNOWN_OUTCOME Safety Protocol
When an outbound call experiences a socket timeout, TCP connection reset, or 504 Gateway Timeout:
1. **Never Assume Success or Failure:** The government portal may or may not have processed the packet before the network broke.
2. **State Transition to `UNKNOWN_OUTCOME`:** The submission record is marked `UNKNOWN_OUTCOME`, setting `reconciliation_required = True`.
3. **No External Reference Invented:** `external_reference_id` remains `None`.
4. **Audited & Notified:** A high-priority system audit event (`government_submission_unknown_outcome`) is logged, and a staff notification is triggered.
5. **Reconciliation Loop:** Admins or background sync routines call `reconcile_submission(reference_id)`, which executes the adapter's `reconcile()` method (querying the external system by idempotency key or case reference) before any retry is permitted.

---

## 7. Status Normalization

External status strings vary across municipal systems (`"registered"`, `"ack"`, `"pending_inspection"`, `"work_order_issued"`, `"closed"`). The adapter normalizes these into the standard enum `NormalizedGovernmentStatus`:

| Raw External Status | Normalized Status | Meaning |
| :--- | :--- | :--- |
| `registered`, `ack`, `received`, `logged` | `REGISTERED` | Acknowledged in official intake system |
| `under_review`, `assigned`, `inspected` | `UNDER_REVIEW` | Assigned to field engineer or inspection team |
| `in_progress`, `work_scheduled`, `dispatched` | `IN_PROGRESS` | Physical repair works initiated |
| `resolved`, `repaired`, `completed` | `RESOLVED` | Official repair completed by authority |
| `closed`, `archived` | `CLOSED` | Case file closed in external registry |
| `rejected`, `invalid`, `out_of_jurisdiction` | `REJECTED` | Rejected by official intake review |
| Unrecognized / Vendor-specific string | `UNKNOWN` | Unmapped vendor status code |

---

## 8. Cross-Module Intelligence Integrations

### 8.1 Evidence Provenance Engine (M6.4)
When a submission is confirmed, an immutable provenance record is registered:
- **`claim_type`**: `ClaimType.GOVERNMENT_SUBMISSION`
- **`source_type`**: `SourceType.GOVERNMENT_ADAPTER`
- **`matched_attribute`**: `external_reference_id`
- **`retrieved_at` / `freshness`**: Precise timestamp and `"fresh"` state.
- **`verification_state`**: `"verified"` (if verified external confirmation) or `"provisional"`.

### 8.2 Civic Knowledge Graph (M6.5)
The civic graph is augmented with two first-class nodes and edges:
- **Node**: `NodeType.GOVERNMENT_SUBMISSION` (carries submission record ID, integration ID, lifecycle state).
- **Node**: `NodeType.EXTERNAL_CASE` (carries external reference ID, normalized status, authority name).
- **Edge**: `(Civic Issue) -[RelationType.GOVERNMENT_SUBMISSION]-> (Government Submission Node)`
- **Edge**: `(Government Submission Node) -[RelationType.REFERENCES]-> (External Case Node)`

### 8.3 Notifications & Audit Logging
- Dedicated notification triggers: `government_submission_accepted`, `government_submission_rejected`, `government_submission_status_changed`, `government_reconciliation_required`.
- Structured audit events recorded via `AuditService`: `government_submission_attempted`, `government_submission_succeeded`, `government_submission_failed`, `government_submission_unknown_outcome`, `government_submission_reconciled`.

---

## 9. Security, Privacy & RBAC

1. **Credential Isolation:** API keys, certificates, and authentication headers reside strictly server-side in secure configuration. No client secret is ever returned via API responses or logged in audit records.
2. **Payload Masking:** Citizen personal contact details (phone, email) are omitted or tokenized unless explicitly required and authorized by legal data agreements.
3. **Strict Role-Based Access Control (RBAC):**
   - `CITIZEN`: Can read own submission status summary (`external_reference_id`, normalized status, notice). Cannot view raw payloads or trigger manual reconciliation.
   - `OFFICER` / `STAFF` / `ADMIN`: Can prepare submission packages, initiate submissions, inspect detailed integration definitions, and execute manual reconciliation.

---

## 10. API Specification

| Endpoint | Method | Role | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/government-integrations` | `GET` | Authenticated | Lists all registered integration definitions and their current states |
| `/api/v1/government-integrations/{integration_id}` | `GET` | Authenticated | Retrieves configuration details for a specific integration |
| `/api/v1/government/cases/{reference_id}/submission` | `GET` | Citizen (own) / Staff | Retrieves government submission summary and tracking record |
| `/api/v1/government/cases/{reference_id}/prepare` | `POST` | Officer / Staff / Admin | Prepares a structured complaint package for submission |
| `/api/v1/government/cases/{reference_id}/submit` | `POST` | Officer / Staff / Admin | Dispatches submission to registered adapter with idempotency lock |
| `/api/v1/government/cases/{reference_id}/reconcile` | `POST` | Officer / Staff / Admin | Reconciles in-flight or `UNKNOWN_OUTCOME` submissions |
| `/api/v1/government/cases/{reference_id}/status` | `GET` | Authenticated | Queries live normalized status from the external government adapter |

---

## 11. Local Engineering Performance Benchmarks

*Measurements taken on Windows local environment using `benchmark_m71.py` (100 iterations, in-memory isolation):*

| Operation | Mean Latency | Median | P95 | Min | Max |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Integration Listing** | 0.006 ms | 0.006 ms | 0.006 ms | 0.005 ms | 0.024 ms |
| **2. Adapter Lookup** | 0.000 ms | 0.000 ms | 0.000 ms | 0.000 ms | 0.002 ms |
| **3. Submission Validation** | 0.000 ms | 0.000 ms | 0.000 ms | 0.000 ms | 0.004 ms |
| **4. Status Normalization** | 0.001 ms | 0.001 ms | 0.001 ms | 0.000 ms | 0.007 ms |
| **5. Mock Adapter Submission** | 0.009 ms | 0.007 ms | 0.014 ms | 0.006 ms | 0.083 ms |
| **6. Submission Summary Retrieval** | 0.008 ms | 0.007 ms | 0.009 ms | 0.007 ms | 0.056 ms |
| **7. Safe Reconciliation** | 0.032 ms | 0.023 ms | 0.109 ms | 0.020 ms | 0.340 ms |

> *Note: Engineering baseline measurements only. Real-world network latencies to government portals will depend on external network infrastructure.*

---

## 12. Verification & Test Suite Summary

- **M7.1 Dedicated Test Suite:** `backend/tests/test_government_integration_m71.py`
  - **Result:** **29/29 Passed** (Covers items A through Z).
- **M5 & M6 Combined Regression Suite:**
  - `test_civic_knowledge_graph_m65.py`
  - `test_evidence_provenance_m64.py`
  - `test_external_civic_data_m63.py`
  - `test_geospatial_intelligence_m62.py`
  - `test_live_authority_m61.py`
  - `test_civic_intelligence_m52.py`
  - `test_government_submission_m310.py`
  - **Result:** **161/161 Passed**.
- **Full Backend Pytest Suite:**
  - **Result:** **560/560 Passed** in 193.97s.
- **Frontend Verification:**
  - `npm run lint`: **0 errors**.
  - `npm run build`: **Built successfully** in 2.32s.
- **Frozen Computer Vision Baseline:**
  - Model weights: `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`
  - Verified SHA-256: `602160D4851E0D79C34CB23B828BDE474FC4C164EAF1A1C2A884CFB372F4BDA3` (Intact).
