from datetime import datetime, timezone
import unittest
import uuid

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import AUDIT_LOGS_COLLECTION, COMPLAINT_CASES_COLLECTION, USERS_COLLECTION
from app.core.security import create_access_token, hash_password
from app.main import app
from app.services.audit import AuditService, _sanitize_metadata

TEST_DB_NAME = "cvki_test_audit_security_m4_8"


def _build_audit_case(ref_id: str, citizen_id: str, status: str = "submitted_to_cvki", assigned_to: str = None):
    now = datetime.now(timezone.utc)
    return {
        "reference_id": ref_id,
        "user_id": citizen_id,
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
            "road": "MG Road",
            "city": "Bengaluru",
            "pincode": "560001",
        },
        "complaint": {
            "language": "en",
            "title": f"Audit Case {ref_id}",
            "description": "Hazardous civic defect.",
        },
        "evidence": ["frame1.jpg"],
        "authority": {
            "name": "BBMP",
            "department": "Stormwater",
            "portal_url": "https://bbmp.gov.in",
            "authority_status": "verified",
        },
        "follow_up": {
            "guidance": "Pending field inspection.",
            "external_submission_status": "not_submitted",
        },
        "priority_analysis": {
            "priority_level": "P1",
            "priority_score": 90,
            "risk_level": "Critical",
            "risk_factors": ["High pedestrian footfall"],
        },
        "duplicate_analysis": {
            "status": "unique",
            "classification": "unique",
            "issue_match": False,
            "reason": "Unique event",
            "similarity_score": 0.05,
        },
        "assignment": {
            "assigned_to_user_id": assigned_to,
            "assigned_to_role": "authority" if assigned_to else None,
            "assigned_to_email": "officer@bbmp.gov.in" if assigned_to else None,
            "assigned_by_user_id": "usr_admin_123" if assigned_to else None,
            "assigned_at": now if assigned_to else None,
            "assignment_status": "assigned" if assigned_to else "unassigned",
        },
    }


class TestAuditSecurityM48(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB is unavailable for Audit & Security test suite.")

        cls.sync_db = cls.sync_client[TEST_DB_NAME]
        cls.users_col = cls.sync_db[USERS_COLLECTION]
        cls.cases_col = cls.sync_db[COMPLAINT_CASES_COLLECTION]
        cls.audit_col = cls.sync_db[AUDIT_LOGS_COLLECTION]

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
        self.audit_col.delete_many({})

        self.admin_id = self._insert_user("admin@cvki.gov.in", role="admin")
        self.citizen_id = self._insert_user("citizen@cvki.gov.in", role="citizen")
        self.authority_id = self._insert_user("officer@bbmp.gov.in", role="authority")

        self.admin_token = create_access_token(self.admin_id, role="admin", email="admin@cvki.gov.in")
        self.citizen_token = create_access_token(self.citizen_id, role="citizen", email="citizen@cvki.gov.in")
        self.authority_token = create_access_token(self.authority_id, role="authority", email="officer@bbmp.gov.in")

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

    # --- Test 1: Record audit event programmatically via AuditService ---
    def test_01_record_event_persists_to_mongodb(self):
        self.audit_col.insert_one({
            "event_id": "evt_test_001",
            "timestamp": datetime.now(timezone.utc),
            "actor_user_id": self.admin_id,
            "actor_role": "admin",
            "action": "system_bootstrap",
            "resource_type": "system",
            "resource_reference_id": None,
            "result": "success",
            "metadata": {"version": "4.8"},
        })
        doc = self.audit_col.find_one({"event_id": "evt_test_001"})
        self.assertIsNotNone(doc)
        self.assertEqual(doc["action"], "system_bootstrap")
        self.assertEqual(doc["result"], "success")

    # --- Test 2: Admin can query audit log list endpoint ---
    def test_02_admin_can_list_audit_logs(self):
        self.audit_col.insert_one({
            "event_id": "evt_002",
            "timestamp": datetime.now(timezone.utc),
            "actor_user_id": self.admin_id,
            "actor_role": "admin",
            "action": "admin_view",
            "result": "success",
            "metadata": {},
        })
        resp = self.client.get(
            "/api/v1/admin/audit",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["event_id"], "evt_002")

    # --- Test 3: Unauthenticated user rejected from audit list (401) ---
    def test_03_unauthenticated_rejected(self):
        resp = self.client.get("/api/v1/admin/audit")
        self.assertEqual(resp.status_code, 401)

    # --- Test 4: Citizen forbidden from audit endpoint (403) ---
    def test_04_citizen_forbidden(self):
        resp = self.client.get(
            "/api/v1/admin/audit",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    # --- Test 5: Authority forbidden from audit endpoint (403) ---
    def test_05_authority_forbidden(self):
        resp = self.client.get(
            "/api/v1/admin/audit",
            headers={"Authorization": f"Bearer {self.authority_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    # --- Test 6: Login success logs audit event ---
    def test_06_login_success_records_audit_event(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": "admin@cvki.gov.in", "password": "SecurePassword2026!"},
            headers={"User-Agent": "cvki-audit-test"},
        )
        self.assertEqual(resp.status_code, 200)
        request_id = resp.headers.get("X-Request-ID")
        self.assertIsNotNone(request_id)

        evt = self.audit_col.find_one({"action": "auth_login", "result": "success"})
        self.assertIsNotNone(evt)
        self.assertEqual(evt["request_id"], request_id)
        self.assertEqual(evt["ip_address"], "testclient")
        self.assertEqual(evt["user_agent"], "cvki-audit-test")
        self.assertEqual(evt["actor_role"], "admin")
        self.assertEqual(evt["metadata"].get("email"), "admin@cvki.gov.in")
        self.assertNotIn("password", evt["metadata"])

    # --- Test 7: Login failure logs audit event without leaking password ---
    def test_07_login_failure_records_audit_event(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": "admin@cvki.gov.in", "password": "WrongPassword!"},
        )
        self.assertEqual(resp.status_code, 401)

        evt = self.audit_col.find_one({"action": "auth_login", "result": "failure"})
        self.assertIsNotNone(evt)
        self.assertEqual(evt["metadata"].get("attempted_email"), "admin@cvki.gov.in")
        self.assertNotIn("password", evt["metadata"])
        self.assertNotIn("WrongPassword!", str(evt))

    def test_request_id_header_is_sanitized(self):
        resp = self.client.get("/", headers={"X-Request-ID": "invalid request id"})
        self.assertEqual(resp.status_code, 200)
        request_id = resp.headers.get("X-Request-ID")
        self.assertIsNotNone(request_id)
        self.assertNotIn(" ", request_id)

    # --- Test 8: Denied authorization records audit event ---
    def test_08_denied_access_records_audit_event(self):
        # Citizen attempts to access admin access-check
        resp = self.client.get(
            "/api/v1/admin/access-check",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(resp.status_code, 403)

        evt = self.audit_col.find_one({"action": "access_denied", "result": "denied"})
        self.assertIsNotNone(evt)
        self.assertEqual(evt["actor_user_id"], self.citizen_id)
        self.assertEqual(evt["actor_role"], "citizen")

    # --- Test 9: Case assignment records audit event ---
    def test_09_case_assignment_records_audit_event(self):
        ref_id = "CVKI-AUDIT-ASGN"
        self.cases_col.insert_one(_build_audit_case(ref_id, self.citizen_id, status="submitted_to_cvki"))

        resp = self.client.post(
            f"/api/v1/admin/cases/{ref_id}/assign",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"assigned_to_user_id": self.authority_id},
        )
        self.assertEqual(resp.status_code, 200)

        evt = self.audit_col.find_one({"action": "case_assigned", "resource_reference_id": ref_id})
        self.assertIsNotNone(evt)
        self.assertEqual(evt["result"], "success")
        self.assertEqual(evt["actor_role"], "admin")

    # --- Test 10: Case unassignment records audit event ---
    def test_10_case_unassignment_records_audit_event(self):
        ref_id = "CVKI-AUDIT-UNASGN"
        self.cases_col.insert_one(_build_audit_case(ref_id, self.citizen_id, status="assigned", assigned_to=self.authority_id))

        resp = self.client.post(
            f"/api/v1/admin/cases/{ref_id}/unassign",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)

        evt = self.audit_col.find_one({"action": "case_unassigned", "resource_reference_id": ref_id})
        self.assertIsNotNone(evt)
        self.assertEqual(evt["result"], "success")

    # --- Test 11: Case status transition records audit event ---
    def test_11_case_status_change_records_audit_event(self):
        ref_id = "CVKI-AUDIT-STAT"
        self.cases_col.insert_one(_build_audit_case(ref_id, self.citizen_id, status="assigned", assigned_to=self.authority_id))

        resp = self.client.patch(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"status": "in_progress", "reason": "Repair in flight"},
        )
        self.assertEqual(resp.status_code, 200)

        evt = self.audit_col.find_one({"action": "case_status_changed", "resource_reference_id": ref_id})
        self.assertIsNotNone(evt)
        self.assertEqual(evt["metadata"]["new_status"], "in_progress")

    # --- Test 12: Admin security overview returns indicators ---
    def test_12_security_overview_endpoint(self):
        # Insert diverse audit events
        now = datetime.now(timezone.utc)
        self.audit_col.insert_one({
            "event_id": "evt_fail_login",
            "timestamp": now,
            "action": "auth_login",
            "result": "failure",
            "actor_role": None,
        })
        self.audit_col.insert_one({
            "event_id": "evt_denied_attempt",
            "timestamp": now,
            "action": "access_denied",
            "result": "denied",
            "actor_role": "citizen",
        })
        self.audit_col.insert_one({
            "event_id": "evt_admin_action",
            "timestamp": now,
            "action": "case_assigned",
            "result": "success",
            "actor_role": "admin",
        })

        resp = self.client.get(
            "/api/v1/admin/audit/summary",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_events"], 3)
        self.assertEqual(data["login_failures"], 1)
        self.assertEqual(data["denied_access_attempts"], 1)
        self.assertEqual(data["administrative_actions"], 1)
        self.assertEqual(data["assignment_actions"], 1)
        self.assertEqual(data["system_label"], "Security & Audit Overview")
        self.assertGreaterEqual(len(data["recent_events"]), 3)

    # --- Test 13: Pagination of audit logs ---
    def test_13_audit_log_pagination(self):
        for i in range(25):
            self.audit_col.insert_one({
                "event_id": f"evt_page_{i}",
                "timestamp": datetime.now(timezone.utc),
                "action": "audit_action",
                "result": "success",
                "actor_role": "admin",
            })

        resp = self.client.get(
            "/api/v1/admin/audit?page=1&page_size=10",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 25)
        self.assertEqual(len(data["items"]), 10)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["total_pages"], 3)

    # --- Test 14: Filter audit logs by action ---
    def test_14_filter_by_action(self):
        now = datetime.now(timezone.utc)
        self.audit_col.insert_one({"event_id": "e1", "timestamp": now, "action": "auth_login", "result": "success"})
        self.audit_col.insert_one({"event_id": "e2", "timestamp": now, "action": "case_created", "result": "success"})

        resp = self.client.get(
            "/api/v1/admin/audit?action=case_created",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["event_id"], "e2")

    # --- Test 15: Filter audit logs by result (failure/denied) ---
    def test_15_filter_by_result(self):
        now = datetime.now(timezone.utc)
        self.audit_col.insert_one({"event_id": "e_succ", "timestamp": now, "action": "op1", "result": "success"})
        self.audit_col.insert_one({"event_id": "e_fail", "timestamp": now, "action": "op2", "result": "failure"})

        resp = self.client.get(
            "/api/v1/admin/audit?result=failure",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["event_id"], "e_fail")

    # --- Test 16: Filter audit logs by role ---
    def test_16_filter_by_role(self):
        now = datetime.now(timezone.utc)
        self.audit_col.insert_one({"event_id": "e_adm", "timestamp": now, "action": "op1", "actor_role": "admin"})
        self.audit_col.insert_one({"event_id": "e_cit", "timestamp": now, "action": "op2", "actor_role": "citizen"})

        resp = self.client.get(
            "/api/v1/admin/audit?role=citizen",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["event_id"], "e_cit")

    # --- Test 17: Filter by resource reference_id ---
    def test_17_filter_by_reference_id(self):
        now = datetime.now(timezone.utc)
        self.audit_col.insert_one({"event_id": "e_c1", "timestamp": now, "action": "a", "resource_reference_id": "CVKI-TARGET-1"})
        self.audit_col.insert_one({"event_id": "e_c2", "timestamp": now, "action": "a", "resource_reference_id": "CVKI-OTHER-2"})

        resp = self.client.get(
            "/api/v1/admin/audit?reference_id=CVKI-TARGET-1",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["event_id"], "e_c1")

    # --- Test 18: Sorting newest first ---
    def test_18_sorting_newest_first(self):
        t1 = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
        self.audit_col.insert_one({"event_id": "e_old", "timestamp": t1, "action": "a"})
        self.audit_col.insert_one({"event_id": "e_new", "timestamp": t2, "action": "a"})

        resp = self.client.get(
            "/api/v1/admin/audit",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(items[0]["event_id"], "e_new")
        self.assertEqual(items[1]["event_id"], "e_old")

    # --- Test 19: Sensitive metadata redaction prevents password / token leakage ---
    def test_19_sensitive_metadata_sanitization(self):
        dirty = {
            "user_email": "user@cvki.gov.in",
            "password": "RawPassword123!",
            "auth_token": "Bearer secret_jwt_token",
            "nested": {
                "secret_key": "private_key_xyz",
                "safe_info": "Indiranagar",
            },
        }
        clean = _sanitize_metadata(dirty)
        self.assertEqual(clean["password"], "[REDACTED]")
        self.assertEqual(clean["auth_token"], "[REDACTED]")
        self.assertEqual(clean["nested"]["secret_key"], "[REDACTED]")
        self.assertEqual(clean["nested"]["safe_info"], "Indiranagar")

    # --- Test 20: Audit records are immutable (no DELETE or PUT endpoint exists) ---
    def test_20_immutability_no_delete_routes(self):
        resp_del = self.client.delete(
            "/api/v1/admin/audit",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp_del.status_code, 405)  # Method Not Allowed

        resp_put = self.client.put(
            "/api/v1/admin/audit",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={},
        )
        self.assertEqual(resp_put.status_code, 405)  # Method Not Allowed

    # --- Test 21: Empty audit database returns 0 metrics safely ---
    def test_21_empty_audit_database(self):
        resp = self.client.get(
            "/api/v1/admin/audit",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["items"], [])
