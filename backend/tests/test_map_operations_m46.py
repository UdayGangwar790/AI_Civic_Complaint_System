from datetime import datetime, timezone
import unittest
import uuid

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, USERS_COLLECTION
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DB_NAME = "cvki_test_map_operations_m4_6"


def _build_map_test_case(
    ref_id: str,
    lat: float = None,
    lng: float = None,
    issue_class: str = "open_damaged_manhole",
    priority: str = "P1",
    status: str = "assigned",
    city: str = "Bengaluru",
    road: str = "MG Road",
    assigned_to: str = None,
):
    now = datetime.now(timezone.utc)
    assignment = {
        "assigned_to_user_id": assigned_to,
        "assigned_to_role": "authority" if assigned_to else None,
        "assigned_to_email": "officer@bbmp.gov.in" if assigned_to else None,
        "assigned_by_user_id": "usr_admin_123" if assigned_to else None,
        "assigned_at": now if assigned_to else None,
        "assignment_status": "assigned" if assigned_to else "unassigned",
    }

    loc = {
        "road": road,
        "city": city,
        "pincode": "560001",
    }
    if lat is not None:
        loc["latitude"] = lat
    if lng is not None:
        loc["longitude"] = lng

    return {
        "reference_id": ref_id,
        "user_id": "usr_citizen_999",
        "created_at": now,
        "updated_at": now,
        "status": status,
        "issue": {
            "class_name": issue_class,
            "label": issue_class.replace("_", " ").title(),
            "severity": "high",
            "confidence": 0.95,
        },
        "location": loc,
        "complaint": {
            "language": "en",
            "title": f"Map Case {ref_id}",
            "description": "Civic issue on map.",
        },
        "evidence": ["frame_map.jpg"],
        "authority": {
            "name": "Bruhat Bengaluru Mahanagara Palike",
            "department": "Road Maintenance",
            "portal_url": "https://bbmp.gov.in",
            "authority_status": "verified",
        },
        "follow_up": {
            "guidance": "Pending site review.",
            "external_submission_status": "not_submitted",
        },
        "priority_analysis": {
            "priority_level": priority,
            "priority_score": 85,
            "risk_level": "High",
            "risk_factors": ["High traffic density"],
        },
        "duplicate_analysis": {
            "status": "unique",
            "classification": "unique",
            "issue_match": False,
            "reason": "Unique occurrence",
            "similarity_score": 0.05,
        },
        "assignment": assignment,
    }


class TestMapOperationsM46(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB is unavailable for Map Operations test suite.")

        cls.sync_db = cls.sync_client[TEST_DB_NAME]
        cls.users_col = cls.sync_db[USERS_COLLECTION]
        cls.cases_col = cls.sync_db[COMPLAINT_CASES_COLLECTION]

        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "sync_client") and cls.sync_client is not None:
            try:
                cls.sync_client.drop_database(TEST_DB_NAME)
            except Exception:
                pass
            cls.sync_client.close()

        if hasattr(cls, "client_cm"):
            cls.client_cm.__exit__(None, None, None)

        settings.MONGODB_DB_NAME = cls._orig_db

    def setUp(self):
        self.users_col.delete_many({})
        self.cases_col.delete_many({})

        self.admin_id = self._insert_user("admin@cvki.gov.in", role="admin")
        self.citizen_id = self._insert_user("citizen@cvki.gov.in", role="citizen")
        self.authority_id_1 = self._insert_user("officer1@bbmp.gov.in", role="authority")
        self.authority_id_2 = self._insert_user("officer2@bbmp.gov.in", role="authority")

        self.admin_token = create_access_token(self.admin_id, role="admin", email="admin@cvki.gov.in")
        self.citizen_token = create_access_token(self.citizen_id, role="citizen", email="citizen@cvki.gov.in")
        self.authority_token_1 = create_access_token(self.authority_id_1, role="authority", email="officer1@bbmp.gov.in")
        self.authority_token_2 = create_access_token(self.authority_id_2, role="authority", email="officer2@bbmp.gov.in")

    def _insert_user(self, email: str, role: str = "citizen") -> str:
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        self.users_col.insert_one({
            "user_id": user_id,
            "email": email.strip().lower(),
            "password_hash": hash_password("SecurePassword2026!"),
            "role": role,
            "is_active": True,
            "created_at": now,
        })
        return user_id

    # --- Test 1: Admin can access map cases endpoint ---
    def test_01_admin_access_allowed(self):
        self.cases_col.insert_one(_build_map_test_case("CVKI-MAP-001", lat=12.9716, lng=77.5946))
        resp = self.client.get(
            "/api/v1/admin/map/cases",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 1)
        self.assertEqual(len(data["mapped_cases"]), 1)
        self.assertEqual(data["mapped_cases"][0]["reference_id"], "CVKI-MAP-001")
        self.assertAlmostEqual(data["mapped_cases"][0]["latitude"], 12.9716, places=4)
        self.assertAlmostEqual(data["mapped_cases"][0]["longitude"], 77.5946, places=4)

    # --- Test 2: Unauthenticated request rejected (401) ---
    def test_02_unauthenticated_rejected(self):
        resp = self.client.get("/api/v1/admin/map/cases")
        self.assertEqual(resp.status_code, 401)

    # --- Test 3: Citizen cannot access admin map endpoint (403) ---
    def test_03_citizen_forbidden(self):
        resp = self.client.get(
            "/api/v1/admin/map/cases",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    # --- Test 4: Coordinate validation rejects None/missing coordinates ---
    def test_04_missing_coordinates_counted_as_unmapped(self):
        # One valid case, one with no coordinates
        self.cases_col.insert_one(_build_map_test_case("CVKI-MAP-VAL", lat=12.9716, lng=77.5946))
        self.cases_col.insert_one(_build_map_test_case("CVKI-MAP-NOLOC", lat=None, lng=None))

        resp = self.client.get(
            "/api/v1/admin/map/cases",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 1)
        self.assertEqual(data["unmapped_cases_count"], 1)
        self.assertEqual(data["mapped_cases"][0]["reference_id"], "CVKI-MAP-VAL")

    # --- Test 5: Coordinate validation rejects 0,0 null-island coordinates ---
    def test_05_null_island_coordinates_omitted(self):
        self.cases_col.insert_one(_build_map_test_case("CVKI-MAP-ZERO", lat=0.0, lng=0.0))

        resp = self.client.get(
            "/api/v1/admin/map/cases",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 0)
        self.assertEqual(data["unmapped_cases_count"], 1)

    # --- Test 6: Out-of-bounds coordinates rejected ---
    def test_06_out_of_bounds_coordinates_omitted(self):
        self.cases_col.insert_one(_build_map_test_case("CVKI-MAP-OOB", lat=120.0, lng=200.0))

        resp = self.client.get(
            "/api/v1/admin/map/cases",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 0)
        self.assertEqual(data["unmapped_cases_count"], 1)

    # --- Test 7: Filter by issue class ---
    def test_07_issue_filter(self):
        self.cases_col.insert_one(_build_map_test_case("CVKI-ISS-1", lat=12.97, lng=77.59, issue_class="open_damaged_manhole"))
        self.cases_col.insert_one(_build_map_test_case("CVKI-ISS-2", lat=12.98, lng=77.60, issue_class="road_waterlogging"))

        resp = self.client.get(
            "/api/v1/admin/map/cases?issue=road_waterlogging",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 1)
        self.assertEqual(data["mapped_cases"][0]["reference_id"], "CVKI-ISS-2")

    # --- Test 8: Filter by priority level ---
    def test_08_priority_filter(self):
        self.cases_col.insert_one(_build_map_test_case("CVKI-PRIO-1", lat=12.97, lng=77.59, priority="P1"))
        self.cases_col.insert_one(_build_map_test_case("CVKI-PRIO-2", lat=12.98, lng=77.60, priority="P3"))

        resp = self.client.get(
            "/api/v1/admin/map/cases?priority=P1",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 1)
        self.assertEqual(data["mapped_cases"][0]["reference_id"], "CVKI-PRIO-1")

    # --- Test 9: Filter by case status ---
    def test_09_status_filter(self):
        self.cases_col.insert_one(_build_map_test_case("CVKI-ST-1", lat=12.97, lng=77.59, status="in_progress"))
        self.cases_col.insert_one(_build_map_test_case("CVKI-ST-2", lat=12.98, lng=77.60, status="resolved"))

        resp = self.client.get(
            "/api/v1/admin/map/cases?status=resolved",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 1)
        self.assertEqual(data["mapped_cases"][0]["reference_id"], "CVKI-ST-2")

    # --- Test 10: Filter by assignment status ---
    def test_10_assignment_filter(self):
        self.cases_col.insert_one(_build_map_test_case("CVKI-ASGN-1", lat=12.97, lng=77.59, assigned_to=self.authority_id_1))
        self.cases_col.insert_one(_build_map_test_case("CVKI-ASGN-2", lat=12.98, lng=77.60, assigned_to=None))

        resp_assigned = self.client.get(
            "/api/v1/admin/map/cases?assignment=assigned",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp_assigned.status_code, 200)
        self.assertEqual(resp_assigned.json()["total_mapped"], 1)
        self.assertEqual(resp_assigned.json()["mapped_cases"][0]["reference_id"], "CVKI-ASGN-1")

        resp_unassigned = self.client.get(
            "/api/v1/admin/map/cases?assignment=unassigned",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp_unassigned.status_code, 200)
        self.assertEqual(resp_unassigned.json()["total_mapped"], 1)
        self.assertEqual(resp_unassigned.json()["mapped_cases"][0]["reference_id"], "CVKI-ASGN-2")

    # --- Test 11: Filter by city ---
    def test_11_city_filter(self):
        self.cases_col.insert_one(_build_map_test_case("CVKI-CITY-1", lat=12.97, lng=77.59, city="Bengaluru"))
        self.cases_col.insert_one(_build_map_test_case("CVKI-CITY-2", lat=13.08, lng=80.27, city="Chennai"))

        resp = self.client.get(
            "/api/v1/admin/map/cases?city=Chennai",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 1)
        self.assertEqual(data["mapped_cases"][0]["reference_id"], "CVKI-CITY-2")

    # --- Test 12: Authority can access only their assigned map cases ---
    def test_12_authority_map_scoped_to_assigned_cases(self):
        # Case assigned to authority 1
        self.cases_col.insert_one(_build_map_test_case("CVKI-AUTH-MY", lat=12.97, lng=77.59, assigned_to=self.authority_id_1))
        # Case assigned to authority 2
        self.cases_col.insert_one(_build_map_test_case("CVKI-AUTH-OTHER", lat=12.98, lng=77.60, assigned_to=self.authority_id_2))
        # Unassigned case
        self.cases_col.insert_one(_build_map_test_case("CVKI-AUTH-UNAS", lat=12.99, lng=77.61, assigned_to=None))

        resp = self.client.get(
            "/api/v1/authority/map/cases",
            headers={"Authorization": f"Bearer {self.authority_token_1}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 1)
        self.assertEqual(data["mapped_cases"][0]["reference_id"], "CVKI-AUTH-MY")

    def test_authority_map_rejects_invalid_date_range(self):
        response = self.client.get(
            "/api/v1/authority/map/cases?created_from=not-a-date",
            headers={"Authorization": f"Bearer {self.authority_token_1}"},
        )
        self.assertEqual(response.status_code, 422)

    # --- Test 13: Limit bound parameter works properly ---
    def test_13_query_limit_enforced(self):
        for i in range(5):
            self.cases_col.insert_one(_build_map_test_case(f"CVKI-LIM-{i}", lat=12.9 + (i * 0.01), lng=77.5 + (i * 0.01)))

        resp = self.client.get(
            "/api/v1/admin/map/cases?limit=3",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["mapped_cases"]), 3)

    # --- Test 14: Empty database returns valid zero-count structure ---
    def test_14_empty_database_returns_valid_structure(self):
        resp = self.client.get(
            "/api/v1/admin/map/cases",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_mapped"], 0)
        self.assertEqual(data["unmapped_cases_count"], 0)
        self.assertEqual(data["mapped_cases"], [])

    # --- Test 15: Map case fields contain all required display data ---
    def test_15_map_item_fields_complete(self):
        self.cases_col.insert_one(_build_map_test_case(
            "CVKI-FULL-01",
            lat=12.971598,
            lng=77.594562,
            road="Commercial Street",
            city="Bengaluru",
            issue_class="damaged_missing_road_sign",
            priority="P2",
            status="in_progress",
            assigned_to=self.authority_id_1,
        ))

        resp = self.client.get(
            "/api/v1/admin/map/cases",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        item = resp.json()["mapped_cases"][0]
        self.assertEqual(item["reference_id"], "CVKI-FULL-01")
        self.assertEqual(item["issue"], "damaged_missing_road_sign")
        self.assertEqual(item["priority"], "P2")
        self.assertEqual(item["status"], "in_progress")
        self.assertEqual(item["road"], "Commercial Street")
        self.assertEqual(item["city"], "Bengaluru")
        self.assertTrue(item["assigned"])
        self.assertEqual(item["assignment_status"], "assigned")

    # --- Test 16: Invalid query bounds rejected (422) ---
    def test_16_invalid_limit_rejected(self):
        resp = self.client.get(
            "/api/v1/admin/map/cases?limit=50000",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 422)
