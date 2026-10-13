import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.authority import AuthorityEvidence, AuthorityParty
from app.services.authority import (
    AuthorityLookup,
    AuthorityProviderError,
    AuthorityProviderTimeout,
)


class TestAuthorityAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_default_context_without_authoritative_source_is_not_verified(self):
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78&city=Sample%20City")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["authority"]["authority_status"], "not_verified")
        self.assertIsNone(data["authority"]["road_owner"])
        self.assertIsNone(data["authority"]["maintenance_authority"])
        self.assertIsNone(data["authority"]["builder_or_contractor"])
        self.assertEqual(data["authority"]["evidence"], [])
        self.assertIn("does not by itself establish", data["authority"]["limitations"][0])

    def test_invalid_coordinates_are_rejected(self):
        self.assertEqual(self.client.get("/api/v1/authority/resolve?latitude=91&longitude=0").status_code, 422)
        self.assertEqual(self.client.get("/api/v1/authority/resolve?latitude=0&longitude=181").status_code, 422)
        self.assertEqual(self.client.get("/api/v1/authority/resolve").status_code, 422)

    @patch("app.services.authority.authority_provider")
    def test_verified_authority_requires_evidence_and_separates_roles(self, provider):
        provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Road Owner Authority", type="public owner", source="Official road register"),
            maintenance_authority=AuthorityParty(name="Maintenance Authority", type="public maintainer", source="Official maintenance register"),
            builder_or_contractor=AuthorityParty(name="Project Contractor", type="contractor", source="Official project document"),
            evidence=(
                AuthorityEvidence(source_name="Official road register", source_type="official_database", reference="record-0", claim="Road matches road register.", matched_attribute="road"),
                AuthorityEvidence(source_name="Official road register", source_type="official_database", reference="record-1", claim="Road owner is Road Owner Authority.", matched_attribute="road_owner"),
                AuthorityEvidence(source_name="Official maintenance register", source_type="official_government", reference="record-2", claim="Maintenance authority is Maintenance Authority.", matched_attribute="maintenance_authority"),
                AuthorityEvidence(source_name="Official contract register", source_type="official_contract_record", reference="record-3", claim="Project Contractor is the named concessionaire.", matched_attribute="builder_or_contractor"),
            ),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 200)
        authority = response.json()["authority"]
        self.assertEqual(authority["authority_status"], "verified")
        self.assertEqual(authority["road_owner"]["name"], "Road Owner Authority")
        self.assertEqual(authority["maintenance_authority"]["name"], "Maintenance Authority")
        self.assertEqual(authority["builder_or_contractor"]["name"], "Project Contractor")
        self.assertEqual(len(authority["evidence"]), 4)
        self.assertEqual(authority["citizen_explanation"], "Available source records are explicitly linked to this road and support both road ownership and maintenance responsibility.")

    @patch("app.services.authority.authority_provider")
    def test_road_owner_only_is_partially_verified(self, provider):
        provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Road Owner Authority", source="Official register"),
            evidence=(
                AuthorityEvidence(source_name="Road Inventory", source_type="official_database", claim="The reported road matches.", matched_attribute="road"),
                AuthorityEvidence(source_name="Official register", source_type="official_database", claim="Road owner is verified.", matched_attribute="road_owner"),
            ),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.json()["authority"]["authority_status"], "partially_verified")
        self.assertIsNone(response.json()["authority"]["maintenance_authority"])

    @patch("app.services.authority.authority_provider")
    def test_missing_evidence_cannot_verify_claim(self, provider):
        provider.lookup.return_value = AuthorityLookup(
            maintenance_authority=AuthorityParty(name="Unsubstantiated Authority"),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.json()["authority"]["authority_status"], "not_verified")
        self.assertEqual(response.json()["authority"]["evidence"], [])

    @patch("app.services.authority.authority_provider")
    def test_builder_unavailable_remains_null(self, provider):
        provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Owner", source="Official register"),
            maintenance_authority=AuthorityParty(name="Maintainer", source="Official register"),
            evidence=(AuthorityEvidence(source_name="Official register", source_type="official_database", claim="Roles verified."),),
        )
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertIsNone(response.json()["authority"]["builder_or_contractor"])

    @patch("app.services.authority.authority_provider")
    def test_provider_timeout_is_safe(self, provider):
        provider.lookup.side_effect = AuthorityProviderTimeout
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 504)
        self.assertNotIn("Traceback", response.text)

    @patch("app.services.authority.authority_provider")
    def test_provider_error_is_safe(self, provider):
        provider.lookup.side_effect = AuthorityProviderError
        response = self.client.get("/api/v1/authority/resolve?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("Traceback", response.text)


if __name__ == "__main__":
    unittest.main()
