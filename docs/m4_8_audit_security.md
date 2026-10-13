# M4.8 Audit Trail & Security Monitoring

## Overview
Module M4.8 introduces a tamper-evident audit logging subsystem and administrative security dashboard for CVKI. It records system events across authentication, access control decisions, case creations, assignment changes, lifecycle transitions, and external preparation workflows. It enforces recursive credential and token redaction, indexed storage in MongoDB, and administrative monitoring for security alerts.

---

## Audit Event Schema & Redaction

The audit data model is defined in `backend/app/schemas/audit.py`:
```python
class AuditLogEntry(BaseModel):
    event_id: str
    timestamp: datetime
    actor_user_id: Optional[str]
    actor_email: Optional[str]
    actor_role: str
    action: str
    resource_type: str
    resource_id: Optional[str]
    resource_reference_id: Optional[str]
    result: Literal["success", "failure", "denied"]
    client_ip: Optional[str]
    user_agent: Optional[str]
    metadata: dict[str, Any]
```

### Recursive Credential Redaction
All audit records pass through `AuditService._sanitize_metadata` prior to persistence.
- **Redacted Keys**: Keys containing `password`, `token`, `secret`, `authorization`, `auth`, `api_key`, `access_token`, `refresh_token`, or `credentials` are automatically replaced with `"[REDACTED]"`.
- **Recursive Processing**: Nested dictionaries and list structures are recursively sanitized to prevent credential leakage.

---

## Indexed Persistence (`audit_logs`)

Audit logs are stored in a dedicated MongoDB collection `audit_logs` defined in `backend/app/core/database.py`. The collection features indexes for query efficiency:
- `event_id` (Unique)
- `timestamp` (Descending for chronological pagination)
- `actor_user_id`
- `action`
- `result`
- `resource_reference_id`

---

## Instrumented Event Triggers

Audit logging is instrumented across core system interactions:
1. **Authentication (`auth.py`)**:
   - `login` (`result="success"` on valid login, `result="failure"` on invalid credentials).
2. **Access Control (`deps.py`)**:
   - `access_denied` (`result="denied"` with attempted role and endpoint on HTTP 403).
3. **Complaint Ingestion (`complaint.py`)**:
   - `case_created` (`result="success"` on case persistence).
   - `submission_prepared` (`result="success"` on government submission package generation).
4. **Lifecycle Transitions (`case_status.py`)**:
   - `case_status_change` (`result="success"` on valid transitions, `result="failure"` or `result="denied"` on invalid attempts).
5. **Assignment Operations (`admin_case.py`)**:
   - `case_assigned` (`result="success"` when case is routed).
   - `case_unassigned` (`result="success"` when routing is cleared).

---

## API Endpoints

### 1. Audit Logs Listing Endpoint
- **Route**: `GET /api/v1/admin/audit`
- **Access**: Role `admin` required.
- **Query Parameters**:
  - `actor`: Filter by actor user ID or email.
  - `role`: Filter by actor role.
  - `action`: Filter by action name.
  - `result`: Filter by `success`, `failure`, or `denied`.
  - `reference_id`: Filter by case reference ID.
  - `created_from`: ISO timestamp lower bound.
  - `created_to`: ISO timestamp upper bound.
  - `page`: Page index (1-indexed).
  - `page_size`: Page limit (default 20, max 100).
- **Response**: `AuditLogsResponse` containing items, total, page, and total_pages.

### 2. Security Overview Summary Endpoint
- **Route**: `GET /api/v1/admin/audit/summary`
- **Access**: Role `admin` required.
- **Response**:
```json
{
  "total_events": 142,
  "failed_events": 4,
  "access_denied_events": 2,
  "login_events": 38,
  "status_change_events": 24,
  "assignment_events": 12,
  "recent_alerts": []
}
```

---

## Frontend Integration (`AdminAuditView`)

- **Security Overview KPIs**: Visual indicator cards for Total Events, Failed Actions, Access Denied (403), and Auth Logins.
- **Audit Table**: Chronologically sorted table displaying Timestamp, Actor (Email + Role), Action Badge, Result Pill (`success`, `failure`, `denied`), Resource Reference, and Client IP.
- **Metadata Inspector**: Toggleable modal/drawer rendering sanitized JSON metadata without exposing credentials.
- **Filter Bar & Pagination**: Action, Result, and timeframe filters with pagination controls.

---

## Test Verification
- Test file: `backend/tests/test_audit_security_m48.py`
- Total tests: **21 passing tests**.
- Validated:
  - Event recording across login, case creation, assignment, and status transitions.
  - Recursive credential and token redaction.
  - Query filtering by actor, action, result, and reference ID.
  - Summary aggregation and alert counting.
  - Admin-only RBAC protection.
