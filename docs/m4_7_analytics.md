# M4.7 Operational Analytics & Insights

## Overview
Module M4.7 implements operational intelligence and reporting for CVKI. It executes native MongoDB aggregation pipelines across persistent complaint records to generate factual, non-simulated analytics. It provides breakdown distributions across categories, priorities, lifecycle statuses, duplicate detections, geographic hotspots, time series trends, and clean CSV export capability.

---

## Aggregation Pipeline Architecture

The analytics engine is implemented in `backend/app/services/analytics.py` and strictly avoids synthetic metric generation. All metrics are computed dynamically over stored documents in the `complaint_cases` collection:

1. **Volume & Turnaround KPIs**:
   - `total_cases`: Total document count matching criteria.
   - `open_cases`: Cases with status in `{"submitted_to_cvki", "under_review", "assigned", "in_progress"}`.
   - `resolved_cases`: Cases with status in `{"resolved", "closed"}`.
   - `resolution_rate_percent`: Calculated as `(resolved_cases / total_cases) * 100`.
   - `average_priority_score`: Calculated via `$avg` over `priority_analysis.priority_score`.

2. **Categorical Distributions**:
   - `priority_distribution`: Grouping by `priority_analysis.priority_level` (`P1`, `P2`, `P3`, `P4`).
   - `issue_distribution`: Grouping by `issue.class_name`.
   - `status_distribution`: Grouping by canonical `status`.
   - `duplicate_distribution`: Grouping by `duplicate_analysis.classification` (`unique`, `duplicate`, `possible_duplicate`).

3. **Geographic Hotspot Aggregation**:
   - Groups cases by road/area and city:
     ```python
     {"$group": {"_id": {"road": "$location.road", "city": "$location.city"}, "count": {"$sum": 1}}}
     ```
   - Sorts by incident count descending to identify high-density municipal corridors.

4. **Time Series Aggregation**:
   - Aggregates cases by `$dateToString` (`daily`, `weekly`, or `monthly`) to identify trends and peak reporting windows.

---

## API Endpoints

### 1. Operational Analytics Dashboard Endpoint
- **Route**: `GET /api/v1/admin/analytics`
- **Access**: Role `admin` required.
- **Query Parameters**:
  - `issue`: Filter by issue category.
  - `priority`: Filter by priority tier (`P1`–`P4`).
  - `status`: Filter by status.
  - `city`: Filter by city.
  - `authority`: Filter by authority name.
  - `created_from`: ISO timestamp lower bound.
  - `created_to`: ISO timestamp upper bound.
  - `group_by`: Time series interval (`daily`, `weekly`, `monthly`).
- **Response**: `OperationalAnalyticsResponse` JSON schema.

### 2. Analytics CSV Export Endpoint
- **Route**: `GET /api/v1/admin/analytics/export`
- **Access**: Role `admin` required.
- **Query Parameters**: Same as `/analytics`.
- **Response**: Streamed CSV file (`text/csv`) with sanitized headers:
  - Header: `Content-Disposition: attachment; filename="cvki_operational_analytics.csv"`.
  - Columns: Metric Category, Key, Count / Metric Value, Percentage / Score.

---

## Frontend Integration (`AdminAnalyticsView`)

- **KPI Metric Cards**: Displays Total Cases, Resolved Cases, Resolution Rate %, and Average Priority Score.
- **CSS / SVG Bar Distributions**: Visual horizontal progress tracks for Priority, Issue Category, Status, and Duplicate Classifications.
- **Hotspot Ranking Table**: Displays top municipal corridors ranked by case frequency.
- **CSV Export Action**: Downloads live CSV report via `downloadAnalyticsCsv()`.
- **Integrity Notice**: Explanatory disclaimer guaranteeing factual metrics derived strictly from persistent MongoDB cases.

---

## Test Verification
- Test file: `backend/tests/test_analytics_m47.py`
- Total tests: **19 passing tests**.
- Validated:
  - Ground-truth volume and resolution rate computation.
  - Distribution aggregations across priority, issue, and status.
  - Hotspot clustering and sorting.
  - Time series grouping across daily, weekly, and monthly intervals.
  - CSV export formatting and download stream headers.
  - RBAC protection (rejection of unauthorized roles).
