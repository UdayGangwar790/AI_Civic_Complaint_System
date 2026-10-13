# M4.4 Case Assignment Documentation

## Overview
M4.4 introduces operational case routing and assignment in CVKI. Administrators can assign, reassign, or unassign complaint cases to verified authority accounts. This module operates strictly on assignment routing; it does not implement operational status workflow transitions (which belong to M4.5).

## Assignment Model
The `ComplaintCase` and `ComplaintCaseSummary` schemas are extended with canonical assignment metadata:
```python
class CaseAssignment(BaseModel):
    assigned_to_user_id: Optional[str] = None
    assigned_to_role: Optional[str] = "authority"
    assigned_by_user_id: Optional[str] = None
    assigned_at: Optional[datetime] = None
    assignment_status: Literal["unassigned", "assigned"] = "unassigned"
    assigned_to_email: Optional[str] = None
```

### Assignment States
- `unassigned`: Case has no assigned authority or assignment was cleared.
- `assigned`: Case is assigned to an active user with role `authority`.
*(Note: Operational workflow states like `in_progress`, `resolved`, or `closed` belong strictly to M4.5 and are not part of M4.4).*

## Assignment APIs

### 1. Assign Case
- **Route**: `POST /api/v1/admin/cases/{reference_id}/assign`
- **Access**: Admin only (`require_role(UserRole.ADMIN)`).
- **Request Body**:
```json
{
  "assigned_to_user_id": "usr_authority_123"
}
```
- **Backend Verification**:
  1. Authenticates current user and asserts `role == "admin"`.
  2. Retrieves target user from MongoDB `users` collection.
  3. Verifies target user exists.
  4. Verifies target user is active (`is_active is True`).
  5. Verifies target user role is strictly `"authority"` (role spoofing or assigning to citizens/admins is rejected with HTTP 400).
  6. Retrieves case from `complaint_cases` collection and verifies existence.
  7. Updates `assignment` atomically.
  8. Triggers in-app notification to the assigned authority via M3.9 notification service.
- **Response**: Updated `ComplaintCase` document.

### 2. Unassign Case
- **Route**: `POST /api/v1/admin/cases/{reference_id}/unassign`
- **Access**: Admin only.
- **Backend Action**:
  - Sets `assignment.assignment_status = "unassigned"`.
  - Clears `assigned_to_user_id`, `assigned_to_email`, and `assigned_at`.
  - Sends unassignment notification if an authority was previously assigned.
- **Response**: Updated `ComplaintCase` document.

### 3. Authority List Endpoint
- **Route**: `GET /api/v1/admin/authorities`
- **Access**: Admin only.
- **Query Filter**: Retrieves only users where `role == "authority"` and `is_active == True`.
- **Projection**: Excludes `password_hash`, tokens, and credentials.
- **Response Format**:
```json
[
  {
    "user_id": "usr_auth_01",
    "email": "officer1@bbmp.gov.in",
    "role": "authority",
    "is_active": true,
    "created_at": "2026-10-10T10:00:00Z"
  }
]
```

## Notification System Integration (M3.9)
- Extended `NotificationType` enum with:
  - `"case_assigned"`: `"Case {ref_id} has been assigned to you for investigation and action."`
  - `"case_unassigned"`: `"Assignment for case {ref_id} has been removed by platform administration."`
- In-app notifications are created atomically in the `notifications` collection upon successful assignment/unassignment.
- Failed assignment attempts (e.g. invalid user or missing case) generate zero notifications.

## Security & Authorization Rules
- **Admin**: Only users with `role == "admin"` may execute assign/unassign actions and fetch the authority directory.
- **Citizens**: Cannot assign cases (HTTP 403 Forbidden). Cannot be assigned cases (HTTP 400 Bad Request).
- **Authorities**: Cannot assign cases (HTTP 403 Forbidden).
- **Target Role Verification**: Role is retrieved directly from MongoDB database; frontend role claims are never trusted.

## Reassignment Handling
- If a case is already assigned to Authority A and an administrator reassigns it to Authority B, the assignment is updated atomically:
  - `assigned_to_user_id` set to Authority B.
  - `assigned_by_user_id` updated to current Admin.
  - `assigned_at` updated to current UTC timestamp.
  - In-app assignment notification sent to Authority B.

## Verification & Testing
- Test suite: `backend/tests/test_case_assignment_m44.py` (17 tests)
  - Assign case successfully
  - Assign only allowed by admin
  - Citizen cannot assign (403)
  - Authority cannot assign (403)
  - Unauthenticated cannot assign (401)
  - Target user must exist (400)
  - Target user must have role=authority (400)
  - Citizen target rejected (400)
  - Unassign case
  - Reassignment updates safely
  - Assignment persistence in MongoDB
  - Authority list endpoint
  - Assignment notification created
  - Failed assignment creates no notification
  - Nonexistent case detail (404)
  - Inactive authority rejected (400)
  - Malformed request handled safely (422 / 400)

## Scope Boundaries & Limitations
- **M4.5 Status Transitions**: NOT implemented. Case status transitions (e.g. `in_progress`, `resolved`, `closed`) belong strictly to M4.5.
- **M4.6 Map Operations**: NOT implemented.
- **M4.7 Analytics**: NOT implemented.
- **M4.8 Audit Trail**: NOT implemented. Full historical audit log timeline is deferred to M4.8.
