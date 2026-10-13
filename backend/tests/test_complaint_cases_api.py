import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.authority import AuthorityResult
from app.schemas.complaint_case import ComplaintCase
from app.services.complaint_case import InMemoryComplaintCaseRepository


BASE_CASE = {
    "issue": {
        "class_name": "open_damaged_manhole",
        "label": "Open/Damaged Manhole",
        "severity": "high",
        "confidence": 0.83,
    },
    "location": {
        "road": "Civic Road",
        "area": "Central Area",
        "city": "Sample City",
        "district": "Sample District",
        "state": "Sample State",
        "latitude": 12.34,
        "longitude": 56.78,
    },
    "complaint": {
        "language": "en",
        "title": "Edited manhole report",
        "description": "Citizen-edited final complaint text.",
    },
    "evidence": ["Photo evidence is attached.", "Model confidence 83%."],
}


class TestComplaintCasesAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        from app.core.config import settings
        cls._orig_db_name = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = "cvki_test_m2_regression"
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()
        email = f"m2_test_{uuid.uuid4().hex}@cvki.internal"
        reg = cls.client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
        cls.auth_headers = {"Authorization": f"Bearer {reg.cookies.get('cvki_access_token')}"}

    def setUp(self):
        self.client.cookies.clear()

    @classmethod
    def tearDownClass(cls):
        import asyncio
        from app.core.config import settings
        from app.core.database import mongo_manager
        if mongo_manager.client is not None:
            try:
                asyncio.run(mongo_manager.client.drop_database("cvki_test_m2_regression"))
            except Exception:
                pass
        cls.client_cm.__exit__(None, None, None)
        settings.MONGODB_DB_NAME = cls._orig_db_name

    def create_case(self, **overrides):
        payload = dict(BASE_CASE)
        payload.update(overrides)
        return self.client.post("/api/v1/complaint/cases", json=payload, headers=self.auth_headers)

    def test_create_case_generates_internal_reference_and_initial_status(self):
        response = self.create_case()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertRegex(data["reference_id"], r"^CVKI-\d{8}-[A-F0-9]{6}$")
        self.assertEqual(data["status"], "submitted_to_cvki")
        self.assertEqual(data["follow_up"]["external_submission_status"], "not_submitted")
        self.assertIn("created inside the CVKI application", data["follow_up"]["guidance"])

    def test_reference_ids_are_unique(self):
        first = self.create_case().json()["reference_id"]
        second = self.create_case().json()["reference_id"]
        self.assertNotEqual(first, second)

    def test_get_case_preserves_edited_text(self):
        created = self.create_case().json()
        fetched = self.client.get(f"/api/v1/complaint/cases/{created['reference_id']}", headers=self.auth_headers)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["complaint"]["title"], "Edited manhole report")
        self.assertEqual(fetched.json()["complaint"]["description"], "Citizen-edited final complaint text.")

    def test_missing_case_returns_404(self):
        self.assertEqual(self.client.get("/api/v1/complaint/cases/CVKI-20990101-ABCDEF", headers=self.auth_headers).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/complaint/cases/CVKI-20990101-ABCDEF/status", headers=self.auth_headers).status_code, 404)

    def test_status_endpoint_distinguishes_cvki_from_external_submission(self):
        reference = self.create_case().json()["reference_id"]
        data = self.client.get(f"/api/v1/complaint/cases/{reference}/status", headers=self.auth_headers).json()
        self.assertEqual(data["reference_id"], reference)
        self.assertEqual(data["status"], "submitted_to_cvki")
        self.assertEqual(data["external_submission_status"], "not_submitted")
        self.assertIn("CVKI application", data["status_description"])

    def test_language_cases_preserve_language(self):
        for language in ("en", "hi", "hinglish"):
            payload = dict(BASE_CASE)
            payload["complaint"] = {"language": language, "title": "Final title", "description": "Final text"}
            response = self.create_case(complaint=payload["complaint"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["complaint"]["language"], language)

    def test_client_supplied_authority_claims_are_ignored(self):
        verified = {
            "authority_status": "verified",
            "road_owner": {"name": "Owner", "source": "Official register"},
            "maintenance_authority": {"name": "Maintainer", "source": "Official register"},
            "builder_or_contractor": None,
            "evidence": [{"source_name": "Official register", "source_type": "official_database", "claim": "Roles verified."}],
            "limitations": [],
        }
        partial = dict(verified)
        partial["authority_status"] = "partially_verified"
        for authority in (verified, partial, None):
            response = self.create_case(authority=authority)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["authority"]["authority_status"], "not_verified")
            self.assertIsNone(response.json()["authority"]["road_owner"])
            self.assertIsNone(response.json()["authority"]["maintenance_authority"])

    def test_missing_location_is_allowed(self):
        response = self.create_case(location=None)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["location"]["road"])

    def test_unsupported_and_invalid_requests_are_rejected(self):
        unsupported = dict(BASE_CASE)
        unsupported["issue"] = {"class_name": "unknown", "label": "Unknown", "severity": "low", "confidence": 0.5}
        invalid = self.client.post("/api/v1/complaint/cases", json={"issue": BASE_CASE["issue"]}, headers=self.auth_headers)
        self.assertEqual(self.client.post("/api/v1/complaint/cases", json=unsupported, headers=self.auth_headers).status_code, 422)
        self.assertEqual(invalid.status_code, 422)

    def test_no_contacts_and_follow_up_safety(self):
        data = self.create_case().json()
        self.assertIsNone(data["authority"]["road_owner"])
        self.assertIsNone(data["authority"]["maintenance_authority"])
        self.assertIsNone(data["authority"]["builder_or_contractor"])
        self.assertNotIn("phone", str(data).lower())
        self.assertIn("No external government complaint has been submitted yet", data["follow_up"]["guidance"])
        self.assertIn("verify the appropriate authority", data["follow_up"]["guidance"])

    def test_in_memory_repository_save_and_get(self):
        repository = InMemoryComplaintCaseRepository()
        case = ComplaintCase.model_validate(self.create_case().json())
        repository.save(case)
        self.assertEqual(repository.get(case.reference_id).reference_id, case.reference_id)
        with self.assertRaises(LookupError):
            repository.get("CVKI-20990101-ABCDEF")


if __name__ == "__main__":
    unittest.main()
