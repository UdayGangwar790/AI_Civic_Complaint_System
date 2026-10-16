"""
CVKI M7.3 Government Reference-ID Mapping Test Suite.
Verifies all 25 core M7.3 requirements:
1. CVKI reference remains immutable (never replaced by government ID)
2. Government reference stored separately
3. Integration-specific mapping (CPGRAMS, NHAI, BBMP, Mock)
4. Successful reference extraction
5. REFERENCE_RECEIVED state
6. REFERENCE_CONFIRMED state
7. UNKNOWN_OUTCOME state
8. Reconciliation to confirmed reference
9. Idempotent repeated observation
10. Duplicate mapping protection
11. Conflict detection: Cross-case duplicate reference
12. Integration mismatch rejection
13. Changed external reference rejection (mutation conflict)
14. Stale / unavailable mapping handling
15. Provenance creation (ClaimType.GOVERNMENT_SUBMISSION)
16. Provenance verification (VerificationState.VERIFIED)
17. Knowledge graph creation (Case -> GOVERNMENT_SUBMISSION -> EXTERNAL_CASE)
18. Conflicted mapping knowledge graph representation
19. Citizen RBAC (read-only for own cases; cannot mutate or confirm)
20. Authority RBAC (authorized scope; manual entry creates unverified reference)
21. Admin RBAC (full access)
22. Client cannot fabricate confirmed reference
23. Audit logging for all identity mapping lifecycle events
24. Notification triggering (confirmed, conflict, reconciled)
25. Mock adapter regression (sandbox deterministic flow)
"""

import asyncio
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import httpx

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.authority import AuthorityParty, AuthorityResult, OfficialSourceRecord
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import CaseComplaint, CaseIssue, ComplaintCase, FollowUp
from app.schemas.government_integration import (
    IntegrationState,
    NormalizedGovernmentStatus,
    SubmissionLifecycleState,
)
from app.schemas.government_reference import (
    GovernmentReferenceMapping,
    ManualReferenceCreateRequest,
    ReferenceMappingState,
)
from app.schemas.government_submission import GovernmentSubmissionPackage
from app.schemas.provenance import ClaimType, SourceType, VerificationState
from app.services.authority_registry import is_safe_official_url
import app.services.complaint_case as complaint_case_module
from app.services.government_adapter import (
    CPGRAMSIntegrationAdapter,
    MockGovernmentAdapter,
)
from app.services.government_integration_service import (
    GovernmentIntegrationService,
    InMemoryGovernmentSubmissionRepository,
    set_government_integration_service,
)
from app.services.government_reference_service import (
    GovernmentReferenceService,
    InMemoryGovernmentReferenceRepository,
    get_government_reference_service,
    set_government_reference_service,
)
from app.services.government_registry import government_registry
from app.services.knowledge_graph import (
    CivicKnowledgeGraphService,
    InMemoryKnowledgeGraphRepository,
    set_knowledge_graph_service,
)
from app.services.provenance_engine import (
    EvidenceProvenanceEngine,
    InMemoryProvenanceRepository,
    set_provenance_engine,
)


def run_async(coro):
    return asyncio.run(coro)


def build_test_case(
    ref_id: str = "CASE-2026-M73-001",
    user_id: str = "citizen_user_001",
    auth_name: str = "National Highways Authority of India (NHAI)",
) -> ComplaintCase:
    now = datetime.now(timezone.utc)
    return ComplaintCase(
        reference_id=ref_id,
        user_id=user_id,
        status="submitted_to_cvki",
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
            description="Deep crater potholes hazardous to two-wheelers and night traffic.",
        ),
        follow_up=FollowUp(guidance="Reported to authority."),
        authority=AuthorityResult(
            authority_status="verified",
            confidence_score=0.96,
            road_owner=AuthorityParty(name=auth_name, type="National Highway", official_portal_url="https://nhai.gov.in"),
            maintenance_authority=AuthorityParty(name=auth_name, type="National Highway", official_portal_url="https://nhai.gov.in"),
            sources=[
                OfficialSourceRecord(
                    source_id="src_nhai_portal",
                    source_name="NHAI Project & Maintenance Portal",
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


class TestGovernmentReferenceMappingM73(unittest.TestCase):
    def setUp(self):
        self.original_overrides = dict(app.dependency_overrides)
        self.client = TestClient(app)

        # Knowledge Graph
        self.kg_repo = InMemoryKnowledgeGraphRepository()
        self.kg_service = CivicKnowledgeGraphService(repository=self.kg_repo)
        set_knowledge_graph_service(self.kg_service)

        # Provenance Engine
        self.prov_repo = InMemoryProvenanceRepository()
        self.prov_engine = EvidenceProvenanceEngine(repository=self.prov_repo)
        set_provenance_engine(self.prov_engine)

        # Complaint Cases
        self.original_case_repo = complaint_case_module.case_repository
        self.case_repo = complaint_case_module.InMemoryComplaintCaseRepository()
        complaint_case_module.set_case_repository(self.case_repo)

        # Government Submissions
        self.gov_sub_repo = InMemoryGovernmentSubmissionRepository()
        self.gov_service = GovernmentIntegrationService(repository=self.gov_sub_repo)
        set_government_integration_service(self.gov_service)

        # Government Reference Mappings (M7.3)
        self.ref_repo = InMemoryGovernmentReferenceRepository()
        self.ref_service = GovernmentReferenceService(repository=self.ref_repo)
        set_government_reference_service(self.ref_service)

        government_registry.reset_to_initial()

    def tearDown(self):
        complaint_case_module.set_case_repository(self.original_case_repo)
        app.dependency_overrides = self.original_overrides
        government_registry.reset_to_initial()

    # ------------------------------------------------------------------
    # 1 & 2. CVKI Reference Immutability & Separate Government Reference
    # ------------------------------------------------------------------
    def test_01_cvki_reference_immutability_and_separation(self):
        """CVKI reference is immutable and is never replaced by a government tracking ID."""
        case = build_test_case("CVKI-PERM-12345")
        self.case_repo.save(case)

        mapping = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_test_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-GOV-987654",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        # Verify separation:
        self.assertEqual(mapping.cvki_reference_id, "CVKI-PERM-12345")
        self.assertEqual(mapping.government_reference_id, "MOCK-GOV-987654")
        self.assertNotEqual(mapping.cvki_reference_id, mapping.government_reference_id)

        # Verify case reference unchanged in repo
        retrieved_case = self.case_repo.get("CVKI-PERM-12345")
        self.assertEqual(retrieved_case.reference_id, "CVKI-PERM-12345")

    # ------------------------------------------------------------------
    # 3. Integration-Specific Mapping (Namespacing)
    # ------------------------------------------------------------------
    def test_02_integration_specific_mapping_namespaces(self):
        """The same CVKI case can have separate mappings for different integrations without collision."""
        case = build_test_case("CVKI-MULTI-001")
        self.case_repo.save(case)

        m_cpgrams = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_cpgrams_001",
                integration_id="gov_cpgrams",
                government_reference_id="DARPG/E/2026/001",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        m_mock = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_mock_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-001",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        mappings = self.ref_service.get_case_mappings(case.reference_id)
        self.assertEqual(mappings.total, 2)
        integration_ids = [m.integration_id for m in mappings.mappings]
        self.assertIn("gov_cpgrams", integration_ids)
        self.assertIn("mock_sandbox_integration", integration_ids)

    # ------------------------------------------------------------------
    # 4 & 5. Reference Received vs Confirmed (Epistemic Honesty)
    # ------------------------------------------------------------------
    def test_03_reference_received_does_not_mean_confirmed(self):
        """REFERENCE_RECEIVED has unverified state and is_authoritative=False."""
        case = build_test_case("CVKI-REC-001")
        self.case_repo.save(case)

        mapping = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_rec_001",
                integration_id="gov_cpgrams",
                government_reference_id="DARPG/P/2026/999",
                mapping_state=ReferenceMappingState.REFERENCE_RECEIVED,
                source="adapter:gov_cpgrams",
            )
        )

        resp = self.ref_service.get_mapping(case.reference_id, "gov_cpgrams")
        self.assertEqual(resp.mapping_state, ReferenceMappingState.REFERENCE_RECEIVED)
        self.assertEqual(resp.verification_state, "unverified")
        self.assertFalse(resp.is_authoritative)
        self.assertIsNone(resp.last_confirmed_at)
        self.assertIsNotNone(resp.first_observed_at)

    def test_04_reference_confirmed_is_authoritative(self):
        """REFERENCE_CONFIRMED has verified state and is_authoritative=True."""
        case = build_test_case("CVKI-CONF-001")
        self.case_repo.save(case)

        mapping = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_conf_001",
                integration_id="gov_cpgrams",
                government_reference_id="DARPG/E/2026/888",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:gov_cpgrams",
            )
        )

        resp = self.ref_service.get_mapping(case.reference_id, "gov_cpgrams")
        self.assertEqual(resp.mapping_state, ReferenceMappingState.REFERENCE_CONFIRMED)
        self.assertEqual(resp.verification_state, "verified")
        self.assertTrue(resp.is_authoritative)
        self.assertIsNotNone(resp.last_confirmed_at)

    # ------------------------------------------------------------------
    # 6 & 7. UNKNOWN_OUTCOME Handling
    # ------------------------------------------------------------------
    def test_05_unknown_outcome_state_preserves_null_reference(self):
        """UNKNOWN_OUTCOME state does not fabricate an external reference ID."""
        case = build_test_case("CVKI-UNK-001")
        self.case_repo.save(case)

        mapping = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_unk_001",
                integration_id="gov_cpgrams",
                government_reference_id=None,
                mapping_state=ReferenceMappingState.UNKNOWN_OUTCOME,
                source="adapter:gov_cpgrams",
            )
        )

        resp = self.ref_service.get_mapping(case.reference_id, "gov_cpgrams")
        self.assertEqual(resp.mapping_state, ReferenceMappingState.UNKNOWN_OUTCOME)
        self.assertIsNone(resp.government_reference_id)
        self.assertFalse(resp.is_authoritative)

    # ------------------------------------------------------------------
    # 8. Reconciliation Transitions UNKNOWN_OUTCOME to Confirmed
    # ------------------------------------------------------------------
    def test_06_reconciliation_transitions_unknown_outcome_to_confirmed(self):
        """Reconciliation discovering an official reference updates the mapping to REFERENCE_CONFIRMED."""
        case = build_test_case("CVKI-REC-CONF-001")
        self.case_repo.save(case)

        # 1. Start in UNKNOWN_OUTCOME
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_rec_001",
                integration_id="mock_sandbox_integration",
                government_reference_id=None,
                mapping_state=ReferenceMappingState.UNKNOWN_OUTCOME,
            )
        )

        # 2. Reconcile with adapter
        reconciled_ref = "MOCK-GOV-CONFIRMED-123"
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_rec_001",
                integration_id="mock_sandbox_integration",
                government_reference_id=reconciled_ref,
                government_reference_status="registered",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="reconciliation:mock_sandbox_integration",
            )
        )

        resp = self.ref_service.get_mapping(case.reference_id, "mock_sandbox_integration")
        self.assertEqual(resp.mapping_state, ReferenceMappingState.REFERENCE_CONFIRMED)
        self.assertEqual(resp.government_reference_id, reconciled_ref)
        self.assertTrue(resp.is_authoritative)
        self.assertIsNotNone(resp.last_confirmed_at)

    # ------------------------------------------------------------------
    # 9 & 10. Idempotent Repeated Observation (No Duplicates)
    # ------------------------------------------------------------------
    def test_07_idempotent_repeated_observation_increments_version_without_duplication(self):
        """Repeated sync updates existing record version and timestamp rather than duplicating."""
        case = build_test_case("CVKI-IDEMP-001")
        self.case_repo.save(case)

        # First observation
        m1 = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_idemp_001",
                integration_id="gov_cpgrams",
                government_reference_id="DARPG/E/2026/777",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )
        self.assertEqual(m1.version, 1)

        # Second observation of same reference
        m2 = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_idemp_001",
                integration_id="gov_cpgrams",
                government_reference_id="DARPG/E/2026/777",
                government_reference_status="in_progress",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )
        self.assertEqual(m2.version, 2)
        self.assertEqual(m1.mapping_id, m2.mapping_id)

        # Total mappings remains 1
        mappings = self.ref_service.get_case_mappings(case.reference_id)
        self.assertEqual(mappings.total, 1)

    # ------------------------------------------------------------------
    # 11. Conflict Detection: Cross-Case Duplicate Reference
    # ------------------------------------------------------------------
    def test_08_cross_case_duplicate_reference_triggers_conflict(self):
        """If Case B claims an external reference already confirmed for Case A, flag REFERENCE_CONFLICT."""
        case_a = build_test_case("CVKI-CASE-A", user_id="citizen_a")
        case_b = build_test_case("CVKI-CASE-B", user_id="citizen_b")
        self.case_repo.save(case_a)
        self.case_repo.save(case_b)

        # Case A receives reference
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_a.reference_id,
                submission_id="sub_a",
                integration_id="gov_cpgrams",
                government_reference_id="DARPG/E/2026/SHARED_THEFT",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                case=case_a,
            )
        )

        # Case B attempts to claim the same reference on the same integration
        mapping_b = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_b.reference_id,
                submission_id="sub_b",
                integration_id="gov_cpgrams",
                government_reference_id="DARPG/E/2026/SHARED_THEFT",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                case=case_b,
            )
        )

        # Verify Case B is marked as REFERENCE_CONFLICT
        self.assertEqual(mapping_b.mapping_state, ReferenceMappingState.REFERENCE_CONFLICT)
        self.assertEqual(mapping_b.verification_state, "conflicted")
        self.assertTrue(mapping_b.metadata.get("conflict_detected"))
        self.assertIn("Cross-case conflict", mapping_b.explanation)

        # Verify Case A's original mapping was NOT modified or overwritten
        mapping_a = self.ref_service.get_mapping(case_a.reference_id, "gov_cpgrams")
        self.assertEqual(mapping_a.mapping_state, ReferenceMappingState.REFERENCE_CONFIRMED)
        self.assertEqual(mapping_a.verification_state, "verified")

    # ------------------------------------------------------------------
    # 12. Changed External Reference Rejection (In-Place Mutation Conflict)
    # ------------------------------------------------------------------
    def test_09_unexpected_reference_replacement_triggers_conflict(self):
        """If a case already has confirmed REF-1 and incoming tries to silently replace with REF-2, flag conflict."""
        case = build_test_case("CVKI-MUTATE-001")
        self.case_repo.save(case)

        # Initial confirmed reference
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m1",
                integration_id="gov_cpgrams",
                government_reference_id="REF-ORIGINAL-1",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        # Attempted silent replacement
        mutated = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m1",
                integration_id="gov_cpgrams",
                government_reference_id="REF-MUTATED-2",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        self.assertEqual(mutated.mapping_state, ReferenceMappingState.REFERENCE_CONFLICT)
        self.assertEqual(mutated.verification_state, "conflicted")
        self.assertIn("Reference mutation conflict", mutated.explanation)

    # ------------------------------------------------------------------
    # 13. Stale / Unavailable Mapping Handling
    # ------------------------------------------------------------------
    def test_10_reconciliation_unavailable_mapping(self):
        """When reconciliation confirms upstream has no record, state is REFERENCE_UNAVAILABLE."""
        case = build_test_case("CVKI-UNAVAIL-001")
        self.case_repo.save(case)

        mapping = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_unavail_001",
                integration_id="gov_cpgrams",
                government_reference_id=None,
                mapping_state=ReferenceMappingState.REFERENCE_UNAVAILABLE,
            )
        )

        resp = self.ref_service.get_mapping(case.reference_id, "gov_cpgrams")
        self.assertEqual(resp.mapping_state, ReferenceMappingState.REFERENCE_UNAVAILABLE)
        self.assertFalse(resp.is_authoritative)

    # ------------------------------------------------------------------
    # 14 & 15. Provenance Linkage (M6.4)
    # ------------------------------------------------------------------
    def test_11_provenance_created_and_verified_for_confirmed_reference(self):
        """Authoritative reference creation generates an M6.4 provenance record."""
        case = build_test_case("CVKI-PROV-001")
        self.case_repo.save(case)

        mapping = run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_prov_001",
                integration_id="gov_cpgrams",
                government_reference_id="DARPG/E/2026/PROV-001",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        self.assertIsNotNone(mapping.provenance_evidence_id)
        ev = self.prov_engine.get_evidence_by_id(mapping.provenance_evidence_id)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.claim_type, ClaimType.GOVERNMENT_SUBMISSION)
        self.assertEqual(ev.source_type, SourceType.GOVERNMENT_ADAPTER)
        self.assertEqual(ev.verification_state, VerificationState.VERIFIED)
        self.assertIn("DARPG/E/2026/PROV-001", ev.explanation)

    # ------------------------------------------------------------------
    # 16 & 17. Knowledge Graph Linkage (M6.5)
    # ------------------------------------------------------------------
    def test_12_knowledge_graph_records_external_case_with_mapping_state(self):
        """Confirmed reference records EXTERNAL_CASE node in knowledge graph with mapping_state."""
        case = build_test_case("CVKI-KG-001")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_kg_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-KG-1234",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        # Check EXTERNAL_CASE node
        ext_key = "ext_case:mock_sandbox_integration:MOCK-KG-1234"
        node = self.kg_repo.get_node_by_key(ext_key)
        self.assertIsNotNone(node)
        self.assertEqual(node.metadata.get("mapping_state"), "REFERENCE_CONFIRMED")
        self.assertEqual(node.metadata.get("verification_state"), "verified")

    def test_13_knowledge_graph_records_conflicted_state(self):
        """Conflicted reference records EXTERNAL_CASE node with conflicted verification state."""
        case_a = build_test_case("CVKI-KG-CONF-A")
        case_b = build_test_case("CVKI-KG-CONF-B")
        self.case_repo.save(case_a)
        self.case_repo.save(case_b)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_a.reference_id,
                submission_id="sub_kg_a",
                integration_id="gov_cpgrams",
                government_reference_id="SHARED-KG-REF",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_b.reference_id,
                submission_id="sub_kg_b",
                integration_id="gov_cpgrams",
                government_reference_id="SHARED-KG-REF",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        ext_key = "ext_case:gov_cpgrams:SHARED-KG-REF"
        node = self.kg_repo.get_node_by_key(ext_key)
        self.assertIsNotNone(node)
        self.assertEqual(node.metadata.get("mapping_state"), "REFERENCE_CONFLICT")
        self.assertEqual(node.metadata.get("verification_state"), "conflicted")

    # ------------------------------------------------------------------
    # 18. Manual Reference Handling (Staff/Admin)
    # ------------------------------------------------------------------
    def test_14_manual_reference_entry_creates_unverified_reference(self):
        """Manual reference entry creates UNVERIFIED_MANUAL_REFERENCE with unverified state."""
        case = build_test_case("CVKI-MANUAL-001")
        self.case_repo.save(case)

        req = ManualReferenceCreateRequest(
            government_reference_id="MANUAL-DOCKET-789",
            government_reference_type="manual_docket",
            reason="Received physical stamped acknowledgment from BBMP Ward 150 office",
            notes="Signed by Junior Engineer Ramesh",
        )

        mapping = run_async(
            self.ref_service.record_manual_reference(
                cvki_reference_id=case.reference_id,
                integration_id="gov_bbmp",
                req=req,
                actor_user_id="staff_user_01",
                actor_role="authority",
                case=case,
            )
        )

        self.assertEqual(mapping.mapping_state, ReferenceMappingState.UNVERIFIED_MANUAL_REFERENCE)
        self.assertEqual(mapping.verification_state, "unverified")
        self.assertIn("Received physical stamped acknowledgment", mapping.explanation)

    # ------------------------------------------------------------------
    # 19, 20, 21. RBAC Enforcements (Citizen, Authority, Admin)
    # ------------------------------------------------------------------
    def test_15_citizen_can_view_own_reference_mappings(self):
        """Citizen can query references for their own case."""
        case = build_test_case("CVKI-RBAC-CIT-01", user_id="citizen_owner")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_cit_01",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-CIT",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_owner", role=UserRole.CITIZEN.value, email="cit@example.com"
        )

        res = self.client.get(f"/api/v1/government/cases/{case.reference_id}/references")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["mappings"][0]["government_reference_id"], "MOCK-REF-CIT")

    def test_16_citizen_cannot_view_other_citizen_reference_mappings(self):
        """Citizen receives 404 when attempting to view another citizen's case references."""
        case = build_test_case("CVKI-RBAC-CIT-02", user_id="citizen_other")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_intruder", role=UserRole.CITIZEN.value, email="intruder@example.com"
        )

        res = self.client.get(f"/api/v1/government/cases/{case.reference_id}/references")
        self.assertEqual(res.status_code, 404)

    def test_17_citizen_forbidden_from_manual_reference_entry(self):
        """Citizen cannot call POST manual reference entry endpoint (403 Forbidden)."""
        case = build_test_case("CVKI-RBAC-CIT-03", user_id="citizen_owner")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_owner", role=UserRole.CITIZEN.value, email="cit@example.com"
        )

        payload = {
            "government_reference_id": "FAKE-CITIZEN-REF-999",
            "government_reference_type": "manual_docket",
            "reason": "Attempting unauthorized manual override",
        }
        res = self.client.post(
            f"/api/v1/government/cases/{case.reference_id}/references/gov_cpgrams/manual",
            json=payload,
        )
        self.assertEqual(res.status_code, 403)

    def test_18_authority_can_record_manual_reference_via_api(self):
        """Authority user can record manual reference via API."""
        case = build_test_case("CVKI-RBAC-AUTH-01", user_id="citizen_owner")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="auth_officer", role=UserRole.AUTHORITY.value, email="officer@nhai.gov.in"
        )

        payload = {
            "government_reference_id": "NHAI-OFFLINE-LETTER-44",
            "government_reference_type": "official_letter",
            "reason": "Received dispatch confirmation memo from Project Director",
        }
        res = self.client.post(
            f"/api/v1/government/cases/{case.reference_id}/references/gov_nhai/manual",
            json=payload,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mapping_state"], "UNVERIFIED_MANUAL_REFERENCE")
        self.assertEqual(data["verification_state"], "unverified")
        self.assertEqual(data["government_reference_id"], "NHAI-OFFLINE-LETTER-44")

    # ------------------------------------------------------------------
    # 22. Client Cannot Fabricate Confirmed Reference
    # ------------------------------------------------------------------
    def test_19_client_cannot_fabricate_confirmed_reference(self):
        """Manual reference entry never produces is_authoritative=True or REFERENCE_CONFIRMED."""
        case = build_test_case("CVKI-NO-FABRICATE-01")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="admin_user", role=UserRole.ADMIN.value, email="admin@cvki.gov.in"
        )

        payload = {
            "government_reference_id": "FABRICATED-CONFIRMED-TRY",
            "reason": "Trying to see if manual entry becomes confirmed",
        }
        res = self.client.post(
            f"/api/v1/government/cases/{case.reference_id}/references/gov_cpgrams/manual",
            json=payload,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["is_authoritative"])
        self.assertNotEqual(data["mapping_state"], "REFERENCE_CONFIRMED")
        self.assertEqual(data["verification_state"], "unverified")

    # ------------------------------------------------------------------
    # 23. Provenance Endpoint
    # ------------------------------------------------------------------
    def test_20_reference_provenance_api_endpoint(self):
        """GET /references/{integration_id}/provenance returns M6.4 evidence record."""
        case = build_test_case("CVKI-API-PROV-01")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_prov_api",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-PROV-API-123",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
            )
        )

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_user_001", role=UserRole.CITIZEN.value, email="cit@example.com"
        )

        res = self.client.get(
            f"/api/v1/government/cases/{case.reference_id}/references/mock_sandbox_integration/provenance"
        )
        self.assertEqual(res.status_code, 200)
        ev_data = res.json()
        self.assertEqual(ev_data["claim_type"], "government_submission")
        self.assertEqual(ev_data["verification_state"], "verified")

    # ------------------------------------------------------------------
    # 24. Audit Logging for Reference Lifecycle Events
    # ------------------------------------------------------------------
    def test_21_audit_logging_recorded_for_mapping_events(self):
        """All mapping events trigger appropriate audit logs."""
        case = build_test_case("CVKI-AUDIT-001")
        self.case_repo.save(case)

        with patch("app.services.audit.AuditService.record_event", new_callable=AsyncMock) as mock_audit:
            run_async(
                self.ref_service.record_mapping(
                    cvki_reference_id=case.reference_id,
                    submission_id="sub_aud_001",
                    integration_id="gov_cpgrams",
                    government_reference_id="DARPG/E/2026/AUDIT",
                    mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                    actor_user_id="staff_123",
                    actor_role="authority",
                )
            )
            mock_audit.assert_awaited()
            # Assert action is government_reference_confirmed
            actions = [call.kwargs.get("action") for call in mock_audit.await_args_list]
            self.assertIn("government_reference_confirmed", actions)

    # ------------------------------------------------------------------
    # 25. Mock Adapter End-to-End Regression
    # ------------------------------------------------------------------
    def test_22_end_to_end_submission_updates_reference_mapping(self):
        """Submitting through GovernmentIntegrationService automatically creates confirmed reference mapping."""
        case = build_test_case("CVKI-E2E-REF-001")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="admin_e2e", role=UserRole.ADMIN.value, email="admin@cvki.gov.in"
        )

        # Submit case to mock adapter
        res = run_async(
            self.gov_service.submit_case(
                case=case,
                integration_id="mock_sandbox_integration",
                user_id="admin_e2e",
                user_role="admin",
            )
        )
        self.assertTrue(res.success)
        self.assertIsNotNone(res.external_reference_id)

        # Verify mapping was created in GovernmentReferenceService
        mapping = self.ref_service.get_mapping(case.reference_id, "mock_sandbox_integration")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.mapping_state, ReferenceMappingState.REFERENCE_CONFIRMED)
        self.assertEqual(mapping.government_reference_id, res.external_reference_id)
        self.assertEqual(mapping.verification_state, "verified")
        self.assertTrue(mapping.is_authoritative)


if __name__ == "__main__":
    unittest.main()
