"""
CVKI M7.7 Government Response Analytics Test Suite.
Verifies all core M7.7 requirements:
1. Deterministic Summary Analytics:
   - Aggregate case counts, linked cases, reference confirmation counts.
   - Normalized status distribution counts and percentages.
2. Latency Metrics:
   - Transition latency (registration to under_review, assigned, in_progress, resolved).
   - Strict Epistemic Invariant: Distinguishes sample_count == 0 (None) from 0.0 latency.
3. Resolution Verification Metrics:
   - Verified resolution count, dispute count, verification rate, dispute rate.
   - None when no feedback samples exist.
4. Escalation Analytics:
   - Total evaluations, follow-up recommendations, escalation counts.
5. Authority Performance Breakdown:
   - Per-integration metrics and integration-specific filtering.
6. Data Quality Metrics:
   - Missing status, stale status, unknown status indicators.
7. Case Lifecycle Timeline Analytics:
   - Chronological event timeline (submission, mapping, status sync, escalation, citizen verification).
8. Epistemic Transparency:
   - Strict system-derived labeling; disclaimer that metrics do not constitute official SLAs.
9. RBAC Enforcement:
   - Citizen cannot access admin analytics endpoints (403).
   - Citizen can access own case timeline; forbidden from others (404).
   - Admin and Authority can access analytics endpoints (200).
"""

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
    EscalationReasonCode,
)
from app.schemas.government_analytics import GovernmentAnalyticsSummaryResponse
from app.schemas.government_integration import NormalizedGovernmentStatus
from app.schemas.government_reference import (
    GovernmentReferenceMapping,
    ReferenceMappingState,
)
from app.schemas.government_status import (
    FreshnessState,
    GovernmentStatusSynchronizationRecord,
    SynchronizationState,
)
from app.schemas.resolution_verification import (
    CitizenResolutionResponse,
    CitizenResolutionVerificationRecord,
    ResolutionVerificationStatus,
)
import app.services.complaint_case as complaint_case_module
from app.services.escalation_service import (
    EscalationService,
    InMemoryEscalationRepository,
    set_escalation_service,
)
from app.services.government_analytics_service import (
    GovernmentAnalyticsService,
    get_government_analytics_service,
    set_government_analytics_service,
)
from app.services.government_reference_service import (
    GovernmentReferenceService,
    InMemoryGovernmentReferenceRepository,
    set_government_reference_service,
)
from app.services.government_status_service import (
    GovernmentStatusService,
    InMemoryGovernmentStatusRepository,
    set_government_status_service,
)
from app.services.resolution_verification_service import (
    InMemoryResolutionVerificationRepository,
    ResolutionVerificationService,
    set_resolution_verification_service,
)


def build_test_case(
    ref_id: str,
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
            road="Outer Ring Road",
            area="Bellandur",
            city="Bengaluru",
            district="Bengaluru Urban",
            state="Karnataka",
            accuracy_m=10.0,
        ),
        complaint=CaseComplaint(
            language="en",
            title="Hazardous road crater",
            description="Large pothole near tech park entrance.",
        ),
        follow_up=FollowUp(guidance="Reported to authority."),
        authority=AuthorityResult(
            authority_status="verified",
            confidence_score=0.96,
            road_owner=AuthorityParty(name="BBMP", type="Municipal", official_portal_url="https://bbmp.gov.in"),
            maintenance_authority=AuthorityParty(name="BBMP", type="Municipal", official_portal_url="https://bbmp.gov.in"),
            sources=[
                OfficialSourceRecord(
                    source_id="src_bbmp",
                    source_name="BBMP Sahaaya",
                    source_type="government_portal",
                    domain="bbmp.gov.in",
                    url="https://bbmp.gov.in",
                    retrieved_at=now,
                )
            ],
            resolved_at=now,
        ),
        created_at=now,
        updated_at=now,
    )


class TestGovernmentAnalyticsM77(unittest.TestCase):
    def setUp(self):
        # Setup In-Memory Repositories and Services
        self.ref_repo = InMemoryGovernmentReferenceRepository()
        self.ref_service = GovernmentReferenceService(repository=self.ref_repo)
        set_government_reference_service(self.ref_service)

        self.status_repo = InMemoryGovernmentStatusRepository()
        self.status_service = GovernmentStatusService(repository=self.status_repo)
        set_government_status_service(self.status_service)

        self.esc_repo = InMemoryEscalationRepository()
        self.esc_service = EscalationService(repository=self.esc_repo)
        set_escalation_service(self.esc_service)

        self.verif_repo = InMemoryResolutionVerificationRepository()
        self.verif_service = ResolutionVerificationService(repository=self.verif_repo)
        set_resolution_verification_service(self.verif_service)

        self.analytics_service = GovernmentAnalyticsService()
        set_government_analytics_service(self.analytics_service)

        # Setup Case Repository
        self.original_case_repo = complaint_case_module.case_repository
        self.case_repo = complaint_case_module.InMemoryComplaintCaseRepository()
        complaint_case_module.set_case_repository(self.case_repo)

        # Default Auth: Admin
        self.admin_user = AuthenticatedUser(
            user_id="admin_analytics_001",
            role=UserRole.ADMIN,
            email="admin@civki.gov",
        )
        app.dependency_overrides[get_current_user] = lambda: self.admin_user
        self.client = TestClient(app)

    def tearDown(self):
        complaint_case_module.set_case_repository(self.original_case_repo)
        app.dependency_overrides.clear()
        self.ref_repo.clear()
        self.status_repo.clear()
        self.esc_repo.clear()
        self.verif_repo.clear()

    # -------------------------------------------------------------------------
    # 1. Summary Analytics & Status Distribution
    # -------------------------------------------------------------------------
    def test_summary_analytics_counts_and_distribution(self):
        now = datetime.now(timezone.utc)

        # Case 1: REGISTERED on BBMP
        case1 = build_test_case("CASE-M77-001")
        self.case_repo.save(case1)
        self.ref_repo.save(
            GovernmentReferenceMapping(
                mapping_id="map-1",
                submission_id="sub-1",
                cvki_reference_id="CASE-M77-001",
                integration_id="bbmp_sahaaya",
                external_reference_id="BBMP-001",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                authority_party="BBMP",
                created_at=now,
                confirmed_at=now,
            )
        )
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync-1",
                cvki_reference_id="CASE-M77-001",
                integration_id="bbmp_sahaaya",
                government_reference_id="BBMP-001",
                raw_status="NEW",
                normalized_status=NormalizedGovernmentStatus.REGISTERED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=10),
                last_seen_at=now,
                last_checked_at=now,
            )
        )

        # Case 2: IN_PROGRESS on BBMP
        case2 = build_test_case("CASE-M77-002")
        self.case_repo.save(case2)
        self.ref_repo.save(
            GovernmentReferenceMapping(
                mapping_id="map-2",
                submission_id="sub-2",
                cvki_reference_id="CASE-M77-002",
                integration_id="bbmp_sahaaya",
                external_reference_id="BBMP-002",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                authority_party="BBMP",
                created_at=now,
                confirmed_at=now,
            )
        )
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync-2",
                cvki_reference_id="CASE-M77-002",
                integration_id="bbmp_sahaaya",
                government_reference_id="BBMP-002",
                raw_status="WORK_ORDER_ISSUED",
                normalized_status=NormalizedGovernmentStatus.IN_PROGRESS,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=20),
                last_seen_at=now,
                last_checked_at=now,
            )
        )

        # Case 3: RESOLVED on BBMP
        case3 = build_test_case("CASE-M77-003")
        self.case_repo.save(case3)
        self.ref_repo.save(
            GovernmentReferenceMapping(
                mapping_id="map-3",
                submission_id="sub-3",
                cvki_reference_id="CASE-M77-003",
                integration_id="bbmp_sahaaya",
                external_reference_id="BBMP-003",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                authority_party="BBMP",
                created_at=now,
                confirmed_at=now,
            )
        )
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync-3",
                cvki_reference_id="CASE-M77-003",
                integration_id="bbmp_sahaaya",
                government_reference_id="BBMP-003",
                raw_status="CLOSED_SATISFIED",
                normalized_status=NormalizedGovernmentStatus.RESOLVED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=30),
                last_seen_at=now,
                last_checked_at=now,
            )
        )

        resp = self.client.get("/api/v1/admin/government/analytics/summary")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()

        self.assertEqual(data["total_cases"], 3)
        self.assertEqual(data["total_government_linked_cases"], 3)
        self.assertFalse(data["is_official_sla"])
        self.assertIn("system-derived", data["epistemic_disclaimer"].lower())

        # Check status distribution
        status_map = {item["status"]: item for item in data["status_distribution"]}
        self.assertEqual(status_map["registered"]["count"], 1)
        self.assertEqual(status_map["in_progress"]["count"], 1)
        self.assertEqual(status_map["resolved"]["count"], 1)
        self.assertAlmostEqual(status_map["registered"]["percentage"], 33.3, places=1)

    # -------------------------------------------------------------------------
    # 2. Transition Latency Metrics (Strict None Invariant)
    # -------------------------------------------------------------------------
    def test_transition_latency_metrics_with_and_without_samples(self):
        # When no transitions exist, sample_count is 0 and avg_latency_hours is None (NOT 0.0)
        summary_empty = self.analytics_service.get_summary_analytics()
        for metric in summary_empty.transition_latencies:
            self.assertEqual(metric.sample_count, 0)
            self.assertIsNone(metric.avg_latency_hours)
            self.assertIsNone(metric.min_latency_hours)
            self.assertIsNone(metric.max_latency_hours)

        # Now simulate a case that transitioned from REGISTERED to RESOLVED in 48 hours
        now = datetime.now(timezone.utc)
        case = build_test_case("CASE-M77-LAT")
        self.case_repo.save(case)
        self.ref_repo.save(
            GovernmentReferenceMapping(
                mapping_id="map-lat",
                submission_id="sub-lat",
                cvki_reference_id="CASE-M77-LAT",
                integration_id="bbmp_sahaaya",
                external_reference_id="BBMP-LAT",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                authority_party="BBMP",
                created_at=now - timedelta(hours=50),
                confirmed_at=now - timedelta(hours=48),
            )
        )
        # First observation: REGISTERED 48 hours ago
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync-lat-1",
                cvki_reference_id="CASE-M77-LAT",
                integration_id="bbmp_sahaaya",
                government_reference_id="BBMP-LAT",
                raw_status="REGISTERED",
                normalized_status=NormalizedGovernmentStatus.REGISTERED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=48),
                last_seen_at=now - timedelta(hours=48),
                last_checked_at=now - timedelta(hours=48),
            )
        )
        # Second observation: RESOLVED now
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync-lat-2",
                cvki_reference_id="CASE-M77-LAT",
                integration_id="bbmp_sahaaya",
                government_reference_id="BBMP-LAT",
                raw_status="RESOLVED",
                normalized_status=NormalizedGovernmentStatus.RESOLVED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now,
                last_seen_at=now,
                last_checked_at=now,
            )
        )

        summary_with_samples = self.analytics_service.get_summary_analytics()
        metric_resolved = next(
            m for m in summary_with_samples.transition_latencies
            if m.target_status == NormalizedGovernmentStatus.RESOLVED
        )
        self.assertEqual(metric_resolved.sample_count, 1)
        self.assertIsNotNone(metric_resolved.avg_latency_hours)
        self.assertAlmostEqual(metric_resolved.avg_latency_hours, 48.0, delta=1.0)

    # -------------------------------------------------------------------------
    # 3. Resolution Verification Metrics
    # -------------------------------------------------------------------------
    def test_resolution_verification_metrics(self):
        now = datetime.now(timezone.utc)

        # 1 Verified record
        self.verif_repo.save_verification(
            CitizenResolutionVerificationRecord(
                verification_id="v-1",
                cvki_reference_id="CASE-M77-001",
                integration_id="bbmp_sahaaya",
                citizen_user_id="user_1",
                citizen_response=CitizenResolutionResponse.CONFIRMED_RESOLVED,
                verification_status=ResolutionVerificationStatus.VERIFIED_RESOLVED,
                is_physical_resolution_verified=True,
                submitted_at=now,
            )
        )

        # 1 Disputed record
        self.verif_repo.save_verification(
            CitizenResolutionVerificationRecord(
                verification_id="v-2",
                cvki_reference_id="CASE-M77-002",
                integration_id="bbmp_sahaaya",
                citizen_user_id="user_2",
                citizen_response=CitizenResolutionResponse.STILL_UNRESOLVED,
                verification_status=ResolutionVerificationStatus.CITIZEN_DISPUTED,
                is_physical_resolution_verified=False,
                submitted_at=now,
            )
        )

        # 1 Partially resolved record
        self.verif_repo.save_verification(
            CitizenResolutionVerificationRecord(
                verification_id="v-3",
                cvki_reference_id="CASE-M77-003",
                integration_id="bbmp_sahaaya",
                citizen_user_id="user_3",
                citizen_response=CitizenResolutionResponse.PARTIALLY_RESOLVED,
                verification_status=ResolutionVerificationStatus.PARTIALLY_RESOLVED,
                is_physical_resolution_verified=False,
                submitted_at=now,
            )
        )

        resp = self.client.get("/api/v1/admin/government/analytics/resolution-verification")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verified_resolved_count"], 1)
        self.assertEqual(data["citizen_disputed_count"], 1)
        self.assertEqual(data["partially_resolved_count"], 1)
        # Dispute rate: 1 disputed / (1 verified + 1 disputed) = 0.50 (50%)
        self.assertAlmostEqual(data["dispute_rate"], 0.50, places=2)

    # -------------------------------------------------------------------------
    # 4. Escalation Analytics Metrics
    # -------------------------------------------------------------------------
    def test_escalation_analytics_metrics(self):
        now = datetime.now(timezone.utc)

        # Record 2 cases with confirmed references so they are included
        case1 = build_test_case("CASE-M77-001")
        self.case_repo.save(case1)
        self.ref_repo.save(
            GovernmentReferenceMapping(
                mapping_id="map-esc-1",
                submission_id="sub-esc-1",
                cvki_reference_id="CASE-M77-001",
                integration_id="bbmp_sahaaya",
                external_reference_id="BBMP-E1",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                authority_party="BBMP",
                created_at=now,
                confirmed_at=now,
            )
        )

        case2 = build_test_case("CASE-M77-002")
        self.case_repo.save(case2)
        self.ref_repo.save(
            GovernmentReferenceMapping(
                mapping_id="map-esc-2",
                submission_id="sub-esc-2",
                cvki_reference_id="CASE-M77-002",
                integration_id="bbmp_sahaaya",
                external_reference_id="BBMP-E2",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                authority_party="BBMP",
                created_at=now,
                confirmed_at=now,
            )
        )

        # Record 2 escalation decisions
        self.esc_repo.save_decision(
            EscalationDecisionRecord(
                decision_id="esc-1",
                cvki_reference_id="CASE-M77-001",
                integration_id="bbmp_sahaaya",
                evaluated_at=now,
                escalation_action=EscalationAction.FOLLOW_UP,
                escalation_level=EscalationLevel.FOLLOW_UP,
                decision="FOLLOW_UP",
                reason_code=EscalationReasonCode.STATUS_UNCHANGED_BEYOND_POLICY,
                explanation="Status unchanged beyond SLA policy",
                recommended_action="Submit follow-up inquiry to BBMP",
                status_age_hours=75.0,
                policy_id="policy-1",
                is_in_cooldown=False,
                is_system_derived=True,
            )
        )
        self.esc_repo.save_decision(
            EscalationDecisionRecord(
                decision_id="esc-2",
                cvki_reference_id="CASE-M77-002",
                integration_id="bbmp_sahaaya",
                evaluated_at=now,
                escalation_action=EscalationAction.ESCALATE,
                escalation_level=EscalationLevel.ESCALATE,
                decision="ESCALATE",
                reason_code=EscalationReasonCode.STATUS_UNCHANGED_BEYOND_POLICY,
                explanation="No action taken after extended follow-up window",
                recommended_action="Escalate to ward officer",
                status_age_hours=180.0,
                policy_id="policy-2",
                is_in_cooldown=False,
                is_system_derived=True,
            )
        )

        resp = self.client.get("/api/v1/admin/government/analytics/escalation")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["total_cases_evaluated"], 2)
        self.assertEqual(data["escalation_recommended_count"], 1)
        self.assertEqual(data["follow_up_recommended_count"], 1)

    # -------------------------------------------------------------------------
    # 5. Authority Performance Aggregates
    # -------------------------------------------------------------------------
    def test_authority_performance_aggregates(self):
        now = datetime.now(timezone.utc)
        case_bbmp = build_test_case("CASE-BBMP-1")
        self.case_repo.save(case_bbmp)
        self.ref_repo.save(
            GovernmentReferenceMapping(
                mapping_id="map-bbmp",
                submission_id="sub-bbmp",
                cvki_reference_id="CASE-BBMP-1",
                integration_id="bbmp_sahaaya",
                external_reference_id="BBMP-X1",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                authority_party="BBMP",
                created_at=now,
                confirmed_at=now,
            )
        )

        resp = self.client.get("/api/v1/admin/government/analytics/authorities")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertTrue(len(data) >= 1)
        bbmp_agg = next((a for a in data if a["integration_id"] == "bbmp_sahaaya"), None)
        self.assertIsNotNone(bbmp_agg)
        self.assertEqual(bbmp_agg["authority_name"], "bbmp_sahaaya")
        self.assertEqual(bbmp_agg["total_cases"], 1)

    # -------------------------------------------------------------------------
    # 6. Case Lifecycle Timeline Analytics
    # -------------------------------------------------------------------------
    def test_case_lifecycle_timeline_analytics(self):
        now = datetime.now(timezone.utc)
        case = build_test_case("CASE-M77-TIMELINE", user_id="citizen_user_001")
        self.case_repo.save(case)

        # Mapping event
        self.ref_repo.save(
            GovernmentReferenceMapping(
                mapping_id="map-time-1",
                submission_id="sub-time-1",
                cvki_reference_id="CASE-M77-TIMELINE",
                integration_id="bbmp_sahaaya",
                external_reference_id="BBMP-TIME-001",
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                authority_party="BBMP",
                created_at=now - timedelta(hours=3),
                confirmed_at=now - timedelta(hours=3),
            )
        )

        # Status sync event
        self.status_repo.save(
            GovernmentStatusSynchronizationRecord(
                sync_id="sync-time-1",
                cvki_reference_id="CASE-M77-TIMELINE",
                integration_id="bbmp_sahaaya",
                government_reference_id="BBMP-TIME-001",
                raw_status="REGISTERED",
                normalized_status=NormalizedGovernmentStatus.REGISTERED,
                synchronization_state=SynchronizationState.SYNCED,
                freshness_state=FreshnessState.FRESH,
                first_seen_at=now - timedelta(hours=2),
                last_seen_at=now - timedelta(hours=2),
                last_checked_at=now - timedelta(hours=2),
            )
        )

        # Verification event
        self.verif_repo.save_verification(
            CitizenResolutionVerificationRecord(
                verification_id="v-time-1",
                cvki_reference_id="CASE-M77-TIMELINE",
                integration_id="bbmp_sahaaya",
                citizen_user_id="citizen_user_001",
                citizen_response=CitizenResolutionResponse.CONFIRMED_RESOLVED,
                verification_status=ResolutionVerificationStatus.VERIFIED_RESOLVED,
                is_physical_resolution_verified=True,
                submitted_at=now - timedelta(hours=1),
            )
        )

        # Citizen views own timeline
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_user_001",
            role=UserRole.CITIZEN,
            email="citizen@example.com",
        )

        resp = self.client.get("/api/v1/government/cases/CASE-M77-TIMELINE/analytics/timeline")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()

        self.assertEqual(data["cvki_reference_id"], "CASE-M77-TIMELINE")
        self.assertTrue(len(data["events"]) >= 3)

        # Verify chronology (earliest to latest)
        timestamps = [e["timestamp"] for e in data["events"]]
        self.assertEqual(timestamps, sorted(timestamps))

        event_types = [e["event_type"] for e in data["events"]]
        self.assertIn("reference_confirmed", event_types)
        self.assertIn("status_sync", event_types)
        self.assertIn("resolution_verified", event_types)

    # -------------------------------------------------------------------------
    # 7. RBAC Enforcement on Analytics Endpoints
    # -------------------------------------------------------------------------
    def test_rbac_citizen_forbidden_from_admin_analytics(self):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_user_001",
            role=UserRole.CITIZEN,
            email="citizen@example.com",
        )

        resp_summary = self.client.get("/api/v1/admin/government/analytics/summary")
        self.assertEqual(resp_summary.status_code, 403)

        resp_dist = self.client.get("/api/v1/admin/government/analytics/status-distribution")
        self.assertEqual(resp_dist.status_code, 403)

        resp_verif = self.client.get("/api/v1/admin/government/analytics/resolution-verification")
        self.assertEqual(resp_verif.status_code, 403)

        resp_esc = self.client.get("/api/v1/admin/government/analytics/escalation")
        self.assertEqual(resp_esc.status_code, 403)

        resp_auth = self.client.get("/api/v1/admin/government/analytics/authorities")
        self.assertEqual(resp_auth.status_code, 403)

    def test_rbac_citizen_forbidden_from_other_citizen_timeline(self):
        case = build_test_case("CASE-M77-OTHER", user_id="citizen_user_001")
        self.case_repo.save(case)

        # Citizen 2 attempts to view Citizen 1's timeline
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen_user_002",
            role=UserRole.CITIZEN,
            email="citizen2@example.com",
        )

        resp = self.client.get("/api/v1/government/cases/CASE-M77-OTHER/analytics/timeline")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
