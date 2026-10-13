import logging
import re
from datetime import datetime, timezone
from math import ceil
from typing import Any, Optional

from pymongo.errors import PyMongoError

from app.core.database import AUDIT_LOGS_COLLECTION, mongo_manager
from app.core.request_context import current_request_context
from app.schemas.audit import AuditLogEntry, AuditLogListResponse, SecurityOverviewResponse

logger = logging.getLogger("cvki.audit")

_DEFAULT_DB = object()

SENSITIVE_KEY_PATTERNS = {"password", "secret", "token", "jwt", "auth", "credential", "hash", "key"}


class AuditDatabaseError(RuntimeError):
    """Audit data could not be read because persistence is unavailable."""


def _sanitize_metadata(data: Any) -> Any:
    """
    Recursively strips any sensitive keys and tokens from audit metadata payloads.
    Guarantees no passwords, tokens, or hashes are ever persisted to audit logs.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if any(pattern in k.lower() for pattern in SENSITIVE_KEY_PATTERNS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = _sanitize_metadata(v)
        return sanitized
    elif isinstance(data, list):
        return [_sanitize_metadata(elem) for elem in data]
    return data


def _get_audit_collection(db: object = None):
    if db is not None and hasattr(db, "__getitem__"):
        return db[AUDIT_LOGS_COLLECTION]
    database = mongo_manager.db
    if database is None:
        return None
    return database[AUDIT_LOGS_COLLECTION]


class AuditService:
    @staticmethod
    async def record_event(
        action: str,
        result: str = "success",
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_reference_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: object = _DEFAULT_DB,
    ) -> Optional[AuditLogEntry]:
        """
        Appends an immutable audit event entry to the audit_logs collection.
        Fail-safe: Logs errors on DB unavailability without throwing unhandled exceptions.
        """
        try:
            col = _get_audit_collection(db)
            if col is None:
                logger.warning("AuditService: MongoDB not available; skipping audit event '%s'.", action)
                return None

            clean_meta = _sanitize_metadata(metadata or {})
            request_context = current_request_context.get()
            entry = AuditLogEntry(
                request_id=request_id or (request_context.request_id if request_context else None),
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action=action,
                resource_type=resource_type,
                resource_reference_id=resource_reference_id,
                result=result,
                metadata=clean_meta,
                ip_address=ip_address or (request_context.ip_address if request_context else None),
                user_agent=(user_agent or (request_context.user_agent if request_context else None))[:512]
                if user_agent or (request_context and request_context.user_agent)
                else None,
            )

            doc = entry.model_dump()
            await col.insert_one(doc)
            return entry
        except Exception as exc:
            logger.error(
                "Audit event persistence failed (action=%s, error_type=%s).",
                action,
                type(exc).__name__,
            )
            return None

    @staticmethod
    async def list_logs(
        actor: Optional[str] = None,
        role: Optional[str] = None,
        action: Optional[str] = None,
        result: Optional[str] = None,
        resource_reference_id: Optional[str] = None,
        created_from: Optional[str] = None,
        created_to: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        db: object = _DEFAULT_DB,
    ) -> AuditLogListResponse:
        """
        Searches, filters, and paginates audit log records for administrative inspection.
        Sorted newest first.
        """
        col = _get_audit_collection(db)
        if col is None:
            raise AuditDatabaseError("Audit data is unavailable.")

        page = min(max(1, page), 1000)
        page_size = min(max(1, page_size), 100)
        query: dict[str, Any] = {}
        if actor and actor.strip():
            query["actor_user_id"] = {"$regex": f"^{re.escape(actor.strip())}", "$options": "i"}
        if role and role.strip():
            query["actor_role"] = role.strip().lower()
        if action and action.strip():
            query["action"] = action.strip()
        if result and result.strip():
            query["result"] = result.strip().lower()
        if resource_reference_id and resource_reference_id.strip():
            query["resource_reference_id"] = resource_reference_id.strip()

        date_filter: dict[str, Any] = {}
        if created_from and created_from.strip():
            try:
                norm = created_from.strip().replace(" ", "+").replace("Z", "+00:00")
                date_filter["$gte"] = datetime.fromisoformat(norm)
            except ValueError:
                pass
        if created_to and created_to.strip():
            try:
                norm = created_to.strip().replace(" ", "+").replace("Z", "+00:00")
                date_filter["$lte"] = datetime.fromisoformat(norm)
            except ValueError:
                pass
        if date_filter:
            query["timestamp"] = date_filter

        total = await col.count_documents(query)
        skip = (page - 1) * page_size
        cursor = col.find(query).sort("timestamp", -1).skip(skip).limit(page_size)

        items = []
        async for doc in cursor:
            doc.pop("_id", None)
            items.append(AuditLogEntry(**doc))

        total_pages = max(1, ceil(total / page_size)) if total > 0 else 1

        return AuditLogListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    async def get_security_overview(db: object = _DEFAULT_DB) -> SecurityOverviewResponse:
        """
        Computes real security and audit overview metrics based on persisted audit records.
        """
        col = _get_audit_collection(db)
        if col is None:
            raise AuditDatabaseError("Audit data is unavailable.")

        total_events = await col.count_documents({})
        login_failures = await col.count_documents({"action": "auth_login", "result": "failure"})
        denied_attempts = await col.count_documents({"result": "denied"})
        admin_actions = await col.count_documents({"actor_role": "admin", "result": "success"})
        assign_actions = await col.count_documents({"action": {"$in": ["case_assigned", "case_unassigned"]}})
        status_actions = await col.count_documents({"action": "case_status_changed"})

        # Top 10 recent events
        recent_cursor = col.find({}).sort("timestamp", -1).limit(10)
        recent_events = []
        async for doc in recent_cursor:
            doc.pop("_id", None)
            recent_events.append(AuditLogEntry(**doc))

        return SecurityOverviewResponse(
            total_events=total_events,
            login_failures=login_failures,
            denied_access_attempts=denied_attempts,
            administrative_actions=admin_actions,
            assignment_actions=assign_actions,
            status_change_actions=status_actions,
            recent_events=recent_events,
            system_label="Security & Audit Overview",
        )
