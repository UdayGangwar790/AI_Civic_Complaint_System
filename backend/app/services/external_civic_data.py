from datetime import datetime, timezone
import logging
from typing import Optional, Tuple

from app.core.config import settings
from app.schemas.external_civic import (
    EnvironmentalCorrelation,
    ExternalCivicContextResponse,
    ExternalDataStatus,
    RainfallContext,
    TrafficContext,
    WeatherContext,
)
from app.services.external_civic_cache import (
    ExternalCivicCache,
    build_external_civic_cache_key,
    default_external_civic_cache,
)
from app.services.external_civic_provider import (
    ExternalCivicDataProvider,
    OpenDataCivicProvider,
    OpenMeteoWeatherProvider,
    TomTomTrafficProvider,
    classify_rainfall_intensity,
)
from app.services.spatial import CoordinateValidationError, validate_coordinates

logger = logging.getLogger("cvki.services.external_civic_data")


class ExternalCivicDataService:
    """
    Composite service coordinating external civic, meteorological, and traffic data providers.
    Enforces caching (live -> cached_fresh -> cached_stale -> unavailable),
    strict non-causal environmental correlation, and resilient failure isolation.
    """

    def __init__(
        self,
        cache: Optional[ExternalCivicCache] = None,
        weather_provider: Optional[ExternalCivicDataProvider] = None,
        traffic_provider: Optional[ExternalCivicDataProvider] = None,
        civic_provider: Optional[ExternalCivicDataProvider] = None,
    ):
        self._cache = cache or default_external_civic_cache
        self._weather_provider = weather_provider or OpenMeteoWeatherProvider()
        self._traffic_provider = traffic_provider or TomTomTrafficProvider()
        self._civic_provider = civic_provider or OpenDataCivicProvider()

    def get_weather_and_rainfall(
        self,
        latitude: float,
        longitude: float,
        window_hours: int = 24,
        timestamp: Optional[datetime] = None,
    ) -> Tuple[WeatherContext, RainfallContext]:
        """
        Retrieves weather and rainfall context with two-tier caching and degraded fallback.
        """
        provider = self._weather_provider
        cache_key = build_external_civic_cache_key(
            provider=provider.name,
            category="weather_rainfall",
            latitude=latitude,
            longitude=longitude,
            window_hours=window_hours,
        )

        now = datetime.now(timezone.utc)
        cached_entry = self._cache.get(cache_key)

        # 1. Fresh Cache Hit
        if cached_entry and cached_entry.is_fresh(now):
            data = cached_entry.data
            intensity = classify_rainfall_intensity(data.get("window_rainfall_mm"))
            return (
                WeatherContext(
                    temperature_c=data.get("temperature_c"),
                    precipitation_mm=data.get("precipitation_mm"),
                    humidity_percent=data.get("humidity_percent"),
                    wind_speed_mps=data.get("wind_speed_mps"),
                    condition=data.get("condition"),
                    weather_code=data.get("weather_code"),
                    observation_time=cached_entry.retrieved_at,
                    source=f"{provider.name} (Cached)",
                    status=ExternalDataStatus.CACHED_FRESH,
                    freshness="fresh",
                ),
                RainfallContext(
                    rainfall_mm=data.get("window_rainfall_mm"),
                    window_hours=window_hours,
                    intensity=intensity,
                    correlation_note=data.get("correlation_note"),
                    observation_time=cached_entry.retrieved_at,
                    source=f"{provider.name} (Cached)",
                    status=ExternalDataStatus.CACHED_FRESH,
                    freshness="fresh",
                ),
            )

        # 2. Live Provider Call
        result = provider.fetch(
            latitude=latitude,
            longitude=longitude,
            window_hours=window_hours,
            timestamp=timestamp,
        )

        if result.status == ExternalDataStatus.LIVE and result.data:
            data = result.data
            # Write to cache
            self._cache.set(
                cache_key=cache_key,
                provider=provider.name,
                category="weather_rainfall",
                query_lat=latitude,
                query_lon=longitude,
                window_hours=window_hours,
                data=data,
                source=result.source,
                status=ExternalDataStatus.LIVE.value,
            )
            intensity = classify_rainfall_intensity(data.get("window_rainfall_mm"))
            return (
                WeatherContext(
                    temperature_c=data.get("temperature_c"),
                    precipitation_mm=data.get("precipitation_mm"),
                    humidity_percent=data.get("humidity_percent"),
                    wind_speed_mps=data.get("wind_speed_mps"),
                    condition=data.get("condition"),
                    weather_code=data.get("weather_code"),
                    observation_time=result.observation_time or now,
                    source=result.source,
                    status=ExternalDataStatus.LIVE,
                    freshness="live",
                ),
                RainfallContext(
                    rainfall_mm=data.get("window_rainfall_mm"),
                    window_hours=window_hours,
                    intensity=intensity,
                    correlation_note=data.get("correlation_note"),
                    observation_time=result.observation_time or now,
                    source=result.source,
                    status=ExternalDataStatus.LIVE,
                    freshness="live",
                ),
            )

        # 3. Live Call Failed -> Check Stale Cache
        if cached_entry and not cached_entry.is_expired(now):
            logger.info("Live weather provider failed (%s); using stale cached entry.", result.status)
            data = cached_entry.data
            intensity = classify_rainfall_intensity(data.get("window_rainfall_mm"))
            return (
                WeatherContext(
                    temperature_c=data.get("temperature_c"),
                    precipitation_mm=data.get("precipitation_mm"),
                    humidity_percent=data.get("humidity_percent"),
                    wind_speed_mps=data.get("wind_speed_mps"),
                    condition=data.get("condition"),
                    weather_code=data.get("weather_code"),
                    observation_time=cached_entry.retrieved_at,
                    source=f"{provider.name} (Stale Cache)",
                    status=ExternalDataStatus.CACHED_STALE,
                    freshness="stale",
                ),
                RainfallContext(
                    rainfall_mm=data.get("window_rainfall_mm"),
                    window_hours=window_hours,
                    intensity=intensity,
                    correlation_note=data.get("correlation_note"),
                    observation_time=cached_entry.retrieved_at,
                    source=f"{provider.name} (Stale Cache)",
                    status=ExternalDataStatus.CACHED_STALE,
                    freshness="stale",
                ),
            )

        # 4. No Cache Available -> Return Provider Failure Status
        return (
            WeatherContext(
                source=result.source,
                status=result.status,
                freshness="unavailable",
            ),
            RainfallContext(
                window_hours=window_hours,
                intensity="unknown",
                source=result.source,
                status=result.status,
                freshness="unavailable",
            ),
        )

    def get_traffic_context(
        self,
        latitude: float,
        longitude: float,
        timestamp: Optional[datetime] = None,
    ) -> TrafficContext:
        """Retrieves traffic context from configured provider."""
        provider = self._traffic_provider
        if not provider.is_configured():
            return TrafficContext(
                source=provider.name,
                status=ExternalDataStatus.NOT_CONFIGURED,
                freshness="not_configured",
            )

        res = provider.fetch(latitude=latitude, longitude=longitude, timestamp=timestamp)
        if res.status == ExternalDataStatus.LIVE:
            d = res.data
            return TrafficContext(
                road_name=d.get("road_name"),
                traffic_condition=d.get("traffic_condition", "normal"),
                congestion_level=d.get("congestion_level"),
                incident_reported=d.get("incident_reported", False),
                source=res.source,
                status=ExternalDataStatus.LIVE,
                freshness="live",
            )

        return TrafficContext(
            source=res.source,
            status=res.status,
            freshness="unavailable",
        )

    def evaluate_environmental_correlation(
        self,
        issue_category: Optional[str],
        weather: WeatherContext,
        rainfall: RainfallContext,
    ) -> Optional[EnvironmentalCorrelation]:
        """
        Evaluates contextual correlation between environmental observations and civic issues.
        CRITICAL INVARIANT: NEVER claims causation (e.g. "rain caused waterlogging").
        Only states whether observations are consistent with the reported condition.
        """
        if not issue_category:
            return None

        disclaimer = (
            "External environmental correlation is contextual and does not establish that rainfall caused the reported civic defect."
        )

        if issue_category == "road_waterlogging":
            if rainfall.status in {ExternalDataStatus.LIVE, ExternalDataStatus.CACHED_FRESH, ExternalDataStatus.CACHED_STALE}:
                amount = rainfall.rainfall_mm or 0.0
                if amount >= settings.RAIN_LIGHT_THRESHOLD_MM:
                    summary = (
                        f"Weather context consistent with recent rainfall: {amount:.1f} mm recorded in the preceding "
                        f"{rainfall.window_hours}h window (intensity: {rainfall.intensity})."
                    )
                    return EnvironmentalCorrelation(
                        issue_category=issue_category,
                        correlation_observed=True,
                        correlation_summary=summary,
                        causal_disclaimer=disclaimer,
                    )
                else:
                    summary = (
                        f"Low or negligible precipitation ({amount:.1f} mm in {rainfall.window_hours}h) observed; "
                        "waterlogging may indicate internal drainage blockage or standing surface runoff."
                    )
                    return EnvironmentalCorrelation(
                        issue_category=issue_category,
                        correlation_observed=False,
                        correlation_summary=summary,
                        causal_disclaimer=disclaimer,
                    )
            else:
                return EnvironmentalCorrelation(
                    issue_category=issue_category,
                    correlation_observed=False,
                    correlation_summary="Environmental precipitation data is currently unavailable for correlation.",
                    causal_disclaimer=disclaimer,
                )

        if issue_category == "damaged_missing_road_sign":
            wind = weather.wind_speed_mps
            if wind is not None and wind >= 15.0:  # ~54 km/h gust
                return EnvironmentalCorrelation(
                    issue_category=issue_category,
                    correlation_observed=True,
                    correlation_summary=(
                        f"Elevated atmospheric wind speed ({wind:.1f} m/s) observed in local weather context."
                    ),
                    causal_disclaimer="External environmental correlation is contextual and does not establish causation.",
                )

        return None

    def get_external_civic_context(
        self,
        latitude: float,
        longitude: float,
        timestamp: Optional[datetime] = None,
        issue_category: Optional[str] = None,
        window_hours: int = 24,
    ) -> ExternalCivicContextResponse:
        """
        Unified service orchestrator for real-time external civic data.
        Validates spatial bounds, queries relevant providers based on issue category,
        and generates non-causal correlation summaries.
        """
        validate_coordinates(latitude, longitude, allow_null_island=False)

        bounded_window = min(max(1, int(window_hours)), settings.EXTERNAL_DATA_MAX_WINDOW_HOURS)
        now = datetime.now(timezone.utc)

        if not settings.EXTERNAL_DATA_ENABLED:
            return ExternalCivicContextResponse(
                status="not_configured",
                retrieved_at=now,
                query_latitude=latitude,
                query_longitude=longitude,
                limitations=["External civic data intelligence is disabled in platform configuration."],
            )

        # Query weather & rainfall
        weather, rainfall = self.get_weather_and_rainfall(
            latitude=latitude,
            longitude=longitude,
            window_hours=bounded_window,
            timestamp=timestamp,
        )

        # Traffic query: relevant for signs, manholes, or when requested
        traffic = None
        if issue_category in {"damaged_missing_road_sign", "open_damaged_manhole"}:
            traffic = self.get_traffic_context(latitude, longitude, timestamp=timestamp)

        # Environmental correlation
        correlation = self.evaluate_environmental_correlation(
            issue_category=issue_category,
            weather=weather,
            rainfall=rainfall,
        )

        # Determine overall response status
        statuses = [weather.status, rainfall.status]
        if traffic:
            statuses.append(traffic.status)

        if any(s == ExternalDataStatus.LIVE for s in statuses):
            overall_status = "live"
        elif any(s == ExternalDataStatus.CACHED_FRESH for s in statuses):
            overall_status = "cached_fresh"
        elif any(s == ExternalDataStatus.CACHED_STALE for s in statuses):
            overall_status = "cached_stale"
        elif all(s == ExternalDataStatus.NOT_CONFIGURED for s in statuses):
            overall_status = "not_configured"
        else:
            overall_status = "unavailable"

        limitations = [
            "External environmental observations provide contextual background and do not prove incident occurrence or cause.",
            "Meteorological observations reflect regional monitoring stations and may differ from localized micro-conditions.",
        ]
        if weather.status in {ExternalDataStatus.UNAVAILABLE, ExternalDataStatus.TIMEOUT, ExternalDataStatus.ERROR}:
            limitations.append(f"Weather data unavailable from provider (status: {weather.status.value}).")

        return ExternalCivicContextResponse(
            status=overall_status,
            retrieved_at=now,
            query_latitude=latitude,
            query_longitude=longitude,
            weather=weather,
            rainfall=rainfall,
            traffic=traffic,
            environmental_correlation=correlation,
            limitations=limitations,
        )


external_civic_service = ExternalCivicDataService()
