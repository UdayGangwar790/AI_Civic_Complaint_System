from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


Language = Literal["en", "hi", "hinglish"]
CivicIssueCategory = Literal[
    "open_damaged_manhole",
    "damaged_missing_road_sign",
    "road_waterlogging",
    "other_civic_issue",
]


class ExtractedEntity(BaseModel):
    name: str
    type: str  # "road", "locality", "landmark", "ward", "city", "district", "state"
    source: Literal["text"] = "text"


class NLPAnalysisRequest(BaseModel):
    title: str = Field(default="")
    description: str = Field(default="")
    language: Optional[Language] = None
    issue_class: Optional[str] = None
    location_context: Optional[dict[str, Any]] = None
    authority_context: Optional[dict[str, Any]] = None


class NLPAnalysisResponse(BaseModel):
    detected_language: str
    issue_category: str
    issue_confidence: float = Field(ge=0.0, le=1.0)
    issue_keywords: list[str] = Field(default_factory=list)
    severity_signals: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    extracted_entities: list[ExtractedEntity] = Field(default_factory=list)
    normalized_summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    approach: str = "rule_based_multilingual_lexicon_baseline"
