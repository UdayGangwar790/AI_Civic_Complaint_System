"""
CVKI M7.5 Evidence-Based Escalation Engine Schemas.
Provides deterministic, policy-driven escalation evaluation linking confirmed references,
synchronized external statuses, status freshness, and verified evidence.
Strictly separates observed government facts from system-derived escalation decisions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.schemas.government_integration import NormalizedGovernmentStatus
from app.schemas.government_status import FreshnessState


class EscalationLevel(str, Enum):
    """Controlled severity levels for civic escalation recommendations."""
    NONE = "NONE"
    FOLLOW_UP = "FOLLOW_UP"
    ESCALATE = "ESCALATE"
    HIGH_PRIORITY_FOLLOW_UP = "HIGH_PRIORITY_FOLLOW_UP"


class EscalationAction(str, Enum):
    """Action category determined by the escalation policy."""
    NONE = "NONE"
    FOLLOW_UP = "FOLLOW_UP"
    ESCALATE = "ESCALATE"
    CITIZEN_ACTION_REQUIRED = "CITIZEN_ACTION_REQUIRED"


class EscalationState(str, Enum):
    """Lifecycle state of escalation evaluation."""
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ELIGIBLE = "ELIGIBLE"
    FOLLOW_UP_RECOMMENDED = "FOLLOW_UP_RECOMMENDED"
    ESCALATION_RECOMMENDED = "ESCALATION_RECOMMENDED"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    COOLDOWN = "COOLDOWN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ESCALATION_SENT = "ESCALATION_SENT"
    CLOSED = "CLOSED"


class EscalationReasonCode(str, Enum):
    """Machine-readable, deterministic reason codes for escalation decisions."""
    NOT_ELIGIBLE_NO_REFERENCE = "NOT_ELIGIBLE_NO_REFERENCE"
    NOT_ELIGIBLE_UNCONFIRMED_REFERENCE = "NOT_ELIGIBLE_UNCONFIRMED_REFERENCE"
    NOT_ELIGIBLE_REFERENCE_CONFLICT = "NOT_ELIGIBLE_REFERENCE_CONFLICT"
    NOT_ELIGIBLE_INTEGRATION_UNCONFIGURED = "NOT_ELIGIBLE_INTEGRATION_UNCONFIGURED"
    INTEGRATION_UNAVAILABLE_DEGRADED = "INTEGRATION_UNAVAILABLE_DEGRADED"
    SYNC_UNCERTAINTY_UNKNOWN_STATUS = "SYNC_UNCERTAINTY_UNKNOWN_STATUS"
    NO_STATUS_AFTER_CONFIRMATION = "NO_STATUS_AFTER_CONFIRMATION"
    STATUS_UNCHANGED_BEYOND_POLICY = "STATUS_UNCHANGED_BEYOND_POLICY"
    NEEDS_INFORMATION_FROM_CITIZEN = "NEEDS_INFORMATION_FROM_CITIZEN"
    SUBMISSION_REJECTED_BY_PORTAL = "SUBMISSION_REJECTED_BY_PORTAL"
    RESOLVED_NO_ESCALATION = "RESOLVED_NO_ESCALATION"
    CLOSED_NO_ESCALATION = "CLOSED_NO_ESCALATION"
    WITHIN_ACCEPTABLE_AGE = "WITHIN_ACCEPTABLE_AGE"
    IN_COOLDOWN = "IN_COOLDOWN"
    MAX_ESCALATION_REACHED = "MAX_ESCALATION_REACHED"


class EscalationPolicy(BaseModel):
    """
    Configurable escalation policy defining deterministic thresholds for follow-up.
    Mandatory safety: labeled as ENGINEERING DEFAULT / CONFIGURABLE POLICY, not official government SLAs.
    """
    policy_id: str = Field(..., description="Unique policy identifier")
    integration_id: str = Field(default="*", description="Target integration slug, or '*' for global default")
    target_issue_category: Optional[str] = Field(None, description="Optional filter by issue category (e.g. pothole)")
    condition_normalized_status: Optional[NormalizedGovernmentStatus] = Field(
        None, description="Status condition to evaluate (e.g. registered, under_review, assigned, in_progress)"
    )
    minimum_age_hours: float = Field(default=72.0, ge=0.0, description="Minimum hours unchanged before escalation")
    maximum_age_hours: Optional[float] = Field(None, description="Optional upper boundary")
    escalation_action: EscalationAction = Field(default=EscalationAction.FOLLOW_UP)
    escalation_level: EscalationLevel = Field(default=EscalationLevel.FOLLOW_UP)
    notification_type: str = Field(default="escalation_recommended", description="Notification template key")
    cooldown_hours: float = Field(default=24.0, ge=1.0, description="Minimum hours before repeating notification")
    max_escalation_count: int = Field(default=3, ge=1, description="Maximum notifications permitted per case")
    requires_reference_confirmation: bool = Field(default=True, description="Strict requirement for confirmed reference")
    requires_fresh_status: bool = Field(default=True, description="Requires non-stale external observation")
    enabled: bool = Field(default=True)
    priority: int = Field(default=100, description="Evaluation order (lower value = higher priority)")
    description: str = Field(..., description="Clear human-readable description of this policy rule")
    is_official_sla: bool = Field(
        default=False,
        description="Mandatory epistemic flag. Always False unless verified from official published government gazette."
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EscalationPolicyCreateRequest(BaseModel):
    """Schema for admin creation or modification of escalation policies."""
    policy_id: str = Field(..., min_length=3, max_length=64)
    integration_id: str = Field(default="*")
    target_issue_category: Optional[str] = None
    condition_normalized_status: Optional[NormalizedGovernmentStatus] = None
    minimum_age_hours: float = Field(ge=0.0)
    maximum_age_hours: Optional[float] = None
    escalation_action: EscalationAction = Field(default=EscalationAction.FOLLOW_UP)
    escalation_level: EscalationLevel = Field(default=EscalationLevel.FOLLOW_UP)
    cooldown_hours: float = Field(default=24.0, ge=1.0)
    max_escalation_count: int = Field(default=3, ge=1)
    requires_reference_confirmation: bool = True
    requires_fresh_status: bool = True
    enabled: bool = True
    priority: int = 100
    description: str = Field(..., min_length=5)


class EscalationDecisionRecord(BaseModel):
    """
    Canonical record of an escalation engine evaluation.
    Clearly marks is_system_derived=True to never confuse system recommendations with official portal actions.
    """
    decision_id: str = Field(..., description="Unique decision record ID (e.g. esc_<hex>)")
    cvki_reference_id: str = Field(..., description="Associated CVKI case reference ID")
    integration_id: str = Field(..., description="Target government integration")
    government_reference_id: Optional[str] = Field(None, description="Confirmed external tracking ID")
    policy_id: Optional[str] = Field(None, description="Matched EscalationPolicy ID, if any")
    escalation_state: EscalationState = Field(default=EscalationState.NOT_ELIGIBLE)
    escalation_level: EscalationLevel = Field(default=EscalationLevel.NONE)
    escalation_action: EscalationAction = Field(default=EscalationAction.NONE)
    decision: str = Field(default="NONE", description="Summary decision token: NONE, FOLLOW_UP, ESCALATE, ACTION_REQUIRED")
    reason_code: EscalationReasonCode = Field(..., description="Deterministic machine-readable reason")
    explanation: str = Field(..., description="Clear human-readable justification of the evaluation")
    recommended_action: str = Field(..., description="Recommended citizen or casework operator action")
    observed_raw_status: Optional[str] = Field(None, description="Raw government status string at evaluation time")
    observed_normalized_status: Optional[NormalizedGovernmentStatus] = Field(None, description="Normalized status at evaluation time")
    status_age_hours: Optional[float] = Field(None, description="Calculated age in hours of current external status")
    status_freshness: Optional[FreshnessState] = Field(None, description="Freshness of status observation")
    escalation_count: int = Field(default=0, description="Cumulative escalation count for this case and policy")
    cooldown_until: Optional[datetime] = Field(None, description="Active cooldown expiry timestamp")
    is_in_cooldown: bool = Field(default=False, description="Whether evaluation is suppressed due to cooldown")
    is_system_derived: bool = Field(default=True, description="Strict epistemic invariant: always True for CVKI decisions")
    provenance_evidence_id: Optional[str] = Field(None, description="M6.4 Evidence Record ID for this decision")
    evidence_ids: list[str] = Field(default_factory=list, description="IDs of supporting status and reference evidence")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor_user_id: Optional[str] = Field(None, description="User or automated trigger that invoked evaluation")
    actor_role: Optional[str] = Field(None, description="Role of invoking actor")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Diagnostic and policy evaluation metrics")

    @property
    def cooldown_active(self) -> bool:
        return self.is_in_cooldown


class EscalationResponse(BaseModel):
    """API response model for case escalation status and latest evaluation."""
    cvki_reference_id: str
    integration_id: str
    government_reference_id: Optional[str] = None
    decision: str
    escalation_state: EscalationState
    escalation_level: EscalationLevel
    escalation_action: EscalationAction
    reason_code: EscalationReasonCode
    explanation: str
    recommended_action: str
    policy_id: Optional[str] = None
    policy_description: Optional[str] = None
    status_age_hours: Optional[float] = None
    status_freshness: Optional[FreshnessState] = None
    escalation_count: int = 0
    max_escalation_count: int = 3
    is_in_cooldown: bool = False
    cooldown_until: Optional[datetime] = None
    is_official_sla: bool = False
    is_system_derived: bool = True
    evaluated_at: Optional[datetime] = None
    provenance_evidence_id: Optional[str] = None

    @property
    def cooldown_active(self) -> bool:
        return self.is_in_cooldown


class EscalationHistoryResponse(BaseModel):
    """API response model for escalation evaluation history."""
    cvki_reference_id: str
    decisions: list[EscalationDecisionRecord]
    total: int


class EscalationPolicyListResponse(BaseModel):
    """API response model listing available escalation policies."""
    policies: list[EscalationPolicy]
    total: int
