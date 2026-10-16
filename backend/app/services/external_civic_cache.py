from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from threading import Lock
from typing import Any, Optional, Tuple

from app.core.config import settings
from app.core.database import EXTERNAL_CIVIC_CACHE_COLLECTION, get_database

logger = logging.getLogger("cvki.services.external_civic_cache")


@dataclass
class ExternalCivicCacheEntry:
    cache_key: str
    provider: str
    category: str
    query_lat: float
    query_lon: float
    window_hours: int
    data: dict[str, Any]
    source: str
    status: str
    retrieved_at: datetime
    expires_at: datetime
    stale_expires_at: datetime

    def is_fresh(self, now: Optional[datetime] = None) -> bool:
        curr = now or datetime.now(timezone.utc)
        curr = curr if curr.tzinfo is not None else curr.replace(tzinfo=timezone.utc)
        exp = self.expires_at if self.expires_at.tzinfo is not None else self.expires_at.replace(tzinfo=timezone.utc)
        return curr <= exp

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        curr = now or datetime.now(timezone.utc)
        curr = curr if curr.tzinfo is not None else curr.replace(tzinfo=timezone.utc)
        exp = self.expires_at if self.expires_at.tzinfo is not None else self.expires_at.replace(tzinfo=timezone.utc)
        stale_exp = (
            self.stale_expires_at
            if self.stale_expires_at.tzinfo is not None
            else self.stale_expires_at.replace(tzinfo=timezone.utc)
        )
        return exp < curr <= stale_exp

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        curr = now or datetime.now(timezone.utc)
        curr = curr if curr.tzinfo is not None else curr.replace(tzinfo=timezone.utc)
        stale_exp = (
            self.stale_expires_at
            if self.stale_expires_at.tzinfo is not None
            else self.stale_expires_at.replace(tzinfo=timezone.utc)
        )
        return curr > stale_exp


def build_external_civic_cache_key(
    provider: str,
    category: str,
    latitude: float,
    longitude: float,
    window_hours: int = 24,
) -> str:
    """
    Creates a deterministic cache key.
    Precision of 3 decimal places (~110 meters) groups micro-neighborhoods for environmental data.
    """
    lat_b = round(float(latitude), 3)
    lon_b = round(float(longitude), 3)
    raw = f"{provider}:{category}:{lat_b:.3f}:{lon_b:.3f}:{window_hours}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class ExternalCivicCache(ABC):
    @abstractmethod
    def get(self, cache_key: str) -> Optional[ExternalCivicCacheEntry]:
        pass

    @abstractmethod
    def set(
        self,
        cache_key: str,
        provider: str,
        category: str,
        query_lat: float,
        query_lon: float,
        window_hours: int,
        data: dict[str, Any],
        source: str,
        status: str,
        fresh_ttl_seconds: Optional[int] = None,
        stale_ttl_seconds: Optional[int] = None,
    ) -> ExternalCivicCacheEntry:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryExternalCivicCache(ExternalCivicCache):
    """In-memory thread-safe cache for test isolation and offline fallback."""

    def __init__(self, max_size: int = 2000):
        self._entries: dict[str, ExternalCivicCacheEntry] = {}
        self._lock = Lock()
        self._max_size = max_size

    def get(self, cache_key: str) -> Optional[ExternalCivicCacheEntry]:
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry and entry.is_expired():
                # Expired past stale threshold
                self._entries.pop(cache_key, None)
                return None
            return entry

    def set(
        self,
        cache_key: str,
        provider: str,
        category: str,
        query_lat: float,
        query_lon: float,
        window_hours: int,
        data: dict[str, Any],
        source: str,
        status: str,
        fresh_ttl_seconds: Optional[int] = None,
        stale_ttl_seconds: Optional[int] = None,
    ) -> ExternalCivicCacheEntry:
        fresh_ttl = fresh_ttl_seconds if fresh_ttl_seconds is not None else settings.EXTERNAL_DATA_CACHE_TTL_SECONDS
        stale_ttl = (
            stale_ttl_seconds if stale_ttl_seconds is not None else settings.EXTERNAL_DATA_CACHE_STALE_TTL_SECONDS
        )
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=fresh_ttl)
        stale_expires_at = now + timedelta(seconds=stale_ttl)

        entry = ExternalCivicCacheEntry(
            cache_key=cache_key,
            provider=provider,
            category=category,
            query_lat=query_lat,
            query_lon=query_lon,
            window_hours=window_hours,
            data=data,
            source=source,
            status=status,
            retrieved_at=now,
            expires_at=expires_at,
            stale_expires_at=stale_expires_at,
        )
        with self._lock:
            if len(self._entries) >= self._max_size:
                oldest_key = next(iter(self._entries))
                self._entries.pop(oldest_key, None)
            self._entries[cache_key] = entry
        return entry

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class MongoExternalCivicCache(ExternalCivicCache):
    """MongoDB TTL-backed cache for production external civic data."""

    def __init__(self, in_memory_fallback: Optional[InMemoryExternalCivicCache] = None):
        self._fallback = in_memory_fallback or InMemoryExternalCivicCache()

    def get(self, cache_key: str) -> Optional[ExternalCivicCacheEntry]:
        db = get_database()
        if db is None:
            return self._fallback.get(cache_key)

        try:
            doc = db.sync_command(
                lambda: db.delegate[EXTERNAL_CIVIC_CACHE_COLLECTION].find_one({"cache_key": cache_key})
            )
            if not doc:
                return self._fallback.get(cache_key)

            entry = ExternalCivicCacheEntry(
                cache_key=doc["cache_key"],
                provider=doc["provider"],
                category=doc.get("category", "general"),
                query_lat=doc.get("query_lat", 0.0),
                query_lon=doc.get("query_lon", 0.0),
                window_hours=doc.get("window_hours", 24),
                data=doc["data"],
                source=doc.get("source", doc["provider"]),
                status=doc.get("status", "live"),
                retrieved_at=doc["retrieved_at"].replace(tzinfo=timezone.utc)
                if doc["retrieved_at"].tzinfo is None
                else doc["retrieved_at"],
                expires_at=doc["expires_at"].replace(tzinfo=timezone.utc)
                if doc["expires_at"].tzinfo is None
                else doc["expires_at"],
                stale_expires_at=doc.get("stale_expires_at", doc["expires_at"]).replace(tzinfo=timezone.utc)
                if doc.get("stale_expires_at", doc["expires_at"]).tzinfo is None
                else doc.get("stale_expires_at", doc["expires_at"]),
            )
            if entry.is_expired():
                return None
            return entry
        except Exception as exc:
            logger.warning("Mongo external civic cache lookup failed (%s); falling back to memory.", exc)
            return self._fallback.get(cache_key)

    def set(
        self,
        cache_key: str,
        provider: str,
        category: str,
        query_lat: float,
        query_lon: float,
        window_hours: int,
        data: dict[str, Any],
        source: str,
        status: str,
        fresh_ttl_seconds: Optional[int] = None,
        stale_ttl_seconds: Optional[int] = None,
    ) -> ExternalCivicCacheEntry:
        # Update in-memory fallback
        entry = self._fallback.set(
            cache_key=cache_key,
            provider=provider,
            category=category,
            query_lat=query_lat,
            query_lon=query_lon,
            window_hours=window_hours,
            data=data,
            source=source,
            status=status,
            fresh_ttl_seconds=fresh_ttl_seconds,
            stale_ttl_seconds=stale_ttl_seconds,
        )

        db = get_database()
        if db is not None:
            try:
                doc = {
                    "cache_key": entry.cache_key,
                    "provider": entry.provider,
                    "category": entry.category,
                    "query_lat": entry.query_lat,
                    "query_lon": entry.query_lon,
                    "window_hours": entry.window_hours,
                    "data": entry.data,
                    "source": entry.source,
                    "status": entry.status,
                    "retrieved_at": entry.retrieved_at,
                    "expires_at": entry.expires_at,
                    "stale_expires_at": entry.stale_expires_at,
                }
                db.sync_command(
                    lambda: db.delegate[EXTERNAL_CIVIC_CACHE_COLLECTION].replace_one(
                        {"cache_key": cache_key}, doc, upsert=True
                    )
                )
            except Exception as exc:
                logger.warning("Failed to persist external civic cache entry to MongoDB (%s).", exc)

        return entry

    def clear(self) -> None:
        self._fallback.clear()
        db = get_database()
        if db is not None:
            try:
                db.sync_command(lambda: db.delegate[EXTERNAL_CIVIC_CACHE_COLLECTION].delete_many({}))
            except Exception as exc:
                logger.warning("Failed to clear MongoDB external civic cache (%s).", exc)


default_external_civic_cache = MongoExternalCivicCache()
