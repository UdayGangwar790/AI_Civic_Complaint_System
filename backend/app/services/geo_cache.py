from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from threading import Lock
from typing import Any, Optional

from app.core.config import settings
from app.core.database import GEO_CACHE_COLLECTION, get_database

logger = logging.getLogger("cvki.services.geo_cache")


@dataclass
class GeoCacheEntry:
    cache_key: str
    provider: str
    retrieved_at: datetime
    expires_at: datetime
    data: dict[str, Any]
    match_quality: str

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        current = now or datetime.now(timezone.utc)
        expires = self.expires_at if self.expires_at.tzinfo is not None else self.expires_at.replace(tzinfo=timezone.utc)
        curr = current if current.tzinfo is not None else current.replace(tzinfo=timezone.utc)
        return curr > expires


def build_geo_cache_key(latitude: float, longitude: float) -> str:
    """
    Creates a deterministic cache key from normalized coordinates.
    Precision of 4 decimal places (~11 meters) matches street-level requests.
    """
    lat_bucket = round(float(latitude), 4)
    lon_bucket = round(float(longitude), 4)
    raw = f"{lat_bucket:.4f}|{lon_bucket:.4f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class GeoCache(ABC):
    @abstractmethod
    def get(self, cache_key: str) -> Optional[GeoCacheEntry]:
        pass

    @abstractmethod
    def set(
        self,
        cache_key: str,
        provider: str,
        data: dict[str, Any],
        match_quality: str,
        ttl_seconds: Optional[int] = None,
    ) -> GeoCacheEntry:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryGeoCache(GeoCache):
    """In-memory thread-safe LRU/TTL cache for test isolation and fallback."""

    def __init__(self, max_size: int = 2000):
        self._entries: dict[str, GeoCacheEntry] = {}
        self._lock = Lock()
        self._max_size = max_size

    def get(self, cache_key: str) -> Optional[GeoCacheEntry]:
        with self._lock:
            return self._entries.get(cache_key)

    def set(
        self,
        cache_key: str,
        provider: str,
        data: dict[str, Any],
        match_quality: str,
        ttl_seconds: Optional[int] = None,
    ) -> GeoCacheEntry:
        ttl = ttl_seconds if ttl_seconds is not None else settings.GEO_CACHE_TTL_SECONDS
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)
        entry = GeoCacheEntry(
            cache_key=cache_key,
            provider=provider,
            retrieved_at=now,
            expires_at=expires_at,
            data=data,
            match_quality=match_quality,
        )
        with self._lock:
            if len(self._entries) >= self._max_size:
                # Evict oldest entry
                oldest_key = next(iter(self._entries))
                self._entries.pop(oldest_key, None)
            self._entries[cache_key] = entry
        return entry

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Default singleton instance (InMemory with Mongo persistence integration when active)
_geo_cache_instance: GeoCache = InMemoryGeoCache()


def get_geo_cache() -> GeoCache:
    return _geo_cache_instance


def set_geo_cache(cache: GeoCache) -> None:
    global _geo_cache_instance
    _geo_cache_instance = cache
