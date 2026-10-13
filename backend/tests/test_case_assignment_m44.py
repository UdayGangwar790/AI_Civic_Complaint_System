from datetime import datetime, timezone
import unittest
import uuid

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, NOTIFICATIONS_COLLECTION, USERS_COLLECTION
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DB_NAME = "cvki_test_case_assignment_m4_4"


def _build_test_case(ref_id: str, assigned_to: str = None):
    now = datetime.now(timezone.utc)
    if assigned_to:
        assignment = {
            "assigned_to_user_id": assigned_to,
            "assigned_to_role": "authority",
            "assigned_by_user_id": "usr_admin_123",
            "assigned_at": now,
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
        "user_id": "usr_citizen_456",
        "created_at": now,
        "updated_at": now,
        "status": "submitted_to_cvki",
        "issue": {
            "class_name": "open_damaged_manhole",
            "label": "Open Damaged Manhole",
            "severity": "high",
            "confidence": 0.94,
        },
        "location": {
            "road": "Brigade Road",
            "city": "Bengaluru",
            "pincode": "560025",
        },
        "complaint": {
            "language": "en",
            "title": f"Assignment Test Case {ref_id}",
            "description": "Uncovered drain dangerous to pedestrians.",
        },
        "evidence": ["frame_drain.jpg"],
        "authority": {
            "name": "Bruhat Bengaluru Mahanagara Palike",
            "department": "Stormwater Drains",
            "portal_url": "https://bbmp.gov.in",
            "authority_status": "verified",
        },
        "follow_up": {
            "guidance": "Forwarded to ward engineer.",
            "external_submission_status": "not_submitted",
        },
        "priority_analysis": {
            "priority_level": "P1",
            "priority_score": 92,
            "risk_level": "Critical",
            "risk_factors": ["High pedestrian volume"],
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


class TestCaseAssignmentM44(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB is unavailable for Case Assignment test suite.")

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
        self.authority_id_1 = self._insert_user("officer1@bbmp.gov.in", role="authority")
        self.authority_id_2 = self._insert_user("officer2@bbmp.gov.in", role="authority")

        self.admin_token = create_access_token(self.admin_id, role="admin", email="admin@cvki.gov.in")
        self.citizen_token = create_access_token(self.citizen_id, role="citizen", email="citizen@cvki.gov.in")
        self.authority_token_1 = create_access_token(self.authority_id_1, role="authority", email="officer1@bbmp.gov.in")

    def _insert_user(self, email: str, role: str = "citizen", is_active: bool = True) -> str:
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        self.users_col.insert_one({
            "user_id": user_id,
            "email": email.strip().lower(),
            "password_hash": hash_password("SecurePassword2026!"),
            "role": role,
            "created_at": now,
            "updated_at": now,
            "is_active": is_active,
        })
        return user_id

    # 1. Assign case successfully
    def test_01_assign_case(self):
        case = _build_test_case("CVKI-ASSIGN-001")
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-ASSIGN-001/assign",
            json={"assigned_to_user_id": self.authority_id_1},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["assignment"]["assignment_status"], "assigned")
        self.assertEqual(data["assignment"]["assigned_to_user_id"], self.authority_id_1)
        self.assertEqual(data["assignment"]["assigned_by_user_id"], self.admin_id)

    # 2. Assign only allowed by admin
    def test_02_assign_only_by_admin(self):
        case = _build_test_case("CVKI-ASSIGN-002")
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-ASSIGN-002/assign",
            json={"assigned_to_user_id": self.authority_id_1},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)

    # 3. Citizen cannot assign
    def test_03_citizen_cannot_assign(self):
        case = _build_test_case("CVKI-ASSIGN-003")
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-ASSIGN-003/assign",
            json={"assigned_to_user_id": self.authority_id_1},
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(res.status_code, 403)

    # 4. Authority cannot assign
    def test_04_authority_cannot_assign(self):
        case = _build_test_case("CVKI-ASSIGN-004")
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-ASSIGN-004/assign",
            json={"assigned_to_user_id": self.authority_id_2},
            headers={"Authorization": f"Bearer {self.authority_token_1}"},
        )
        self.assertEqual(res.status_code, 403)

    # 5. Unauthenticated cannot assign
    def test_05_unauthenticated_cannot_assign(self):
        res = self.client.post(
            "/api/v1/admin/cases/CVKI-ASSIGN-005/assign",
            json={"assigned_to_user_id": self.authority_id_1},
        )
        self.assertEqual(res.status_code, 401)

    # 6. Target user must exist
    def test_06_target_user_must_exist(self):
        case = _build_test_case("CVKI-ASSIGN-006")
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-ASSIGN-006/assign",
            json={"assigned_to_user_id": "usr_nonexistent_999"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("does not exist", res.json()["detail"].lower())

    # 7. Target user must have role=authority
    def test_07_target_user_must_be_authority(self):
        case = _build_test_case("CVKI-ASSIGN-007")
        self.cases_col.insert_one(case)

        # Attempt to assign to another admin
        other_admin_id = self._insert_user("second_admin@cvki.gov.in", role="admin")
        res = self.client.post(
            "/api/v1/admin/cases/CVKI-ASSIGN-007/assign",
            json={"assigned_to_user_id": other_admin_id},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("authority", res.json()["detail"].lower())

    # 8. Citizen target rejected
    def test_08_citizen_target_rejected(self):
        case = _build_test_case("CVKI-ASSIGN-008")
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-ASSIGN-008/assign",
            json={"assigned_to_user_id": self.citizen_id},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("authority", res.json()["detail"].lower())

    # 9. Unassign case
    def test_09_unassign(self):
        case = _build_test_case("CVKI-UNASSIGN-009", assigned_to=self.authority_id_1)
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-UNASSIGN-009/unassign",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["assignment"]["assignment_status"], "unassigned")
        self.assertIsNone(data["assignment"]["assigned_to_user_id"])

        # Check DB reflects change
        db_doc = self.cases_col.find_one({"reference_id": "CVKI-UNASSIGN-009"})
        self.assertEqual(db_doc["assignment"]["assignment_status"], "unassigned")
        self.assertIsNone(db_doc["assignment"]["assigned_to_user_id"])

    # 10. Reassignment updates safely
    def test_10_reassignment(self):
        case = _build_test_case("CVKI-REASSIGN-010", assigned_to=self.authority_id_1)
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-REASSIGN-010/assign",
            json={"assigned_to_user_id": self.authority_id_2},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["assignment"]["assigned_to_user_id"], self.authority_id_2)

        # Check in DB
        db_doc = self.cases_col.find_one({"reference_id": "CVKI-REASSIGN-010"})
        self.assertEqual(db_doc["assignment"]["assigned_to_user_id"], self.authority_id_2)

    # 11. Assignment persistence in MongoDB
    def test_11_assignment_persistence(self):
        case = _build_test_case("CVKI-PERSIST-011")
        self.cases_col.insert_one(case)

        self.client.post(
            "/api/v1/admin/cases/CVKI-PERSIST-011/assign",
            json={"assigned_to_user_id": self.authority_id_1},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )

        db_doc = self.cases_col.find_one({"reference_id": "CVKI-PERSIST-011"})
        self.assertIsNotNone(db_doc)
        self.assertEqual(db_doc["assignment"]["assignment_status"], "assigned")
        self.assertEqual(db_doc["assignment"]["assigned_to_user_id"], self.authority_id_1)
        self.assertEqual(db_doc["assignment"]["assigned_by_user_id"], self.admin_id)

    # 12. Authority list endpoint
    def test_12_authority_list(self):
        res = self.client.get(
            "/api/v1/admin/authorities",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        authorities = res.json()
        self.assertGreaterEqual(len(authorities), 2)
        u_ids = [a["user_id"] for a in authorities]
        self.assertIn(self.authority_id_1, u_ids)
        self.assertIn(self.authority_id_2, u_ids)
        self.assertNotIn(self.citizen_id, u_ids)
        self.assertNotIn(self.admin_id, u_ids)

        # Verify no credentials leaked
        text = res.text
        self.assertNotIn("password_hash", text)
        self.assertNotIn("access_token", text)

    def test_authority_list_is_paged_and_bounded(self):
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        first_page = self.client.get(
            "/api/v1/admin/authorities?page=1&page_size=1",
            headers=headers,
        )
        second_page = self.client.get(
            "/api/v1/admin/authorities?page=2&page_size=1",
            headers=headers,
        )
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(first_page.json()), 1)
        self.assertEqual(len(second_page.json()), 1)
        self.assertNotEqual(first_page.json()[0]["user_id"], second_page.json()[0]["user_id"])

        oversized_page = self.client.get(
            "/api/v1/admin/authorities?page_size=201",
            headers=headers,
        )
        self.assertEqual(oversized_page.status_code, 422)

    # 13. Assignment creates notification in M3.9 system
    def test_13_assignment_notification(self):
        case = _build_test_case("CVKI-NOTIF-013")
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-NOTIF-013/assign",
            json={"assigned_to_user_id": self.authority_id_1},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 200)

        # Query notifications for authority 1
        notifs = list(self.notifs_col.find({"user_id": self.authority_id_1}))
        self.assertGreaterEqual(len(notifs), 1)
        self.assertEqual(notifs[0]["type"], "case_assigned")
        self.assertIn("CVKI-NOTIF-013", notifs[0]["title"])

    # 14. Failed assignment creates no notification
    def test_14_failed_assignment_creates_no_notification(self):
        notifs_before = self.notifs_col.count_documents({})
        res = self.client.post(
            "/api/v1/admin/cases/CVKI-NONEXISTENT/assign",
            json={"assigned_to_user_id": self.authority_id_1},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 404)
        notifs_after = self.notifs_col.count_documents({})
        self.assertEqual(notifs_before, notifs_after)

    # 15. Nonexistent case returns 404
    def test_15_nonexistent_case(self):
        res = self.client.post(
            "/api/v1/admin/cases/CVKI-MISSING-404/assign",
            json={"assigned_to_user_id": self.authority_id_1},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 404)

        res_un = self.client.post(
            "/api/v1/admin/cases/CVKI-MISSING-404/unassign",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_un.status_code, 404)

    # 16. Inactive authority rejected
    def test_16_inactive_authority_rejected(self):
        inactive_auth_id = self._insert_user("inactive@bbmp.gov.in", role="authority", is_active=False)
        case = _build_test_case("CVKI-INACTIVE-016")
        self.cases_col.insert_one(case)

        res = self.client.post(
            "/api/v1/admin/cases/CVKI-INACTIVE-016/assign",
            json={"assigned_to_user_id": inactive_auth_id},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("inactive", res.json()["detail"].lower())

    # 17. Malformed request handled safely
    def test_17_malformed_request(self):
        case = _build_test_case("CVKI-MALFORMED-017")
        self.cases_col.insert_one(case)

        res_empty = self.client.post(
            "/api/v1/admin/cases/CVKI-MALFORMED-017/assign",
            json={},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_empty.status_code, 422)

        res_blank_user = self.client.post(
            "/api/v1/admin/cases/CVKI-MALFORMED-017/assign",
            json={"assigned_to_user_id": "   "},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_blank_user.status_code, 400)


if __name__ == "__main__":
    unittest.main()
