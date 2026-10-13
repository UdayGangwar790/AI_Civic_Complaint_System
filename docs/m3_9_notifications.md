# M3.9 Automated Case Notification & Citizen Alerts

## Overview
Module **M3.9** implements an application-level, in-app notification infrastructure for the Civic Vision & Knowledge Intelligence (CVKI) platform. It provides persistent alerts for complaint lifecycle events (case creation, priority assignment, duplicate detection, status changes, and government submission preparation) without sending unsolicited external communications or falsely claiming government submissions.

---

## Architecture & Principles
1. **Application-Level In-App Alerts Only:**
   - Notifications represent CVKI platform events (`delivery_status: in_app`).
   - CVKI case notifications and external government dispatch notifications are strictly decoupled.
   - No mock or simulated SMS, WhatsApp, or email dispatches.
   - Future channels (email, SMS, web push) are abstracted for future extension without generating false delivery receipts.

2. **Strict User Privacy & Ownership:**
   - Notifications are bound to the authenticated user ID (`user_id`) obtained from verified JWT credentials.
   - Cross-user notification reading or updates are blocked with `403 Forbidden` / `404 Not Found`.
   - Notification messages contain no secrets, tokens, passwords, or sensitive citizen demographics.

3. **No Phantom Notifications:**
   - Notifications are only persisted upon successful database commits.
   - If a complaint case creation or update fails, no notification is written.

---

## Notification Types & Triggers

| Type | Trigger | Priority Mapping | Description |
| :--- | :--- | :--- | :--- |
| `case_created` | Complaint case created in CVKI | P3 (Medium) | Informs citizen that their complaint case has been registered. |
| `priority_assigned` | M3.8 priority scoring computed | Dynamic: P1 / P2 / P3 / P4 | Reflects priority triage (e.g. Critical Safety Hazard -> P1). |
| `duplicate_detected` | M3.7 flags `duplicate` or `possible_duplicate` | Dynamic (P2 for duplicate, P3 for possible) | Informs citizen of spatial/text similarity with prior cases. |
| `case_status_changed` | Case status transition | P3 (Medium) | Emitted when case workflow state updates. |
| `follow_up_due` | Case SLA / follow-up milestone | Dynamic | Alerts citizen to follow up on pending case. |
| `government_submission_prepared` | M3.10 package generated | P3 (Medium) | Informs citizen that the dispatch package is compiled for review. |
| `government_submission_status_changed` | Government submission status update | P3 (Medium) | Reserved for verified government interactions. |
| `system_notification` | System-wide maintenance or notice | P4 (Low) / P3 | Administrative alerts. |

---

## MongoDB Schema & Indexes

### Collection: `notifications`
```json
{
  "notification_id": "notif_6641abc912344efb",
  "user_id": "67083049182390abdf011223",
  "reference_id": "CVKI-20261011-B61A9C",
  "type": "case_created",
  "title": "Case Created Successfully",
  "message": "Your CVKI case CVKI-20261011-B61A9C for pothole has been created.",
  "priority": "P3",
  "is_read": false,
  "created_at": "2026-10-11T17:15:30.123456Z",
  "metadata": {
    "issue_category": "pothole",
    "delivery_status": "in_app"
  }
}
```

### Database Indexes
- `notification_id` (Unique index)
- `user_id` + `created_at` (Compound descending index for paginated feeds)
- `user_id` + `is_read` (Compound index for rapid unread-count and unread filtering)
- `reference_id` + `created_at` (Compound index for case-linked audit trail)

---

## REST API Endpoints

### 1. List Notifications
`GET /api/v1/notifications`
- **Query Parameters:**
  - `page` (integer, default: 1)
  - `page_size` (integer, default: 20, max: 100)
  - `unread_only` (boolean, optional)
- **Response:**
```json
{
  "total": 3,
  "unread_count": 2,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "items": [
    {
      "notification_id": "notif_6641abc912344efb",
      "user_id": "67083049182390abdf011223",
      "reference_id": "CVKI-20261011-B61A9C",
      "type": "case_created",
      "title": "Case Created Successfully",
      "message": "Your CVKI case CVKI-20261011-B61A9C for pothole has been created.",
      "priority": "P3",
      "is_read": false,
      "created_at": "2026-10-11T17:15:30.123456Z",
      "metadata": {
        "issue_category": "pothole",
        "delivery_status": "in_app"
      }
    }
  ]
}
```

### 2. Unread Notification Count
`GET /api/v1/notifications/unread-count`
- **Response:**
```json
{
  "unread_count": 2
}
```

### 3. Mark Single Notification as Read
`POST /api/v1/notifications/{notification_id}/read`
- **Response:**
```json
{
  "status": "success",
  "notification_id": "notif_6641abc912344efb",
  "is_read": true
}
```

### 4. Mark All Notifications as Read
`POST /api/v1/notifications/read-all`
- **Response:**
```json
{
  "status": "success",
  "marked_count": 2
}
```

---

## Frontend Integration
- **Notification Bell Header:** Displayed for authenticated users with dynamic unread counter badge that refreshes on an interval.
- **Notification Dropdown:** Shows type tag, priority badge (P1–P4), title, message preview, timestamp, and "Mark read" button.
- **Deep Linking to Cases:** Clicking any notification linked to a `reference_id` immediately opens the case detail modal.
- **State Handling:** Full handling for loading spinner, empty notifications state, API errors, and mark-all-read.
