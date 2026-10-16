# CVKI Module M6.3 — Real-Time External Civic Data Intelligence

## 1. Executive Summary & Architecture

Module M6.3 introduces the **Real-Time External Civic Data Intelligence** subsystem within the CIVKI platform. The core goal of M6.3 is to enrich civic issue context using real-time or periodically refreshed external environmental and municipal data.

```
+---------------------------------------------------------------------------------------------------+
|                                  M6.3 EXTERNAL CIVIC DATA PIPELINE                                |
|                                                                                                   |
|  [Civic Issue & Geospatial Location (lat, lon, issue_category, window_hours)]                     |
|                                     |                                                             |
|                                     v                                                             |
|                    [Spatial Bounds & Window Validation]                                           |
|                                     |                                                             |
|                                     v                                                             |
|              [External Civic Cache (InMemory / MongoDB TTL Index)]                                |
|                         |                              |                                          |
|                Fresh Cache Hit?                 Cache Miss / Expired?                             |
|                    [YES]                               [NO]                                       |
|                      |                                   v                                        |
|                      |                 [Provider Abstraction Layer]                               |
|                      |                 +-- OpenMeteoWeatherProvider                               |
|                      |                 +-- TomTomTrafficProvider (Modular)                        |
|                      |                 +-- OpenDataCivicProvider (Extensible)                     |
|                      |                                   |                                        |
|                      |                           [SSRF Validation]                                |
|                      |                                   |                                        |
|                      |                       [HTTP Call with Timeout]                             |
|                      |                                   |                                        |
|                      |                  +----------------+----------------+                       |
|                      |                  | Success (LIVE) | Failure/Timeout|                       |
|                      |                  v                v                |                       |
|                      |            [Store Cache]     [Stale Cache Fallback]|                       |
|                      |                  |                |                |                       |
|                      +------------------+----------------+                |                       |
|                                         |                                 |                       |
|                                         v                                 v                       |
|                     [Normalized Schemas & WMO Weather Interpretation]     |                       |
|                                         |                                 |                       |
|                                         v                                 |                       |
|                 [Non-Causal Environmental Correlation Engine]             |                       |
|                    (e.g., "Weather context consistent with...")           |                       |
|                                         |                                 |                       |
|                                         v                                 |                       |
|              [Embedded in M6.2 GeospatialContextResponse & API Surface]   |                       |
|                                         |                                 |                       |
|                                         v                                                         |
|             [Frontend GeospatialContextPanel: Weather & Context Cards]                            |
+---------------------------------------------------------------------------------------------------+
```

### Critical Epistemological Invariant
> **"External environmental correlation does not establish causation."**
> 
> Real-time or recent weather data (such as heavy rainfall) provides **context** regarding environmental conditions around a reported incident. It does **not** prove that a civic defect exists, nor does it establish legal or physical causation (e.g. CVKI never asserts that "rain caused the waterlogging").

---

## 2. Provider Abstraction & Modularity

External data providers adhere to the `ExternalCivicDataProvider` abstract base interface in `backend/app/services/external_civic_provider.py`:

```python
class ExternalCivicDataProvider(ABC):
    @property
    def name(self) -> str: ...
    @property
    def category(self) -> ExternalCategory: ...
    def is_configured(self) -> bool: ...
    def fetch(self, latitude: float, longitude: float, window_hours: int = 24, timestamp: Optional[datetime] = None) -> ProviderFetchResult: ...
```

### Implemented Providers
1. **`OpenMeteoWeatherProvider`:**
   - Free, open-data, non-commercial meteorological endpoint (`https://api.open-meteo.com/v1/forecast`).
   - Retrieves real-time temperature ($^\circ\text{C}$), relative humidity ($\%$), precipitation ($\text{mm}$), wind speed ($\text{m/s}$), WMO weather code, and cumulative hourly precipitation over the specified observation window.
   - Requires zero hardcoded credentials.
2. **`TomTomTrafficProvider`:**
   - Modular adapter for traffic speed, congestion levels, and road incidents.
   - When credentials or endpoint URLs are unset in configuration, it safely reports `ExternalDataStatus.NOT_CONFIGURED` without failing requests.
3. **`OpenDataCivicProvider`:**
   - Extensible adapter for municipal open data portals (e.g., smart city road maintenance feeds).
   - Gracefully reports `ExternalDataStatus.NOT_CONFIGURED` when no municipal endpoint is configured.

---

## 3. Supported Data Categories & Normalization

All external data is mapped into normalized Pydantic schemas in `backend/app/schemas/external_civic.py`:

### Weather Context (`WeatherContext`)
- `temperature_c`: Air temperature at 2m above ground.
- `precipitation_mm`: Current precipitation rate.
- `humidity_percent`: Relative atmospheric humidity.
- `wind_speed_mps`: Wind speed at 10m elevation.
- `condition`: Human-readable condition derived from WMO standard weather codes (e.g., `Clear sky`, `Moderate rain`, `Thunderstorm`).
- `observation_time`: Timestamp of observation.
- `source`: Source provider name.
- `status`: Source status enum.
- `freshness`: Lifecycle freshness state (`live`, `fresh`, `stale`, `unavailable`).

### Rainfall & Waterlogging Context (`RainfallContext`)
- `rainfall_mm`: Total accumulated rainfall within observation window.
- `window_hours`: Observation window duration (default 24h, max 168h).
- `intensity`: Standardized meteorological classification:
  - `none`: $< 0.1\,\text{mm}$
  - `light`: $0.1\,\text{mm} \le r < 10.0\,\text{mm}$
  - `moderate`: $10.0\,\text{mm} \le r < 35.0\,\text{mm}$
  - `heavy`: $35.0\,\text{mm} \le r < 65.0\,\text{mm}$
  - `very_heavy`: $\ge 65.0\,\text{mm}$

### Traffic Context (`TrafficContext`)
- `road_name`: Correlated street name.
- `traffic_condition`: Traffic flow assessment (`free_flow`, `congested`, `blocked`).
- `congestion_level`: Percentage delay indicator.
- `incident_reported`: Boolean flag for reported vehicular incidents.

---

## 4. Two-Tier Caching & Lifecycle States

External civic data caching is managed by `ExternalCivicCache` in `backend/app/services/external_civic_cache.py`:

```
+------------------------------------------------------------------------+
| Cache Key: ext:{provider}:{category}:{lat:.3f}:{lon:.3f}:{window_hours}|
+------------------------------------------------------------------------+
|                                                                        |
|  [Retrieved] ---------------------> [Fresh TTL: 30m]                   |
|     |                                      |                           |
|     +--> Status: "cached_fresh"            +--> Status: "cached_stale" |
|                                                    |                   |
|                                            [Stale TTL: 6h]             |
|                                                    |                   |
|                                                    +--> Evicted / None |
+------------------------------------------------------------------------+
```

### Provider Status State Machine
- `live`: Fetched successfully from live external API within the current request.
- `cached_fresh`: Retrieved from cache within fresh TTL window (default 1,800s / 30m).
- `cached_stale`: Live call timed out or failed; safely serving cached data within stale TTL (default 21,600s / 6h).
- `unavailable`: Live call failed and no stale cache exists.
- `not_configured`: Provider requires unconfigured API credentials or endpoint URL.
- `rate_limited`: Upstream API returned HTTP 429.
- `timeout`: Upstream API failed to respond within `EXTERNAL_DATA_REQUEST_TIMEOUT_SECONDS` (4.0s).
- `error`: Upstream API returned a malformed or invalid response.

---

## 5. Security & SSRF Protection

External request security is enforced before any outbound HTTP connection:
1. **SSRF Filtering (`is_ssrf_safe_external_url`):**
   - Disallows loopback addresses (`127.0.0.1`, `localhost`).
   - Disallows cloud instance metadata services (`169.254.169.254`).
   - Disallows private RFC-1918 networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
   - Disallows link-local and multicast ranges.
   - Enforces standard HTTP (80) and HTTPS (443) ports only.
2. **Credential Secrecy:**
   - Server-side only storage via `app.core.config.settings`.
   - Never exposed in JSON response models, error strings, or frontend assets.
3. **Bounded Timeouts:**
   - Every outbound HTTP call enforces a 4.0-second bounded timeout (`EXTERNAL_DATA_REQUEST_TIMEOUT_SECONDS`).

---

## 6. Environmental Correlation & Civic Intelligence

In `backend/app/services/external_civic_data.py`, `evaluate_environmental_correlation` combines issue categories with environmental readings:

### `road_waterlogging` Correlation Logic
- **When Rainfall $\ge 1.0\,\text{mm}$ in preceding 24h:**
  > `"Weather context consistent with recent rainfall: 22.4 mm recorded in the preceding 24h window (intensity: moderate)."`
- **When Rainfall $< 1.0\,\text{mm}$:**
  > `"Low or negligible precipitation (0.2 mm in 24h) observed; waterlogging may indicate internal drainage blockage or standing surface runoff."`
- **When Weather Provider is Unavailable:**
  > `"Environmental precipitation data is currently unavailable for correlation."`
- **Mandatory Causal Disclaimer:**
  > `"External environmental correlation is contextual and does not establish that rainfall caused the reported civic defect."`

---

## 7. M6.2 & M5.2 Integration

- **M6.2 Integration:** `GeospatialContextResponse` includes an `external_context: Optional[ExternalCivicContextResponse]` field. Whenever `/api/v1/geospatial/context` or `/api/v1/geospatial/cases/{ref}/context` is evaluated, environmental context is seamlessly populated.
- **Dedicated Endpoint:** Added `GET /api/v1/geospatial/external-context` for targeted queries.
- **M5.2 Isolation:** M5.2 recurrence and hotspot algorithms remain 100% frozen and unmodified. Environmental data is displayed strictly as contextual accompaniment.

---

## 8. Frontend UI Integration

The `GeospatialContextPanel.jsx` component includes an **"Environmental & External Context"** section:
- Compact visual metrics:
  - 🌧 **Rainfall:** 24h precipitation with intensity badges (`NONE`, `LIGHT`, `MODERATE`, `HEAVY`, `VERY_HEAVY`).
  - 🌡 **Temperature:** Recorded ambient temperature in $^\circ\text{C}$.
  - 💨 **Wind Speed:** Measured wind velocity in $\text{m/s}$.
  - ☁ **Weather Condition:** Clear condition text.
  - 🚗 **Traffic Condition:** Road flow indicator when configured.
- **Provenance & Disclaimers:** Displays provider name, freshness state badge, and non-causal disclaimer.

---

## 9. Test Matrix & Validation Results

The M6.3 test suite in `backend/tests/test_external_civic_data_m63.py` validates all 24 required scenarios (A through X):

| Scenario | Category | Expected Behavior | Status |
|---|---|---|---|
| A | Provider Abstraction | Validates interface compliance and unconfigured states | PASSED |
| B | Configured Provider Success | Successfully normalizes live weather and rainfall data | PASSED |
| C | Provider Unavailable | Gracefully degrades without 500 errors | PASSED |
| D | Timeout Handling | Catches connection timeouts and flags TIMEOUT status | PASSED |
| E | Rate Limiting | Handles HTTP 429 and flags RATE_LIMITED status | PASSED |
| F | Malformed Response | Safely handles corrupt JSON and flags ERROR status | PASSED |
| G | Cache Fresh | Returns fresh cached entry without upstream request | PASSED |
| H | Cache Stale | Returns stale cache entry on live failure | PASSED |
| I | No Cache | Returns unavailable when live fails and no cache exists | PASSED |
| J | Weather Normalization | Correctly maps temp, humidity, wind, and WMO conditions | PASSED |
| K | Rainfall Intensity | Normalizes intensity across 5 meteorological tiers | PASSED |
| L | Missing Optional Fields | Null/missing fields parse safely without schema failure | PASSED |
| M | Timestamp Handling | Observation, retrieval, and window hours preserved | PASSED |
| N | Coordinate Validation | Rejects invalid coordinates with 422 Unprocessable | PASSED |
| O | Time-Window Bounding | Clamps observation windows to configured bounds | PASSED |
| P | Radius & Query Limits | Rejects out-of-bounds parameters | PASSED |
| Q | SSRF Security | Rejects loopback, private IP, and cloud metadata targets | PASSED |
| R | API Key Secrecy | Ensures no credentials appear in serialized responses | PASSED |
| S | M6.2 Integration | Verifies external_context in GeospatialContextResponse | PASSED |
| T | Waterlogging Correlation | Produces consistent contextual rainfall summary | PASSED |
| U | Non-Causal Enforcement | Verifies no causal assertions ("caused by rain") | PASSED |
| V | M5.2 Regression | Validates recurrence intelligence remains untouched | PASSED |
| W | RBAC & Privacy | Enforces authority assignment and citizen privacy | PASSED |
| X | Case Context Endpoint | Case detail endpoint returns external civic context | PASSED |

### Regression Suite Results
- `tests/test_external_civic_data_m63.py`: **24 passed** in 7.15s.
- `tests/test_geospatial_intelligence_m62.py` + `tests/test_live_authority_m61.py`: **42 passed** in 8.39s.
- Full pytest test suite across entire backend: **463 passed** in 172.94s (100% pass rate).
- Frontend lint (`npm run lint`): **0 errors**.
- Frontend production bundle (`npm run build`): **Built successfully in 2.15s**.
- YOLOv8 model hash: **Identical (`602160D4851E0D79...`)**.
- AI & dataset trees: **0 files modified in `ai/` or `dataset/`**.

---

## 10. Representative Performance Baseline

Measured on representative local test workloads:
- **Live External Context Query (Open-Meteo):** $\sim 1550\,\text{ms}$ (includes live HTTPS roundtrip).
- **Cached External Context Query:** $0.07\,\text{ms}$ (sub-millisecond in-memory cache hit).
- **Combined Geospatial + External Context:** $\sim 518\,\text{ms}$ (parallelized spatial analysis with cached environmental data).
