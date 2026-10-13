from datetime import datetime, timezone
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from app.api.deps import AuthenticatedUser, require_role
from app.models.roles import UserRole
from app.schemas.admin import (
    AdminCaseListResponse,
    AuthorityUserSummary,
    CaseAssignRequest,
    DashboardSummaryResponse,
)
from app.schemas.complaint_case import ComplaintCase
from app.services.admin_case import (
    assign_case_to_authority,
    get_admin_case_detail,
    get_admin_cases,
    get_dashboard_summary,
    list_authorities,
    unassign_case,
)
from app.services.complaint_case import ComplaintCaseDatabaseError, ComplaintCaseNotFoundError
from app.schemas.case_status import CaseStatusUpdateRequest, CaseStatusUpdateResponse
from app.services.case_status import transition_case_status
from app.schemas.map_case import MapCasesResponse
from app.services.map_case import get_map_cases
from app.schemas.analytics import OperationalAnalyticsResponse
from app.services.analytics import get_operational_analytics, generate_analytics_csv
from app.schemas.audit import AuditLogListResponse, SecurityOverviewResponse
from app.services.audit import AuditDatabaseError, AuditService
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.core.query_validation import validate_iso_date_range

router = APIRouter()
_expensive_search_limit = Depends(
    rate_limit_dependency(
        scope="expensive_search",
        limit=settings.EXPENSIVE_SEARCH_RATE_LIMIT_REQUESTS,
        window_seconds=settings.EXPENSIVE_SEARCH_RATE_LIMIT_WINDOW_SECONDS,
    )
)


class AdminAccessCheckResponse(BaseModel):
    authorized: bool
    role: str


@router.get(
    "/access-check",
    response_model=AdminAccessCheckResponse,
    summary="Verify admin role access",
)
async def admin_access_check(
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> AdminAccessCheckResponse:
    """
    Protected administrative access check probe.
    Accessible strictly to authenticated operators with admin role.
    """
    return AdminAccessCheckResponse(
        authorized=True,
        role=current_user.role,
    )


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    summary="Get aggregated operational dashboard statistics",
)
async def dashboard_summary_endpoint(
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> DashboardSummaryResponse:
    """
    Returns real aggregated statistics across all CVKI cases in MongoDB.
    """
    try:
        return await get_dashboard_summary()
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get(
    "/cases",
    response_model=AdminCaseListResponse,
    summary="Search, filter, and paginate complaint cases across all citizens",
    dependencies=[_expensive_search_limit],
)
async def list_admin_cases_endpoint(
    search: Optional[str] = Query(None, max_length=200, description="Search term across reference, road, city, title"),
    priority: Optional[str] = Query(None, pattern="^(P1|P2|P3|P4)$", description="Filter by priority level (P1, P2, P3, P4)"),
    issue: Optional[str] = Query(None, pattern="^(open_damaged_manhole|damaged_missing_road_sign|road_waterlogging|other_civic_issue)$", description="Filter by issue class name"),
    case_status: Optional[str] = Query(None, alias="status", pattern="^(draft|submitted_to_cvki|under_review|assigned|in_progress|resolved|closed)$", description="Filter by case status"),
    assignment: Optional[str] = Query(None, pattern="^(assigned|unassigned)$", description="Filter by assignment state"),
    duplicate: Optional[str] = Query(None, pattern="^(unique|possible_duplicate|duplicate)$", description="Filter by duplicate classification"),
    created_from: Optional[str] = Query(None, max_length=40, description="Start date ISO string"),
    created_to: Optional[str] = Query(None, max_length=40, description="End date ISO string"),
    sort_by: str = Query("newest", pattern="^(newest|oldest|highest_priority)$", description="Sort order: newest, oldest, or highest_priority"),
    page: int = Query(1, ge=1, le=1000, description="Page number (max 1000)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> AdminCaseListResponse:
    created_from, created_to = validate_iso_date_range(created_from, created_to)
    try:
        items, total = await get_admin_cases(
            search=search,
            priority=priority,
            issue=issue,
            status=case_status,
            assignment=assignment,
            duplicate=duplicate,
            created_from=created_from,
            created_to=created_to,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )
        total_pages = ceil(total / page_size) if total > 0 else 1
        return AdminCaseListResponse(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get(
    "/cases/{reference_id}",
    response_model=ComplaintCase,
    summary="Get full operational case details for administration",
)
async def get_admin_case_detail_endpoint(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> ComplaintCase:
    try:
        return await get_admin_case_detail(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{reference_id}' was not found.",
        )
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.post(
    "/cases/{reference_id}/assign",
    response_model=ComplaintCase,
    summary="Assign or reassign a complaint case to an authority account",
)
async def assign_case_endpoint(
    reference_id: str,
    payload: CaseAssignRequest,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> ComplaintCase:
    try:
        return await assign_case_to_authority(
            reference_id=reference_id,
            authority_user_id=payload.assigned_to_user_id,
            admin_user_id=current_user.user_id,
        )
    except ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{reference_id}' was not found.",
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


@router.post(
    "/cases/{reference_id}/unassign",
    response_model=ComplaintCase,
    summary="Remove operational authority assignment from a case",
)
async def unassign_case_endpoint(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> ComplaintCase:
    try:
        return await unassign_case(
            reference_id=reference_id,
            admin_user_id=current_user.user_id,
        )
    except ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{reference_id}' was not found.",
        )
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get(
    "/authorities",
    response_model=list[AuthorityUserSummary],
    summary="List operational authority accounts for assignment selection",
    dependencies=[_expensive_search_limit],
)
async def list_authorities_endpoint(
    page: int = Query(1, ge=1, le=1000, description="Page number (max 1000)"),
    page_size: int = Query(100, ge=1, le=200, description="Items per page (max 200)"),
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> list[AuthorityUserSummary]:
    try:
        return await list_authorities(page=page, page_size=page_size)
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.patch(
    "/cases/{reference_id}/status",
    response_model=CaseStatusUpdateResponse,
    summary="Update case workflow status via admin portal",
)
async def admin_update_case_status_endpoint(
    reference_id: str,
    payload: CaseStatusUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> CaseStatusUpdateResponse:
    try:
        return await transition_case_status(
            reference_id=reference_id,
            target_status=payload.status,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            reason=payload.reason,
        )
    except ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{reference_id}' was not found.",
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


@router.get(
    "/map/cases",
    response_model=MapCasesResponse,
    summary="Get operational complaint cases for interactive geospatial map",
    dependencies=[_expensive_search_limit],
)
async def get_admin_map_cases_endpoint(
    issue: Optional[str] = Query(None, pattern="^(open_damaged_manhole|damaged_missing_road_sign|road_waterlogging|other_civic_issue)$", description="Filter by issue category"),
    priority: Optional[str] = Query(None, pattern="^(P1|P2|P3|P4)$", description="Filter by priority level"),
    case_status: Optional[str] = Query(None, alias="status", pattern="^(draft|submitted_to_cvki|under_review|assigned|in_progress|resolved|closed)$", description="Filter by status"),
    city: Optional[str] = Query(None, max_length=200, description="Filter by city"),
    authority: Optional[str] = Query(None, max_length=200, description="Filter by authority name or status"),
    assignment: Optional[str] = Query(None, pattern="^(assigned|unassigned)$", description="Filter by assignment state"),
    created_from: Optional[str] = Query(None, max_length=40, description="Start date ISO string"),
    created_to: Optional[str] = Query(None, max_length=40, description="End date ISO string"),
    limit: int = Query(500, ge=1, le=2000, description="Max cases to map"),
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> MapCasesResponse:
    created_from, created_to = validate_iso_date_range(created_from, created_to)
    try:
        return await get_map_cases(
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            issue=issue,
            priority=priority,
            status=case_status,
            city=city,
            authority=authority,
            assignment=assignment,
            created_from=created_from,
            created_to=created_to,
            limit=limit,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get(
    "/analytics",
    response_model=OperationalAnalyticsResponse,
    summary="Get aggregated operational analytics across civic complaints",
    dependencies=[_expensive_search_limit],
)
async def admin_operational_analytics_endpoint(
    issue: Optional[str] = Query(None, pattern="^(open_damaged_manhole|damaged_missing_road_sign|road_waterlogging|other_civic_issue)$", description="Filter by issue class name"),
    priority: Optional[str] = Query(None, pattern="^(P1|P2|P3|P4)$", description="Filter by priority level"),
    case_status: Optional[str] = Query(None, alias="status", pattern="^(draft|submitted_to_cvki|under_review|assigned|in_progress|resolved|closed)$", description="Filter by status"),
    city: Optional[str] = Query(None, max_length=200, description="Filter by city"),
    authority: Optional[str] = Query(None, max_length=200, description="Filter by authority"),
    created_from: Optional[str] = Query(None, max_length=40, description="Start date ISO string"),
    created_to: Optional[str] = Query(None, max_length=40, description="End date ISO string"),
    group_by: str = Query("daily", pattern="^(daily|weekly|monthly)$", description="Time grouping: daily, weekly, or monthly"),
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> OperationalAnalyticsResponse:
    created_from, created_to = validate_iso_date_range(created_from, created_to)
    try:
        return await get_operational_analytics(
            issue=issue,
            priority=priority,
            status=case_status,
            city=city,
            authority=authority,
            created_from=created_from,
            created_to=created_to,
            group_by=group_by,
        )
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get(
    "/analytics/export",
    summary="Export aggregated operational analytics to CSV",
    dependencies=[_expensive_search_limit],
)
async def export_operational_analytics_csv(
    issue: Optional[str] = Query(None, pattern="^(open_damaged_manhole|damaged_missing_road_sign|road_waterlogging|other_civic_issue)$"),
    priority: Optional[str] = Query(None, pattern="^(P1|P2|P3|P4)$"),
    case_status: Optional[str] = Query(None, alias="status", pattern="^(draft|submitted_to_cvki|under_review|assigned|in_progress|resolved|closed)$"),
    city: Optional[str] = Query(None, max_length=200),
    authority: Optional[str] = Query(None, max_length=200),
    created_from: Optional[str] = Query(None, max_length=40),
    created_to: Optional[str] = Query(None, max_length=40),
    group_by: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> PlainTextResponse:
    created_from, created_to = validate_iso_date_range(created_from, created_to)
    try:
        analytics = await get_operational_analytics(
            issue=issue,
            priority=priority,
            status=case_status,
            city=city,
            authority=authority,
            created_from=created_from,
            created_to=created_to,
            group_by=group_by,
        )
        csv_data = generate_analytics_csv(analytics)
        return PlainTextResponse(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=cvki_operational_analytics.csv"},
        )
    except ComplaintCaseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )


@router.get(
    "/audit",
    response_model=AuditLogListResponse,
    summary="Search, filter, and paginate security and operational audit logs",
    dependencies=[_expensive_search_limit],
)
async def list_audit_logs_endpoint(
    actor: Optional[str] = Query(None, max_length=100, description="Filter by actor user ID prefix"),
    role: Optional[str] = Query(None, pattern="^(citizen|admin|authority)$", description="Filter by actor role"),
    action: Optional[str] = Query(None, max_length=100, description="Filter by action name"),
    result: Optional[str] = Query(None, pattern="^(success|failure|denied)$", description="Filter by result"),
    resource_id: Optional[str] = Query(None, alias="reference_id", max_length=100, description="Filter by resource reference ID"),
    created_from: Optional[str] = Query(None, max_length=40, description="Start date ISO string"),
    created_to: Optional[str] = Query(None, max_length=40, description="End date ISO string"),
    page: int = Query(1, ge=1, le=1000, description="Page number (max 1000)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> AuditLogListResponse:
    created_from, created_to = validate_iso_date_range(created_from, created_to)
    try:
        return await AuditService.list_logs(
            actor=actor,
            role=role,
            action=action,
            result=result,
            resource_reference_id=resource_id,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
    except (AuditDatabaseError, PyMongoError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit service is unavailable.",
        )


@router.get(
    "/audit/summary",
    response_model=SecurityOverviewResponse,
    summary="Get aggregated security indicators and audit summary",
)
async def get_security_overview_endpoint(
    current_user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> SecurityOverviewResponse:
    try:
        return await AuditService.get_security_overview()
    except (AuditDatabaseError, PyMongoError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit service is unavailable.",
        )
