from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ResolutionEvidenceState = Literal["status_only", "evidence_supported", "evidence_missing"]


class RecurrenceAnalysis(BaseModel):
    recurrence_detected: bool = False
    recurrence_count: int = Field(default=0, ge=0)
    related_historical_case_ids: list[str] = Field(default_factory=list)
    recurrence_window_days: int = Field(default=180, ge=1)
    history_scan_complete: bool = True
    recurrence_explanation: str


class ResolutionEvidenceRecord(BaseModel):
    note: str = Field(min_length=1, max_length=500)
    recorded_at: datetime
    recorded_by_role: Literal["admin", "authority"]


class CivicRecommendation(BaseModel):
    kind: Literal["recurrence", "hotspot", "unresolved_duration", "resolution_evidence_missing"]
    message: str
    basis: str


class CaseIntelligenceResponse(BaseModel):
    reference_id: str
    recurrence: RecurrenceAnalysis
    recent_location_case_count: int = Field(default=0, ge=0)
    recent_location_unresolved_count: int = Field(default=0, ge=0)
    hotspot_detected: bool = False
    dominant_issue_category: str | None = None
    hotspot_window_days: int = Field(default=30, ge=1)
    hotspot_explanation: str
    resolution_evidence_state: ResolutionEvidenceState
    resolution_evidence_explanation: str
    priority_level: str | None = None
    priority_score: int | None = None
    priority_reasons: list[str] = Field(default_factory=list)
    recommendations: list[CivicRecommendation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class HotspotItem(BaseModel):
    road: str
    city: str | None = None
    count: int = Field(ge=0)
    dominant_issue_category: str
    unresolved_count: int = Field(default=0, ge=0)
    time_window_days: int = Field(default=30, ge=1)
    explanation: str