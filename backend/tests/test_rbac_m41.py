from datetime import datetime, timedelta, timezone
import unittest
import uuid

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, NOTIFICATIONS_COLLECTION, USERS_COLLECTION
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.roles import UserRole, validate_role
from app.services.user import create_privileged_user

TEST_DB_NAME = "cvki_test_rbac_m4_1"

BASE_CASE_PAYLOAD = {
    "issue": {
        "class_name": "open_damaged_manhole",
        "label": "Open/Damaged Manhole",
        "severity": "high",
        "confidence": 0.88,
    },
    "location": {
        "road": "MG Road",
        "city": "Bengaluru",
    },
    "complaint": {
        "language": "en",
        "title": "Hazardous open manhole",
        "description": "Deep open manhole posing danger to pedestrians.",
    },
    "evidence": ["Test evidence frame"],
}


class TestRBACM41(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB is unavailable for RBAC test suite.")

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
        self.client.cookies.clear()
        self.users_col.delete_many({})
        self.cases_col.delete_many({})
        self.notifs_col.delete_many({})

    # Helper: insert user directly into MongoDB
    def _insert_user(self, email: str, password: str = "Password123!", role: str = None, is_active: bool = True) -> str:
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        doc = {
            "user_id": user_id,
            "email": email.strip().lower(),
            "password_hash": hash_password(password),
            "created_at": now,
            "updated_at": now,
            "is_active": is_active,
        }
        if role is not None:
            doc["role"] = role
        self.users_col.insert_one(doc)
        return user_id

    # 1. default role for new citizen
    def test_01_default_role_for_new_citizen(self):
        res = self.client.post(
            "/api/v1/auth/register",
            json={"email": "new_citizen@example.com", "password": "CitizenSecure2026!"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["user"]["role"], "citizen")

        # Verify role in MongoDB
        doc = self.users_col.find_one({"email": "new_citizen@example.com"})
        self.assertIsNotNone(doc)
        self.assertEqual(doc.get("role"), "citizen")

    # 2. existing user without role behaves as citizen
    def test_02_existing_user_without_role_behaves_as_citizen(self):
        # Insert legacy user record lacking 'role' field
        user_id = self._insert_user("legacy_user@example.com", "LegacyPass123!", role=None)

        # 1) Verify login returns defaulted citizen role
        login_res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "legacy_user@example.com", "password": "LegacyPass123!"},
        )
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.json()["user"]["role"], "citizen")

        token = login_res.cookies.get(settings.AUTH_COOKIE_NAME)

        # 2) Verify /me returns citizen role
        me_res = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["role"], "citizen")

        # 3) Verify legacy user is blocked from admin endpoint (behaves strictly as citizen)
        admin_res = self.client.get("/api/v1/admin/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(admin_res.status_code, 403)

    # 3. invalid role rejected
    def test_03_invalid_role_rejected(self):
        for bad_role in ["superman", "hacker", "root", "moderator", "", " "]:
            with self.assertRaises(ValueError):
                validate_role(bad_role)

        # Attempt registration with invalid role in payload should fail with 422
        res = self.client.post(
            "/api/v1/auth/register",
            json={"email": "bad_role@example.com", "password": "Password123!", "role": "invalid_superadmin"},
        )
        self.assertEqual(res.status_code, 422)

    # 4. citizen login returns citizen role
    def test_04_citizen_login_returns_citizen_role(self):
        self._insert_user("regular_citizen@example.com", "CitizenPass2026!", role="citizen")
        res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "regular_citizen@example.com", "password": "CitizenPass2026!"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["user"]["role"], "citizen")

    # 5. admin login returns admin role
    def test_05_admin_login_returns_admin_role(self):
        self._insert_user("sys_admin@cvki.gov.in", "AdminPass2026!", role="admin")
        res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "sys_admin@cvki.gov.in", "password": "AdminPass2026!"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["user"]["role"], "admin")

    # 6. authority login returns authority role
    def test_06_authority_login_returns_authority_role(self):
        self._insert_user("field_officer@bbmp.gov.in", "OfficerPass2026!", role="authority")
        res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "field_officer@bbmp.gov.in", "password": "OfficerPass2026!"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["user"]["role"], "authority")

    # 7. unauthenticated admin endpoint → 401
    def test_07_unauthenticated_admin_endpoint_returns_401(self):
        res = self.client.get("/api/v1/admin/access-check")
        self.assertEqual(res.status_code, 401)
        self.assertIn("detail", res.json())

    # 8. citizen admin endpoint → 403
    def test_08_citizen_admin_endpoint_returns_403(self):
        uid = self._insert_user("citizen_forbidden@example.com", "Citizen123!", role="citizen")
        token = create_access_token(uid, "citizen_forbidden@example.com", role="citizen")
        res = self.client.get("/api/v1/admin/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Insufficient permissions", res.json()["detail"])

    # 9. authority admin endpoint → 403
    def test_09_authority_admin_endpoint_returns_403(self):
        uid = self._insert_user("authority_forbidden@example.com", "Auth123!", role="authority")
        token = create_access_token(uid, "authority_forbidden@example.com", role="authority")
        res = self.client.get("/api/v1/admin/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Insufficient permissions", res.json()["detail"])

    # 10. admin admin endpoint → 200
    def test_10_admin_admin_endpoint_returns_200(self):
        uid = self._insert_user("valid_admin@cvki.gov.in", "AdminPass123!", role="admin")
        token = create_access_token(uid, "valid_admin@cvki.gov.in", role="admin")
        res = self.client.get("/api/v1/admin/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data, {"authorized": True, "role": "admin"})

    # 11. unauthenticated authority endpoint → 401
    def test_11_unauthenticated_authority_endpoint_returns_401(self):
        res = self.client.get("/api/v1/authority/access-check")
        self.assertEqual(res.status_code, 401)
        self.assertIn("detail", res.json())

    # 12. citizen authority endpoint → 403
    def test_12_citizen_authority_endpoint_returns_403(self):
        uid = self._insert_user("citizen_auth_forbidden@example.com", "Citizen123!", role="citizen")
        token = create_access_token(uid, "citizen_auth_forbidden@example.com", role="citizen")
        res = self.client.get("/api/v1/authority/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Insufficient permissions", res.json()["detail"])

    # 13. admin authority endpoint → 403 (Explicit separate operational role policy)
    def test_13_admin_authority_endpoint_returns_403(self):
        uid = self._insert_user("admin_auth_forbidden@cvki.gov.in", "Admin123!", role="admin")
        token = create_access_token(uid, "admin_auth_forbidden@cvki.gov.in", role="admin")
        res = self.client.get("/api/v1/authority/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Insufficient permissions", res.json()["detail"])

    # 14. authority authority endpoint → 200
    def test_14_authority_authority_endpoint_returns_200(self):
        uid = self._insert_user("valid_authority@bbmp.gov.in", "AuthorityPass123!", role="authority")
        token = create_access_token(uid, "valid_authority@bbmp.gov.in", role="authority")
        res = self.client.get("/api/v1/authority/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data, {"authorized": True, "role": "authority"})

    # 15. frontend role is not trusted for backend authorization
    def test_15_frontend_role_not_trusted(self):
        uid = self._insert_user("sneaky_citizen@example.com", "Password123!", role="citizen")
        token = create_access_token(uid, "sneaky_citizen@example.com", role="citizen")

        # Attacker sends role="admin" in custom header, query param, and cookie
        res = self.client.get(
            "/api/v1/admin/access-check?role=admin",
            headers={
                "Authorization": f"Bearer {token}",
                "X-User-Role": "admin",
                "role": "admin",
            },
        )
        self.assertEqual(res.status_code, 403)

    # 16. citizen cannot self-register as admin
    def test_16_citizen_cannot_self_register_as_admin(self):
        res = self.client.post(
            "/api/v1/auth/register",
            json={"email": "attacker_admin@example.com", "password": "Password123!", "role": "admin"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        # Even if 'role': 'admin' was supplied, self-registration strictly assigns citizen
        self.assertEqual(data["user"]["role"], "citizen")

        # Verify DB document
        doc = self.users_col.find_one({"email": "attacker_admin@example.com"})
        self.assertEqual(doc["role"], "citizen")

        # Verify that using issued token cannot access admin endpoint
        token = res.cookies.get(settings.AUTH_COOKIE_NAME)
        admin_res = self.client.get("/api/v1/admin/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(admin_res.status_code, 403)

    # 17. citizen cannot self-register as authority
    def test_17_citizen_cannot_self_register_as_authority(self):
        res = self.client.post(
            "/api/v1/auth/register",
            json={"email": "attacker_authority@example.com", "password": "Password123!", "role": "authority"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        # Even if 'role': 'authority' was supplied, self-registration strictly assigns citizen
        self.assertEqual(data["user"]["role"], "citizen")

        # Verify DB document
        doc = self.users_col.find_one({"email": "attacker_authority@example.com"})
        self.assertEqual(doc["role"], "citizen")

        # Verify that using issued token cannot access authority endpoint
        token = res.cookies.get(settings.AUTH_COOKIE_NAME)
        auth_res = self.client.get("/api/v1/authority/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(auth_res.status_code, 403)

    # 18. existing complaint ownership remains protected
    def test_18_complaint_ownership_remains_protected(self):
        # Citizen A creates a case
        user_a = self._insert_user("user_a@example.com", "Password123!", role="citizen")
        token_a = create_access_token(user_a, "user_a@example.com", role="citizen")

        case_res = self.client.post(
            "/api/v1/complaint/cases",
            json=BASE_CASE_PAYLOAD,
            headers={"Authorization": f"Bearer {token_a}"},
        )
        self.assertEqual(case_res.status_code, 200)
        ref_id = case_res.json()["reference_id"]

        # Citizen B attempts to access Citizen A's case
        user_b = self._insert_user("user_b@example.com", "Password123!", role="citizen")
        token_b = create_access_token(user_b, "user_b@example.com", role="citizen")

        b_access = self.client.get(
            f"/api/v1/complaint/cases/{ref_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(b_access.status_code, 404)

        # Citizen B attempts to check status of Citizen A's case
        b_status = self.client.get(
            f"/api/v1/complaint/cases/{ref_id}/status",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(b_status.status_code, 404)

    # 19. existing notification ownership remains protected
    def test_19_notification_ownership_remains_protected(self):
        user_a = self._insert_user("notif_owner@example.com", "Password123!", role="citizen")
        token_a = create_access_token(user_a, "notif_owner@example.com", role="citizen")

        # Insert a notification owned by User A
        notif_id = f"notif_{uuid.uuid4().hex[:12]}"
        self.notifs_col.insert_one({
            "notification_id": notif_id,
            "user_id": user_a,
            "type": "case_created",
            "title": "Case Created",
            "message": "Your case was created.",
            "read": False,
            "created_at": datetime.now(timezone.utc),
        })

        # User B attempts to mark User A's notification as read
        user_b = self._insert_user("intruder@example.com", "Password123!", role="citizen")
        token_b = create_access_token(user_b, "intruder@example.com", role="citizen")

        intrude_res = self.client.post(
            f"/api/v1/notifications/{notif_id}/read",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(intrude_res.status_code, 403)

    # 20. malformed authentication/role input handled safely
    def test_20_malformed_auth_input_handled_safely(self):
        # Invalid / corrupt bearer token
        corrupt_res = self.client.get(
            "/api/v1/admin/access-check",
            headers={"Authorization": "Bearer not.a.valid.jwt.token"},
        )
        self.assertEqual(corrupt_res.status_code, 401)

        # Non-Bearer auth header format
        bad_scheme = self.client.get(
            "/api/v1/admin/access-check",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        self.assertEqual(bad_scheme.status_code, 401)

        # Empty Authorization header
        empty_auth = self.client.get(
            "/api/v1/admin/access-check",
            headers={"Authorization": ""},
        )
        self.assertEqual(empty_auth.status_code, 401)

        # Missing payload fields in register
        bad_payload = self.client.post(
            "/api/v1/auth/register",
            json={"not_email": "bad"},
        )
        self.assertEqual(bad_payload.status_code, 422)

    # 21. JWT role claim matches database canonical role
    def test_21_jwt_token_role_claim(self):
        uid = self._insert_user("token_claim@example.com", "Pass123!", role="admin")
        token = create_access_token(uid, "token_claim@example.com", role="admin")
        import jwt
        decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        self.assertEqual(decoded["role"], "admin")
        self.assertEqual(decoded["sub"], uid)

    # 22. Inactive account blocked even with valid token
    def test_22_inactive_account_blocked(self):
        uid = self._insert_user("inactive_admin@cvki.gov.in", "Pass123!", role="admin", is_active=False)
        token = create_access_token(uid, "inactive_admin@cvki.gov.in", role="admin")
        res = self.client.get("/api/v1/admin/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("inactive", res.json()["detail"].lower())

    # 23. Password hashes and secrets not leaked in auth or RBAC endpoints
    def test_23_no_sensitive_secrets_leaked(self):
        self._insert_user("secret_check@example.com", "SecretPass123!", role="admin")
        login_res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "secret_check@example.com", "password": "SecretPass123!"},
        )
        self.assertNotIn("password_hash", login_res.text)
        self.assertNotIn("SecretPass123!", login_res.text)
        self.assertNotIn(settings.JWT_SECRET, login_res.text)

        token = login_res.cookies.get(settings.AUTH_COOKIE_NAME)
        check_res = self.client.get("/api/v1/admin/access-check", headers={"Authorization": f"Bearer {token}"})
        self.assertNotIn("password", check_res.text)
        self.assertNotIn(settings.JWT_SECRET, check_res.text)
