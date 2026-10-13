# M4.2 Admin Dashboard Documentation

## Overview
The CVKI Operational Admin Dashboard provides authenticated administrators with real-time, aggregated visibility into complaint cases across the civic platform. It presents real MongoDB aggregations and counts without synthetic data or hardcoded mock metrics.

## Route & Access Control
- **Frontend Route**: `/admin`
- **Backend Protected Endpoint**: `GET /api/v1/admin/dashboard/summary`
- **RBAC Enforcement**:
  - `role == "admin"`: Full operational dashboard access granted (HTTP 200).
  - `role == "citizen"`: Denied with HTTP 403 Forbidden (`detail: "Access forbidden: insufficient permissions. Required role: admin."`).
  - `role == "authority"`: Denied with HTTP 403 Forbidden.
  - Unauthenticated requests: Denied with HTTP 401 Unauthorized.
  - Both frontend routing (`RoleProtectedRoute`) and backend dependency (`require_role(UserRole.ADMIN)`) enforce access control.

## Dashboard Summary API
- **Endpoint**: `GET /api/v1/admin/dashboard/summary`
- **Response Structure**:
```json
{
  "total_cases": 120,
  "open_cases": 85,
  "resolved_cases": 35,
  "unassigned_cases": 42,
  "priority_counts": {
    "P1": 15,
    "P2": 45,
    "P3": 40,
    "P4": 20
  },
  "issue_counts": {
    "open_damaged_manhole": 50,
    "damaged_missing_road_sign": 30,
    "road_waterlogging": 35,
    "other_civic_issue": 5
  },
  "duplicate_counts": {
    "unique": 100,
    "possible_duplicate": 15,
    "duplicate": 5
  },
  "status_counts": {
    "submitted_to_cvki": 60,
    "under_review": 25,
    "resolved": 35
  },
  "recent_cases": [
    {
      "reference_id": "CVKI-20261013-ABCD",
      "created_at": "2026-10-13T04:30:00Z",
      "status": "submitted_to_cvki",
      "issue": {
        "class_name": "open_damaged_manhole",
        "label": "Open/Damaged Manhole"
      },
      "location": {
        "road": "MG Road",
        "city": "Bengaluru"
      },
      "priority_analysis": {
        "priority_level": "P1"
      },
      "assignment": {
        "assignment_status": "unassigned"
      }
    }
  ]
}
```

## Performance & Aggregation Strategy
- **Native MongoDB Counts & Aggregations**:
  - `total_cases`: `collection.count_documents({})`
  - `open_cases`: `collection.count_documents({"status": {"$nin": ["resolved", "closed"]}})`
  - `resolved_cases`: `collection.count_documents({"status": "resolved"})`
  - `unassigned_cases`: `collection.count_documents({"$or": [{"assignment": None}, {"assignment.assignment_status": "unassigned"}, {"assignment.assigned_to_user_id": None}]})`
  - Priority and Issue breakdown queries leverage indexed fields (`priority_analysis.priority_level` and `issue.class_name`).
  - `recent_cases`: Bounded cursor query sorted by `created_at: -1` and limited to 8 items, preventing unbounded memory consumption.
- **Empty State Behavior**:
  - If the database contains 0 cases, the API safely returns zeroes for all numerical tallies, an empty `recent_cases` array, and the frontend displays a dedicated empty state banner rather than breaking.

## Privacy & Security
- Passwords, password hashes, JWT tokens, and user credentials are never returned by the dashboard summary or recent cases API.
- Sensitive internal user credentials remain protected.

## Verification & Testing
- Test suite: `backend/tests/test_admin_dashboard_m42.py` (12 tests)
  - Admin access allowed (200)
  - Citizen access denied (403)
  - Authority access denied (403)
  - Unauthenticated denied (401)
  - Summary counts calculation verified
  - Priority breakdown aggregation
  - Issue distribution aggregation
  - Status counts aggregation
  - Recent cases order (newest first)
  - Empty database safety
  - Malformed token/auth header rejection
  - Privacy checks: no secret leakage

## Scope Boundaries & Limitations
- **M4.5 Status Transition Engine**: NOT implemented. Status values are presented read-only as stored in existing MongoDB records.
- **M4.6 Map Operations**: NOT implemented. Geospatial map views are deferred.
- **M4.7 Advanced Analytics**: NOT implemented. Advanced time-series trend forecasting is deferred.
- **M4.8 Audit Dashboard**: NOT implemented. Detailed audit history logging is deferred.
