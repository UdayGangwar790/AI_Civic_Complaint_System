from pydantic import BaseModel, Field


class JurisdictionContext(BaseModel):
    level: str
    name: str
    source: str
    confidence: str | None = None


class LocationResponse(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    display_name: str | None = None
    road: str | None = None
    area: str | None = None
    city: str | None = None
    district: str | None = None
    municipality: str | None = None
    state: str | None = None
    country: str | None = None
    jurisdiction: JurisdictionContext | None = None
    source: str | None = None
    resolution_status: str
    message: str | None = None
    road_type: str | None = None
    road_reference: str | None = None
    match_quality: str | None = None
    source_status: str | None = None
    accuracy_m: float | None = None
    postal_code: str | None = None
