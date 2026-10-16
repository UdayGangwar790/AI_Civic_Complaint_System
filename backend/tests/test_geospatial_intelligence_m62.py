import asyncio
from datetime import datetime, timedelta, timezone
import math
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.authority import AuthorityParty, AuthorityResult, OfficialSourceRecord
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseAssignment,
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.schemas.geospatial import (
    GeoSourceStatus,
    LocationMatchQuality,
    RoadType,
    SpatialRelationship,
)
import app.services.complaint_case as complaint_case_module
from app.services.complaint_case import (
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
from app.services.geo_cache import (
    GeoCacheEntry,
    InMemoryGeoCache,
    build_geo_cache_key,
    get_geo_cache,
    set_geo_cache,
)
from app.services.geocoding_provider import (
    GeocodingError,
    GeocodingTimeout,
    RawGeocodingResponse,
    ResilientGeocodingService,
    evaluate_location_match_quality,
    extract_road_type_and_ref,
    geocoding_service,
)
from app.services.geospatial_intelligence import (
    classify_spatial_relationships,
    find_nearby_cases,
    get_case_geospatial_context,
    get_geospatial_intelligence_context,
)
from app.services.spatial import (
    CoordinateValidationError,
    bounding_box_for_radius,
    calculate_bearing_degrees,
    from_geojson_point,
    haversine_distance_km,
    haversine_distance_meters,
    to_geojson_point,
    validate_accuracy,
    validate_coordinates,
)


def _build_test_case(
    ref_id: str,
    lat: float = 12.9716,
    lon: float = 77.5946,
    issue_class: str = "open_damaged_manhole",
    status: str = "submitted_to_cvki",
    road: str = "MG Road",
    city: str = "Bengaluru",
    created_at: datetime = None,
    assigned_to: str = None,
) -> ComplaintCase:
    now = created_at or datetime.now(timezone.utc)
    return ComplaintCase(
        reference_id=ref_id,
        user_id="usr_citizen_456",
        status=status,
        created_at=now,
        updated_at=now,
        issue=CaseIssue(
            class_name=issue_class,
            label=issue_class.replace("_", " ").title(),
            severity="high",
            confidence=0.92,
        ),
        location=ComplaintLocation(
            road=road,
            area="Central",
            city=city,
            district="Bengaluru Urban",
            state="Karnataka",
            latitude=lat,
            longitude=lon,
            accuracy_m=10.0,
        ),
        authority=AuthorityResult(
            road_owner=AuthorityParty(
                name="Bruhat Bengaluru Mahanagara Palike",
                level="municipal_corporation",
                jurisdiction="Bengaluru",
                verified=True,
            ),
            authority_status="verified",
            sources=[
                OfficialSourceRecord(
                    source_id="src_bbmp_01",
                    source_name="BBMP Official Road Register",
                    url="https://bbmp.gov.in/roads",
                    source_type="official_government_page",
                    retrieved_at=now,
                )
            ],
            resolved_at=now,
        ),
        complaint=CaseComplaint(
            language="en",
            title=f"Issue on {road}",
            description="Hazardous situation observed on the roadway.",
        ),
        follow_up=FollowUp(guidance="Follow up with BBMP"),
        assignment=CaseAssignment(
            assigned_to_user_id=assigned_to,
            assignment_status="assigned" if assigned_to else "unassigned",
        ) if assigned_to else None,
    )


class TestGeospatialIntelligenceM62(unittest.TestCase):
    def setUp(self):
        self.original_repository = complaint_case_module.case_repository
        self.repo = InMemoryComplaintCaseRepository()
        set_case_repository(self.repo)

        self.cache = InMemoryGeoCache()
        self.orig_cache = get_geo_cache()
        set_geo_cache(self.cache)

        self.original_overrides = dict(app.dependency_overrides)
        self.client_cm = TestClient(app)
        self.client = self.client_cm.__enter__()

    def tearDown(self):
        self.client_cm.__exit__(None, None, None)
        app.dependency_overrides = self.original_overrides
        set_case_repository(self.original_repository)
        set_geo_cache(self.orig_cache)

    # -------------------------------------------------------------------------
    # A. Valid Coordinate Normalization
    # -------------------------------------------------------------------------
    def test_a_valid_coordinate_normalization(self):
        lat, lon = validate_coordinates(12.9716, 77.5946)
        self.assertEqual(lat, 12.9716)
        self.assertEqual(lon, 77.5946)

        # Boundary checks
        lat_n, lon_e = validate_coordinates(90.0, 180.0)
        self.assertEqual(lat_n, 90.0)
        self.assertEqual(lon_e, 180.0)

        lat_s, lon_w = validate_coordinates(-90.0, -180.0)
        self.assertEqual(lat_s, -90.0)
        self.assertEqual(lon_w, -180.0)

    # -------------------------------------------------------------------------
    # B. Invalid Latitude Rejected
    # -------------------------------------------------------------------------
    def test_b_invalid_latitude_rejected(self):
        with self.assertRaises(CoordinateValidationError):
            validate_coordinates(91.0, 77.0)

        with self.assertRaises(CoordinateValidationError):
            validate_coordinates(-90.5, 77.0)

        res = self.client.get("/api/v1/geospatial/cases/nearby?latitude=95.0&longitude=77.0")
        self.assertEqual(res.status_code, 422)

    # -------------------------------------------------------------------------
    # C. Invalid Longitude Rejected
    # -------------------------------------------------------------------------
    def test_c_invalid_longitude_rejected(self):
        with self.assertRaises(CoordinateValidationError):
            validate_coordinates(12.0, 181.0)

        with self.assertRaises(CoordinateValidationError):
            validate_coordinates(12.0, -185.0)

        res = self.client.get("/api/v1/geospatial/cases/nearby?latitude=12.0&longitude=185.0")
        self.assertEqual(res.status_code, 422)

    # -------------------------------------------------------------------------
    # D. Missing / Null Coordinates Rejected
    # -------------------------------------------------------------------------
    def test_d_missing_coordinates_rejected(self):
        with self.assertRaises(CoordinateValidationError):
            validate_coordinates(None, 77.0)

        with self.assertRaises(CoordinateValidationError):
            validate_coordinates(12.0, None)

        with self.assertRaises(CoordinateValidationError):
            validate_coordinates(0.0, 0.0, allow_null_island=False)

        res = self.client.post("/api/v1/geospatial/context", json={})
        self.assertEqual(res.status_code, 422)

    # -------------------------------------------------------------------------
    # E. GPS Accuracy Handling
    # -------------------------------------------------------------------------
    def test_e_gps_accuracy_handling(self):
        self.assertIsNone(validate_accuracy(None))
        self.assertEqual(validate_accuracy(15.5), 15.5)

        with self.assertRaises(CoordinateValidationError):
            validate_accuracy(-5.0)

        with self.assertRaises(CoordinateValidationError):
            validate_accuracy("invalid_acc")

        quality_high = evaluate_location_match_quality(has_road=True, accuracy_m=10.0)
        self.assertEqual(quality_high, LocationMatchQuality.STRONG)

        quality_mod = evaluate_location_match_quality(has_road=True, accuracy_m=55.0)
        self.assertEqual(quality_mod, LocationMatchQuality.APPROXIMATE)

        quality_low = evaluate_location_match_quality(has_road=True, accuracy_m=180.0)
        self.assertEqual(quality_low, LocationMatchQuality.APPROXIMATE)

        quality_none = evaluate_location_match_quality(has_road=False, accuracy_m=5.0)
        self.assertEqual(quality_none, LocationMatchQuality.UNAVAILABLE)

    # -------------------------------------------------------------------------
    # F. Haversine Distance (Known Coordinate Pairs)
    # -------------------------------------------------------------------------
    def test_f_haversine_distance_known_pairs(self):
        dist_zero = haversine_distance_meters(12.9716, 77.5946, 12.9716, 77.5946)
        self.assertAlmostEqual(dist_zero, 0.0, places=3)

        # Pair 1: Bengaluru Vidhana Soudha to MG Road Metro (~1.78 km)
        dist_blr = haversine_distance_km(12.9797, 77.5907, 12.9756, 77.6066)
        self.assertTrue(1.7 <= dist_blr <= 1.9, f"Expected ~1.78km, got {dist_blr:.3f}km")

        # Pair 2: New Delhi India Gate to Connaught Place Central (~2.41 km)
        dist_del = haversine_distance_km(28.6129, 77.2295, 28.6315, 77.2167)
        self.assertTrue(2.3 <= dist_del <= 2.5, f"Expected ~2.41km, got {dist_del:.3f}km")

    # -------------------------------------------------------------------------
    # G. Road Match Exact
    # -------------------------------------------------------------------------
    def test_g_road_match_exact(self):
        quality = evaluate_location_match_quality(has_road=True, accuracy_m=5.0, is_official_segment=True)
        self.assertEqual(quality, LocationMatchQuality.EXACT)

        rtype, ref = extract_road_type_and_ref(
            road_name="National Highway 44",
            osm_class="highway",
            osm_type="trunk",
            raw_address={"ref": "NH 44"},
        )
        self.assertEqual(rtype, RoadType.NATIONAL_HIGHWAY)
        self.assertEqual(ref, "NH-44")

    # -------------------------------------------------------------------------
    # H. Road Match Approximate
    # -------------------------------------------------------------------------
    def test_h_road_match_approximate(self):
        quality = evaluate_location_match_quality(has_road=True, accuracy_m=45.0, is_official_segment=False)
        self.assertEqual(quality, LocationMatchQuality.APPROXIMATE)

        rtype, ref = extract_road_type_and_ref(
            road_name="5th Cross Road",
            osm_class="place",
            osm_type=None,
        )
        self.assertEqual(rtype, RoadType.UNKNOWN)
        self.assertIsNone(ref)

    # -------------------------------------------------------------------------
    # I. Geocoder Unavailable (Safe Fallback, No Hallucinated Addresses)
    # -------------------------------------------------------------------------
    def test_i_geocoder_unavailable(self):
        mock_provider = MagicMock()
        mock_provider.reverse_geocode.side_effect = GeocodingTimeout("Timeout")

        service = ResilientGeocodingService(provider=mock_provider)
        norm_loc, road_id, segment, status = service.resolve(12.9716, 77.5946)

        self.assertEqual(status, GeoSourceStatus.UNAVAILABLE)
        self.assertEqual(norm_loc.match_quality, LocationMatchQuality.UNAVAILABLE)
        self.assertIsNone(norm_loc.formatted_address)
        self.assertIsNone(road_id.road_name)
        self.assertEqual(road_id.road_type, RoadType.UNKNOWN)
        self.assertEqual(norm_loc.geocoding_source, "unavailable")

    # -------------------------------------------------------------------------
    # J. Cached Geocoder Result
    # -------------------------------------------------------------------------
    def test_j_cached_geocoder_result(self):
        lat, lon = 12.9716, 77.5946
        cache_key = build_geo_cache_key(lat, lon)
        self.cache.set(
            cache_key=cache_key,
            provider="OpenStreetMap Nominatim",
            data={
                "display_name": "MG Road, Bengaluru, Karnataka",
                "road": "MG Road",
                "city": "Bengaluru",
                "state": "Karnataka",
                "osm_type": "primary",
                "osm_class": "highway",
            },
            match_quality="strong",
            ttl_seconds=3600,
        )

        mock_provider = MagicMock()
        mock_provider.reverse_geocode.side_effect = GeocodingError("Provider down")

        service = ResilientGeocodingService(provider=mock_provider)
        norm_loc, road_id, segment, status = service.resolve(lat, lon)

        self.assertEqual(status, GeoSourceStatus.CACHED)
        self.assertEqual(norm_loc.road, "MG Road")
        self.assertEqual(norm_loc.city, "Bengaluru")
        self.assertIn("cached", norm_loc.geocoding_source)

    # -------------------------------------------------------------------------
    # K. Stale Geocoder Result (Expiration Check)
    # -------------------------------------------------------------------------
    def test_k_stale_geocoder_result(self):
        entry = GeoCacheEntry(
            cache_key="test_key",
            provider="Nominatim",
            retrieved_at=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            data={"road": "Old Stale Road"},
            match_quality="approximate",
        )
        self.assertTrue(entry.is_expired())

        fresh_entry = GeoCacheEntry(
            cache_key="fresh_key",
            provider="Nominatim",
            retrieved_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            data={"road": "Fresh Road"},
            match_quality="strong",
        )
        self.assertFalse(fresh_entry.is_expired())

    # -------------------------------------------------------------------------
    # L. Nearby Case Search
    # -------------------------------------------------------------------------
    def test_l_nearby_case_search(self):
        base_lat, base_lon = 12.9716, 77.5946
        c1 = _build_test_case("CVKI-20261014-001", lat=base_lat, lon=base_lon)
        c2 = _build_test_case("CVKI-20261014-002", lat=base_lat + 0.0009, lon=base_lon)
        c3 = _build_test_case("CVKI-20261014-003", lat=13.4000, lon=77.5946)

        self.repo.save(c1)
        self.repo.save(c2)
        self.repo.save(c3)

        summary = asyncio.run(find_nearby_cases(base_lat, base_lon, radius_meters=250.0, actor_role="admin"))

        self.assertEqual(summary.count, 2)
        refs = [item.reference_id for item in summary.cases]
        self.assertTrue(any("001" in r for r in refs))
        self.assertTrue(any("002" in r for r in refs))
        self.assertFalse(any("003" in r for r in refs))

    # -------------------------------------------------------------------------
    # M. Radius Limit
    # -------------------------------------------------------------------------
    def test_m_radius_limit(self):
        summary = asyncio.run(find_nearby_cases(12.9716, 77.5946, radius_meters=50_000.0))
        self.assertLessEqual(summary.radius_meters, settings.GEO_SEARCH_MAX_RADIUS_METERS)

        res = self.client.get("/api/v1/geospatial/cases/nearby?latitude=12.0&longitude=77.0&radius_meters=6000")
        self.assertEqual(res.status_code, 422)

    # -------------------------------------------------------------------------
    # N. Time-Window Filter
    # -------------------------------------------------------------------------
    def test_n_time_window_filter(self):
        now = datetime.now(timezone.utc)
        recent_case = _build_test_case("CVKI-20261014-REC", created_at=now - timedelta(days=5))
        old_case = _build_test_case("CVKI-20261014-OLD", created_at=now - timedelta(days=60))

        self.repo.save(recent_case)
        self.repo.save(old_case)

        summary = asyncio.run(
            find_nearby_cases(12.9716, 77.5946, radius_meters=500.0, time_window_days=30, actor_role="admin")
        )

        refs = [c.reference_id for c in summary.cases]
        self.assertTrue(any("REC" in r for r in refs))
        self.assertFalse(any("OLD" in r for r in refs))

    # -------------------------------------------------------------------------
    # O. Category Filter
    # -------------------------------------------------------------------------
    def test_o_category_filter(self):
        c_manhole = _build_test_case("CVKI-20261014-MAN", issue_class="open_damaged_manhole")
        c_sign = _build_test_case("CVKI-20261014-SGN", issue_class="damaged_missing_road_sign")

        self.repo.save(c_manhole)
        self.repo.save(c_sign)

        summary = asyncio.run(find_nearby_cases(12.9716, 77.5946, issue_category="open_damaged_manhole"))

        for item in summary.cases:
            self.assertEqual(item.issue_class, "open_damaged_manhole")

    # -------------------------------------------------------------------------
    # P. Unauthorized Case Access (RBAC)
    # -------------------------------------------------------------------------
    def test_p_unauthorized_case_access(self):
        case = _build_test_case("CVKI-20261014-AUTH1", assigned_to="usr_authority_A")
        self.repo.save(case)

        # Mock current user as Authority B (not assigned to this case)
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_authority_B",
            email="auth_b@example.com",
            role=UserRole.AUTHORITY.value,
        )

        res = self.client.get(f"/api/v1/geospatial/cases/{case.reference_id}/context")
        self.assertEqual(res.status_code, 403)
        self.assertIn("Authorities can only view", res.json()["detail"])

    # -------------------------------------------------------------------------
    # Q. Privacy Protection (No Citizen PII in Spatial Returns)
    # -------------------------------------------------------------------------
    def test_q_privacy_protection(self):
        case = _build_test_case("CVKI-20261014-PII")
        self.repo.save(case)

        # Unauthenticated citizen call
        self.client.cookies.clear()
        res = self.client.get(
            f"/api/v1/geospatial/cases/nearby?latitude={case.location.latitude}&longitude={case.location.longitude}"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for item in data["cases"]:
            self.assertNotIn("user_id", item)
            self.assertNotIn("email", item)
            self.assertNotIn("description", item)
            self.assertTrue(item["reference_id"].endswith("-***"))

    # -------------------------------------------------------------------------
    # R. Same-Road Relationship
    # -------------------------------------------------------------------------
    def test_r_same_road_relationship(self):
        now = datetime.now(timezone.utc)
        relationships = classify_spatial_relationships(
            target_lat=12.9716,
            target_lon=77.5946,
            target_road="MG Road",
            target_category="open_damaged_manhole",
            case_lat=12.9720,
            case_lon=77.5950,
            case_road="  m.g. road  ",  # Normalized match with punctuation stripping
            case_category="other_issue",
            distance_m=60.0,
            case_created_at=now,
            now=now,
        )
        self.assertIn(SpatialRelationship.NEARBY, relationships)
        self.assertIn(SpatialRelationship.SAME_ROAD, relationships)

    # -------------------------------------------------------------------------
    # S. Recurrence Context
    # -------------------------------------------------------------------------
    def test_s_recurrence_context(self):
        now = datetime.now(timezone.utc)
        relationships = classify_spatial_relationships(
            target_lat=12.9716,
            target_lon=77.5946,
            target_road="Outer Ring Road",
            target_category="road_waterlogging",
            case_lat=12.9725,
            case_lon=77.5950,
            case_road="Outer Ring Road",
            case_category="road_waterlogging",
            distance_m=110.0,
            case_created_at=now - timedelta(days=4),
            now=now,
        )
        self.assertIn(SpatialRelationship.RECURRENCE_CANDIDATE, relationships)

    # -------------------------------------------------------------------------
    # T. Hotspot Context
    # -------------------------------------------------------------------------
    def test_t_hotspot_context(self):
        now = datetime.now(timezone.utc)
        relationships = classify_spatial_relationships(
            target_lat=12.9716,
            target_lon=77.5946,
            target_road="Hosur Road",
            target_category="open_damaged_manhole",
            case_lat=12.9720,
            case_lon=77.5948,
            case_road="Hosur Road",
            case_category="road_waterlogging",
            distance_m=80.0,
            case_created_at=now - timedelta(days=10),
            now=now,
        )
        self.assertIn(SpatialRelationship.HOTSPOT_CONTEXT, relationships)

    # -------------------------------------------------------------------------
    # U. Authority Integration (M6.1 Resolver is Source of Truth)
    # -------------------------------------------------------------------------
    def test_u_authority_integration(self):
        ctx = asyncio.run(
            get_geospatial_intelligence_context(
                latitude=12.9716,
                longitude=77.5946,
                issue_category="open_damaged_manhole",
            )
        )

        self.assertIsNotNone(ctx.authority_preview)
        self.assertIn("authority_status", ctx.authority_preview)
        self.assertIn("resolution_message", ctx.authority_preview)

    # -------------------------------------------------------------------------
    # V. Coordinate Order Correctness ([longitude, latitude] for GeoJSON)
    # -------------------------------------------------------------------------
    def test_v_coordinate_order_correctness(self):
        lat, lon = 12.9716, 77.5946
        geojson = to_geojson_point(lat, lon)
        self.assertEqual(geojson["type"], "Point")
        self.assertEqual(geojson["coordinates"][0], lon)  # Longitude first
        self.assertEqual(geojson["coordinates"][1], lat)  # Latitude second

        parsed_lat, parsed_lon = from_geojson_point(geojson)
        self.assertEqual(parsed_lat, lat)
        self.assertEqual(parsed_lon, lon)

    # -------------------------------------------------------------------------
    # W. Geospatial Index / Query Bounding Box Behavior
    # -------------------------------------------------------------------------
    def test_w_geospatial_bounding_box(self):
        lat, lon = 12.9716, 77.5946
        min_lat, min_lon, max_lat, max_lon = bounding_box_for_radius(lat, lon, 250.0)

        self.assertTrue(min_lat <= lat <= max_lat)
        self.assertTrue(min_lon <= lon <= max_lon)
        lat_delta = max_lat - lat
        self.assertTrue(0.002 <= lat_delta <= 0.003)

    # -------------------------------------------------------------------------
    # X. Existing M5.2 Civic Intelligence Regression Check
    # -------------------------------------------------------------------------
    def test_x_existing_m52_regression(self):
        now = datetime.now(timezone.utc)
        case_a = _build_test_case(
            "CVKI-20261014-A",
            lat=12.9716,
            lon=77.5946,
            issue_class="road_waterlogging",
            road="MG Road",
            city="Bengaluru",
            created_at=now - timedelta(days=10),
        )
        case_b = _build_test_case(
            "CVKI-20261014-B",
            lat=12.9718,
            lon=77.5948,
            issue_class="road_waterlogging",
            road="MG Road",
            city="Bengaluru",
            created_at=now,
        )
        self.repo.save(case_a)
        self.repo.save(case_b)

        # Mock current user as Admin
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_admin",
            email="admin@example.com",
            role=UserRole.ADMIN.value,
        )

        res = self.client.get(f"/api/v1/admin/cases/{case_b.reference_id}/intelligence")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["reference_id"], case_b.reference_id)
        self.assertTrue(data["recurrence"]["recurrence_detected"])
        self.assertEqual(data["recurrence"]["recurrence_count"], 1)


if __name__ == "__main__":
    unittest.main()
