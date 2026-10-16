"""
CVKI M7.3 Government Reference-ID Mapping Schemas.
Maintains strict separation between internal CVKI case references and external government portal tracking IDs.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ReferenceMappingState(str, Enum):
    """
    Explicit lifecycle states for government reference ID mapping.
    Ensures epistemic honesty: REFERENCE_RECEIVED is not automatically REFERENCE_CONFIRMED.
    """
    UNMAPPED = "UNMAPPED"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    REFERENCE_RECEIVED = "REFERENCE_RECEIVED"
    REFERENCE_CONFIRMED = "REFERENCE_CONFIRMED"
    REFERENCE_STALE = "REFERENCE_STALE"
    REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"
    REFERENCE_CONFLICT = "REFERENCE_CONFLICT"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    UNVERIFIED_MANUAL_REFERENCE = "UNVERIFIED_MANUAL_REFERENCE"


class GovernmentReferenceMapping(BaseModel):
    """
    Canonical data model representing an identity mapping between a CVKI case/submission
    and an external government authority portal tracking ID.
    """
    mapping_id: str = Field(..., description="Unique mapping identifier (e.g. grm_...)")
    cvki_reference_id: str = Field(..., description="Permanent, immutable CVKI Case Reference ID")
    submission_id: str = Field(..., description="Associated CVKI submission attempt ID")
    integration_id: str = Field(..., description="Target government integration slug (e.g. gov_cpgrams)")
    government_reference_id: Optional[str] = Field(None, description="External government tracking or docket ID")
    government_reference_type: Optional[str] = Field(None, description="Type of reference (e.g. registration_number, docket_id, manual_entry)")
    government_reference_status: Optional[str] = Field(None, description="Raw or normalized external status corresponding to this reference")
    mapping_state: ReferenceMappingState = Field(default=ReferenceMappingState.UNMAPPED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    first_observed_at: Optional[datetime] = Field(None, description="Timestamp when government reference was first seen")
    last_confirmed_at: Optional[datetime] = Field(None, description="Timestamp of latest authoritative confirmation")
    source: str = Field(default="system", description="Source of reference observation (e.g. adapter:gov_cpgrams, manual_operator)")
    provenance_evidence_id: Optional[str] = Field(None, description="M6.4 Evidence Record ID justifying this mapping")
    verification_state: str = Field(default="unverified", description="Verification state: unverified, verified, conflicted, stale")
    explanation: Optional[str] = Field(None, description="Human-readable explanation of mapping basis or conflict reason")
    external_case_url: Optional[str] = Field(None, description="Verified portal citizen tracking URL if available")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Sanitized metadata and response fingerprints")
    version: int = Field(default=1, description="Mapping record mutation version")


class ManualReferenceCreateRequest(BaseModel):
    """
    Schema for authorized authority/admin manual entry of an official reference ID
    (e.g. from an offline government receipt or paper acknowledgement).
    Strictly recorded as UNVERIFIED_MANUAL_REFERENCE.
    """
    government_reference_id: str = Field(..., min_length=3, max_length=128, description="Government docket or tracking number")
    government_reference_type: str = Field(default="manual_docket", description="Reference type (e.g. manual_docket, letter_reference)")
    reason: str = Field(..., min_length=5, description="Administrative justification for manual entry")
    notes: Optional[str] = Field(None, description="Additional contextual notes")


class GovernmentReferenceMappingResponse(BaseModel):
    """
    Safe API response representing government reference mapping for clients.
    Excludes sensitive credentials or raw internal keys.
    """
    mapping_id: str
    cvki_reference_id: str
    submission_id: str
    integration_id: str
    integration_display_name: str
    government_reference_id: Optional[str] = None
    government_reference_type: Optional[str] = None
    government_reference_status: Optional[str] = None
    mapping_state: ReferenceMappingState
    verification_state: str
    first_observed_at: Optional[datetime] = None
    last_confirmed_at: Optional[datetime] = None
    source: str
    explanation: Optional[str] = None
    external_case_url: Optional[str] = None
    provenance_evidence_id: Optional[str] = None
    is_authoritative: bool = False
    conflict_detected: bool = False
    conflict_details: Optional[str] = None
    version: int


class GovernmentReferenceListResponse(BaseModel):
    """List of all government reference mappings for a CVKI case."""
    cvki_reference_id: str
    mappings: list[GovernmentReferenceMappingResponse]
    total: int
