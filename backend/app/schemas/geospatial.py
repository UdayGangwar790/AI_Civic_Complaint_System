from datetime import datetime
from enum import Enum
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field

from app.schemas.external_civic import ExternalCivicContextResponse


class RoadType(str, Enum):
    NATIONAL_HIGHWAY = "national_highway"
    STATE_HIGHWAY = "state_highway"
    MUNICIPAL_ARTERIAL = "municipal_arterial"
    MUNICIPAL_ROAD = "municipal_road"
    RURAL_ROAD = "rural_road"
    EXPRESSWAY = "expressway"
    SERVICE_ROAD = "service_road"
    UNKNOWN = "unknown"


class LocationMatchQuality(str, Enum):
    EXACT = "exact"
    STRONG = "strong"
    APPROXIMATE = "approximate"
    UNAVAILABLE = "unavailable"


class GeoSourceStatus(str, Enum):
    LIVE = "live"
    CACHED = "cached"
    UNAVAILABLE = "unavailable"


class SpatialRelationship(str, Enum):
    SAME_LOCATION = "same_location"
    NEARBY = "nearby"
    SAME_ROAD = "same_road"
    SAME_CATEGORY = "same_category"
    RECURRENCE_CANDIDATE = "recurrence_candidate"
    HOTSPOT_CONTEXT = "hotspot_context"


class NormalizedLocation(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    accuracy_m: Optional[float] = Field(default=None, ge=0.0)
    timestamp: datetime
    formatted_address: Optional[str] = None
    road: Optional[str] = None
    area: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    geocoding_source: str = "OpenStreetMap Nominatim"
    geocoding_timestamp: Optional[datetime] = None
    match_quality: LocationMatchQuality = LocationMatchQuality.APPROXIMATE


class RoadIdentification(BaseModel):
    road_name: Optional[str] = None
    road_type: RoadType = RoadType.UNKNOWN
    road_reference: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    source: str = "OpenStreetMap Nominatim"
    retrieval_time: Optional[datetime] = None
    match_quality: LocationMatchQuality = LocationMatchQuality.APPROXIMATE


class RoadSegmentContext(BaseModel):
    road_identifier: Optional[str] = None
    road_name: Optional[str] = None
    start_end_context: Optional[str] = None
    nearest_point: Optional[dict[str, float]] = None
    distance_to_identified_road_m: Optional[float] = None
    direction_bearing_deg: Optional[float] = None
    source: str = "OpenStreetMap Nominatim"
    matching_method: str = "reverse_geocoding_address"
    matching_quality: LocationMatchQuality = LocationMatchQuality.APPROXIMATE


class CivicEntityItem(BaseModel):
    kind: str
    name: str
    distance_meters: Optional[float] = None
    details: Optional[str] = None


class NearbyCivicContext(BaseModel):
    drainage_waterlogging_zones: list[CivicEntityItem] = Field(default_factory=list)
    bridges_flyovers: list[CivicEntityItem] = Field(default_factory=list)
    traffic_infrastructure: list[CivicEntityItem] = Field(default_factory=list)
    intersections: list[CivicEntityItem] = Field(default_factory=list)
    public_facilities: list[CivicEntityItem] = Field(default_factory=list)
    source_status: Literal["available", "unavailable"] = "unavailable"
    source_notes: str = (
        "External civic POI layers are set to unavailable; CVKI does not fabricate unverified POI data."
    )


class NearbyCaseItem(BaseModel):
    reference_id: str
    issue_class: str
    issue_label: str
    priority: Optional[str] = None
    status: str
    distance_meters: float
    direction: Optional[str] = None
    road: Optional[str] = None
    city: Optional[str] = None
    spatial_relationships: list[SpatialRelationship] = Field(default_factory=list)
    created_at: datetime


class NearbyCasesSummary(BaseModel):
    count: int = 0
    unresolved_count: int = 0
    radius_meters: float
    time_window_days: int
    categories: dict[str, int] = Field(default_factory=dict)
    cases: list[NearbyCaseItem] = Field(default_factory=list)
    recurrence_count: int = 0
    hotspot_candidate: bool = False
    explanation: str


class JurisdictionContext(BaseModel):
    level: str
    name: str
    source: str
    confidence: Optional[str] = None


class GeospatialContextRequest(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    accuracy_m: Optional[float] = Field(default=None, ge=0.0)
    issue_category: Optional[str] = None
    radius_meters: Optional[float] = Field(default=250.0, ge=10.0, le=5000.0)
    time_window_days: Optional[int] = Field(default=30, ge=1, le=365)


class GeospatialContextResponse(BaseModel):
    location: NormalizedLocation
    road: RoadIdentification
    road_segment: RoadSegmentContext
    jurisdiction: Optional[JurisdictionContext] = None
    authority_preview: Optional[dict[str, Any]] = None
    nearby_cases: NearbyCasesSummary
    nearby_civic_context: NearbyCivicContext
    spatial_relationships: list[SpatialRelationship] = Field(default_factory=list)
    location_match: LocationMatchQuality = LocationMatchQuality.APPROXIMATE
    source_status: GeoSourceStatus = GeoSourceStatus.LIVE
    external_context: Optional[ExternalCivicContextResponse] = None
    limitations: list[str] = Field(default_factory=list)
