from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import AuthenticatedUser, require_role
from app.models.roles import UserRole
from app.schemas.authority import AuthorityLocation, AuthorityResolutionResponse
from app.services.authority import AuthorityProviderError, AuthorityProviderTimeout, resolve_authority
from app.schemas.map_case import MapCasesResponse
from app.services.map_case import get_map_cases
from app.services.complaint_case import ComplaintCaseDatabaseError
from app.core.query_validation import validate_iso_date_range

router = APIRouter()


class AuthorityAccessCheckResponse(BaseModel):
    authorized: bool
    role: str


@router.get(
    "/access-check",
    response_model=AuthorityAccessCheckResponse,
    summary="Verify authority role access",
)
async def authority_access_check(
    current_user: AuthenticatedUser = Depends(require_role(UserRole.AUTHORITY)),
) -> AuthorityAccessCheckResponse:
    """
    Protected authority access check endpoint (M4.1).
    Explicit policy: Separate operational role. Strictly accessible to users with authority role.
    """
    return AuthorityAccessCheckResponse(
        authorized=True,
        role=current_user.role,
    )


@router.get("/resolve", response_model=AuthorityResolutionResponse, summary="Resolve evidence-backed authority context")
def resolve_authority_endpoint(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    road: str | None = None,
    area: str | None = None,
    city: str | None = None,
    district: str | None = None,
    state: str | None = None,
    country: str | None = None,
) -> AuthorityResolutionResponse:
    context = {
        "road": road,
        "area": area,
        "city": city,
        "district": district,
        "state": state,
        "country": country,
    }
    try:
        authority = resolve_authority(
            latitude=latitude,
            longitude=longitude,
            context=context,
        )
    except AuthorityProviderTimeout:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Authority source timed out.")
    except AuthorityProviderError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Authority information is temporarily unavailable.")

    return AuthorityResolutionResponse(
        location=AuthorityLocation(
            latitude=latitude,
            longitude=longitude,
            **context,
        ),
        authority=authority,
    )


@router.get(
    "/map/cases",
    response_model=MapCasesResponse,
    summary="Get assigned cases for operational authority map",
)
async def get_authority_map_cases_endpoint(
    issue: Optional[str] = Query(None, pattern="^(open_damaged_manhole|damaged_missing_road_sign|road_waterlogging|other_civic_issue)$", description="Filter by issue category"),
    priority: Optional[str] = Query(None, pattern="^(P1|P2|P3|P4)$", description="Filter by priority level"),
    case_status: Optional[str] = Query(None, alias="status", pattern="^(draft|submitted_to_cvki|under_review|assigned|in_progress|resolved|closed)$", description="Filter by status"),
    city: Optional[str] = Query(None, max_length=200, description="Filter by city"),
    created_from: Optional[str] = Query(None, max_length=40, description="Start date ISO string"),
    created_to: Optional[str] = Query(None, max_length=40, description="End date ISO string"),
    limit: int = Query(500, ge=1, le=2000, description="Max cases to map"),
    current_user: AuthenticatedUser = Depends(require_role(UserRole.AUTHORITY)),
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
