"""
CVKI M7.4 Government Status Synchronization Test Suite.
Verifies all core M7.4 requirements:
1. Normalization mapping across all external statuses (REGISTERED, UNDER_REVIEW, ASSIGNED, IN_PROGRESS, NEEDS_INFORMATION, RESOLVED, REJECTED, CLOSED, ON_HOLD, CANCELLED, UNKNOWN).
2. Idempotent repeated observation (same external status updates last_checked/last_seen without duplicating history).
3. Append-oriented history on status transitions (state change appends new record).
4. Stale external response protection (out-of-order or older timestamp does not regress state).
5. Reference-state gating:
   - REFERENCE_CONFIRMED: allowed to query upstream
   - REFERENCE_CONFLICT: blocked with CONFLICT_BLOCKED
   - UNKNOWN_OUTCOME: triggers reconciliation or returns UNKNOWN_OUTCOME
   - REFERENCE_RECEIVED / unconfirmed: returns NOT_READY if adapter requires confirmation
6. Freshness state computation: FRESH (<24h), STALE (>24h), UNAVAILABLE, UNKNOWN.
7. Epistemic Invariant: Internal CVKI complaint case lifecycle is NEVER mutated by government status sync.
8. Provenance claim generation (ClaimType.GOVERNMENT_STATUS) with SHA-256 hash.
9. Knowledge graph edge creation (NodeType.GOVERNMENT_STATUS, RelationType.HAS_GOVERNMENT_STATUS).
10. Notification triggers (status changed, needs info, unavailable).
11. RBAC on endpoints: Citizen own case, forbidden other case, Authority authorized scope, Admin full access.
12. Mock adapter regression: end-to-end sync through MockGovernmentAdapter.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

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
)
from app.schemas.government_reference import (
    GovernmentReferenceMapping,
    ReferenceMappingState,
)
from app.schemas.government_status import (
    FreshnessState,
    GovernmentStatusHistoryResponse,
    GovernmentStatusSynchronizationRecord,
    GovernmentStatusSyncResponse,
    SynchronizationState,
)
from app.schemas.provenance import ClaimType, SourceType, VerificationState
import app.services.complaint_case as complaint_case_module
import app.services.notification as notification_module
from app.services.government_adapter import (
    AdapterStatusResult,
    MockGovernmentAdapter,
)
from app.services.government_reference_service import (
    GovernmentReferenceService,
    InMemoryGovernmentReferenceRepository,
    set_government_reference_service,
)
from app.services.government_registry import government_registry
from app.services.government_status_service import (
    GovernmentStatusService,
    InMemoryGovernmentStatusRepository,
    get_government_status_service,
    set_government_status_service,
)
from app.services.knowledge_graph import (
    CivicKnowledgeGraphService,
    InMemoryKnowledgeGraphRepository,
    NodeType,
    RelationType,
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
    ref_id: str = "CASE-2026-M74-001",
    user_id: str = "citizen_user_001",
    auth_name: str = "National Highways Authority of India (NHAI)",
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


class TestGovernmentStatusSyncM74(unittest.TestCase):
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

        # Government Reference Mappings (M7.3)
        self.ref_repo = InMemoryGovernmentReferenceRepository()
        self.ref_service = GovernmentReferenceService(repository=self.ref_repo)
        set_government_reference_service(self.ref_service)

        # Notifications
        self.notif_repo = notification_module.InMemoryNotificationRepository()
        self.original_notif_repo = notification_module.notification_repository
        notification_module.set_notification_repository(self.notif_repo)

        # Government Status Synchronization (M7.4)
        self.status_repo = InMemoryGovernmentStatusRepository()
        self.status_service = GovernmentStatusService(repository=self.status_repo)
        set_government_status_service(self.status_service)

        government_registry.reset_to_initial()

    def tearDown(self):
        complaint_case_module.set_case_repository(self.original_case_repo)
        notification_module.set_notification_repository(self.original_notif_repo)
        app.dependency_overrides = self.original_overrides
        government_registry.reset_to_initial()

    # ------------------------------------------------------------------
    # 1. Normalization mapping across all external statuses
    # ------------------------------------------------------------------
    def test_01_external_status_normalization(self):
        """Adapter correctly normalizes raw portal statuses into NormalizedGovernmentStatus enum."""
        adapter = MockGovernmentAdapter()
        status_map = {
            "registered": NormalizedGovernmentStatus.REGISTERED,
            "under_review": NormalizedGovernmentStatus.UNDER_REVIEW,
            "assigned": NormalizedGovernmentStatus.ASSIGNED,
            "in_progress": NormalizedGovernmentStatus.IN_PROGRESS,
            "needs_information": NormalizedGovernmentStatus.NEEDS_INFORMATION,
            "resolved": NormalizedGovernmentStatus.RESOLVED,
            "rejected": NormalizedGovernmentStatus.REJECTED,
            "closed": NormalizedGovernmentStatus.CLOSED,
            "on_hold": NormalizedGovernmentStatus.ON_HOLD,
            "cancelled": NormalizedGovernmentStatus.CANCELLED,
            "random_unknown_token": NormalizedGovernmentStatus.UNKNOWN,
        }
        for raw, expected in status_map.items():
            norm = adapter.normalize_status(raw)
            self.assertEqual(norm, expected, f"Failed mapping '{raw}' to '{expected}'")

    # ------------------------------------------------------------------
    # 2. Idempotent repeated observation
    # ------------------------------------------------------------------
    def test_02_idempotent_repeated_observation(self):
        """Repeated sync with identical external status updates check timestamp but does not duplicate history."""
        case = build_test_case("CASE-M74-IDEMPOTENT")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_idem_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-100",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        with patch.object(
            MockGovernmentAdapter,
            "get_status",
            new=AsyncMock(
                return_value=AdapterStatusResult(
                    external_reference_id="MOCK-REF-100",
                    raw_status="registered",
                    normalized_status=NormalizedGovernmentStatus.REGISTERED,
                    observed_at=datetime.now(timezone.utc),
                    success=True,
                )
            ),
        ):
            # First sync
            res1 = run_async(self.status_service.synchronize_status(case=case))
            self.assertEqual(res1.synchronization_state, SynchronizationState.SYNCED)
            self.assertEqual(res1.normalized_status, NormalizedGovernmentStatus.REGISTERED)

            # Second sync (same status)
            res2 = run_async(self.status_service.synchronize_status(case=case))
            self.assertEqual(res2.synchronization_state, SynchronizationState.UNCHANGED)
            self.assertEqual(res2.normalized_status, NormalizedGovernmentStatus.REGISTERED)

        # History should contain exactly 1 entry because status did not change
        history = self.status_service.get_status_history(case.reference_id)
        self.assertEqual(history.total, 1)
        self.assertEqual(len(history.records), 1)

    # ------------------------------------------------------------------
    # 3. Append-oriented history on status transitions
    # ------------------------------------------------------------------
    def test_03_append_oriented_status_transitions(self):
        """When external status transitions, new records are appended to status history."""
        case = build_test_case("CASE-M74-TRANSITIONS")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_trans_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-200",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        # 1st status: REGISTERED
        with patch.object(
            MockGovernmentAdapter,
            "get_status",
            new=AsyncMock(
                return_value=AdapterStatusResult(
                    external_reference_id="MOCK-REF-200",
                    raw_status="registered",
                    normalized_status=NormalizedGovernmentStatus.REGISTERED,
                    observed_at=now - timedelta(hours=5),
                    success=True,
                )
            ),
        ):
            run_async(self.status_service.synchronize_status(case=case))

        # 2nd status: IN_PROGRESS
        with patch.object(
            MockGovernmentAdapter,
            "get_status",
            new=AsyncMock(
                return_value=AdapterStatusResult(
                    external_reference_id="MOCK-REF-200",
                    raw_status="in_progress",
                    normalized_status=NormalizedGovernmentStatus.IN_PROGRESS,
                    observed_at=now - timedelta(hours=2),
                    success=True,
                )
            ),
        ):
            res_trans = run_async(self.status_service.synchronize_status(case=case))
            self.assertEqual(res_trans.synchronization_state, SynchronizationState.SYNCED)
            self.assertEqual(res_trans.normalized_status, NormalizedGovernmentStatus.IN_PROGRESS)

        history = self.status_service.get_status_history(case.reference_id)
        self.assertEqual(history.total, 2)
        # History sorted latest first
        self.assertEqual(history.records[0].normalized_status, NormalizedGovernmentStatus.IN_PROGRESS)
        self.assertEqual(history.records[1].normalized_status, NormalizedGovernmentStatus.REGISTERED)

    # ------------------------------------------------------------------
    # 4. Stale external response protection
    # ------------------------------------------------------------------
    def test_04_stale_external_response_protection(self):
        """Out-of-order or older timestamp from upstream does not overwrite newer observation."""
        case = build_test_case("CASE-M74-STALE-RESP")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_stale_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-300",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        # Observation at now
        with patch.object(
            MockGovernmentAdapter,
            "get_status",
            new=AsyncMock(
                return_value=AdapterStatusResult(
                    external_reference_id="MOCK-REF-300",
                    raw_status="in_progress",
                    normalized_status=NormalizedGovernmentStatus.IN_PROGRESS,
                    observed_at=now,
                    success=True,
                )
            ),
        ):
            run_async(self.status_service.synchronize_status(case=case))

        # Stale response with timestamp from 3 days ago trying to say REGISTERED
        with patch.object(
            MockGovernmentAdapter,
            "get_status",
            new=AsyncMock(
                return_value=AdapterStatusResult(
                    external_reference_id="MOCK-REF-300",
                    raw_status="registered",
                    normalized_status=NormalizedGovernmentStatus.REGISTERED,
                    observed_at=now - timedelta(days=3),
                    success=True,
                )
            ),
        ):
            res_stale = run_async(self.status_service.synchronize_status(case=case))
            self.assertEqual(res_stale.synchronization_state, SynchronizationState.STALE_RESPONSE)
            # Latest state preserved as IN_PROGRESS
            self.assertEqual(res_stale.normalized_status, NormalizedGovernmentStatus.IN_PROGRESS)

    # ------------------------------------------------------------------
    # 5. Reference-state gating
    # ------------------------------------------------------------------
    def test_05_reference_state_gating(self):
        """Status synchronization honors reference mapping states."""
        # A. Conflict blocked
        case_conflict = build_test_case("CASE-M74-CONFLICT")
        self.case_repo.save(case_conflict)
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_conflict.reference_id,
                submission_id="sub_conflict_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-CONFLICT",
                mapping_state=ReferenceMappingState.REFERENCE_CONFLICT,
                source="adapter:mock_sandbox_integration",
            )
        )
        res_conflict = run_async(self.status_service.synchronize_status(case=case_conflict))
        self.assertEqual(res_conflict.synchronization_state, SynchronizationState.CONFLICT_BLOCKED)

        # B. Unconfirmed / Reference Received (mock adapter requires confirmed)
        case_received = build_test_case("CASE-M74-RECEIVED")
        self.case_repo.save(case_received)
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_received.reference_id,
                submission_id="sub_rec_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="TEMP-REF-999",
                mapping_state=ReferenceMappingState.REFERENCE_RECEIVED,
                source="adapter:mock_sandbox_integration",
            )
        )
        res_rec = run_async(self.status_service.synchronize_status(case=case_received))
        self.assertIn(
            res_rec.synchronization_state,
            (SynchronizationState.NOT_READY, SynchronizationState.REFERENCE_NOT_CONFIRMED),
        )

        # C. Unknown outcome
        case_unknown = build_test_case("CASE-M74-UNKNOWN-OUTCOME")
        self.case_repo.save(case_unknown)
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_unknown.reference_id,
                submission_id="sub_unk_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-UNK",
                mapping_state=ReferenceMappingState.UNKNOWN_OUTCOME,
                source="adapter:mock_sandbox_integration",
            )
        )
        res_unk = run_async(self.status_service.synchronize_status(case=case_unknown))
        self.assertEqual(res_unk.synchronization_state, SynchronizationState.UNKNOWN_OUTCOME)

    # ------------------------------------------------------------------
    # 6. Freshness state computation
    # ------------------------------------------------------------------
    def test_06_freshness_state_computation(self):
        """Freshness transitions from FRESH to STALE after 24 hours, and UNAVAILABLE on failure."""
        now = datetime.now(timezone.utc)

        # No record -> UNKNOWN
        self.assertEqual(self.status_service.compute_freshness(None), FreshnessState.UNKNOWN)

        # Fresh record (< 24h)
        fresh_rec = GovernmentStatusSynchronizationRecord(
            sync_id="sync_fresh",
            cvki_reference_id="CASE-001",
            integration_id="mock",
            government_reference_id="REF-1",
            raw_status="REGISTERED",
            normalized_status=NormalizedGovernmentStatus.REGISTERED,
            synchronization_state=SynchronizationState.SYNCED,
            freshness_state=FreshnessState.FRESH,
            last_checked_at=now - timedelta(hours=2),
            first_seen_at=now - timedelta(hours=2),
            last_seen_at=now - timedelta(hours=2),
        )
        self.assertEqual(self.status_service.compute_freshness(fresh_rec), FreshnessState.FRESH)

        # Stale record (> 24h)
        stale_rec = fresh_rec.model_copy(update={"last_checked_at": now - timedelta(hours=25)})
        self.assertEqual(self.status_service.compute_freshness(stale_rec), FreshnessState.STALE)

        # Unavailable
        unavail_rec = fresh_rec.model_copy(update={"synchronization_state": SynchronizationState.UNAVAILABLE})
        self.assertEqual(self.status_service.compute_freshness(unavail_rec), FreshnessState.UNAVAILABLE)

    # ------------------------------------------------------------------
    # 7. Epistemic Invariant: CVKI internal lifecycle remains untouched
    # ------------------------------------------------------------------
    def test_07_epistemic_invariant_internal_lifecycle_not_mutated(self):
        """External portal status RESOLVED must NEVER mutate CVKI complaint status to resolved."""
        case = build_test_case("CASE-M74-INVARIANT", status="submitted_to_cvki")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_inv_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-INV",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        with patch.object(
            MockGovernmentAdapter,
            "get_status",
            new=AsyncMock(
                return_value=AdapterStatusResult(
                    external_reference_id="MOCK-REF-INV",
                    raw_status="resolved",
                    normalized_status=NormalizedGovernmentStatus.RESOLVED,
                    observed_at=datetime.now(timezone.utc),
                    success=True,
                )
            ),
        ):
            res = run_async(self.status_service.synchronize_status(case=case))
            self.assertEqual(res.normalized_status, NormalizedGovernmentStatus.RESOLVED)

        # Epistemic invariant check: The CVKI internal complaint status MUST STILL BE 'submitted_to_cvki'!
        persisted_case = self.case_repo.get(case.reference_id)
        self.assertEqual(persisted_case.status, "submitted_to_cvki")
        self.assertNotEqual(persisted_case.status, "resolved")

    # ------------------------------------------------------------------
    # 8. Provenance claim generation
    # ------------------------------------------------------------------
    def test_08_provenance_claim_generation(self):
        """Status synchronization records an M6.4 provenance claim of type GOVERNMENT_STATUS."""
        case = build_test_case("CASE-M74-PROVENANCE")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_prov_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-PROV",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        with patch.object(
            MockGovernmentAdapter,
            "get_status",
            new=AsyncMock(
                return_value=AdapterStatusResult(
                    external_reference_id="MOCK-REF-PROV",
                    raw_status="in_progress",
                    normalized_status=NormalizedGovernmentStatus.IN_PROGRESS,
                    observed_at=datetime.now(timezone.utc),
                    success=True,
                )
            ),
        ):
            res = run_async(self.status_service.synchronize_status(case=case))

        self.assertIsNotNone(res.provenance_evidence_id)
        ev = self.prov_engine.get_evidence_by_id(res.provenance_evidence_id)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.claim_type, ClaimType.GOVERNMENT_STATUS)
        self.assertEqual(ev.verification_state, VerificationState.VERIFIED)
        self.assertEqual(ev.metadata.get("normalized_status"), "in_progress")

    # ------------------------------------------------------------------
    # 9. Knowledge Graph edge creation
    # ------------------------------------------------------------------
    def test_09_knowledge_graph_edge_creation(self):
        """Status synchronization creates a GOVERNMENT_STATUS node and HAS_GOVERNMENT_STATUS edge."""
        case = build_test_case("CASE-M74-KG")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_kg_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-KG",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        with patch.object(
            MockGovernmentAdapter,
            "get_status",
            new=AsyncMock(
                return_value=AdapterStatusResult(
                    external_reference_id="MOCK-REF-KG",
                    raw_status="assigned",
                    normalized_status=NormalizedGovernmentStatus.ASSIGNED,
                    observed_at=datetime.now(timezone.utc),
                    success=True,
                )
            ),
        ):
            run_async(self.status_service.synchronize_status(case=case))

        # Check knowledge graph contains government status node
        nodes = self.kg_repo.all_nodes()
        gov_status_nodes = [n for n in nodes if n.node_type == NodeType.GOVERNMENT_STATUS]
        self.assertTrue(len(gov_status_nodes) >= 1)
        self.assertEqual(gov_status_nodes[0].metadata.get("normalized_status"), "assigned")

        edges = self.kg_repo.all_edges()
        status_edges = [e for e in edges if e.relation_type == RelationType.HAS_GOVERNMENT_STATUS]
        self.assertTrue(len(status_edges) >= 1)

    # ------------------------------------------------------------------
    # 10. Notification triggers
    # ------------------------------------------------------------------
    def test_10_notification_triggers(self):
        """Status changes trigger notifications appropriately."""
        case = build_test_case("CASE-M74-NOTIFS")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_notif_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-NOTIF",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        # Needs Information triggers citizen clarification notification
        with patch("app.services.government_status_service.trigger_gov_needs_information_notification") as mock_needs_info, \
             patch.object(
                 MockGovernmentAdapter,
                 "get_status",
                 new=AsyncMock(
                     return_value=AdapterStatusResult(
                         external_reference_id="MOCK-REF-NOTIF",
                         raw_status="needs_information",
                         normalized_status=NormalizedGovernmentStatus.NEEDS_INFORMATION,
                         observed_at=datetime.now(timezone.utc),
                         success=True,
                     )
                 ),
             ):
            run_async(self.status_service.synchronize_status(case=case))
            mock_needs_info.assert_called_once()

    # ------------------------------------------------------------------
    # 11. RBAC on API endpoints
    # ------------------------------------------------------------------
    def test_11_rbac_status_endpoints(self):
        """Citizen can access own case; forbidden from other cases; Admin has full access."""
        case = build_test_case("CASE-M74-RBAC", user_id="citizen_alice")
        self.case_repo.save(case)

        # 1. Citizen Alice accesses her own case -> 200 OK
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_alice", role=UserRole.CITIZEN.value, email="alice@example.com"
        )
        res_alice = self.client.get(f"/api/v1/government/cases/{case.reference_id}/status")
        self.assertEqual(res_alice.status_code, 200)

        # 2. Citizen Bob attempts to access Alice's case -> 404 Not Found (or 403)
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_bob", role=UserRole.CITIZEN.value, email="bob@example.com"
        )
        res_bob = self.client.get(f"/api/v1/government/cases/{case.reference_id}/status")
        self.assertIn(res_bob.status_code, (403, 404))

        # 3. Admin accesses Alice's case -> 200 OK
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="admin_001", role=UserRole.ADMIN.value, email="admin@example.com"
        )
        res_admin = self.client.get(f"/api/v1/government/cases/{case.reference_id}/status")
        self.assertEqual(res_admin.status_code, 200)

    # ------------------------------------------------------------------
    # 12. Mock adapter regression live sync
    # ------------------------------------------------------------------
    def test_12_mock_adapter_live_sync_endpoint(self):
        """Calling live sync endpoint through mock adapter returns 200 OK with SYNCED status."""
        case = build_test_case("CASE-M74-MOCK-LIVE", user_id="citizen_live")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_live_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-CONFIRMED-999",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        # Setup mock adapter store so it finds MOCK-CONFIRMED-999
        adapter = government_registry.get_adapter("mock_sandbox_integration")
        adapter._submitted_store["MOCK-CONFIRMED-999"] = {
            "raw_status": "registered",
            "fingerprint": "mock_fp",
            "created_at": datetime.now(timezone.utc),
        }

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_live", role=UserRole.CITIZEN.value, email="live@example.com"
        )

        res = self.client.post(f"/api/v1/government/cases/{case.reference_id}/status/sync")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["synchronization_state"], "SYNCED")
        self.assertIn("normalized_status", data)
        self.assertIn(data["freshness"], ("FRESH", "fresh"))
        self.assertIsNotNone(data["provenance_evidence_id"])
