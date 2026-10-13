from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.complaint_case import CaseAssignment, ComplaintCase


class CaseAssignRequest(BaseModel):
    assigned_to_user_id: str = Field(..., min_length=1, description="Target authority user ID")


class AuthorityUserSummary(BaseModel):
    user_id: str
    email: str
    role: str = "authority"
    is_active: bool = True


class DashboardSummaryResponse(BaseModel):
    total_cases: int
    open_cases: int
    resolved_cases: int
    unassigned_cases: int
    priority_counts: dict[str, int]
    issue_counts: dict[str, int]
    duplicate_counts: dict[str, int]
    status_counts: dict[str, int]
    recent_cases: list[ComplaintCase]


class AdminCaseListResponse(BaseModel):
    items: list[ComplaintCase]
    page: int
    page_size: int
    total: int
    total_pages: int
