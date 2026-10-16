"""
CVKI M7.6 Citizen Resolution Verification Test Suite.
Verifies all core M7.6 requirements:
1. Epistemic Separation:
   - External government status ("RESOLVED") does NOT automatically mutate internal ComplaintCase.status.
2. Citizen Confirmation:
   - CONFIRMED_RESOLVED evaluates to VERIFIED_RESOLVED with is_physical_resolution_verified = True.
3. Citizen Dispute:
   - STILL_UNRESOLVED evaluates to CITIZEN_DISPUTED with is_physical_resolution_verified = False.
   - Triggers citizen dispute notification.
4. Partial Resolution:
   - PARTIALLY_RESOLVED evaluates to PARTIALLY_RESOLVED with is_physical_resolution_verified = False.
5. Inability to Verify:
   - CANNOT_VERIFY evaluates to INSUFFICIENT_EVIDENCE with is_physical_resolution_verified = False.
6. Uncertainty Routing:
   - Notes containing uncertainty phrases ("not sure", "maybe", etc.) route CONFIRMED_RESOLVED to NEEDS_REVIEW.
7. Operator / Admin Review:
   - Staff/Admin review transitions state (e.g., NEEDS_REVIEW -> VERIFIED_RESOLVED).
   - Review history and timestamps recorded.
   - Non-admin cannot modify CLOSED_UNVERIFIED.
   - Invalid transitions rejected with ValueError / 400.
8. Provenance Emission:
   - ClaimType.RESOLUTION_VERIFICATION emitted in ProvenanceEngine.
9. Knowledge Graph Integration:
   - NodeType.RESOLUTION_VERIFICATION and RelationType.HAS_RESOLUTION_VERIFICATION edge recorded.
10. RBAC Enforcement:
    - Citizen cannot submit verification for another citizen's case (404).
    - Citizen cannot review/override verification (403).
    - Authority / Admin can review verifications.
11. Multi-submission & History:
    - Multiple submissions preserved chronologically in latest and history endpoints.
"""

import asyncio
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.main import app
from app.models.roles import UserRole
from app.schemas.authority import AuthorityParty, AuthorityResult, OfficialSourceRecord
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import CaseComplaint, CaseIssue, ComplaintCase, FollowUp
from app.schemas.government_reference import (
    GovernmentReferenceMapping,
    ReferenceMappingState,
)
from app.schemas.knowledge_graph import (
    canonical_case_key,
    canonical_resolution_verification_key,
)
from app.schemas.provenance import ClaimType, SourceType, VerificationState
from app.schemas.resolution_verification import (
    CitizenResolutionResponse,
    CitizenResolutionVerificationRecord,
    CitizenResolutionVerificationSubmitRequest,
    ResolutionVerificationReviewRequest,
    ResolutionVerificationStatus,
)
import app.services.complaint_case as complaint_case_module
from app.services.government_reference_service import (
    GovernmentReferenceService,
    InMemoryGovernmentReferenceRepository,
    set_government_reference_service,
)
from app.services.knowledge_graph import (
    CivicKnowledgeGraphService,
    InMemoryKnowledgeGraphRepository,
    NodeType,
    RelationType,
    get_knowledge_graph_service,
    set_knowledge_graph_service,
)
import app.services.notification as notification_module
from app.services.provenance_engine import (
    EvidenceProvenanceEngine,
    InMemoryProvenanceRepository,
    get_provenance_engine,
    set_provenance_engine,
)
from app.services.resolution_verification_service import (
    InMemoryResolutionVerificationRepository,
    ResolutionVerificationService,
    get_resolution_verification_service,
    set_resolution_verification_service,
)


def run_async(coro):
    return asyncio.run(coro)


def build_test_case(
    ref_id: str = "CASE-2026-M76-001",
    user_id: str = "citizen_user_001",
    status: str = "submitted_to_cvki",
) -> ComplaintCase:
    now = datetime.now(timezone.utc)
    return ComplaintCase(
        reference_id=ref_id,
        user_id=user_id,
        status=status,
        issue=CaseIssue(
            class_name="deep_pothole",
            label="Deep Pothole",
            severity="high",
            confidence=0.95,
        ),
        location=ComplaintLocation(
            latitude=12.9716,
            longitude=77.5946,
            road="National Highway 44",
            area="Electronic City",
            city="Bengaluru",
            district="Bengaluru Urban",
            state="Karnataka",
            accuracy_m=10.0,
        ),
        complaint=CaseComplaint(
            language="en",
            title="Severe Pothole Cluster on NH-44",
            description="Deep crater potholes hazardous to two-wheelers.",
        ),
        follow_up=FollowUp(guidance="Reported to authority."),
        authority=AuthorityResult(
            authority_status="verified",
            confidence_score=0.96,
            road_owner=AuthorityParty(
                name="NHAI", type="National Highway", official_portal_url="https://nhai.gov.in"
            ),
            maintenance_authority=AuthorityParty(
                name="NHAI", type="National Highway", official_portal_url="https://nhai.gov.in"
            ),
            sources=[
                OfficialSourceRecord(
                    source_id="src_nhai_portal",
                    source_name="NHAI Portal",
                    source_type="government_portal",
                    domain="nhai.gov.in",
                    url="https://nhai.gov.in",
                    retrieved_at=now,
                )
            ],
            resolved_at=now,
        ),
        created_at=now,
        updated_at=now,
    )


class TestCitizenResolutionVerificationM76(unittest.TestCase):
    def setUp(self):
        self.verif_repo = InMemoryResolutionVerificationRepository()
        self.verif_service = ResolutionVerificationService(repository=self.verif_repo)
        set_resolution_verification_service(self.verif_service)

        self.ref_repo = InMemoryGovernmentReferenceRepository()
        self.ref_service = GovernmentReferenceService(repository=self.ref_repo)
        set_government_reference_service(self.ref_service)

        self.prov_repo = InMemoryProvenanceRepository()
        self.prov_engine = EvidenceProvenanceEngine(repository=self.prov_repo)
        set_provenance_engine(self.prov_engine)

        self.kg_repo = InMemoryKnowledgeGraphRepository()
        self.kg_service = CivicKnowledgeGraphService(repository=self.kg_repo)
        set_knowledge_graph_service(self.kg_service)

        # Set up in-memory case repository
        self.original_case_repo = complaint_case_module.case_repository
        self.case_repo = complaint_case_module.InMemoryComplaintCaseRepository()
        complaint_case_module.set_case_repository(self.case_repo)

        # Set up in-memory notification repository
        self.notif_repo = notification_module.InMemoryNotificationRepository()
        self.original_notif_repo = notification_module.notification_repository
        notification_module.set_notification_repository(self.notif_repo)

        # Mock current user default
        self.current_user = AuthenticatedUser(
            user_id="citizen_user_001",
            role=UserRole.CITIZEN,
            email="citizen@example.com",
        )

        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

        # Set up test case and reference mapping
        self.case = build_test_case(ref_id="CASE-2026-M76-001", user_id="citizen_user_001")
        self.case_repo.save(self.case)

        # Add confirmed reference mapping
        mapping = GovernmentReferenceMapping(
            mapping_id="map-m76-001",
            submission_id="sub-m76-001",
            cvki_reference_id="CASE-2026-M76-001",
            integration_id="bbmp_sahaaya",
            external_reference_id="BBMP-REV-2026-999",
            mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            authority_party="BBMP",
            created_at=datetime.now(timezone.utc),
            confirmed_at=datetime.now(timezone.utc),
        )
        self.ref_repo.save(mapping)

    def tearDown(self):
        complaint_case_module.set_case_repository(self.original_case_repo)
        notification_module.set_notification_repository(self.original_notif_repo)
        app.dependency_overrides.clear()
        self.verif_repo.clear()
        self.ref_repo.clear()
        self.prov_repo.clear()
        self.kg_repo.clear()

    # -------------------------------------------------------------------------
    # 1. Citizen confirms resolution (CONFIRMED_RESOLVED)
    # -------------------------------------------------------------------------
    def test_citizen_confirms_resolution_verified_resolved(self):
        payload = {
            "citizen_response": "CONFIRMED_RESOLVED",
            "citizen_notes": "The pothole was completely filled with asphalt and steamrolled today.",
            "evidence_photo_url": "https://storage.cvki.org/evidence/verified_repair.jpg",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }

        resp = self.client.post(
            "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification",
            json=payload,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()

        self.assertEqual(data["verification_status"], "VERIFIED_RESOLVED")
        self.assertTrue(data["is_physical_resolution_verified"])
        self.assertEqual(data["citizen_response"], "CONFIRMED_RESOLVED")
        self.assertEqual(data["cvki_reference_id"], "CASE-2026-M76-001")
        self.assertEqual(data["integration_id"], "bbmp_sahaaya")

        # Invariant check: ComplaintCase.status must NOT have mutated
        stored_case = self.case_repo.get("CASE-2026-M76-001")
        self.assertEqual(stored_case.status, "submitted_to_cvki")

    # -------------------------------------------------------------------------
    # 2. Citizen disputes resolution (STILL_UNRESOLVED)
    # -------------------------------------------------------------------------
    def test_citizen_disputes_resolution_citizen_disputed(self):
        with patch(
            "app.services.resolution_verification_service.trigger_resolution_verification_disputed_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            payload = {
                "citizen_response": "STILL_UNRESOLVED",
                "citizen_notes": "Portal marked it resolved, but the crater is still open and full of water.",
                "evidence_photo_url": "https://storage.cvki.org/evidence/still_broken.jpg",
                "latitude": 12.9716,
                "longitude": 77.5946,
            }

            resp = self.client.post(
                "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification",
                json=payload,
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()

            self.assertEqual(data["verification_status"], "CITIZEN_DISPUTED")
            self.assertFalse(data["is_physical_resolution_verified"])
            self.assertEqual(data["citizen_response"], "STILL_UNRESOLVED")

            # Notification triggered
            mock_notify.assert_called_once()

    # -------------------------------------------------------------------------
    # 3. Partial resolution (PARTIALLY_RESOLVED)
    # -------------------------------------------------------------------------
    def test_citizen_partial_resolution(self):
        payload = {
            "citizen_response": "PARTIALLY_RESOLVED",
            "citizen_notes": "Only 1 of 3 potholes was filled with loose gravel.",
        }

        resp = self.client.post(
            "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification",
            json=payload,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()

        self.assertEqual(data["verification_status"], "PARTIALLY_RESOLVED")
        self.assertFalse(data["is_physical_resolution_verified"])

    # -------------------------------------------------------------------------
    # 4. Cannot verify (CANNOT_VERIFY)
    # -------------------------------------------------------------------------
    def test_citizen_cannot_verify(self):
        payload = {
            "citizen_response": "CANNOT_VERIFY",
            "citizen_notes": "I moved out of the city and cannot check the site.",
        }

        resp = self.client.post(
            "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification",
            json=payload,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()

        self.assertEqual(data["verification_status"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(data["is_physical_resolution_verified"])

    # -------------------------------------------------------------------------
    # 5. Uncertainty phrases route to NEEDS_REVIEW
    # -------------------------------------------------------------------------
    def test_uncertainty_in_notes_routes_to_needs_review(self):
        payload = {
            "citizen_response": "CONFIRMED_RESOLVED",
            "citizen_notes": "I think it might be fixed, but I am not sure since it was dark.",
        }

        resp = self.client.post(
            "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification",
            json=payload,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()

        self.assertEqual(data["verification_status"], "NEEDS_REVIEW")
        self.assertFalse(data["is_physical_resolution_verified"])

    # -------------------------------------------------------------------------
    # 6. Operator / Admin review transition
    # -------------------------------------------------------------------------
    def test_admin_review_transition(self):
        # Step A: Citizen submits uncertain verification
        rec = run_async(
            self.verif_service.submit_verification(
                case=self.case,
                req=CitizenResolutionVerificationSubmitRequest(
                    citizen_response=CitizenResolutionResponse.CONFIRMED_RESOLVED,
                    citizen_notes="Maybe it was fixed, doubt it will last.",
                ),
                citizen_user_id="citizen_user_001",
                citizen_role=UserRole.CITIZEN,
            )
        )
        self.assertEqual(rec.verification_status, ResolutionVerificationStatus.NEEDS_REVIEW)
        verif_id = rec.verification_id

        # Step B: Switch to Admin user
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="admin_001",
            role=UserRole.ADMIN,
            email="admin@civki.gov",
        )

        with patch(
            "app.services.resolution_verification_service.trigger_resolution_verification_reviewed_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            review_payload = {
                "verification_status": "VERIFIED_RESOLVED",
                "reviewer_notes": "Operator inspected road surveillance feed and confirmed site asphalt resurfaced.",
                "override_physical_resolution": True,
            }

            resp = self.client.post(
                f"/api/v1/admin/government/cases/CASE-2026-M76-001/resolution-verification/{verif_id}/review",
                json=review_payload,
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()

            self.assertEqual(data["verification_status"], "VERIFIED_RESOLVED")
            self.assertTrue(data["is_physical_resolution_verified"])
            self.assertEqual(data["reviewer_user_id"], "admin_001")
            self.assertEqual(data["reviewer_notes"], review_payload["reviewer_notes"])

            mock_notify.assert_called_once()

    # -------------------------------------------------------------------------
    # 7. Invalid review transition rejection
    # -------------------------------------------------------------------------
    def test_invalid_review_transition_rejected(self):
        rec = run_async(
            self.verif_service.submit_verification(
                case=self.case,
                req=CitizenResolutionVerificationSubmitRequest(
                    citizen_response=CitizenResolutionResponse.CONFIRMED_RESOLVED,
                    citizen_notes="Clean repair completed.",
                ),
                citizen_user_id="citizen_user_001",
                citizen_role=UserRole.CITIZEN,
            )
        )
        self.assertEqual(rec.verification_status, ResolutionVerificationStatus.VERIFIED_RESOLVED)
        verif_id = rec.verification_id

        # Switch to Admin
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="admin_001",
            role=UserRole.ADMIN,
            email="admin@civki.gov",
        )

        # Illegal transition to PENDING
        resp = self.client.post(
            f"/api/v1/admin/government/cases/CASE-2026-M76-001/resolution-verification/{verif_id}/review",
            json={"verification_status": "PENDING", "reviewer_notes": "Invalid rollback"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Cannot transition a reviewed verification back to PENDING", resp.json()["detail"])

    # -------------------------------------------------------------------------
    # 8. Provenance claim emission
    # -------------------------------------------------------------------------
    def test_provenance_claim_emission(self):
        rec = run_async(
            self.verif_service.submit_verification(
                case=self.case,
                req=CitizenResolutionVerificationSubmitRequest(
                    citizen_response=CitizenResolutionResponse.CONFIRMED_RESOLVED,
                    citizen_notes="Pothole completely filled.",
                ),
                citizen_user_id="citizen_user_001",
                citizen_role=UserRole.CITIZEN,
            )
        )

        records = self.prov_repo.find_by_case("CASE-2026-M76-001")
        verif_records = [r for r in records if r.claim_type == ClaimType.RESOLUTION_VERIFICATION]
        self.assertEqual(len(verif_records), 1)

        claim = verif_records[0]
        self.assertEqual(claim.case_reference, "CASE-2026-M76-001")
        self.assertEqual(claim.source_type, SourceType.CITIZEN_REPORT)
        self.assertEqual(claim.metadata["verification_id"], rec.verification_id)
        self.assertTrue(claim.metadata["is_physical_resolution_verified"])

    # -------------------------------------------------------------------------
    # 9. Knowledge Graph integration
    # -------------------------------------------------------------------------
    def test_knowledge_graph_integration(self):
        rec = run_async(
            self.verif_service.submit_verification(
                case=self.case,
                req=CitizenResolutionVerificationSubmitRequest(
                    citizen_response=CitizenResolutionResponse.STILL_UNRESOLVED,
                    citizen_notes="Crater still open.",
                ),
                citizen_user_id="citizen_user_001",
                citizen_role=UserRole.CITIZEN,
            )
        )

        # Check node
        node_key = canonical_resolution_verification_key("CASE-2026-M76-001", rec.verification_id)
        node = self.kg_repo.get_node_by_key(node_key)
        self.assertIsNotNone(node)
        self.assertEqual(node.node_type, NodeType.RESOLUTION_VERIFICATION)
        self.assertEqual(node.metadata["verification_status"], "CITIZEN_DISPUTED")

        # Check edge
        edges = self.kg_repo.all_edges()
        verif_edges = [
            e
            for e in edges
            if e.relation_type == RelationType.HAS_RESOLUTION_VERIFICATION
            and e.to_node == node_key
        ]
        self.assertEqual(len(verif_edges), 1)
        self.assertEqual(verif_edges[0].from_node, canonical_case_key("CASE-2026-M76-001"))

    # -------------------------------------------------------------------------
    # 10. RBAC Enforcement
    # -------------------------------------------------------------------------
    def test_rbac_citizen_forbidden_from_other_citizen_case(self):
        # Current user is citizen_user_002, but case belongs to citizen_user_001
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_user_002",
            role=UserRole.CITIZEN,
            email="other_citizen@example.com",
        )

        resp = self.client.post(
            "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification",
            json={"citizen_response": "CONFIRMED_RESOLVED"},
        )
        self.assertEqual(resp.status_code, 404)

        resp_latest = self.client.get(
            "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification"
        )
        self.assertEqual(resp_latest.status_code, 404)

    def test_rbac_citizen_cannot_review_verifications(self):
        rec = run_async(
            self.verif_service.submit_verification(
                case=self.case,
                req=CitizenResolutionVerificationSubmitRequest(
                    citizen_response=CitizenResolutionResponse.CONFIRMED_RESOLVED,
                ),
                citizen_user_id="citizen_user_001",
                citizen_role=UserRole.CITIZEN,
            )
        )

        # Citizen attempts to review
        resp = self.client.post(
            f"/api/v1/admin/government/cases/CASE-2026-M76-001/resolution-verification/{rec.verification_id}/review",
            json={"verification_status": "CLOSED_UNVERIFIED", "reviewer_notes": "Unauthorized attempt"},
        )
        self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------------------
    # 11. Multi-submission history & latest endpoint
    # -------------------------------------------------------------------------
    def test_verification_history_and_latest(self):
        # Submission 1: Disputed
        run_async(
            self.verif_service.submit_verification(
                case=self.case,
                req=CitizenResolutionVerificationSubmitRequest(
                    citizen_response=CitizenResolutionResponse.STILL_UNRESOLVED,
                    citizen_notes="Still open.",
                ),
                citizen_user_id="citizen_user_001",
                citizen_role=UserRole.CITIZEN,
            )
        )

        # Submission 2: Confirmed resolved
        run_async(
            self.verif_service.submit_verification(
                case=self.case,
                req=CitizenResolutionVerificationSubmitRequest(
                    citizen_response=CitizenResolutionResponse.CONFIRMED_RESOLVED,
                    citizen_notes="Finally patched properly.",
                ),
                citizen_user_id="citizen_user_001",
                citizen_role=UserRole.CITIZEN,
            )
        )

        # Latest endpoint
        resp_latest = self.client.get(
            "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification"
        )
        self.assertEqual(resp_latest.status_code, 200)
        latest_data = resp_latest.json()
        self.assertEqual(latest_data["citizen_response"], "CONFIRMED_RESOLVED")
        self.assertEqual(latest_data["verification_status"], "VERIFIED_RESOLVED")

        # History endpoint
        resp_hist = self.client.get(
            "/api/v1/government/cases/CASE-2026-M76-001/resolution-verification/history"
        )
        self.assertEqual(resp_hist.status_code, 200)
        hist_data = resp_hist.json()
        self.assertEqual(hist_data["total"], 2)
        self.assertEqual(hist_data["verifications"][0]["citizen_response"], "CONFIRMED_RESOLVED")
        self.assertEqual(hist_data["verifications"][1]["citizen_response"], "STILL_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
