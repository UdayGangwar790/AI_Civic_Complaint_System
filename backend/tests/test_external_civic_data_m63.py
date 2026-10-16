import asyncio
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseAssignment,
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.schemas.external_civic import (
    EnvironmentalCorrelation,
    ExternalCategory,
    ExternalCivicContextResponse,
    ExternalDataStatus,
    RainfallContext,
    TrafficContext,
    WeatherContext,
)
from app.services.authority import resolve_authority_for_location
import app.services.complaint_case as complaint_case_module
from app.services.external_civic_cache import (
    ExternalCivicCacheEntry,
    InMemoryExternalCivicCache,
    build_external_civic_cache_key,
)
from app.services.external_civic_data import (
    ExternalCivicDataService,
    external_civic_service,
)
from app.services.external_civic_provider import (
    ExternalCivicDataProvider,
    OpenDataCivicProvider,
    OpenMeteoWeatherProvider,
    ProviderFetchResult,
    TomTomTrafficProvider,
    classify_rainfall_intensity,
    is_ssrf_safe_external_url,
)
from app.services.spatial import CoordinateValidationError, validate_coordinates


def _build_test_case(
    ref_id: str,
    lat: float = 12.9716,
    lon: float = 77.5946,
    issue_class: str = "road_waterlogging",
    road: str = "MG Road",
    assigned_to: str | None = None,
    created_at: datetime | None = None,
) -> ComplaintCase:
    now = created_at or datetime.now(timezone.utc)
    complaint_loc = ComplaintLocation(
        road=road,
        area="Central Area",
        city="Bengaluru",
        district="Bengaluru Urban",
        state="Karnataka",
        latitude=lat,
        longitude=lon,
    )
    auth = resolve_authority_for_location(complaint_loc)
    return ComplaintCase(
        reference_id=ref_id,
        user_id="usr_citizen_123",
        status="submitted_to_cvki",
        created_at=now,
        issue=CaseIssue(class_name=issue_class, label=issue_class.replace("_", " ").title(), severity="medium", confidence=0.88),
        location=complaint_loc,
        authority=auth,
        complaint=CaseComplaint(language="en", title=f"Report {ref_id}", description="Observed civic issue on road corridor."),
        follow_up=FollowUp(guidance="Reported via CVKI portal."),
        assignment=CaseAssignment(assigned_to_user_id=assigned_to, assignment_status="assigned" if assigned_to else "unassigned"),
    )


class TestExternalCivicDataM63(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def setUp(self):
        self.cache = InMemoryExternalCivicCache()
        self.mock_provider = MagicMock(spec=ExternalCivicDataProvider)
        self.mock_provider.name = "Mock Weather Provider"
        self.mock_provider.category = ExternalCategory.WEATHER
        self.mock_provider.is_configured.return_value = True
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.LIVE,
            data={"temperature_c": 26.0, "window_rainfall_mm": 5.0, "condition": "Cloudy"},
            source="Mock Weather Provider",
            source_type="open_weather_api",
            observation_time=datetime.now(timezone.utc),
        )

        self.service = ExternalCivicDataService(
            cache=self.cache,
            weather_provider=self.mock_provider,
        )

        self.repo = complaint_case_module.InMemoryComplaintCaseRepository()
        self.orig_repo = complaint_case_module.case_repository
        complaint_case_module.case_repository = self.repo
        app.dependency_overrides.clear()

    def tearDown(self):
        complaint_case_module.case_repository = self.orig_repo
        app.dependency_overrides.clear()

    # -------------------------------------------------------------------------
    # A. Provider Abstraction & Interface Compliance
    # -------------------------------------------------------------------------
    def test_a_provider_abstraction(self):
        provider = OpenMeteoWeatherProvider()
        self.assertEqual(provider.name, "Open-Meteo Forecast")
        self.assertEqual(provider.category, ExternalCategory.WEATHER)
        self.assertTrue(provider.is_configured())

        traffic_provider = TomTomTrafficProvider(endpoint_url=None, api_key=None)
        self.assertFalse(traffic_provider.is_configured())
        unconf_res = traffic_provider.fetch(12.9716, 77.5946)
        self.assertEqual(unconf_res.status, ExternalDataStatus.NOT_CONFIGURED)

        open_civic = OpenDataCivicProvider(endpoint_url=None)
        self.assertFalse(open_civic.is_configured())

    # -------------------------------------------------------------------------
    # B. Configured Provider Success
    # -------------------------------------------------------------------------
    def test_b_configured_provider_success(self):
        now = datetime.now(timezone.utc)
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.LIVE,
            data={
                "temperature_c": 28.4,
                "precipitation_mm": 12.5,
                "humidity_percent": 82,
                "wind_speed_mps": 4.1,
                "weather_code": 65,
                "condition": "Heavy rain",
                "window_rainfall_mm": 18.2,
                "window_hours": 24,
            },
            source="Mock Weather Provider",
            source_type="open_weather_api",
            observation_time=now,
        )

        weather, rainfall = self.service.get_weather_and_rainfall(12.9716, 77.5946, window_hours=24)
        self.assertEqual(weather.status, ExternalDataStatus.LIVE)
        self.assertEqual(weather.temperature_c, 28.4)
        self.assertEqual(weather.condition, "Heavy rain")
        self.assertEqual(rainfall.rainfall_mm, 18.2)
        self.assertEqual(rainfall.intensity, "moderate")
        self.assertEqual(weather.freshness, "live")

    # -------------------------------------------------------------------------
    # C. Provider Unavailable (Graceful Fallback, No Crash)
    # -------------------------------------------------------------------------
    def test_c_provider_unavailable(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.UNAVAILABLE,
            data={},
            source="Mock Weather Provider",
            source_type="open_weather_api",
            error_message="Remote weather server 503 unavailable.",
        )

        weather, rainfall = self.service.get_weather_and_rainfall(12.9716, 77.5946)
        self.assertEqual(weather.status, ExternalDataStatus.UNAVAILABLE)
        self.assertIsNone(weather.temperature_c)
        self.assertEqual(rainfall.status, ExternalDataStatus.UNAVAILABLE)

        # Full context endpoint must not 500
        res = self.client.get("/api/v1/geospatial/external-context?latitude=12.9716&longitude=77.5946")
        self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------------------
    # D. Timeout Handling
    # -------------------------------------------------------------------------
    def test_d_timeout_handling(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.TIMEOUT,
            data={},
            source="Mock Weather Provider",
            source_type="open_weather_api",
            error_message="Connection timed out after 4.0s.",
        )

        weather, rainfall = self.service.get_weather_and_rainfall(12.9716, 77.5946)
        self.assertEqual(weather.status, ExternalDataStatus.TIMEOUT)
        self.assertEqual(rainfall.status, ExternalDataStatus.TIMEOUT)

    # -------------------------------------------------------------------------
    # E. Rate Limiting Handling (429)
    # -------------------------------------------------------------------------
    def test_e_rate_limiting_handling(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.RATE_LIMITED,
            data={},
            source="Mock Weather Provider",
            source_type="open_weather_api",
            error_message="HTTP 429 rate limit exceeded.",
        )

        weather, rainfall = self.service.get_weather_and_rainfall(12.9716, 77.5946)
        self.assertEqual(weather.status, ExternalDataStatus.RATE_LIMITED)

    # -------------------------------------------------------------------------
    # F. Malformed Provider Response Handled Safely
    # -------------------------------------------------------------------------
    def test_f_malformed_provider_response(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.ERROR,
            data={},
            source="Mock Weather Provider",
            source_type="open_weather_api",
            error_message="Malformed JSON payload received from provider.",
        )

        weather, rainfall = self.service.get_weather_and_rainfall(12.9716, 77.5946)
        self.assertEqual(weather.status, ExternalDataStatus.ERROR)

    # -------------------------------------------------------------------------
    # G. Cache Fresh
    # -------------------------------------------------------------------------
    def test_g_cache_fresh(self):
        lat, lon = 12.9716, 77.5946
        cache_key = build_external_civic_cache_key(
            provider=self.mock_provider.name,
            category="weather_rainfall",
            latitude=lat,
            longitude=lon,
            window_hours=24,
        )
        self.cache.set(
            cache_key=cache_key,
            provider=self.mock_provider.name,
            category="weather_rainfall",
            query_lat=lat,
            query_lon=lon,
            window_hours=24,
            data={
                "temperature_c": 22.0,
                "window_rainfall_mm": 5.5,
                "condition": "Partly cloudy",
            },
            source="Mock Weather Provider",
            status="live",
            fresh_ttl_seconds=1800,
        )

        weather, rainfall = self.service.get_weather_and_rainfall(lat, lon, window_hours=24)
        self.assertEqual(weather.status, ExternalDataStatus.CACHED_FRESH)
        self.assertEqual(weather.temperature_c, 22.0)
        self.assertEqual(weather.freshness, "fresh")
        # Provider fetch must NOT be called when fresh cache hit occurs
        self.mock_provider.fetch.assert_not_called()

    # -------------------------------------------------------------------------
    # H. Cache Stale (Live Fails, Stale Entry Returned)
    # -------------------------------------------------------------------------
    def test_h_cache_stale(self):
        lat, lon = 12.9716, 77.5946
        cache_key = build_external_civic_cache_key(
            provider=self.mock_provider.name,
            category="weather_rainfall",
            latitude=lat,
            longitude=lon,
            window_hours=24,
        )
        now = datetime.now(timezone.utc)
        # Entry whose fresh TTL expired 10 minutes ago, but within 6-hour stale TTL
        entry = ExternalCivicCacheEntry(
            cache_key=cache_key,
            provider=self.mock_provider.name,
            category="weather_rainfall",
            query_lat=lat,
            query_lon=lon,
            window_hours=24,
            data={"temperature_c": 19.5, "window_rainfall_mm": 0.0, "condition": "Overcast"},
            source="Mock Weather Provider",
            status="live",
            retrieved_at=now - timedelta(hours=1),
            expires_at=now - timedelta(minutes=10),
            stale_expires_at=now + timedelta(hours=3),
        )
        self.cache._entries[cache_key] = entry

        # Live provider fails
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.UNAVAILABLE,
            data={},
            source="Mock Weather Provider",
            source_type="open_weather_api",
        )

        weather, rainfall = self.service.get_weather_and_rainfall(lat, lon, window_hours=24)
        self.assertEqual(weather.status, ExternalDataStatus.CACHED_STALE)
        self.assertEqual(weather.temperature_c, 19.5)
        self.assertEqual(weather.freshness, "stale")

    # -------------------------------------------------------------------------
    # I. No Cache (Live Fails and No Cache Exists)
    # -------------------------------------------------------------------------
    def test_i_no_cache(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.UNAVAILABLE,
            data={},
            source="Mock Weather Provider",
            source_type="open_weather_api",
        )

        weather, rainfall = self.service.get_weather_and_rainfall(12.9716, 77.5946)
        self.assertEqual(weather.status, ExternalDataStatus.UNAVAILABLE)
        self.assertEqual(weather.freshness, "unavailable")

    # -------------------------------------------------------------------------
    # J. Weather Normalization
    # -------------------------------------------------------------------------
    def test_j_weather_normalization(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.LIVE,
            data={
                "temperature_c": 31.2,
                "precipitation_mm": 0.0,
                "humidity_percent": 65,
                "wind_speed_mps": 3.8,
                "weather_code": 0,
                "condition": "Clear sky",
                "window_rainfall_mm": 0.0,
            },
            source="Open-Meteo",
            source_type="open_weather_api",
        )

        weather, _ = self.service.get_weather_and_rainfall(12.9716, 77.5946)
        self.assertEqual(weather.temperature_c, 31.2)
        self.assertEqual(weather.humidity_percent, 65)
        self.assertEqual(weather.wind_speed_mps, 3.8)
        self.assertEqual(weather.condition, "Clear sky")

    # -------------------------------------------------------------------------
    # K. Rainfall Intensity Normalization
    # -------------------------------------------------------------------------
    def test_k_rainfall_intensity_normalization(self):
        self.assertEqual(classify_rainfall_intensity(0.0), "none")
        self.assertEqual(classify_rainfall_intensity(0.05), "none")
        self.assertEqual(classify_rainfall_intensity(0.5), "light")
        self.assertEqual(classify_rainfall_intensity(15.0), "moderate")
        self.assertEqual(classify_rainfall_intensity(45.0), "heavy")
        self.assertEqual(classify_rainfall_intensity(80.0), "very_heavy")

    # -------------------------------------------------------------------------
    # L. Missing Optional Fields Handled Gracefully
    # -------------------------------------------------------------------------
    def test_l_missing_optional_fields(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.LIVE,
            data={
                "temperature_c": None,
                "precipitation_mm": None,
                "wind_speed_mps": None,
                "condition": None,
                "window_rainfall_mm": None,
            },
            source="Mock Weather Provider",
            source_type="open_weather_api",
        )

        weather, rainfall = self.service.get_weather_and_rainfall(12.9716, 77.5946)
        self.assertEqual(weather.status, ExternalDataStatus.LIVE)
        self.assertIsNone(weather.temperature_c)
        self.assertIsNone(rainfall.rainfall_mm)
        self.assertEqual(rainfall.intensity, "none")

    # -------------------------------------------------------------------------
    # M. Timestamp Handling
    # -------------------------------------------------------------------------
    def test_m_timestamp_handling(self):
        now = datetime.now(timezone.utc)
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.LIVE,
            data={"temperature_c": 25.0, "window_rainfall_mm": 2.0},
            source="Mock Weather Provider",
            source_type="open_weather_api",
            observation_time=now,
        )

        weather, rainfall = self.service.get_weather_and_rainfall(12.9716, 77.5946, window_hours=48, timestamp=now)
        self.assertEqual(weather.observation_time, now)
        self.assertEqual(rainfall.window_hours, 48)

    # -------------------------------------------------------------------------
    # N. Coordinate Validation
    # -------------------------------------------------------------------------
    def test_n_coordinate_validation(self):
        with self.assertRaises(CoordinateValidationError):
            self.service.get_external_civic_context(latitude=95.0, longitude=77.0)

        with self.assertRaises(CoordinateValidationError):
            self.service.get_external_civic_context(latitude=12.0, longitude=185.0)

        res = self.client.get("/api/v1/geospatial/external-context?latitude=95.0&longitude=77.0")
        self.assertEqual(res.status_code, 422)

    # -------------------------------------------------------------------------
    # O. Time-Window Validation & Bounding
    # -------------------------------------------------------------------------
    def test_o_time_window_validation(self):
        # Negative / 0 window is bounded to min 1
        ctx = self.service.get_external_civic_context(12.9716, 77.5946, window_hours=-5)
        self.assertEqual(ctx.rainfall.window_hours, 1)

        # Window exceeding 168 hours is bounded to 168
        ctx2 = self.service.get_external_civic_context(12.9716, 77.5946, window_hours=500)
        self.assertEqual(ctx2.rainfall.window_hours, 168)

    # -------------------------------------------------------------------------
    # P. Radius & Query Limits
    # -------------------------------------------------------------------------
    def test_p_radius_query_limits(self):
        res = self.client.get("/api/v1/geospatial/external-context?latitude=12.0&longitude=77.0&window_hours=200")
        self.assertEqual(res.status_code, 422)

    # -------------------------------------------------------------------------
    # Q. SSRF Protection on External Provider URLs
    # -------------------------------------------------------------------------
    def test_q_ssrf_protection(self):
        safe_url, _ = is_ssrf_safe_external_url("https://api.open-meteo.com/v1/forecast")
        self.assertTrue(safe_url)

        # Disallow loopback
        loopback, _ = is_ssrf_safe_external_url("http://127.0.0.1:8080/weather")
        self.assertFalse(loopback)

        # Disallow cloud metadata (169.254.169.254)
        metadata, _ = is_ssrf_safe_external_url("http://169.254.169.254/latest/meta-data")
        self.assertFalse(metadata)

        # Disallow private IPs
        private_ip, _ = is_ssrf_safe_external_url("http://192.168.1.50/data")
        self.assertFalse(private_ip)

        # Disallow non-HTTP
        file_scheme, _ = is_ssrf_safe_external_url("file:///etc/passwd")
        self.assertFalse(file_scheme)

    # -------------------------------------------------------------------------
    # R. API Key Secrecy (Never Expose Secrets in Returns)
    # -------------------------------------------------------------------------
    def test_r_api_key_secrecy(self):
        res = self.client.get("/api/v1/geospatial/external-context?latitude=12.9716&longitude=77.5946")
        self.assertEqual(res.status_code, 200)
        content = res.text.lower()
        self.assertNotIn("api_key", content)
        self.assertNotIn("secret", content)
        self.assertNotIn("password", content)

    # -------------------------------------------------------------------------
    # S. M6.2 Integration (GeospatialContextResponse includes external_context)
    # -------------------------------------------------------------------------
    def test_s_m62_integration(self):
        res = self.client.post(
            "/api/v1/geospatial/context",
            json={
                "latitude": 12.9716,
                "longitude": 77.5946,
                "issue_category": "road_waterlogging",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("external_context", data)
        self.assertIn("weather", data["external_context"])
        self.assertIn("rainfall", data["external_context"])

    # -------------------------------------------------------------------------
    # T. Waterlogging Environmental Context
    # -------------------------------------------------------------------------
    def test_t_waterlogging_environmental_context(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.LIVE,
            data={
                "temperature_c": 24.0,
                "window_rainfall_mm": 22.4,
                "condition": "Rain showers",
            },
            source="Mock Weather Provider",
            source_type="open_weather_api",
        )

        ctx = self.service.get_external_civic_context(
            latitude=12.9716,
            longitude=77.5946,
            issue_category="road_waterlogging",
        )
        corr = ctx.environmental_correlation
        self.assertIsNotNone(corr)
        self.assertTrue(corr.correlation_observed)
        self.assertIn("consistent with recent rainfall", corr.correlation_summary)
        self.assertIn("22.4 mm", corr.correlation_summary)

    # -------------------------------------------------------------------------
    # U. No Causal Claim Generation (Strict Invariant)
    # -------------------------------------------------------------------------
    def test_u_no_causal_claim_generation(self):
        self.mock_provider.fetch.return_value = ProviderFetchResult(
            status=ExternalDataStatus.LIVE,
            data={"temperature_c": 24.0, "window_rainfall_mm": 50.0},
            source="Mock Weather Provider",
            source_type="open_weather_api",
        )

        ctx = self.service.get_external_civic_context(
            latitude=12.9716,
            longitude=77.5946,
            issue_category="road_waterlogging",
        )
        corr = ctx.environmental_correlation
        summary_lower = corr.correlation_summary.lower()
        self.assertNotIn("caused the waterlogging", summary_lower)
        self.assertNotIn("due to rain", summary_lower)
        self.assertNotIn("rain resulted in", summary_lower)
        self.assertIn("consistent with", summary_lower)
        self.assertIn("does not establish that rainfall caused", corr.causal_disclaimer.lower())

    # -------------------------------------------------------------------------
    # V. M5.2 Regression (Civic Intelligence Untouched)
    # -------------------------------------------------------------------------
    def test_v_m52_regression(self):
        now = datetime.now(timezone.utc)
        c1 = _build_test_case("CVKI-20261014-M5A", created_at=now - timedelta(days=5))
        c2 = _build_test_case("CVKI-20261014-M5B", created_at=now)
        self.repo.save(c1)
        self.repo.save(c2)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_admin",
            email="admin@example.com",
            role=UserRole.ADMIN.value,
        )

        res = self.client.get(f"/api/v1/admin/cases/{c2.reference_id}/intelligence")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["recurrence"]["recurrence_detected"])

    # -------------------------------------------------------------------------
    # W. RBAC & Privacy Protection
    # -------------------------------------------------------------------------
    def test_w_rbac_and_privacy(self):
        case = _build_test_case("CVKI-20261014-PRIV", assigned_to="usr_assigned_auth")
        self.repo.save(case)

        # Unassigned authority gets 403
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_other_auth",
            email="other@example.com",
            role=UserRole.AUTHORITY.value,
        )
        res = self.client.get(f"/api/v1/geospatial/cases/{case.reference_id}/context")
        self.assertEqual(res.status_code, 403)

    # -------------------------------------------------------------------------
    # X. Case Geospatial Context Integration
    # -------------------------------------------------------------------------
    def test_x_case_geospatial_context_integration(self):
        case = _build_test_case("CVKI-20261014-EXT", assigned_to="usr_assigned_auth")
        self.repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_assigned_auth",
            email="assigned@example.com",
            role=UserRole.AUTHORITY.value,
        )
        res = self.client.get(f"/api/v1/geospatial/cases/{case.reference_id}/context")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("external_context", data)
        self.assertIsNotNone(data["external_context"])


if __name__ == "__main__":
    unittest.main()
