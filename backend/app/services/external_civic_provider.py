from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import logging
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.schemas.external_civic import (
    ExternalCategory,
    ExternalDataStatus,
    RainfallContext,
    TrafficContext,
    WeatherContext,
)

logger = logging.getLogger("cvki.services.external_civic_provider")


@dataclass
class ProviderFetchResult:
    status: ExternalDataStatus
    data: dict[str, Any]
    source: str
    source_type: str
    observation_time: Optional[datetime] = None
    error_message: Optional[str] = None


def is_ssrf_safe_external_url(url: str | None) -> tuple[bool, str]:
    """
    Validates URL safety against Server-Side Request Forgery (SSRF).
    Blocks private IP addresses, loopback, link-local, cloud metadata (169.254.169.254),
    non-HTTP/HTTPS schemes, and non-standard ports.
    """
    if not url:
        return False, "URL is empty."

    raw = url.strip()
    try:
        parsed = urlparse(raw)
    except Exception:
        return False, "Malformed URL syntax."

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return False, f"URL scheme '{scheme}' is disallowed; only HTTP and HTTPS are permitted."

    hostname = (parsed.hostname or "").lower()
    port = parsed.port

    if not hostname:
        return False, "URL missing valid hostname."

    if port and port not in {80, 443}:
        return False, f"Disallowed destination port {port}."

    # Validate IP addresses
    try:
        ip = ipaddress.ip_address(hostname)
        if str(ip) == "169.254.169.254":
            return False, "Cloud instance metadata service address is forbidden."
        if ip.is_loopback:
            return False, "Loopback IP addresses are forbidden."
        if ip.is_private:
            return False, "Private network IP addresses are forbidden."
        if ip.is_link_local:
            return False, "Link-local IP addresses are forbidden."
        if ip.is_reserved or ip.is_multicast:
            return False, "Reserved or multicast IP addresses are forbidden."
    except ValueError:
        pass

    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        return False, "Localhost domain is forbidden."

    return True, "URL is valid and safe."


WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def classify_rainfall_intensity(rainfall_mm: float | None) -> str:
    """Classifies rainfall amount into standardized intensity tiers."""
    if rainfall_mm is None or rainfall_mm < 0.1:
        return "none"
    if rainfall_mm < settings.RAIN_LIGHT_THRESHOLD_MM:
        return "light"
    if rainfall_mm < settings.RAIN_MODERATE_THRESHOLD_MM:
        return "light"
    if rainfall_mm < settings.RAIN_HEAVY_THRESHOLD_MM:
        return "moderate"
    if rainfall_mm < 65.0:
        return "heavy"
    return "very_heavy"


class ExternalCivicDataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def category(self) -> ExternalCategory:
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        pass

    @abstractmethod
    def fetch(
        self,
        latitude: float,
        longitude: float,
        window_hours: int = 24,
        timestamp: Optional[datetime] = None,
    ) -> ProviderFetchResult:
        pass


class OpenMeteoWeatherProvider(ExternalCivicDataProvider):
    """
    Live open-data weather & precipitation provider using Open-Meteo.
    Requires no API keys, standard WGS-84 coordinates, and bounded HTTP timeouts.
    """

    def __init__(self, endpoint_url: Optional[str] = None):
        self._endpoint_url = endpoint_url or settings.WEATHER_PROVIDER_URL

    @property
    def name(self) -> str:
        return "Open-Meteo Forecast"

    @property
    def category(self) -> ExternalCategory:
        return ExternalCategory.WEATHER

    def is_configured(self) -> bool:
        return bool(self._endpoint_url)

    def fetch(
        self,
        latitude: float,
        longitude: float,
        window_hours: int = 24,
        timestamp: Optional[datetime] = None,
    ) -> ProviderFetchResult:
        if not self.is_configured():
            return ProviderFetchResult(
                status=ExternalDataStatus.NOT_CONFIGURED,
                data={},
                source=self.name,
                source_type="open_weather_api",
                error_message="Weather provider URL is not configured.",
            )

        is_safe, reason = is_ssrf_safe_external_url(self._endpoint_url)
        if not is_safe:
            logger.warning("SSRF check rejected weather provider endpoint '%s': %s", self._endpoint_url, reason)
            return ProviderFetchResult(
                status=ExternalDataStatus.ERROR,
                data={},
                source=self.name,
                source_type="open_weather_api",
                error_message=f"SSRF policy rejection: {reason}",
            )

        past_days = 1 if window_hours <= 24 else min(7, (window_hours // 24) + 1)
        params = {
            "latitude": round(float(latitude), 4),
            "longitude": round(float(longitude), 4),
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m",
            "hourly": "precipitation,rain",
            "past_days": past_days,
            "forecast_days": 1,
            "timezone": "UTC",
        }

        timeout = settings.EXTERNAL_DATA_REQUEST_TIMEOUT_SECONDS

        try:
            with httpx.Client(timeout=timeout) as client:
                res = client.get(self._endpoint_url, params=params)

                if res.status_code == 429:
                    logger.warning("Weather provider rate limited (HTTP 429).")
                    return ProviderFetchResult(
                        status=ExternalDataStatus.RATE_LIMITED,
                        data={},
                        source=self.name,
                        source_type="open_weather_api",
                        error_message="Upstream weather API rate limit exceeded.",
                    )

                if res.status_code >= 500:
                    logger.warning("Weather provider server error (HTTP %d).", res.status_code)
                    return ProviderFetchResult(
                        status=ExternalDataStatus.UNAVAILABLE,
                        data={},
                        source=self.name,
                        source_type="open_weather_api",
                        error_message=f"Weather provider error (HTTP {res.status_code}).",
                    )

                res.raise_for_status()
                payload = res.json()

        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException) as exc:
            logger.warning("Weather provider timed out after %.1fs (%s).", timeout, exc)
            return ProviderFetchResult(
                status=ExternalDataStatus.TIMEOUT,
                data={},
                source=self.name,
                source_type="open_weather_api",
                error_message="Weather provider connection timed out.",
            )
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            logger.warning("Weather provider network connection failed (%s).", exc)
            return ProviderFetchResult(
                status=ExternalDataStatus.UNAVAILABLE,
                data={},
                source=self.name,
                source_type="open_weather_api",
                error_message=f"Weather network error: {exc}",
            )
        except Exception as exc:
            logger.warning("Weather provider unexpected error (%s).", exc)
            return ProviderFetchResult(
                status=ExternalDataStatus.ERROR,
                data={},
                source=self.name,
                source_type="open_weather_api",
                error_message=f"Weather provider processing error: {exc}",
            )

        # Parse normalized payload
        current = payload.get("current", {})
        hourly = payload.get("hourly", {})

        weather_code = current.get("weather_code")
        condition_name = WMO_WEATHER_CODES.get(weather_code, "Unknown weather") if weather_code is not None else None

        # Calculate window precipitation from hourly records
        precipitation_series = hourly.get("precipitation", [])
        if precipitation_series and isinstance(precipitation_series, list):
            # Take last window_hours records
            recent_precip = precipitation_series[-window_hours:] if len(precipitation_series) >= window_hours else precipitation_series
            window_rainfall_mm = round(sum(p for p in recent_precip if isinstance(p, (int, float))), 2)
        else:
            window_rainfall_mm = current.get("precipitation")

        obs_time_str = current.get("time")
        obs_time = None
        if obs_time_str:
            try:
                obs_time = datetime.fromisoformat(obs_time_str).replace(tzinfo=timezone.utc)
            except Exception:
                obs_time = datetime.now(timezone.utc)
        else:
            obs_time = datetime.now(timezone.utc)

        data = {
            "temperature_c": current.get("temperature_2m"),
            "precipitation_mm": current.get("precipitation"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_mps": current.get("wind_speed_10m"),
            "weather_code": weather_code,
            "condition": condition_name,
            "window_rainfall_mm": window_rainfall_mm,
            "window_hours": window_hours,
        }

        return ProviderFetchResult(
            status=ExternalDataStatus.LIVE,
            data=data,
            source=self.name,
            source_type="open_weather_api",
            observation_time=obs_time,
        )


class TomTomTrafficProvider(ExternalCivicDataProvider):
    """
    Traffic & road condition provider interface.
    Safely reports NOT_CONFIGURED when credentials are missing.
    """

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None):
        self._endpoint_url = endpoint_url or settings.TRAFFIC_PROVIDER_URL
        self._api_key = api_key or settings.TRAFFIC_API_KEY

    @property
    def name(self) -> str:
        return "TomTom Traffic"

    @property
    def category(self) -> ExternalCategory:
        return ExternalCategory.TRAFFIC

    def is_configured(self) -> bool:
        return bool(self._endpoint_url and self._api_key)

    def fetch(
        self,
        latitude: float,
        longitude: float,
        window_hours: int = 24,
        timestamp: Optional[datetime] = None,
    ) -> ProviderFetchResult:
        if not self.is_configured():
            return ProviderFetchResult(
                status=ExternalDataStatus.NOT_CONFIGURED,
                data={},
                source=self.name,
                source_type="traffic_service",
                error_message="Traffic provider credentials or endpoint are not configured.",
            )

        is_safe, reason = is_ssrf_safe_external_url(self._endpoint_url)
        if not is_safe:
            return ProviderFetchResult(
                status=ExternalDataStatus.ERROR,
                data={},
                source=self.name,
                source_type="traffic_service",
                error_message=f"SSRF policy rejection: {reason}",
            )

        # When configured, executes HTTP request
        try:
            with httpx.Client(timeout=settings.EXTERNAL_DATA_REQUEST_TIMEOUT_SECONDS) as client:
                res = client.get(
                    self._endpoint_url,
                    params={
                        "point": f"{latitude},{longitude}",
                        "key": self._api_key,
                    },
                )
                if res.status_code == 429:
                    return ProviderFetchResult(
                        status=ExternalDataStatus.RATE_LIMITED,
                        data={},
                        source=self.name,
                        source_type="traffic_service",
                        error_message="Traffic provider rate limit exceeded.",
                    )
                res.raise_for_status()
                payload = res.json()
                return ProviderFetchResult(
                    status=ExternalDataStatus.LIVE,
                    data=payload,
                    source=self.name,
                    source_type="traffic_service",
                    observation_time=datetime.now(timezone.utc),
                )
        except (httpx.TimeoutException, httpx.ConnectTimeout):
            return ProviderFetchResult(
                status=ExternalDataStatus.TIMEOUT,
                data={},
                source=self.name,
                source_type="traffic_service",
                error_message="Traffic provider timed out.",
            )
        except Exception as exc:
            return ProviderFetchResult(
                status=ExternalDataStatus.UNAVAILABLE,
                data={},
                source=self.name,
                source_type="traffic_service",
                error_message=f"Traffic provider unavailable: {exc}",
            )


class OpenDataCivicProvider(ExternalCivicDataProvider):
    """
    Extensible open-data municipal/civic provider.
    Reports NOT_CONFIGURED when no municipal portal is designated.
    """

    def __init__(self, endpoint_url: Optional[str] = None):
        self._endpoint_url = endpoint_url

    @property
    def name(self) -> str:
        return "Municipal Open Data Portal"

    @property
    def category(self) -> ExternalCategory:
        return ExternalCategory.CIVIC_INFRASTRUCTURE

    def is_configured(self) -> bool:
        return bool(self._endpoint_url)

    def fetch(
        self,
        latitude: float,
        longitude: float,
        window_hours: int = 24,
        timestamp: Optional[datetime] = None,
    ) -> ProviderFetchResult:
        if not self.is_configured():
            return ProviderFetchResult(
                status=ExternalDataStatus.NOT_CONFIGURED,
                data={},
                source=self.name,
                source_type="municipal_open_data",
                error_message="Municipal open data provider endpoint is not configured.",
            )
        return ProviderFetchResult(
            status=ExternalDataStatus.UNAVAILABLE,
            data={},
            source=self.name,
            source_type="municipal_open_data",
            error_message="Municipal open data provider endpoint is currently offline.",
        )
