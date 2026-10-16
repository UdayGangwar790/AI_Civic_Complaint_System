"""
CVKI M6.1 Authority Response Cache & Freshness Management.
Supports safe caching of official authority lookups, distinguishing between
cached fresh, cached stale, live, unavailable, not_found, and conflict states.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from typing import Any

from app.core.config import settings
from app.schemas.authority import (
    AuthorityConflict,
    AuthorityEvidence,
    AuthorityParty,
    OfficialSourceRecord,
)

logger = logging.getLogger("cvki.authority.cache")


@dataclass
class AuthorityCacheEntry:
    cache_key: str
    source_id: str
    retrieved_at: datetime
    expires_at: datetime
    freshness_policy_days: int
    data: dict[str, Any]

    def is_stale(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            expires = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires = self.expires_at
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current > expires


def build_cache_key(
    *,
    latitude: float,
    longitude: float,
    context: dict[str, str | None],
) -> str:
    """
    Creates a deterministic cache key from normalized road, city, and coordinates.
    """
    road = " ".join((context.get("road") or "").casefold().split())
    city = " ".join((context.get("city") or "").casefold().split())
    state = " ".join((context.get("state") or "").casefold().split())
    # Precision of 3 decimal places (~110 meters) captures local street segments
    lat_bucket = round(latitude, 3)
    lon_bucket = round(longitude, 3)

    raw = f"{road}|{city}|{state}|{lat_bucket:.3f}|{lon_bucket:.3f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def lookup_to_cache_data(lookup: Any) -> dict[str, Any]:
    """Serializes an AuthorityLookup dataclass to a cacheable dictionary."""
    def _dump_party(party: AuthorityParty | None) -> dict[str, Any] | None:
        return party.model_dump(mode="json") if party else None

    return {
        "road_owner": _dump_party(lookup.road_owner),
        "maintenance_authority": _dump_party(lookup.maintenance_authority),
        "builder_or_contractor": _dump_party(lookup.builder_or_contractor),
        "evidence": [item.model_dump(mode="json") for item in lookup.evidence],
        "sources": [src.model_dump(mode="json") for src in lookup.sources],
        "resolved_at": lookup.resolved_at.isoformat() if lookup.resolved_at else None,
        "resolution_message": lookup.resolution_message,
        "source_status": getattr(lookup, "source_status", None),
        "freshness": getattr(lookup, "freshness", "unknown"),
        "conflicts": [c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in getattr(lookup, "conflicts", ())],
    }


def cache_data_to_lookup_args(data: dict[str, Any]) -> dict[str, Any]:
    """Deserializes cache data back into kwargs suitable for AuthorityLookup."""
    road_owner = AuthorityParty(**data["road_owner"]) if data.get("road_owner") else None
    maintenance_authority = AuthorityParty(**data["maintenance_authority"]) if data.get("maintenance_authority") else None
    builder_or_contractor = AuthorityParty(**data["builder_or_contractor"]) if data.get("builder_or_contractor") else None

    evidence = tuple(
        AuthorityEvidence(**item) for item in data.get("evidence", [])
    )
    sources = tuple(
        OfficialSourceRecord(**src) for src in data.get("sources", [])
    )

    resolved_at = None
    if data.get("resolved_at"):
        try:
            resolved_at = datetime.fromisoformat(data["resolved_at"])
        except Exception:
            resolved_at = None

    conflicts = tuple(
        AuthorityConflict(**c) if isinstance(c, dict) else c
        for c in data.get("conflicts", [])
    )

    return {
        "road_owner": road_owner,
        "maintenance_authority": maintenance_authority,
        "builder_or_contractor": builder_or_contractor,
        "evidence": evidence,
        "sources": sources,
        "resolved_at": resolved_at,
        "resolution_message": data.get("resolution_message"),
        "source_status": data.get("source_status"),
        "freshness": data.get("freshness", "unknown"),
        "conflicts": conflicts,
    }


class AuthorityCacheRepository(ABC):
    @abstractmethod
    def get(self, cache_key: str) -> AuthorityCacheEntry | None:
        pass

    @abstractmethod
    def set(self, entry: AuthorityCacheEntry) -> None:
        pass

    @abstractmethod
    def delete(self, cache_key: str) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryAuthorityCache(AuthorityCacheRepository):
    """Safe, fast in-memory cache for development and unit testing."""

    def __init__(self) -> None:
        self._store: dict[str, AuthorityCacheEntry] = {}

    def get(self, cache_key: str) -> AuthorityCacheEntry | None:
        return self._store.get(cache_key)

    def set(self, entry: AuthorityCacheEntry) -> None:
        self._store[entry.cache_key] = entry

    def delete(self, cache_key: str) -> None:
        self._store.pop(cache_key, None)

    def clear(self) -> None:
        self._store.clear()


_active_cache: AuthorityCacheRepository = InMemoryAuthorityCache()


def get_authority_cache() -> AuthorityCacheRepository:
    return _active_cache


def set_authority_cache(cache: AuthorityCacheRepository) -> None:
    global _active_cache
    _active_cache = cache
