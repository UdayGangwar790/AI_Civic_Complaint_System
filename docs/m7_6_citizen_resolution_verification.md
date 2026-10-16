# Module M7.6: Citizen Resolution Verification

## 1. Executive Summary & Epistemic Stance

> **CORE INVARIANT: GROUND TRUTH SOURCING**
> *"An external government portal marking a complaint as 'Resolved' or 'Closed' is strictly a bureaucratic claim, NOT proof of physical defect rectification. Physical resolution verification belongs exclusively to the affected citizen and on-the-ground human casework review. An external 'RESOLVED' status MUST NEVER automatically close a case or be treated as verified reality without citizen confirmation or documented staff review."*

Module M7.6 delivers the **Citizen Resolution Verification Engine** of the CVKI platform. It bridges the gap between third-party government claim observations and physical ground reality. When an integrated government system signals case resolution, M7.6 enables citizens to confirm, dispute, or partially verify the work done, incorporating photographic proof, physical inspection observations, and administrative casework review workflows.

### Epistemic Principles of Resolution Verification
1. **Physical Reality vs. Bureaucratic Claim:** A portal docket closed by BBMP or CPGRAMS indicates administrative closure. Physical defect remediation requires human verification.
2. **Citizen-First Ground Truth:** The citizen who reported the defect is the primary source of truth. Their input directly sets `is_physical_resolution_verified`.
3. **Dispute Escalation:** When a citizen disputes an external resolution claim (`STILL_UNRESOLVED`), the system flags the docket as disputed (`CITIZEN_DISPUTED`), preventing premature closure and triggering administrative follow-up.
4. **Uncertainty & Ambiguity Routing:** Ambiguous responses or citizen comments indicating uncertainty automatically route to `NEEDS_REVIEW` for casework inspection.
5. **Auditable Casework Oversight:** Platform staff and civic administrators can review disputed or ambiguous verifications, transition them through explicit review states (`OVERRIDDEN_RESOLVED`, `ESCALATED_DISPUTED`), and log cryptographically backed justification.
6. **Provenance & Graph Integration:** Every verification and administrative review emits a verifiable provenance claim (`ClaimType.RESOLUTION_VERIFICATION`) and adds nodes and edges to the Civic Knowledge Graph (`NodeType.RESOLUTION_VERIFICATION`, `RelationType.HAS_RESOLUTION_VERIFICATION`).

---

## 2. Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 Government Status (M7.4)                    │
│   observed_status: "resolved"                               │
└──────────────────────────────┬──────────────────────────────┘
                               │ Notification Trigger:
                               │ "Government reported resolved"
                               ▼
┌─────────────────────────────────────────────────────────────┐
│            Citizen Resolution Verification (M7.6)           │
│                                                             │
│  Citizen Submission:                                        │
│   - citizen_response: CONFIRMED_RESOLVED | STILL_UNRESOLVED │
│                       PARTIALLY_RESOLVED | CANNOT_VERIFY    │
│   - citizen_notes: "Pothole filled with proper bitumen"     │
│   - evidence_photo_url: "https://.../repaired_road.jpg"     │
│                                                             │
│  Verification Status Outcome:                               │
│   - VERIFIED_RESOLVED (Citizen confirmed)                   │
│   - CITIZEN_DISPUTED  (Citizen disputes repair)             │
│   - PARTIALLY_RESOLVED (Work partially done)                │
│   - NEEDS_REVIEW      (Citizen cannot verify / uncertain)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌───────────────────────────────┐     ┌───────────────────────────────┐
│ Casework Review (Admin/Staff) │     │ Provenance & Knowledge Graph  │
│  - OVERRIDDEN_RESOLVED        │     │  - Claim:                     │
│  - ESCALATED_DISPUTED         │     │    RESOLUTION_VERIFICATION    │
│  - DISMISSED                  │     │  - Graph Node:                │
│  - Immutable review notes     │     │    RESOLUTION_VERIFICATION    │
└───────────────────────────────┘     └───────────────────────────────┘
```

---

## 3. Schema Definitions (`backend/app/schemas/resolution_verification.py`)

### Citizen Resolution Response & Status Enums
```python
class CitizenResolutionResponse(str, Enum):
    CONFIRMED_RESOLVED = "CONFIRMED_RESOLVED"    # Citizen confirms physical repair completed
    STILL_UNRESOLVED = "STILL_UNRESOLVED"        # Citizen disputes: defect remains intact
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"    # Citizen indicates incomplete work
    CANNOT_VERIFY = "CANNOT_VERIFY"              # Citizen inaccessible, moved, or cannot inspect

class ResolutionVerificationStatus(str, Enum):
    PENDING_CITIZEN_INPUT = "PENDING_CITIZEN_INPUT"
    VERIFIED_RESOLVED = "VERIFIED_RESOLVED"
    CITIZEN_DISPUTED = "CITIZEN_DISPUTED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    OVERRIDDEN_RESOLVED = "OVERRIDDEN_RESOLVED"
    ESCALATED_DISPUTED = "ESCALATED_DISPUTED"
    DISMISSED = "DISMISSED"
```

### Core Record Schema
```python
class CitizenResolutionVerificationRecord(BaseModel):
    verification_id: str
    cvki_reference_id: str
    citizen_user_id: str
    citizen_response: CitizenResolutionResponse
    verification_status: ResolutionVerificationStatus
    is_physical_resolution_verified: bool
    citizen_notes: Optional[str]
    evidence_photo_url: Optional[str]
    submitted_at: datetime
    reviewed_at: Optional[datetime]
    reviewed_by_user_id: Optional[str]
    review_notes: Optional[str]
    provenance_claim_id: Optional[str]
    knowledge_graph_node_id: Optional[str]
    is_system_derived: bool = False
```

---

## 4. API Endpoints (`backend/app/api/v1/government_integration.py`)

| Method | Endpoint | Access / Role | Description |
|---|---|---|---|
| `POST` | `/api/v1/government/cases/{ref}/resolution-verification` | Citizen (Owner) / Staff | Submit physical resolution verification |
| `GET` | `/api/v1/government/cases/{ref}/resolution-verification` | Citizen (Owner) / Staff | Get latest verification record for case |
| `GET` | `/api/v1/government/cases/{ref}/resolution-verification/history` | Citizen (Owner) / Staff | Get full chronological verification history |
| `POST` | `/api/v1/admin/government/cases/{ref}/resolution-verification/{id}/review` | Staff / Admin | Execute administrative review / override |

---

## 5. Security & Role-Based Access Control (RBAC)

1. **Owner Isolation:** Citizens may only submit and view resolution verification records for complaints that they own (`case.user_id == current_user.user_id`). Accessing other citizens' cases returns `404 Not Found`.
2. **Review Protection:** Administrative review endpoints (`/admin/government/.../review`) are restricted to `SUPER_ADMIN`, `CITY_OFFICIAL`, and `DEPARTMENT_STAFF`. Any citizen attempting review is rejected with `403 Forbidden`.
3. **Immutable Audit Trails:** Neither verifications nor review decisions can be deleted or overwritten in place; all state progressions append new verification records and generate immutable audit events.

---

## 6. Verification & Test Suite

The M7.6 test suite is implemented in [`backend/tests/test_citizen_resolution_verification_m76.py`](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/backend/tests/test_citizen_resolution_verification_m76.py):
- `test_citizen_confirms_resolution_verified_resolved`: Tests verified resolution path.
- `test_citizen_disputes_resolution_citizen_disputed`: Tests dispute handling and state mutation.
- `test_citizen_partial_resolution`: Validates `PARTIALLY_RESOLVED` classification.
- `test_citizen_cannot_verify`: Validates routing of `CANNOT_VERIFY` to `NEEDS_REVIEW`.
- `test_uncertainty_in_notes_routes_to_needs_review`: Evaluates heuristic routing when citizen text contains uncertainty keywords.
- `test_admin_review_transition`: Validates staff review transitions (`OVERRIDDEN_RESOLVED`, `ESCALATED_DISPUTED`).
- `test_invalid_review_transition_rejected`: Tests rejection of invalid administrative state transitions.
- `test_rbac_citizen_forbidden_from_other_citizen_case`: Confirms case isolation.
- `test_rbac_citizen_cannot_review_verifications`: Asserts 403 on citizen administrative review attempts.
- `test_verification_history_and_latest`: Tests retrieval of latest and complete history.
- `test_provenance_claim_emission`: Verifies emission of `ClaimType.RESOLUTION_VERIFICATION` in M6.4 engine.
- `test_knowledge_graph_integration`: Verifies insertion of graph node and edge in M6.5 Knowledge Graph.

**Test Results:** 12/12 PASSED (100%).
