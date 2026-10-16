from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExternalDataStatus(str, Enum):
    LIVE = "live"
    CACHED_FRESH = "cached_fresh"
    CACHED_STALE = "cached_stale"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    ERROR = "error"


class ExternalCategory(str, Enum):
    WEATHER = "weather"
    RAINFALL = "rainfall"
    TEMPERATURE = "temperature"
    TRAFFIC = "traffic"
    CIVIC_INFRASTRUCTURE = "civic_infrastructure"


class WeatherContext(BaseModel):
    temperature_c: Optional[float] = None
    precipitation_mm: Optional[float] = None
    humidity_percent: Optional[float] = None
    wind_speed_mps: Optional[float] = None
    condition: Optional[str] = None
    weather_code: Optional[int] = None
    observation_time: Optional[datetime] = None
    source: str
    status: ExternalDataStatus = ExternalDataStatus.UNAVAILABLE
    freshness: str = "unknown"  # fresh, stale, live, unavailable


class RainfallContext(BaseModel):
    rainfall_mm: Optional[float] = None
    window_hours: int = 24
    intensity: str = "none"  # none, light, moderate, heavy, very_heavy, unknown
    correlation_note: Optional[str] = None
    observation_time: Optional[datetime] = None
    source: str
    status: ExternalDataStatus = ExternalDataStatus.UNAVAILABLE
    freshness: str = "unknown"


class TrafficContext(BaseModel):
    road_name: Optional[str] = None
    traffic_condition: Optional[str] = None
    congestion_level: Optional[str] = None
    incident_reported: Optional[bool] = None
    source: str
    status: ExternalDataStatus = ExternalDataStatus.NOT_CONFIGURED
    freshness: str = "unknown"


class EnvironmentalCorrelation(BaseModel):
    issue_category: Optional[str] = None
    correlation_observed: bool = False
    correlation_summary: str
    causal_disclaimer: str = (
        "External environmental correlation is contextual and does not establish that rainfall caused the reported civic defect."
    )


class ExternalCivicContextResponse(BaseModel):
    status: str = "unavailable"  # success, partial, unavailable, not_configured
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    query_latitude: float
    query_longitude: float
    weather: Optional[WeatherContext] = None
    rainfall: Optional[RainfallContext] = None
    traffic: Optional[TrafficContext] = None
    environmental_correlation: Optional[EnvironmentalCorrelation] = None
    limitations: list[str] = Field(default_factory=list)
