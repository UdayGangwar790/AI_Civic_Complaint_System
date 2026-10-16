"""
CVKI M7.2 Official Government Portal / API Adapters Test Suite.
Covers Items 1 through 25:
1. Verified adapter registration (CPGRAMS, NHAI, BBMP, Mock)
2. Unconfigured adapter behavior (truthful diagnostic, refuses fake dispatch)
3. Configuration validation (unconfigured, staging, production, disabled)
4. Authentication failure (401/403)
5. Timeout & network interruption -> UNKNOWN_OUTCOME
6. Upstream 4xx (400, 422)
7. Upstream 5xx (500, 502, 503)
8. Malformed response handling
9. Successful submission & response fingerprinting
10. External reference ID extraction
11. Status normalization table
12. Unknown status safety
13. UNKNOWN_OUTCOME blocks blind resubmission
14. Reconciliation workflow (confirmed vs not received)
15. Idempotency preservation
16. Duplicate submission protection
17. Retry safety (safe operations only, no blind retry on unknown POST outcome)
18. SSRF protection
19. Credential protection & sanitization
20. RBAC enforcement
21. Provenance integration (ClaimType.GOVERNMENT_SUBMISSION)
22. Knowledge graph integration (Case -> GOVERNMENT_SUBMISSION -> EXTERNAL_CASE)
23. Audit logging for all integration lifecycle events
24. Production mock blocking (cannot dispatch mock in production)
25. Frontend summary & diagnostics schema consistency
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
    AdapterCapabilities,
    AdapterType,
    IntegrationState,
    NormalizedGovernmentStatus,
    SubmissionLifecycleState,
)
from app.schemas.government_submission import GovernmentSubmissionPackage
from app.schemas.provenance import ClaimType, SourceType
from app.services.authority_registry import is_safe_official_url
import app.services.complaint_case as complaint_case_module
from app.services.government_adapter import (
    BBMPSahaayaIntegrationAdapter,
    CPGRAMSIntegrationAdapter,
    MockGovernmentAdapter,
    NHAIIntegrationAdapter,
)
from app.services.government_integration_service import (
    GovernmentIntegrationService,
    InMemoryGovernmentSubmissionRepository,
    NOT_CONFIGURED_NOTICE,
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


class MockHttpxResponse:
    def __init__(self, status_code: int, json_data: dict = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text if text else (json.dumps(json_data) if json_data is not None else "")
        self.content = self.text.encode("utf-8")

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON object could be decoded")
        return self._json_data


def build_test_case(
    ref_id: str = "CASE-2026-M72-001",
    user_id: str = "citizen_user_001",
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
            confidence=0.94,
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
            title="Dangerous Missing Drain Cover on NH-44",
            description="Deep uncovered drain opening in the highway shoulder causing extreme hazard to road users.",
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


class TestGovernmentAdaptersM72(unittest.TestCase):
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
    # 1. Verified Adapter Registration
    # --------------------------------------------------
    def test_01_verified_adapter_registration(self):
        defs = government_registry.list_definitions()
        ids = {d.integration_id for d in defs}
        self.assertIn("gov_cpgrams", ids)
        self.assertIn("gov_nhai", ids)
        self.assertIn("gov_bbmp", ids)
        self.assertIn("mock_sandbox_integration", ids)

        cpgrams = government_registry.get_definition("gov_cpgrams")
        self.assertEqual(cpgrams.official_domain, "pgportal.gov.in")
        self.assertEqual(cpgrams.adapter_type, AdapterType.REST_API)
        self.assertEqual(cpgrams.verification_state, "api_specification_verified")

        nhai = government_registry.get_definition("gov_nhai")
        self.assertEqual(nhai.official_domain, "nhai.gov.in")
        self.assertEqual(nhai.configuration_status, IntegrationState.NOT_CONFIGURED)

        bbmp = government_registry.get_definition("gov_bbmp")
        self.assertEqual(bbmp.official_domain, "bbmp.gov.in")
        self.assertEqual(bbmp.configuration_status, IntegrationState.NOT_CONFIGURED)

    # --------------------------------------------------
    # 2. Unconfigured Adapter Behavior
    # --------------------------------------------------
    def test_02_unconfigured_adapter_behavior(self):
        nhai_adapter = government_registry.get_adapter("gov_nhai")
        self.assertIsInstance(nhai_adapter, NHAIIntegrationAdapter)
        caps = nhai_adapter.get_capabilities()
        self.assertFalse(caps.submission_supported)
        self.assertFalse(caps.status_supported)
        self.assertEqual(nhai_adapter.get_configuration_state(), IntegrationState.NOT_CONFIGURED)
        self.assertIn("Rajmarg Yatra", nhai_adapter.get_diagnostic_message())

        case = build_test_case(auth_name="National Highways Authority of India (NHAI)")
        pkg = GovernmentSubmissionPackage(
            reference_id=case.reference_id,
            issue_category="open_damaged_manhole",
            complaint_title="Test title",
            complaint_description="Test desc",
            detected_location={"latitude": 12.9716, "longitude": 77.5946},
            authority_verification_state="verified",
            created_at=datetime.now(timezone.utc),
            prepared_at=datetime.now(timezone.utc),
        )
        is_valid, errors = run_async(nhai_adapter.validate_submission(case, pkg))
        self.assertFalse(is_valid)
        self.assertIn("not available or configured", errors[0])

        sub_res = run_async(nhai_adapter.submit(case, pkg, idempotency_key="nhai-k1"))
        self.assertEqual(sub_res.state, IntegrationState.UNAVAILABLE)
        self.assertEqual(sub_res.error_code, "NHAI_API_NOT_AVAILABLE")

        bbmp_adapter = government_registry.get_adapter("gov_bbmp")
        self.assertIsInstance(bbmp_adapter, BBMPSahaayaIntegrationAdapter)
        self.assertEqual(bbmp_adapter.get_configuration_state(), IntegrationState.NOT_CONFIGURED)
        self.assertIn("BBMP Sahaaya", bbmp_adapter.get_diagnostic_message())

    # --------------------------------------------------
    # 3. Configuration Validation (unconfigured, staging, production, disabled)
    # --------------------------------------------------
    def test_03_configuration_validation(self):
        # 1. Unconfigured by default
        adapter_default = CPGRAMSIntegrationAdapter()
        self.assertEqual(adapter_default.get_configuration_state(), IntegrationState.NOT_CONFIGURED)
        self.assertFalse(adapter_default.is_configured())

        # 2. Configured staging
        adapter_staging = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="test-staging-key-12345",
            client_id_override="cvki-staging-client",
        )
        self.assertEqual(adapter_staging.get_configuration_state(), IntegrationState.CONFIGURED_STAGING)
        self.assertTrue(adapter_staging.is_configured())
        self.assertTrue(adapter_staging.get_capabilities().submission_supported)

        # 3. Configured production
        adapter_prod = CPGRAMSIntegrationAdapter(
            env_override="production",
            api_key_override="test-prod-secret-key-67890",
            client_id_override="cvki-prod-client",
        )
        self.assertEqual(adapter_prod.get_configuration_state(), IntegrationState.CONFIGURED_PRODUCTION)
        self.assertTrue(adapter_prod.is_configured())

        # 4. Missing API key in staging
        adapter_no_key = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="")
        self.assertEqual(adapter_no_key.get_configuration_state(), IntegrationState.NOT_CONFIGURED)
        self.assertFalse(adapter_no_key.is_configured())

    # --------------------------------------------------
    # 4. Authentication Failure (HTTP 401 / 403)
    # --------------------------------------------------
    def test_04_authentication_failure(self):
        adapter = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="invalid-secret-key",
            client_id_override="client-1",
        )
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case(auth_name="Department of Administrative Reforms and Public Grievances (DARPG)")
        self.case_repo.save(case)

        mock_resp = MockHttpxResponse(401, {"detail": "Invalid bearer token or API key."})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertFalse(res.success)
            self.assertEqual(res.submission_state, SubmissionLifecycleState.FAILED)
            self.assertIn("CPGRAMS_AUTHENTICATION_FAILED", res.error_code)

    # --------------------------------------------------
    # 5. Timeout & Network Interruption -> UNKNOWN_OUTCOME
    # --------------------------------------------------
    def test_05_timeout_handling_unknown_outcome(self):
        adapter = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="valid-key",
            client_id_override="client-1",
        )
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out from pgportal")):
            res = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertFalse(res.success)
            self.assertEqual(res.submission_state, SubmissionLifecycleState.UNKNOWN_OUTCOME)
            self.assertTrue(res.reconciliation_required)
            self.assertIsNone(res.external_reference_id)
            self.assertIn("Reconciliation required", res.notice)

    # --------------------------------------------------
    # 6. Upstream 4xx (400, 422) Validation Error
    # --------------------------------------------------
    def test_06_upstream_4xx_validation_error(self):
        adapter = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="valid-key",
            client_id_override="client-1",
        )
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        mock_resp = MockHttpxResponse(422, {"detail": "Road coordinate outside registered national highway segment."})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertFalse(res.success)
            self.assertEqual(res.submission_state, SubmissionLifecycleState.REJECTED)
            self.assertIn("CPGRAMS_SUBMISSION_REJECTED", res.error_code)

    # --------------------------------------------------
    # 7. Upstream 5xx Server Error
    # --------------------------------------------------
    def test_07_upstream_5xx_server_error(self):
        adapter = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="valid-key",
            client_id_override="client-1",
        )
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        mock_resp = MockHttpxResponse(503, text="Government Portal Gateway Unavailable")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertFalse(res.success)
            self.assertEqual(res.submission_state, SubmissionLifecycleState.FAILED)
            self.assertIn("UPSTREAM_GOVERNMENT_ERROR", res.error_code)

    # --------------------------------------------------
    # 8. Malformed Response Handling
    # --------------------------------------------------
    def test_08_malformed_response_handling(self):
        adapter = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="valid-key",
            client_id_override="client-1",
        )
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        # 1. Non-JSON response
        mock_resp1 = MockHttpxResponse(200, text="<html>Proxy Timeout</html>")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp1):
            res1 = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertFalse(res1.success)
            self.assertEqual(res1.error_code, "MALFORMED_RESPONSE")

        # 2. JSON without external reference ID
        mock_resp2 = MockHttpxResponse(200, {"success": True, "notice": "Acknowledged without tracking code"})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp2):
            res2 = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertFalse(res2.success)
            self.assertEqual(res2.error_code, "MALFORMED_RESPONSE")

    # --------------------------------------------------
    # 9 & 10. Successful Submission & Reference ID Extraction
    # --------------------------------------------------
    def test_09_10_successful_submission_and_reference_extraction(self):
        adapter = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="valid-key",
            client_id_override="client-1",
        )
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        mock_resp = MockHttpxResponse(201, {
            "registration_number": "DARPG/E/2026/0098765",
            "status": "registered",
            "received_at": "2026-10-15T10:30:00Z",
        })
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertTrue(res.success)
            self.assertEqual(res.submission_state, SubmissionLifecycleState.SUBMITTED)
            self.assertEqual(res.external_reference_id, "DARPG/E/2026/0098765")
            self.assertEqual(res.normalized_status, NormalizedGovernmentStatus.REGISTERED)

            subs = self.gov_sub_repo.find_by_case(case.reference_id)
            self.assertEqual(len(subs), 1)
            self.assertEqual(subs[0].external_reference_id, "DARPG/E/2026/0098765")
            self.assertIsNotNone(subs[0].response_fingerprint)

    # --------------------------------------------------
    # 11 & 12. Status Normalization & Unknown Status Safety
    # --------------------------------------------------
    def test_11_12_status_normalization_and_unknown_safety(self):
        adapter = CPGRAMSIntegrationAdapter()
        self.assertEqual(adapter.normalize_status("registered"), NormalizedGovernmentStatus.REGISTERED)
        self.assertEqual(adapter.normalize_status("lodged"), NormalizedGovernmentStatus.REGISTERED)
        self.assertEqual(adapter.normalize_status("under_examination"), NormalizedGovernmentStatus.UNDER_REVIEW)
        self.assertEqual(adapter.normalize_status("forwarded"), NormalizedGovernmentStatus.ASSIGNED)
        self.assertEqual(adapter.normalize_status("in_process"), NormalizedGovernmentStatus.IN_PROGRESS)
        self.assertEqual(adapter.normalize_status("clarification_sought"), NormalizedGovernmentStatus.AWAITING_INFORMATION)
        self.assertEqual(adapter.normalize_status("disposed"), NormalizedGovernmentStatus.RESOLVED)
        self.assertEqual(adapter.normalize_status("closed"), NormalizedGovernmentStatus.CLOSED)
        self.assertEqual(adapter.normalize_status("rejected"), NormalizedGovernmentStatus.REJECTED)
        # Unknown status
        self.assertEqual(adapter.normalize_status("custom_internal_code_99"), NormalizedGovernmentStatus.UNKNOWN)
        self.assertEqual(adapter.normalize_status(""), NormalizedGovernmentStatus.UNKNOWN)
        self.assertEqual(adapter.normalize_status(None), NormalizedGovernmentStatus.UNKNOWN)

    # --------------------------------------------------
    # 13. UNKNOWN_OUTCOME Blocks Blind Resubmission
    # --------------------------------------------------
    def test_13_unknown_outcome_blocks_blind_resubmission(self):
        adapter = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="key")
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        # Trigger timeout to create UNKNOWN_OUTCOME
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
            run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))

        # Re-attempt without reconciliation
        second_resp = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
        self.assertFalse(second_resp.success)
        self.assertEqual(second_resp.error_code, "RECONCILIATION_REQUIRED")
        self.assertTrue(second_resp.reconciliation_required)

    # --------------------------------------------------
    # 14. Reconciliation Workflow (Confirmed vs Not Received)
    # --------------------------------------------------
    def test_14_reconciliation_workflow(self):
        adapter = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="key")
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        # 1. Simulate UNKNOWN_OUTCOME
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
            run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))

        # 2. Case A: Government portal confirmed it received the complaint upon reconciliation
        mock_recon_resp = MockHttpxResponse(200, {
            "registration_number": "DARPG/E/2026/0011223",
            "status": "under_examination",
        })
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_recon_resp):
            rec_res = run_async(self.gov_service.reconcile_submission(case.reference_id))
            self.assertTrue(rec_res.resolved)
            self.assertEqual(rec_res.reconciled_state, SubmissionLifecycleState.SUBMITTED)
            self.assertEqual(rec_res.external_reference_id, "DARPG/E/2026/0011223")

        # 3. Case B: Another case where government portal confirms NOT received
        case_b = build_test_case(ref_id="CASE-2026-M72-002")
        self.case_repo.save(case_b)
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
            run_async(self.gov_service.submit_case(case_b, integration_id="gov_cpgrams"))

        mock_recon_404 = MockHttpxResponse(404, {"detail": "No grievance found"})
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_recon_404):
            rec_res_b = run_async(self.gov_service.reconcile_submission(case_b.reference_id))
            self.assertTrue(rec_res_b.resolved)
            self.assertEqual(rec_res_b.reconciled_state, SubmissionLifecycleState.READY)
            self.assertIsNone(rec_res_b.external_reference_id)
            self.assertIn("reset to READY", rec_res_b.explanation)

    # --------------------------------------------------
    # 15. Idempotency Preservation
    # --------------------------------------------------
    def test_15_idempotency_preservation(self):
        adapter = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="key")
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        mock_resp = MockHttpxResponse(201, {
            "registration_number": "DARPG/E/2026/0044556",
            "status": "registered",
        })
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
            res1 = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams", caller_idempotency_key="idemp-1"))
            self.assertTrue(res1.success)
            self.assertEqual(mock_post.call_count, 1)

            # Re-dispatch with same idempotency key
            res2 = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams", caller_idempotency_key="idemp-1"))
            self.assertTrue(res2.success)
            self.assertEqual(res2.external_reference_id, "DARPG/E/2026/0044556")
            self.assertEqual(mock_post.call_count, 1)  # No second HTTP call

    # --------------------------------------------------
    # 16. Duplicate Active Submission Protection
    # --------------------------------------------------
    def test_16_duplicate_active_submission_protection(self):
        adapter = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="key")
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        from app.schemas.government_integration import GovernmentSubmissionRecord
        inflight = GovernmentSubmissionRecord(
            submission_id="sub_inflight_test",
            case_reference_id=case.reference_id,
            integration_id="gov_cpgrams",
            submission_state=SubmissionLifecycleState.SUBMITTING,
        )
        self.gov_sub_repo.save(inflight)

        res = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "DUPLICATE_ACTIVE_SUBMISSION")

    # --------------------------------------------------
    # 17. Retry Safety (Safe GET retries, No blind POST retries)
    # --------------------------------------------------
    def test_17_retry_safety(self):
        adapter = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="key")
        government_registry.register_adapter("gov_cpgrams", adapter)

        # GET status should retry transient error
        call_count = [0]

        async def mock_get(endpoint, headers=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockHttpxResponse(502, text="Bad Gateway")
            return MockHttpxResponse(200, {"status": "in_progress"})

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            status_res = run_async(adapter.get_status("DARPG/E/2026/001"))
            self.assertTrue(status_res.success)
            self.assertEqual(call_count[0], 2)
            self.assertEqual(status_res.normalized_status, NormalizedGovernmentStatus.IN_PROGRESS)

    # --------------------------------------------------
    # 18. SSRF Protection
    # --------------------------------------------------
    def test_18_ssrf_protection(self):
        # Localhost forbidden
        adapter_bad = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="key",
            base_url_override="http://127.0.0.1:8000/api",
        )
        case = build_test_case()
        pkg = GovernmentSubmissionPackage(
            reference_id=case.reference_id,
            issue_category="manhole",
            complaint_title="T",
            complaint_description="D",
            detected_location={"latitude": 1.0, "longitude": 1.0},
            authority_verification_state="verified",
            created_at=datetime.now(timezone.utc),
            prepared_at=datetime.now(timezone.utc),
        )
        res = run_async(adapter_bad.submit(case, pkg, idempotency_key="ssrf-1"))
        self.assertEqual(res.state, IntegrationState.TEMPORARY_FAILURE)
        self.assertEqual(res.error_code, "SSRF_SECURITY_REJECTION")

        # Metadata IP forbidden
        adapter_meta = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="key",
            base_url_override="http://169.254.169.254/latest",
        )
        res_meta = run_async(adapter_meta.submit(case, pkg, idempotency_key="ssrf-2"))
        self.assertEqual(res_meta.error_code, "SSRF_SECURITY_REJECTION")

    # --------------------------------------------------
    # 19. Credential Protection & Non-Leakage
    # --------------------------------------------------
    def test_19_credential_non_leakage(self):
        adapter = CPGRAMSIntegrationAdapter(
            env_override="staging",
            api_key_override="SUPER_SECRET_CPGRAMS_TOKEN",
            client_id_override="client-1",
        )
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        summary = self.gov_service.get_submission_summary(case)
        summary_dump = summary.model_dump_json()
        self.assertNotIn("SUPER_SECRET_CPGRAMS_TOKEN", summary_dump)
        self.assertNotIn("API_KEY", summary_dump)

        defn = government_registry.get_definition("gov_cpgrams")
        self.assertNotIn("SUPER_SECRET_CPGRAMS_TOKEN", defn.model_dump_json())

    # --------------------------------------------------
    # 20. RBAC Enforcement
    # --------------------------------------------------
    def test_20_rbac_enforcement(self):
        case = build_test_case(user_id="citizen_alice")
        self.case_repo.save(case)

        # Citizen Bob cannot see Alice's submission
        mock_bob = AuthenticatedUser(user_id="citizen_bob", email="bob@civki.in", role=UserRole.CITIZEN.value)
        app.dependency_overrides[get_current_user] = lambda: mock_bob

        resp = self.client.get(f"/api/v1/government/cases/{case.reference_id}/submission")
        self.assertEqual(resp.status_code, 404)

        # Citizen cannot reconcile
        recon_resp = self.client.post(f"/api/v1/government/cases/{case.reference_id}/reconcile")
        self.assertEqual(recon_resp.status_code, 403)

    # --------------------------------------------------
    # 21. Provenance Integration
    # --------------------------------------------------
    def test_21_provenance_integration(self):
        adapter = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="key")
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        mock_resp = MockHttpxResponse(201, {
            "registration_number": "DARPG/E/2026/0077889",
            "status": "registered",
        })
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertTrue(res.success)

            ev_records = self.prov_repo.find_by_case(case.reference_id)
            gov_ev = [e for e in ev_records if e.claim_type == ClaimType.GOVERNMENT_SUBMISSION]
            self.assertEqual(len(gov_ev), 1)
            self.assertEqual(gov_ev[0].source_type, SourceType.GOVERNMENT_ADAPTER)
            self.assertEqual(gov_ev[0].matched_attribute, "external_reference_id")
            self.assertIn("DARPG/E/2026/0077889", gov_ev[0].explanation)

    # --------------------------------------------------
    # 22. Knowledge Graph Integration
    # --------------------------------------------------
    def test_22_knowledge_graph_integration(self):
        adapter = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="key")
        government_registry.register_adapter("gov_cpgrams", adapter)

        case = build_test_case()
        self.case_repo.save(case)

        mock_resp = MockHttpxResponse(201, {
            "registration_number": "DARPG/E/2026/0099112",
            "status": "registered",
        })
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams"))
            self.assertTrue(res.success)

            nodes = self.kg_repo.all_nodes()
            gov_nodes = [n for n in nodes if n.node_type == "government_submission"]
            ext_nodes = [n for n in nodes if n.node_type == "external_case"]
            self.assertEqual(len(gov_nodes), 1)
            self.assertEqual(len(ext_nodes), 1)
            self.assertEqual(ext_nodes[0].metadata["external_reference_id"], "DARPG/E/2026/0099112")

    # --------------------------------------------------
    # 23. Audit Logging
    # --------------------------------------------------
    def test_23_audit_logging(self):
        audit_events = []

        async def capture_event(action, result="success", **kwargs):
            audit_events.append({"action": action, "result": result, **kwargs})

        with patch("app.services.audit.AuditService.record_event", side_effect=capture_event):
            adapter = CPGRAMSIntegrationAdapter(env_override="staging", api_key_override="key")
            government_registry.register_adapter("gov_cpgrams", adapter)

            case = build_test_case()
            self.case_repo.save(case)

            mock_resp = MockHttpxResponse(201, {
                "registration_number": "DARPG/E/2026/0033221",
                "status": "registered",
            })
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
                run_async(self.gov_service.submit_case(case, integration_id="gov_cpgrams", user_id="u1", user_role="citizen"))

            actions = [e["action"] for e in audit_events]
            self.assertIn("government_submission_attempted", actions)
            self.assertIn("government_submission_accepted", actions)

    # --------------------------------------------------
    # 24. Production Mock Blocking
    # --------------------------------------------------
    def test_24_production_mock_blocking(self):
        case = build_test_case()
        self.case_repo.save(case)

        with patch.object(settings, "ENVIRONMENT", "production"):
            res = run_async(self.gov_service.submit_case(case, integration_id="mock_sandbox_integration"))
            self.assertFalse(res.success)
            self.assertEqual(res.error_code, "MOCK_ADAPTER_FORBIDDEN_IN_PRODUCTION")
            self.assertIn("Mock adapter cannot be used in production", res.notice)

    # --------------------------------------------------
    # 25. Frontend Summary & Diagnostics Consistency
    # --------------------------------------------------
    def test_25_frontend_summary_and_diagnostics(self):
        case = build_test_case(auth_name="Bruhat Bengaluru Mahanagara Palike (BBMP)")
        self.case_repo.save(case)

        mock_citizen = AuthenticatedUser(user_id=case.user_id, email="cit@civki.in", role=UserRole.CITIZEN.value)
        app.dependency_overrides[get_current_user] = lambda: mock_citizen

        resp = self.client.get(f"/api/v1/government/cases/{case.reference_id}/submission")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["integration_state"], IntegrationState.NOT_CONFIGURED.value)
        self.assertIn(NOT_CONFIGURED_NOTICE, data["notice"])
        self.assertIn("BBMP Sahaaya", data["diagnostic_message"])
        self.assertIsNone(data["external_reference_id"])
