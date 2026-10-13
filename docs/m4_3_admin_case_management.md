# M4.3 Admin Case Management Documentation

## Overview
CVKI Admin Case Management provides platform administrators with comprehensive capabilities to inspect, search, filter, and paginate complaint cases across all citizens. It enables administrative oversight while preserving the privacy of non-operational data and keeping citizen data isolation strictly intact.

## APIs & Endpoints

### 1. Case List Endpoint
- **Route**: `GET /api/v1/admin/cases`
- **Access**: Admin only (`require_role(UserRole.ADMIN)`).
- **Pagination**: `?page=1&page_size=20` (defaults to page 1, 20 items per page; max page size 100).
- **Query Parameters**:
  - `search`: Safe substring match across `reference_id`, `issue.label`, `complaint.title`, `location.road`, and `location.city`.
  - `priority`: Matches `priority_analysis.priority_level` (`P1`, `P2`, `P3`, `P4`).
  - `issue`: Matches `issue.class_name` (`open_damaged_manhole`, `damaged_missing_road_sign`, `road_waterlogging`, `other_civic_issue`).
  - `status`: Matches `status` (`submitted_to_cvki`, `under_review`, `resolved`, `closed`).
  - `assignment`: `assigned` (has non-null `assigned_to_user_id`) or `unassigned`.
  - `duplicate`: Matches `duplicate_analysis.classification` (`unique`, `possible_duplicate`, `duplicate`).
  - `created_from`: ISO timestamp filter (`created_at >= created_from`).
  - `created_to`: ISO timestamp filter (`created_at <= created_to`).
  - `sort_by`: `newest` (default, `created_at` desc), `oldest` (`created_at` asc), or `highest_priority` (`priority_score` desc, `created_at` desc).
- **Response Format**:
```json
{
  "items": [
    {
      "reference_id": "CVKI-20261013-1234",
      "user_id": "usr_citizen_001",
      "created_at": "2026-10-13T05:00:00Z",
      "updated_at": "2026-10-13T05:00:00Z",
      "status": "submitted_to_cvki",
      "issue": {
        "class_name": "open_damaged_manhole",
        "label": "Open/Damaged Manhole",
        "severity": "high",
        "confidence": 0.94
      },
      "location": {
        "road": "Brigade Road",
        "city": "Bengaluru"
      },
      "complaint": {
        "title": "Hazardous uncovered manhole",
        "description": "Pedestrian hazard near metro station."
      },
      "priority_analysis": {
        "priority_level": "P1",
        "priority_score": 92
      },
      "assignment": {
        "assignment_status": "unassigned"
      }
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 52,
  "total_pages": 3
}
```

### 2. Case Detail Endpoint
- **Route**: `GET /api/v1/admin/cases/{reference_id}`
- **Access**: Admin only.
- **Response**: Full operationally relevant case document including:
  - Reference ID, dates, and status
  - Computer Vision issue detection metadata
  - GPS & road location summary
  - Assigned authority intelligence
  - Citizen complaint description and evidence
  - NLP intelligence analysis
  - Duplicate analysis
  - Priority & risk intelligence
  - Government submission preparation status
  - Assignment details (assigned authority, assigned at, assigned by)
- **Error Handling**: Nonexistent reference returns HTTP 404 (`detail: "Case '...' was not found."`).

## Frontend Integration
- **Admin Cases Table**: Displays reference ID, creation date, issue label with preview, location, priority badge, assignment status badge, and review action button.
- **Search & Filters Card**: Instant dropdown filtering by priority, issue, status, assignment, and sort order, with quick reset button.
- **Admin Case Detail Modal**: Interactive modal displaying multi-section operational breakdown with tabbed inspection and assignment routing controls.

## Privacy & Security
- Admin endpoints only return operational data required for routing and inspection.
- Passwords, password hashes, and JWT tokens are completely excluded.
- Citizen case ownership endpoints (`GET /api/v1/complaint/cases/my`) remain strictly scoped to the authenticated citizen's `user_id`.

## Verification & Testing
- Test suite: `backend/tests/test_admin_case_management_m43.py` (18 tests)
  - Admin case list envelope
  - Pagination mechanics
  - Newest-first default sorting
  - Reference search
  - Priority filter
  - Issue filter
  - Status filter
  - Assignment filter
  - Duplicate filter
  - Date range filters
  - Combined multi-condition filters
  - Case detail retrieval
  - Nonexistent case detail 404
  - Citizen denied (403)
  - Authority denied (403)
  - Unauthenticated denied (401)
  - No secret leakage
  - Citizen case ownership regression

## Scope Boundaries & Limitations
- **M4.5 Status Editing**: NOT implemented. Case status is strictly read-only.
- **M4.6 Map Operations**: NOT implemented. Map rendering is deferred.
- **M4.7 Advanced Analytics**: NOT implemented.
- **M4.8 Audit Logs**: NOT implemented.
