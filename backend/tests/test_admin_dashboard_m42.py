from datetime import datetime, timedelta, timezone
import unittest
import uuid

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, NOTIFICATIONS_COLLECTION, USERS_COLLECTION
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DB_NAME = "cvki_test_admin_dashboard_m4_2"


def _build_test_case(
    ref_id: str,
    class_name: str = "open_damaged_manhole",
    status: str = "submitted_to_cvki",
    priority_level: str = "P2",
    created_at: datetime = None,
    assigned_to: str = None,
):
    now = created_at or datetime.now(timezone.utc)
    assignment = None
    if assigned_to:
        assignment = {
            "assigned_to_user_id": assigned_to,
            "assigned_to_role": "authority",
            "assigned_by_user_id": "usr_admin_123",
            "assigned_at": now.isoformat(),
            "assignment_status": "assigned",
        }
    else:
        assignment = {
            "assigned_to_user_id": None,
            "assigned_to_role": None,
            "assigned_by_user_id": None,
            "assigned_at": None,
            "assignment_status": "unassigned",
        }

    return {
        "reference_id": ref_id,
        "user_id": "usr_citizen_456",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "status": status,
        "issue": {
            "class_name": class_name,
            "label": class_name.replace("_", " ").title(),
            "severity": "high",
            "confidence": 0.92,
        },
        "location": {
            "road": "Outer Ring Road",
            "city": "Bengaluru",
            "pincode": "560103",
        },
        "complaint": {
            "language": "en",
            "title": f"Test civic issue {ref_id}",
            "description": "Details about civic issue.",
        },
        "authority": {
            "name": "Bruhat Bengaluru Mahanagara Palike",
            "department": "Road Infrastructure",
            "portal_url": "https://bbmp.gov.in",
            "authority_status": "verified",
        },
        "follow_up": {
            "guidance": "Reported to civic authority.",
            "external_submission_status": "not_submitted",
        },
        "priority_analysis": {
            "priority_level": priority_level,
            "priority_score": 85 if priority_level == "P1" else 65,
            "risk_level": "Critical" if priority_level == "P1" else "Medium",
            "risk_factors": ["High pedestrian density"],
        },
        "duplicate_analysis": {
            "status": "unique",
            "classification": "unique",
            "issue_match": False,
            "reason": "Unique civic issue instance",
            "similarity_score": 0.1,
        },
        "assignment": assignment,
    }


class TestAdminDashboardM42(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB is unavailable for Admin Dashboard test suite.")

        cls.sync_db = cls.sync_client[TEST_DB_NAME]
        cls.users_col = cls.sync_db[USERS_COLLECTION]
        cls.cases_col = cls.sync_db[COMPLAINT_CASES_COLLECTION]
        cls.notifs_col = cls.sync_db[NOTIFICATIONS_COLLECTION]

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
        self.notifs_col.delete_many({})

        self.admin_id = self._insert_user("admin@cvki.gov.in", role="admin")
        self.citizen_id = self._insert_user("citizen@cvki.gov.in", role="citizen")
        self.authority_id = self._insert_user("authority@cvki.gov.in", role="authority")

        self.admin_token = create_access_token(self.admin_id, role="admin", email="admin@cvki.gov.in")
        self.citizen_token = create_access_token(self.citizen_id, role="citizen", email="citizen@cvki.gov.in")
        self.authority_token = create_access_token(self.authority_id, role="authority", email="authority@cvki.gov.in")

    def _insert_user(self, email: str, role: str = "citizen", is_active: bool = True) -> str:
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        self.users_col.insert_one({
            "user_id": user_id,
            "email": email.strip().lower(),
            "password_hash": hash_password("SecureAdmin2026!"),
            "role": role,
            "created_at": now,
            "updated_at": now,
            "is_active": is_active,
        })
        return user_id

    # 1. Admin dashboard access allowed
    def test_01_admin_dashboard_access_allowed(self):
        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_cases", data)
        self.assertIn("priority_counts", data)
        self.assertIn("issue_counts", data)

    # 2. Citizen denied (403)
    def test_02_citizen_denied_dashboard_access(self):
        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("insufficient permissions", res.json()["detail"].lower())

    # 3. Authority denied (403)
    def test_03_authority_denied_dashboard_access(self):
        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.authority_token}"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("insufficient permissions", res.json()["detail"].lower())

    # 4. Unauthenticated denied (401)
    def test_04_unauthenticated_denied_dashboard_access(self):
        res = self.client.get("/api/v1/admin/dashboard/summary")
        self.assertEqual(res.status_code, 401)

    # 5. Summary counts calculation
    def test_05_summary_counts_calculation(self):
        cases = [
            _build_test_case("CVKI-001", status="submitted_to_cvki"),
            _build_test_case("CVKI-002", status="under_review", assigned_to="usr_auth_1"),
            _build_test_case("CVKI-003", status="resolved", assigned_to="usr_auth_1"),
        ]
        self.cases_col.insert_many(cases)

        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total_cases"], 3)
        self.assertEqual(data["open_cases"], 2)
        self.assertEqual(data["resolved_cases"], 1)
        self.assertEqual(data["unassigned_cases"], 1)

    # 6. Priority aggregation
    def test_06_priority_aggregation(self):
        cases = [
            _build_test_case("CVKI-P1", priority_level="P1"),
            _build_test_case("CVKI-P2-A", priority_level="P2"),
            _build_test_case("CVKI-P2-B", priority_level="P2"),
            _build_test_case("CVKI-P3", priority_level="P3"),
            _build_test_case("CVKI-P4", priority_level="P4"),
        ]
        self.cases_col.insert_many(cases)

        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        p_counts = res.json()["priority_counts"]
        self.assertEqual(p_counts["P1"], 1)
        self.assertEqual(p_counts["P2"], 2)
        self.assertEqual(p_counts["P3"], 1)
        self.assertEqual(p_counts["P4"], 1)

    # 7. Issue aggregation
    def test_07_issue_aggregation(self):
        cases = [
            _build_test_case("CVKI-M1", class_name="open_damaged_manhole"),
            _build_test_case("CVKI-M2", class_name="open_damaged_manhole"),
            _build_test_case("CVKI-S1", class_name="damaged_missing_road_sign"),
            _build_test_case("CVKI-W1", class_name="road_waterlogging"),
        ]
        self.cases_col.insert_many(cases)

        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        i_counts = res.json()["issue_counts"]
        self.assertEqual(i_counts["open_damaged_manhole"], 2)
        self.assertEqual(i_counts["damaged_missing_road_sign"], 1)
        self.assertEqual(i_counts["road_waterlogging"], 1)
        self.assertEqual(i_counts["other_civic_issue"], 0)

    # 8. Status aggregation
    def test_08_status_aggregation(self):
        cases = [
            _build_test_case("CVKI-S-SUB", status="submitted_to_cvki"),
            _build_test_case("CVKI-S-REV", status="under_review"),
            _build_test_case("CVKI-S-RES", status="resolved"),
        ]
        self.cases_col.insert_many(cases)

        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        s_counts = res.json()["status_counts"]
        self.assertEqual(s_counts["submitted_to_cvki"], 1)
        self.assertEqual(s_counts["under_review"], 1)
        self.assertEqual(s_counts["resolved"], 1)

    # 9. Recent cases newest first
    def test_09_recent_cases_ordering(self):
        now = datetime.now(timezone.utc)
        case_old = _build_test_case("CVKI-OLD", created_at=now - timedelta(days=2))
        case_mid = _build_test_case("CVKI-MID", created_at=now - timedelta(days=1))
        case_new = _build_test_case("CVKI-NEW", created_at=now)
        self.cases_col.insert_many([case_old, case_mid, case_new])

        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        recent = res.json()["recent_cases"]
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[0]["reference_id"], "CVKI-NEW")
        self.assertEqual(recent[1]["reference_id"], "CVKI-MID")
        self.assertEqual(recent[2]["reference_id"], "CVKI-OLD")

    # 10. Empty database handles safely
    def test_10_empty_database_handling(self):
        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total_cases"], 0)
        self.assertEqual(data["open_cases"], 0)
        self.assertEqual(data["resolved_cases"], 0)
        self.assertEqual(data["unassigned_cases"], 0)
        self.assertEqual(data["recent_cases"], [])
        self.assertEqual(data["priority_counts"]["P1"], 0)

    # 11. Malformed query and expired/invalid auth handling
    def test_11_malformed_auth_handling(self):
        res_bad_token = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        self.assertEqual(res_bad_token.status_code, 401)

        res_bad_header = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": "Basic admin:password"},
        )
        self.assertEqual(res_bad_header.status_code, 401)

    # 12. No private authentication fields exposed
    def test_12_no_private_auth_fields_exposed(self):
        case = _build_test_case("CVKI-PRIVACY-1")
        self.cases_col.insert_one(case)

        res = self.client.get(
            "/api/v1/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        text = res.text
        self.assertNotIn("password_hash", text)
        self.assertNotIn("access_token", text)
        self.assertNotIn("jwt_secret", text)


if __name__ == "__main__":
    unittest.main()
