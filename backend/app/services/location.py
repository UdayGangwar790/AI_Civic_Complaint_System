import json
import logging
from dataclasses import dataclass, replace
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings

logger = logging.getLogger("cvki.services.location")


class LocationProviderError(Exception):
    """Base error for safe reverse-geocoding failures."""


class LocationProviderTimeout(LocationProviderError):
    """The reverse-geocoding provider did not respond in time."""


class LocationProviderRateLimited(LocationProviderError):
    """The provider rejected the request due to rate limiting."""


@dataclass(frozen=True)
class ReverseGeocodingResult:
    display_name: str | None = None
    road: str | None = None
    area: str | None = None
    city: str | None = None
    district: str | None = None
    municipality: str | None = None
    state: str | None = None
    country: str | None = None
    source: str = "OpenStreetMap Nominatim"
    jurisdiction: dict[str, str | None] | None = None
    resolution_status: str = "unresolved"
    message: str | None = None


class NominatimReverseGeocoder:
    """OpenStreetMap Nominatim adapter kept behind a replaceable interface."""

    def reverse_geocode(self, latitude: float, longitude: float) -> ReverseGeocodingResult:
        query = urlencode({
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
        })
        request = Request(
            f"{settings.REVERSE_GEOCODER_URL}?{query}",
            headers={"User-Agent": settings.REVERSE_GEOCODER_USER_AGENT},
        )
        try:
            with urlopen(request, timeout=settings.REVERSE_GEOCODER_TIMEOUT_SECONDS) as response:
                if response.status == 429:
                    raise LocationProviderRateLimited
                response_body = response.read(1_000_001)
                if len(response_body) > 1_000_000:
                    raise LocationProviderError
                payload = json.loads(response_body.decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429:
                raise LocationProviderRateLimited from exc
            logger.warning("Reverse geocoder request failed (status=%s).", exc.code)
            raise LocationProviderError from exc
        except TimeoutError as exc:
            logger.warning("Reverse geocoder request timed out.")
            raise LocationProviderTimeout from exc
        except (URLError, ValueError, OSError) as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                logger.warning("Reverse geocoder request timed out.")
                raise LocationProviderTimeout from exc
            logger.warning("Reverse geocoder request failed (error_type=%s).", type(exc).__name__)
            raise LocationProviderError from exc

        if not isinstance(payload, dict):
            raise LocationProviderError
        address = payload.get("address") or {}
        if not isinstance(address, dict):
            raise LocationProviderError
        return ReverseGeocodingResult(
            display_name=payload.get("display_name"),
            road=address.get("road"),
            area=address.get("suburb") or address.get("neighbourhood") or address.get("village"),
            city=address.get("city") or address.get("town") or address.get("municipality"),
            district=address.get("district") or address.get("county"),
            municipality=address.get("municipality"),
            state=address.get("state"),
            country=address.get("country"),
        )


reverse_geocoder = NominatimReverseGeocoder()


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")
    return latitude, longitude


def reverse_geocode(latitude: float, longitude: float) -> ReverseGeocodingResult:
    validate_coordinates(latitude, longitude)
    result = reverse_geocoder.reverse_geocode(latitude, longitude)
    has_road = bool(result.road)
    has_context = any((result.area, result.city, result.district, result.municipality, result.state, result.country))
    if has_road and has_context:
        resolution_status = "resolved"
    elif has_road or has_context:
        resolution_status = "partial"
    else:
        resolution_status = "unresolved"

    jurisdiction_name = result.municipality or result.city or result.district or result.state or result.country
    jurisdiction = None
    if jurisdiction_name:
        jurisdiction = {
            "level": "administrative_context",
            "name": jurisdiction_name,
            "source": result.source,
            "confidence": None,
        }
    message = None if has_road else "Road information could not be resolved for these coordinates."
    return replace(
        result,
        jurisdiction=jurisdiction,
        resolution_status=resolution_status,
        message=message,
    )


def get_location_details(lat: float, lon: float) -> ReverseGeocodingResult:
    return reverse_geocode(lat, lon)