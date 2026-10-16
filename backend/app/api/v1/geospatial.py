from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AuthenticatedUser, get_current_user_optional, require_authenticated_user
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.models.roles import UserRole
from app.schemas.external_civic import ExternalCivicContextResponse
from app.schemas.geospatial import (
    GeospatialContextRequest,
    GeospatialContextResponse,
    NearbyCasesSummary,
    RoadIdentification,
)
from app.services.complaint_case import ComplaintCaseNotFoundError
from app.services.external_civic_data import external_civic_service
from app.services.geocoding_provider import geocoding_service
from app.services.geospatial_intelligence import (
    find_nearby_cases,
    get_case_geospatial_context,
    get_geospatial_intelligence_context,
)
from app.services.spatial import CoordinateValidationError, validate_coordinates

router = APIRouter()

_expensive_search_limit = Depends(
    rate_limit_dependency(
        scope="expensive_search",
        limit=settings.EXPENSIVE_SEARCH_RATE_LIMIT_REQUESTS,
        window_seconds=settings.EXPENSIVE_SEARCH_RATE_LIMIT_WINDOW_SECONDS,
    )
)


@router.post(
    "/context",
    response_model=GeospatialContextResponse,
    summary="Get comprehensive geospatial intelligence context for coordinates",
    dependencies=[_expensive_search_limit],
)
async def get_geospatial_context_endpoint(
    request: GeospatialContextRequest,
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional),
) -> GeospatialContextResponse:
    """
    Evaluates geospatial context for given coordinates:
    - Normalized reverse-geocoded location
    - Road identification and road type classification
    - Road segment context
    - Administrative jurisdiction
    - Nearby civic cases and spatial relationships
    - M6.1 Authority intelligence resolution
    """
    try:
        validate_coordinates(request.latitude, request.longitude, allow_null_island=False)
    except CoordinateValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    role = current_user.role if current_user else UserRole.CITIZEN.value

    return await get_geospatial_intelligence_context(
        latitude=request.latitude,
        longitude=request.longitude,
        accuracy_m=request.accuracy_m,
        issue_category=request.issue_category,
        radius_meters=request.radius_meters or 250.0,
        time_window_days=request.time_window_days or 30,
        actor_role=role,
    )


@router.get(
    "/cases/nearby",
    response_model=NearbyCasesSummary,
    summary="Search nearby civic cases around a coordinate radius",
    dependencies=[_expensive_search_limit],
)
async def get_nearby_cases_endpoint(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude"),
    radius_meters: float = Query(250.0, ge=10.0, le=5000.0, description="Search radius in meters (max 5000m)"),
    time_window_days: int = Query(30, ge=1, le=365, description="Historical time window in days"),
    issue: Optional[str] = Query(None, description="Optional issue category filter"),
    unresolved_only: bool = Query(False, description="Filter for unresolved cases only"),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional),
) -> NearbyCasesSummary:
    """
    Radius search around coordinates returning nearby civic cases summary.
    Enforces privacy rules: strips citizen PII and masks references for citizen roles.
    """
    try:
        validate_coordinates(latitude, longitude, allow_null_island=False)
    except CoordinateValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    role = current_user.role if current_user else UserRole.CITIZEN.value

    return await find_nearby_cases(
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        time_window_days=time_window_days,
        issue_category=issue,
        unresolved_only=unresolved_only,
        actor_role=role,
    )


@router.get(
    "/cases/{reference_id}/context",
    response_model=GeospatialContextResponse,
    summary="Get geospatial context panel for an existing case",
    dependencies=[_expensive_search_limit],
)
async def get_case_geospatial_context_endpoint(
    reference_id: str,
    radius_meters: float = Query(250.0, ge=10.0, le=5000.0),
    time_window_days: int = Query(30, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> GeospatialContextResponse:
    """
    Returns spatial preview context for an operational or citizen case.
    Enforces RBAC: authorities can only inspect their assigned cases.
    """
    try:
        return await get_case_geospatial_context(
            reference_id=reference_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            radius_meters=radius_meters,
            time_window_days=time_window_days,
        )
    except ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


@router.get(
    "/road/resolve",
    summary="Resolve road identification and type for coordinates",
)
def resolve_road_endpoint(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    accuracy_m: Optional[float] = Query(None, ge=0.0),
):
    """
    Lightweight endpoint returning evidence-based road identification and matching quality.
    """
    try:
        validate_coordinates(latitude, longitude, allow_null_island=False)
    except CoordinateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    norm_loc, road_id, segment_ctx, source_status = geocoding_service.resolve(
        latitude, longitude, accuracy_m=accuracy_m
    )
    return {
        "location": norm_loc.model_dump(mode="json"),
        "road": road_id.model_dump(mode="json"),
        "segment": segment_ctx.model_dump(mode="json"),
        "source_status": source_status.value,
    }


@router.get(
    "/external-context",
    response_model=ExternalCivicContextResponse,
    summary="Retrieve real-time external civic, weather, and environmental context",
    dependencies=[_expensive_search_limit],
)
def get_external_civic_context_endpoint(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude"),
    issue_category: Optional[str] = Query(None, description="Civic issue category (e.g. road_waterlogging)"),
    window_hours: int = Query(24, ge=1, le=168, description="Observation time window in hours (1-168)"),
) -> ExternalCivicContextResponse:
    """
    Retrieves real-time or cached external civic and environmental context for coordinates.
    Provides non-causal weather, precipitation, and traffic conditions.
    """
    try:
        validate_coordinates(latitude, longitude, allow_null_island=False)
    except CoordinateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return external_civic_service.get_external_civic_context(
        latitude=latitude,
        longitude=longitude,
        issue_category=issue_category,
        window_hours=window_hours,
    )

