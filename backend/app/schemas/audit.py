import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

AuditResult = Literal["success", "failure", "denied"]


class AuditLogEntry(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[str] = Field(None, max_length=64)
    actor_user_id: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_reference_id: Optional[str] = None
    result: AuditResult = "success"
    metadata: dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = Field(None, max_length=512)


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class SecurityOverviewResponse(BaseModel):
    total_events: int = 0
    login_failures: int = 0
    denied_access_attempts: int = 0
    administrative_actions: int = 0
    assignment_actions: int = 0
    status_change_actions: int = 0
    recent_events: list[AuditLogEntry] = Field(default_factory=list)
    system_label: str = "Security & Audit Overview"
