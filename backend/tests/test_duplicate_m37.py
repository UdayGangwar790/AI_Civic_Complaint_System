from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.schemas.authority import AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.schemas.duplicate import DuplicateCheckRequest
from app.services.complaint_case import (
    ComplaintCaseDatabaseError,
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
from app.services.duplicate import check_complaint_duplicate


class TestDuplicateM37(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()
        reg = cls.client.post("/api/v1/auth/register", json={"email": "m37_dup_test@cvki.internal", "password": "Password123!"})
        if reg.status_code in (200, 201):
            cls.token = reg.cookies.get(settings.AUTH_COOKIE_NAME)
        else:
            login = cls.client.post("/api/v1/auth/login", json={"email": "m37_dup_test@cvki.internal", "password": "Password123!"})
            cls.token = login.cookies.get(settings.AUTH_COOKIE_NAME)
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def setUp(self):
        self.client.cookies.clear()
        from app.services import complaint_case as cc_mod
        self._orig_repo = cc_mod.case_repository
        self.repo = InMemoryComplaintCaseRepository()
        set_case_repository(self.repo)

    def tearDown(self):
        set_case_repository(self._orig_repo)

    def _seed_case(
        self,
        reference_id: str,
        issue_class: str = "open_damaged_manhole",
        title: str = "Dangerous open manhole on MG Road",
        description: str = "A deep open drain pit without cover is posing severe fall risk.",
        lat: float = 12.9716,
        lon: float = 77.5946,
        created_at: datetime | None = None,
        user_id: str = "citizen_secret_user_999",
    ) -> ComplaintCase:
        now = created_at or datetime.now(timezone.utc)
        case = ComplaintCase(
            reference_id=reference_id,
            user_id=user_id,
            status="submitted_to_cvki",
            created_at=now,
            updated_at=now,
            issue=CaseIssue(class_name=issue_class, label=issue_class.replace("_", " ").title(), severity="high", confidence=0.91),
            location=ComplaintLocation(road="MG Road", latitude=lat, longitude=lon),
            authority=AuthorityResult(authority_status="not_verified", limitations=[]),
            complaint=CaseComplaint(language="en", title=title, description=description),
            evidence=["photo.jpg"],
            follow_up=FollowUp(guidance="Standard guidance", external_submission_status="not_submitted"),
        )
        self.repo.save(case)
        return case

    # 1. Exact duplicate
    def test_01_exact_duplicate(self):
        self._seed_case(
            reference_id="CVKI-20261011-DUP001",
            issue_class="open_damaged_manhole",
            title="Dangerous open manhole on MG Road",
            description="A deep open drain pit without cover is posing severe fall risk.",
            lat=12.9716,
            lon=77.5946,
        )

        payload = {
            "complaint_text": "Dangerous open manhole on MG Road. A deep open drain pit without cover is posing severe fall risk.",
            "issue_category": "open_damaged_manhole",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["classification"], "duplicate")
        self.assertEqual(data["matched_reference_id"], "CVKI-20261011-DUP001")
        self.assertAlmostEqual(data["distance_meters"], 0.0, delta=1.0)
        self.assertGreaterEqual(data["similarity_score"], 0.82)
        self.assertTrue(data["issue_match"])

    # 2. Semantically similar complaint
    def test_02_semantically_similar_complaint(self):
        self._seed_case(
            reference_id="CVKI-20261011-DUP002",
            issue_class="open_damaged_manhole",
            title="Open manhole on MG Road",
            description="Deep chamber lid broken near Metro station.",
            lat=12.9716,
            lon=77.5946,
        )

        payload = {
            "complaint_text": "MG Road open manhole with broken lid near Metro station.",
            "issue_category": "open_damaged_manhole",
            "latitude": 12.9718,  # ~25 meters away
            "longitude": 77.5946,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["classification"], ["duplicate", "possible_duplicate"])
        self.assertEqual(data["matched_reference_id"], "CVKI-20261011-DUP002")

    # 3. Same issue but different location
    def test_03_same_issue_different_location(self):
        self._seed_case(
            reference_id="CVKI-20261011-DUP003",
            issue_class="road_waterlogging",
            title="Severe waterlogging on Ring Road",
            description="Flooding due to clogged storm drain.",
            lat=12.9716,
            lon=77.5946,
        )

        payload = {
            "complaint_text": "Severe waterlogging on Ring Road. Flooding due to clogged storm drain.",
            "issue_category": "road_waterlogging",
            "latitude": 13.0827,  # ~15 km away (North Bangalore)
            "longitude": 77.5877,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["classification"], "unique")
        self.assertIsNone(data["matched_reference_id"])

    # 4. Same location but different issue
    def test_04_same_location_different_issue(self):
        self._seed_case(
            reference_id="CVKI-20261011-DUP004",
            issue_class="open_damaged_manhole",
            title="Open manhole pit",
            description="Pit is open on road.",
            lat=12.9716,
            lon=77.5946,
        )

        payload = {
            "complaint_text": "Broken speed limit road sign on the footpath.",
            "issue_category": "damaged_missing_road_sign",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["classification"], "unique")
        self.assertFalse(data["issue_match"])
        self.assertIsNone(data["matched_reference_id"])

    # 5. Different locations
    def test_05_different_locations(self):
        self._seed_case(
            reference_id="CVKI-20261011-DUP005",
            issue_class="damaged_missing_road_sign",
            title="Road sign knocked down",
            description="Traffic signboard missing at crossing.",
            lat=12.9716,
            lon=77.5946,
        )

        payload = {
            "complaint_text": "Road sign knocked down. Traffic signboard missing at crossing.",
            "issue_category": "damaged_missing_road_sign",
            "latitude": 28.6139,  # New Delhi (~1700 km away)
            "longitude": 77.2090,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["classification"], "unique")

    # 6. Different time window
    def test_06_different_time_window(self):
        old_time = datetime.now(timezone.utc) - timedelta(days=10)  # 240 hours ago
        self._seed_case(
            reference_id="CVKI-20261011-DUP006",
            issue_class="open_damaged_manhole",
            title="Open manhole",
            description="Manhole lid open.",
            lat=12.9716,
            lon=77.5946,
            created_at=old_time,
        )

        payload = {
            "complaint_text": "Open manhole. Manhole lid open.",
            "issue_category": "open_damaged_manhole",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Should not be classified as active duplicate due to elapsed time window
        self.assertEqual(data["classification"], "unique")

    # 7. No previous cases
    def test_07_no_previous_cases(self):
        payload = {
            "complaint_text": "Road waterlogging near hospital.",
            "issue_category": "road_waterlogging",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["classification"], "unique")
        self.assertEqual(data["similarity_score"], 0.0)
        self.assertIsNone(data["matched_reference_id"])

    # 8. Private case data not leaked
    def test_08_private_case_data_not_leaked(self):
        secret_title = "Private citizen sensitive title confidential"
        secret_desc = "Resident phone 9876543210 and secret details"
        self._seed_case(
            reference_id="CVKI-20261011-DUP008",
            issue_class="open_damaged_manhole",
            title=secret_title,
            description=secret_desc,
            lat=12.9716,
            lon=77.5946,
            user_id="secret_citizen_id_xyz",
        )

        payload = {
            "complaint_text": f"{secret_title} {secret_desc}",
            "issue_category": "open_damaged_manhole",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        raw_text = res.text
        # Assert private personal details and other citizen's full text are not exposed in the response
        self.assertNotIn("secret_citizen_id_xyz", raw_text)
        self.assertNotIn("9876543210", raw_text)
        self.assertNotIn("confidential", raw_text)

    # 9. Unauthorized access
    def test_09_unauthorized_access(self):
        payload = {
            "complaint_text": "Testing unauthenticated request",
            "issue_category": "open_damaged_manhole",
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload)
        self.assertEqual(res.status_code, 401)

    # 10. Threshold behavior
    def test_10_threshold_behavior(self):
        self._seed_case(
            reference_id="CVKI-20261011-DUP010",
            issue_class="open_damaged_manhole",
            title="Broken drain cover",
            description="Broken drain cover on street.",
            lat=12.9716,
            lon=77.5946,
        )

        # Distance exactly beyond DUPLICATE_DISTANCE_METERS (150m) but within 500m
        payload = {
            "complaint_text": "Broken drain cover on street.",
            "issue_category": "open_damaged_manhole",
            "latitude": 12.9735,  # ~210m away
            "longitude": 77.5946,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["distance_meters"], settings.DUPLICATE_DISTANCE_METERS)
        self.assertNotEqual(data["classification"], "duplicate")

    # 11. Missing coordinates
    def test_11_missing_coordinates(self):
        self._seed_case(
            reference_id="CVKI-20261011-DUP011",
            issue_class="damaged_missing_road_sign",
            title="Missing speed limit sign",
            description="The speed limit signboard was removed and is missing.",
            lat=None,
            lon=None,
        )

        payload = {
            "complaint_text": "Missing speed limit sign. The speed limit signboard was removed and is missing.",
            "issue_category": "damaged_missing_road_sign",
            "latitude": None,
            "longitude": None,
        }
        res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["classification"], "possible_duplicate")
        self.assertIsNone(data["distance_meters"])

    # 12. Malformed input
    def test_12_malformed_input(self):
        # Empty text
        res = self.client.post("/api/v1/complaint/duplicate-check", json={"complaint_text": "", "issue_category": "road_waterlogging"}, headers=self.auth_headers)
        self.assertEqual(res.status_code, 422)

        # Missing issue_category
        res2 = self.client.post("/api/v1/complaint/duplicate-check", json={"complaint_text": "Valid text"}, headers=self.auth_headers)
        self.assertEqual(res2.status_code, 422)

    # 13. MongoDB unavailable
    def test_13_mongodb_unavailable(self):
        payload = {
            "complaint_text": "Valid complaint text for db failure test",
            "issue_category": "open_damaged_manhole",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
        with patch.object(self.repo, "list_recent_candidates", side_effect=ComplaintCaseDatabaseError("DB down")):
            res = self.client.post("/api/v1/complaint/duplicate-check", json=payload, headers=self.auth_headers)
            self.assertEqual(res.status_code, 503)
            self.assertIn("Database service is unavailable", res.json()["detail"])

    # 14. Existing case creation regression
    def test_14_existing_case_creation_regression(self):
        case_payload = {
            "issue": {
                "class_name": "open_damaged_manhole",
                "label": "Open/Damaged Manhole",
                "severity": "high",
                "confidence": 0.85,
            },
            "location": {
                "road": "Outer Ring Road",
                "city": "Bengaluru",
                "latitude": 12.9716,
                "longitude": 77.5946,
            },
            "complaint": {
                "language": "en",
                "title": "Open drain on Outer Ring Road",
                "description": "Pedestrians can fall into the uncovered drain.",
            },
            "evidence": ["photo.jpg"],
        }
        res = self.client.post("/api/v1/complaint/cases", json=case_payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "submitted_to_cvki")
        self.assertIn("nlp_analysis", data)
        self.assertIn("duplicate_analysis", data)
        self.assertIn("priority_analysis", data)
        self.assertIsNotNone(data["duplicate_analysis"])
        self.assertEqual(data["duplicate_analysis"]["classification"], "unique")


if __name__ == "__main__":
    unittest.main()
