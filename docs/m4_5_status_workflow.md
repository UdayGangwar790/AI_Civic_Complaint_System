# M4.5 Case Status Workflow & Lifecycle Management

## Overview
Module M4.5 introduces a deterministic, RBAC-guarded state machine governing civic complaint case lifecycles in CVKI. It replaces the previous read-only status approach with structured, audited transitions between canonical states, enforcing strict role permissions, atomic database updates, automatic citizen/authority notifications, and complete immutability for terminal states.

---

## Canonical Lifecycle Model

The canonical status schema is defined in `backend/app/schemas/case_status.py` and `backend/app/schemas/complaint_case.py`.

### Lifecycle States
1. `draft`: Case prepared locally or in-flight prior to final submission.
2. `submitted_to_cvki`: Freshly submitted civic report awaiting triage and routing.
3. `under_review`: Complaint actively being assessed or cross-referenced.
4. `assigned`: Case routed to a verified authority operator for field execution.
5. `in_progress`: Remediation crews or inspection teams actively working on site.
6. `resolved`: Physical repair or mitigation confirmed on site.
7. `closed`: Terminal archived state; issue completed and administratively finalized.

### State Transition Graph
```
           [draft]
              │
              ▼
    [submitted_to_cvki] ◄──────────────┐
       │             │                 │
       ▼             ▼                 │
 [under_review] ──► [assigned] ────────┤
       │             │                 │
       ▼             ▼                 │
       └──────► [in_progress]          │
                     │                 │
                     ▼                 │
                 [resolved]            │
                     │                 │
                     ▼                 │
                  [closed] (TERMINAL) ─┘ (Closed cases cannot transition)
```

### Transition Validation Rules (`VALID_TRANSITIONS`)
- `draft` ➔ `{"submitted_to_cvki", "closed"}`
- `submitted_to_cvki` ➔ `{"assigned", "under_review", "in_progress", "closed"}`
- `under_review` ➔ `{"assigned", "in_progress", "resolved", "closed"}`
- `assigned` ➔ `{"in_progress", "submitted_to_cvki", "closed"}`
- `in_progress` ➔ `{"resolved", "assigned", "closed"}`
- `resolved` ➔ `{"closed", "in_progress"}`
- `closed` ➔ `set()` (Terminal state: modifications strictly forbidden)

---

## Role-Based Access Control (RBAC) Enforcement

1. **Citizen Role (`citizen`)**:
   - Strictly forbidden from modifying complaint status (`HTTP 403 Forbidden`).
   - Retains read-only visibility into case lifecycle progress via the interactive `LifecycleProgressBar`.

2. **Authority Role (`authority`)**:
   - May only update status for cases **assigned to their specific account** (`assigned_to_user_id == current_user.user_id`).
   - Restricted to operational remediation transitions:
     - `assigned` ➔ `in_progress`
     - `in_progress` ➔ `resolved`
   - Attempting unpermitted transitions (e.g., closing cases or reopening resolved cases) returns `HTTP 403 Forbidden`.

3. **Admin Role (`admin`)**:
   - Permitted across all valid transitions according to `VALID_TRANSITIONS`.
   - Cannot transition from terminal `closed` state (`HTTP 400 Bad Request`).
   - Requires a reason string when closing cases.

---

## API Endpoints

### 1. Update Case Status (Admin Endpoint)
- **Route**: `PATCH /api/v1/admin/cases/{reference_id}/status`
- **Access**: Role `admin` required.
- **Request Body**:
```json
{
  "status": "in_progress",
  "reason": "Road maintenance crew dispatched to site"
}
```
- **Response**: Updated `ComplaintCase` model.

### 2. Update Case Status (Authority / Operational Endpoint)
- **Route**: `PATCH /api/v1/complaint/cases/{reference_id}/status`
- **Access**: Roles `authority` or `admin`.
- **Request Body**:
```json
{
  "status": "resolved",
  "reason": "Manhole cover replaced and asphalt leveled"
}
```
- **Response**: Updated `ComplaintCase` model.

---

## Side Effects & Audit Trail

Every status transition executed through `CaseStatusService.update_status`:
1. **Validates Case Existence**: Returns `HTTP 404` if reference is not found.
2. **Evaluates Terminal Immutability**: Returns `HTTP 400` if current status is `closed`.
3. **Validates RBAC Permissions**: Enforces authority ownership and permitted transitions.
4. **Applies Atomic DB Mutation**:
   - Updates `status`.
   - Updates `updated_at` timestamp.
   - Appends an entry to `status_history` containing `from_status`, `to_status`, `changed_by_user_id`, `changed_by_role`, `changed_at`, and optional `reason`.
5. **Issues Notifications**:
   - Notifies citizen creator of their report's progress.
   - Notifies assigned authority when status updates occur.
6. **Records Audit Log Event**:
   - Logs `action="case_status_change"`, `result="success"`, actor metadata, and sanitized payload to the `audit_logs` collection.

---

## Frontend Integration
- **`LifecycleProgressBar`**: Added to citizen `CaseDetailModal` and admin `AdminCaseDetailModal`, rendering active progress from `submitted_to_cvki` through `closed`.
- **Status Workflow Box**: Embedded in `AdminCaseDetailModal`, featuring dynamic dropdowns filtered to allowed transitions and reason input.
- **Authority Remediation Buttons**: Inline "Start Work" and "Mark Resolved" workflow triggers within `AuthorityPortalView`.

---

## Test Verification
- Test file: `backend/tests/test_case_status_workflow_m45.py`
- Total tests: **22 passing tests**.
- Validated:
  - Canonical state definitions and transition validity.
  - Invalid transition rejection (`HTTP 400`).
  - Terminal `closed` immutability.
  - Authority permitted transitions (`assigned -> in_progress`, `in_progress -> resolved`).
  - Authority forbidden transitions (`closed`, cross-account tampering).
  - Citizen rejection (`HTTP 403`).
  - History tracking and notifications dispatch.
