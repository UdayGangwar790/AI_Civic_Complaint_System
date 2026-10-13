from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.authority import AuthorityParty, AuthorityResult
from app.schemas.guidance import GovernmentGuidanceResponse


Language = Literal["en", "hi", "hinglish"]


class ComplaintDetection(BaseModel):
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)


class ComplaintLocation(BaseModel):
    road: str | None = None
    area: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)


class ComplaintDraftRequest(BaseModel):
    detection: ComplaintDetection
    location: ComplaintLocation | None = None
    authority: AuthorityResult | None = None
    language: Language = "en"
    image_attached: bool = False


class ComplaintDraftResponse(BaseModel):
    issue_category: str
    issue_label: str
    title: str
    description: str
    language: Language
    severity: Literal["low", "medium", "high"]
    severity_reason: str
    location: ComplaintLocation
    authority_status: str
    suggested_authority: AuthorityParty | None = None
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    draft_text: str
    guidance: Optional[GovernmentGuidanceResponse] = None
