# CVKI Module M6.2 — Advanced Geospatial Civic Intelligence

## 1. Executive Summary & Architecture

Module M6.2 establishes the **Advanced Geospatial Civic Intelligence** subsystem within the CIVKI platform. The core goal of M6.2 is to bridge the semantic gap between a citizen's complaint report (or computer vision detection event) and physical civic infrastructure.

```
+---------------------------------------------------------------------------------------------------+
|                                  M6.2 GEOSPATIAL INTELLIGENCE PIPELINE                           |
|                                                                                                   |
|  [Issue / Detection Event]                                                                       |
|             |                                                                                     |
|             v                                                                                     |
|  [GPS Coordinates (lat, lon, accuracy_m)] ---> [Validation & Bounding Box Checks]                 |
|             |                                                                                     |
|             +---> [Resilient Geocoding Provider (OSM Nominatim)] <---> [MongoDB Geo Cache (TTL)]  |
|             |        |                                                                            |
|             |        v                                                                            |
|             |     [Road Identification & Context (Type, Ref, Match Quality)]                      |
|             |                                                                                     |
|             +---> [Spatial Index Query ($geoWithin / Haversine)]                                  |
|             |        |                                                                            |
|             |        v                                                                            |
|             |     [Nearby Cases Aggregation (250m default, 5000m max, time window)]               |
|             |        |                                                                            |
|             |        v                                                                            |
|             |     [Spatial Relationship Classifier (same_road, recurrence, hotspot)]              |
|             |        |                                                                            |
|             v        v                                                                            |
|  [M5.2 Recurrence / Hotspot Core] + [M6.1 Live Authority Resolver]                                |
|             |                                                                                     |
|             v                                                                                     |
|  [RBAC & Privacy Sanitizer] (Masked refs for Citizens, Scoped for Authorities)                     |
|             |                                                                                     |
|             v                                                                                     |
|  [GeospatialContextResponse] ---> [Frontend GeospatialContextPanel & Leaflet Interactive Map]      |
+---------------------------------------------------------------------------------------------------+
```

### Frozen Invariant Compliance
- **M1.13 YOLO Model Weights:** Untouched at `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`.
  - SHA-256 Checksum: `602160D4851E0D79C34CB23B828BDE474FC4C164EAF1A1C2A884CFB372F4BDA3` (verified identical).
- **M1.13 Contract & CV Dataset:** 0 files modified in `ai/` or `dataset/`.
- **M5.2 Civic Intelligence Logic:** Reused directly via clean composition without competing duplicate algorithms.
- **M6.1 Live Authority Architecture:** Kept as the authoritative source of truth for jurisdictional resolution.

---

## 2. Mathematical Geospatial Foundation

All spatial computations are isolated within `backend/app/services/spatial.py`, relying on pure mathematical formulations using the standard WGS-84 reference ellipsoid approximation ($R = 6,371,000$ meters).

### Haversine Distance Formula
Given two points $(\phi_1, \lambda_1)$ and $(\phi_2, \lambda_2)$ in radians:
$$\Delta\phi = \phi_2 - \phi_1$$
$$\Delta\lambda = \lambda_2 - \lambda_1$$
$$a = \sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)$$
$$c = 2 \cdot \text{atan2}\left(\sqrt{a}, \sqrt{1 - a}\right)$$
$$d = R \cdot c$$

Implemented in `haversine_distance_meters(lat1, lon1, lat2, lon2)` and `haversine_distance_km(...)`.

### Bearing & Compass Direction
Bearing $\theta$ from point 1 to point 2:
$$y = \sin(\Delta\lambda) \cdot \cos(\phi_2)$$
$$x = \cos(\phi_1)\sin(\phi_2) - \sin(\phi_1)\cos(\phi_2)\cos(\Delta\lambda)$$
$$\theta = \left(\text{atan2}(y, x) \cdot \frac{180}{\pi} + 360\right) \pmod{360}$$
M6.2 converts this azimuth into an 8-point compass cardinal direction (`N`, `NE`, `E`, `SE`, `S`, `SW`, `W`, `NW`) for human-readable civic spatial reports.

### GeoJSON Standard Compliance
In accordance with RFC 7946, all GeoJSON coordinates follow the **`[longitude, latitude]`** order:
```json
{
  "type": "Point",
  "coordinates": [77.5946, 12.9716]
}
```
Helper functions `to_geojson_point(lat, lon)` and `from_geojson_point(geojson)` guarantee proper transformation across the stack.

---

## 3. Resilient Geocoding Provider & Caching

The geocoding layer in `backend/app/services/geocoding_provider.py` abstracts external location lookups with an abstract base class `GeocodingProvider`.

### Provider Implementations
1. **`NominatimGeocodingProvider`:** Direct integration with OpenStreetMap Nominatim reverse geocoding (`reverse?lat=...&lon=...&format=jsonv2`). Includes User-Agent compliance, HTTP timeout handling (5.0s default), and backoff retry.
2. **`ResilientGeocodingService`:** Decorator wrapping the active provider:
   - **Step 1:** Queries local cache (`MongoGeoCache` / `InMemoryGeoCache`). If valid cache entry exists, returns immediately with `GeoSourceStatus.CACHED`.
   - **Step 2:** Calls live provider. If successful, writes to cache with configured TTL (`GEO_CACHE_TTL_SECONDS = 86400` / 24 hours) and returns `GeoSourceStatus.LIVE`.
   - **Step 3:** On network failure, provider rate limit, or timeout, attempts to read stale cache.
   - **Step 4:** If no cache exists, gracefully falls back to `GeoSourceStatus.UNAVAILABLE`, returning ungrounded coordinate fallback without crashing the complaint flow.

---

## 4. Road Identification & Context

Road attributes are extracted from reverse geocoding metadata and categorized into standardized road classifications:

| Category | Typical Indian Context | OSM Highway Tags | Match Impact |
|---|---|---|---|
| `arterial` | National/State Highways, Ring Roads | `motorway`, `trunk`, `primary` | High priority corridors |
| `collector` | Major City Roads, Connecting Avenues | `secondary`, `tertiary` | Medium-high density |
| `local` | Colony Roads, Cross Roads, Residential Streets | `residential`, `living_street`, `service`, `unclassified` | Hyper-local neighborhood |
| `pedestrian` | Walkways, Footpaths, Promenades | `pedestrian`, `footway`, `path` | High pedestrian risk |
| `unknown` | Rural / Unmapped Tracks | Missing / Unclassified | Flagged for surveyor verification |

Road matching performs normalization:
- Strips punctuation (`M.G. Road` == `MG Road`)
- Trims whitespace and normalizes case
- Ignores generic road type suffixes during equality checks

---

## 5. Location Match Quality Scoring

M6.2 explicitly communicates spatial certainty through `LocationMatchQuality`:

```
+----------------------------------------------------------------------+
| LocationMatchQuality Scale                                           |
+----------------------------------------------------------------------+
| [EXACT]       Official surveyor confirmed / pinpoint GPS match       |
| [STRONG]      GPS accuracy <= 25m AND confirmed road identified      |
| [APPROXIMATE] GPS accuracy > 25m OR unverified road geometry          |
| [UNAVAILABLE] No coordinates or reverse geocoding unavailable        |
+----------------------------------------------------------------------+
```

### GPS Uncertainty Rules:
- **Accuracy $\le 25\text{m}$:** High precision consumer GPS. Yields `LocationMatchQuality.STRONG`.
- **Accuracy $25\text{m} < \text{acc} \le 100\text{m}$:** Approximate. Road assignment tagged as approximate.
- **Accuracy $> 100\text{m}$:** Degraded accuracy. System logs uncertainty flag and widens proximity search radius.
- **Null / Missing Accuracy:** Falls back to `LocationMatchQuality.APPROXIMATE` when road is resolved.

---

## 6. Spatial Civic Relationships & Proximity Intelligence

In `backend/app/services/geospatial_intelligence.py`, nearby civic context within a radial buffer (default 250 meters, max 5,000 meters) is analyzed to produce relational classifications:

1. **`SAME_ROAD`:** Two cases reside along the same normalized road corridor and within reasonable travel proximity.
2. **`NEARBY`:** Cases within Euclidean/Haversine distance threshold (e.g., 250m).
3. **`RECURRENCE_CANDIDATE`:** Cases sharing the same issue category on the same road or within 150m created within the temporal window (default 30 days). Directly correlates with M5.2 recurrence detection.
4. **`HOTSPOT_CONTEXT`:** Multiple overlapping civic complaints within an acute spatial cluster, indicating systemic infrastructure breakdown.

---

## 7. Database Architecture & MongoDB Indexing

### 1. `complaint_cases` 2dsphere Index
A sparse 2dsphere index was added to the `complaint_cases` collection on `geo_location`:
```python
IndexModel(
    [("geo_location", "2dsphere")],
    name="complaint_cases_geo_location_2dsphere",
    sparse=True,
)
```
Every case saved through `ComplaintCaseRepository` automatically computes and persists the GeoJSON `geo_location` point when latitude and longitude are valid.

### 2. `geo_cache` Collection & TTL Index
Reverse geocoding responses are cached deterministically by a coordinate spatial hash `geo:{lat:.5f}:{lon:.5f}`:
```python
IndexModel([("cache_key", 1)], unique=True, name="geo_cache_key_idx")
IndexModel([("expires_at", 1)], expireAfterSeconds=0, name="geo_cache_ttl_idx")
IndexModel([("retrieved_at", -1)], name="geo_cache_retrieved_idx")
```

---

## 8. Role-Based Access Control (RBAC) & Privacy Protection

Geospatial data inherently carries citizen privacy risks (e.g., home address proximity). M6.2 enforces strict privacy guards at the API and service layers:

1. **Citizen & Anonymous Masking:**
   - Case reference IDs are masked: `CVKI-20261014-001` $\rightarrow$ `CVKI-20261014-***`.
   - Citizen reporter IDs (`user_id`, `email`, citizen notes) are completely stripped from nearby case queries.
2. **Authority Scoping:**
   - When an `authority` user requests `/api/v1/geospatial/cases/{reference_id}/context`, the backend verifies whether the case is assigned to that authority.
   - Unauthorized attempts return `HTTP 403 Forbidden: "Authorities can only view geospatial intelligence for cases assigned to them."`
3. **Admin Full Visibility:**
   - Admin users have full unmasked access to reference IDs and assignment details for city-wide civic orchestration.

---

## 9. API Surface

| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/api/v1/geospatial/context` | POST | Public / All | Computes geospatial intelligence from raw GPS point and issue category |
| `/api/v1/geospatial/cases/nearby` | GET | Public / All | Returns nearby cases within radius (meters) and time window (days) |
| `/api/v1/geospatial/cases/{ref}/context` | GET | Authenticated | Returns geospatial context for a specific registered complaint case |
| `/api/v1/geospatial/road/resolve` | GET | Public / All | Quick endpoint to reverse-geocode and normalize road name |

---

## 10. Frontend Interactive Component

A reusable, responsive React component `GeospatialContextPanel.jsx` was built and integrated into both Citizen and Admin case modals:

- **Header Bar:** Shows normalized road name, road type tag, and match quality badge (`exact`, `strong`, `approximate`, `unavailable`).
- **Interactive Mini-Map:** Leaflet map centered on case coordinates with an active marker and a 250m radial context circle.
- **Nearby Case Aggregation:** Displays the count of nearby open/resolved issues within the radius.
- **Relational Alert Banners:** Displays warnings when same-road recurrence or acute hotspot clusters are detected.
- **Degraded Fallback:** Renders a clean message when geocoding is unavailable or when the case lacks GPS coordinates.

---

## 11. Test Matrix & Validation Results

The M6.2 test suite in `backend/tests/test_geospatial_intelligence_m62.py` implements 24 rigorous test scenarios covering all required edge cases:

| Scenario | Category | Expected Behavior | Status |
|---|---|---|---|
| A | Valid Coordinate Normalization | Normalizes lat/lon within valid bounds | PASSED |
| B | Invalid Latitude Rejected | Lat > 90 or < -90 raises validation error | PASSED |
| C | Invalid Longitude Rejected | Lon > 180 or < -180 raises validation error | PASSED |
| D | Missing Coordinates Rejected | None or (0,0) rejected | PASSED |
| E | GPS Accuracy Handling | Accuracy thresholds correctly mapped to quality | PASSED |
| F | Haversine Known Pairs | Distance checks on Bengaluru & Delhi coordinates | PASSED |
| G | Road Match Exact | Verifies exact road identity matching | PASSED |
| H | Road Match Approximate | Case & punctuation normalization | PASSED |
| I | Geocoder Unavailable | Graceful fallback without 500 error | PASSED |
| J | Cached Geocoder Result | Returns cached road when provider is down | PASSED |
| K | Stale Cache Expiration | Correctly identifies expired cache entries | PASSED |
| L | Nearby Case Search | Finds cases within 250m, excludes distant cases | PASSED |
| M | Radius Limit | Enforces max radius of 5000m | PASSED |
| N | Time-Window Filter | Excludes cases outside time window | PASSED |
| O | Category Filter | Filters nearby cases by issue class | PASSED |
| P | Unauthorized Case Access | HTTP 403 for authorities viewing unassigned cases | PASSED |
| Q | Citizen Privacy Protection | Strips PII and masks reference ID suffix | PASSED |
| R | Same-Road Relationship | Classifies same-road spatial relationship | PASSED |
| S | Recurrence Context | Classifies recurrence candidates | PASSED |
| T | Hotspot Context | Classifies hotspot clusters | PASSED |
| U | Authority Integration | M6.1 authority resolver integrated seamlessly | PASSED |
| V | Coordinate Order | Validates GeoJSON `[lon, lat]` order | PASSED |
| W | Bounding Box Behavior | Validates min/max lat/lon bounding box | PASSED |
| X | Existing M5.2 Regression | Validates M5.2 recurrence calculation unchanged | PASSED |

### Regression Suite Results
- `tests/test_geospatial_intelligence_m62.py`: **24 passed** in 6.93s.
- Full pytest test suite across entire backend: **439 passed** in 146.25s (100% pass rate).
- Frontend lint (`npm run lint`): **0 errors**.
- Frontend production bundle (`npm run build`): **Built successfully in 1.17s**.
- YOLOv8 model hash: **Identical (`602160D4851E0D79...`)**.
