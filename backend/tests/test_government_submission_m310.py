from datetime import datetime, timezone
import unittest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.schemas.authority import (
    AuthorityEvidence,
    AuthorityParty,
    AuthorityResult,
    OfficialSourceRecord,
)
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.services import complaint_case as cc_mod
from app.services import notification as notif_mod
from app.services.complaint_case import InMemoryComplaintCaseRepository
from app.services.government_submission import (
    SubmissionBlockedError,
    SubmissionNotReadyError,
    check_submission_readiness,
    prepare_government_submission,
)
from app.services.notification import InMemoryNotificationRepository


class TestGovernmentSubmissionM310(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

        # Register User 1
        reg1 = cls.client.post("/api/v1/auth/register", json={"email": "m310_user1@cvki.internal", "password": "Password123!", "full_name": "Gov User One"})
        if reg1.status_code in (200, 201):
            cls.token1 = reg1.cookies.get(settings.AUTH_COOKIE_NAME)
            cls.user1_id = reg1.json()["user"]["user_id"]
        else:
            login1 = cls.client.post("/api/v1/auth/login", json={"email": "m310_user1@cvki.internal", "password": "Password123!"})
            cls.token1 = login1.cookies.get(settings.AUTH_COOKIE_NAME)
            cls.user1_id = login1.json()["user"]["user_id"]
        cls.auth_headers1 = {"Authorization": f"Bearer {cls.token1}"}

        # Register User 2 (for cross-user ownership tests)
        reg2 = cls.client.post("/api/v1/auth/register", json={"email": "m310_user2@cvki.internal", "password": "Password123!", "full_name": "Gov User Two"})
        if reg2.status_code in (200, 201):
            cls.token2 = reg2.cookies.get(settings.AUTH_COOKIE_NAME)
            cls.user2_id = reg2.json()["user"]["user_id"]
        else:
            login2 = cls.client.post("/api/v1/auth/login", json={"email": "m310_user2@cvki.internal", "password": "Password123!"})
            cls.token2 = login2.cookies.get(settings.AUTH_COOKIE_NAME)
            cls.user2_id = login2.json()["user"]["user_id"]
        cls.auth_headers2 = {"Authorization": f"Bearer {cls.token2}"}

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def setUp(self):
        self.client.cookies.clear()
        self._orig_case_repo = cc_mod.case_repository
        self._orig_notif_repo = notif_mod.notification_repository
        self.case_repo = InMemoryComplaintCaseRepository()
        self.notif_repo = InMemoryNotificationRepository()
        cc_mod.set_case_repository(self.case_repo)
        notif_mod.set_notification_repository(self.notif_repo)

    def tearDown(self):
        cc_mod.set_case_repository(self._orig_case_repo)
        notif_mod.set_notification_repository(self._orig_notif_repo)

    def _create_sample_case(
        self,
        reference_id: str,
        authority_status: str = "verified",
        with_location: bool = True,
        with_description: bool = True,
        builder: AuthorityParty | None = None,
        sources: list[OfficialSourceRecord] | None = None,
        evidence: list[AuthorityEvidence] | None = None,
    ) -> ComplaintCase:
        now = datetime.now(timezone.utc)
        auth = AuthorityResult(
            authority_status=authority_status,
            road_owner=AuthorityParty(name="National Highways Authority of India (NHAI)", official_portal_url="https://nhai.gov.in") if authority_status != "not_verified" else None,
            maintenance_authority=AuthorityParty(name="NHAI Project Division", official_portal_url="https://nhai.gov.in") if authority_status != "not_verified" else None,
            builder_or_contractor=builder,
            evidence=evidence or [
                AuthorityEvidence(source_name="NHAI Register", source_type="official_portal", claim="NHAI maintains NH 44 corridor")
            ] if authority_status != "not_verified" else [],
            sources=sources or [
                OfficialSourceRecord(
                    source_id="src_nhai_01",
                    source_name="NHAI Portal",
                    source_type="government_portal",
                    source_url="https://nhai.gov.in",
                    source_domain="nhai.gov.in",
                )
            ] if authority_status != "not_verified" else [],
        )

        loc = ComplaintLocation(
            road="NH 44 Hosur Road" if with_location else None,
            city="Bengaluru" if with_location else None,
            latitude=12.9123 if with_location else None,
            longitude=77.6321 if with_location else None,
        )

        case = ComplaintCase(
            reference_id=reference_id,
            user_id=self.user1_id,
            status="submitted_to_cvki",
            created_at=now,
            updated_at=now,
            issue=CaseIssue(class_name="open_damaged_manhole", label="Open Manhole", severity="high", confidence=0.88),
            location=loc,
            authority=auth,
            complaint=CaseComplaint(
                language="en",
                title="Dangerous open manhole on NH 44",
                description="Large uncovered storm drain on highway shoulder causing acute accident risk." if with_description else " ",
            ),
            follow_up=FollowUp(guidance="Standard guidance"),
        )
        self.case_repo.save(case)
        return case

    # 1. Verified authority -> ready
    def test_01_verified_authority_ready(self):
        case = self._create_sample_case("CVKI-20261011-GOV001", authority_status="verified")
        readiness = check_submission_readiness(case)
        self.assertEqual(readiness.readiness_status, "ready")
        self.assertEqual(readiness.submission_status, "READY_FOR_REVIEW")
        self.assertEqual(readiness.authority_status, "verified")
        self.assertEqual(len(readiness.missing_fields), 0)
        self.assertIn("verified government authority", readiness.reasons[0])

    # 2. Partially verified authority -> review required
    def test_02_partially_verified_review_required(self):
        case = self._create_sample_case("CVKI-20261011-GOV002", authority_status="partially_verified")
        readiness = check_submission_readiness(case)
        self.assertEqual(readiness.readiness_status, "partially_ready")
        self.assertEqual(readiness.submission_status, "READY_FOR_REVIEW")
        self.assertEqual(readiness.authority_status, "partially_verified")
        self.assertIn("Citizen review is required", readiness.reasons[0])

    # 3. Not verified authority -> blocked/not ready
    def test_03_not_verified_authority_blocked(self):
        case = self._create_sample_case("CVKI-20261011-GOV003", authority_status="not_verified")
        readiness = check_submission_readiness(case)
        self.assertEqual(readiness.readiness_status, "blocked")
        self.assertEqual(readiness.submission_status, "SUBMISSION_BLOCKED")
        self.assertIn("blocked to prevent misdirected dispatch", readiness.reasons[0])

    # 4. Missing location -> not ready
    def test_04_missing_location(self):
        case = self._create_sample_case("CVKI-20261011-GOV004", authority_status="verified", with_location=False)
        readiness = check_submission_readiness(case)
        self.assertEqual(readiness.readiness_status, "not_ready")
        self.assertIn("location", readiness.missing_fields)

    # 5. Missing complaint description -> not ready
    def test_05_missing_complaint_description(self):
        case = self._create_sample_case("CVKI-20261011-GOV005", authority_status="verified", with_description=False)
        readiness = check_submission_readiness(case)
        self.assertEqual(readiness.readiness_status, "not_ready")
        self.assertIn("complaint.description", readiness.missing_fields)

    # 6. Missing authority object -> blocked
    def test_06_missing_authority(self):
        case = self._create_sample_case("CVKI-20261011-GOV006")
        case.authority = None
        readiness = check_submission_readiness(case)
        self.assertEqual(readiness.readiness_status, "blocked")
        self.assertEqual(readiness.submission_status, "SUBMISSION_BLOCKED")

    # 7. Official source preservation
    def test_07_official_source_preservation(self):
        sources = [
            OfficialSourceRecord(
                source_id="src_nhai_portal",
                source_name="NHAI Central Registry",
                source_type="government_portal",
                source_url="https://nhai.gov.in/projects",
                source_domain="nhai.gov.in",
            )
        ]
        case = self._create_sample_case("CVKI-20261011-GOV007", authority_status="verified", sources=sources)
        readiness = check_submission_readiness(case)
        self.assertEqual(len(readiness.official_sources), 1)
        self.assertEqual(readiness.official_sources[0].source_name, "NHAI Central Registry")
        self.assertEqual(readiness.official_sources[0].source_domain, "nhai.gov.in")

    # 8. No fabricated government URL
    def test_08_no_fabricated_government_url(self):
        # Case with verified authority but no portal URL supplied
        auth = AuthorityResult(
            authority_status="verified",
            road_owner=AuthorityParty(name="PWD State Division", official_portal_url=None),
            maintenance_authority=AuthorityParty(name="PWD Sub-division", official_portal_url=None),
            sources=[],
        )
        case = self._create_sample_case("CVKI-20261011-GOV008")
        case.authority = auth
        readiness = check_submission_readiness(case)
        self.assertEqual(len(readiness.official_sources), 0)
        # Ensure no URL was fabricated in sources
        for s in readiness.official_sources:
            self.assertIsNotNone(s.source_url)

    # 9. No fabricated reference number
    def test_09_no_fabricated_reference_number(self):
        import asyncio
        case = self._create_sample_case("CVKI-20261011-GOV009", authority_status="verified")
        updated_case, response = asyncio.run(prepare_government_submission(case, user_id=self.user1_id))
        # Package and record should have CVKI reference, but NOT claim any fake government tracking token
        self.assertEqual(response.package.reference_id, "CVKI-20261011-GOV009")
        self.assertEqual(response.package.submission_status, "NOT_SUBMITTED")
        # Ensure limitations explicitly explain this
        self.assertTrue(any("does not generate government acknowledgment" in lim for lim in response.limitations))

    # 10. Prepare submission package via API
    def test_10_prepare_submission_package(self):
        case = self._create_sample_case("CVKI-20261011-GOV010", authority_status="verified")
        res = self.client.post(f"/api/v1/complaint/cases/{case.reference_id}/prepare-submission", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["reference_id"], "CVKI-20261011-GOV010")
        self.assertEqual(data["submission_status"], "PREPARED")
        self.assertEqual(data["readiness_status"], "ready")
        self.assertEqual(data["package"]["submission_status"], "NOT_SUBMITTED")
        self.assertEqual(data["package"]["road"], "NH 44 Hosur Road")
        self.assertIsNotNone(data["package"]["maintenance_authority"])

    # 11. Owner-only access (readiness & preparation)
    def test_11_owner_only_access(self):
        case = self._create_sample_case("CVKI-20261011-GOV011", authority_status="verified")
        # User 1 is owner
        res1 = self.client.get(f"/api/v1/complaint/cases/{case.reference_id}/submission-readiness", headers=self.auth_headers1)
        self.assertEqual(res1.status_code, 200)

        # User 2 is not owner
        res2 = self.client.get(f"/api/v1/complaint/cases/{case.reference_id}/submission-readiness", headers=self.auth_headers2)
        self.assertEqual(res2.status_code, 404)

        res2_prep = self.client.post(f"/api/v1/complaint/cases/{case.reference_id}/prepare-submission", headers=self.auth_headers2)
        self.assertEqual(res2_prep.status_code, 404)

    # 12. Cross-user access denied / unauthorized
    def test_12_unauthorized_access(self):
        case = self._create_sample_case("CVKI-20261011-GOV012")
        # Without headers
        res = self.client.get(f"/api/v1/complaint/cases/{case.reference_id}/submission-readiness")
        self.assertEqual(res.status_code, 401)
        res_prep = self.client.post(f"/api/v1/complaint/cases/{case.reference_id}/prepare-submission")
        self.assertEqual(res_prep.status_code, 401)

    # 13. Government status remains NOT_SUBMITTED
    def test_13_status_remains_not_submitted(self):
        case = self._create_sample_case("CVKI-20261011-GOV013", authority_status="verified")
        res = self.client.post(f"/api/v1/complaint/cases/{case.reference_id}/prepare-submission", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["package"]["submission_status"], "NOT_SUBMITTED")

        # Also verify case status endpoint still returns not_submitted
        res_stat = self.client.get(f"/api/v1/complaint/cases/{case.reference_id}/status", headers=self.auth_headers1)
        self.assertEqual(res_stat.json()["external_submission_status"], "not_submitted")

    # 14. Builder / contractor only when official evidence supports it
    def test_14_builder_contractor_evidence_requirement(self):
        import asyncio
        # Case A: Builder without supporting official evidence
        builder_no_evidence = AuthorityParty(name="Unverified Construction Corp", source=None)
        case_a = self._create_sample_case(
            "CVKI-20261011-GOV014A",
            authority_status="verified",
            builder=builder_no_evidence,
            evidence=[AuthorityEvidence(source_name="Portal", source_type="db", claim="Road maintained by NHAI")],
        )
        _, resp_a = asyncio.run(prepare_government_submission(case_a, user_id=self.user1_id))
        self.assertIsNone(resp_a.package.builder_or_contractor)

        # Case B: Builder with explicit official source / evidence
        builder_supported = AuthorityParty(
            name="L&T Infrastructure Concessionaire",
            source="NHAI Concession Agreement Record",
        )
        case_b = self._create_sample_case(
            "CVKI-20261011-GOV014B",
            authority_status="verified",
            builder=builder_supported,
            evidence=[AuthorityEvidence(source_name="NHAI Contract", source_type="official_contract", claim="Contractor L&T executed BOT project")],
        )
        _, resp_b = asyncio.run(prepare_government_submission(case_b, user_id=self.user1_id))
        self.assertIsNotNone(resp_b.package.builder_or_contractor)
        self.assertEqual(resp_b.package.builder_or_contractor.name, "L&T Infrastructure Concessionaire")

    # 15. Case creation regression
    def test_15_case_creation_regression(self):
        payload = {
            "issue": {"class_name": "road_waterlogging", "label": "Road Waterlogging", "severity": "medium", "confidence": 0.81},
            "location": {"road": "Outer Ring Road", "city": "Bengaluru", "latitude": 12.93, "longitude": 77.68},
            "complaint": {"language": "en", "title": "Severe flooding", "description": "Water accumulated on highway lane."},
            "evidence": ["photo.jpg"],
        }
        res = self.client.post("/api/v1/complaint/cases", json=payload, headers=self.auth_headers1)
        self.assertIn(res.status_code, (200, 201))
        data = res.json()
        self.assertIn("reference_id", data)
        self.assertEqual(data["issue"]["class_name"], "road_waterlogging")

    # 16. Submission preparation persists to repository
    def test_16_persistence_of_government_submission(self):
        case = self._create_sample_case("CVKI-20261011-GOV016", authority_status="verified")
        res = self.client.post(f"/api/v1/complaint/cases/{case.reference_id}/prepare-submission", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 200)

        # Reload case from repository
        import inspect
        res_case = self.case_repo.get(case.reference_id)
        if inspect.isawaitable(res_case):
            import asyncio
            reloaded = asyncio.run(res_case)
        else:
            reloaded = res_case
        self.assertIsNotNone(reloaded.government_submission)
        self.assertEqual(reloaded.government_submission.submission_status, "PREPARED")
        self.assertEqual(reloaded.government_submission.package.reference_id, case.reference_id)

    # 17. Malformed request / non-existent case
    def test_17_malformed_request_or_not_found(self):
        res = self.client.get("/api/v1/complaint/cases/NON_EXISTENT_CASE_999/submission-readiness", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 404)

        res_prep = self.client.post("/api/v1/complaint/cases/NON_EXISTENT_CASE_999/prepare-submission", headers=self.auth_headers1)
        self.assertEqual(res_prep.status_code, 404)

        # Blocked preparation returns 400
        case_blocked = self._create_sample_case("CVKI-20261011-GOV017B", authority_status="not_verified")
        res_blocked = self.client.post(f"/api/v1/complaint/cases/{case_blocked.reference_id}/prepare-submission", headers=self.auth_headers1)
        self.assertEqual(res_blocked.status_code, 400)


if __name__ == "__main__":
    unittest.main()
