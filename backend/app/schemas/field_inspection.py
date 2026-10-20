"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.5: Field Inspection Protocol & Audit Schemas
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

from app.services.multimodal.contracts import EpistemicState, IssueCategory


class ExpectedObservationType(str, Enum):
    """Categorization of expected sensory/physical observations in the field."""
    PHOTO_EVALUATION = "PHOTO_EVALUATION"
    DIMENSION_ESTIMATE = "DIMENSION_ESTIMATE"
    STRUCTURAL_CONDITION = "STRUCTURAL_CONDITION"
    SAFETY_HAZARD_PRESENCE = "SAFETY_HAZARD_PRESENCE"
    VISIBILITY_OBSTRUCTION = "VISIBILITY_OBSTRUCTION"
    DRAINAGE_FLOW_CONDITION = "DRAINAGE_FLOW_CONDITION"
    GENERAL_VERIFICATION = "GENERAL_VERIFICATION"


class GeofenceResult(str, Enum):
    """Geospatial validation state comparing inspection GPS against reported incident GPS."""
    WITHIN_EXPECTED_AREA = "WITHIN_EXPECTED_AREA"
    OUTSIDE_EXPECTED_AREA = "OUTSIDE_EXPECTED_AREA"
    LOCATION_UNAVAILABLE = "LOCATION_UNAVAILABLE"
    LOCATION_UNCERTAIN = "LOCATION_UNCERTAIN"


class InspectionCompleteness(str, Enum):
    """Completeness evaluation of submitted inspection evidence against protocol requirements."""
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


class AuditOutcome(str, Enum):
    """Audit determination of whether submitted inspection evidence corroborates prior decision context."""
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class InspectionStep(BaseModel):
    """Atomic step in a deterministic civic inspection protocol."""
    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(description="Unique step code (e.g. STEP-MANHOLE-01)")
    instruction: str = Field(description="Clear operational instruction for the inspector")
    purpose: str = Field(description="Why this observation or evidence is necessary")
    evidence_to_collect: str = Field(description="Evidence artifact descriptor (e.g. overview_photo, curb_measurement)")
    expected_observation_type: ExpectedObservationType
    mandatory: bool = Field(default=True)
    order: int = Field(ge=1, description="Logical execution sequence")
    safety_guidance: Optional[str] = Field(default=None, description="Precautionary safety rule overriding data capture")


class LocationRequirements(BaseModel):
    """Location tolerance constraints for valid on-site inspection."""
    model_config = ConfigDict(extra="ignore")

    target_latitude: Optional[float] = None
    target_longitude: Optional[float] = None
    max_acceptable_distance_meters: float = Field(default=150.0, ge=1.0)
    allow_outside_with_justification: bool = Field(default=True)


class TemporalRequirements(BaseModel):
    """Temporal window constraints for inspection validity."""
    model_config = ConfigDict(extra="ignore")

    max_inspection_age_hours: int = Field(default=72, ge=1)
    prohibit_future_timestamps: bool = Field(default=True)


class FieldInspectionProtocol(BaseModel):
    """
    Structured, versioned operational protocol guiding human on-site inspection.
    Explicitly labeled as a CVKI recommendation, NOT an official municipal regulation.
    """
    model_config = ConfigDict(extra="ignore")

    protocol_id: str = Field(description="Unique protocol ID (e.g. PROTOCOL-MANHOLE-V1)")
    protocol_version: str = Field(default="1.0.0")
    case_reference: str = Field(description="Complaint case this protocol was generated for")
    issue_category: IssueCategory
    objective: str = Field(description="Core physical question this protocol aims to verify")
    inspection_steps: list[InspectionStep] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    optional_evidence: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    location_requirements: LocationRequirements = Field(default_factory=LocationRequirements)
    temporal_requirements: TemporalRequirements = Field(default_factory=TemporalRequirements)
    acceptance_conditions: list[str] = Field(default_factory=list)
    prohibited_inferences: list[str] = Field(default_factory=list)
    source_playbook_id: Optional[str] = None
    source_playbook_version: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


import html
import re
from datetime import timedelta
from pydantic import field_validator
from app.services.external_civic_provider import is_ssrf_safe_external_url


class InspectionObservationItem(BaseModel):
    """Specific observation recorded by the inspector for a protocol step."""
    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$", description="Matching step_id from protocol")
    observation_text: str = Field(min_length=1, max_length=2000, description="Written finding from field")
    defect_confirmed: Optional[bool] = Field(
        default=None,
        description="Whether inspector observed defect in physical state",
    )
    dimensions: Optional[dict[str, Any]] = None
    severity_observed: Optional[str] = Field(default=None, max_length=32)
    safety_measures_taken: Optional[str] = Field(default=None, max_length=1000)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("observation_text", "notes", "safety_measures_taken")
    @classmethod
    def sanitize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "\0" in v:
            raise ValueError("Null bytes are prohibited in text observations.")
        if re.search(r"<\s*script[^>]*>", v, re.IGNORECASE) or re.search(r"javascript:", v, re.IGNORECASE):
            raise ValueError("Executable script payloads or HTML script tags are prohibited.")
        return v


class FieldInspectionSubmissionRequest(BaseModel):
    """Input payload submitted by authorized field personnel or authority."""
    model_config = ConfigDict(extra="ignore")

    protocol_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    protocol_version: str = Field(default="1.0.0", min_length=1, max_length=16)
    observations: list[InspectionObservationItem] = Field(min_length=1, max_length=50)
    evidence_items: list[str] = Field(default_factory=list, max_length=20, description="IDs or references to captured photos/docs")
    location: Optional[dict[str, float]] = Field(default=None, description="GPS coords at time of inspection")
    inspection_timestamp: datetime = Field(description="Timestamp when on-site inspection occurred")
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("location")
    @classmethod
    def validate_location_coords(cls, v: Optional[dict[str, float]]) -> Optional[dict[str, float]]:
        if v is None:
            return v
        lat = v.get("latitude")
        lon = v.get("longitude")
        if lat is not None:
            if not isinstance(lat, (int, float)) or lat < -90.0 or lat > 90.0:
                raise ValueError("Latitude must be a valid float between -90.0 and 90.0 degrees.")
        if lon is not None:
            if not isinstance(lon, (int, float)) or lon < -180.0 or lon > 180.0:
                raise ValueError("Longitude must be a valid float between -180.0 and 180.0 degrees.")
        return v

    @field_validator("evidence_items")
    @classmethod
    def validate_evidence_uris(cls, items: list[str]) -> list[str]:
        for item in items:
            raw = item.strip()
            if ".." in raw or "\\.." in raw or "\0" in raw:
                raise ValueError(f"Path traversal sequence detected in evidence reference: '{item}'.")
            if raw.startswith("/") or re.match(r"^[a-zA-Z]:[\\/]", raw):
                raise ValueError(f"Direct filesystem path disallowed: '{item}'.")
            lower = raw.lower()
            if any(lower.startswith(sch) for sch in ("file://", "ftp://", "gopher://", "dict://", "ldap://")):
                raise ValueError(f"Disallowed URI scheme in evidence reference: '{item}'.")
            if lower.startswith("http://") or lower.startswith("https://"):
                safe, reason = is_ssrf_safe_external_url(raw)
                if not safe:
                    raise ValueError(f"SSRF safety check failed for evidence URI: {reason}")
        return items

    @field_validator("notes")
    @classmethod
    def sanitize_submission_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "\0" in v:
            raise ValueError("Null bytes are prohibited in inspection notes.")
        if re.search(r"<\s*script[^>]*>", v, re.IGNORECASE) or re.search(r"javascript:", v, re.IGNORECASE):
            raise ValueError("Executable script payloads or HTML script tags are prohibited.")
        return v


class FieldInspectionAuditResult(BaseModel):
    """
    Automated audit evaluation of submitted field inspection against protocol requirements.
    Epistemic state is strictly SYSTEM_DERIVED.
    Does NOT assert physical truth or automatically mark case resolved.
    """
    model_config = ConfigDict(extra="ignore")

    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    outcome: AuditOutcome
    completeness: InspectionCompleteness
    geofence_result: GeofenceResult
    distance_from_case_meters: Optional[float] = None
    supported_points: list[str] = Field(default_factory=list)
    conflicts_detected: list[str] = Field(default_factory=list)
    missing_mandatory_steps: list[str] = Field(default_factory=list)
    audit_explanation: str
    epistemic_state: EpistemicState = Field(default=EpistemicState.SYSTEM_DERIVED)
    audited_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FieldInspectionRecord(BaseModel):
    """
    Persisted canonical record of an executed field inspection and its automated audit.
    Inspector identity is strictly derived from authenticated context.
    """
    model_config = ConfigDict(extra="ignore")

    inspection_id: str = Field(default_factory=lambda: f"INSP-{uuid4().hex[:12].upper()}")
    case_reference: str
    protocol_id: str
    protocol_version: str
    inspector_id: str = Field(description="Authenticated user_id of the inspector")
    observations: list[InspectionObservationItem]
    evidence_items: list[str] = Field(default_factory=list)
    location: Optional[dict[str, float]] = None
    inspection_timestamp: datetime
    geofence_result: GeofenceResult
    completeness: InspectionCompleteness
    conflicts: list[str] = Field(default_factory=list)
    audit_result: FieldInspectionAuditResult
    epistemic_state: EpistemicState = Field(default=EpistemicState.USER_REPORTED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
