from datetime import datetime, timedelta, timezone
import unittest
import uuid

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, NOTIFICATIONS_COLLECTION, USERS_COLLECTION
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DB_NAME = "cvki_test_admin_case_mgmt_m4_3"


def _build_test_case(
    ref_id: str,
    user_id: str = "usr_citizen_456",
    class_name: str = "open_damaged_manhole",
    status: str = "submitted_to_cvki",
    priority_level: str = "P2",
    created_at: datetime = None,
    assigned_to: str = None,
    duplicate_status: str = "unique",
):
    now = created_at or datetime.now(timezone.utc)
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
            "assigned_to_role": "authority",
            "assigned_by_user_id": None,
            "assigned_at": None,
            "assignment_status": "unassigned",
        }

    return {
        "reference_id": ref_id,
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
        "status": status,
        "issue": {
            "class_name": class_name,
            "label": class_name.replace("_", " ").title(),
            "severity": "high",
            "confidence": 0.92,
        },
        "location": {
            "road": "MG Road",
            "city": "Bengaluru",
            "pincode": "560001",
        },
        "complaint": {
            "language": "en",
            "title": f"Civic Issue {ref_id}",
            "description": "Hazardous road condition detected by CVKI.",
        },
        "evidence": ["frame_001.jpg"],
        "authority": {
            "name": "Bruhat Bengaluru Mahanagara Palike",
            "department": "Road Infrastructure",
            "portal_url": "https://bbmp.gov.in",
            "authority_status": "verified",
        },
        "follow_up": {
            "guidance": "Reported to BBMP control room.",
            "external_submission_status": "not_submitted",
        },
        "priority_analysis": {
            "priority_level": priority_level,
            "priority_score": 90 if priority_level == "P1" else (70 if priority_level == "P2" else 40),
            "risk_level": "Critical" if priority_level == "P1" else "Medium",
            "risk_factors": ["High pedestrian density"],
        },
        "duplicate_analysis": {
            "status": duplicate_status,
            "classification": duplicate_status,
            "issue_match": duplicate_status != "unique",
            "reason": "Test duplicate status evaluation",
            "similarity_score": 0.85 if duplicate_status != "unique" else 0.1,
        },
        "assignment": assignment,
    }


class TestAdminCaseManagementM43(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB is unavailable for Admin Case Management test suite.")

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

    # 1. Admin case list endpoint returns paginated envelope
    def test_01_admin_case_list(self):
        c1 = _build_test_case("CVKI-CASE-001")
        c2 = _build_test_case("CVKI-CASE-002")
        self.cases_col.insert_many([c1, c2])

        res = self.client.get(
            "/api/v1/admin/cases",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["page"], 1)
        self.assertEqual(len(data["items"]), 2)

    def test_admin_case_search_validates_sort_filters_and_page_bounds(self):
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        for query in (
            "sort_by=untrusted",
            "priority=invalid",
            "status=unknown",
            "page=1001",
            "page_size=101",
            "created_from=not-a-date",
            "created_from=2026-10-12T00:00:00Z&created_to=2026-10-01T00:00:00Z",
        ):
            with self.subTest(query=query):
                response = self.client.get(
                    f"/api/v1/admin/cases?{query}",
                    headers=headers,
                )
                self.assertEqual(response.status_code, 422)

    # 2. Pagination behaves correctly
    def test_02_pagination(self):
        cases = [_build_test_case(f"CVKI-PAG-{i:03d}") for i in range(1, 6)]
        self.cases_col.insert_many(cases)

        res = self.client.get(
            "/api/v1/admin/cases?page=2&page_size=2",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["page_size"], 2)
        self.assertEqual(data["total_pages"], 3)
        self.assertEqual(len(data["items"]), 2)

    # 3. Newest-first sorting by default
    def test_03_newest_first_sorting(self):
        now = datetime.now(timezone.utc)
        c_old = _build_test_case("CVKI-SORT-OLD", created_at=now - timedelta(days=5))
        c_new = _build_test_case("CVKI-SORT-NEW", created_at=now)
        self.cases_col.insert_many([c_old, c_new])

        res = self.client.get(
            "/api/v1/admin/cases",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(items[0]["reference_id"], "CVKI-SORT-NEW")
        self.assertEqual(items[1]["reference_id"], "CVKI-SORT-OLD")

    # 4. Reference search
    def test_04_reference_search(self):
        c1 = _build_test_case("CVKI-SEARCH-AAA")
        c2 = _build_test_case("CVKI-SEARCH-BBB")
        self.cases_col.insert_many([c1, c2])

        res = self.client.get(
            "/api/v1/admin/cases?search=SEARCH-AAA",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["reference_id"], "CVKI-SEARCH-AAA")

    # 5. Priority filter
    def test_05_priority_filter(self):
        c1 = _build_test_case("CVKI-PRIO-P1", priority_level="P1")
        c2 = _build_test_case("CVKI-PRIO-P4", priority_level="P4")
        self.cases_col.insert_many([c1, c2])

        res = self.client.get(
            "/api/v1/admin/cases?priority=P1",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["reference_id"], "CVKI-PRIO-P1")

    # 6. Issue filter
    def test_06_issue_filter(self):
        c1 = _build_test_case("CVKI-ISSUE-MAN", class_name="open_damaged_manhole")
        c2 = _build_test_case("CVKI-ISSUE-WATER", class_name="road_waterlogging")
        self.cases_col.insert_many([c1, c2])

        res = self.client.get(
            "/api/v1/admin/cases?issue=road_waterlogging",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["reference_id"], "CVKI-ISSUE-WATER")

    # 7. Status filter
    def test_07_status_filter(self):
        c1 = _build_test_case("CVKI-STAT-SUB", status="submitted_to_cvki")
        c2 = _build_test_case("CVKI-STAT-RES", status="resolved")
        self.cases_col.insert_many([c1, c2])

        res = self.client.get(
            "/api/v1/admin/cases?status=resolved",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["reference_id"], "CVKI-STAT-RES")

    # 8. Assignment filter
    def test_08_assignment_filter(self):
        c_unassigned = _build_test_case("CVKI-ASGN-NONE", assigned_to=None)
        c_assigned = _build_test_case("CVKI-ASGN-YES", assigned_to="usr_auth_123")
        self.cases_col.insert_many([c_unassigned, c_assigned])

        res_un = self.client.get(
            "/api/v1/admin/cases?assignment=unassigned",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_un.status_code, 200)
        self.assertEqual(len(res_un.json()["items"]), 1)
        self.assertEqual(res_un.json()["items"][0]["reference_id"], "CVKI-ASGN-NONE")

        res_asg = self.client.get(
            "/api/v1/admin/cases?assignment=assigned",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_asg.status_code, 200)
        self.assertEqual(len(res_asg.json()["items"]), 1)
        self.assertEqual(res_asg.json()["items"][0]["reference_id"], "CVKI-ASGN-YES")

    # 9. Duplicate filter
    def test_09_duplicate_filter(self):
        c_uniq = _build_test_case("CVKI-DUP-UNIQ", duplicate_status="unique")
        c_dup = _build_test_case("CVKI-DUP-YES", duplicate_status="duplicate")
        self.cases_col.insert_many([c_uniq, c_dup])

        res = self.client.get(
            "/api/v1/admin/cases?duplicate=duplicate",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["reference_id"], "CVKI-DUP-YES")

    # 10. Date filter
    def test_10_date_filter(self):
        now = datetime.now(timezone.utc)
        c_old = _build_test_case("CVKI-DATE-OLD", created_at=now - timedelta(days=10))
        c_mid = _build_test_case("CVKI-DATE-MID", created_at=now - timedelta(days=3))
        c_new = _build_test_case("CVKI-DATE-NEW", created_at=now)
        self.cases_col.insert_many([c_old, c_mid, c_new])

        date_from = (now - timedelta(days=5)).isoformat()
        res = self.client.get(
            f"/api/v1/admin/cases?created_from={date_from}",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 2)
        refs = [x["reference_id"] for x in items]
        self.assertIn("CVKI-DATE-MID", refs)
        self.assertIn("CVKI-DATE-NEW", refs)

    # 11. Combined filters
    def test_11_combined_filters(self):
        c1 = _build_test_case("CVKI-COMB-MATCH", class_name="open_damaged_manhole", priority_level="P1")
        c2 = _build_test_case("CVKI-COMB-DIFF1", class_name="open_damaged_manhole", priority_level="P3")
        c3 = _build_test_case("CVKI-COMB-DIFF2", class_name="road_waterlogging", priority_level="P1")
        self.cases_col.insert_many([c1, c2, c3])

        res = self.client.get(
            "/api/v1/admin/cases?priority=P1&issue=open_damaged_manhole",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["reference_id"], "CVKI-COMB-MATCH")

    # 12. Case detail endpoint
    def test_12_case_detail(self):
        c = _build_test_case("CVKI-DETAIL-100", assigned_to="usr_auth_999")
        self.cases_col.insert_one(c)

        res = self.client.get(
            "/api/v1/admin/cases/CVKI-DETAIL-100",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["reference_id"], "CVKI-DETAIL-100")
        self.assertIn("location", data)
        self.assertIn("authority", data)
        self.assertIn("complaint", data)
        self.assertIn("priority_analysis", data)
        self.assertIn("assignment", data)
        self.assertEqual(data["assignment"]["assigned_to_user_id"], "usr_auth_999")

    # 13. Nonexistent case detail returns 404
    def test_13_nonexistent_case_detail_returns_404(self):
        res = self.client.get(
            "/api/v1/admin/cases/CVKI-DOES-NOT-EXIST",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 404)

    # 14. Citizen denied case list and detail
    def test_14_citizen_denied(self):
        c = _build_test_case("CVKI-DENIED-CIT")
        self.cases_col.insert_one(c)

        res_list = self.client.get(
            "/api/v1/admin/cases",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(res_list.status_code, 403)

        res_detail = self.client.get(
            "/api/v1/admin/cases/CVKI-DENIED-CIT",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(res_detail.status_code, 403)

    # 15. Authority denied admin case list and detail
    def test_15_authority_denied(self):
        c = _build_test_case("CVKI-DENIED-AUTH")
        self.cases_col.insert_one(c)

        res_list = self.client.get(
            "/api/v1/admin/cases",
            headers={"Authorization": f"Bearer {self.authority_token}"},
        )
        self.assertEqual(res_list.status_code, 403)

        res_detail = self.client.get(
            "/api/v1/admin/cases/CVKI-DENIED-AUTH",
            headers={"Authorization": f"Bearer {self.authority_token}"},
        )
        self.assertEqual(res_detail.status_code, 403)

    # 16. Unauthenticated denied
    def test_16_unauthenticated_denied(self):
        res = self.client.get("/api/v1/admin/cases")
        self.assertEqual(res.status_code, 401)

    # 17. No password/hash/JWT leakage
    def test_17_no_secret_leakage(self):
        c = _build_test_case("CVKI-LEAK-TEST")
        self.cases_col.insert_one(c)

        res_detail = self.client.get(
            "/api/v1/admin/cases/CVKI-LEAK-TEST",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_detail.status_code, 200)
        text = res_detail.text
        self.assertNotIn("password_hash", text)
        self.assertNotIn("access_token", text)
        self.assertNotIn("jwt_secret", text)

    # 18. Citizen case ownership regression
    def test_18_existing_citizen_ownership_regression(self):
        # Insert a case owned by citizen_id and one owned by another citizen
        c_mine = _build_test_case("CVKI-MY-OWN", user_id=self.citizen_id)
        c_other = _build_test_case("CVKI-OTHER-USER", user_id="usr_other_789")
        self.cases_col.insert_many([c_mine, c_other])

        # Citizen calling /api/v1/complaint/cases/my must only see their own cases
        res = self.client.get(
            "/api/v1/complaint/cases/my",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        refs = [x["reference_id"] for x in items]
        self.assertIn("CVKI-MY-OWN", refs)
        self.assertNotIn("CVKI-OTHER-USER", refs)


if __name__ == "__main__":
    unittest.main()
