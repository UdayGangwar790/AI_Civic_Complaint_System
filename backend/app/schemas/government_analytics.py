"""
CVKI M7.7 Government Response Analytics Schemas.
Provides reproducible, read-only analytics over observed government events,
status transitions, escalation occurrences, and citizen resolution verifications.
Strictly distinguishes observed and system-derived metrics from official statutory SLAs.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.schemas.government_integration import NormalizedGovernmentStatus


class GovernmentStatusDistributionItem(BaseModel):
    """Aggregate count and percentage for a normalized government status."""
    status: NormalizedGovernmentStatus
    count: int = Field(default=0, ge=0)
    percentage: float = Field(default=0.0, ge=0.0, le=100.0)


class TransitionLatencyMetric(BaseModel):
    """Observed transition latency metrics between civic lifecycle stages."""
    transition_name: str = Field(..., description="Stage transition identifier")
    target_status: NormalizedGovernmentStatus
    sample_count: int = Field(default=0, ge=0)
    avg_latency_hours: Optional[float] = Field(None, description="Average elapsed hours (None if sample_count == 0)")
    min_latency_hours: Optional[float] = Field(None, description="Minimum elapsed hours observed")
    max_latency_hours: Optional[float] = Field(None, description="Maximum elapsed hours observed")
    is_official_sla: bool = Field(default=False, description="Strictly False: this is observed latency, not official SLA.")
    data_quality_label: str = Field(default="OBSERVED", description="Classification token: OBSERVED | SYSTEM_DERIVED")


class ResolutionVerificationMetrics(BaseModel):
    """Aggregate metrics evaluating citizen resolution verifications (M7.6)."""
    total_government_resolved_cases: int = Field(default=0, ge=0)
    verified_resolved_count: int = Field(default=0, ge=0)
    citizen_disputed_count: int = Field(default=0, ge=0)
    partially_resolved_count: int = Field(default=0, ge=0)
    needs_review_count: int = Field(default=0, ge=0)
    unverified_resolved_count: int = Field(default=0, ge=0)
    verification_rate: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="verified_resolved / total_resolved (None if no resolved cases)"
    )
    dispute_rate: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="disputed / (verified + disputed) (None if no citizen feedback)"
    )


class EscalationAnalyticsMetrics(BaseModel):
    """Aggregate metrics evaluating evidence-based escalation engine decisions (M7.5)."""
    total_cases_evaluated: int = Field(default=0, ge=0)
    follow_up_recommended_count: int = Field(default=0, ge=0)
    escalation_recommended_count: int = Field(default=0, ge=0)
    action_required_count: int = Field(default=0, ge=0)
    in_cooldown_count: int = Field(default=0, ge=0)
    max_escalation_capped_count: int = Field(default=0, ge=0)
    exceeded_policy_threshold_count: int = Field(default=0, ge=0)


class AuthorityPerformanceAggregate(BaseModel):
    """Aggregate performance and distribution breakdown per government integration / authority."""
    integration_id: str
    authority_name: str
    total_cases: int = Field(default=0, ge=0)
    status_distribution: dict[str, int] = Field(default_factory=dict)
    avg_resolution_time_hours: Optional[float] = Field(None, description="Mean hours to resolution (None if 0 samples)")
    dispute_rate: Optional[float] = Field(None, description="Dispute rate for this authority")
    escalation_count: int = Field(default=0, ge=0)
    freshness_summary: dict[str, int] = Field(default_factory=dict)


class DataQualityMetrics(BaseModel):
    """Data quality and completeness indicators across government integrations."""
    missing_status_count: int = Field(default=0, ge=0, description="Cases with confirmed reference but 0 status pulses")
    stale_status_count: int = Field(default=0, ge=0, description="Cases where status pulse is STALE or EXPIRED (> 24h)")
    unknown_status_count: int = Field(default=0, ge=0, description="Cases reporting UNKNOWN status code")
    unconfirmed_reference_count: int = Field(default=0, ge=0, description="Cases dispatched but awaiting upstream confirmation")


class GovernmentAnalyticsSummaryResponse(BaseModel):
    """Comprehensive executive dashboard response for government response analytics (M7.7)."""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_cases: int = Field(default=0, ge=0)
    total_government_linked_cases: int = Field(default=0, ge=0)
    status_distribution: list[GovernmentStatusDistributionItem] = Field(default_factory=list)
    transition_latencies: list[TransitionLatencyMetric] = Field(default_factory=list)
    resolution_verification: ResolutionVerificationMetrics = Field(default_factory=ResolutionVerificationMetrics)
    escalation: EscalationAnalyticsMetrics = Field(default_factory=EscalationAnalyticsMetrics)
    data_quality: DataQualityMetrics = Field(default_factory=DataQualityMetrics)
    authority_aggregates: list[AuthorityPerformanceAggregate] = Field(default_factory=list)
    is_official_sla: bool = Field(default=False, description="Strict epistemic invariant: always False for CVKI analytics.")
    epistemic_disclaimer: str = Field(
        default="All metrics represent system-derived analytics from observed public events. They do not constitute official statutory government SLAs."
    )


class CaseTimelineEvent(BaseModel):
    """Discrete chronological event on a case's government lifecycle timeline."""
    event_id: str
    event_type: str = Field(
        ...,
        description="Event classification: case_created | reference_confirmed | status_synchronized | escalation_evaluated | resolution_verified | resolution_reviewed",
    )
    timestamp: datetime
    source: str
    label: str
    details: dict[str, Any] = Field(default_factory=dict)


class CaseTimelineAnalyticsResponse(BaseModel):
    """Case-level lifecycle timeline and duration analytics."""
    cvki_reference_id: str
    integration_id: Optional[str] = None
    government_reference_id: Optional[str] = None
    events: list[CaseTimelineEvent] = Field(default_factory=list)
    total_duration_hours: Optional[float] = None
    current_status: Optional[str] = None
    is_resolved: bool = False
    is_citizen_verified: bool = False
    is_disputed: bool = False
    epistemic_disclaimer: str = "System-derived case timeline. Reflects observed events only."
