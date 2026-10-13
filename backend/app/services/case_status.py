import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo.errors import PyMongoError

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, mongo_manager
from app.models.roles import UserRole
from app.schemas.case_status import CaseStatusUpdateResponse
from app.schemas.complaint_case import ComplaintCase
from app.services.complaint_case import ComplaintCaseDatabaseError, ComplaintCaseNotFoundError
from app.services.notification import (
    create_notification,
    trigger_case_status_changed_notification,
)
from app.schemas.notification import NotificationCreate

logger = logging.getLogger("cvki.case_status")

# Explicit canonical lifecycle transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    "submitted_to_cvki": {"assigned", "under_review", "in_progress", "closed"},
    "under_review": {"assigned", "in_progress", "resolved", "closed"},
    "assigned": {"in_progress", "submitted_to_cvki", "closed"},
    "in_progress": {"resolved", "assigned", "closed"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),  # Terminal state: cannot be modified
    "draft": {"submitted_to_cvki", "closed"},
}

# Authority allowed transitions
AUTHORITY_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "assigned": {"in_progress"},
    "in_progress": {"resolved"},
}

_DEFAULT_DB = object()


def _get_collection(name: str = COMPLAINT_CASES_COLLECTION, db: object = None):
    if db is not None and hasattr(db, "__getitem__"):
        return db[name]
    database = mongo_manager.db
    if database is None:
        raise ComplaintCaseDatabaseError("MongoDB persistence is unavailable.")
    return database[name]


def _clean_case_doc(doc: dict) -> ComplaintCase:
    doc.pop("_id", None)
    if isinstance(doc.get("created_at"), datetime) and doc["created_at"].tzinfo is None:
        doc["created_at"] = doc["created_at"].replace(tzinfo=timezone.utc)
    if isinstance(doc.get("updated_at"), datetime) and doc["updated_at"].tzinfo is None:
        doc["updated_at"] = doc["updated_at"].replace(tzinfo=timezone.utc)
    if (
        isinstance(doc.get("assignment"), dict)
        and isinstance(doc["assignment"].get("assigned_at"), datetime)
        and doc["assignment"]["assigned_at"].tzinfo is None
    ):
        doc["assignment"]["assigned_at"] = doc["assignment"]["assigned_at"].replace(tzinfo=timezone.utc)
    return ComplaintCase.model_validate(doc)


async def transition_case_status(
    reference_id: str,
    target_status: str,
    actor_user_id: str,
    actor_role: str,
    reason: Optional[str] = None,
    resolution_evidence: Optional[str] = None,
    db: object = _DEFAULT_DB,
) -> CaseStatusUpdateResponse:
    """
    Executes a formal case status transition with lifecycle rules,
    role-based authorization, and notification triggers.
    """
    clean_target = target_status.strip().lower()
    cases_col = _get_collection(COMPLAINT_CASES_COLLECTION, db)

    try:
        doc = await cases_col.find_one({"reference_id": reference_id})
    except PyMongoError as exc:
        logger.error("Case status lookup failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc

    if not doc:
        raise ComplaintCaseNotFoundError(reference_id)

    case = _clean_case_doc(doc)
    current_status = case.status

    # Helper for audit recording failure/denied
    async def _audit_rejection(res: str, err_msg: str):
        try:
            from app.services.audit import AuditService
            await AuditService.record_event(
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="case_status_changed",
                resource_type="case",
                resource_reference_id=reference_id,
                result=res,
                metadata={
                    "previous_status": current_status,
                    "target_status": clean_target,
                    "error": err_msg,
                },
                db=db,
            )
        except Exception:
            pass

    if resolution_evidence is not None and clean_target != "resolved":
        msg = "Resolution evidence can only be recorded when marking a case resolved."
        await _audit_rejection("failure", msg)
        raise ValueError(msg)
    clean_resolution_evidence = resolution_evidence.strip() if resolution_evidence is not None else None
    if resolution_evidence is not None and not clean_resolution_evidence:
        msg = "Resolution evidence note cannot be empty."
        await _audit_rejection("failure", msg)
        raise ValueError(msg)

    # 1. Closed case protection
    if current_status == "closed":
        msg = f"Case '{reference_id}' is closed and cannot be modified."
        await _audit_rejection("failure", msg)
        raise ValueError(msg)

    # 2. Prevent illegal no-op or backwards/invalid transitions
    allowed_next = VALID_TRANSITIONS.get(current_status, set())
    if clean_target not in allowed_next:
        msg = f"Illegal status transition from '{current_status}' to '{clean_target}'."
        await _audit_rejection("failure", msg)
        raise ValueError(msg)

    # 3. Role-based transition enforcement
    if actor_role == UserRole.CITIZEN.value:
        msg = "Citizens cannot modify case status."
        await _audit_rejection("denied", msg)
        raise PermissionError(msg)

    elif actor_role == UserRole.AUTHORITY.value:
        # Authority can only modify cases assigned to them
        assigned_user = case.assignment.assigned_to_user_id if case.assignment else None
        if not assigned_user or assigned_user != actor_user_id:
            msg = "Authorities can only transition cases assigned to them."
            await _audit_rejection("denied", msg)
            raise PermissionError(msg)

        auth_allowed = AUTHORITY_ALLOWED_TRANSITIONS.get(current_status, set())
        if clean_target not in auth_allowed:
            msg = f"Authorities are not permitted to transition case from '{current_status}' to '{clean_target}'."
            await _audit_rejection("denied", msg)
            raise PermissionError(msg)

    elif actor_role == UserRole.ADMIN.value:
        # Admin can transition any non-closed case according to VALID_TRANSITIONS
        pass
    else:
        msg = "Unauthorized role for status transition."
        await _audit_rejection("denied", msg)
        raise PermissionError(msg)

    # 4. Perform atomic update in MongoDB
    now = datetime.now(timezone.utc)
    update_fields: dict = {
        "status": clean_target,
        "updated_at": now,
    }
    update_operators: dict = {"$set": update_fields}

    if clean_target == "resolved":
        # The marker makes older resolution notes stale after reopen/re-resolution.
        update_fields["resolution_evidence_recorded_at"] = now
        if clean_resolution_evidence:
            update_operators["$push"] = {
                "resolution_evidence": {
                    "note": clean_resolution_evidence,
                    "recorded_at": now,
                    "recorded_by_role": actor_role,
                }
            }
    elif current_status in {"resolved", "closed"}:
        update_fields["resolution_evidence_recorded_at"] = now

    # If transitioning to 'assigned' and assignment exists, ensure assignment_status is assigned
    if clean_target == "assigned" and case.assignment:
        update_fields["assignment.assignment_status"] = "assigned"

    try:
        await cases_col.update_one(
            {"reference_id": reference_id},
            update_operators,
        )
    except PyMongoError as exc:
        logger.error("Case status update failed (error_type=%s).", type(exc).__name__)
        raise ComplaintCaseDatabaseError("Database service is unavailable.") from exc

    # 5. Trigger notifications (M3.9)
    try:
        # Notify the citizen owner
        await trigger_case_status_changed_notification(case, current_status, clean_target)

        # If admin changed status and case is assigned to an authority, notify the authority
        if (
            actor_role == UserRole.ADMIN.value
            and case.assignment
            and case.assignment.assigned_to_user_id
            and case.assignment.assigned_to_user_id != actor_user_id
        ):
            await create_notification(
                NotificationCreate(
                    user_id=case.assignment.assigned_to_user_id,
                    reference_id=case.reference_id,
                    type="case_status_changed",
                    title=f"Case Status Updated: {case.reference_id}",
                    message=f"Case {case.reference_id} status was updated to '{clean_target}' by administration.",
                    priority="P2",
                    metadata={
                        "old_status": current_status,
                        "new_status": clean_target,
                        "updated_by": actor_user_id,
                    },
                )
            )
    except Exception as notif_err:
        logger.warning("Status change notification error: %s", notif_err)

    # 6. Audit logging (M4.8 integration)
    try:
        from app.services.audit import AuditService
        await AuditService.record_event(
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="case_status_changed",
            resource_type="case",
            resource_reference_id=reference_id,
            result="success",
            metadata={
                "previous_status": current_status,
                "new_status": clean_target,
                "reason": reason,
                "resolution_evidence_recorded": bool(clean_resolution_evidence),
            },
            db=db,
        )
    except Exception as audit_err:
        logger.debug("Audit logging non-fatal exception: %s", audit_err)

    return CaseStatusUpdateResponse(
        reference_id=reference_id,
        previous_status=current_status,
        new_status=clean_target,
        updated_at=now,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        transition_result="success",
        reason=reason,
    )
