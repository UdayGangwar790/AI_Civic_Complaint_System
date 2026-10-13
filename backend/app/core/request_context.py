from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


current_request_context: ContextVar[Optional[RequestContext]] = ContextVar(
    "current_request_context",
    default=None,
)
