import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.authority import AuthorityEvidence, AuthorityParty, OfficialSourceRecord
from app.services.authority import (
    AuthorityLookup,
    AuthorityProviderError,
    AuthorityProviderTimeout,
    is_trusted_official_domain,
)


class TestAuthorityM34(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_01_default_provider_never_claims_unconfigured_authority(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=12.91&longitude=77.63&road=NH-44%20Hosur%20Road")
        self.assertEqual(response.status_code, 200)
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])
        self.assertIsNone(data["maintenance_authority"])
        self.assertEqual(data["evidence"], [])
        self.assertEqual(data["sources"], [])

    def test_02_default_provider_never_claims_partial_verification(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=13.0&longitude=77.5&road=Karnataka%20State%20Highway%2039")
        self.assertEqual(response.status_code, 200)
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])
        self.assertIsNone(data["maintenance_authority"])
        self.assertEqual(data["sources"], [])

    def test_03_not_verified_for_unrecognized_location(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78&road=Unregistered%20Private%20Lane&city=Bengaluru")
        self.assertEqual(response.status_code, 200)
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])
        self.assertIsNone(data["maintenance_authority"])
        self.assertIsNone(data["builder_or_contractor"])
        self.assertIn("Administrative jurisdiction does not by itself establish", data["limitations"][0])

    def test_04_no_road_information_returns_not_verified(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 200)
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])

    def test_05_unsupported_location_never_guesses_from_city_or_state(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=28.61&longitude=77.20&city=Delhi&state=Delhi")
        self.assertEqual(response.status_code, 200)
        data = response.json()["authority"]
        # System must NEVER guess MCD or NDMC from city name alone without road evidence
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])

    @patch("app.services.authority.authority_provider")
    def test_06_missing_source_evidence_cannot_verify_claim(self, mock_provider):
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Unsubstantiated Owner"),
            maintenance_authority=AuthorityParty(name="Unsubstantiated Maintainer"),
            evidence=(),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])

    @patch("app.services.authority.authority_provider")
    def test_07_untrusted_source_rejection(self, mock_provider):
        # Evidence claiming to come from a random blog or wikipedia
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Blog Claimed Owner"),
            maintenance_authority=AuthorityParty(name="Blog Claimed Maintainer"),
            evidence=(
                AuthorityEvidence(
                    source_name="Random Citizen Blog",
                    source_type="blog",
                    claim="Owner is Blog Claimed Owner",
                    source_url="https://randomblog.com/civic-issues",
                ),
            ),
            sources=(
                OfficialSourceRecord(
                    source_id="untrusted_1",
                    source_name="Random Blog",
                    source_type="blog",
                    source_url="https://randomblog.com",
                    source_domain="randomblog.com",
                ),
            ),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])
        self.assertTrue(any("disallowed by official source policy" in lim for lim in data["limitations"]))

    @patch("app.services.authority.authority_provider")
    def test_08_builder_contractor_not_guessed_without_tender_record(self, mock_provider):
        # Road owner & maintainer verified, but contractor has no tender/official contract record
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Municipal Authority", source="Official register"),
            maintenance_authority=AuthorityParty(name="Works Division", source="Official register"),
            builder_or_contractor=AuthorityParty(name="Unverified Contractor Corp"),  # No tender/contract source
            evidence=(
                AuthorityEvidence(
                    source_name="Municipal Register",
                    source_type="municipal_registry",
                    claim="Road owned and maintained by municipality",
                    matched_attribute="road",
                ),
                AuthorityEvidence(
                    source_name="Municipal Register",
                    source_type="municipal_registry",
                    claim="Municipality owns the road",
                    matched_attribute="road_owner",
                ),
                AuthorityEvidence(
                    source_name="Municipal Register",
                    source_type="municipal_registry",
                    claim="Municipality maintains the road",
                    matched_attribute="maintenance_authority",
                ),
            ),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "verified")
        # Builder must be null because no official contract/tender record supported it
        self.assertIsNone(data["builder_or_contractor"])

    @patch("app.services.authority.authority_provider")
    def test_09_road_owner_not_copied_into_maintenance_authority(self, mock_provider):
        # Only road owner known
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="State Road Department", source="Official gazette"),
            maintenance_authority=None,
            evidence=(
                AuthorityEvidence(
                    source_name="Road Inventory",
                    source_type="official_database",
                    claim="The reported road matches the road inventory record.",
                    matched_attribute="road",
                ),
                AuthorityEvidence(
                    source_name="State Gazette",
                    source_type="official_gazette",
                    claim="Road owner is State Road Department",
                    matched_attribute="road_owner",
                ),
            ),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "partially_verified")
        self.assertEqual(data["road_owner"]["name"], "State Road Department")
        self.assertIsNone(data["maintenance_authority"])
        self.assertNotEqual(data["road_owner"]["name"], data["maintenance_authority"])

    def test_10_default_provider_has_no_static_source_metadata(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=12.97&longitude=77.59&road=MG%20Road")
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertEqual(data["sources"], [])

    def test_11_existing_m28_behavior_preserved(self):
        # Empty context returns safe not_verified
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("location", data)
        self.assertIn("authority", data)
        self.assertEqual(data["authority"]["authority_status"], "not_verified")
        self.assertTrue(len(data["authority"]["limitations"]) >= 1)

    def test_12_unconfigured_provider_emits_no_authority_urls(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=12.91&longitude=77.63&road=NH-44%20Hosur%20Road")
        data = response.json()["authority"]
        self.assertEqual(data["sources"], [])

    def test_trusted_domain_allowlist(self):
        self.assertTrue(is_trusted_official_domain("https://morth.nic.in"))
        self.assertTrue(is_trusted_official_domain("https://transport.gov.in/"))
        self.assertFalse(is_trusted_official_domain("https://randomblog.com"))

    @patch("app.services.authority.authority_provider")
    def test_13_provider_failure_handling(self, mock_provider):
        mock_provider.lookup.side_effect = AuthorityProviderError("Official provider connection failure")
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 502)
        self.assertIn("Authority information is temporarily unavailable", response.json()["detail"])

    @patch("app.services.authority.authority_provider")
    def test_14_timeout_handling(self, mock_provider):
        mock_provider.lookup.side_effect = AuthorityProviderTimeout("Provider timeout")
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 504)
        self.assertIn("Authority source timed out", response.json()["detail"])

    def test_15_unconfigured_provider_does_not_claim_source_freshness(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=12.91&longitude=77.63&road=NH-44%20Hosur%20Road")
        data = response.json()["authority"]
        self.assertIsNotNone(data.get("resolved_at"))
        self.assertEqual(data["sources"], [])

    @patch("app.services.authority.authority_provider")
    def test_16_authority_claims_without_road_link_are_not_verified(self, mock_provider):
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Claimed Owner"),
            maintenance_authority=AuthorityParty(name="Claimed Maintainer"),
            evidence=(
                AuthorityEvidence(
                    source_name="Official register",
                    source_type="official_database",
                    claim="This organization owns the road.",
                    matched_attribute="road_owner",
                ),
                AuthorityEvidence(
                    source_name="Official register",
                    source_type="official_database",
                    claim="This organization maintains the road.",
                    matched_attribute="maintenance_authority",
                ),
            ),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78&road=Civic%20Road")
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])
        self.assertIsNone(data["maintenance_authority"])
        self.assertEqual(data["evidence"][0]["verification_state"], "not_verified")
        self.assertIn("could not link", data["citizen_explanation"])

    @patch("app.services.authority.authority_provider")
    def test_17_linked_owner_evidence_is_partial_and_explanation_is_deterministic(self, mock_provider):
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Road Owner"),
            maintenance_authority=AuthorityParty(name="Unsupported Maintainer"),
            evidence=(
                AuthorityEvidence(
                    source_name="Road Inventory",
                    source_type="official_database",
                    claim="The reported road matches this inventory record.",
                    matched_attribute="road",
                    verification_state="not_verified",
                ),
                AuthorityEvidence(
                    source_name="Road Register",
                    source_type="municipal_registry",
                    claim="The registered owner is Road Owner.",
                    matched_attribute="road_owner",
                    verification_state="not_verified",
                ),
            ),
        )
        first = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78&road=Civic%20Road").json()["authority"]
        second = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78&road=Civic%20Road").json()["authority"]
        self.assertEqual(first["authority_status"], "partially_verified")
        self.assertIsNone(first["maintenance_authority"])
        self.assertEqual(first["evidence"][0]["verification_state"], "verified")
        self.assertEqual(first["evidence"][1]["matched_attribute"], "road_owner")
        self.assertEqual(first["evidence"][1]["verification_state"], "verified")
        self.assertEqual(first["citizen_explanation"], second["citizen_explanation"])
        self.assertIn("do not verify both", first["citizen_explanation"])

    @patch("app.services.authority.authority_provider")
    def test_18_builder_needs_road_link_and_builder_specific_contract_record(self, mock_provider):
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Road Owner"),
            maintenance_authority=AuthorityParty(name="Maintainer"),
            builder_or_contractor=AuthorityParty(name="Unverified Builder", source="contractor list"),
            evidence=(
                AuthorityEvidence(
                    source_name="Road Inventory",
                    source_type="official_database",
                    claim="The road matches this record.",
                    matched_attribute="road",
                ),
                AuthorityEvidence(
                    source_name="Authority Registry",
                    source_type="official_database",
                    claim="Owner and maintainer verified.",
                    matched_attribute="road_owner",
                ),
                AuthorityEvidence(
                    source_name="Authority Registry",
                    source_type="official_database",
                    claim="Owner and maintainer verified.",
                    matched_attribute="maintenance_authority",
                ),
                AuthorityEvidence(
                    source_name="General Project Page",
                    source_type="government_portal",
                    claim="A contractor is mentioned in project material.",
                    matched_attribute="builder_or_contractor",
                ),
            ),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78&road=Civic%20Road")
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "verified")
        self.assertIsNone(data["builder_or_contractor"])
        self.assertEqual(data["evidence"][-1]["verification_state"], "not_verified")

    @patch("app.services.authority.authority_provider")
    def test_19_unknown_source_type_cannot_verify_authority(self, mock_provider):
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Claimed Owner"),
            evidence=(
                AuthorityEvidence(
                    source_name="Unregistered source",
                    source_type="private_directory",
                    claim="The road belongs to Claimed Owner.",
                    matched_attribute="road_owner",
                ),
            ),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78&road=Civic%20Road")
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])
        self.assertTrue(any("not approved" in item for item in data["limitations"]))


if __name__ == "__main__":
    unittest.main()
