"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.5: Field Inspection REST API Endpoints
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.models.roles import UserRole
from app.schemas.field_inspection import (
    FieldInspectionProtocol,
    FieldInspectionRecord,
    FieldInspectionSubmissionRequest,
)
import app.services.complaint_case as complaint_case_module
from app.services.field_inspection import (
    get_audit_engine,
    get_field_inspection_repository,
    get_protocol_generator,
)
from app.services.decision_projection import get_decision_projector
from app.services.multimodal.contracts import IssueCategory

logger = logging.getLogger("cvki.api.field_inspection")

router = APIRouter()


def _resolve_case_issue_category(case) -> IssueCategory:
    if case.issue and case.issue.class_name:
        name_upper = case.issue.class_name.upper()
        if "MANHOLE" in name_upper:
            return IssueCategory.OPEN_DAMAGED_MANHOLE
        elif "SIGN" in name_upper:
            return IssueCategory.DAMAGED_MISSING_ROAD_SIGN
        elif "WATER" in name_upper or "FLOOD" in name_upper:
            return IssueCategory.ROAD_WATERLOGGING
    return IssueCategory.OTHER_CIVIC_ISSUE


def _verify_case_access(case, current_user: AuthenticatedUser, require_authority_or_admin: bool = False) -> None:
    if require_authority_or_admin:
        if current_user.role == UserRole.CITIZEN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Citizens are strictly prohibited from submitting or modifying official field inspections.",
            )
        if current_user.role == UserRole.AUTHORITY.value:
            assigned = case.assignment.assigned_to_user_id if case.assignment else None
            if assigned and assigned != current_user.user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Authorities can only inspect cases assigned to them.",
                )
        return

    # General read access
    if current_user.role == UserRole.CITIZEN.value:
        if case.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Citizens can only access inspection data for their own reported cases.",
            )
    elif current_user.role == UserRole.AUTHORITY.value:
        assigned = case.assignment.assigned_to_user_id if case.assignment else None
        if assigned and assigned != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authorities can only access inspection data for cases assigned to them.",
            )


@router.get(
    "/cases/{reference_id}/protocol",
    response_model=FieldInspectionProtocol,
    summary="Get tailored field inspection protocol for a complaint case",
)
async def get_case_inspection_protocol(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> FieldInspectionProtocol:
    """
    Retrieves the deterministic, issue-specific inspection protocol for a case.
    RBAC:
    - Authority assigned / Admin: full operational protocol.
    - Citizen: read-only sanitized view of protocol steps for their own case.
    """
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _verify_case_access(case, current_user, require_authority_or_admin=False)

    category = _resolve_case_issue_category(case)
    case_loc = None
    if case.location:
        case_loc = {"latitude": case.location.latitude, "longitude": case.location.longitude}

    generator = get_protocol_generator()
    protocol = generator.generate_protocol(
        case_reference=reference_id,
        issue_category=category,
        case_location=case_loc,
    )

    return protocol


@router.post(
    "/cases/{reference_id}/submit",
    response_model=FieldInspectionRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an executed on-site field inspection and trigger automated audit",
    dependencies=[
        Depends(
            rate_limit_dependency(
                scope="inspection_submit",
                limit=settings.INFERENCE_RATE_LIMIT_REQUESTS,
                window_seconds=settings.INFERENCE_RATE_LIMIT_WINDOW_SECONDS,
            )
        )
    ],
)
async def submit_case_field_inspection(
    reference_id: str,
    request: FieldInspectionSubmissionRequest,
    http_request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Submits a completed on-site inspection.
    RBAC:
    - Authority assigned to case / Admin ONLY.
    - Citizens are strictly forbidden (403).
    Inspector ID is strictly taken from the authenticated user context.
    """
    from app.core.idempotency import compute_payload_fingerprint, get_idempotency_store
    fingerprint = compute_payload_fingerprint(request.model_dump())
    idem_key = http_request.headers.get("Idempotency-Key") or f"inspection_{reference_id}_{current_user.user_id}_{fingerprint}"
    idem_store = get_idempotency_store()
    acquired, existing_record = idem_store.acquire(
        key=idem_key,
        scope="field_inspection",
        fingerprint=fingerprint,
    )
    if not acquired and existing_record:
        if existing_record.status == "IN_PROGRESS":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A field inspection submission with this key is currently in progress.",
            )
        return JSONResponse(
            status_code=existing_record.response_status_code or 201,
            content=existing_record.response_body,
            headers={"Idempotent-Replay": "true"},
        )

    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        idem_store.release_on_failure(idem_key)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _verify_case_access(case, current_user, require_authority_or_admin=True)

    category = _resolve_case_issue_category(case)
    case_loc = None
    if case.location:
        case_loc = {"latitude": case.location.latitude, "longitude": case.location.longitude}

    generator = get_protocol_generator()
    protocol = generator.generate_protocol(
        case_reference=reference_id,
        issue_category=category,
        case_location=case_loc,
    )

    audit_engine = get_audit_engine()
    try:
        record = audit_engine.audit_submission(
            protocol=protocol,
            submission=request,
            inspector_id=current_user.user_id,
        )
    except ValueError as e:
        idem_store.release_on_failure(idem_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    repo = get_field_inspection_repository()
    repo.save(record)

    # Project field inspection into M6.4 Provenance & M6.5 Knowledge Graph
    try:
        projector = get_decision_projector()
        projector.project_field_inspection(record)
    except Exception as exc:
        logger.warning("Field inspection projection failed for %s: %s", record.inspection_id, exc)

    logger.info(
        "Recorded field inspection %s for case %s (Inspector: %s, Outcome: %s)",
        record.inspection_id,
        reference_id,
        current_user.user_id,
        record.audit_result.outcome.value,
    )

    record_dict = record.model_dump(mode="json")
    idem_store.complete(key=idem_key, response_status_code=201, response_body=record_dict)
    return record


@router.get(
    "/{inspection_id}",
    response_model=FieldInspectionRecord,
    summary="Retrieve a field inspection record and its audit evaluation",
)
async def get_field_inspection(
    inspection_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> FieldInspectionRecord:
    """
    Retrieves an inspection record by unique inspection_id.
    RBAC:
    - Admin: unrestricted.
    - Authority: must be assigned to the associated case or be the submitting inspector.
    - Citizen: can only view if they are the owner of the associated case.
    """
    repo = get_field_inspection_repository()
    record = repo.get(inspection_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Field inspection record '{inspection_id}' was not found.",
        )

    if current_user.role == UserRole.CITIZEN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizens are strictly prohibited from accessing private field inspection records.",
        )

    try:
        case = await complaint_case_module.get_case(record.case_reference)
        _verify_case_access(case, current_user, require_authority_or_admin=False)
    except complaint_case_module.ComplaintCaseNotFoundError:
        # If case is somehow missing, only admin or the submitting inspector can access
        if current_user.role != UserRole.ADMIN.value and current_user.user_id != record.inspector_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    return record


@router.get(
    "/cases/{reference_id}/inspections",
    response_model=list[FieldInspectionRecord],
    summary="List field inspections for a complaint case (Authority/Admin only)",
)
async def list_case_field_inspections(
    reference_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[FieldInspectionRecord]:
    if current_user.role == UserRole.CITIZEN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizens are strictly prohibited from accessing private field inspection records.",
        )
    try:
        case = await complaint_case_module.get_case(reference_id)
        _verify_case_access(case, current_user, require_authority_or_admin=True)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )
    repo = get_field_inspection_repository()
    records = repo.list_by_case(reference_id)
    return records[:limit]

