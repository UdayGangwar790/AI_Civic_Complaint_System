# M4.6 Map Operations & Spatial Dispatch

## Overview
Module M4.6 provides geospatial dispatch intelligence and interactive mapping operations for CVKI. It enables administrative and authority personnel to visualize civic issues geographically, filter cases by priority, category, status, and timeline, inspect incidents directly from map markers, and detect unmapped or coordinate-deficient cases without relying on synthetic or fabricated coordinates.

---

## Coordinate Integrity & Validation Rules

Strict geographic validation is enforced in `backend/app/services/map_case.py`:
1. **Coordinate Completeness**: Cases missing latitude or longitude are excluded from plotting.
2. **Boundary Validation**:
   - Latitude must be between `-90.0` and `+90.0`.
   - Longitude must be between `-180.0` and `+180.0`.
3. **Null-Island Protection**:
   - Coordinates at `(0.0, 0.0)` or near-zero anomalies (`abs(lat) < 0.001 and abs(lon) < 0.001`) are rejected as unmapped GPS errors.
4. **Unmapped Count Transparency**:
   - The query response explicitly returns `unmapped_count` alongside `items`, ensuring full transparency regarding cases lacking valid GPS tags.

---

## Data Schemas

Defined in `backend/app/schemas/map_case.py`:
```python
class MapCaseItem(BaseModel):
    reference_id: str
    issue: ComplaintIssueSummary
    location: Optional[ComplaintLocationSummary]
    priority_analysis: Optional[ComplaintPrioritySummary]
    status: str
    created_at: datetime
    assignment: Optional[CaseAssignmentSummary]

class MapCasesResponse(BaseModel):
    items: list[MapCaseItem]
    total_mapped: int
    unmapped_count: int
```

---

## API Endpoints

### 1. Admin Map Cases Endpoint
- **Route**: `GET /api/v1/admin/map/cases`
- **Access**: Role `admin` required.
- **Query Parameters**:
  - `issue`: Filter by issue class name (e.g., `open_damaged_manhole`).
  - `priority`: Filter by priority tier (`P1`, `P2`, `P3`, `P4`).
  - `status`: Filter by lifecycle status (`submitted_to_cvki`, `assigned`, `in_progress`, etc.).
  - `city`: Filter by municipal city name.
  - `authority`: Filter by responsible authority name.
  - `assignment`: Filter by `assigned` or `unassigned`.
  - `created_from`: ISO timestamp lower bound.
  - `created_to`: ISO timestamp upper bound.
  - `limit`: Result count ceiling (default 250, maximum 500).
- **Response**: `MapCasesResponse`.

### 2. Authority Map Cases Endpoint
- **Route**: `GET /api/v1/authority/map/cases`
- **Access**: Role `authority` required.
- **Scoping**: Automatically scopes results to cases assigned to the authenticated authority user (`assigned_to_user_id == current_user.user_id`).
- **Response**: `MapCasesResponse`.

---

## Frontend Integration (`AdminMapView`)

- **Interactive Leaflet Mapping**: Built using Vanilla Leaflet (`L.map`) with OpenStreetMap tiles.
- **Priority-Coded Circle Markers**:
  - `P1 Critical`: `#dc2626` (Red)
  - `P2 High`: `#ea580c` (Orange)
  - `P3 Medium`: `#d97706` (Amber)
  - `P4 Low`: `#16a34a` (Green)
- **Interactive Marker Popups**: Displays Reference ID, issue label, corridor address, priority pill, and an "Inspect Case Details" button that opens the detailed review modal.
- **Automatic Bounds Fitting**: Auto-fits viewport to visible markers via `map.fitBounds(latLngs)`.
- **KPI Counter Badges**: Displays plotted count and unmapped count in the header.

---

## Test Verification
- Test file: `backend/tests/test_map_operations_m46.py`
- Total tests: **16 passing tests**.
- Validated:
  - Valid coordinate plotting and bounding.
  - Rejection of `(0, 0)` Null Island coordinates.
  - Correct computation of `unmapped_count`.
  - Multi-parameter filtering (priority, issue, status, date bounds).
  - Authority scoping and isolation.
  - Limit boundary caps (max 500).
