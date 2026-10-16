from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AuthorityEvidenceAttribute = Literal[
    "road",
    "jurisdiction",
    "road_owner",
    "maintenance_authority",
    "builder_or_contractor",
]
AuthorityVerificationState = Literal["verified", "partially_verified", "not_verified"]
EvidenceFreshness = Literal["fresh", "stale", "unknown"]
SourceStatus = Literal["live", "cached_fresh", "cached_stale", "unavailable", "not_found", "conflict"]


class OfficialSourceRecord(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    organization: str | None = None
    base_url: str | None = None
    allowed_domain: str | None = None
    jurisdiction_scope: str | None = None
    supported_roles: list[str] = Field(default_factory=list)
    supported_road_types: list[str] = Field(default_factory=list)
    refresh_policy_days: int | None = None
    active: bool = True
    last_verified_at: datetime | None = None
    source_url: str | None = None
    source_domain: str | None = None
    retrieved_at: datetime | None = None
    evidence_summary: str | None = None
    supported_fields: list[str] = Field(default_factory=list)


class AuthorityContact(BaseModel):
    phone: str | None = None
    email: str | None = None
    url: str | None = None
    source: str | None = None


class AuthorityParty(BaseModel):
    name: str | None = None
    type: str | None = None
    source: str | None = None
    contact: AuthorityContact | None = None
    official_portal_url: str | None = None


class AuthorityEvidence(BaseModel):
    source_name: str
    source_type: str
    reference: str | None = None
    claim: str
    source_url: str | None = None
    source_id: str | None = None
    source_domain: str | None = None
    retrieved_at: datetime | None = None
    freshness: EvidenceFreshness = "unknown"
    matched_attribute: AuthorityEvidenceAttribute | None = None
    verification_state: AuthorityVerificationState | None = None
    explanation: str | None = None


class AuthorityConflict(BaseModel):
    conflicting_attribute: AuthorityEvidenceAttribute
    source_a: str
    source_b: str
    claim_a: str
    claim_b: str
    retrieved_at_a: datetime | None = None
    retrieved_at_b: datetime | None = None
    explanation: str


class AuthorityResult(BaseModel):
    authority_status: str = Field(pattern="^(verified|partially_verified|not_verified)$")
    road_owner: AuthorityParty | None = None
    maintenance_authority: AuthorityParty | None = None
    builder_or_contractor: AuthorityParty | None = None
    evidence: list[AuthorityEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    sources: list[OfficialSourceRecord] = Field(default_factory=list)
    resolved_at: datetime | None = None
    resolution_message: str | None = None
    citizen_explanation: str | None = None
    source_status: SourceStatus | None = None
    freshness: EvidenceFreshness = "unknown"
    conflicts: list[AuthorityConflict] = Field(default_factory=list)


class AuthorityLocation(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    road: str | None = None
    area: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    country: str | None = None


class AuthorityResolutionResponse(BaseModel):
    location: AuthorityLocation
    authority: AuthorityResult
