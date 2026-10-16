from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


NotificationType = Literal[
    "case_created",
    "priority_assigned",
    "duplicate_detected",
    "case_status_changed",
    "follow_up_due",
    "government_submission_prepared",
    "government_submission_status_changed",
    "government_submission_accepted",
    "government_submission_rejected",
    "government_reconciliation_required",
    "case_assigned",
    "case_unassigned",
    "system_notification",
    "government_reference_confirmed",
    "government_reference_conflict",
    "government_reference_reconciled",
    "government_status_changed",
    "government_status_unavailable",
    "government_needs_information",
    "escalation_recommended",
    "resolution_verification_submitted",
    "resolution_verification_disputed",
    "resolution_verification_reviewed",
]

NotificationPriority = Literal["P1", "P2", "P3", "P4"]


class NotificationBase(BaseModel):
    user_id: str = Field(..., description="ID of the citizen recipient")
    reference_id: Optional[str] = Field(None, description="Associated CVKI case reference ID, if applicable")
    type: NotificationType
    title: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    priority: NotificationPriority = Field(default="P3", description="Priority level matching M3.8 triage (P1-P4)")
    metadata: Optional[dict[str, Any]] = None
    delivery_status: Literal["in_app"] = "in_app"


class NotificationCreate(NotificationBase):
    pass


class Notification(NotificationBase):
    notification_id: str
    is_read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[Notification]
    total: int
    page: int
    page_size: int
    pages: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkReadResponse(BaseModel):
    success: bool
    notification: Optional[Notification] = None


class MarkAllReadResponse(BaseModel):
    success: bool
    updated_count: int
