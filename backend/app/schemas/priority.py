from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.schemas.authority import AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.duplicate import DuplicateCheckResponse
from app.schemas.nlp import NLPAnalysisResponse


PriorityLevel = Literal["P1", "P2", "P3", "P4"]
RiskLevel = Literal["Critical", "High", "Medium", "Low"]


class PriorityScoreRequest(BaseModel):
    issue_category: str
    cv_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    nlp_analysis: Optional[NLPAnalysisResponse] = None
    duplicate_analysis: Optional[DuplicateCheckResponse] = None
    location_context: Optional[ComplaintLocation] = None
    authority_context: Optional[AuthorityResult] = None


class PriorityScoreResponse(BaseModel):
    priority_score: int = Field(ge=0, le=100)
    priority_level: PriorityLevel
    risk_level: RiskLevel
    recurrence_score: int = Field(default=0, ge=0)
    reasons: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
