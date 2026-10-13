from datetime import datetime, timezone
import unittest
import uuid

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, NOTIFICATIONS_COLLECTION, USERS_COLLECTION
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DB_NAME = "cvki_test_case_status_workflow_m4_5"


def _build_test_case(ref_id: str, status: str = "submitted_to_cvki", assigned_to: str = None):
    now = datetime.now(timezone.utc)
    assignment = {
        "assigned_to_user_id": assigned_to,
        "assigned_to_role": "authority" if assigned_to else None,
        "assigned_to_email": "officer1@bbmp.gov.in" if assigned_to else None,
        "assigned_by_user_id": "usr_admin_123" if assigned_to else None,
        "assigned_at": now if assigned_to else None,
        "assignment_status": "assigned" if assigned_to else "unassigned",
    }

    return {
        "reference_id": ref_id,
        "user_id": "usr_citizen_456",
        "created_at": now,
        "updated_at": now,
        "status": status,
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
            "title": f"Workflow Case {ref_id}",
            "description": "Hazardous uncovered drainage.",
        },
        "evidence": ["frame1.jpg"],
        "authority": {
            "name": "Bruhat Bengaluru Mahanagara Palike",
            "department": "Stormwater Drains",
            "portal_url": "https://bbmp.gov.in",
            "authority_status": "verified",
        },
        "follow_up": {
            "guidance": "Notice issued.",
            "external_submission_status": "not_submitted",
        },
        "priority_analysis": {
            "priority_level": "P1",
            "priority_score": 90,
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


class TestCaseStatusWorkflowM45(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB is unavailable for Status Workflow test suite.")

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

    # --- Test 1: Admin transitions submitted_to_cvki -> assigned ---
    def test_01_admin_transition_submitted_to_assigned(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="submitted_to_cvki"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "assigned", "reason": "Dispatching to ward"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["reference_id"], ref_id)
        self.assertEqual(data["previous_status"], "submitted_to_cvki")
        self.assertEqual(data["new_status"], "assigned")
        self.assertEqual(data["actor_role"], "admin")

    # --- Test 2: Admin transitions assigned -> in_progress ---
    def test_02_admin_transition_assigned_to_in_progress(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="assigned"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "in_progress")

    # --- Test 3: Admin transitions in_progress -> resolved ---
    def test_03_admin_transition_in_progress_to_resolved(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="in_progress"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "resolved", "reason": "Repairs verified"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "resolved")

    # --- Test 4: Admin transitions resolved -> closed ---
    def test_04_admin_transition_resolved_to_closed(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="resolved"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "closed"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "closed")

    # --- Test 5: Closed case is immutable (cannot transition) ---
    def test_05_closed_case_protection_blocks_transition(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="closed"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("closed", resp.json()["detail"].lower())

    # --- Test 6: Illegal skip transition rejected (submitted -> resolved directly) ---
    def test_06_illegal_transition_rejected(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="submitted_to_cvki"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "resolved"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("illegal status transition", resp.json()["detail"].lower())

    # --- Test 7: Citizen cannot modify case status (403) ---
    def test_07_citizen_cannot_modify_status(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="submitted_to_cvki"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("citizens cannot modify", resp.json()["detail"].lower())

    # --- Test 8: Authority can transition assigned -> in_progress on own assigned case ---
    def test_08_authority_can_transition_assigned_to_in_progress(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="assigned", assigned_to=self.authority_id_1))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.authority_token_1}"},
            json={"status": "in_progress", "reason": "Crew deployed on site"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["new_status"], "in_progress")
        self.assertEqual(data["actor_role"], "authority")

    # --- Test 9: Authority can transition in_progress -> resolved on own assigned case ---
    def test_09_authority_can_transition_in_progress_to_resolved(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="in_progress", assigned_to=self.authority_id_1))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.authority_token_1}"},
            json={"status": "resolved", "reason": "Drain cover reinstalled"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "resolved")

    # --- Test 10: Authority cannot transition unassigned case ---
    def test_10_authority_cannot_modify_unassigned_case(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="assigned", assigned_to=None))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.authority_token_1}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("authorities can only transition cases assigned to them", resp.json()["detail"].lower())

    # --- Test 11: Authority cannot modify case assigned to different authority ---
    def test_11_authority_cannot_modify_other_authority_case(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="assigned", assigned_to=self.authority_id_1))

        # Authority 2 attempts to modify Authority 1's case
        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.authority_token_2}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("assigned to them", resp.json()["detail"].lower())

    # --- Test 12: Authority cannot close case (resolved -> closed is admin only) ---
    def test_12_authority_cannot_close_case(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="resolved", assigned_to=self.authority_id_1))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.authority_token_1}"},
            json={"status": "closed"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("not permitted", resp.json()["detail"].lower())

    # --- Test 13: Admin endpoint /admin/cases/{ref}/status works identically ---
    def test_13_admin_dedicated_status_endpoint(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="submitted_to_cvki"))

        resp = self.client.patch(
            f"/api/v1/admin/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "under_review", "reason": "Administrative pre-check"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "under_review")

    # --- Test 14: Non-admin rejected from /admin/cases/{ref}/status ---
    def test_14_non_admin_forbidden_on_admin_status_endpoint(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="submitted_to_cvki"))

        resp = self.client.patch(
            f"/api/v1/admin/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.authority_token_1}"},
            json={"status": "under_review"},
        )
        self.assertEqual(resp.status_code, 403)

    # --- Test 15: Invalid status enum value rejected (422) ---
    def test_15_invalid_status_value_rejected(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="submitted_to_cvki"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "teleported_to_moon"},
        )
        self.assertIn(resp.status_code, (400, 422))

    # --- Test 16: Nonexistent case reference rejected (404) ---
    def test_16_nonexistent_case_rejected(self):
        resp = self.client.patch(
            "/api/v1/complaint/cases/CVKI-FAKE-9999/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 404)

    # --- Test 17: Unauthenticated request rejected (401) ---
    def test_17_unauthenticated_request_rejected(self):
        resp = self.client.patch(
            "/api/v1/complaint/cases/CVKI-1234/status",
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 401)

    # --- Test 18: Notification created for citizen on status transition ---
    def test_18_notification_generated_for_citizen(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="submitted_to_cvki"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "assigned"},
        )
        self.assertEqual(resp.status_code, 200)

        # Check notification was created for usr_citizen_456
        notif = self.notifs_col.find_one({"reference_id": ref_id, "user_id": "usr_citizen_456"})
        self.assertIsNotNone(notif)
        self.assertEqual(notif["type"], "case_status_changed")

    # --- Test 19: Notification created for assigned authority when admin updates status ---
    def test_19_notification_generated_for_authority(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="assigned", assigned_to=self.authority_id_1))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 200)

        notif = self.notifs_col.find_one({"reference_id": ref_id, "user_id": self.authority_id_1})
        self.assertIsNotNone(notif)
        self.assertEqual(notif["type"], "case_status_changed")

    # --- Test 20: Database atomic update persists new status and updated_at ---
    def test_20_database_atomic_update_persists(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="assigned"))

        self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "in_progress"},
        )

        doc = self.cases_col.find_one({"reference_id": ref_id})
        self.assertEqual(doc["status"], "in_progress")
        self.assertIsNotNone(doc["updated_at"])

    # --- Test 21: Reopening resolved case back to in_progress is permitted for admin ---
    def test_21_reopen_resolved_case_permitted(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="resolved"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "in_progress", "reason": "Issue recurred after rain"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "in_progress")

    # --- Test 22: No-op transition (same status) rejected as illegal transition ---
    def test_22_noop_transition_rejected(self):
        ref_id = f"CVKI-STAT-{uuid.uuid4().hex[:6].upper()}"
        self.cases_col.insert_one(_build_test_case(ref_id, status="in_progress"))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 400)
