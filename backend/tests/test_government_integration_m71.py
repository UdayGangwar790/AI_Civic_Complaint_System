"""
CVKI M7.1 Government Integration Foundation Test Suite.
Covers Items A through Z:
A. Adapter interface
B. Adapter capabilities
C. Registry
D. NOT_CONFIGURED behavior
E. Mock adapter
F. Submission schema
G. State machine
H. Valid transitions
I. Invalid transitions
J. Idempotency
K. Duplicate submission protection
L. Unknown outcome
M. Reconciliation
N. Status normalization
O. External reference handling
P. Provenance integration
Q. Knowledge graph integration
R. Audit logging
S. RBAC & Privacy
T. Credential protection
U. SSRF security
V. Credential leakage prevention
W. API endpoints
X. Environment configuration
Y. Regression compatibility
Z. Safe failure behavior
"""

import asyncio
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.authority import AuthorityParty, AuthorityResult, OfficialSourceRecord
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import CaseComplaint, CaseIssue, ComplaintCase, FollowUp
from app.schemas.government_integration import (
    AdapterCapabilities,
    AdapterType,
    GovernmentIntegrationDefinition,
    GovernmentSubmissionRecord,
    IntegrationState,
    NormalizedGovernmentStatus,
    SubmissionLifecycleState,
)
from app.schemas.government_submission import GovernmentSubmissionPackage
from app.schemas.provenance import ClaimType, SourceType
from app.services.authority_registry import is_safe_official_url
import app.services.complaint_case as complaint_case_module
from app.services.government_adapter import (
    GovernmentIntegrationAdapter,
    MockGovernmentAdapter,
    AdapterSubmissionResult,
    AdapterStatusResult,
)
from app.services.government_integration_service import (
    GovernmentIntegrationService,
    InMemoryGovernmentSubmissionRepository,
    NOT_CONFIGURED_NOTICE,
    government_integration_service,
)
from app.services.government_registry import GovernmentServiceRegistry, government_registry
from app.services.government_state_machine import InvalidStateTransitionError, SubmissionStateMachine
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


def build_mock_case(
    ref_id: str = "CASE-2026-M71-001",
    user_id: str = "citizen_user_001",
    auth_status: str = "verified",
    auth_name: str = "National Highways Authority of India (NHAI)",
) -> ComplaintCase:
    now = datetime.now(timezone.utc)
    return ComplaintCase(
        reference_id=ref_id,
        user_id=user_id,
        status="submitted_to_cvki",
        issue=CaseIssue(
            class_name="open_damaged_manhole",
            label="Open/Damaged Manhole",
            severity="high",
            confidence=0.92,
        ),
        location=ComplaintLocation(
            latitude=12.9716,
            longitude=77.5946,
            road="Hosur Road",
            area="Koramangala",
            city="Bengaluru",
            district="Bengaluru Urban",
            state="Karnataka",
            accuracy_m=12.0,
        ),
        complaint=CaseComplaint(
            language="en",
            title="Hazardous Open Manhole on Hosur Road",
            description="Dangerous uncovered manhole right on the road corridor posing severe traffic danger.",
        ),
        follow_up=FollowUp(guidance="Reported to official authority."),
        authority=AuthorityResult(
            authority_status=auth_status,
            confidence_score=0.95,
            road_owner=AuthorityParty(name=auth_name, type="National Highway", official_portal_url="https://nhai.gov.in"),
            maintenance_authority=AuthorityParty(name=auth_name, type="National Highway", official_portal_url="https://nhai.gov.in"),
            sources=[
                OfficialSourceRecord(
                    source_id="src_morth_gazette",
                    source_name="MoRTH Official Gazette",
                    source_type="official_gazette",
                    domain="morth.nic.in",
                    url="https://morth.nic.in/gazette",
                    retrieved_at=now,
                )
            ],
            resolved_at=now,
        ),
        created_at=now,
        updated_at=now,
    )


class TestGovernmentIntegrationM71(unittest.TestCase):
    def setUp(self):
        self.original_overrides = dict(app.dependency_overrides)
        self.client = TestClient(app)

        self.kg_repo = InMemoryKnowledgeGraphRepository()
        self.kg_service = CivicKnowledgeGraphService(repository=self.kg_repo)
        set_knowledge_graph_service(self.kg_service)

        self.prov_repo = InMemoryProvenanceRepository()
        self.prov_engine = EvidenceProvenanceEngine(repository=self.prov_repo)
        set_provenance_engine(self.prov_engine)

        self.original_case_repo = complaint_case_module.case_repository
        self.case_repo = complaint_case_module.InMemoryComplaintCaseRepository()
        complaint_case_module.set_case_repository(self.case_repo)

        self.gov_sub_repo = InMemoryGovernmentSubmissionRepository()
        self.gov_service = GovernmentIntegrationService(repository=self.gov_sub_repo)
        government_registry.reset_to_initial()

    def tearDown(self):
        complaint_case_module.set_case_repository(self.original_case_repo)
        app.dependency_overrides = self.original_overrides
        government_registry.reset_to_initial()

    # --------------------------------------------------
    # A. Adapter Interface Compliance
    # --------------------------------------------------
    def test_a_adapter_interface_compliance(self):
        class IncompleteAdapter(GovernmentIntegrationAdapter):
            pass

        with self.assertRaises(TypeError):
            IncompleteAdapter()

    # --------------------------------------------------
    # B. Adapter Capabilities
    # --------------------------------------------------
    def test_b_adapter_capabilities_declaration(self):
        adapter = MockGovernmentAdapter()
        caps = adapter.get_capabilities()
        self.assertIsInstance(caps, AdapterCapabilities)
        self.assertTrue(caps.submission_supported)
        self.assertTrue(caps.status_supported)
        self.assertTrue(caps.reference_id_supported)
        self.assertTrue(caps.attachment_supported)
        self.assertTrue(caps.citizen_identity_supported)
        self.assertTrue(caps.polling_supported)

    # --------------------------------------------------
    # C. Registry & Authority Lookup
    # --------------------------------------------------
    def test_c_registry_and_authority_lookup(self):
        reg = GovernmentServiceRegistry()
        defs = reg.list_definitions()
        self.assertGreaterEqual(len(defs), 4)

        nhai_int = reg.find_integration_for_authority("National Highways Authority of India (NHAI)")
        self.assertIsNotNone(nhai_int)
        self.assertEqual(nhai_int.integration_id, "gov_nhai")

        bbmp_int = reg.find_integration_for_authority("Bruhat Bengaluru Mahanagara Palike (BBMP)")
        self.assertIsNotNone(bbmp_int)
        self.assertEqual(bbmp_int.integration_id, "gov_bbmp")

    # --------------------------------------------------
    # D. NOT_CONFIGURED Safe Default
    # --------------------------------------------------
    def test_d_not_configured_safe_default(self):
        case = build_mock_case(auth_name="National Highways Authority of India (NHAI)")
        summary = self.gov_service.get_submission_summary(case)
        self.assertEqual(summary.integration_state, IntegrationState.NOT_CONFIGURED)
        self.assertIsNone(summary.external_reference_id)
        self.assertIn(NOT_CONFIGURED_NOTICE, summary.notice)

    # --------------------------------------------------
    # E. Mock Adapter Execution
    # --------------------------------------------------
    def test_e_mock_adapter_execution(self):
        adapter = MockGovernmentAdapter()
        self.assertEqual(adapter.ENVIRONMENT, "TEST")

        case = build_mock_case()
        pkg = GovernmentSubmissionPackage(
            reference_id=case.reference_id,
            issue_category=case.issue.class_name,
            complaint_title=case.complaint.title,
            complaint_description=case.complaint.description,
            detected_location={"latitude": 12.9716, "longitude": 77.5946},
            authority_verification_state="verified",
            created_at=case.created_at,
            prepared_at=case.created_at,
        )

        res = run_async(adapter.submit(case, pkg, idempotency_key="test-key-1"))
        self.assertEqual(res.state, IntegrationState.SUBMISSION_ACCEPTED)
        self.assertTrue(res.external_reference_id.startswith("MOCK-GOV-"))
        self.assertEqual(res.raw_status, "registered")
        self.assertEqual(res.normalized_status, NormalizedGovernmentStatus.REGISTERED)

    # --------------------------------------------------
    # F. Submission Schema
    # --------------------------------------------------
    def test_f_submission_schema_validation(self):
        rec = GovernmentSubmissionRecord(
            submission_id="sub_123",
            case_reference_id="CASE-001",
            integration_id="gov_test",
            submission_state=SubmissionLifecycleState.SUBMITTED,
            external_reference_id="GOV-REF-999",
            raw_status="registered",
            normalized_status=NormalizedGovernmentStatus.REGISTERED,
        )
        d = rec.model_dump()
        self.assertIn("submission_id", d)
        self.assertIn("external_reference_id", d)
        self.assertNotIn("password", d)
        self.assertNotIn("token", d)
        self.assertNotIn("secret", d)

    # --------------------------------------------------
    # G. State Machine Deterministic Transitions
    # --------------------------------------------------
    def test_g_state_machine_deterministic_lifecycle(self):
        self.assertTrue(SubmissionStateMachine.can_transition(
            SubmissionLifecycleState.READY,
            SubmissionLifecycleState.SUBMITTING,
        ))
        self.assertTrue(SubmissionStateMachine.can_transition(
            SubmissionLifecycleState.SUBMITTING,
            SubmissionLifecycleState.SUBMITTED,
        ))
        self.assertTrue(SubmissionStateMachine.can_transition(
            SubmissionLifecycleState.SUBMITTING,
            SubmissionLifecycleState.UNKNOWN_OUTCOME,
        ))

    # --------------------------------------------------
    # H. Valid Transitions
    # --------------------------------------------------
    def test_h_valid_transitions(self):
        target = SubmissionStateMachine.validate_transition(
            SubmissionLifecycleState.READY,
            SubmissionLifecycleState.SUBMITTING,
        )
        self.assertEqual(target, SubmissionLifecycleState.SUBMITTING)

        target2 = SubmissionStateMachine.validate_transition(
            SubmissionLifecycleState.SUBMITTED,
            SubmissionLifecycleState.STATUS_SYNCING,
        )
        self.assertEqual(target2, SubmissionLifecycleState.STATUS_SYNCING)

    # --------------------------------------------------
    # I. Invalid Transitions
    # --------------------------------------------------
    def test_i_invalid_transitions(self):
        with self.assertRaises(InvalidStateTransitionError):
            SubmissionStateMachine.validate_transition(
                SubmissionLifecycleState.READY,
                SubmissionLifecycleState.COMPLETED,
            )

        with self.assertRaises(InvalidStateTransitionError):
            SubmissionStateMachine.validate_transition(
                SubmissionLifecycleState.SUBMITTING,
                SubmissionLifecycleState.READY,
            )

        with self.assertRaises(InvalidStateTransitionError):
            SubmissionStateMachine.validate_transition(
                SubmissionLifecycleState.CANCELLED,
                SubmissionLifecycleState.SUBMITTING,
            )

    # --------------------------------------------------
    # J. Idempotency Protection
    # --------------------------------------------------
    def test_j_idempotency_protection(self):
        case = build_mock_case()
        resp1 = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertTrue(resp1.success)
        self.assertEqual(resp1.submission_state, SubmissionLifecycleState.SUBMITTED)
        first_ref = resp1.external_reference_id

        # Re-submit should return idempotent replay
        resp2 = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertTrue(resp2.success)
        self.assertEqual(resp2.external_reference_id, first_ref)
        self.assertIn("Idempotent response", resp2.notice)

    # --------------------------------------------------
    # K. Duplicate Active Submission Protection
    # --------------------------------------------------
    def test_k_duplicate_active_submission_protection(self):
        case = build_mock_case()
        active_rec = GovernmentSubmissionRecord(
            submission_id="sub_inflight_01",
            case_reference_id=case.reference_id,
            integration_id="mock_sandbox_integration",
            submission_state=SubmissionLifecycleState.SUBMITTING,
        )
        self.gov_sub_repo.save(active_rec)

        resp = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_code, "DUPLICATE_ACTIVE_SUBMISSION")
        self.assertIn("already in progress", resp.notice)

    # --------------------------------------------------
    # L. UNKNOWN_OUTCOME Handling
    # --------------------------------------------------
    def test_l_unknown_outcome_handling(self):
        case = build_mock_case()
        timeout_adapter = MockGovernmentAdapter(should_timeout=True)
        government_registry.register_adapter("mock_sandbox_integration", timeout_adapter)

        resp = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertFalse(resp.success)
        self.assertEqual(resp.submission_state, SubmissionLifecycleState.UNKNOWN_OUTCOME)
        self.assertTrue(resp.reconciliation_required)
        self.assertIsNone(resp.external_reference_id)
        self.assertIn("Reconciliation required", resp.notice)

    # --------------------------------------------------
    # M. Reconciliation Workflow
    # --------------------------------------------------
    def test_m_reconciliation_workflow(self):
        case = build_mock_case()
        timeout_adapter = MockGovernmentAdapter(should_timeout=True)
        government_registry.register_adapter("mock_sandbox_integration", timeout_adapter)

        resp = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertEqual(resp.submission_state, SubmissionLifecycleState.UNKNOWN_OUTCOME)

        # Run reconciliation
        rec_res = run_async(self.gov_service.reconcile_submission(case.reference_id))
        self.assertTrue(rec_res.resolved)
        self.assertEqual(rec_res.reconciled_state, SubmissionLifecycleState.SUBMITTED)
        self.assertIsNotNone(rec_res.external_reference_id)
        self.assertTrue(rec_res.external_reference_id.startswith("MOCK-GOV-"))

    # --------------------------------------------------
    # N. Status Normalization
    # --------------------------------------------------
    def test_n_status_normalization(self):
        adapter = MockGovernmentAdapter()
        self.assertEqual(adapter.normalize_status("registered"), NormalizedGovernmentStatus.REGISTERED)
        self.assertEqual(adapter.normalize_status("ack"), NormalizedGovernmentStatus.REGISTERED)
        self.assertEqual(adapter.normalize_status("under_review"), NormalizedGovernmentStatus.UNDER_REVIEW)
        self.assertEqual(adapter.normalize_status("in_progress"), NormalizedGovernmentStatus.IN_PROGRESS)
        self.assertEqual(adapter.normalize_status("resolved"), NormalizedGovernmentStatus.RESOLVED)
        self.assertEqual(adapter.normalize_status("closed"), NormalizedGovernmentStatus.CLOSED)
        self.assertEqual(adapter.normalize_status("arbitrary_status"), NormalizedGovernmentStatus.UNKNOWN)

    # --------------------------------------------------
    # O. External Reference Handling
    # --------------------------------------------------
    def test_o_external_reference_handling(self):
        case = build_mock_case()
        summary = self.gov_service.get_submission_summary(case)
        self.assertIsNone(summary.external_reference_id)

    # --------------------------------------------------
    # P. Provenance Integration
    # --------------------------------------------------
    def test_p_provenance_integration(self):
        case = build_mock_case()
        resp = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertTrue(resp.success)

        ev_records = self.prov_repo.find_by_case(case.reference_id)
        gov_ev = [e for e in ev_records if e.claim_type == ClaimType.GOVERNMENT_SUBMISSION]
        self.assertEqual(len(gov_ev), 1)
        self.assertEqual(gov_ev[0].source_type, SourceType.GOVERNMENT_ADAPTER)
        self.assertEqual(gov_ev[0].matched_attribute, "external_reference_id")
        self.assertIn(resp.external_reference_id, gov_ev[0].explanation)

    # --------------------------------------------------
    # Q. Knowledge Graph Integration
    # --------------------------------------------------
    def test_q_knowledge_graph_integration(self):
        case = build_mock_case()
        resp = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertTrue(resp.success)

        nodes = self.kg_repo.all_nodes()
        gov_nodes = [n for n in nodes if n.node_type == "government_submission"]
        ext_nodes = [n for n in nodes if n.node_type == "external_case"]
        self.assertEqual(len(gov_nodes), 1)
        self.assertEqual(len(ext_nodes), 1)
        self.assertEqual(ext_nodes[0].metadata["external_reference_id"], resp.external_reference_id)

    # --------------------------------------------------
    # R. Audit Logging
    # --------------------------------------------------
    def test_r_audit_logging(self):
        audit_events = []

        async def mock_record_event(action, result="success", **kwargs):
            audit_events.append({"action": action, "result": result, **kwargs})
            return None

        with patch("app.services.audit.AuditService.record_event", side_effect=mock_record_event):
            case = build_mock_case()
            run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration", user_id="u123", user_role="citizen"))

            actions = [e["action"] for e in audit_events]
            self.assertIn("government_submission_attempted", actions)
            self.assertIn("government_submission_accepted", actions)

    # --------------------------------------------------
    # S. RBAC
    # --------------------------------------------------
    def test_s_rbac_checks(self):
        case = build_mock_case(user_id="citizen_alice")
        saved = complaint_case_module.case_repository.save(case)
        if hasattr(saved, "__await__"):
            run_async(saved)

        # Citizen Bob attempting to access Alice's case submission
        mock_bob = AuthenticatedUser(user_id="citizen_bob", email="bob@civki.in", role=UserRole.CITIZEN.value)
        app.dependency_overrides[get_current_user] = lambda: mock_bob

        res = self.client.get(f"/api/v1/government/cases/{case.reference_id}/submission")
        self.assertEqual(res.status_code, 404)

        # Admin access permitted
        mock_admin = AuthenticatedUser(user_id="admin_01", email="admin@civki.in", role=UserRole.ADMIN.value)
        app.dependency_overrides[get_current_user] = lambda: mock_admin
        res = self.client.get(f"/api/v1/government/cases/{case.reference_id}/submission")
        self.assertEqual(res.status_code, 200)

    # --------------------------------------------------
    # T & V. Credential Protection & Sanitization
    # --------------------------------------------------
    def test_t_v_credential_protection(self):
        from app.services.audit import _sanitize_metadata
        dirty = {
            "case_id": "C-123",
            "api_key": "SUPER_SECRET_KEY",
            "access_token": "BEARER_XYZ",
            "password": "secret_password",
            "safe_attr": "ok_value",
        }
        clean = _sanitize_metadata(dirty)
        self.assertEqual(clean["api_key"], "[REDACTED]")
        self.assertEqual(clean["access_token"], "[REDACTED]")
        self.assertEqual(clean["password"], "[REDACTED]")
        self.assertEqual(clean["safe_attr"], "ok_value")

    # --------------------------------------------------
    # U. SSRF Security
    # --------------------------------------------------
    def test_u_ssrf_and_domain_security(self):
        safe, reason = is_safe_official_url("http://localhost:8080/api")
        self.assertFalse(safe)

        safe, reason = is_safe_official_url("http://127.0.0.1/submit")
        self.assertFalse(safe)

        safe, reason = is_safe_official_url("http://192.168.1.50/portal")
        self.assertFalse(safe)
        self.assertIn("private", reason.lower())

        safe, reason = is_safe_official_url("http://169.254.169.254/latest/meta-data")
        self.assertFalse(safe)

        safe, reason = is_safe_official_url("https://arbitrary-third-party.com/api")
        self.assertFalse(safe)

        safe, reason = is_safe_official_url("https://nhai.gov.in/grievance")
        self.assertTrue(safe)

        safe, reason = is_safe_official_url("https://bbmp.gov.in/sahaya")
        self.assertTrue(safe)

    # --------------------------------------------------
    # W. API Endpoints
    # --------------------------------------------------
    def test_w_api_endpoints(self):
        mock_citizen = AuthenticatedUser(user_id="citizen_user_001", email="cit@civki.in", role=UserRole.CITIZEN.value)
        app.dependency_overrides[get_current_user] = lambda: mock_citizen

        res = self.client.get("/api/v1/government-integrations")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("integrations", data)
        self.assertGreaterEqual(data["total"], 4)

        res = self.client.get("/api/v1/government-integrations/gov_nhai")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["integration_id"], "gov_nhai")

    # --------------------------------------------------
    # X. Environment Configuration Defaults
    # --------------------------------------------------
    def test_x_environment_configuration_defaults(self):
        self.assertFalse(settings.GOVERNMENT_INTEGRATION_ENABLED)
        self.assertFalse(settings.GOVERNMENT_STATUS_SYNC_ENABLED)
        self.assertEqual(settings.GOVERNMENT_REQUEST_TIMEOUT_SECONDS, 5.0)
        self.assertEqual(settings.GOVERNMENT_MAX_RETRIES, 2)
        self.assertEqual(settings.GOVERNMENT_SYNC_INTERVAL_SECONDS, 3600)

    # --------------------------------------------------
    # Y. CVKI Case Lifecycle Integrity
    # --------------------------------------------------
    def test_y_cvki_case_lifecycle_integrity(self):
        case = build_mock_case()
        self.assertEqual(case.status, "submitted_to_cvki")

        sub_rec = GovernmentSubmissionRecord(
            submission_id="sub_test",
            case_reference_id=case.reference_id,
            integration_id="mock_sandbox_integration",
            submission_state=SubmissionLifecycleState.SUBMITTED,
        )
        self.assertEqual(sub_rec.submission_state, SubmissionLifecycleState.SUBMITTED)
        self.assertEqual(case.status, "submitted_to_cvki")

    # --------------------------------------------------
    # Z. Safe Failure Behavior
    # --------------------------------------------------
    def test_z_safe_failure_behavior(self):
        case = build_mock_case()
        failing_adapter = MockGovernmentAdapter(should_fail=True)
        government_registry.register_adapter("mock_sandbox_integration", failing_adapter)

        resp = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertFalse(resp.success)
        self.assertEqual(resp.submission_state, SubmissionLifecycleState.FAILED)
        self.assertEqual(resp.error_code, "MOCK_EXTERNAL_ERROR")
        self.assertIn("Simulated 500 error", resp.notice)

    # --------------------------------------------------
    # Additional Security Tests: UNKNOWN_OUTCOME Retry Protection & Cross-Authority
    # --------------------------------------------------
    def test_security_unknown_outcome_blocks_blind_retry(self):
        case = build_mock_case()
        # Seed an UNKNOWN_OUTCOME record
        unknown_rec = GovernmentSubmissionRecord(
            submission_id="sub_unknown_01",
            case_reference_id=case.reference_id,
            integration_id="mock_sandbox_integration",
            submission_state=SubmissionLifecycleState.UNKNOWN_OUTCOME,
        )
        self.gov_sub_repo.save(unknown_rec)

        # Attempt to submit again without reconciling
        resp = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_code, "RECONCILIATION_REQUIRED")
        self.assertTrue(resp.reconciliation_required)

    def test_status_sync_progression(self):
        case = build_mock_case()
        resp = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
        self.assertTrue(resp.success)

        # External portal progresses status to in_progress
        adapter = government_registry.get_adapter("mock_sandbox_integration")
        adapter.set_external_status(resp.external_reference_id, "in_progress")

        sync_res = run_async(self.gov_service.sync_case_status(case.reference_id))
        self.assertTrue(sync_res.success)
        self.assertEqual(sync_res.normalized_status, NormalizedGovernmentStatus.IN_PROGRESS)

    def test_cross_authority_dispatch_refusal(self):
        case = build_mock_case(auth_name="National Highways Authority of India (NHAI)")
        saved = complaint_case_module.case_repository.save(case)
        if hasattr(saved, "__await__"):
            run_async(saved)

        mock_citizen = AuthenticatedUser(user_id=case.user_id, email="cit@civki.in", role=UserRole.CITIZEN.value)
        app.dependency_overrides[get_current_user] = lambda: mock_citizen

        # Citizen attempts to dispatch to BBMP while case authority is NHAI
        res = self.client.post(
            f"/api/v1/government/cases/{case.reference_id}/submit",
            json={"integration_id": "gov_bbmp"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("arbitrary", res.json()["detail"].lower())

    def test_client_cannot_inject_state(self):
        case = build_mock_case(auth_name="Sandbox Test Authority")
        saved = complaint_case_module.case_repository.save(case)
        if hasattr(saved, "__await__"):
            run_async(saved)

        mock_citizen = AuthenticatedUser(user_id=case.user_id, email="cit@civki.in", role=UserRole.CITIZEN.value)
        app.dependency_overrides[get_current_user] = lambda: mock_citizen

        # Client sends payload attempting to inject external_reference_id or state
        res = self.client.post(
            f"/api/v1/government/cases/{case.reference_id}/submit",
            json={"external_reference_id": "FAKE-INJECTED-ID", "submission_state": "COMPLETED"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Injected reference must NOT be accepted; adapter generates reference
        self.assertNotEqual(data.get("external_reference_id"), "FAKE-INJECTED-ID")
        self.assertTrue(data.get("external_reference_id", "").startswith("MOCK-GOV-"))
