from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MapCaseItem(BaseModel):
    reference_id: str
    issue: str
    issue_label: str
    status: str
    priority: str
    latitude: float
    longitude: float
    road: Optional[str] = None
    city: Optional[str] = None
    authority_name: Optional[str] = None
    authority_status: Optional[str] = None
    assigned: bool = False
    assigned_to_user_id: Optional[str] = None
    assignment_status: str = "unassigned"
    created_at: Optional[datetime] = None


class MapCasesResponse(BaseModel):
    mapped_cases: list[MapCaseItem] = Field(default_factory=list)
    total_mapped: int = 0
    unmapped_cases_count: int = 0
    total_matching: int = 0
