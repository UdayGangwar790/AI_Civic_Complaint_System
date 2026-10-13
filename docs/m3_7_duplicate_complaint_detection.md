# M3.7 — Duplicate Complaint Detection

## 1. Objective
The objective of Module 3.7 is to detect whether an incoming civic complaint is:
- `unique`
- `possible_duplicate`
- `duplicate`

The system goes beyond exact string matching by combining semantic textual similarity with spatiotemporal metadata (geographic distance and temporal window) and issue category concordance.

## 2. Duplicate Definitions & Classifications
- **`unique`**: The complaint presents novel civic issue details or occurs outside the spatial/temporal proximity window of existing cases. Created and routed normally.
- **`possible_duplicate`**: The complaint exhibits moderate-to-high semantic overlap or geographic proximity to an open case within the active time window. Created with duplicate metadata attached to aid municipal consolidation without rejecting citizen submission.
- **`duplicate`**: The complaint satisfies high textual similarity, matches the civic issue category, and falls within both the geographic radius threshold and temporal window of an active reference complaint. Created with duplicate status flagged, preserving citizen submission while preventing duplicate municipal dispatch.

## 3. Similarity Method
To guarantee deterministic execution and reproducibility without heavy transformer runtime overhead, the module uses a documented, transparent NLP approach:
- **Feature Extraction**: `scikit-learn` `TfidfVectorizer` configured with sublinear term-frequency scaling, combining word n-grams `(1, 2)` and character n-grams `(3, 5)`. This enables robust similarity computation across noisy text, spelling variations, and phonetic transliterations common in Indian civic reporting.
- **Similarity Metric**: Cosine similarity between normalized TF-IDF term vectors:
  $$\text{Cosine Similarity}(\vec{u}, \vec{v}) = \frac{\vec{u} \cdot \vec{v}}{\|\vec{u}\|_2 \|\vec{v}\|_2}$$
- **Active Method Identifier**: Explicitly reported as `tfidf_cosine_ngram_baseline`.

## 4. Configurable Engineering Thresholds
All thresholds are defined in `backend/app/core/config.py` rather than hardcoded magic numbers:
- `DUPLICATE_SIMILARITY_THRESHOLD`: `0.82` (minimum cosine similarity for high duplicate confidence).
- `POSSIBLE_DUPLICATE_SIMILARITY_THRESHOLD`: `0.55` (minimum cosine similarity for possible duplicate detection).
- `DUPLICATE_DISTANCE_METERS`: `150.0` meters (spatial radius calculated via the great-circle Haversine formula).
- `DUPLICATE_TIME_WINDOW_HOURS`: `72.0` hours (active temporal window for open complaints).

*Note: These values represent initial engineering baseline thresholds and are not claimed to be scientifically validated optimal parameters.*

## 5. Spatiotemporal & Metadata Signals
The classification combines multiple independent evidence signals:
1. **Textual Similarity**: TF-IDF cosine score comparing the combined title and description.
2. **Geographic Proximity**: Haversine distance in meters between complaint coordinates. If coordinates are omitted from either complaint, distance comparison is bypassed and spatial distance is reported as `null`.
3. **Temporal Proximity**: Elapsed hours between complaint creation timestamps.
4. **Issue Concordance**: Boolean match between reported civic issue categories (`open_damaged_manhole`, `damaged_missing_road_sign`, `road_waterlogging`, `other_civic_issue`).

Complaints with the same issue category but 10 km apart are correctly classified as `unique`.

## 6. Citizen Privacy & Data Security
To prevent privacy leakage across citizen accounts:
- Duplicate detection **never exposes** another citizen's full complaint text, personal description, contact details, user ID, password, or JWT.
- Responses only return safe, sanitized metadata:
  - `matched_reference_id` (public case reference, e.g., `CVKI-20261011-ABC12345`)
  - `similarity_score`
  - `distance_meters`
  - `time_difference_hours`
  - `issue_match`
  - Sanitized explanation string
- Unauthorized requests without valid authentication tokens are rejected (`401 Unauthorized`).

## 7. Database Query Strategy & Scalability
- Operates directly against the existing MongoDB `complaint_cases` collection via `MongoComplaintCaseRepository.list_recent_candidates`.
- **Bounded Query Execution**: Does not load the entire collection into memory. Queries are bounded by `limit` (default: 50 most recent records) and filtered by status where appropriate (`OPEN`, `INVESTIGATING`, etc.).
- Preserves asynchronous non-blocking I/O with Motor in production while seamlessly supporting synchronous in-memory storage during unit tests.

## 8. API Specification
- **Endpoint**: `POST /api/v1/complaint/duplicate-check`
- **Authentication**: Bearer JWT (`get_current_active_user`)
- **Request Body**:
```json
{
  "text": "Deep open manhole opposite metro pillar 42, dangerous for bikes",
  "issue_category": "open_damaged_manhole",
  "latitude": 12.9716,
  "longitude": 77.5946,
  "created_at": "2026-10-11T12:00:00Z"
}
```
- **Response Body**:
```json
{
  "classification": "possible_duplicate",
  "similarity_score": 0.74,
  "matched_reference_id": "CVKI-20261011-85FE6D",
  "distance_meters": 42.5,
  "time_difference_hours": 3.2,
  "issue_match": true,
  "reason": "High semantic similarity (0.74) and proximate location (42.5m) within 3.2h for open_damaged_manhole."
}
```

## 9. Disclaimers & Known Limitations
> [!IMPORTANT]
> **Duplicate detection identifies similarity evidence and does not prove that two complaints describe the same real-world event.**

- **Physical Incident Disambiguation**: Two distinct manholes 50 meters apart on the same street may exhibit similar wording and proximity without representing the identical physical pit. Municipal inspection remains necessary.
- **Submission Preservation**: Complaints flagged as duplicates are never deleted or rejected silently; they are persisted with duplicate metadata attached to preserve citizen evidence and auditability.

## 10. Verification & Test Suite
Module 3.7 is validated by `backend/tests/test_duplicate_m37.py` covering:
1. Exact text duplicate matching.
2. Semantically similar complaints (phrasing variations).
3. Same civic issue category but distinct geographic locations (> 1 km apart).
4. Same location coordinates but distinct issue categories.
5. Large distance variance.
6. Temporal window expiry (> 72 hours).
7. Zero existing cases in repository (`unique`).
8. Prevention of private text leakage in duplicate response.
9. Rejection of unauthenticated duplicate check requests (`401`).
10. Verification of configurable similarity thresholds.
11. Resilient execution when coordinates are missing (`null`).
12. Resilient handling of malformed input payloads.
13. MongoDB failure and fallback isolation.
14. Regression testing ensuring case creation persists duplicate intelligence without regression.
