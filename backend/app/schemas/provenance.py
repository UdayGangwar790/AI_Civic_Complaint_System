from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Optional

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    DETECTION = "detection"
    LOCATION = "location"
    ROAD_IDENTITY = "road_identity"
    JURISDICTION = "jurisdiction"
    ROAD_OWNER = "road_owner"
    MAINTENANCE_AUTHORITY = "maintenance_authority"
    BUILDER_OR_CONTRACTOR = "builder_or_contractor"
    WEATHER_CONTEXT = "weather_context"
    RAINFALL_CONTEXT = "rainfall_context"
    TRAFFIC_CONTEXT = "traffic_context"
    RECURRENCE = "recurrence"
    HOTSPOT_CONTEXT = "hotspot_context"
    PRIORITY = "priority"
    COMPLAINT_SUBMISSION_READINESS = "complaint_submission_readiness"
    RESOLUTION_EVIDENCE = "resolution_evidence"
    GOVERNMENT_SUBMISSION = "government_submission"
    GOVERNMENT_STATUS = "government_status"
    ESCALATION_DECISION = "escalation_decision"
    RESOLUTION_VERIFICATION = "resolution_verification"
    VERNACULAR_NORMALIZATION = "vernacular_normalization"
    VISUAL_RESOLUTION_AUDIT = "visual_resolution_audit"
    OPERATIONAL_DECISION_RECOMMENDATION = "operational_decision_recommendation"
    FIELD_INSPECTION_AUDIT = "field_inspection_audit"



class SourceType(str, Enum):
    CV_MODEL = "cv_model"
    GPS = "gps"
    GEOCODER = "geocoder"
    ROAD_REGISTRY = "road_registry"
    GOVERNMENT_REGISTRY = "government_registry"
    TENDER_REGISTRY = "tender_registry"
    CONCESSION_REGISTRY = "concession_registry"
    WEATHER_PROVIDER = "weather_provider"
    TRAFFIC_PROVIDER = "traffic_provider"
    OPEN_DATA = "open_data"
    CVKI_CASE_HISTORY = "cvki_case_history"
    CITIZEN_REPORT = "citizen_report"
    AUTHORITY_UPDATE = "authority_update"
    ADMIN_UPDATE = "admin_update"
    SYSTEM_DERIVED = "system_derived"
    GOVERNMENT_ADAPTER = "government_adapter"


class VerificationState(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    NOT_VERIFIED = "not_verified"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    SYSTEM_DERIVED = "system_derived"


def calculate_evidence_hash(
    claim_type: str,
    matched_attribute: Optional[str] = None,
    source: str = "",
    source_type: str = "",
    value: Any = None,
    explanation: Optional[str] = None,
) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for normalized evidence.
    Allows deduplication, auditability, and tamper detection without storing raw payloads.
    """
    content = value if value is not None else explanation
    normalized_val = json.dumps(content, sort_keys=True, default=str) if isinstance(content, (dict, list)) else str(content or "")
    raw = f"{claim_type}:{matched_attribute or ''}:{source}:{source_type}:{normalized_val}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EvidenceRecord(BaseModel):
    evidence_id: str
    case_reference: Optional[str] = None
    claim_type: ClaimType
    matched_attribute: Optional[str] = None
    source: str
    source_type: SourceType
    source_url: Optional[str] = None
    provider: Optional[str] = None
    observed_at: Optional[datetime] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    freshness: str = "fresh"  # fresh, stale, unknown, live
    status: str = "active"  # active, stale, invalidated, superseded
    verification_state: VerificationState
    explanation: str
    evidence_hash: str
    version: int = 1
    invalidation_reason: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseProvenanceResponse(BaseModel):
    reference_id: str
    case_reference: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary_verification_state: VerificationState = VerificationState.PARTIALLY_VERIFIED
    claims: list[EvidenceRecord] = Field(default_factory=list)
    claim_groups: dict[str, list[EvidenceRecord]] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    def __init__(self, **data: Any):
        if "reference_id" in data and not data.get("case_reference"):
            data["case_reference"] = data["reference_id"]
        elif "case_reference" in data and not data.get("reference_id"):
            data["reference_id"] = data["case_reference"]
        super().__init__(**data)
