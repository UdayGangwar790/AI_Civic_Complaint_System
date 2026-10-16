from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.authority import AuthorityResult
from app.schemas.complaint import ComplaintLocation, Language


CaseStatus = Literal["draft", "submitted_to_cvki", "under_review", "assigned", "in_progress", "resolved", "closed"]


class CaseIssue(BaseModel):
    class_name: str
    label: str
    severity: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0.0, le=1.0)


class CaseComplaint(BaseModel):
    language: Language
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


from app.schemas.guidance import GovernmentGuidanceResponse
from app.schemas.nlp import NLPAnalysisResponse
from app.schemas.duplicate import DuplicateCheckResponse
from app.schemas.priority import PriorityScoreResponse
from app.schemas.government_submission import GovernmentSubmissionRecord
from app.schemas.civic_intelligence import RecurrenceAnalysis, ResolutionEvidenceRecord


class FollowUp(BaseModel):
    guidance: str
    external_submission_status: Literal["not_submitted"] = "not_submitted"
    official_guidance: Optional[GovernmentGuidanceResponse] = None


AssignmentStatus = Literal["unassigned", "assigned"]


class CaseAssignment(BaseModel):
    assigned_to_user_id: Optional[str] = None
    assigned_to_role: Optional[str] = "authority"
    assigned_by_user_id: Optional[str] = None
    assigned_at: Optional[datetime] = None
    assignment_status: AssignmentStatus = "unassigned"
    assigned_to_email: Optional[str] = None


class ComplaintCaseCreateRequest(BaseModel):
    issue: CaseIssue
    location: ComplaintLocation | None = None
    authority: AuthorityResult | None = None
    complaint: CaseComplaint
    evidence: list[str] = Field(default_factory=list)
    nlp_analysis: Optional[NLPAnalysisResponse] = None
    duplicate_analysis: Optional[DuplicateCheckResponse] = None
    priority_analysis: Optional[PriorityScoreResponse] = None


class ComplaintCase(BaseModel):
    reference_id: str
    user_id: str | None = None
    status: CaseStatus
    created_at: datetime
    updated_at: datetime | None = None
    issue: CaseIssue
    location: ComplaintLocation
    authority: AuthorityResult
    complaint: CaseComplaint
    evidence: list[str] = Field(default_factory=list)
    follow_up: FollowUp
    nlp_analysis: Optional[NLPAnalysisResponse] = None
    duplicate_analysis: Optional[DuplicateCheckResponse] = None
    priority_analysis: Optional[PriorityScoreResponse] = None
    recurrence_analysis: Optional[RecurrenceAnalysis] = None
    resolution_evidence: list[ResolutionEvidenceRecord] = Field(default_factory=list)
    resolution_evidence_recorded_at: Optional[datetime] = None
    government_submission: Optional[GovernmentSubmissionRecord] = None
    assignment: Optional[CaseAssignment] = None
    geo_location: Optional[dict[str, Any]] = None


class ComplaintCaseStatus(BaseModel):
    reference_id: str
    status: CaseStatus
    status_description: str
    external_submission_status: Literal["not_submitted"] = "not_submitted"


class ComplaintCaseSummary(BaseModel):
    reference_id: str
    created_at: datetime
    updated_at: datetime
    status: CaseStatus
    external_submission_status: Literal["not_submitted"] = "not_submitted"
    issue_class: str
    issue_label: str
    severity: str
    confidence: float
    location_summary: str | None = None
    title: str
    priority_level: Optional[str] = None
    duplicate_status: Optional[str] = None
    assignment: Optional[CaseAssignment] = None


class ComplaintHistoryResponse(BaseModel):
    items: list[ComplaintCaseSummary]
    total: int
    page: int
    limit: int
    pages: int
