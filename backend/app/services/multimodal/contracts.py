"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.1: Multimodal Intelligence Standard Contracts & Epistemic Boundaries

Defines framework-agnostic data contracts and controlled epistemic enumerations for the
multimodal civic intelligence pipeline. Establishes a strict boundary between citizen-reported
text, computer vision defect observations, structured civic context, and future multi-modal
reasoning outputs without hardcoded provider dependencies.
"""

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.cv.base_provider import StandardDetectionResult


# =============================================================================
# 1. Epistemic States & Information Origins
# =============================================================================

class EpistemicState(str, Enum):
    """
    Epistemic classification ensuring downstream systems distinguish between
    unverified model observations, raw citizen claims, and physical ground truth.
    """
    USER_REPORTED = "user_reported"
    MODEL_OBSERVATION = "model_observation"
    SYSTEM_DERIVED = "system_derived"
    VERIFIED_EVIDENCE = "verified_evidence"
    NOT_EVALUATED = "not_evaluated"
    UNKNOWN = "unknown"
    INCONCLUSIVE = "inconclusive"


class InformationOrigin(str, Enum):
    """Origin taxonomy identifying where a piece of information was generated."""
    USER_PROVIDED = "user_provided"
    MODEL_DERIVED = "model_derived"
    SYSTEM_DERIVED = "system_derived"


# =============================================================================
# 2. Intent & Civic Issue Taxonomies
# =============================================================================

class CivicIntent(str, Enum):
    """Controlled civic user intents recognizable by multimodal assistance."""
    REPORT_ISSUE = "report_issue"
    UPDATE_EXISTING_REPORT = "update_existing_report"
    ASK_STATUS = "ask_status"
    PROVIDE_CLARIFICATION = "provide_clarification"
    VERIFY_RESOLUTION = "verify_resolution"
    UNKNOWN = "unknown"


class IssueCategory(str, Enum):
    """
    Controlled civic issue taxonomy strictly aligned with M1.13 and CVKI core classes.
    """
    OPEN_DAMAGED_MANHOLE = "open_damaged_manhole"
    DAMAGED_MISSING_ROAD_SIGN = "damaged_missing_road_sign"
    ROAD_WATERLOGGING = "road_waterlogging"
    OTHER_CIVIC_ISSUE = "other_civic_issue"
    UNKNOWN = "unknown"


# =============================================================================
# 3. Ambiguity & Alignment States
# =============================================================================

class AmbiguityState(str, Enum):
    """Operational assessment of whether an input is clear or requires clarification."""
    CLEAR = "clear"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    NOT_EVALUATED = "not_evaluated"


class AlignmentState(str, Enum):
    """Cross-modal consistency state comparing text claims with visual/spatial evidence."""
    NOT_EVALUATED = "not_evaluated"
    ALIGNED = "aligned"
    PARTIALLY_ALIGNED = "partially_aligned"
    CONFLICTING = "conflicting"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MultimodalTaskType(str, Enum):
    """Supported multimodal operational task categories."""
    COMPLAINT_ANALYSIS = "complaint_analysis"
    CROSS_MODAL_VERIFICATION = "cross_modal_verification"
    CLARIFICATION_GENERATION = "clarification_generation"
    VERNACULAR_NORMALIZATION = "vernacular_normalization"
    RESOLUTION_AUDIT = "resolution_audit"


# =============================================================================
# 3.1 Clarification Taxonomies & Operational States (M9.3)
# =============================================================================

class ClarificationQuestionType(str, Enum):
    """
    Controlled question type taxonomy for M9.3 active clarification.
    Bounded to civic defect and report verification attributes.
    """
    ISSUE_TYPE = "ISSUE_TYPE"
    ISSUE_SCOPE = "ISSUE_SCOPE"
    ISSUE_LOCATION = "ISSUE_LOCATION"
    ISSUE_COUNT = "ISSUE_COUNT"
    ISSUE_SEVERITY_DESCRIPTION = "ISSUE_SEVERITY_DESCRIPTION"
    VISUAL_CONDITION = "VISUAL_CONDITION"
    TEMPORAL_CONTEXT = "TEMPORAL_CONTEXT"
    RESOLUTION_STATE = "RESOLUTION_STATE"
    OTHER = "OTHER"


class ClarificationAnswerType(str, Enum):
    """Supported answer modalities for citizen interaction."""
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"
    FREE_TEXT = "FREE_TEXT"


class ClarificationStatus(str, Enum):
    """
    State machine states for active clarification resolution.
    CRITICAL: 'RESOLVED' denotes that report ambiguity has been clarified,
    NOT that the physical civic defect has been resolved or verified.
    """
    NOT_REQUIRED = "NOT_REQUIRED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    QUESTION_PRESENTED = "QUESTION_PRESENTED"
    ANSWER_RECEIVED = "ANSWER_RECEIVED"
    ANSWER_ACCEPTED = "ANSWER_ACCEPTED"
    RESOLVED = "RESOLVED"
    NEEDS_USER_DECISION = "NEEDS_USER_DECISION"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    CANCELLED = "CANCELLED"


# =============================================================================
# 4. Atomic Sub-Models & Context Contracts
# =============================================================================

class ExtractedCivicEntity(BaseModel):
    """Extracted named civic entity (e.g. road, landmark, city, defect detail)."""
    entity_name: str = Field(min_length=1, max_length=256, description="Entity value")
    entity_type: str = Field(min_length=1, max_length=64, description="Entity category: road, locality, city, landmark, defect")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Extraction confidence score if available")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible entity properties")


class AmbiguityAssessment(BaseModel):
    """Structured assessment of ambiguity and missing critical civic attributes."""
    state: AmbiguityState = Field(default=AmbiguityState.NOT_EVALUATED)
    reasons: list[str] = Field(default_factory=list, max_length=20, description="Specific identified ambiguity causes")
    missing_information: list[str] = Field(default_factory=list, max_length=20, description="Critical civic fields needed")
    requires_clarification: bool = Field(default=False, description="Flag indicating if interactive clarification is recommended")


class EvidenceAlignmentAssessment(BaseModel):
    """Structured assessment of consistency between text and CV visual detections."""
    state: AlignmentState = Field(default=AlignmentState.NOT_EVALUATED)
    matched_issue_category: Optional[IssueCategory] = Field(default=None, description="Category agreed upon across modalities")
    conflicting_fields: list[str] = Field(default_factory=list, max_length=20, description="Fields where text contradicts vision")
    supporting_evidence: list[str] = Field(default_factory=list, max_length=20, description="Evidence items supporting alignment")
    missing_evidence: list[str] = Field(default_factory=list, max_length=20, description="Evidence items missing to confirm claim")
    explanation: Optional[str] = Field(default=None, max_length=1000, description="Safe summary of cross-modal reasoning")


class CivicIssueContext(BaseModel):
    """Pre-existing civic issue metadata provided by caller or previous pipeline steps."""
    reported_class: Optional[str] = Field(default=None, max_length=128)
    severity: Optional[str] = Field(default=None, max_length=64)
    hazard_description: Optional[str] = Field(default=None, max_length=500)


class MultimodalLocationContext(BaseModel):
    """Geospatial context supplied alongside the multimodal request."""
    road_name: Optional[str] = Field(default=None, max_length=256)
    locality: Optional[str] = Field(default=None, max_length=256)
    city: Optional[str] = Field(default=None, max_length=128)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)


class MultimodalMessage(BaseModel):
    """Single message in a conversational clarification context."""
    role: str = Field(description="Role of message sender (citizen, assistant, system)")
    content: str = Field(min_length=1, max_length=2000, description="Message text content")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"citizen", "assistant", "system"}:
            raise ValueError(f"Invalid message role '{v}'. Allowed roles: citizen, assistant, system.")
        return clean


# =============================================================================
# 5. Standard Multimodal Input Contract
# =============================================================================

_FORBIDDEN_PATH_CHARS = re.compile(r"(\.\.|/|\\|\x00)")
_URL_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


class MultimodalInput(BaseModel):
    """
    Standardized, strictly bounded input container for multimodal inference.
    Enforces security guards: no path traversal, no arbitrary network URLs,
    and bounded field lengths.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: str = Field(
        min_length=1,
        max_length=128,
        description="Unique request correlation identifier",
    )
    text: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Citizen-authored complaint or message text",
    )
    language: Optional[str] = Field(
        default=None,
        max_length=32,
        description="Optional language hint (e.g. 'en', 'hi', 'hinglish')",
    )
    evidence_reference_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Controlled internal evidence ID or storage reference (not a path/URL)",
    )
    cv_result: Optional[StandardDetectionResult] = Field(
        default=None,
        description="Standardized detection result from M8 computer vision runtime",
    )
    civic_issue_context: Optional[CivicIssueContext] = Field(
        default=None,
        description="Structured civic issue metadata",
    )
    location_context: Optional[MultimodalLocationContext] = Field(
        default=None,
        description="Structured location attributes",
    )
    conversation_context: list[MultimodalMessage] = Field(
        default_factory=list,
        max_length=30,
        description="Prior interactive clarification messages",
    )
    origin: InformationOrigin = Field(
        default=InformationOrigin.USER_PROVIDED,
        description="Origin tag distinguishing user vs system data",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Bounded metadata without secrets or authentication tokens",
    )

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        v_clean = v.strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", v_clean):
            raise ValueError("request_id must contain only alphanumeric characters, dots, underscores, or hyphens.")
        return v_clean

    @field_validator("evidence_reference_id")
    @classmethod
    def validate_evidence_reference(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = v.strip()
        if _URL_SCHEME_PATTERN.match(v_clean):
            raise ValueError("evidence_reference_id cannot be an external network URL or scheme.")
        if _FORBIDDEN_PATH_CHARS.search(v_clean):
            raise ValueError("evidence_reference_id cannot contain path traversal characters (.., /, \\, or null bytes).")
        return v_clean

    @field_validator("metadata")
    @classmethod
    def validate_metadata_security(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > 50:
            raise ValueError("metadata dictionary exceeds maximum allowed limit of 50 keys.")
        sensitive_patterns = {"password", "secret", "token", "jwt", "auth", "credential", "session", "cookie"}
        for k in v.keys():
            k_lower = str(k).lower()
            if any(p in k_lower for p in sensitive_patterns):
                raise ValueError(f"metadata key '{k}' contains prohibited sensitive credential pattern.")
        return v

    @model_validator(mode="after")
    def validate_presence(self) -> "MultimodalInput":
        # At least one of text, cv_result, or evidence_reference_id must be provided
        has_text = bool(self.text and self.text.strip())
        has_cv = self.cv_result is not None
        has_evidence = bool(self.evidence_reference_id and self.evidence_reference_id.strip())
        if not (has_text or has_cv or has_evidence):
            raise ValueError("MultimodalInput must contain at least one of: text, cv_result, or evidence_reference_id.")
        return self


# =============================================================================
# 6. Standard Multimodal Output Contract
# =============================================================================

class StandardMultimodalResult(BaseModel):
    """
    Standardized, model-independent multimodal inference response contract.
    Decoupled from underlying LLM/VLM/framework token formats.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = Field(description="Whether multimodal processing completed successfully")
    provider_id: str = Field(min_length=1, description="Identifier of the executing provider implementation")
    model_id: str = Field(min_length=1, description="Identifier of the multimodal model instance")
    model_version: str = Field(min_length=1, description="Release version of the multimodal model artifact")
    model_hash: Optional[str] = Field(default=None, description="SHA-256 cryptographic hash of model/adapter")
    task: MultimodalTaskType | str = Field(
        default=MultimodalTaskType.COMPLAINT_ANALYSIS,
        description="Task executed",
    )
    processing_time_ms: float = Field(default=0.0, ge=0.0, description="Processing duration in milliseconds")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of multimodal execution",
    )
    language: Optional[str] = Field(default=None, description="Identified language of interaction")
    normalized_intent: CivicIntent = Field(default=CivicIntent.UNKNOWN, description="Classified civic intent")
    issue_category: IssueCategory = Field(default=IssueCategory.UNKNOWN, description="Classified civic issue category")
    extracted_entities: list[ExtractedCivicEntity] = Field(
        default_factory=list,
        max_length=100,
        description="Civic entities extracted from text/evidence",
    )
    ambiguity_assessment: AmbiguityAssessment = Field(
        default_factory=AmbiguityAssessment,
        description="Assessment of report ambiguity and missing details",
    )
    evidence_alignment: EvidenceAlignmentAssessment = Field(
        default_factory=EvidenceAlignmentAssessment,
        description="Consistency assessment comparing text with visual detection",
    )
    suggested_clarifications: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="List of targeted, non-leading clarifying questions for citizen",
    )
    explanation: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Transparent natural language summary of analysis",
    )
    epistemic_state: EpistemicState = Field(
        default=EpistemicState.MODEL_OBSERVATION,
        description="Epistemic status strictly bounding model observation vs verified truth",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible provider metadata without credentials",
    )

    @field_validator("epistemic_state")
    @classmethod
    def validate_epistemic_integrity(cls, v: EpistemicState) -> EpistemicState:
        # A raw model result cannot unilaterally declare itself verified physical ground truth
        if v == EpistemicState.VERIFIED_EVIDENCE:
            raise ValueError(
                "StandardMultimodalResult cannot claim VERIFIED_EVIDENCE directly; "
                "epistemic state must be MODEL_OBSERVATION, SYSTEM_DERIVED, or INCONCLUSIVE."
            )
        return v


# =============================================================================
# 7. Active Clarification Contracts (M9.3)
# =============================================================================

class ClarificationQuestion(BaseModel):
    """
    Structured, targeted, non-leading clarification question generated by M9.3.
    """
    question_id: str = Field(
        min_length=1,
        max_length=128,
        description="Deterministic unique question identifier",
    )
    question_text: str = Field(
        min_length=1,
        max_length=1000,
        description="Citizen-friendly, neutral, non-leading question text",
    )
    target_field: str = Field(
        min_length=1,
        max_length=64,
        description="Target civic field being clarified (e.g. issue_type, issue_scope, location)",
    )
    question_type: ClarificationQuestionType = Field(
        default=ClarificationQuestionType.ISSUE_TYPE,
        description="Controlled category of clarification",
    )
    options: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Bounded, discrete response choices presented to the citizen",
    )
    required: bool = Field(
        default=True,
        description="Whether this clarification is critical for processing",
    )
    priority: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Priority order (1 is highest priority)",
    )
    reason: str = Field(
        min_length=1,
        max_length=500,
        description="Explainable system rationale for why this question is needed",
    )
    answer_type: ClarificationAnswerType = Field(
        default=ClarificationAnswerType.SINGLE_CHOICE,
        description="Expected format of the citizen response",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Bounded non-sensitive context metadata",
    )


class ClarificationAnswer(BaseModel):
    """
    Citizen-supplied clarification response.
    CRITICAL: Epistemic state is strictly USER_REPORTED. An answer expresses citizen intent,
    NOT verified physical ground truth.
    """
    question_id: str = Field(
        min_length=1,
        max_length=128,
        description="Identifier of the question being answered",
    )
    selected_option: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Selected discrete choice for SINGLE_CHOICE questions",
    )
    selected_options: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Selected choices for MULTI_CHOICE questions",
    )
    free_text: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional bounded citizen elaboration",
    )

    answer_type: ClarificationAnswerType = Field(
        default=ClarificationAnswerType.SINGLE_CHOICE,
        description="Answer modality",
    )
    valid: bool = Field(
        default=True,
        description="Whether the answer passed validation guards",
    )
    normalized_value: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Internal normalized representation of citizen choice",
    )
    origin: str = Field(
        default="citizen",
        max_length=64,
        description="Origin of answer data (must be citizen)",
    )
    epistemic_state: EpistemicState = Field(
        default=EpistemicState.USER_REPORTED,
        description="Epistemic status strictly bounded to USER_REPORTED",
    )

    @field_validator("epistemic_state")
    @classmethod
    def validate_answer_epistemic_state(cls, v: EpistemicState) -> EpistemicState:
        if v != EpistemicState.USER_REPORTED:
            raise ValueError(
                f"ClarificationAnswer epistemic_state must remain USER_REPORTED. "
                f"Citizen responses cannot be labeled '{v.value}'."
            )
        return v


class ClarificationResult(BaseModel):
    """
    Strict Pydantic contract capturing the output of M9.3 Active Clarification.
    CRITICAL: status='RESOLVED' denotes that report ambiguity has been clarified,
    NOT that the physical civic defect has been resolved.
    """
    status: ClarificationStatus = Field(
        default=ClarificationStatus.NOT_REQUIRED,
        description="Operational state of the clarification process",
    )
    requires_clarification: bool = Field(
        default=False,
        description="Boolean indicator whether citizen clarification is currently required",
    )
    questions: list[ClarificationQuestion] = Field(
        default_factory=list,
        max_length=3,
        description="Bounded list of targeted clarification questions (max budget 3)",
    )
    unresolved_fields: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Civic attributes that remain unresolved",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="High-level explainable justification for clarification state",
    )
    max_questions: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Maximum permitted questions per clarification cycle",
    )
    epistemic_state: EpistemicState = Field(
        default=EpistemicState.USER_REPORTED,
        description="Epistemic state of the clarification result",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Bounded metadata without credentials",
    )

    @field_validator("epistemic_state")
    @classmethod
    def validate_result_epistemic_state(cls, v: EpistemicState) -> EpistemicState:
        if v == EpistemicState.VERIFIED_EVIDENCE:
            raise ValueError(
                "ClarificationResult cannot claim VERIFIED_EVIDENCE; "
                "clarification resolves report ambiguity, not physical ground truth."
            )
        return v


# =============================================================================
# 8. Multilingual Vernacular Normalization Contracts (M9.4)
# =============================================================================

class AssertionType(str, Enum):
    """Controlled assertion status for citizen reported claims."""
    ASSERTED = "ASSERTED"
    NEGATED = "NEGATED"
    UNCERTAIN = "UNCERTAIN"
    QUESTION = "QUESTION"
    UNKNOWN = "UNKNOWN"


class VernacularNormalizationResult(BaseModel):
    """
    Standardized result contract for M9.4 Multilingual Vernacular Normalization.
    CRITICAL: Epistemic state is strictly USER_REPORTED. Normalization standardizes
    lexical expressions without establishing physical truth.
    """
    original_text: str = Field(min_length=1, max_length=5000, description="Raw citizen input text")
    normalized_text: str = Field(min_length=1, max_length=5000, description="Standardized canonical civic text")
    detected_language: str = Field(default="en", max_length=32, description="Detected language (en, hi, hinglish, or other)")
    script: str = Field(default="latin", max_length=32, description="Script type (latin, devanagari, mixed)")
    canonical_terms: list[str] = Field(default_factory=list, max_length=50, description="Extracted canonical civic vocabulary terms")
    civic_entities: list[str] = Field(default_factory=list, max_length=50, description="Extracted civic entities (streets, landmarks)")
    issue_candidates: list[IssueCategory] = Field(default_factory=list, max_length=20, description="Positive candidate civic issue categories")
    negated_candidates: list[IssueCategory] = Field(default_factory=list, max_length=20, description="Explicitly negated civic issue categories")
    assertion_type: AssertionType = Field(default=AssertionType.ASSERTED, description="Assertion modality")
    normalization_applied: bool = Field(default=False, description="Whether lexical transformations were made")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Lexical normalization confidence only (NOT probability that defect physically exists)",
    )
    epistemic_state: EpistemicState = Field(
        default=EpistemicState.USER_REPORTED,
        description="Strictly USER_REPORTED epistemic state",
    )
    explanation: Optional[str] = Field(default=None, max_length=1000, description="Explainable transformation summary")
    fallback_used: bool = Field(default=False, description="Whether safe fallback was triggered")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Bounded contextual metadata")

    @field_validator("epistemic_state")
    @classmethod
    def validate_epistemic_boundary(cls, v: EpistemicState) -> EpistemicState:
        if v == EpistemicState.VERIFIED_EVIDENCE:
            raise ValueError(
                "VernacularNormalizationResult cannot claim VERIFIED_EVIDENCE. "
                "Citizen language normalization remains USER_REPORTED."
            )
        return v


# =============================================================================
# 9. Before/After Visual Resolution Audit Contracts (M9.5)
# =============================================================================

class ResolutionAuditOutcome(str, Enum):
    """
    Controlled, epistemically bounded outcomes for M9.5 Visual Resolution Auditing.
    CRITICAL: Never declare REPAIR_CONFIRMED or FULLY_FIXED.
    """
    DEFECT_PERSISTS = "DEFECT_PERSISTS"
    DEFECT_NOT_OBSERVED = "DEFECT_NOT_OBSERVED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceQuality(str, Enum):
    """Image evidence quality assessment."""
    SUFFICIENT = "SUFFICIENT"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


class ConsistencyAssessmentState(str, Enum):
    """Spatial and temporal consistency status."""
    CONSISTENT = "CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    UNKNOWN = "UNKNOWN"


class VisualResolutionAuditRequest(BaseModel):
    """
    Controlled input container for before/after visual resolution comparison.
    Rejects arbitrary client filesystem paths and network URLs.
    """
    case_reference: str = Field(min_length=1, max_length=128, description="Correlated civic complaint case reference")
    before_detection_result: Optional[StandardDetectionResult] = Field(default=None, description="Pre-repair CV result")
    after_detection_result: Optional[StandardDetectionResult] = Field(default=None, description="Post-repair CV result")
    before_image_metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="Bounded metadata for before image")
    after_image_metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="Bounded metadata for after image")
    before_timestamp: Optional[datetime] = Field(default=None, description="Timestamp when before image was captured")
    after_timestamp: Optional[datetime] = Field(default=None, description="Timestamp when after image was captured")
    before_location: Optional[MultimodalLocationContext] = Field(default=None, description="Location of before image")
    after_location: Optional[MultimodalLocationContext] = Field(default=None, description="Location of after image")
    issue_category: Optional[IssueCategory] = Field(default=None, description="Canonical category under audit")
    requested_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Standardized detection evidence threshold",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Bounded non-credential audit metadata")


class VisualResolutionAuditResult(BaseModel):
    """
    Model-independent visual resolution audit report.
    CRITICAL: Epistemic state is strictly MODEL_OBSERVATION or SYSTEM_DERIVED.
    Does NOT assert physical ground truth or perform automatic case closure.
    """
    outcome: ResolutionAuditOutcome = Field(description="Bounded comparison outcome")
    issue_category: IssueCategory = Field(default=IssueCategory.UNKNOWN, description="Audited civic issue category")
    before_observation: Optional[str] = Field(default=None, max_length=500, description="Summary of before observation")
    after_observation: Optional[str] = Field(default=None, max_length=500, description="Summary of after observation")
    evidence_quality: EvidenceQuality = Field(default=EvidenceQuality.UNKNOWN, description="Quality of comparative evidence")
    temporal_consistency: ConsistencyAssessmentState = Field(
        default=ConsistencyAssessmentState.UNKNOWN,
        description="Verification that after_timestamp follows before_timestamp",
    )
    spatial_consistency: ConsistencyAssessmentState = Field(
        default=ConsistencyAssessmentState.UNKNOWN,
        description="Verification that before and after locations are geographically consistent",
    )
    explanation: str = Field(min_length=1, max_length=2000, description="Explainable, neutral summary of comparison")
    limitations: list[str] = Field(default_factory=list, max_length=20, description="Explicit epistemic limitations")
    epistemic_state: EpistemicState = Field(
        default=EpistemicState.SYSTEM_DERIVED,
        description="Epistemic status strictly bounded to SYSTEM_DERIVED or MODEL_OBSERVATION",
    )
    model_metadata: dict[str, Any] = Field(default_factory=dict, description="Audit model and threshold parameters")

    @field_validator("epistemic_state")
    @classmethod
    def validate_audit_epistemic_state(cls, v: EpistemicState) -> EpistemicState:
        if v == EpistemicState.VERIFIED_EVIDENCE:
            raise ValueError(
                "VisualResolutionAuditResult cannot claim VERIFIED_EVIDENCE; "
                "visual comparison provides evidence signals, not ground truth repair confirmation."
            )
        return v


