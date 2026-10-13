import unittest

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.schemas.authority import AuthorityEvidence, AuthorityParty, AuthorityResult, OfficialSourceRecord
from app.schemas.guidance import GovernmentGuidanceRequest
from app.services.guidance import generate_government_guidance


class TestGuidanceM35(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_01_verified_authority_guidance_generated(self):
        authority = AuthorityResult(
            authority_status="verified",
            road_owner=AuthorityParty(name="MoRTH", official_portal_url="https://morth.nic.in"),
            maintenance_authority=AuthorityParty(name="NHAI", official_portal_url="https://nhai.gov.in"),
            sources=[
                OfficialSourceRecord(
                    source_id="src1",
                    source_name="NHAI Project Portal",
                    source_type="government_portal",
                    source_url="https://nhai.gov.in",
                    source_domain="nhai.gov.in",
                )
            ],
        )
        req = GovernmentGuidanceRequest(
            issue_category="open_damaged_manhole",
            location={"road": "Hosur Road", "city": "Bengaluru"},
            authority=authority,
            language="en",
        )
        guidance = generate_government_guidance(req)
        self.assertIn("Official Grievance Portal", guidance.recommended_channel)
        self.assertEqual(guidance.official_portal_url, "https://nhai.gov.in")
        self.assertEqual(guidance.external_submission_status, "not_submitted")
        self.assertTrue(len(guidance.steps) >= 5)
        self.assertTrue(len(guidance.what_to_attach) >= 2)
        self.assertTrue(len(guidance.what_to_write) >= 2)

    def test_02_partially_verified_authority_guidance(self):
        authority = AuthorityResult(
            authority_status="partially_verified",
            road_owner=AuthorityParty(name="Karnataka Public Works Department (PWD)", official_portal_url="https://karnataka.gov.in"),
            maintenance_authority=None,
        )
        req = GovernmentGuidanceRequest(
            issue_category="damaged_missing_road_sign",
            location={"road": "State Highway 39"},
            authority=authority,
            language="en",
        )
        guidance = generate_government_guidance(req)
        self.assertIn("Jurisdictional Division Office", guidance.recommended_channel)
        self.assertEqual(guidance.external_submission_status, "not_submitted")
        self.assertTrue(any("partially verified" in lim for lim in guidance.limitations))

    def test_03_not_verified_no_guessed_authority(self):
        authority = AuthorityResult(
            authority_status="not_verified",
            road_owner=None,
            maintenance_authority=None,
        )
        req = GovernmentGuidanceRequest(
            issue_category="road_waterlogging",
            location={"city": "Mumbai"},
            authority=authority,
            language="en",
        )
        guidance = generate_government_guidance(req)
        self.assertEqual(guidance.recommended_channel, "Official authority contact/process could not be verified.")
        self.assertIsNone(guidance.official_portal_url)
        self.assertEqual(guidance.external_submission_status, "not_submitted")
        self.assertTrue(any("could not verify the responsible authority" in lim for lim in guidance.limitations))

    def test_04_official_portal_source_present(self):
        authority = AuthorityResult(
            authority_status="verified",
            road_owner=AuthorityParty(name="BBMP", official_portal_url="https://bbmp.gov.in"),
            maintenance_authority=AuthorityParty(name="BBMP East Zone", official_portal_url="https://bbmp.gov.in"),
        )
        req = GovernmentGuidanceRequest(
            issue_category="open_damaged_manhole",
            location={"road": "MG Road", "city": "Bengaluru"},
            authority=authority,
            language="en",
        )
        guidance = generate_government_guidance(req)
        self.assertEqual(guidance.official_portal_url, "https://bbmp.gov.in")
        self.assertIn("https://bbmp.gov.in", guidance.steps[0])

    def test_05_no_official_portal_source(self):
        authority = AuthorityResult(
            authority_status="not_verified",
            road_owner=None,
            maintenance_authority=None,
        )
        req = GovernmentGuidanceRequest(
            issue_category="open_damaged_manhole",
            authority=authority,
            language="en",
        )
        guidance = generate_government_guidance(req)
        self.assertIsNone(guidance.official_portal_url)
        self.assertEqual(guidance.recommended_channel, "Official authority contact/process could not be verified.")

    def test_06_untrusted_url_not_used(self):
        # Party claiming a non-government URL
        authority = AuthorityResult(
            authority_status="verified",
            road_owner=AuthorityParty(name="Agency", official_portal_url="https://commercial-blog.com/portal"),
            maintenance_authority=AuthorityParty(name="Agency Maintainer", official_portal_url="https://untrusted-directory.org"),
        )
        req = GovernmentGuidanceRequest(
            issue_category="open_damaged_manhole",
            authority=authority,
            language="en",
        )
        guidance = generate_government_guidance(req)
        # Untrusted URLs must be rejected and omitted
        self.assertIsNone(guidance.official_portal_url)

    def test_07_government_submission_remains_not_submitted(self):
        for status in ("verified", "partially_verified", "not_verified"):
            guidance = generate_government_guidance(
                GovernmentGuidanceRequest(
                    issue_category="open_damaged_manhole",
                    authority=AuthorityResult(authority_status=status),
                    language="en",
                )
            )
            self.assertEqual(guidance.external_submission_status, "not_submitted")
            self.assertTrue(any("not_submitted" in lim for lim in guidance.limitations))

    def test_08_english_guidance(self):
        req = GovernmentGuidanceRequest(
            issue_category="open_damaged_manhole",
            location={"road": "Main Street"},
            language="en",
        )
        guidance = generate_government_guidance(req)
        self.assertEqual(guidance.language, "en")
        self.assertIn("Select the relevant civic grievance category", guidance.steps[1])

    def test_09_hindi_guidance(self):
        req = GovernmentGuidanceRequest(
            issue_category="open_damaged_manhole",
            location={"road": "Main Street"},
            language="hi",
        )
        guidance = generate_government_guidance(req)
        self.assertEqual(guidance.language, "hi")
        self.assertIn("नागरिक शिकायत / सड़क रखरखाव श्रेणी चुनें।", guidance.steps[1])
        self.assertIn("फोटो संलग्न करें", guidance.steps[3])

    def test_10_hinglish_guidance(self):
        req = GovernmentGuidanceRequest(
            issue_category="open_damaged_manhole",
            location={"road": "Main Street"},
            language="hinglish",
        )
        guidance = generate_government_guidance(req)
        self.assertEqual(guidance.language, "hinglish")
        self.assertIn("category select kijiye", guidance.steps[1])
        self.assertIn("photo attach kijiye", guidance.steps[3])

    def test_11_guidance_preserves_official_names(self):
        authority = AuthorityResult(
            authority_status="verified",
            road_owner=AuthorityParty(name="Bruhat Bengaluru Mahanagara Palike (BBMP)"),
            maintenance_authority=AuthorityParty(name="BBMP Road Infrastructure Division"),
        )
        for lang in ("en", "hi", "hinglish"):
            guidance = generate_government_guidance(
                GovernmentGuidanceRequest(
                    issue_category="open_damaged_manhole",
                    authority=authority,
                    language=lang,
                )
            )
            # Factual organization names must remain untranslated and uncorrupted
            self.assertIn("BBMP", guidance.recommended_channel)

    def test_12_guidance_preserves_urls(self):
        authority = AuthorityResult(
            authority_status="verified",
            road_owner=AuthorityParty(name="NHAI", official_portal_url="https://nhai.gov.in"),
            maintenance_authority=AuthorityParty(name="NHAI", official_portal_url="https://nhai.gov.in"),
        )
        for lang in ("en", "hi", "hinglish"):
            guidance = generate_government_guidance(
                GovernmentGuidanceRequest(
                    issue_category="open_damaged_manhole",
                    authority=authority,
                    language=lang,
                )
            )
            self.assertEqual(guidance.official_portal_url, "https://nhai.gov.in")
            self.assertIn("https://nhai.gov.in", guidance.steps[0])

    def test_13_complaint_endpoint_attaches_guidance(self):
        payload = {
            "detection": {"class_name": "open_damaged_manhole", "confidence": 0.88},
            "location": {"road": "Vittal Mallya Road", "city": "Bengaluru"},
            "language": "en",
        }
        response = self.client.post("/api/v1/complaint/draft", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("guidance", data)
        self.assertIsNotNone(data["guidance"])
        self.assertEqual(data["guidance"]["external_submission_status"], "not_submitted")
        # Text remains editable
        self.assertTrue(len(data["description"]) > 10)

    def test_14_guidance_api_endpoint(self):
        payload = {
            "issue_category": "open_damaged_manhole",
            "location": {"road": "MG Road", "city": "Bengaluru"},
            "language": "hinglish",
        }
        response = self.client.post("/api/v1/complaint/guidance", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["external_submission_status"], "not_submitted")
        self.assertEqual(data["language"], "hinglish")

    def test_15_case_distinguishes_cvki_from_government_submission(self):
        # Register user to get valid authenticated token
        email = "test_guidance_m35@example.com"
        reg = self.client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
        if reg.status_code == 201:
            token = reg.cookies.get(settings.AUTH_COOKIE_NAME)
        else:
            login = self.client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
            token = login.cookies.get(settings.AUTH_COOKIE_NAME)

        case_payload = {
            "issue": {"class_name": "open_damaged_manhole", "label": "Open/Damaged Manhole", "severity": "high", "confidence": 0.9},
            "location": {"road": "Vittal Mallya Road", "city": "Bengaluru"},
            "complaint": {"language": "en", "title": "Hazardous Manhole", "description": "Please fix."},
            "evidence": ["Vision analysis"],
        }
        response = self.client.post(
            "/api/v1/complaint/cases",
            json=case_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertIn(response.status_code, (200, 201))
        data = response.json()
        self.assertEqual(data["status"], "submitted_to_cvki")
        self.assertEqual(data["follow_up"]["external_submission_status"], "not_submitted")
        self.assertIn("official_guidance", data["follow_up"])
        self.assertIsNotNone(data["follow_up"]["official_guidance"])
        self.assertEqual(data["follow_up"]["official_guidance"]["external_submission_status"], "not_submitted")


if __name__ == "__main__":
    unittest.main()
