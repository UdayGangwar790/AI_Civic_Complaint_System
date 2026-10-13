from datetime import timedelta
import unittest

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import USERS_COLLECTION, COMPLAINT_CASES_COLLECTION
from app.core.security import create_access_token, verify_password
from app.main import app

TEST_DB_NAME = "cvki_test_auth_m3_2"

BASE_CASE_PAYLOAD = {
    "issue": {
        "class_name": "open_damaged_manhole",
        "label": "Open/Damaged Manhole",
        "severity": "high",
        "confidence": 0.85,
    },
    "location": {
        "road": "Test Road",
        "city": "Bengaluru",
    },
    "complaint": {
        "language": "en",
        "title": "Auth Test Manhole",
        "description": "Auth test description text.",
    },
    "evidence": ["Test evidence."],
}


class TestAuthM32(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB not available for auth tests")

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

    # 1. Registration success
    def test_01_registration_success(self):
        res = self.client.post("/api/v1/auth/register", json={"email": "citizen1@example.com", "password": "Password123!"})
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertNotIn("access_token", data)
        self.assertIn(settings.AUTH_COOKIE_NAME, res.cookies)
        self.assertIn(settings.CSRF_COOKIE_NAME, res.cookies)
        self.assertEqual(data["user"]["email"], "citizen1@example.com")
        self.assertTrue(data["user"]["user_id"].startswith("usr_"))

    # 2. Duplicate email rejection
    def test_02_duplicate_email_rejection(self):
        self.client.post("/api/v1/auth/register", json={"email": "duplicate@example.com", "password": "Password123!"})
        # Attempt with same email in different casing
        res = self.client.post("/api/v1/auth/register", json={"email": "DUPLICATE@example.com", "password": "Password123!"})
        self.assertEqual(res.status_code, 409)
        self.assertIn("already exists", res.json()["detail"])

    # 3. Invalid email rejection
    def test_03_invalid_email_rejection(self):
        for bad_email in ["notanemail", "user@", "@domain.com", "user@domain"]:
            res = self.client.post("/api/v1/auth/register", json={"email": bad_email, "password": "Password123!"})
            self.assertEqual(res.status_code, 422)

    # 4. Weak password rejection
    def test_04_weak_password_rejection(self):
        for weak_pass in ["short", "1234567", "        "]:
            res = self.client.post("/api/v1/auth/register", json={"email": "user_weak@example.com", "password": weak_pass})
            self.assertEqual(res.status_code, 422)

    # 5. Password is hashed in MongoDB
    def test_05_password_is_hashed_in_mongodb(self):
        plain = "MySecretPassword!2026"
        res = self.client.post("/api/v1/auth/register", json={"email": "hashed@example.com", "password": plain})
        self.assertEqual(res.status_code, 201)

        doc = self.users_col.find_one({"email": "hashed@example.com"})
        self.assertIsNotNone(doc)
        self.assertNotIn(plain, doc["password_hash"])
        self.assertTrue(doc["password_hash"].startswith("$2b$") or doc["password_hash"].startswith("$2a$"))
        self.assertTrue(verify_password(plain, doc["password_hash"]))

    # 6. Password hash is never returned in API responses
    def test_06_password_hash_not_returned(self):
        reg_res = self.client.post("/api/v1/auth/register", json={"email": "nohash@example.com", "password": "Password123!"})
        self.assertNotIn("password_hash", reg_res.text)
        self.assertNotIn("password", reg_res.json()["user"])

        login_res = self.client.post("/api/v1/auth/login", json={"email": "nohash@example.com", "password": "Password123!"})
        self.assertNotIn("password_hash", login_res.text)
        self.assertNotIn("password", login_res.json()["user"])

    # 7. Login success
    def test_07_login_success(self):
        self.client.post("/api/v1/auth/register", json={"email": "login_user@example.com", "password": "CorrectPassword123!"})
        login_res = self.client.post("/api/v1/auth/login", json={"email": "LOGIN_USER@example.com", "password": "CorrectPassword123!"})
        self.assertEqual(login_res.status_code, 200)
        data = login_res.json()
        self.assertNotIn("access_token", data)
        self.assertIn(settings.AUTH_COOKIE_NAME, login_res.cookies)
        self.assertEqual(data["user"]["email"], "login_user@example.com")
        auth_cookie = next(
            value for value in login_res.headers.get_list("set-cookie")
            if value.startswith(f"{settings.AUTH_COOKIE_NAME}=")
        )
        csrf_cookie = next(
            value for value in login_res.headers.get_list("set-cookie")
            if value.startswith(f"{settings.CSRF_COOKIE_NAME}=")
        )
        self.assertIn("HttpOnly", auth_cookie)
        self.assertNotIn("HttpOnly", csrf_cookie)
        self.assertIn("SameSite=lax", auth_cookie)
        if settings.auth_cookie_secure:
            self.assertIn("Secure", auth_cookie)
        else:
            self.assertNotIn("Secure", auth_cookie)

    # 8. Invalid credentials return safe error
    def test_08_invalid_credentials(self):
        self.client.post("/api/v1/auth/register", json={"email": "valid@example.com", "password": "CorrectPassword123!"})
        # Wrong password
        bad_pass = self.client.post("/api/v1/auth/login", json={"email": "valid@example.com", "password": "WrongPassword!"})
        self.assertEqual(bad_pass.status_code, 401)
        self.assertEqual(bad_pass.json()["detail"], "Invalid email or password.")

        # Nonexistent email
        bad_user = self.client.post("/api/v1/auth/login", json={"email": "nonexistent@example.com", "password": "SomePassword123!"})
        self.assertEqual(bad_user.status_code, 401)
        self.assertEqual(bad_user.json()["detail"], "Invalid email or password.")

    # 9. JWT generated with expected claims
    def test_09_jwt_generated(self):
        reg_res = self.client.post("/api/v1/auth/register", json={"email": "jwt_user@example.com", "password": "Password123!"})
        token = reg_res.cookies.get(settings.AUTH_COOKIE_NAME)
        import jwt
        decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        self.assertEqual(decoded["email"], "jwt_user@example.com")
        self.assertTrue(decoded["sub"].startswith("usr_"))
        self.assertIn("exp", decoded)

    # 10. Expired/invalid JWT returns 401
    def test_10_expired_or_invalid_jwt(self):
        # Expired token
        expired_token = create_access_token("usr_123", "test@example.com", expires_delta=timedelta(seconds=-10))
        res1 = self.client.get("/api/v1/complaint/cases/my", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res1.status_code, 401)

        # Corrupt token
        res2 = self.client.get("/api/v1/complaint/cases/my", headers={"Authorization": "Bearer corrupt.token.signature"})
        self.assertEqual(res2.status_code, 401)

    # 11. Missing Authorization header returns 401
    def test_11_missing_auth_header(self):
        res = self.client.get("/api/v1/complaint/cases/my")
        self.assertEqual(res.status_code, 401)

    def test_cookie_authentication_and_logout(self):
        self.client.post(
            "/api/v1/auth/register",
            json={"email": "cookie_user@example.com", "password": "CorrectPassword123!"},
        )
        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "cookie_user@example.com", "password": "CorrectPassword123!"},
        )
        self.assertEqual(login.status_code, 200)
        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, 200)
        csrf_token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
        logout = self.client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        self.assertEqual(logout.status_code, 204)
        cleared_auth_cookie = next(
            value for value in logout.headers.get_list("set-cookie")
            if value.startswith(f"{settings.AUTH_COOKIE_NAME}=")
        )
        self.assertIn("Max-Age=0", cleared_auth_cookie)
        after_logout = self.client.get("/api/v1/auth/me")
        self.assertEqual(after_logout.status_code, 401)

    # 12. Protected endpoint without authentication returns 401
    def test_12_protected_endpoints_require_auth(self):
        res1 = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD)
        self.assertEqual(res1.status_code, 401)

        res2 = self.client.get("/api/v1/complaint/cases/CVKI-20261011-123456")
        self.assertEqual(res2.status_code, 401)

        res3 = self.client.get("/api/v1/complaint/cases/CVKI-20261011-123456/status")
        self.assertEqual(res3.status_code, 401)

    # 13. Authenticated case creation persists user_id
    def test_13_authenticated_case_creation(self):
        reg = self.client.post("/api/v1/auth/register", json={"email": "owner@example.com", "password": "Password123!"}).json()
        token = self.client.cookies.get(settings.AUTH_COOKIE_NAME)
        user_id = reg["user"]["user_id"]

        create_res = self.client.post(
            "/api/v1/complaint/cases",
            json=BASE_CASE_PAYLOAD,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(create_res.status_code, 200)
        ref_id = create_res.json()["reference_id"]

        # Verify in MongoDB that user_id was stored
        doc = self.cases_col.find_one({"reference_id": ref_id})
        self.assertEqual(doc["user_id"], user_id)

    # 14. user_id comes strictly from JWT, not from client request body
    def test_14_user_id_comes_from_jwt_not_request_body(self):
        reg = self.client.post("/api/v1/auth/register", json={"email": "real_owner@example.com", "password": "Password123!"}).json()
        token = self.client.cookies.get(settings.AUTH_COOKIE_NAME)
        real_user_id = reg["user"]["user_id"]

        tampered_payload = dict(BASE_CASE_PAYLOAD)
        tampered_payload["user_id"] = "usr_fake_spoofed_victim_id"

        create_res = self.client.post(
            "/api/v1/complaint/cases",
            json=tampered_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(create_res.status_code, 200)
        ref_id = create_res.json()["reference_id"]

        # Database must have real user_id, NOT spoofed id
        doc = self.cases_col.find_one({"reference_id": ref_id})
        self.assertEqual(doc["user_id"], real_user_id)
        self.assertNotEqual(doc["user_id"], "usr_fake_spoofed_victim_id")

    # 15. User can retrieve own case
    def test_15_user_can_retrieve_own_case(self):
        reg = self.client.post("/api/v1/auth/register", json={"email": "own_case@example.com", "password": "Password123!"}).json()
        reg["access_token"] = self.client.cookies.get(settings.AUTH_COOKIE_NAME)
        headers = {"Authorization": f"Bearer {reg['access_token']}"}

        ref_id = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers).json()["reference_id"]
        get_res = self.client.get(f"/api/v1/complaint/cases/{ref_id}", headers=headers)
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["reference_id"], ref_id)

    # 16. User A CANNOT retrieve User B's case (Strict Isolation -> 404)
    def test_16_user_cannot_retrieve_another_users_case(self):
        user_a = self.client.post("/api/v1/auth/register", json={"email": "user_a@example.com", "password": "Password123!"}).json()
        user_a["access_token"] = self.client.cookies.get(settings.AUTH_COOKIE_NAME)
        user_b = self.client.post("/api/v1/auth/register", json={"email": "user_b@example.com", "password": "Password123!"}).json()
        user_b["access_token"] = self.client.cookies.get(settings.AUTH_COOKIE_NAME)

        headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}
        headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}

        # User A creates a complaint case
        case_a_ref = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers_a).json()["reference_id"]

        # User B attempts to access User A's case
        get_res = self.client.get(f"/api/v1/complaint/cases/{case_a_ref}", headers=headers_b)
        self.assertEqual(get_res.status_code, 404)
        self.assertEqual(get_res.json()["detail"], "CVKI case was not found.")

    # 17. User A CANNOT retrieve User B's case status (Strict Isolation -> 404)
    def test_17_user_cannot_retrieve_another_users_status(self):
        user_a = self.client.post("/api/v1/auth/register", json={"email": "status_a@example.com", "password": "Password123!"}).json()
        user_a["access_token"] = self.client.cookies.get(settings.AUTH_COOKIE_NAME)
        user_b = self.client.post("/api/v1/auth/register", json={"email": "status_b@example.com", "password": "Password123!"}).json()
        user_b["access_token"] = self.client.cookies.get(settings.AUTH_COOKIE_NAME)

        headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}
        headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}

        case_a_ref = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers_a).json()["reference_id"]

        status_res = self.client.get(f"/api/v1/complaint/cases/{case_a_ref}/status", headers=headers_b)
        self.assertEqual(status_res.status_code, 404)

    # 18. User history returns only own cases
    def test_18_user_history_returns_only_own_cases(self):
        user_a = self.client.post("/api/v1/auth/register", json={"email": "hist_a@example.com", "password": "Password123!"}).json()
        user_a["access_token"] = self.client.cookies.get(settings.AUTH_COOKIE_NAME)
        user_b = self.client.post("/api/v1/auth/register", json={"email": "hist_b@example.com", "password": "Password123!"}).json()
        user_b["access_token"] = self.client.cookies.get(settings.AUTH_COOKIE_NAME)

        headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}
        headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}

        # User A creates 2 cases
        ref_a1 = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers_a).json()["reference_id"]
        ref_a2 = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers_a).json()["reference_id"]

        # User B creates 1 case
        ref_b1 = self.client.post("/api/v1/complaint/cases", json=BASE_CASE_PAYLOAD, headers=headers_b).json()["reference_id"]

        # Query User A history
        hist_a = self.client.get("/api/v1/complaint/cases/my", headers=headers_a).json()
        self.assertEqual(hist_a["total"], 2)
        refs_in_a = [item["reference_id"] for item in hist_a["items"]]
        self.assertIn(ref_a1, refs_in_a)
        self.assertIn(ref_a2, refs_in_a)
        self.assertNotIn(ref_b1, refs_in_a)

        # Query User B history
        hist_b = self.client.get("/api/v1/complaint/cases/my", headers=headers_b).json()
        self.assertEqual(hist_b["total"], 1)
        refs_in_b = [item["reference_id"] for item in hist_b["items"]]
        self.assertIn(ref_b1, refs_in_b)
        self.assertNotIn(ref_a1, refs_in_b)
        self.assertNotIn(ref_a2, refs_in_b)


if __name__ == "__main__":
    unittest.main()
