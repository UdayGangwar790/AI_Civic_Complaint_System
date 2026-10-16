from datetime import datetime, timedelta, timezone
import inspect
import logging
import re
from typing import Any, List, Optional, Tuple

from pymongo.errors import PyMongoError

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, get_database
from app.models.roles import UserRole
from app.schemas.authority import AuthorityResult
from app.schemas.civic_intelligence import CaseIntelligenceResponse
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import ComplaintCase
from app.schemas.geospatial import (
    CivicEntityItem,
    GeoSourceStatus,
    GeospatialContextResponse,
    JurisdictionContext,
    LocationMatchQuality,
    NearbyCaseItem,
    NearbyCasesSummary,
    NearbyCivicContext,
    NormalizedLocation,
    RoadIdentification,
    RoadSegmentContext,
    SpatialRelationship,
)
from app.services.authority import resolve_authority_for_location
from app.services.civic_intelligence import get_case_intelligence
import app.services.complaint_case as complaint_case_module
from app.services.external_civic_data import external_civic_service
from app.services.geocoding_provider import geocoding_service
from app.services.spatial import (
    bearing_to_compass_direction,
    bounding_box_for_radius,
    calculate_bearing_degrees,
    haversine_distance_meters,
    validate_accuracy,
    validate_coordinates,
)

logger = logging.getLogger("cvki.services.geospatial_intelligence")

FINAL_STATUSES = {"resolved", "closed"}


def _normalized_text(val: Optional[str]) -> str:
    cleaned = re.sub(r"[^\w\s]", "", (val or "").casefold())
    return " ".join(cleaned.split())


def classify_spatial_relationships(
    target_lat: float,
    target_lon: float,
    target_road: Optional[str],
    target_category: Optional[str],
    case_lat: float,
    case_lon: float,
    case_road: Optional[str],
    case_category: Optional[str],
    distance_m: float,
    case_created_at: datetime,
    now: datetime,
) -> list[SpatialRelationship]:
    """
    Classifies analytical relationships between target point and a case.
    Maintains clear distinction: duplicate vs recurrence vs nearby context.
    """
    relationships: list[SpatialRelationship] = [SpatialRelationship.NEARBY]

    if distance_m <= 25.0:
        relationships.append(SpatialRelationship.SAME_LOCATION)

    norm_target_road = _normalized_text(target_road)
    norm_case_road = _normalized_text(case_road)
    if norm_target_road and norm_case_road and norm_target_road == norm_case_road:
        relationships.append(SpatialRelationship.SAME_ROAD)

    is_same_category = bool(target_category and case_category and target_category.lower() == case_category.lower())
    if is_same_category:
        relationships.append(SpatialRelationship.SAME_CATEGORY)

    # Recurrence candidate check (M5.2 rule: within 250m, same category, separated by duplicate window)
    case_time = case_created_at if case_created_at.tzinfo is not None else case_created_at.replace(tzinfo=timezone.utc)
    current_time = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    age_hours = (current_time - case_time).total_seconds() / 3600.0

    if (
        is_same_category
        and distance_m <= 250.0
        and age_hours >= settings.DUPLICATE_TIME_WINDOW_HOURS
        and age_hours <= (settings.RECURRENCE_WINDOW_DAYS * 24.0)
    ):
        relationships.append(SpatialRelationship.RECURRENCE_CANDIDATE)

    # Hotspot context check (concentration within hotspot window)
    if (
        norm_target_road
        and norm_case_road
        and norm_target_road == norm_case_road
        and age_hours <= (settings.HOTSPOT_WINDOW_DAYS * 24.0)
    ):
        relationships.append(SpatialRelationship.HOTSPOT_CONTEXT)

    return relationships


async def find_nearby_cases(
    latitude: float,
    longitude: float,
    radius_meters: float = 250.0,
    time_window_days: int = 30,
    issue_category: Optional[str] = None,
    unresolved_only: bool = False,
    target_road: Optional[str] = None,
    actor_role: str = "citizen",
    max_results: Optional[int] = None,
) -> NearbyCasesSummary:
    """
    Searches stored complaint cases around coordinates using bounding-box prefilter
    and precise Haversine distance calculations.
    Enforces RBAC/Privacy: strips citizen PII from returned summaries.
    """
    lat, lon = validate_coordinates(latitude, longitude, allow_null_island=True)
    safe_radius = max(10.0, min(float(radius_meters), settings.GEO_SEARCH_MAX_RADIUS_METERS))
    safe_days = max(1, min(int(time_window_days), 365))
    limit = min(max_results or settings.GEO_MAX_NEARBY_CASES, settings.GEO_MAX_NEARBY_CASES)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=safe_days)

    min_lat, min_lon, max_lat, max_lon = bounding_box_for_radius(lat, lon, safe_radius)
    try:
        candidate_cases = await complaint_case_module.case_repository.find_nearby_candidates(
            min_lat=min_lat,
            min_lon=min_lon,
            max_lat=max_lat,
            max_lon=max_lon,
            cutoff=cutoff,
            issue_category=issue_category,
            unresolved_only=unresolved_only,
            limit=limit * 2,
        )
    except Exception as exc:
        logger.warning("Error querying nearby candidates: %s", exc)
        candidate_cases = []

    items: list[NearbyCaseItem] = []
    category_counts: dict[str, int] = {}
    unresolved_count = 0
    recurrence_count = 0
    hotspot_candidate_count = 0

    for c in candidate_cases:
        loc = c.location
        c_lat = loc.latitude
        c_lon = loc.longitude
        if c_lat is None or c_lon is None:
            continue

        try:
            dist_m = haversine_distance_meters(lat, lon, float(c_lat), float(c_lon))
        except Exception:
            continue

        if dist_m > safe_radius:
            continue

        c_time = c.created_at if c.created_at.tzinfo is not None else c.created_at.replace(tzinfo=timezone.utc)
        c_class = c.issue.class_name
        c_label = c.issue.label
        c_prio = c.priority_analysis.priority_level if c.priority_analysis else None
        c_status = c.status

        category_counts[c_class] = category_counts.get(c_class, 0) + 1
        if c_status not in FINAL_STATUSES:
            unresolved_count += 1

        bearing = calculate_bearing_degrees(lat, lon, float(c_lat), float(c_lon))
        direction = bearing_to_compass_direction(bearing)

        relationships = classify_spatial_relationships(
            target_lat=lat,
            target_lon=lon,
            target_road=target_road,
            target_category=issue_category,
            case_lat=float(c_lat),
            case_lon=float(c_lon),
            case_road=loc.road,
            case_category=c_class,
            distance_m=dist_m,
            case_created_at=c_time,
            now=now,
        )

        if SpatialRelationship.RECURRENCE_CANDIDATE in relationships:
            recurrence_count += 1
        if SpatialRelationship.HOTSPOT_CONTEXT in relationships:
            hotspot_candidate_count += 1

        ref_id = c.reference_id
        # Protect privacy: for citizen views, anonymize or mask reference_id suffix
        if actor_role == UserRole.CITIZEN.value:
            masked_ref = f"{ref_id[:13]}-***" if len(ref_id) > 13 else "CVKI-CASE"
        else:
            masked_ref = ref_id

        items.append(
            NearbyCaseItem(
                reference_id=masked_ref,
                issue_class=c_class,
                issue_label=c_label,
                priority=c_prio,
                status=c_status,
                distance_meters=round(dist_m, 1),
                direction=direction,
                road=loc.road,
                city=loc.city,
                spatial_relationships=relationships,
                created_at=c_time,
            )
        )

    # Sort items by distance ascending
    items.sort(key=lambda item: item.distance_meters)
    items = items[:limit]

    explanation = (
        f"Found {len(items)} persisted case(s) within {safe_radius:.0f}m in the last {safe_days} days "
        f"({unresolved_count} unresolved). Proximity does not establish physical identity."
    )

    return NearbyCasesSummary(
        count=len(items),
        unresolved_count=unresolved_count,
        radius_meters=safe_radius,
        time_window_days=safe_days,
        categories=category_counts,
        cases=items,
        recurrence_count=recurrence_count,
        hotspot_candidate=hotspot_candidate_count >= settings.HOTSPOT_MIN_CASES,
        explanation=explanation,
    )


async def get_geospatial_intelligence_context(
    latitude: float,
    longitude: float,
    accuracy_m: Optional[float] = None,
    issue_category: Optional[str] = None,
    radius_meters: float = 250.0,
    time_window_days: int = 30,
    actor_role: str = "citizen",
) -> GeospatialContextResponse:
    """
    Builds the complete M6.2 Geospatial Civic Intelligence pipeline:
    Coordinates
    -> normalized location
    -> road identification
    -> road segment context
    -> jurisdiction
    -> nearby civic context
    -> nearby civic cases (from MongoDB)
    -> spatial relationships
    -> M6.1 authority intelligence
    """
    lat, lon = validate_coordinates(latitude, longitude, allow_null_island=True)
    acc = validate_accuracy(accuracy_m)

    norm_loc, road_id, segment_ctx, source_status = geocoding_service.resolve(
        lat, lon, accuracy_m=acc
    )

    # Build Jurisdiction Context
    jurisdiction_name = (
        norm_loc.district
        or norm_loc.city
        or norm_loc.area
        or norm_loc.state
        or norm_loc.country
    )
    jurisdiction = (
        JurisdictionContext(
            level="administrative_context",
            name=jurisdiction_name,
            source=norm_loc.geocoding_source,
            confidence=norm_loc.match_quality.value,
        )
        if jurisdiction_name
        else None
    )

    # Build Nearby Cases Summary
    nearby_cases = await find_nearby_cases(
        latitude=lat,
        longitude=lon,
        radius_meters=radius_meters,
        time_window_days=time_window_days,
        issue_category=issue_category,
        target_road=norm_loc.road,
        actor_role=actor_role,
    )

    # Build Nearby Civic Context (Infrastructure POIs)
    # Evidence-based: CVKI does not invent POIs; set to unavailable if external GIS layers not connected
    nearby_civic = NearbyCivicContext(
        drainage_waterlogging_zones=[],
        bridges_flyovers=[],
        traffic_infrastructure=[],
        intersections=[],
        public_facilities=[],
        source_status="unavailable",
        source_notes="External civic GIS POI layers are unavailable; CVKI does not fabricate unverified POI data.",
    )

    # Resolve Authority using M6.1 Authority Intelligence
    complaint_loc = ComplaintLocation(
        road=norm_loc.road,
        area=norm_loc.area,
        city=norm_loc.city,
        district=norm_loc.district,
        state=norm_loc.state,
        latitude=lat,
        longitude=lon,
        accuracy_m=acc,
        postal_code=norm_loc.postal_code,
    )
    authority_res: AuthorityResult = resolve_authority_for_location(complaint_loc)

    authority_preview = {
        "road_owner": authority_res.road_owner.model_dump(mode="python") if authority_res.road_owner else None,
        "maintenance_authority": authority_res.maintenance_authority.model_dump(mode="python") if authority_res.maintenance_authority else None,
        "authority_status": authority_res.authority_status,
        "resolution_message": authority_res.resolution_message,
        "source_count": len(authority_res.sources),
        "evidence_count": len(authority_res.evidence),
    }

    # Aggregate spatial relationships
    overall_relationships: list[SpatialRelationship] = []
    if nearby_cases.count > 0:
        overall_relationships.append(SpatialRelationship.NEARBY)
        if any(SpatialRelationship.SAME_LOCATION in c.spatial_relationships for c in nearby_cases.cases):
            overall_relationships.append(SpatialRelationship.SAME_LOCATION)
        if any(SpatialRelationship.SAME_ROAD in c.spatial_relationships for c in nearby_cases.cases):
            overall_relationships.append(SpatialRelationship.SAME_ROAD)
        if any(SpatialRelationship.SAME_CATEGORY in c.spatial_relationships for c in nearby_cases.cases):
            overall_relationships.append(SpatialRelationship.SAME_CATEGORY)
        if nearby_cases.recurrence_count > 0:
            overall_relationships.append(SpatialRelationship.RECURRENCE_CANDIDATE)
        if nearby_cases.hotspot_candidate:
            overall_relationships.append(SpatialRelationship.HOTSPOT_CONTEXT)

    limitations = [
        "Geospatial proximity indicates spatial clustering and does not prove that reports share a common physical defect.",
        "Road identification reflects reverse geocoding from available map data; exact vector segment attribution requires authoritative municipal GIS layers.",
        "Authority assignment reflects deterministic matching against official registries; proximity alone does not override jurisdictional boundaries.",
    ]

    # Fetch M6.3 External Civic / Environmental Context
    external_context = None
    try:
        external_context = external_civic_service.get_external_civic_context(
            latitude=lat,
            longitude=lon,
            timestamp=norm_loc.timestamp,
            issue_category=issue_category,
        )
    except Exception as exc:
        logger.warning("Failed to retrieve external civic context (%s); continuing.", exc)

    return GeospatialContextResponse(
        location=norm_loc,
        road=road_id,
        road_segment=segment_ctx,
        jurisdiction=jurisdiction,
        authority_preview=authority_preview,
        nearby_cases=nearby_cases,
        nearby_civic_context=nearby_civic,
        spatial_relationships=overall_relationships,
        location_match=norm_loc.match_quality,
        source_status=source_status,
        external_context=external_context,
        limitations=limitations,
    )


async def get_case_geospatial_context(
    reference_id: str,
    actor_user_id: str,
    actor_role: str,
    radius_meters: float = 250.0,
    time_window_days: int = 30,
) -> GeospatialContextResponse:
    """
    Fetches geospatial intelligence context specifically for an existing persisted case.
    Reuses M5.2 case intelligence and enforces role permissions.
    """
    case_or_coro = complaint_case_module.case_repository.get(reference_id)
    case = await case_or_coro if inspect.isawaitable(case_or_coro) else case_or_coro
    if case is None:
        raise complaint_case_module.ComplaintCaseNotFoundError(reference_id)

    # Authority role check: Authorities can only view cases assigned to them
    if actor_role == UserRole.AUTHORITY.value:
        assigned_user_id = case.assignment.assigned_to_user_id if case.assignment else None
        if assigned_user_id != actor_user_id:
            raise PermissionError("Authorities can only view geospatial intelligence for cases assigned to them.")

    loc = case.location
    if loc.latitude is None or loc.longitude is None:
        # Case has no coordinates: return unavailable location
        now = datetime.now(timezone.utc)
        return GeospatialContextResponse(
            location=NormalizedLocation(
                latitude=0.0,
                longitude=0.0,
                timestamp=now,
                road=loc.road,
                area=loc.area,
                city=loc.city,
                district=loc.district,
                state=loc.state,
                geocoding_source="unavailable",
                match_quality=LocationMatchQuality.UNAVAILABLE,
            ),
            road=RoadIdentification(
                road_name=loc.road,
                source="case_record",
                match_quality=LocationMatchQuality.UNAVAILABLE,
            ),
            road_segment=RoadSegmentContext(
                road_name=loc.road,
                source="case_record",
                matching_quality=LocationMatchQuality.UNAVAILABLE,
            ),
            jurisdiction=None,
            nearby_cases=NearbyCasesSummary(
                count=0,
                unresolved_count=0,
                radius_meters=radius_meters,
                time_window_days=time_window_days,
                explanation="Coordinates missing on case; nearby spatial search unavailable.",
            ),
            nearby_civic_context=NearbyCivicContext(),
            spatial_relationships=[],
            location_match=LocationMatchQuality.UNAVAILABLE,
            source_status=GeoSourceStatus.UNAVAILABLE,
            limitations=["Case contains no GPS coordinates; spatial intelligence cannot be calculated."],
        )

    return await get_geospatial_intelligence_context(
        latitude=loc.latitude,
        longitude=loc.longitude,
        accuracy_m=loc.accuracy_m,
        issue_category=case.issue.class_name,
        radius_meters=radius_meters,
        time_window_days=time_window_days,
        actor_role=actor_role,
    )
