from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings
from app.schemas.geospatial import (
    GeoSourceStatus,
    LocationMatchQuality,
    NormalizedLocation,
    RoadIdentification,
    RoadSegmentContext,
    RoadType,
)
from app.services.geo_cache import (
    build_geo_cache_key,
    get_geo_cache,
)
from app.services.spatial import (
    validate_accuracy,
    validate_coordinates,
)

logger = logging.getLogger("cvki.services.geocoding_provider")


class GeocodingError(Exception):
    """Base error for geocoding failures."""


class GeocodingTimeout(GeocodingError):
    """Geocoding provider timed out."""


class GeocodingRateLimited(GeocodingError):
    """Geocoding provider rate limited."""


@dataclass(frozen=True)
class RawGeocodingResponse:
    display_name: Optional[str] = None
    road: Optional[str] = None
    area: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    municipality: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    source: str = "OpenStreetMap Nominatim"
    osm_type: Optional[str] = None
    osm_class: Optional[str] = None
    road_ref: Optional[str] = None
    raw_payload: Optional[dict[str, Any]] = None


def extract_road_type_and_ref(
    road_name: Optional[str],
    osm_class: Optional[str],
    osm_type: Optional[str],
    raw_address: Optional[dict[str, Any]] = None,
) -> Tuple[RoadType, Optional[str]]:
    """
    Classifies road type strictly based on source evidence:
    - OSM highway tags (motorway, trunk, primary, secondary, tertiary, residential, service)
    - Highway reference designations (e.g., NH-44, SH-17, NE-1) present in source data
    Never guesses road type if no evidence is present.
    """
    raw_address = raw_address or {}
    ref_val = raw_address.get("ref") or ""

    # Check for highway reference in road name or ref tag (e.g. NH-44, NH 44, SH-1, NE 1)
    combined_text = f"{road_name or ''} {ref_val}".strip().upper()

    nh_match = re.search(r"\b(NH[-\s]?\d+[A-Z]?)\b", combined_text)
    sh_match = re.search(r"\b(SH[-\s]?\d+[A-Z]?)\b", combined_text)
    ne_match = re.search(r"\b(NE[-\s]?\d+[A-Z]?)\b", combined_text)

    road_ref = None
    if nh_match:
        road_ref = nh_match.group(1).replace(" ", "-")
    elif sh_match:
        road_ref = sh_match.group(1).replace(" ", "-")
    elif ne_match:
        road_ref = ne_match.group(1).replace(" ", "-")
    elif ref_val:
        road_ref = ref_val.strip()

    # Classification based on explicit OSM tagging and/or official reference
    t = (osm_type or "").lower().strip()
    c = (osm_class or "").lower().strip()

    if t in ("motorway", "motorway_link") or ne_match:
        return RoadType.EXPRESSWAY, road_ref
    if t in ("trunk", "trunk_link") or nh_match:
        return RoadType.NATIONAL_HIGHWAY, road_ref
    if t in ("primary", "primary_link"):
        if sh_match:
            return RoadType.STATE_HIGHWAY, road_ref
        return RoadType.MUNICIPAL_ARTERIAL, road_ref
    if sh_match:
        return RoadType.STATE_HIGHWAY, road_ref
    if t in ("secondary", "secondary_link"):
        return RoadType.MUNICIPAL_ARTERIAL, road_ref
    if t in ("tertiary", "tertiary_link", "residential", "living_street", "unclassified"):
        return RoadType.MUNICIPAL_ROAD, road_ref
    if t in ("service",):
        return RoadType.SERVICE_ROAD, road_ref
    if t in ("track", "path"):
        return RoadType.RURAL_ROAD, road_ref

    # If highway tag or highway class exists but sub-type is unknown
    if c == "highway" and road_name:
        return RoadType.MUNICIPAL_ROAD, road_ref

    return RoadType.UNKNOWN, road_ref


def evaluate_location_match_quality(
    has_road: bool,
    accuracy_m: Optional[float] = None,
    is_official_segment: bool = False,
) -> LocationMatchQuality:
    """
    Evaluates qualitative match quality based on available road data and device GPS accuracy.
    No fabricated confidence numbers.
    """
    if not has_road:
        return LocationMatchQuality.UNAVAILABLE

    if accuracy_m is not None:
        if accuracy_m > settings.GPS_ACCURACY_THRESHOLD_UNRELIABLE_METERS:
            # High device uncertainty makes exact road identification uncertain
            return LocationMatchQuality.APPROXIMATE
        if accuracy_m > settings.GPS_ACCURACY_THRESHOLD_APPROXIMATE_METERS:
            return LocationMatchQuality.APPROXIMATE

    if is_official_segment:
        return LocationMatchQuality.EXACT

    # Reliable road match with reasonable GPS accuracy
    if accuracy_m is not None and accuracy_m <= 25.0:
        return LocationMatchQuality.STRONG

    return LocationMatchQuality.APPROXIMATE


class GeocodingProvider(ABC):
    """Abstract Base Class for resilient geocoding providers."""

    @abstractmethod
    def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        accuracy_m: Optional[float] = None,
    ) -> RawGeocodingResponse:
        """Fetch raw reverse geocoding data from provider."""
        pass


class NominatimGeocodingProvider(GeocodingProvider):
    """OpenStreetMap Nominatim reverse geocoding provider."""

    def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        accuracy_m: Optional[float] = None,
    ) -> RawGeocodingResponse:
        lat, lon = validate_coordinates(latitude, longitude, allow_null_island=True)

        query = urlencode({
            "lat": lat,
            "lon": lon,
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
        })
        request = Request(
            f"{settings.REVERSE_GEOCODER_URL}?{query}",
            headers={"User-Agent": settings.REVERSE_GEOCODER_USER_AGENT},
        )
        try:
            with urlopen(request, timeout=settings.REVERSE_GEOCODER_TIMEOUT_SECONDS) as response:
                if response.status == 429:
                    raise GeocodingRateLimited("Nominatim rate limit reached.")
                body = response.read(1_000_001)
                if len(body) > 1_000_000:
                    raise GeocodingError("Nominatim response exceeded 1MB limit.")
                payload = json.loads(body.decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429:
                raise GeocodingRateLimited("Nominatim rate limit reached.") from exc
            logger.warning("Nominatim HTTP error (status=%s).", exc.code)
            raise GeocodingError(f"Nominatim request failed: {exc.code}") from exc
        except TimeoutError as exc:
            logger.warning("Nominatim request timed out.")
            raise GeocodingTimeout("Nominatim provider timed out.") from exc
        except (URLError, ValueError, OSError) as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                logger.warning("Nominatim request timed out.")
                raise GeocodingTimeout("Nominatim provider timed out.") from exc
            logger.warning("Nominatim network/parse error: %s", type(exc).__name__)
            raise GeocodingError(f"Nominatim provider error: {exc}") from exc

        if not isinstance(payload, dict):
            raise GeocodingError("Unexpected Nominatim response format.")

        address = payload.get("address") or {}
        if not isinstance(address, dict):
            address = {}

        return RawGeocodingResponse(
            display_name=payload.get("display_name"),
            road=address.get("road"),
            area=address.get("suburb") or address.get("neighbourhood") or address.get("residential"),
            locality=address.get("locality") or address.get("suburb") or address.get("village"),
            city=address.get("city") or address.get("town") or address.get("municipality"),
            district=address.get("district") or address.get("county") or address.get("state_district"),
            municipality=address.get("municipality"),
            state=address.get("state"),
            country=address.get("country"),
            postal_code=address.get("postcode"),
            source="OpenStreetMap Nominatim",
            osm_type=payload.get("type"),
            osm_class=payload.get("class"),
            road_ref=address.get("ref"),
            raw_payload=payload,
        )


class ResilientGeocodingService:
    """
    Coordinates geocoding lookups with tiered fallback:
    1. Check Live provider
    2. Fallback to Cached result on live failure
    3. Return unavailable status if both live and cache are exhausted
    Never fabricates fallback addresses.
    """

    def __init__(self, provider: Optional[GeocodingProvider] = None):
        self._provider = provider or NominatimGeocodingProvider()

    def set_provider(self, provider: GeocodingProvider) -> None:
        self._provider = provider

    def resolve(
        self,
        latitude: float,
        longitude: float,
        accuracy_m: Optional[float] = None,
    ) -> Tuple[NormalizedLocation, RoadIdentification, RoadSegmentContext, GeoSourceStatus]:
        lat, lon = validate_coordinates(latitude, longitude, allow_null_island=True)
        acc = validate_accuracy(accuracy_m)

        cache = get_geo_cache()
        cache_key = build_geo_cache_key(lat, lon)
        cached_entry = cache.get(cache_key)

        now = datetime.now(timezone.utc)
        raw_res: Optional[RawGeocodingResponse] = None
        source_status = GeoSourceStatus.LIVE

        try:
            raw_res = self._provider.reverse_geocode(lat, lon, accuracy_m=acc)
            # Store in cache
            if raw_res:
                cache_data = {
                    "display_name": raw_res.display_name,
                    "road": raw_res.road,
                    "area": raw_res.area,
                    "locality": raw_res.locality,
                    "city": raw_res.city,
                    "district": raw_res.district,
                    "municipality": raw_res.municipality,
                    "state": raw_res.state,
                    "country": raw_res.country,
                    "postal_code": raw_res.postal_code,
                    "source": raw_res.source,
                    "osm_type": raw_res.osm_type,
                    "osm_class": raw_res.osm_class,
                    "road_ref": raw_res.road_ref,
                }
                match_qual = evaluate_location_match_quality(bool(raw_res.road), acc)
                cache.set(
                    cache_key=cache_key,
                    provider=raw_res.source,
                    data=cache_data,
                    match_quality=match_qual.value,
                )
        except (GeocodingError, Exception) as exc:
            logger.warning("Live geocoding failed (%s). Checking cache fallback.", exc)
            if cached_entry:
                logger.info("Serving geocoding from cache for (%s, %s).", lat, lon)
                cd = cached_entry.data
                raw_res = RawGeocodingResponse(
                    display_name=cd.get("display_name"),
                    road=cd.get("road"),
                    area=cd.get("area"),
                    locality=cd.get("locality"),
                    city=cd.get("city"),
                    district=cd.get("district"),
                    municipality=cd.get("municipality"),
                    state=cd.get("state"),
                    country=cd.get("country"),
                    postal_code=cd.get("postal_code"),
                    source=f"{cd.get('source', 'Unknown')} (cached)",
                    osm_type=cd.get("osm_type"),
                    osm_class=cd.get("osm_class"),
                    road_ref=cd.get("road_ref"),
                )
                source_status = GeoSourceStatus.CACHED
            else:
                source_status = GeoSourceStatus.UNAVAILABLE
                # Do NOT fabricate fallback addresses! Return clean unavailable location
                return (
                    NormalizedLocation(
                        latitude=lat,
                        longitude=lon,
                        accuracy_m=acc,
                        timestamp=now,
                        formatted_address=None,
                        road=None,
                        geocoding_source="unavailable",
                        geocoding_timestamp=now,
                        match_quality=LocationMatchQuality.UNAVAILABLE,
                    ),
                    RoadIdentification(
                        road_name=None,
                        road_type=RoadType.UNKNOWN,
                        road_reference=None,
                        source="unavailable",
                        retrieval_time=now,
                        match_quality=LocationMatchQuality.UNAVAILABLE,
                    ),
                    RoadSegmentContext(
                        road_identifier=None,
                        road_name=None,
                        source="unavailable",
                        matching_method="none",
                        matching_quality=LocationMatchQuality.UNAVAILABLE,
                    ),
                    source_status,
                )

        # Build normalized location
        has_road = bool(raw_res.road)
        match_quality = evaluate_location_match_quality(has_road, acc)

        road_type, road_ref = extract_road_type_and_ref(
            raw_res.road,
            raw_res.osm_class,
            raw_res.osm_type,
            raw_res.raw_payload.get("address") if raw_res.raw_payload else None,
        )

        norm_loc = NormalizedLocation(
            latitude=lat,
            longitude=lon,
            accuracy_m=acc,
            timestamp=now,
            formatted_address=raw_res.display_name,
            road=raw_res.road,
            area=raw_res.area,
            locality=raw_res.locality,
            city=raw_res.city,
            district=raw_res.district,
            state=raw_res.state,
            country=raw_res.country,
            postal_code=raw_res.postal_code,
            geocoding_source=raw_res.source,
            geocoding_timestamp=now,
            match_quality=match_quality,
        )

        road_id = RoadIdentification(
            road_name=raw_res.road,
            road_type=road_type,
            road_reference=road_ref,
            locality=raw_res.locality or raw_res.area,
            city=raw_res.city,
            district=raw_res.district,
            state=raw_res.state,
            source=raw_res.source,
            retrieval_time=now,
            match_quality=match_quality,
        )

        # Build Road Segment Context
        # Note: Unless an official road network vector/segment is matched, segment is approximate
        road_identifier = f"SEG-{road_ref or (raw_res.road or 'UNNAMED')[:12].upper().replace(' ', '_')}" if raw_res.road else None
        segment_ctx = RoadSegmentContext(
            road_identifier=road_identifier,
            road_name=raw_res.road,
            start_end_context=f"Near {raw_res.locality or raw_res.area or raw_res.city}" if (raw_res.road and (raw_res.locality or raw_res.area or raw_res.city)) else None,
            nearest_point={"latitude": lat, "longitude": lon} if raw_res.road else None,
            distance_to_identified_road_m=0.0 if raw_res.road else None,
            source=raw_res.source,
            matching_method="reverse_geocoding_address",
            matching_quality=match_quality if raw_res.road else LocationMatchQuality.UNAVAILABLE,
        )

        return norm_loc, road_id, segment_ctx, source_status


geocoding_service = ResilientGeocodingService()
