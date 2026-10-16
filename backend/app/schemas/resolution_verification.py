"""
CVKI M7.6 Citizen Resolution Verification Schemas.
Enforces strict epistemic separation between external government status observations
("RESOLVED") and verified citizen-ground resolution ground truth.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class CitizenResolutionResponse(str, Enum):
    """Controlled response types submitted by a citizen verifying resolution."""
    CONFIRMED_RESOLVED = "CONFIRMED_RESOLVED"
    STILL_UNRESOLVED = "STILL_UNRESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    CANNOT_VERIFY = "CANNOT_VERIFY"


class ResolutionVerificationStatus(str, Enum):
    """Controlled lifecycle states of citizen resolution verification."""
    PENDING = "PENDING"
    VERIFIED_RESOLVED = "VERIFIED_RESOLVED"
    CITIZEN_DISPUTED = "CITIZEN_DISPUTED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CLOSED_UNVERIFIED = "CLOSED_UNVERIFIED"


class ResolutionVerificationTransitionRecord(BaseModel):
    """Audit entry documenting a state transition during resolution review."""
    transition_id: str = Field(..., description="Unique transition token")
    from_status: ResolutionVerificationStatus
    to_status: ResolutionVerificationStatus
    actor_user_id: str
    actor_role: str
    transition_reason: str
    transitioned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CitizenResolutionVerificationSubmitRequest(BaseModel):
    """API payload when a citizen submits resolution feedback for a case."""
    integration_id: Optional[str] = Field(None, description="Optional target integration slug")
    citizen_response: CitizenResolutionResponse = Field(..., description="Resolution confirmation response")
    citizen_notes: Optional[str] = Field(None, max_length=1000, description="Optional observations on physical ground repair")
    evidence_photo_url: Optional[str] = Field(None, description="Optional image/photo URL verifying ground condition")
    evidence_photo_metadata: Optional[dict[str, Any]] = Field(None, description="Photo EXIF or capture timestamp/metadata")
    latitude: Optional[float] = Field(None, description="Citizen location latitude at verification time")
    longitude: Optional[float] = Field(None, description="Citizen location longitude at verification time")
    requires_review: bool = Field(default=False, description="Citizen requests explicit case manager review")


class ResolutionVerificationReviewRequest(BaseModel):
    """API payload for case managers or admins reviewing a disputed verification."""
    verification_status: ResolutionVerificationStatus = Field(..., description="Target verified outcome")
    reviewer_notes: str = Field(..., min_length=3, max_length=2000, description="Justification for verification determination")
    override_physical_resolution: Optional[bool] = Field(
        None, description="Explicit operator flag affirming or disaffirming physical ground repair"
    )


class CitizenResolutionVerificationRecord(BaseModel):
    """Persistent database model for citizen resolution verification."""
    verification_id: str = Field(..., description="Unique identifier (verif_<hex>)")
    cvki_reference_id: str = Field(..., description="Associated CVKI case reference ID")
    integration_id: str = Field(..., description="Target government integration slug")
    government_reference_id: Optional[str] = Field(None, description="Confirmed external tracking ID")
    government_status_sync_id: Optional[str] = Field(None, description="Associated status sync observation ID")
    observed_government_status: Optional[str] = Field(None, description="External status token at verification time")
    citizen_user_id: str = Field(..., description="Citizen submitting verification")
    citizen_response: CitizenResolutionResponse
    verification_status: ResolutionVerificationStatus = Field(default=ResolutionVerificationStatus.PENDING)
    citizen_notes: Optional[str] = None
    evidence_photo_url: Optional[str] = None
    evidence_photo_metadata: Optional[dict[str, Any]] = None
    location: Optional[dict[str, Any]] = None
    is_physical_resolution_verified: bool = Field(
        default=False,
        description="Strict epistemic invariant: True only when verified ground truth exists.",
    )
    reviewer_user_id: Optional[str] = None
    reviewer_role: Optional[str] = None
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    provenance_evidence_id: Optional[str] = Field(None, description="M6.4 Evidence Record ID")
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    history: list[ResolutionVerificationTransitionRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CitizenResolutionVerificationResponse(BaseModel):
    """API response model for case resolution verification status."""
    verification_id: str
    cvki_reference_id: str
    integration_id: str
    government_reference_id: Optional[str] = None
    observed_government_status: Optional[str] = None
    citizen_user_id: str
    citizen_response: CitizenResolutionResponse
    verification_status: ResolutionVerificationStatus
    is_physical_resolution_verified: bool
    citizen_notes: Optional[str] = None
    evidence_photo_url: Optional[str] = None
    reviewer_user_id: Optional[str] = None
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    provenance_evidence_id: Optional[str] = None
    submitted_at: datetime
    updated_at: datetime


class CitizenResolutionVerificationHistoryResponse(BaseModel):
    """API response model for case resolution verification history."""
    cvki_reference_id: str
    verifications: list[CitizenResolutionVerificationRecord]
    total: int
