import asyncio
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
import pymongo
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.database import (
    COMPLAINT_CASES_COLLECTION,
    USERS_COLLECTION,
    get_database,
    is_mongo_healthy,
    sanitize_mongodb_uri,
)
from app.main import app
from app.schemas.authority import AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.services.complaint_case import (
    ComplaintCaseDatabaseError,
    ComplaintCaseDuplicateError,
    MongoComplaintCaseRepository,
    _new_reference_id,
)

TEST_DB_NAME = "cvki_test_m3_1"

SAMPLE_PAYLOAD = {
    "issue": {
        "class_name": "open_damaged_manhole",
        "label": "Open/Damaged Manhole",
        "severity": "high",
        "confidence": 0.89,
    },
    "location": {
        "road": "MG Road",
        "area": "Indiranagar",
        "city": "Bengaluru",
        "district": "Bengaluru Urban",
        "state": "Karnataka",
        "latitude": 12.9716,
        "longitude": 77.5946,
    },
    "complaint": {
        "language": "en",
        "title": "Severe Open Manhole on MG Road",
        "description": "An open manhole poses immediate danger to two-wheelers and pedestrians.",
    },
    "evidence": ["Photo evidence attached.", "YOLOv8 confidence 89%."],
}


class TestMongoPersistenceM31(unittest.TestCase):
    """
    Focused verification suite for M3.1 MongoDB Complaint Case Persistence.
    Executes real MongoDB integration tests against dedicated test database.
    """

    @classmethod
    def setUpClass(cls):
        # Point to dedicated test database
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        # Verify real MongoDB connectivity via pymongo
        try:
            cls.sync_client = pymongo.MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=2000,
            )
            cls.sync_client.admin.command("ping")
            cls.mongo_available = True
        except Exception:
            cls.mongo_available = False

        if not cls.mongo_available:
            raise unittest.SkipTest("Real MongoDB is not available on localhost:27017")

        cls.sync_db = cls.sync_client[TEST_DB_NAME]
        cls.sync_collection = cls.sync_db[COMPLAINT_CASES_COLLECTION]
        cls.sync_users = cls.sync_db[USERS_COLLECTION]

        # Enter FastAPI TestClient lifespan so motor connection pool is initialized
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

        # Register a test citizen for authenticated case operations
        reg_res = cls.client.post(
            "/api/v1/auth/register",
            json={"email": f"persistent_tester_{uuid.uuid4().hex}@cvki.internal", "password": "Password123!"},
        )
        cls.auth_headers = {"Authorization": f"Bearer {reg_res.cookies.get('cvki_access_token')}"}

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
        # Clean complaint cases collection between tests
        self.sync_collection.delete_many({})

    # 1. MongoDB Configuration Loading & Credential Masking
    def test_01_mongodb_configuration_loading(self):
        self.assertIsNotNone(settings.MONGODB_URI)
        self.assertIn("mongodb://", settings.MONGODB_URI)
        self.assertEqual(settings.MONGODB_TIMEOUT_MS, 5000)

        # Verify credential masking prevents credential exposure in logs
        raw_uri_with_creds = "mongodb://cvki_user:superSecretPassword99@cluster.cvki.internal:27017/cvki"
        sanitized = sanitize_mongodb_uri(raw_uri_with_creds)
        self.assertNotIn("superSecretPassword99", sanitized)
        self.assertIn("cvki_user:***@", sanitized)

    # 2. Case Creation Persistence in MongoDB
    def test_02_case_creation_persists_in_mongodb(self):
        response = self.client.post("/api/v1/complaint/cases", json=SAMPLE_PAYLOAD, headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        ref_id = data["reference_id"]

        # Directly query MongoDB to verify data was physically stored
        doc = self.sync_collection.find_one({"reference_id": ref_id})
        self.assertIsNotNone(doc, "Case document was not found in MongoDB collection")
        self.assertEqual(doc["reference_id"], ref_id)
        self.assertEqual(doc["status"], "submitted_to_cvki")
        self.assertEqual(doc["external_submission_status"], "not_submitted")
        self.assertEqual(doc["issue"]["class_name"], "open_damaged_manhole")
        self.assertEqual(doc["complaint"]["title"], "Severe Open Manhole on MG Road")
        self.assertEqual(doc["location"]["city"], "Bengaluru")
        self.assertIn("Photo evidence attached.", doc["evidence"])

    # 3. Case Retrieval from MongoDB
    def test_03_case_retrieval(self):
        create_res = self.client.post("/api/v1/complaint/cases", json=SAMPLE_PAYLOAD, headers=self.auth_headers)
        ref_id = create_res.json()["reference_id"]

        get_res = self.client.get(f"/api/v1/complaint/cases/{ref_id}", headers=self.auth_headers)
        self.assertEqual(get_res.status_code, 200)
        case_data = get_res.json()
        self.assertEqual(case_data["reference_id"], ref_id)
        self.assertEqual(case_data["complaint"]["title"], SAMPLE_PAYLOAD["complaint"]["title"])
        self.assertEqual(case_data["complaint"]["description"], SAMPLE_PAYLOAD["complaint"]["description"])

    # 4. Status Retrieval from MongoDB
    def test_04_status_retrieval(self):
        create_res = self.client.post("/api/v1/complaint/cases", json=SAMPLE_PAYLOAD, headers=self.auth_headers)
        ref_id = create_res.json()["reference_id"]

        status_res = self.client.get(f"/api/v1/complaint/cases/{ref_id}/status", headers=self.auth_headers)
        self.assertEqual(status_res.status_code, 200)
        status_data = status_res.json()
        self.assertEqual(status_data["reference_id"], ref_id)
        self.assertEqual(status_data["status"], "submitted_to_cvki")
        self.assertEqual(status_data["external_submission_status"], "not_submitted")
        self.assertIn("CVKI application", status_data["status_description"])

    # 5. Unknown Reference -> 404
    def test_05_unknown_reference_returns_404(self):
        fake_ref = "CVKI-20261011-999999"
        get_res = self.client.get(f"/api/v1/complaint/cases/{fake_ref}", headers=self.auth_headers)
        self.assertEqual(get_res.status_code, 404)
        self.assertEqual(get_res.json()["detail"], "CVKI case was not found.")

        status_res = self.client.get(f"/api/v1/complaint/cases/{fake_ref}/status", headers=self.auth_headers)
        self.assertEqual(status_res.status_code, 404)
        self.assertEqual(status_res.json()["detail"], "CVKI case was not found.")

    # 6. Duplicate Reference Protection (Unique Index & DuplicateKeyError)
    def test_06_duplicate_reference_protection(self):
        async def run_duplicate_test():
            client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            db = client[TEST_DB_NAME]
            repo = MongoComplaintCaseRepository(db=db)
            ref_id = _new_reference_id()
            now = datetime.now(timezone.utc)

            case1 = ComplaintCase(
                reference_id=ref_id,
                user_id="usr_tester1234",
                status="submitted_to_cvki",
                created_at=now,
                updated_at=now,
                issue=CaseIssue(class_name="open_damaged_manhole", label="Open/Damaged Manhole", severity="high", confidence=0.9),
                location=ComplaintLocation(city="Bengaluru"),
                authority=AuthorityResult(authority_status="not_verified", limitations=[]),
                complaint=CaseComplaint(language="en", title="Original Title", description="Original Desc"),
                evidence=["photo.jpg"],
                follow_up=FollowUp(guidance="Follow up guidance", external_submission_status="not_submitted"),
            )
            await repo.save(case1)

            # Attempting to save the same reference_id again must raise ComplaintCaseDuplicateError
            case2 = ComplaintCase(
                reference_id=ref_id,
                user_id="usr_tester1234",
                status="submitted_to_cvki",
                created_at=now,
                updated_at=now,
                issue=CaseIssue(class_name="open_damaged_manhole", label="Open/Damaged Manhole", severity="high", confidence=0.9),
                location=ComplaintLocation(city="Bengaluru"),
                authority=AuthorityResult(authority_status="not_verified", limitations=[]),
                complaint=CaseComplaint(language="en", title="Overwriting Title", description="Overwriting Desc"),
                evidence=["photo2.jpg"],
                follow_up=FollowUp(guidance="Follow up guidance", external_submission_status="not_submitted"),
            )
            with self.assertRaises(ComplaintCaseDuplicateError):
                await repo.save(case2)

            persisted = await repo.get(ref_id)
            self.assertEqual(persisted.complaint.title, "Original Title")
            client.close()

        asyncio.run(run_duplicate_test())

    # 7. Required Field Validation (422)
    def test_07_required_field_validation(self):
        # Missing issue
        invalid1 = dict(SAMPLE_PAYLOAD)
        del invalid1["issue"]
        self.assertEqual(self.client.post("/api/v1/complaint/cases", json=invalid1, headers=self.auth_headers).status_code, 422)

        # Missing complaint text
        invalid2 = dict(SAMPLE_PAYLOAD)
        invalid2["complaint"] = {"language": "en", "title": "", "description": ""}
        self.assertEqual(self.client.post("/api/v1/complaint/cases", json=invalid2, headers=self.auth_headers).status_code, 422)

        # Invalid issue label / class mismatch
        invalid3 = dict(SAMPLE_PAYLOAD)
        invalid3["issue"] = {"class_name": "unknown_class", "label": "Unknown", "severity": "low", "confidence": 0.5}
        self.assertEqual(self.client.post("/api/v1/complaint/cases", json=invalid3, headers=self.auth_headers).status_code, 422)

    # 8. Timestamp Existence & UTC Correctness
    def test_08_timestamp_existence(self):
        response = self.client.post("/api/v1/complaint/cases", json=SAMPLE_PAYLOAD, headers=self.auth_headers)
        data = response.json()
        ref_id = data["reference_id"]

        # Verify created_at in API response
        self.assertIn("created_at", data)
        self.assertIsNotNone(data["created_at"])

        # Verify MongoDB document has both created_at and updated_at
        doc = self.sync_collection.find_one({"reference_id": ref_id})
        self.assertIn("created_at", doc)
        self.assertIn("updated_at", doc)
        self.assertIsInstance(doc["created_at"], datetime)
        self.assertIsInstance(doc["updated_at"], datetime)

    # 9. Data Survives Repository Reinitialization (Persistence Across Lifecycle)
    def test_09_data_survives_repository_reinitialization(self):
        async def run_reinit_test():
            client1 = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            repo1 = MongoComplaintCaseRepository(db=client1[TEST_DB_NAME])
            ref_id = _new_reference_id()
            now = datetime.now(timezone.utc)

            case = ComplaintCase(
                reference_id=ref_id,
                user_id="usr_tester1234",
                status="submitted_to_cvki",
                created_at=now,
                updated_at=now,
                issue=CaseIssue(class_name="open_damaged_manhole", label="Open/Damaged Manhole", severity="high", confidence=0.88),
                location=ComplaintLocation(city="Bengaluru"),
                authority=AuthorityResult(authority_status="not_verified", limitations=[]),
                complaint=CaseComplaint(language="en", title="Survives Restart", description="Case text"),
                evidence=["photo.jpg"],
                follow_up=FollowUp(guidance="Follow up guidance", external_submission_status="not_submitted"),
            )
            await repo1.save(case)
            client1.close()

            # Create a completely new client and repository instance simulating a backend restart
            client2 = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            repo2 = MongoComplaintCaseRepository(db=client2[TEST_DB_NAME])
            retrieved = await repo2.get(ref_id)

            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.reference_id, ref_id)
            self.assertEqual(retrieved.complaint.title, "Survives Restart")
            client2.close()

        asyncio.run(run_reinit_test())

    # 10. MongoDB Failure / Safe Error Handling
    def test_10_mongodb_failure_handling(self):
        # Disconnected repository must raise ComplaintCaseDatabaseError
        disconnected_repo = MongoComplaintCaseRepository(db=None)
        with self.assertRaises(ComplaintCaseDatabaseError):
            disconnected_repo._get_collection()

        # Direct test on API when DB is disconnected
        with patch("app.core.database.get_database", return_value=None):
            with patch("app.services.complaint_case.get_database", return_value=None):
                post_res = self.client.post("/api/v1/complaint/cases", json=SAMPLE_PAYLOAD, headers=self.auth_headers)
                self.assertEqual(post_res.status_code, 503)
                self.assertIn("Database service is unavailable", post_res.json()["detail"])

                get_res = self.client.get("/api/v1/complaint/cases/CVKI-20261011-123456", headers=self.auth_headers)
                self.assertEqual(get_res.status_code, 503)

        # Liveness stays healthy while readiness reports dependency failure.
        with patch("app.api.health.is_mongo_healthy", return_value=False):
            health_res = self.client.get("/api/health")
            self.assertEqual(health_res.status_code, 200)
            self.assertEqual(health_res.json()["status"], "ok")

            ready_res = self.client.get("/api/ready")
            self.assertEqual(ready_res.status_code, 503)
            self.assertEqual(ready_res.json()["status"], "not_ready")
            self.assertEqual(ready_res.json()["dependencies"]["database"], "unavailable")


if __name__ == "__main__":
    unittest.main()
