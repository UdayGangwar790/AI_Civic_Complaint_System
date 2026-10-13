from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


DuplicateClassification = Literal["unique", "possible_duplicate", "duplicate"]


class DuplicateCheckRequest(BaseModel):
    complaint_text: str = Field(min_length=1, max_length=5000)
    issue_category: str = Field(min_length=1, max_length=80)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    created_at: Optional[datetime] = None


class DuplicateCheckResponse(BaseModel):
    classification: DuplicateClassification
    similarity_score: float = Field(ge=0.0, le=1.0)
    matched_reference_id: Optional[str] = None
    distance_meters: Optional[float] = None
    time_difference_hours: Optional[float] = None
    issue_match: bool
    reason: str
    method: str = "tfidf_cosine_similarity_with_spatiotemporal_heuristic"
