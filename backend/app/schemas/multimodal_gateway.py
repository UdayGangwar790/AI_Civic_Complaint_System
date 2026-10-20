"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.2: Multimodal REST API Gateway Schemas
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.multimodal.contracts import (
    AmbiguityAssessment,
    ClarificationResult,
    EpistemicState,
    EvidenceAlignmentAssessment,
    IssueCategory,
    MultimodalLocationContext,
    StandardMultimodalResult,
    VernacularNormalizationResult,
    VisualResolutionAuditResult,
)
from app.services.cv.base_provider import StandardDetectionResult


class MultimodalGatewayRequest(BaseModel):
    """
    Standard request schema for multimodal analysis gateway.
    Accepts raw citizen or authority inputs, optional CV detection results,
    and optional before/after evidence references.
    """
    model_config = ConfigDict(extra="ignore")

    case_reference: Optional[str] = Field(
        default=None,
        description="Optional internal CVKI complaint case reference ID",
        max_length=64,
    )
    text: Optional[str] = Field(
        default=None,
        description="Citizen or authority textual description",
        max_length=2000,
    )
    language_hint: Optional[str] = Field(
        default=None,
        description="Optional language code (e.g. 'hi', 'en', 'ta', 'te', 'bn')",
        max_length=10,
    )
    issue_category: Optional[IssueCategory] = Field(
        default=None,
        description="Optional pre-classified or suspected civic issue category",
    )
    detection_result: Optional[StandardDetectionResult] = Field(
        default=None,
        description="Standardized computer vision detection result from M8 CV runtime",
    )
    location_context: Optional[MultimodalLocationContext] = Field(
        default=None,
        description="Geographic and jurisdictional location context",
    )
    # Fields for before/after visual resolution auditing
    before_image_path: Optional[str] = Field(
        default=None,
        description="Path or URI to baseline defect evidence image",
        max_length=512,
    )
    after_image_path: Optional[str] = Field(
        default=None,
        description="Path or URI to claimed resolution evidence image",
        max_length=512,
    )
    before_detection: Optional[StandardDetectionResult] = Field(
        default=None,
        description="Detection result on baseline defect image",
    )
    after_detection: Optional[StandardDetectionResult] = Field(
        default=None,
        description="Detection result on resolution evidence image",
    )
    before_timestamp: Optional[datetime] = Field(
        default=None,
        description="Timestamp of baseline defect observation",
    )
    after_timestamp: Optional[datetime] = Field(
        default=None,
        description="Timestamp of resolution observation",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Auxiliary operational metadata",
    )

    @field_validator("case_reference")
    @classmethod
    def validate_case_ref(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("Malformed case reference identifier.")
        return v

    @field_validator("text")
    @classmethod
    def sanitize_gateway_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "\0" in v:
            raise ValueError("Null bytes are prohibited.")
        import re
        if re.search(r"<\s*script[^>]*>", v, re.IGNORECASE) or re.search(r"javascript:", v, re.IGNORECASE):
            raise ValueError("Executable script payloads or HTML script tags are prohibited.")
        return v

    @field_validator("before_image_path", "after_image_path")
    @classmethod
    def validate_image_uris(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        raw = v.strip()
        if ".." in raw or "\\.." in raw or "\0" in raw:
            raise ValueError(f"Path traversal sequence detected in image reference: '{v}'.")
        import re
        if raw.startswith("/") or re.match(r"^[a-zA-Z]:[\\/]", raw):
            raise ValueError(f"Direct absolute filesystem path disallowed: '{v}'.")
        lower = raw.lower()
        if any(lower.startswith(sch) for sch in ("file://", "ftp://", "gopher://", "dict://", "ldap://")):
            raise ValueError(f"Disallowed URI scheme: '{v}'.")
        if lower.startswith("http://") or lower.startswith("https://"):
            from app.services.external_civic_provider import is_ssrf_safe_external_url
            safe, reason = is_ssrf_safe_external_url(raw)
            if not safe:
                raise ValueError(f"SSRF safety check failed: {reason}")
        return v

    @field_validator("before_timestamp", "after_timestamp")
    @classmethod
    def validate_gateway_timestamps(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return v
        from datetime import timedelta, timezone
        now_utc = datetime.now(timezone.utc)
        v_cmp = v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
        if v_cmp > now_utc + timedelta(minutes=5):
            raise ValueError("Timestamp cannot be in the future.")
        return v


class MultimodalGatewayResponse(BaseModel):
    """
    Standard response schema returned by the M10 multimodal REST gateway.
    Encapsulates normalized vernacular input, cross-modal consistency,
    ambiguity assessments, active clarification requests, visual resolution audit,
    and provenance/KG references.
    """
    model_config = ConfigDict(extra="ignore")

    gateway_execution_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this gateway pipeline execution",
    )
    case_reference: Optional[str] = Field(
        default=None,
        description="Associated CVKI case reference ID",
    )
    normalized_text: Optional[str] = Field(
        default=None,
        description="Vernacular-normalized English complaint text",
    )
    vernacular_result: Optional[VernacularNormalizationResult] = Field(
        default=None,
        description="Full vernacular normalization details and detected entities",
    )
    detection_result: Optional[StandardDetectionResult] = Field(
        default=None,
        description="Computer vision detection result",
    )
    alignment_assessment: Optional[EvidenceAlignmentAssessment] = Field(
        default=None,
        description="Cross-modal consistency and alignment evaluation",
    )
    ambiguity_assessment: Optional[AmbiguityAssessment] = Field(
        default=None,
        description="Ambiguity score and identified ambiguity reasons",
    )
    clarification_result: Optional[ClarificationResult] = Field(
        default=None,
        description="Active clarification questions if ambiguity was detected",
    )
    visual_audit_result: Optional[VisualResolutionAuditResult] = Field(
        default=None,
        description="Before/after visual resolution audit result if media was provided",
    )
    provenance_claims: list[str] = Field(
        default_factory=list,
        description="Recorded provenance claim IDs for audit trail",
    )
    kg_node_keys: list[str] = Field(
        default_factory=list,
        description="Created or updated Knowledge Graph canonical node keys",
    )
    epistemic_state: EpistemicState = Field(
        default=EpistemicState.SYSTEM_DERIVED,
        description="Epistemic status of the gateway analysis (always SYSTEM_DERIVED)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Operational or evidence warnings identified during processing",
    )
    processing_time_ms: float = Field(
        default=0.0,
        description="Execution duration in milliseconds",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of gateway execution",
    )
