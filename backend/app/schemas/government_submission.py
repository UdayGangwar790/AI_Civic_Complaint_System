from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

from app.schemas.authority import AuthorityEvidence, AuthorityParty, AuthorityResult, OfficialSourceRecord


ReadinessStatus = Literal["ready", "partially_ready", "not_ready", "blocked"]

GovernmentSubmissionStatus = Literal[
    "NOT_PREPARED",
    "READY_FOR_REVIEW",
    "PREPARED",
    "SUBMISSION_BLOCKED",
    "NOT_SUBMITTED",
]


class SubmissionReadinessResponse(BaseModel):
    reference_id: str
    readiness_status: ReadinessStatus
    submission_status: GovernmentSubmissionStatus
    authority_status: str
    reasons: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    official_sources: list[OfficialSourceRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class GovernmentSubmissionPackage(BaseModel):
    reference_id: str
    issue_category: str
    complaint_title: str
    complaint_description: str
    detected_location: dict[str, Any]
    road: Optional[str] = None
    area: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    authority_verification_state: str
    road_owner: Optional[AuthorityParty] = None
    maintenance_authority: Optional[AuthorityParty] = None
    builder_or_contractor: Optional[AuthorityParty] = None
    official_evidence_records: list[AuthorityEvidence] = Field(default_factory=list)
    priority: Optional[dict[str, Any]] = None
    nlp_analysis_summary: Optional[str] = None
    duplicate_status: Optional[str] = None
    created_at: datetime
    prepared_at: datetime
    submission_status: Literal["NOT_SUBMITTED"] = "NOT_SUBMITTED"


class GovernmentSubmissionRecord(BaseModel):
    readiness_status: ReadinessStatus
    submission_status: GovernmentSubmissionStatus
    prepared_at: datetime
    authority_status: str
    package: GovernmentSubmissionPackage
    official_sources: list[OfficialSourceRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    prepared_by_user_id: Optional[str] = None


class PrepareSubmissionResponse(BaseModel):
    reference_id: str
    submission_status: GovernmentSubmissionStatus
    readiness_status: ReadinessStatus
    prepared_at: datetime
    authority: Optional[AuthorityResult] = None
    package: GovernmentSubmissionPackage
    limitations: list[str] = Field(default_factory=list)
