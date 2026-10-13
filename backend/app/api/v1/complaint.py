from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AuthenticatedUser, get_current_user
from app.schemas.complaint import ComplaintDraftRequest, ComplaintDraftResponse
from app.schemas.complaint_case import (
    ComplaintCase,
    ComplaintCaseCreateRequest,
    ComplaintCaseStatus,
    ComplaintHistoryResponse,
)
from app.services.complaint import UnsupportedIssueError, generate_complaint
from app.services.authority import (
    AuthorityProviderError,
    AuthorityProviderTimeout,
    resolve_authority_for_location,
)
from app.services.complaint_case import (
    ComplaintCaseDatabaseError,
    ComplaintCaseDuplicateError,
    ComplaintCaseNotFoundError,
    create_case,
    get_case,
    get_case_status,
    get_user_cases,
)

from app.schemas.guidance import GovernmentGuidanceRequest, GovernmentGuidanceResponse
from app.services.guidance import generate_government_guidance
from app.schemas.duplicate import DuplicateCheckRequest, DuplicateCheckResponse
from app.services.duplicate import check_complaint_duplicate
from app.schemas.government_submission import (
    PrepareSubmissionResponse,
    SubmissionReadinessResponse,
)
from app.services.government_submission import (
    SubmissionBlockedError,
    SubmissionNotReadyError,
    check_submission_readiness,
    prepare_government_submission,
)
from app.schemas.case_status import CaseStatusUpdateRequest, CaseStatusUpdateResponse
from app.services.case_status import transition_case_status
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency

router = APIRouter()


def _resolve_request_authority(location):
    try:
        return resolve_authority_for_location(location)
    except AuthorityProviderTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Authority source timed out.",
        ) from exc
    except AuthorityProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authority information is temporarily unavailable.",
        ) from exc


@router.post("/draft", response_model=ComplaintDraftResponse, summary="Generate an editable civic complaint draft")
def create_complaint_draft(request: ComplaintDraftRequest) -> ComplaintDraftResponse:
    try:
        trusted_request = request.model_copy(
            update={"authority": _resolve_request_authority(request.location)}
        )
        return generate_complaint(trusted_request)
    except UnsupportedIssueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/guidance", response_model=GovernmentGuidanceResponse, summary="Generate official government complaint portal guidance")
def get_complaint_guidance(request: GovernmentGuidanceRequest) -> GovernmentGuidanceResponse:
    trusted_request = request.model_copy(
        update={"authority": _resolve_request_authority(request.location)}
    )
    return generate_government_guidance(trusted_request)


@router.post(
    "/duplicate-check",
    response_model=DuplicateCheckResponse,
    summary="Detect duplicate or near-duplicate civic complaint cases",
    dependencies=[
        Depends(rate_limit_dependency(
            scope="duplicate_check",
            limit=settings.DUPLICATE_CHECK_RATE_LIMIT_REQUESTS,
            window_seconds=settings.DUPLICATE_CHECK_RATE_LIMIT_WINDOW_SECONDS,
        ))
    ],
)
async def check_duplicate_complaint_endpoint(
    request: DuplicateCheckRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DuplicateCheckResponse:
    try:
        return await check_complaint_duplicate(request, raise_on_db_error=True)
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable. Duplicate check failed.",
        )


@router.post(
    "/cases",
    response_model=ComplaintCase,
    summary="Create an internal CVKI complaint case",
    dependencies=[
        Depends(rate_limit_dependency(
            scope="complaint_creation",
            limit=settings.COMPLAINT_RATE_LIMIT_REQUESTS,
            window_seconds=settings.COMPLAINT_RATE_LIMIT_WINDOW_SECONDS,
        ))
    ],
)
async def create_complaint_case(
    request: ComplaintCaseCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ComplaintCase:
    try:
        # user_id is strictly derived from the authenticated JWT, never accepted from request body
        new_case = await create_case(request, user_id=current_user.user_id)
        try:
            from app.services.audit import AuditService
            await AuditService.record_event(
                action="case_created",
                result="success",
                actor_user_id=current_user.user_id,
                actor_role=current_user.role,
                resource_type="case",
                resource_reference_id=new_case.reference_id,
                metadata={
                    "issue": new_case.issue.class_name,
                    "city": new_case.location.city if new_case.location else None,
                },
            )
        except Exception:
            pass
        return new_case
    except (ValueError, UnsupportedIssueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except AuthorityProviderTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Authority source timed out.",
        ) from exc
    except AuthorityProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authority information is temporarily unavailable.",
        ) from exc
    except ComplaintCaseDuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable. Complaint case persistence failed.",
        )


@router.get("/cases/my", response_model=ComplaintHistoryResponse, summary="Get authenticated citizen's complaint history")
async def get_my_complaint_cases(
    page: int = Query(1, ge=1, le=1000, description="Page number (1-indexed, max 1000)"),
    limit: int = Query(10, ge=1, le=50, description="Cases per page (max 50)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ComplaintHistoryResponse:
    try:
        return await get_user_cases(current_user.user_id, page=page, limit=limit)
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get("/cases/{reference_id}", response_model=ComplaintCase, summary="Get an internal CVKI complaint case")
async def get_complaint_case(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ComplaintCase:
    try:
        case = await get_case(reference_id)
        # Strict user isolation: only the owner can access their case
        if case.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
        return case
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get("/cases/{reference_id}/status", response_model=ComplaintCaseStatus, summary="Get CVKI case status")
async def get_complaint_case_status(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ComplaintCaseStatus:
    try:
        case = await get_case(reference_id)
        # Strict user isolation: only the owner can check status
        if case.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
        return await get_case_status(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get(
    "/cases/{reference_id}/submission-readiness",
    response_model=SubmissionReadinessResponse,
    summary="Evaluate case readiness for government dispatch packaging",
)
async def get_case_submission_readiness(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SubmissionReadinessResponse:
    try:
        case = await get_case(reference_id)
        if case.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
        return check_submission_readiness(case)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.post(
    "/cases/{reference_id}/prepare-submission",
    response_model=PrepareSubmissionResponse,
    summary="Compile a verified government submission package without external submission",
)
async def prepare_case_submission(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PrepareSubmissionResponse:
    try:
        case = await get_case(reference_id)
        if case.user_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
        _, response = await prepare_government_submission(case, user_id=current_user.user_id)
        try:
            from app.services.audit import AuditService
            await AuditService.record_event(
                action="submission_prepared",
                result="success",
                actor_user_id=current_user.user_id,
                actor_role=current_user.role,
                resource_type="submission_package",
                resource_reference_id=reference_id,
            )
        except Exception:
            pass
        return response
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except (SubmissionBlockedError, SubmissionNotReadyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.patch(
    "/cases/{reference_id}/status",
    response_model=CaseStatusUpdateResponse,
    summary="Update civic complaint case operational workflow status",
)
async def update_complaint_case_status(
    reference_id: str,
    payload: CaseStatusUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CaseStatusUpdateResponse:
    try:
        return await transition_case_status(
            reference_id=reference_id,
            target_status=payload.status,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            reason=payload.reason,
            resolution_evidence=payload.resolution_evidence,
        )
    except ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CVKI case '{reference_id}' was not found.",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )
