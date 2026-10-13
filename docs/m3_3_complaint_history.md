# M3.3 — Complaint History Dashboard Documentation

## 1. Executive Summary & Scope

Module M3.3 delivers the citizen-facing complaint history capability for the CVKI platform. Authenticated citizens can review, paginate, and inspect previously submitted civic cases, verifying case details, issue classification, and resolution tracking.

### Strict Scope Boundaries
- **In Scope (M3.3):**
  - Authenticated complaint history API (`GET /api/v1/complaint/cases/my`).
  - Strict tenant isolation: queries filter strictly by `user_id == current_user.user_id`.
  - Pagination parameters (`page`, `limit`) with safe limits (`limit <= 100`, default `10`).
  - Newest-first sorting (`created_at: -1`).
  - Lightweight summary projection omitting large base64 visual evidence payloads.
  - Case detail access restricted to the authenticated owner (`GET /api/v1/complaint/cases/{reference_id}`).
  - Frontend "My Complaints" UI with case cards, status badges, pagination, refresh controls, loading/empty states, and full detail view modal.
- **Explicitly Out of Scope (NOT implemented):**
  - Government portal submission or automated external filing.
  - External government API integration.
  - Live authority contact directories.
  - Advanced NLP / duplicate complaint detection / priority scoring.
  - Admin dashboards or system-wide complaint aggregation views.
  - Push notifications or SMS/email status alerts.
  - YOLO retraining, dataset expansion, or modifying frozen CV model artifacts (`best.pt`).

---

## 2. Complaint History API Specification

### Endpoint: `GET /api/v1/complaint/cases/my`

**Headers:**
- `Authorization`: `Bearer <jwt_token>` (Required)

**Query Parameters:**
- `page` (integer, default: 1, min: 1): Page number.
- `limit` (integer, default: 10, min: 1, max: 100): Cases per page.

**Response Schema (`ComplaintHistoryResponse`):**
```json
{
  "total": 3,
  "page": 1,
  "limit": 10,
  "total_pages": 1,
  "cases": [
    {
      "reference_id": "CVKI-20261011-B6714E",
      "created_at": "2026-10-11T07:15:30.000Z",
      "updated_at": "2026-10-11T07:15:30.000Z",
      "status": "submitted_to_cvki",
      "external_submission_status": "not_submitted",
      "issue_class": "open_manhole",
      "issue_label": "Open/Damaged Manhole",
      "severity": "high",
      "confidence": 0.88,
      "location_summary": {
        "road": "Vittal Mallya Road",
        "area": "Shanthala Nagar",
        "city": "Bengaluru",
        "state": "Karnataka",
        "latitude": 12.9716,
        "longitude": 77.5946
      },
      "complaint_title": "Hazardous Open/Damaged Manhole on Vittal Mallya Road"
    }
  ]
}
```

### Route Ordering Note
In FastAPI, `GET /api/v1/complaint/cases/my` is registered **before** `GET /api/v1/complaint/cases/{reference_id}` to prevent route parameter collision where `"my"` would otherwise be matched as a case reference ID.

---

## 3. Case Isolation & Security Architecture

1. **Strict User Scoping:**
   - The query sent to MongoDB is strictly bounded: `{ "user_id": current_user.user_id }`.
   - Cases belonging to other citizens are never fetched, counted, or returned.
2. **Compound Index Optimization:**
   - MongoDB index: `{ "user_id": 1, "created_at": -1 }` ensures high-performance retrieval and sorting without in-memory sort buffer exhaustion.
3. **Detail View Masking:**
   - Attempting to access an unowned case via `GET /cases/{reference_id}` returns `404 Not Found`, ensuring that even valid reference IDs belonging to other citizens cannot be probed or confirmed.
4. **Backward Compatibility:**
   - Historical cases from M3.1 lacking a `user_id` field are treated safely: they are never arbitrarily assigned to any user and are inaccessible through `/cases/my`.

---

## 4. Frontend UI Implementation

### Components Added & Updated
- **Header Navigation:**
  - Displays authentication status: "Logged in as: `user@example.com`" with Logout button.
  - If unauthenticated, displays "Sign In" and "Register" buttons triggering `AuthModal`.
- **My Complaints View (`MyComplaintsView`):**
  - Route: `/my-complaints` (and `/dashboard`).
  - Displays responsive cards detailing:
    - Reference ID (e.g., `CVKI-20261011-XXXXXX`)
    - Issue type and priority tag
    - Date formatted in readable citizen format (`11 Oct 2026`)
    - Location summary (`Vittal Mallya Road, Bengaluru`)
    - Internal status: `Submitted to CVKI`
    - External status: `Government Submission: Not Submitted`
  - Actions:
    - `View Details`: Opens `CaseDetailModal` displaying full issue, location, authority, complaint description, and follow-up guidance.
    - `Refresh`: Reloads cases from API with loading indicator.
    - `Pagination`: Previous/Next controls with page counters.
  - States:
    - Empty state: `"You have not created any CVKI cases yet."` with direct CTA to inspect images.
    - Unauthorized state: Prompts citizen to sign in or register.
    - Error state: Displays user-friendly error with "Try again" action.

---

## 5. Test Suite Summary

M3.3 includes 10 dedicated automated tests in `backend/tests/test_complaint_history_api.py`:
1. Empty history returns total=0 and empty list.
2. Single case history returns the case with correct summary fields.
3. Multiple cases returned accurately for authenticated user.
4. Default ordering sorts cases newest first (`created_at` desc).
5. Pagination correctly respects `page` and `limit`.
6. User isolation: User A sees only their cases; User B sees only their cases.
7. Detail access succeeds for the case owner.
8. Unknown or nonexistent reference ID returns 404.
9. Unauthorized history request without Bearer token returns 401.
10. Database unavailable returns graceful 503 error.

---

## 6. Known Limitations

- **Lightweight Projections:** Base64 image crops are excluded from history listings to maintain sub-second page load times.
- **Search & Filtering:** Filtering by date range or issue class is not implemented in M3.3 and can be added in future reporting modules.
- **External Submission:** Cases remain in `external_submission_status = "not_submitted"`; no simulated or real external transmission is executed.
