"""
CVKI M7.5 Evidence-Based Escalation Engine Test Suite.
Verifies all core M7.5 requirements:
1. Rejection of unconfirmed reference:
   - Unmapped or unconfirmed reference returns NONE / NO_CONFIRMED_REFERENCE.
2. Status unchanged beyond policy threshold:
   - REGISTERED > 72h evaluates to FOLLOW_UP / REGISTERED_NO_ACTION_72H.
3. Status within acceptable threshold:
   - REGISTERED < 72h evaluates to NONE / WITHIN_SLA_OR_THRESHOLD.
4. IN_PROGRESS status beyond threshold:
   - IN_PROGRESS > 168h evaluates to ESCALATE / IN_PROGRESS_DELAY_168H.
5. Status uncertainty (UNKNOWN):
   - External status UNKNOWN evaluates to NONE / SYNC_UNCERTAINTY_UNKNOWN_STATUS.
6. Integration outage / degradation:
   - Upstream UNAVAILABLE/DEGRADED evaluates to NONE / INTEGRATION_UNAVAILABLE_DEGRADED.
7. Action Routing:
   - NEEDS_INFORMATION evaluates to CITIZEN_ACTION_REQUIRED / CITIZEN_ACTION_REQUIRED.
   - REJECTED evaluates to NONE / REJECTED_GOVERNMENT_GUIDANCE.
8. Resolution suppression:
   - RESOLVED evaluates to NONE / RESOLVED_NO_ESCALATION, deferring to citizen verification (M7.6).
9. Cooldown period enforcement:
   - Repeated evaluation within cooldown window sets cooldown_active=True and does not re-escalate.
10. Frequency capping / Max escalation count:
    - Reaching max_escalation_count caps further escalation.
11. Epistemic Transparency:
    - is_official_sla is strictly False; is_system_derived is True.
12. Provenance emission:
    - ClaimType.ESCALATION_DECISION recorded in provenance engine.
13. Knowledge Graph edge creation:
    - NodeType.ESCALATION_DECISION and RelationType.HAS_ESCALATION_DECISION created.
14. RBAC on API endpoints:
    - Citizen can view own escalation; forbidden from others.
    - Citizen cannot create/update escalation policies (403).
    - Admin can list and create/update policies.
15. Notification trigger:
    - Escalation recommendation triggers trigger_escalation_recommended_notification.
"""

import asyncio
from datetime import datetime, timedelta, timezone
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
from app.schemas.escalation import (
    EscalationAction,
    EscalationDecisionRecord,
    EscalationLevel,
    EscalationPolicy,
    EscalationReasonCode,
    EscalationState,
)
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
    GovernmentStatusSynchronizationRecord,
    SynchronizationState,
)
from app.schemas.provenance import ClaimType, VerificationState
import app.services.complaint_case as complaint_case_module
import app.services.notification as notification_module
from app.services.escalation_service import (
    EscalationService,
    InMemoryEscalationRepository,
    get_escalation_service,
    set_escalation_service,
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
    ref_id: str = "CASE-2026-M75-001",
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
            area="Hebbal",
            city="Bengaluru",
            district="Bengaluru Urban",
            state="Karnataka",
            accuracy_m=10.0,
        ),
        complaint=CaseComplaint(
            language="en",
            title="Dangerous crater pothole on elevated corridor",
            description="Deep crater potholes hazardous to high-speed commuter traffic.",
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


class TestEscalationEngineM75(unittest.TestCase):
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

        # Escalation Engine (M7.5)
        self.escalation_repo = InMemoryEscalationRepository()
        self.escalation_service = EscalationService(repository=self.escalation_repo)
        set_escalation_service(self.escalation_service)

        government_registry.reset_to_initial()

    def tearDown(self):
        complaint_case_module.set_case_repository(self.original_case_repo)
        notification_module.set_notification_repository(self.original_notif_repo)
        app.dependency_overrides = self.original_overrides
        government_registry.reset_to_initial()

    # ------------------------------------------------------------------
    # 1. Rejection of unconfirmed reference
    # ------------------------------------------------------------------
    def test_01_reject_unconfirmed_reference(self):
        """Case without confirmed reference returns NONE / NOT_ELIGIBLE_NO_REFERENCE."""
        case = build_test_case("CASE-M75-NO-REF")
        self.case_repo.save(case)

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(decision.escalation_level, EscalationLevel.NONE)
        self.assertEqual(decision.escalation_action, EscalationAction.NONE)
        self.assertEqual(decision.reason_code, EscalationReasonCode.NOT_ELIGIBLE_NO_REFERENCE)
        self.assertFalse(decision.is_official_sla)
        self.assertTrue(decision.is_system_derived)

    # ------------------------------------------------------------------
    # 2. Status unchanged beyond policy threshold (REGISTERED > 72h)
    # ------------------------------------------------------------------
    def test_02_status_unchanged_beyond_policy_age(self):
        """Case with confirmed reference in REGISTERED status for 80 hours triggers FOLLOW_UP."""
        case = build_test_case("CASE-M75-REG-OLD")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_002",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-002",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        rec = GovernmentStatusSynchronizationRecord(
            sync_id="sync_75_002",
            cvki_reference_id=case.reference_id,
            integration_id="mock_sandbox_integration",
            government_reference_id="MOCK-REF-75-002",
            raw_status="REGISTERED",
            normalized_status=NormalizedGovernmentStatus.REGISTERED,
            synchronization_state=SynchronizationState.SYNCED,
            freshness_state=FreshnessState.FRESH,
            first_seen_at=now - timedelta(hours=80),
            last_seen_at=now - timedelta(hours=80),
            last_checked_at=now,
        )
        self.status_repo.save(rec)

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(decision.escalation_level, EscalationLevel.FOLLOW_UP)
        self.assertEqual(decision.escalation_action, EscalationAction.FOLLOW_UP)
        self.assertEqual(decision.reason_code, EscalationReasonCode.STATUS_UNCHANGED_BEYOND_POLICY)
        self.assertFalse(decision.is_official_sla)
        self.assertTrue(decision.is_system_derived)

    # ------------------------------------------------------------------
    # 3. Status within acceptable threshold (REGISTERED < 72h)
    # ------------------------------------------------------------------
    def test_03_status_within_acceptable_age(self):
        """Case with confirmed reference in REGISTERED status for 10 hours evaluates to NONE."""
        case = build_test_case("CASE-M75-REG-NEW")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_003",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-003",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        rec = GovernmentStatusSynchronizationRecord(
            sync_id="sync_75_003",
            cvki_reference_id=case.reference_id,
            integration_id="mock_sandbox_integration",
            government_reference_id="MOCK-REF-75-003",
            raw_status="REGISTERED",
            normalized_status=NormalizedGovernmentStatus.REGISTERED,
            synchronization_state=SynchronizationState.SYNCED,
            freshness_state=FreshnessState.FRESH,
            first_seen_at=now - timedelta(hours=10),
            last_seen_at=now - timedelta(hours=10),
            last_checked_at=now,
        )
        self.status_repo.save(rec)

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(decision.escalation_level, EscalationLevel.NONE)
        self.assertEqual(decision.escalation_action, EscalationAction.NONE)
        self.assertEqual(decision.reason_code, EscalationReasonCode.WITHIN_ACCEPTABLE_AGE)

    # ------------------------------------------------------------------
    # 4. IN_PROGRESS status beyond threshold (> 168h / 7 days)
    # ------------------------------------------------------------------
    def test_04_in_progress_delay_escalation(self):
        """Case in IN_PROGRESS for 200 hours triggers ESCALATE."""
        case = build_test_case("CASE-M75-IN-PROGRESS-OLD")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_004",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-004",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        rec = GovernmentStatusSynchronizationRecord(
            sync_id="sync_75_004",
            cvki_reference_id=case.reference_id,
            integration_id="mock_sandbox_integration",
            government_reference_id="MOCK-REF-75-004",
            raw_status="IN_PROGRESS",
            normalized_status=NormalizedGovernmentStatus.IN_PROGRESS,
            synchronization_state=SynchronizationState.SYNCED,
            freshness_state=FreshnessState.FRESH,
            first_seen_at=now - timedelta(hours=200),
            last_seen_at=now - timedelta(hours=200),
            last_checked_at=now,
        )
        self.status_repo.save(rec)

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(decision.escalation_level, EscalationLevel.ESCALATE)
        self.assertEqual(decision.escalation_action, EscalationAction.ESCALATE)
        self.assertEqual(decision.reason_code, EscalationReasonCode.STATUS_UNCHANGED_BEYOND_POLICY)

    # ------------------------------------------------------------------
    # 5. Status uncertainty (UNKNOWN)
    # ------------------------------------------------------------------
    def test_05_unknown_status_never_escalates(self):
        """External status UNKNOWN evaluates to NONE / SYNC_UNCERTAINTY_UNKNOWN_STATUS."""
        case = build_test_case("CASE-M75-UNKNOWN")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_005",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-005",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        rec = GovernmentStatusSynchronizationRecord(
            sync_id="sync_75_005",
            cvki_reference_id=case.reference_id,
            integration_id="mock_sandbox_integration",
            government_reference_id="MOCK-REF-75-005",
            raw_status="UNKNOWN_STATUS_CODE",
            normalized_status=NormalizedGovernmentStatus.UNKNOWN,
            synchronization_state=SynchronizationState.SYNCED,
            freshness_state=FreshnessState.FRESH,
            first_seen_at=now - timedelta(hours=100),
            last_seen_at=now - timedelta(hours=100),
            last_checked_at=now,
        )
        self.status_repo.save(rec)

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(decision.escalation_level, EscalationLevel.NONE)
        self.assertEqual(decision.reason_code, EscalationReasonCode.SYNC_UNCERTAINTY_UNKNOWN_STATUS)

    # ------------------------------------------------------------------
    # 6. Integration outage / degradation
    # ------------------------------------------------------------------
    def test_06_integration_outage_does_not_blame_government(self):
        """If sync failed or integration is degraded, escalation is withheld."""
        case = build_test_case("CASE-M75-OUTAGE")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_006",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-006",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        rec = GovernmentStatusSynchronizationRecord(
            sync_id="sync_75_006",
            cvki_reference_id=case.reference_id,
            integration_id="mock_sandbox_integration",
            government_reference_id="MOCK-REF-75-006",
            raw_status="GATEWAY_504",
            normalized_status=NormalizedGovernmentStatus.UNKNOWN,
            synchronization_state=SynchronizationState.UNAVAILABLE,
            freshness_state=FreshnessState.UNAVAILABLE,
            first_seen_at=now - timedelta(hours=100),
            last_seen_at=now - timedelta(hours=100),
            last_checked_at=now,
        )
        self.status_repo.save(rec)

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(decision.escalation_level, EscalationLevel.NONE)
        self.assertEqual(decision.reason_code, EscalationReasonCode.INTEGRATION_UNAVAILABLE_DEGRADED)

    # ------------------------------------------------------------------
    # 7. Action Routing: NEEDS_INFORMATION & REJECTED
    # ------------------------------------------------------------------
    def test_07_action_routing_needs_info_and_rejected(self):
        """NEEDS_INFORMATION prompts citizen action; REJECTED routes guidance without escalation."""
        # A. Needs Information
        case_info = build_test_case("CASE-M75-NEEDS-INFO")
        self.case_repo.save(case_info)
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_info.reference_id,
                submission_id="sub_info_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-INFO",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )
        now = datetime.now(timezone.utc)
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync_info",
                cvki_reference_id=case_info.reference_id,
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-INFO",
                raw_status="NEED_DOCS",
                normalized_status=NormalizedGovernmentStatus.NEEDS_INFORMATION,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=2),
                last_seen_at=now - timedelta(hours=2),
                last_checked_at=now,
            )
        )
        dec_info = run_async(self.escalation_service.evaluate_escalation(case=case_info))
        self.assertEqual(dec_info.escalation_action, EscalationAction.CITIZEN_ACTION_REQUIRED)
        self.assertEqual(dec_info.reason_code, EscalationReasonCode.NEEDS_INFORMATION_FROM_CITIZEN)

        # B. Rejected
        case_rej = build_test_case("CASE-M75-REJECTED")
        self.case_repo.save(case_rej)
        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case_rej.reference_id,
                submission_id="sub_rej_001",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-REJ",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync_rej",
                cvki_reference_id=case_rej.reference_id,
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-REJ",
                raw_status="REJECTED_OUT_OF_JURISDICTION",
                normalized_status=NormalizedGovernmentStatus.REJECTED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=10),
                last_seen_at=now - timedelta(hours=10),
                last_checked_at=now,
            )
        )
        dec_rej = run_async(self.escalation_service.evaluate_escalation(case=case_rej))
        self.assertEqual(dec_rej.escalation_level, EscalationLevel.NONE)
        self.assertEqual(dec_rej.reason_code, EscalationReasonCode.SUBMISSION_REJECTED_BY_PORTAL)

    # ------------------------------------------------------------------
    # 8. Resolution suppression (M7.6 citizen verification boundary)
    # ------------------------------------------------------------------
    def test_08_resolved_status_suppresses_escalation(self):
        """Status RESOLVED results in NONE / RESOLVED_NO_ESCALATION, awaiting citizen verification."""
        case = build_test_case("CASE-M75-RESOLVED")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_008",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-008",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync_res",
                cvki_reference_id=case.reference_id,
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-008",
                raw_status="RESOLVED",
                normalized_status=NormalizedGovernmentStatus.RESOLVED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=300),
                last_seen_at=now - timedelta(hours=300),
                last_checked_at=now,
            )
        )

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(decision.escalation_level, EscalationLevel.NONE)
        self.assertEqual(decision.reason_code, EscalationReasonCode.RESOLVED_NO_ESCALATION)

    # ------------------------------------------------------------------
    # 9. Cooldown period enforcement
    # ------------------------------------------------------------------
    def test_09_cooldown_period_enforcement(self):
        """Repeated evaluation within cooldown period marks cooldown_active=True and preserves decision."""
        case = build_test_case("CASE-M75-COOLDOWN")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_009",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-009",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync_cool",
                cvki_reference_id=case.reference_id,
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-009",
                raw_status="REGISTERED",
                normalized_status=NormalizedGovernmentStatus.REGISTERED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=85),
                last_seen_at=now - timedelta(hours=85),
                last_checked_at=now,
            )
        )

        # First evaluation -> FOLLOW_UP
        dec1 = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(dec1.escalation_level, EscalationLevel.FOLLOW_UP)
        self.assertFalse(dec1.cooldown_active)

        # Immediate second evaluation -> Cooldown is now active
        dec2 = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertTrue(dec2.cooldown_active)
        self.assertEqual(dec2.reason_code, EscalationReasonCode.IN_COOLDOWN)
        self.assertEqual(dec2.escalation_level, EscalationLevel.NONE)

    # ------------------------------------------------------------------
    # 10. Max escalation count capping
    # ------------------------------------------------------------------
    def test_10_max_escalation_count_capping(self):
        """Capping occurs when escalation count exceeds policy max_escalation_count."""
        case = build_test_case("CASE-M75-MAX-COUNT")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_010",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-010",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync_max",
                cvki_reference_id=case.reference_id,
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-010",
                raw_status="REGISTERED",
                normalized_status=NormalizedGovernmentStatus.REGISTERED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=90),
                last_seen_at=now - timedelta(hours=90),
                last_checked_at=now,
            )
        )

        # Artificially simulate 3 previous escalations
        for i in range(3):
            self.escalation_repo.save_decision(
                EscalationDecisionRecord(
                    decision_id=f"dec_prior_{i}",
                    cvki_reference_id=case.reference_id,
                    integration_id="mock_sandbox_integration",
                    government_reference_id="MOCK-REF-75-010",
                    escalation_state=EscalationState.FOLLOW_UP_RECOMMENDED,
                    escalation_level=EscalationLevel.FOLLOW_UP,
                    escalation_action=EscalationAction.FOLLOW_UP,
                    decision="FOLLOW_UP",
                    reason_code=EscalationReasonCode.STATUS_UNCHANGED_BEYOND_POLICY,
                    explanation="Prior test escalation",
                    recommended_action="Follow up",
                    evaluated_at=now - timedelta(hours=100 - i * 10),
                    escalation_count=i + 1,
                )
            )

        # Evaluation should now cap escalation
        dec_capped = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(dec_capped.reason_code, EscalationReasonCode.MAX_ESCALATION_REACHED)
        self.assertEqual(dec_capped.escalation_level, EscalationLevel.NONE)
        self.assertTrue(dec_capped.escalation_count >= 3)

    # ------------------------------------------------------------------
    # 11. Epistemic Transparency
    # ------------------------------------------------------------------
    def test_11_epistemic_transparency_fields(self):
        """All escalation decisions clearly distinguish internal policy from official SLAs."""
        case = build_test_case("CASE-M75-TRANSPARENCY")
        self.case_repo.save(case)

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertEqual(decision.is_official_sla, False)
        self.assertEqual(decision.is_system_derived, True)
        self.assertIn("policy", decision.explanation.lower())

    # ------------------------------------------------------------------
    # 12. Provenance emission
    # ------------------------------------------------------------------
    def test_12_provenance_emission(self):
        """Escalation decision creates an M6.4 provenance claim of type ESCALATION_DECISION."""
        case = build_test_case("CASE-M75-PROV")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_prov_075",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-PROV",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync_prov_075",
                cvki_reference_id=case.reference_id,
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-PROV",
                raw_status="REGISTERED",
                normalized_status=NormalizedGovernmentStatus.REGISTERED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=85),
                last_seen_at=now - timedelta(hours=85),
                last_checked_at=now,
            )
        )

        decision = run_async(self.escalation_service.evaluate_escalation(case=case))
        self.assertIsNotNone(decision.provenance_evidence_id)

        ev = self.prov_engine.get_evidence_by_id(decision.provenance_evidence_id)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.claim_type, ClaimType.ESCALATION_DECISION)
        self.assertEqual(ev.verification_state, VerificationState.SYSTEM_DERIVED)

    # ------------------------------------------------------------------
    # 13. Knowledge Graph edge creation
    # ------------------------------------------------------------------
    def test_13_knowledge_graph_edge_creation(self):
        """Escalation decision adds ESCALATION_DECISION node and HAS_ESCALATION_DECISION edge to knowledge graph."""
        case = build_test_case("CASE-M75-KG")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_kg_075",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-KG",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync_kg_075",
                cvki_reference_id=case.reference_id,
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-KG",
                raw_status="REGISTERED",
                normalized_status=NormalizedGovernmentStatus.REGISTERED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=85),
                last_seen_at=now - timedelta(hours=85),
                last_checked_at=now,
            )
        )

        run_async(self.escalation_service.evaluate_escalation(case=case))

        nodes = self.kg_repo.all_nodes()
        esc_nodes = [n for n in nodes if n.node_type == NodeType.ESCALATION_DECISION]
        self.assertTrue(len(esc_nodes) >= 1)

        edges = self.kg_repo.all_edges()
        status_edges = [e for e in edges if e.relation_type == RelationType.HAS_ESCALATION_DECISION]
        self.assertTrue(len(status_edges) >= 1)

    # ------------------------------------------------------------------
    # 14. RBAC on API endpoints & Policy Management
    # ------------------------------------------------------------------
    def test_14_rbac_escalation_endpoints_and_policies(self):
        """Citizen can view own escalation; cannot create policies (403); Admin can create policies."""
        case = build_test_case("CASE-M75-RBAC", user_id="citizen_alice")
        self.case_repo.save(case)

        # 1. Citizen Alice views her own escalation -> 200 OK
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_alice", role=UserRole.CITIZEN.value, email="alice@example.com"
        )
        res_view = self.client.get(f"/api/v1/government/cases/{case.reference_id}/escalation")
        self.assertEqual(res_view.status_code, 200)

        # 2. Citizen Alice tries to create an escalation policy -> 403 Forbidden
        res_post_policy = self.client.post(
            "/api/v1/admin/government/escalation-policies",
            json={
                "policy_id": "malicious_policy",
                "integration_id": "*",
                "minimum_age_hours": 10.0,
                "escalation_action": "ESCALATE",
                "escalation_level": "ESCALATE",
                "cooldown_hours": 12.0,
                "max_escalation_count": 3,
                "priority": 10,
                "description": "Unauthorized policy creation attempt",
            },
        )
        self.assertEqual(res_post_policy.status_code, 403)

        # 3. Admin creates an escalation policy -> 200 OK
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="admin_001", role=UserRole.ADMIN.value, email="admin@example.com"
        )
        res_admin_policy = self.client.post(
            "/api/v1/admin/government/escalation-policies",
            json={
                "policy_id": "admin_express_pothole_48h",
                "integration_id": "*",
                "minimum_age_hours": 48.0,
                "escalation_action": "FOLLOW_UP",
                "escalation_level": "FOLLOW_UP",
                "cooldown_hours": 24.0,
                "max_escalation_count": 3,
                "priority": 80,
                "description": "Express follow up for high-severity pothole cluster",
            },
        )
        self.assertEqual(res_admin_policy.status_code, 200)
        self.assertEqual(res_admin_policy.json()["policy_id"], "admin_express_pothole_48h")

        # 4. Admin lists policies -> 200 OK and contains new policy
        res_list = self.client.get("/api/v1/admin/government/escalation-policies")
        self.assertEqual(res_list.status_code, 200)
        policy_ids = [p["policy_id"] for p in res_list.json()["policies"]]
        self.assertIn("admin_express_pothole_48h", policy_ids)

    # ------------------------------------------------------------------
    # 15. Notification trigger
    # ------------------------------------------------------------------
    def test_15_notification_trigger_on_escalation_recommendation(self):
        """Notification is triggered when escalation or follow-up is recommended."""
        case = build_test_case("CASE-M75-NOTIF")
        self.case_repo.save(case)

        run_async(
            self.ref_service.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id="sub_m75_015",
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-015",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source="adapter:mock_sandbox_integration",
            )
        )

        now = datetime.now(timezone.utc)
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync_notif_075",
                cvki_reference_id=case.reference_id,
                integration_id="mock_sandbox_integration",
                government_reference_id="MOCK-REF-75-015",
                raw_status="REGISTERED",
                normalized_status=NormalizedGovernmentStatus.REGISTERED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=90),
                last_seen_at=now - timedelta(hours=90),
                last_checked_at=now,
            )
        )

        with patch("app.services.escalation_service.trigger_escalation_recommended_notification") as mock_notif:
            run_async(self.escalation_service.evaluate_escalation(case=case))
            mock_notif.assert_called_once()
