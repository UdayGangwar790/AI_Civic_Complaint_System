from typing import Any, Literal
from pydantic import BaseModel, Field

from app.schemas.authority import AuthorityResult

Language = Literal["en", "hi", "hinglish"]


class GuidanceLocation(BaseModel):
    road: str | None = None
    area: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class GovernmentGuidanceRequest(BaseModel):
    issue_category: str
    location: Any = None
    authority: AuthorityResult | None = None
    language: Language = "en"
    complaint_title: str | None = None
    complaint_description: str | None = None


class GovernmentGuidanceResponse(BaseModel):
    recommended_channel: str
    authority_basis: str
    official_portal_url: str | None = None
    official_source: str | None = None
    steps: list[str] = Field(default_factory=list)
    what_to_attach: list[str] = Field(default_factory=list)
    what_to_write: list[str] = Field(default_factory=list)
    external_submission_status: Literal["not_submitted"] = "not_submitted"
    limitations: list[str] = Field(default_factory=list)
    language: Language = "en"
