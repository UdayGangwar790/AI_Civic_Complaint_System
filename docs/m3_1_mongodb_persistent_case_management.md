# CVKI Module 3.1 - MongoDB Persistent Case Management

## Statement of Scope

"M3.1 provides persistent CVKI case storage. It does not implement government submission, citizen authentication, NLP intelligence, duplicate detection, priority scoring, or admin analytics."

---

## 1. Objective

The objective of Module 3.1 is to replace the temporary in-memory case repository introduced in M2.10 with production-grade MongoDB persistent storage. Complaint cases, reference IDs, citizen-edited text, authority states, detection metadata, and evidence references now survive application restarts and lifecycle events without altering the existing API contracts, response models, or frontend citizen inspection flow.

---

## 2. Previous In-Memory Architecture

In Module 2.10:
- Case storage was backed by `InMemoryComplaintCaseRepository`, storing objects in an in-process Python dictionary protected by a thread `Lock`.
- When the backend restarted or terminated, all cases were irrevocably lost.
- No database connections, configuration parameters, or index constraints existed.
- Re-querying previously created reference IDs after restart resulted in HTTP 404 responses.

---

## 3. New MongoDB Persistence Architecture

In Module 3.1:
- **Client & Pool Management**: Managed asynchronously via `motor.motor_asyncio.AsyncIOMotorClient`, integrated directly with FastAPI's application lifespan manager in [backend/app/main.py](../backend/app/main.py).
- **Single Connection Pool**: A single, shared client is initialized on application startup and gracefully closed upon application shutdown in [backend/app/core/database.py](../backend/app/core/database.py). No per-request connection overhead is incurred.
- **Repository Abstraction**: `MongoComplaintCaseRepository` implements the `ComplaintCaseRepository` abstract interface in [backend/app/services/complaint_case.py](../backend/app/services/complaint_case.py), cleanly isolating database persistence logic from API controllers.
- **Backward Compatibility**: `InMemoryComplaintCaseRepository` remains available for isolated synchronous unit tests.

---

## 4. Configuration

Configuration options are managed via `pydantic-settings` in [backend/app/core/config.py](../backend/app/core/config.py) and loaded from `.env`:

| Setting | Default | Description |
| :--- | :--- | :--- |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection URI string |
| `MONGODB_DB_NAME` | `cvki` | Active database name |
| `MONGODB_TIMEOUT_MS` | `5000` | Connection & server selection timeout in milliseconds |

### Credential Protection & Logging Safety
The helper `sanitize_mongodb_uri()` masks sensitive credentials (`mongodb://user:***@host:port/db`) in all system logs. MongoDB credentials are never logged in plain text.

---

## 5. Collection and Schema

- **Database**: `cvki` (or configured via `MONGODB_DB_NAME`)
- **Collection**: `complaint_cases`

### Persisted Document Schema

```json
{
  "_id": "ObjectId(...)",
  "reference_id": "CVKI-20261011-EAD15D",
  "status": "submitted_to_cvki",
  "created_at": "2026-10-11T07:05:33.732Z",
  "updated_at": "2026-10-11T07:05:33.732Z",
  "external_submission_status": "not_submitted",
  "issue": {
    "class_name": "open_damaged_manhole",
    "label": "Open/Damaged Manhole",
    "severity": "high",
    "confidence": 0.83
  },
  "location": {
    "road": "Civic Road",
    "area": "Central Area",
    "city": "Sample City",
    "district": "Sample District",
    "state": "Sample State",
    "latitude": 12.34,
    "longitude": 56.78
  },
  "authority": {
    "authority_status": "verified",
    "road_owner": { "name": "Owner", "source": "Official register" },
    "maintenance_authority": { "name": "Maintainer", "source": "Official register" },
    "builder_or_contractor": null,
    "evidence": [
      {
        "source_name": "Official register",
        "source_type": "official_database",
        "claim": "Roles verified."
      }
    ],
    "limitations": []
  },
  "complaint": {
    "language": "en",
    "title": "Edited manhole report",
    "description": "Citizen-edited final complaint text."
  },
  "evidence": [
    "Photo evidence is attached.",
    "Model confidence 83%."
  ],
  "follow_up": {
    "guidance": "Your complaint has been created inside the CVKI application and saved as a CVKI case...",
    "external_submission_status": "not_submitted"
  }
}
```

- **Binary Policy**: Image binary files are NOT stored in MongoDB; only evidence metadata and model confidence descriptions are persisted.
- **Privacy Policy**: No unnecessary PII is introduced.
- **Timestamps**: Stored strictly as UTC datetimes.

---

## 6. Indexes & Uniqueness Enforcement

Indexes are automatically ensured at application startup via `init_mongo_indexes()`:

1. **Unique Index**:
   ```javascript
   db.complaint_cases.createIndex({ "reference_id": 1 }, { "unique": true })
   ```
   Guarantees that duplicate reference IDs cannot be inserted or silently overwrite existing cases. Violations raise `pymongo.errors.DuplicateKeyError`, caught and converted into `ComplaintCaseDuplicateError` (HTTP 409).
2. **Timestamp Index**:
   ```javascript
   db.complaint_cases.createIndex({ "created_at": 1 })
   ```
   Optimizes chronological ordering and temporal queries.

---

## 7. API Behavior

All endpoints preserve the M2 API contract and response schemas:

### `POST /api/v1/complaint/cases`
- **Validation**: Enforces `ComplaintCaseCreateRequest` schema rules (issue labels, non-empty complaint title and description, valid severity).
- **Generation**: Creates a unique `CVKI-YYYYMMDD-XXXXXX` reference ID.
- **Persistence**: Persists the document to the MongoDB `complaint_cases` collection.
- **Response**: HTTP 200 with complete `ComplaintCase` payload.

### `GET /api/v1/complaint/cases/{reference_id}`
- **Lookup**: Queries MongoDB by `reference_id`.
- **Response**: HTTP 200 with `ComplaintCase` if found; HTTP 404 with `"detail": "CVKI case was not found."` if missing.

### `GET /api/v1/complaint/cases/{reference_id}/status`
- **Lookup**: Queries MongoDB by `reference_id`.
- **Response**: HTTP 200 with `ComplaintCaseStatus` (`status: "submitted_to_cvki"`, `external_submission_status: "not_submitted"`).

### `GET /api/health`
- Verifies MongoDB ping liveness.
- If healthy: `{"status": "ok", "service": "CVKI backend", "database": "connected"}`.
- If disconnected: `{"status": "degraded", "service": "CVKI backend", "database": "unavailable"}`.

---

## 8. Error Handling & Failure Safeguards

1. **Database Unavailability**:
   - If MongoDB is down at startup or becomes unreachable, complaint case endpoints return HTTP 503 Service Unavailable (`"Database service is unavailable. Complaint case persistence failed."`).
   - The system **never** silently falls back to in-memory persistence.
   - Unrelated endpoints (`/api/v1/model/status`, `/api/v1/detection/predict`, `/api/v1/location/reverse-geocode`, `/api/v1/authority/resolve`, `/api/v1/complaint/draft`) remain fully functional.
2. **Duplicate Keys**:
   - Handled via `ComplaintCaseDuplicateError` -> HTTP 409 Conflict.
3. **Missing Cases**:
   - Handled via `ComplaintCaseNotFoundError` -> HTTP 404 Not Found.
4. **Validation Errors**:
   - Schema violations -> HTTP 422 Unprocessable Content.

---

## 9. Verification & Test Suite

The test suite consists of **64 passing tests** across unit, integration, and regression suites:

### Dedicated M3.1 Persistence Suite (`backend/tests/test_mongo_persistence.py`):
1. `test_01_mongodb_configuration_loading`: Configuration parsing and URI credential masking.
2. `test_02_case_creation_persists_in_mongodb`: Real MongoDB document creation and field persistence verification.
3. `test_03_case_retrieval`: Case retrieval by `reference_id` from database.
4. `test_04_status_retrieval`: Case status retrieval preserving `not_submitted`.
5. `test_05_unknown_reference_returns_404`: Non-existent reference returns 404.
6. `test_06_duplicate_reference_protection`: Unique index enforcement prevents overwriting and raises duplicate error.
7. `test_07_required_field_validation`: 422 error on invalid/missing fields.
8. `test_08_timestamp_existence`: `created_at` and `updated_at` UTC timestamps verified.
9. `test_09_data_survives_repository_reinitialization`: Verifies data survives client teardown and repository reinitialization.
10. `test_10_mongodb_failure_handling`: Verifies HTTP 503 on database unavailability and degraded health status.

### Real MongoDB Verification:
- **YES**: All tests were executed against a real running MongoDB 8.2.5 instance on `localhost:27017` using test-isolated database `cvki_test_m3_1` and cleaned up after execution.

---

## 10. Regression Results

- **Backend Test Suite**: 64 tests ran, 64 passed (0 failures, 0 errors).
- **Frontend Build**: `vite build` completed successfully (dist generated).
- **Frontend Lint**: `oxlint` reported 0 errors, 0 warnings across all files.
- **Model Weight Verification**: `best.pt` SHA-256 hash remains unchanged:
  `602160D4851E0D79C34CB23B828BDE474FC4C164EAF1A1C2A884CFB372F4BDA3`.

---

## 11. Known Limitations & Intentionally Not Implemented

- **No external government submission**: CVKI reference ID is strictly internal.
- **No citizen authentication**: Anonymous/stateless report creation is retained.
- **No duplicate complaint clustering / NLP intelligence**: Deferred to future modules.
- **No priority / risk scoring**: Deferred to future modules.
- **No administrative dashboard / analytics**: Deferred to future modules.
- **No contact data / authority integration**: Only M2 authority resolution is referenced.
