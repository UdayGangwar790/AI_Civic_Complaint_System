"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.4: Evidence-Aware Decision Support Schemas
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.action_playbook import PlaybookActionItem
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.cv.base_provider import StandardDetectionResult


class DecisionEvidenceQuality(str, Enum):
    """
    Epistemic assessment of evidence completeness and consistency.
    """
    STRONG = "STRONG"              # Both CV and text agree with high confidence
    PARTIAL = "PARTIAL"            # Single verified source (e.g. CV only or text only)
    WEAK = "WEAK"                  # Low confidence detection or vague text
    MISSING = "MISSING"            # Essential evidence absent
    CONFLICTING = "CONFLICTING"    # Incompatible visual and textual claims
    STALE = "STALE"                # Evidence past operational freshness window
    UNAVAILABLE = "UNAVAILABLE"    # Required data sources could not be reached


class DecisionSupportContext(BaseModel):
    """
    Input context synthesized from M1–M9 modules feeding into M10 decision support.
    Must ONLY accept server-derived or trusted inputs (no client priority overrides).
    """
    model_config = ConfigDict(extra="ignore")

    case_reference: Optional[str] = Field(default=None, max_length=64)
    issue_category: IssueCategory = Field(default=IssueCategory.UNKNOWN)
    detection_result: Optional[StandardDetectionResult] = Field(default=None)
    citizen_text: Optional[str] = Field(default=None, max_length=2000)
    normalized_text: Optional[str] = Field(default=None, max_length=2000)
    alignment_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ambiguity_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    clarification_needed: bool = Field(default=False)
    priority_level: Optional[str] = Field(
        default=None,
        description="Server-derived priority level (P1, P2, P3, P4). Client overrides are rejected.",
    )
    is_recurrent: bool = Field(default=False, description="Server-derived recurrence indicator")
    recurrence_count: int = Field(default=0, ge=0)
    is_hotspot: bool = Field(default=False, description="Server-derived hotspot indicator")
    location_context: Optional[dict[str, Any]] = Field(default=None)
    authority_name: Optional[str] = Field(default=None)
    is_authority_verified: bool = Field(default=False)
    weather_condition: Optional[str] = Field(default=None, description="Contextual precipitation info")
    traffic_level: Optional[str] = Field(default=None)
    government_status: Optional[str] = Field(default=None, description="Reported external portal status")
    visual_audit_outcome: Optional[str] = Field(default=None, description="M9.5 visual audit outcome if available")
    evidence_ids: list[str] = Field(default_factory=list, description="Associated evidence identifiers")
    metadata: dict[str, Any] = Field(default_factory=dict)


DecisionContext = DecisionSupportContext


class DecisionSupportResult(BaseModel):
    """
    Actionable operational recommendation result produced by the M10 Decision Support Engine.
    Strictly preserves epistemic boundaries:
    - Never declares physical ground truth.
    - Never automatically resolves, closes, or escalates cases.
    - Explicitly tags epistemic state as SYSTEM_DERIVED.
    """
    model_config = ConfigDict(extra="ignore")

    recommendation_id: str = Field(default_factory=lambda: str(uuid4()))
    case_reference: Optional[str] = Field(default=None)
    matched_playbooks: list[str] = Field(
        default_factory=list,
        description="IDs and versions of playbooks matched (e.g. ['PB-MANHOLE-SAFETY-V1'])",
    )
    recommended_actions: list[PlaybookActionItem] = Field(
        default_factory=list,
        description="Structured operational actions recommended for human review",
    )
    mitigation_actions: list[PlaybookActionItem] = Field(
        default_factory=list,
        description="Immediate risk-mitigation measures while awaiting permanent repair",
    )
    required_inspection: list[str] = Field(
        default_factory=list,
        description="Checkpoints that field personnel should verify on-site",
    )
    required_evidence: list[str] = Field(
        default_factory=list,
        description="Additional evidence items needed to confirm condition",
    )
    supporting_evidence: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Traceable list of evidence claims that justified this recommendation",
    )
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence gaps identified during evaluation",
    )
    explanation: str = Field(
        description="Human-readable transparent rule explanation for why actions were recommended",
    )
    uncertainty: list[str] = Field(
        default_factory=list,
        description="Explicit uncertainties and unverified parameters",
    )
    evidence_quality: DecisionEvidenceQuality = Field(
        default=DecisionEvidenceQuality.PARTIAL,
        description="Quality and consistency of supporting evidence",
    )
    epistemic_state: EpistemicState = Field(
        default=EpistemicState.SYSTEM_DERIVED,
        description="Always SYSTEM_DERIVED to enforce decision support boundary",
    )
    human_review_required: bool = Field(
        default=True,
        description="Whether an authorized human must review this before operational execution",
    )
    human_review_reasons: list[str] = Field(
        default_factory=list,
        description="Explicit justifications for mandatory human review",
    )
    decision_version: str = Field(default="1.0.0")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provenance_reference: Optional[str] = Field(default=None)


import re
from pydantic import field_validator


class RecommendationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    review_status: str = Field(
        default="REVIEWED",
        max_length=32,
        pattern=r"^(REVIEWED|ACCEPTED|MODIFIED|REJECTED|DISMISSED|OVERRIDDEN)$",
        description="Status of human review: REVIEWED, ACCEPTED, MODIFIED, REJECTED, DISMISSED, OVERRIDDEN",
    )
    review_notes: Optional[str] = Field(default=None, max_length=1000)
    decision_action_taken: Optional[str] = Field(default=None, max_length=500)

    @field_validator("review_notes", "decision_action_taken")
    @classmethod
    def sanitize_review_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "\0" in v:
            raise ValueError("Null bytes are prohibited.")
        if re.search(r"<\s*script[^>]*>", v, re.IGNORECASE) or re.search(r"javascript:", v, re.IGNORECASE):
            raise ValueError("Executable script payloads or HTML script tags are prohibited.")
        return v


class CitizenClarifyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    selected_option: Optional[str] = Field(default=None, max_length=200)
    selected_options: Optional[list[str]] = Field(default=None, max_length=10)
    free_text: Optional[str] = Field(default=None, max_length=1000)
    language: str = Field(default="en", max_length=10, pattern=r"^[a-zA-Z\-]+$")

    @field_validator("selected_option", "free_text")
    @classmethod
    def sanitize_clarify_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "\0" in v:
            raise ValueError("Null bytes are prohibited.")
        if re.search(r"<\s*script[^>]*>", v, re.IGNORECASE) or re.search(r"javascript:", v, re.IGNORECASE):
            raise ValueError("Executable script payloads or HTML script tags are prohibited.")
        return v


class CitizenViewResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    case_reference: str
    issue_category: str
    status: str
    simplified_explanation: str
    clarification_required: bool
    clarification_questions: list[Any] = Field(default_factory=list)
    available_evidence: list[str] = Field(default_factory=list)
    additional_information_needed: list[str] = Field(default_factory=list)
    follow_up_guidance: list[str] = Field(default_factory=list)
    public_location: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = Field(
        default="CIVKI recommendations and observations are system-derived and assist municipal response. They do not constitute statutory orders."
    )

