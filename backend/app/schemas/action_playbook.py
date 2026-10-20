"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.3: Civic Action Playbook Knowledge Base & Schema
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.services.multimodal.contracts import IssueCategory


class ActionCategory(str, Enum):
    """Categories of operational actions recommended by CVKI playbooks."""
    INSPECT = "INSPECT"
    MITIGATE = "MITIGATE"
    DOCUMENT = "DOCUMENT"
    VERIFY = "VERIFY"
    FOLLOW_UP = "FOLLOW_UP"
    ESCALATE_PREPARATION = "ESCALATE_PREPARATION"
    MONITOR = "MONITOR"
    DO_NOT_ACT_YET = "DO_NOT_ACT_YET"


class ActionUrgency(str, Enum):
    """Urgency tier for an operational action recommendation."""
    IMMEDIATE = "immediate"
    STANDARD = "standard"
    ADVISORY = "advisory"


class PlaybookActionItem(BaseModel):
    """
    Individual operational action recommended within a civic response playbook.
    Explicitly labeled as a CVKI system recommendation, not an official government order.
    """
    model_config = ConfigDict(extra="ignore")

    action_id: str = Field(description="Unique action item code within the playbook")
    action_type: ActionCategory = Field(description="Classification of the action")
    title: str = Field(description="Short concise action heading")
    description: str = Field(description="Detailed operational guidance for the assigned role")
    urgency_level: ActionUrgency = Field(default=ActionUrgency.STANDARD)
    target_role: str = Field(
        default="field_inspector",
        description="Target stakeholder (e.g. field_inspector, maintenance_crew, authority_officer)",
    )
    required_equipment: list[str] = Field(
        default_factory=list,
        description="Recommended safety and operational tools/equipment",
    )
    epistemic_tag: str = Field(
        default="CVKI recommended action",
        description="Explicit epistemic boundary tag preventing false legal/SOP authority",
    )


class PlaybookTriggerConditions(BaseModel):
    """
    Deterministic rule criteria required to activate this playbook.
    """
    model_config = ConfigDict(extra="ignore")

    allowed_categories: list[IssueCategory] = Field(
        description="Civic issue categories this playbook applies to"
    )
    min_priority: Optional[str] = Field(
        default=None,
        description="Minimum priority tier required (e.g. P1, P2)",
    )
    requires_cv_detection: bool = Field(
        default=False,
        description="Whether a visual detection observation is mandatory to trigger",
    )
    requires_rain_context: bool = Field(
        default=False,
        description="Whether recent precipitation/flood alert is a trigger requirement",
    )
    requires_recurrence: bool = Field(
        default=False,
        description="Whether chronic defect recurrence is a trigger requirement",
    )
    min_alignment_score: Optional[float] = Field(
        default=None,
        description="Minimum cross-modal consistency score (0.0 to 1.0)",
    )


class PlaybookEvidenceRequirements(BaseModel):
    """
    Evidence requirements and inspection checkpoints for a civic playbook.
    """
    model_config = ConfigDict(extra="ignore")

    mandatory_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence elements that must be present (e.g. issue_category, location)",
    )
    recommended_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence elements recommended for higher-confidence triage",
    )
    inspection_checkpoints: list[str] = Field(
        default_factory=list,
        description="Specific on-site physical inspection criteria for field personnel",
    )


class ActionPlaybook(BaseModel):
    """
    Structured, versioned operational playbook schema.
    Provides evidence-aware action recommendations to authorized human decision-makers.
    Does NOT assert official municipal regulations, laws, or mandatory legal orders.
    """
    model_config = ConfigDict(extra="ignore")

    playbook_id: str = Field(description="Unique immutable playbook identifier (e.g. PB-MANHOLE-SAFETY-V1)")
    version: str = Field(default="1.0.0", description="Semantic playbook schema version")
    title: str = Field(description="Human-readable title of the playbook")
    description: str = Field(description="Overview of the operational response strategy")
    issue_categories: list[IssueCategory] = Field(description="Target civic defect categories")
    trigger_conditions: PlaybookTriggerConditions
    evidence_requirements: PlaybookEvidenceRequirements
    recommended_actions: list[PlaybookActionItem] = Field(description="Core recommended action items")
    optional_actions: list[PlaybookActionItem] = Field(default_factory=list)
    mitigation_actions: list[PlaybookActionItem] = Field(
        default_factory=list,
        description="Immediate risk-reduction actions while awaiting permanent repair",
    )
    prohibited_assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit cognitive caveats preventing premature or unverified conclusions",
    )
    escalation_guidance: Optional[str] = Field(
        default=None,
        description="Advisory guidance on when authority supervisor escalation should be considered",
    )
    enabled: bool = Field(default=True, description="Whether this playbook is active in the registry")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlaybookMatchResult(BaseModel):
    """
    Output of deterministic playbook matching against a complaint case context.
    """
    model_config = ConfigDict(extra="ignore")

    playbook_id: str
    playbook_version: str
    matched: bool
    match_score: float = Field(ge=0.0, le=1.0)
    match_reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[PlaybookActionItem] = Field(default_factory=list)
    mitigation_actions: list[PlaybookActionItem] = Field(default_factory=list)
    prohibited_assumptions: list[str] = Field(default_factory=list)
    inspection_checkpoints: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
