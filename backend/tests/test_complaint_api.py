import unittest

from fastapi.testclient import TestClient

from app.main import app


BASE_DETECTION = {"class_name": "open_damaged_manhole", "confidence": 0.83}
LOCATION = {
    "road": "Civic Road",
    "area": "Central Area",
    "city": "Sample City",
    "district": "Sample District",
    "state": "Sample State",
    "latitude": 12.34,
    "longitude": 56.78,
}
VERIFIED_AUTHORITY = {
    "authority_status": "verified",
    "road_owner": {"name": "Road Owner", "type": "public owner", "source": "Official register"},
    "maintenance_authority": {"name": "Maintenance Authority", "type": "public maintainer", "source": "Official register"},
    "builder_or_contractor": None,
    "evidence": [{"source_name": "Official register", "source_type": "official_database", "reference": "record-1", "claim": "Maintenance authority verified."}],
    "limitations": [],
}


class TestComplaintAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def post_draft(self, **overrides):
        payload = {"detection": BASE_DETECTION, "location": LOCATION, "language": "en", "image_attached": True}
        payload.update(overrides)
        return self.client.post("/api/v1/complaint/draft", json=payload)

    def test_manhole_severity_and_title(self):
        response = self.post_draft()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["issue_category"], "open_damaged_manhole")
        self.assertEqual(data["title"], "Open/Damaged Manhole Report")
        self.assertEqual(data["severity"], "high")
        self.assertIn("safety hazard", data["severity_reason"])

    def test_road_sign_and_waterlogging_issue_normalization(self):
        sign = self.post_draft(detection={"class_name": "damaged_missing_road_sign", "confidence": 0.78})
        water = self.post_draft(detection={"class_name": "road_waterlogging", "confidence": 0.64})
        self.assertEqual(sign.json()["issue_label"], "Damaged/Missing Road Sign")
        self.assertEqual(sign.json()["severity"], "medium")
        self.assertEqual(water.json()["issue_label"], "Road Waterlogging")
        self.assertEqual(water.json()["severity"], "medium")

    def test_language_options_preserve_issue_facts(self):
        english = self.post_draft(language="en").json()
        hindi = self.post_draft(language="hi").json()
        hinglish = self.post_draft(language="hinglish").json()
        self.assertIn("Open/Damaged Manhole", english["description"])
        self.assertIn("Open/Damaged Manhole", hindi["title"])
        self.assertIn("Open/Damaged Manhole", hinglish["title"])
        self.assertEqual(hindi["issue_category"], hinglish["issue_category"])
        self.assertEqual(hindi["severity"], hinglish["severity"])
        self.assertEqual(hindi["location"], hinglish["location"])

    def test_client_supplied_authority_claim_is_ignored(self):
        data = self.post_draft(authority=VERIFIED_AUTHORITY).json()
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["suggested_authority"])
        self.assertFalse(any("Authority evidence:" in item for item in data["evidence"]))

    def test_client_supplied_partial_authority_claim_is_ignored(self):
        partial = dict(VERIFIED_AUTHORITY)
        partial["authority_status"] = "partially_verified"
        partial_data = self.post_draft(authority=partial).json()
        missing_data = self.post_draft(authority=None).json()
        self.assertEqual(partial_data["authority_status"], "not_verified")
        self.assertIsNone(partial_data["suggested_authority"])
        self.assertEqual(missing_data["authority_status"], "not_verified")
        self.assertIsNone(missing_data["suggested_authority"])
        self.assertTrue(any("No authoritative" in item for item in missing_data["limitations"]))

    def test_guidance_api_ignores_client_supplied_authority(self):
        response = self.client.post(
            "/api/v1/complaint/guidance",
            json={
                "issue_category": "open_damaged_manhole",
                "location": LOCATION,
                "authority": VERIFIED_AUTHORITY,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["official_portal_url"])
        self.assertIn("No authoritative", data["authority_basis"])
        self.assertEqual(data["external_submission_status"], "not_submitted")

    def test_missing_road_and_detection_only_work(self):
        no_road = self.post_draft(location={"city": "Sample City"}).json()
        detection_only = self.post_draft(location=None).json()
        self.assertIn("Road information is not available", no_road["description"])
        self.assertEqual(detection_only["location"], {"road": None, "area": None, "city": None, "district": None, "state": None, "latitude": None, "longitude": None})

    def test_evidence_mentions_model_confidence_and_attachment(self):
        data = self.post_draft().json()
        self.assertTrue(any("83%" in item for item in data["evidence"]))
        self.assertTrue(any("Photo evidence" in item for item in data["evidence"]))
        self.assertNotIn("100% confirmed", data["draft_text"])

    def test_no_contacts_are_fabricated(self):
        data = self.post_draft().json()
        self.assertNotIn("phone", data["draft_text"].lower())
        self.assertNotIn("email", data["draft_text"].lower())
        self.assertIsNone(data["suggested_authority"])

    def test_invalid_request_and_unsupported_class(self):
        invalid = self.client.post("/api/v1/complaint/draft", json={"detection": BASE_DETECTION, "language": "fr"})
        unsupported = self.post_draft(detection={"class_name": "unknown_issue", "confidence": 0.9})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(unsupported.status_code, 422)


if __name__ == "__main__":
    unittest.main()
