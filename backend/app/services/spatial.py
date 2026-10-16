import math
from typing import Any, Optional, Tuple


class CoordinateValidationError(ValueError):
    """Raised when GPS coordinates or spatial parameters fail validation."""


def validate_coordinates(
    latitude: Any,
    longitude: Any,
    allow_null_island: bool = False,
) -> Tuple[float, float]:
    """
    Strictly validates latitude and longitude.

    Requirements:
    - Must be finite float numbers.
    - Latitude range: -90.0 to 90.0 degrees.
    - Longitude range: -180.0 to 180.0 degrees.
    - Exclude (0.0, 0.0) 'Null Island' by default unless explicitly allowed.
    """
    if latitude is None or longitude is None:
        raise CoordinateValidationError("Both latitude and longitude are required.")

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError) as exc:
        raise CoordinateValidationError("Coordinates must be valid numeric values.") from exc

    if not math.isfinite(lat) or not math.isfinite(lon):
        raise CoordinateValidationError("Coordinates must be finite numeric values.")

    if not -90.0 <= lat <= 90.0:
        raise CoordinateValidationError(
            f"Latitude must be between -90 and 90 degrees. Received: {lat}"
        )

    if not -180.0 <= lon <= 180.0:
        raise CoordinateValidationError(
            f"Longitude must be between -180 and 180 degrees. Received: {lon}"
        )

    if not allow_null_island and abs(lat) < 1e-6 and abs(lon) < 1e-6:
        raise CoordinateValidationError(
            "Null Island coordinates (0.0, 0.0) indicate missing or uninitialized GPS fix."
        )

    return lat, lon


def validate_accuracy(accuracy_m: Optional[Any]) -> Optional[float]:
    """
    Validates GPS horizontal accuracy in meters.
    Must be a non-negative finite number if provided.
    """
    if accuracy_m is None:
        return None
    try:
        acc = float(accuracy_m)
    except (TypeError, ValueError) as exc:
        raise CoordinateValidationError("GPS accuracy must be a numeric value in meters.") from exc

    if not math.isfinite(acc) or acc < 0:
        raise CoordinateValidationError("GPS accuracy must be a non-negative finite number.")

    return acc


def haversine_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Computes great-circle distance between two GPS coordinates in meters using the Haversine formula.
    Mean Earth radius: 6,371,000 meters.
    """
    lat1, lon1 = validate_coordinates(lat1, lon1, allow_null_island=True)
    lat2, lon2 = validate_coordinates(lat2, lon2, allow_null_island=True)

    earth_radius_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp 'a' to [0.0, 1.0] to guard against rare floating point imprecision
    a = max(0.0, min(1.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_m * c


def haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Computes distance in kilometers.
    """
    return haversine_distance_meters(lat1, lon1, lat2, lon2) / 1000.0


def calculate_bearing_degrees(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculates initial compass bearing in degrees (0 to 360) from point 1 to point 2.
    0° = North, 90° = East, 180° = South, 270° = West.
    """
    lat1, lon1 = validate_coordinates(lat1, lon1, allow_null_island=True)
    lat2, lon2 = validate_coordinates(lat2, lon2, allow_null_island=True)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)

    bearing_rad = math.atan2(y, x)
    bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
    return bearing_deg


def bearing_to_compass_direction(bearing_deg: float) -> str:
    """
    Converts bearing degrees into an 8-point compass direction (N, NE, E, SE, S, SW, W, NW).
    """
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((bearing_deg + 22.5) // 45.0) % 8
    return directions[idx]


def bounding_box_for_radius(
    latitude: float,
    longitude: float,
    radius_meters: float,
) -> Tuple[float, float, float, float]:
    """
    Calculates an approximate latitude/longitude bounding box (min_lat, min_lon, max_lat, max_lon)
    for a given radius in meters around a coordinate.
    Useful for index-friendly bounding-box pre-filtering before exact Haversine calculation.
    """
    lat, lon = validate_coordinates(latitude, longitude, allow_null_island=True)
    if radius_meters < 0:
        raise ValueError("Radius must be non-negative.")

    earth_radius_m = 6_371_000.0
    lat_delta = math.degrees(radius_meters / earth_radius_m)
    # Longitude scaling depends on latitude
    cos_lat = math.cos(math.radians(lat))
    lon_delta = math.degrees(radius_meters / (earth_radius_m * cos_lat)) if abs(cos_lat) > 1e-6 else 180.0

    min_lat = max(-90.0, lat - lat_delta)
    max_lat = min(90.0, lat + lat_delta)
    min_lon = max(-180.0, lon - lon_delta)
    max_lon = min(180.0, lon + lon_delta)

    return min_lat, min_lon, max_lat, max_lon


def to_geojson_point(latitude: float, longitude: float) -> dict[str, Any]:
    """
    Produces a valid GeoJSON Point structure.
    CRITICAL: GeoJSON standard specifies coordinate order as [longitude, latitude].
    """
    lat, lon = validate_coordinates(latitude, longitude, allow_null_island=True)
    return {
        "type": "Point",
        "coordinates": [lon, lat],
    }


def from_geojson_point(point: dict[str, Any]) -> Tuple[float, float]:
    """
    Extracts (latitude, longitude) from a GeoJSON Point object.
    GeoJSON coordinates are [longitude, latitude].
    """
    if not isinstance(point, dict) or point.get("type") != "Point":
        raise ValueError("Invalid GeoJSON Point.")
    coords = point.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        raise ValueError("GeoJSON coordinates must have at least 2 elements [lon, lat].")
    lon, lat = coords[0], coords[1]
    return validate_coordinates(lat, lon, allow_null_island=True)
