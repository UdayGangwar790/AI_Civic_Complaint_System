from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.complaint_case import CaseStatus


class CaseStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Target lifecycle status")
    reason: Optional[str] = Field(None, max_length=500, description="Optional explanation for transition")
    resolution_evidence: Optional[str] = Field(None, min_length=1, max_length=500, description="Optional staff-authored resolution note; does not verify physical repair")


class CaseStatusUpdateResponse(BaseModel):
    reference_id: str
    previous_status: str
    new_status: str
    updated_at: datetime
    actor_user_id: str
    actor_role: str
    transition_result: str = "success"
    reason: Optional[str] = None
