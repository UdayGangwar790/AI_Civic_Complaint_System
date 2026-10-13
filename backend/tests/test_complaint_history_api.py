import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, USERS_COLLECTION
from app.main import app

TEST_DB_NAME = "cvki_test_history_m3_3"

BASE_CASE_PAYLOAD = {
    "issue": {
        "class_name": "open_damaged_manhole",
        "label": "Open/Damaged Manhole",
        "severity": "high",
        "confidence": 0.88,
    },
    "location": {
        "road": "History Boulevard",
        "area": "Sector 4",
        "city": "Bengaluru",
    },
    "complaint": {
        "language": "en",
        "title": "Historical Manhole Issue",
        "description": "Hazardous road defect.",
    },
    "evidence": ["Evidence note."],
}


class TestComplaintHistoryM33(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB not available for history tests")

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
        self.client.cookies.clear()
        self.users_col.delete_many({})
        self.cases_col.delete_many({})

    def register_and_get_headers(self, email: str = "history_tester@example.com") -> dict:
        res = self.client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
        return {"Authorization": f"Bearer {res.cookies.get('cvki_access_token')}"}

    # 1. Empty history returns 0 items
    def test_01_empty_history(self):
        headers = self.register_and_get_headers("empty_user@example.com")
        res = self.client.get("/api/v1/complaint/cases/my", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["pages"], 1)

    # 2. One case history
    def test_02_one_case_history(self):
        headers = self.register_and_get_headers("single_user@example.com")
        create_res = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers)
        ref_id = create_res.json()["reference_id"]

        res = self.client.get("/api/v1/complaint/cases/my", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["reference_id"], ref_id)
        self.assertEqual(item["title"], "Historical Manhole Issue")
        self.assertEqual(item["issue_class"], "open_damaged_manhole")
        self.assertEqual(item["status"], "submitted_to_cvki")
        self.assertEqual(item["external_submission_status"], "not_submitted")
        self.assertIn("History Boulevard", item["location_summary"])

    # 3. Multiple cases history
    def test_03_multiple_cases_history(self):
        headers = self.register_and_get_headers("multi_user@example.com")
        refs = []
        for i in range(3):
            payload = dict(BASE_CASE_PAYLOAD)
            payload["complaint"] = {"language": "en", "title": f"Issue #{i}", "description": f"Desc #{i}"}
            created = self.client.post("/api/v1/complaint/cases", json=payload, headers=headers).json()
            refs.append(created["reference_id"])

        res = self.client.get("/api/v1/complaint/cases/my", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["items"]), 3)

    # 4. Newest-first ordering
    def test_04_newest_first_ordering(self):
        headers = self.register_and_get_headers("ordering_user@example.com")
        created_refs = []
        for i in range(4):
            payload = dict(BASE_CASE_PAYLOAD)
            payload["complaint"] = {"language": "en", "title": f"Order Case {i}", "description": f"Order Desc {i}"}
            created = self.client.post("/api/v1/complaint/cases", json=payload, headers=headers).json()
            created_refs.append(created["reference_id"])

        res = self.client.get("/api/v1/complaint/cases/my", headers=headers)
        items = res.json()["items"]
        # The latest created case should appear first
        self.assertEqual(items[0]["reference_id"], created_refs[-1])
        self.assertEqual(items[-1]["reference_id"], created_refs[0])

    # 5. Pagination (page and limit)
    def test_05_pagination(self):
        headers = self.register_and_get_headers("paginated_user@example.com")
        for i in range(7):
            payload = dict(BASE_CASE_PAYLOAD)
            payload["complaint"] = {"language": "en", "title": f"Page Item {i}", "description": "Desc"}
            self.client.post("/api/v1/complaint/cases", json=payload, headers=headers)

        # Page 1, limit 3
        p1 = self.client.get("/api/v1/complaint/cases/my?page=1&limit=3", headers=headers).json()
        self.assertEqual(len(p1["items"]), 3)
        self.assertEqual(p1["total"], 7)
        self.assertEqual(p1["pages"], 3)
        self.assertEqual(p1["page"], 1)

        # Page 2, limit 3
        p2 = self.client.get("/api/v1/complaint/cases/my?page=2&limit=3", headers=headers).json()
        self.assertEqual(len(p2["items"]), 3)
        self.assertEqual(p2["page"], 2)

        # Page 3, limit 3 (should have 1 item)
        p3 = self.client.get("/api/v1/complaint/cases/my?page=3&limit=3", headers=headers).json()
        self.assertEqual(len(p3["items"]), 1)
        self.assertEqual(p3["page"], 3)

        # Ensure no overlap between page 1 and page 2
        p1_refs = {item["reference_id"] for item in p1["items"]}
        p2_refs = {item["reference_id"] for item in p2["items"]}
        self.assertTrue(p1_refs.isdisjoint(p2_refs))

    # 6. User isolation (Tenant A does not see Tenant B's cases)
    def test_06_user_isolation(self):
        headers_a = self.register_and_get_headers("isolated_a@example.com")
        headers_b = self.register_and_get_headers("isolated_b@example.com")

        # User A creates 2 cases
        ref_a1 = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers_a).json()["reference_id"]
        ref_a2 = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers_a).json()["reference_id"]

        # User B creates 1 case
        ref_b1 = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers_b).json()["reference_id"]

        # User A history
        hist_a = self.client.get("/api/v1/complaint/cases/my", headers=headers_a).json()
        self.assertEqual(hist_a["total"], 2)
        refs_a = [i["reference_id"] for i in hist_a["items"]]
        self.assertIn(ref_a1, refs_a)
        self.assertIn(ref_a2, refs_a)
        self.assertNotIn(ref_b1, refs_a)

        # User B history
        hist_b = self.client.get("/api/v1/complaint/cases/my", headers=headers_b).json()
        self.assertEqual(hist_b["total"], 1)
        refs_b = [i["reference_id"] for i in hist_b["items"]]
        self.assertIn(ref_b1, refs_b)
        self.assertNotIn(ref_a1, refs_b)

    # 7. Detail access for the authenticated owner
    def test_07_detail_access(self):
        headers = self.register_and_get_headers("detail_owner@example.com")
        created = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers).json()
        ref_id = created["reference_id"]

        detail_res = self.client.get(f"/api/v1/complaint/cases/{ref_id}", headers=headers)
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.json()
        self.assertEqual(detail["reference_id"], ref_id)
        self.assertEqual(detail["complaint"]["title"], BASE_CASE_PAYLOAD["complaint"]["title"])
        self.assertEqual(detail["complaint"]["description"], BASE_CASE_PAYLOAD["complaint"]["description"])

    # 8. Unknown reference returns 404
    def test_08_unknown_reference(self):
        headers = self.register_and_get_headers("unknown_tester@example.com")
        res = self.client.get("/api/v1/complaint/cases/CVKI-20261011-999999", headers=headers)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "CVKI case was not found.")

    # 9. Unauthorized history request returns 401
    def test_09_unauthorized_history_request(self):
        res = self.client.get("/api/v1/complaint/cases/my")
        self.assertEqual(res.status_code, 401)

    # 10. Database unavailable behavior returns 503
    def test_10_database_unavailable_behavior(self):
        headers = self.register_and_get_headers("db_down_tester@example.com")
        with patch("app.services.complaint_case.get_database", return_value=None):
            res = self.client.get("/api/v1/complaint/cases/my", headers=headers)
            self.assertEqual(res.status_code, 503)
            self.assertIn("Database service is unavailable", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
