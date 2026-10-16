"""
CVKI M7.7 Government Response Analytics Service.
Aggregates, derives, and reports deterministic analytics over observed government events,
status observations, escalation decisions, and citizen resolution verifications.
Strict epistemic invariant: ANALYTICS ONLY. Never alters source records or masquerades as official SLAs.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Optional

from app.schemas.complaint_case import ComplaintCase
from app.schemas.government_analytics import (
    AuthorityPerformanceAggregate,
    CaseTimelineAnalyticsResponse,
    CaseTimelineEvent,
    DataQualityMetrics,
    EscalationAnalyticsMetrics,
    GovernmentAnalyticsSummaryResponse,
    GovernmentStatusDistributionItem,
    ResolutionVerificationMetrics,
    TransitionLatencyMetric,
)
from app.schemas.government_integration import NormalizedGovernmentStatus
from app.schemas.government_reference import ReferenceMappingState
from app.schemas.government_status import FreshnessState
from app.schemas.resolution_verification import ResolutionVerificationStatus
import app.services.complaint_case as complaint_case_module
from app.services.escalation_service import get_escalation_service
from app.services.government_reference_service import get_government_reference_service
from app.services.government_registry import government_registry
from app.services.government_status_service import get_government_status_service
from app.services.resolution_verification_service import get_resolution_verification_service

logger = logging.getLogger("cvki.government_analytics")


class GovernmentAnalyticsService:
    """
    Core Analytics Engine for Government Response Intelligence (M7.7).
    Derives reproducible metrics from verified stored observations.
    """

    def __init__(self):
        pass

    def get_summary_analytics(
        self, integration_id: Optional[str] = None
    ) -> GovernmentAnalyticsSummaryResponse:
        """
        Computes aggregate government performance, status distribution, latency,
        verification, and escalation metrics.
        """
        now = datetime.now(timezone.utc)
        ref_service = get_government_reference_service()
        status_service = get_government_status_service()
        escalation_service = get_escalation_service()
        verif_service = get_resolution_verification_service()

        # Step 1: Collect reference mappings
        all_mappings = ref_service.repository.list_all(limit=1000)
        if integration_id and integration_id != "*":
            all_mappings = [m for m in all_mappings if m.integration_id == integration_id]

        total_cases_set = set(m.cvki_reference_id for m in all_mappings)
        confirmed_mappings = [
            m for m in all_mappings if m.mapping_state == ReferenceMappingState.REFERENCE_CONFIRMED
        ]
        gov_linked_case_ids = set(m.cvki_reference_id for m in confirmed_mappings)

        # Step 2: Collect latest status records for linked cases
        status_counts: dict[NormalizedGovernmentStatus, int] = {
            s: 0 for s in NormalizedGovernmentStatus
        }
        latest_statuses = []
        missing_status_count = 0
        stale_status_count = 0
        unknown_status_count = 0

        resolved_case_ids = set()

        for case_id in gov_linked_case_ids:
            st = status_service.repository.find_latest(case_id, integration_id)
            if not st:
                missing_status_count += 1
                continue

            latest_statuses.append(st)
            norm = st.normalized_external_status
            status_counts[norm] = status_counts.get(norm, 0) + 1

            if norm == NormalizedGovernmentStatus.UNKNOWN:
                unknown_status_count += 1
            if norm == NormalizedGovernmentStatus.RESOLVED:
                resolved_case_ids.add(case_id)

            freshness = status_service.compute_freshness(st)
            if freshness in (FreshnessState.STALE, FreshnessState.UNAVAILABLE):
                stale_status_count += 1

        total_observed_statuses = len(latest_statuses)
        status_distribution = []
        for norm_stat in NormalizedGovernmentStatus:
            cnt = status_counts[norm_stat]
            pct = round((cnt / total_observed_statuses * 100.0), 1) if total_observed_statuses > 0 else 0.0
            status_distribution.append(
                GovernmentStatusDistributionItem(status=norm_stat, count=cnt, percentage=pct)
            )

        # Step 3: Compute Transition Latencies
        # Track registration -> under_review, assigned, in_progress, resolved
        latencies_by_target: dict[NormalizedGovernmentStatus, list[float]] = {
            NormalizedGovernmentStatus.UNDER_REVIEW: [],
            NormalizedGovernmentStatus.ASSIGNED: [],
            NormalizedGovernmentStatus.IN_PROGRESS: [],
            NormalizedGovernmentStatus.RESOLVED: [],
        }

        for case_id in gov_linked_case_ids:
            c_history = status_service.repository.find_history(case_id, integration_id)
            if not c_history:
                continue
            c_history = sorted(c_history, key=lambda x: x.first_seen_at or x.retrieved_at)
            reg_rec = next(
                (r for r in c_history if r.normalized_external_status == NormalizedGovernmentStatus.REGISTERED),
                None,
            )
            if not reg_rec:
                continue
            reg_time = reg_rec.first_seen_at or reg_rec.retrieved_at

            for r in c_history:
                target_stat = r.normalized_external_status
                if target_stat in latencies_by_target and r.sync_id != reg_rec.sync_id:
                    obs_time = r.first_seen_at or r.retrieved_at
                    elapsed_hours = (obs_time - reg_time).total_seconds() / 3600.0
                    if elapsed_hours >= 0:
                        latencies_by_target[target_stat].append(elapsed_hours)

        transition_latencies = []
        for target_stat, hours_list in latencies_by_target.items():
            cnt = len(hours_list)
            avg_h = round(sum(hours_list) / cnt, 2) if cnt > 0 else None
            min_h = round(min(hours_list), 2) if cnt > 0 else None
            max_h = round(max(hours_list), 2) if cnt > 0 else None
            transition_latencies.append(
                TransitionLatencyMetric(
                    transition_name=f"registration_to_{target_stat.value}",
                    target_status=target_stat,
                    sample_count=cnt,
                    avg_latency_hours=avg_h,
                    min_latency_hours=min_h,
                    max_latency_hours=max_h,
                    is_official_sla=False,
                    data_quality_label="OBSERVED",
                )
            )

        # Step 4: Resolution Verification Metrics (M7.6)
        all_verifs = verif_service.repository.list_all(limit=1000)
        if integration_id and integration_id != "*":
            all_verifs = [v for v in all_verifs if v.integration_id == integration_id]

        # Group latest verification by case
        verif_by_case: dict[str, Any] = {}
        for v in all_verifs:
            if v.cvki_reference_id not in verif_by_case:
                verif_by_case[v.cvki_reference_id] = v

        verified_resolved_cnt = sum(
            1 for v in verif_by_case.values() if v.verification_status == ResolutionVerificationStatus.VERIFIED_RESOLVED
        )
        citizen_disputed_cnt = sum(
            1 for v in verif_by_case.values() if v.verification_status == ResolutionVerificationStatus.CITIZEN_DISPUTED
        )
        partially_resolved_cnt = sum(
            1 for v in verif_by_case.values() if v.verification_status == ResolutionVerificationStatus.PARTIALLY_RESOLVED
        )
        needs_review_cnt = sum(
            1 for v in verif_by_case.values() if v.verification_status == ResolutionVerificationStatus.NEEDS_REVIEW
        )

        total_gov_resolved = len(resolved_case_ids)
        unverified_resolved_cnt = max(0, total_gov_resolved - verified_resolved_cnt - citizen_disputed_cnt - partially_resolved_cnt)

        verif_rate = (
            round(verified_resolved_cnt / total_gov_resolved, 3) if total_gov_resolved > 0 else None
        )
        disputed_total = verified_resolved_cnt + citizen_disputed_cnt
        dispute_rate = (
            round(citizen_disputed_cnt / disputed_total, 3) if disputed_total > 0 else None
        )

        res_verif_metrics = ResolutionVerificationMetrics(
            total_government_resolved_cases=total_gov_resolved,
            verified_resolved_count=verified_resolved_cnt,
            citizen_disputed_count=citizen_disputed_cnt,
            partially_resolved_count=partially_resolved_cnt,
            needs_review_count=needs_review_cnt,
            unverified_resolved_count=unverified_resolved_cnt,
            verification_rate=verif_rate,
            dispute_rate=dispute_rate,
        )

        # Step 5: Escalation Analytics (M7.5)
        # Scan decisions
        decisions = []
        for case_id in gov_linked_case_ids:
            latest_dec = escalation_service.repository.get_latest_decision(case_id, integration_id)
            if latest_dec:
                decisions.append(latest_dec)

        follow_up_cnt = sum(1 for d in decisions if d.escalation_action.value == "FOLLOW_UP")
        escalate_cnt = sum(1 for d in decisions if d.escalation_action.value == "ESCALATE")
        action_req_cnt = sum(1 for d in decisions if d.escalation_action.value == "CITIZEN_ACTION_REQUIRED")
        cooldown_cnt = sum(1 for d in decisions if d.is_in_cooldown or d.reason_code.value == "IN_COOLDOWN")
        max_capped_cnt = sum(1 for d in decisions if d.reason_code.value == "MAX_ESCALATION_REACHED")
        exceeded_threshold_cnt = sum(
            1 for d in decisions if d.reason_code.value in ("STATUS_UNCHANGED_BEYOND_POLICY", "NO_STATUS_AFTER_CONFIRMATION")
        )

        escalation_metrics = EscalationAnalyticsMetrics(
            total_cases_evaluated=len(decisions),
            follow_up_recommended_count=follow_up_cnt,
            escalation_recommended_count=escalate_cnt,
            action_required_count=action_req_cnt,
            in_cooldown_count=cooldown_cnt,
            max_escalation_capped_count=max_capped_cnt,
            exceeded_policy_threshold_count=exceeded_threshold_cnt,
        )

        # Step 6: Data Quality Metrics
        unconfirmed_ref_cnt = sum(
            1 for m in all_mappings if m.mapping_state in (ReferenceMappingState.REFERENCE_RECEIVED, ReferenceMappingState.SUBMISSION_PENDING)
        )
        data_quality = DataQualityMetrics(
            missing_status_count=missing_status_count,
            stale_status_count=stale_status_count,
            unknown_status_count=unknown_status_count,
            unconfirmed_reference_count=unconfirmed_ref_cnt,
        )

        # Step 7: Authority / Department Level Breakdown
        auth_aggregates: list[AuthorityPerformanceAggregate] = []
        grouped_by_int: dict[str, list[str]] = {}
        for m in confirmed_mappings:
            grouped_by_int.setdefault(m.integration_id, []).append(m.cvki_reference_id)

        for int_slug, c_ids in grouped_by_int.items():
            defn = government_registry.get_definition(int_slug)
            auth_name = defn.display_name if defn else int_slug
            auth_statuses = [st for st in latest_statuses if st.integration_id == int_slug]
            auth_status_counts = {}
            for s in auth_statuses:
                auth_status_counts[s.normalized_external_status.value] = (
                    auth_status_counts.get(s.normalized_external_status.value, 0) + 1
                )

            # Resolution latency for authority
            auth_res_latencies = latencies_by_target.get(NormalizedGovernmentStatus.RESOLVED, [])
            avg_res_h = round(sum(auth_res_latencies) / len(auth_res_latencies), 1) if auth_res_latencies else None

            # Dispute rate for authority
            auth_verifs = [v for v in verif_by_case.values() if v.integration_id == int_slug]
            auth_v_res = sum(1 for v in auth_verifs if v.verification_status == ResolutionVerificationStatus.VERIFIED_RESOLVED)
            auth_v_disp = sum(1 for v in auth_verifs if v.verification_status == ResolutionVerificationStatus.CITIZEN_DISPUTED)
            auth_disp_rate = (
                round(auth_v_disp / (auth_v_res + auth_v_disp), 2) if (auth_v_res + auth_v_disp) > 0 else None
            )

            auth_escs = sum(1 for d in decisions if d.integration_id == int_slug and d.escalation_action.value in ("FOLLOW_UP", "ESCALATE"))

            fresh_map: dict[str, int] = {}
            for st in auth_statuses:
                fr = status_service.compute_freshness(st).value
                fresh_map[fr] = fresh_map.get(fr, 0) + 1

            auth_aggregates.append(
                AuthorityPerformanceAggregate(
                    integration_id=int_slug,
                    authority_name=auth_name,
                    total_cases=len(set(c_ids)),
                    status_distribution=auth_status_counts,
                    avg_resolution_time_hours=avg_res_h,
                    dispute_rate=auth_disp_rate,
                    escalation_count=auth_escs,
                    freshness_summary=fresh_map,
                )
            )

        return GovernmentAnalyticsSummaryResponse(
            generated_at=now,
            total_cases=len(total_cases_set),
            total_government_linked_cases=len(gov_linked_case_ids),
            status_distribution=status_distribution,
            transition_latencies=transition_latencies,
            resolution_verification=res_verif_metrics,
            escalation=escalation_metrics,
            data_quality=data_quality,
            authority_aggregates=auth_aggregates,
            is_official_sla=False,
            epistemic_disclaimer="All metrics represent system-derived analytics from observed public events. They do not constitute official statutory government SLAs.",
        )

    def get_case_timeline_analytics(
        self, case: ComplaintCase, integration_id: Optional[str] = None
    ) -> CaseTimelineAnalyticsResponse:
        """
        Builds a complete chronological lifecycle timeline for an individual case across
        submission, reference mapping, status synchronization, escalation, and resolution verification.
        """
        now = datetime.now(timezone.utc)
        cvki_ref = case.reference_id
        ref_service = get_government_reference_service()
        status_service = get_government_status_service()
        escalation_service = get_escalation_service()
        verif_service = get_resolution_verification_service()

        events: list[CaseTimelineEvent] = []

        # 1. Case Creation Event
        events.append(
            CaseTimelineEvent(
                event_id=f"evt_create_{cvki_ref}",
                event_type="case_created",
                timestamp=case.created_at,
                source="CVKI Core",
                label="Civic complaint created in CVKI",
                details={"reference_id": cvki_ref, "issue": case.issue.label if case.issue else "Civic defect"},
            )
        )

        # 2. Reference Mapping Events
        mappings = ref_service.get_case_mappings(cvki_ref).mappings
        gov_ref = None
        target_int_id = integration_id
        for m in mappings:
            if integration_id and m.integration_id != integration_id:
                continue
            gov_ref = m.government_reference_id
            target_int_id = m.integration_id
            events.append(
                CaseTimelineEvent(
                    event_id=f"evt_ref_{m.mapping_id}",
                    event_type="reference_confirmed" if m.mapping_state == ReferenceMappingState.REFERENCE_CONFIRMED else "reference_recorded",
                    timestamp=m.first_observed_at or now,
                    source=f"Integration: {m.integration_id}",
                    label=f"Government Reference ({m.mapping_state.value}): {m.government_reference_id or 'Pending'}",
                    details={"integration_id": m.integration_id, "state": m.mapping_state.value},
                )
            )

        # 3. Government Status Transitions
        status_recs = status_service.repository.find_history(cvki_ref, target_int_id, limit=50)
        current_status = None
        is_resolved = False

        for st in status_recs:
            current_status = st.normalized_external_status.value
            if st.normalized_external_status == NormalizedGovernmentStatus.RESOLVED:
                is_resolved = True

            prev_norm = st.previous_normalized_status.value if st.previous_normalized_status else "INITIAL"
            events.append(
                CaseTimelineEvent(
                    event_id=f"evt_stat_{st.sync_id}",
                    event_type="status_sync",
                    timestamp=st.first_seen_at or st.retrieved_at,
                    source=f"Portal: {st.integration_id}",
                    label=f"Status Observation: {prev_norm.upper()} ➔ {st.normalized_external_status.value.upper()}",
                    details={"raw_status": st.raw_external_status, "normalized": st.normalized_external_status.value},
                )
            )

        # 4. Escalation Decisions
        esc_history = escalation_service.repository.get_decision_history(cvki_ref, target_int_id, limit=20)
        for dec in esc_history:
            if dec.escalation_action.value != "NONE":
                events.append(
                    CaseTimelineEvent(
                        event_id=f"evt_esc_{dec.decision_id}",
                        event_type="escalation_evaluated",
                        timestamp=dec.evaluated_at,
                        source="CVKI Escalation Engine",
                        label=f"Escalation Evaluated: {dec.decision} ({dec.reason_code.value})",
                        details={
                            "action": dec.escalation_action.value,
                            "level": dec.escalation_level.value,
                            "explanation": dec.explanation,
                        },
                    )
                )

        # 5. Citizen Resolution Verification
        verif_history = verif_service.repository.get_verification_history(cvki_ref, target_int_id, limit=20)
        is_citizen_verified = False
        is_disputed = False

        for v in verif_history:
            if v.verification_status == ResolutionVerificationStatus.VERIFIED_RESOLVED:
                is_citizen_verified = True
            if v.verification_status == ResolutionVerificationStatus.CITIZEN_DISPUTED:
                is_disputed = True

            events.append(
                CaseTimelineEvent(
                    event_id=f"evt_verif_{v.verification_id}",
                    event_type="resolution_verified",
                    timestamp=v.submitted_at,
                    source=f"Citizen: {v.citizen_user_id}",
                    label=f"Citizen Resolution Feedback: {v.citizen_response.value} ({v.verification_status.value})",
                    details={
                        "citizen_notes": v.citizen_notes,
                        "is_physical_verified": v.is_physical_resolution_verified,
                        "status": v.verification_status.value,
                    },
                )
            )

            # Review events
            for tr in v.history:
                if tr.from_status != ResolutionVerificationStatus.PENDING:
                    events.append(
                        CaseTimelineEvent(
                            event_id=f"evt_rev_{tr.transition_id}",
                            event_type="resolution_reviewed",
                            timestamp=tr.transitioned_at,
                            source=f"Reviewer: {tr.actor_user_id} ({tr.actor_role})",
                            label=f"Review Determination: {tr.from_status.value} ➔ {tr.to_status.value}",
                            details={"reason": tr.transition_reason},
                        )
                    )

        # Sort timeline chronologically
        events.sort(key=lambda e: e.timestamp)

        # Compute duration
        total_duration_hours = None
        if len(events) >= 2:
            first_time = events[0].timestamp
            last_time = events[-1].timestamp
            total_duration_hours = round((last_time - first_time).total_seconds() / 3600.0, 2)

        return CaseTimelineAnalyticsResponse(
            cvki_reference_id=cvki_ref,
            integration_id=target_int_id,
            government_reference_id=gov_ref,
            events=events,
            total_duration_hours=total_duration_hours,
            current_status=current_status,
            is_resolved=is_resolved,
            is_citizen_verified=is_citizen_verified,
            is_disputed=is_disputed,
            epistemic_disclaimer="System-derived case timeline. Reflects observed events only.",
        )


government_analytics_service = GovernmentAnalyticsService()


def get_government_analytics_service() -> GovernmentAnalyticsService:
    return government_analytics_service


def set_government_analytics_service(service: GovernmentAnalyticsService) -> None:
    global government_analytics_service
    government_analytics_service = service
