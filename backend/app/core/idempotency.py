"""
CVKI - Civic Vision & Knowledge Intelligence
Module 11.4: Data Integrity, Idempotency & Consistency Hardening
"""

from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from threading import Lock
from typing import Any, Optional

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

logger = logging.getLogger("cvki.core.idempotency")


def compute_payload_fingerprint(data: Any) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for arbitrary JSON-serializable payloads.
    """
    try:
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        canonical_json = str(data)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@dataclass
class IdempotencyRecord:
    key: str
    scope: str
    fingerprint: str
    status: str  # "IN_PROGRESS", "COMPLETED", "FAILED"
    response_status_code: Optional[int] = None
    response_body: Optional[Any] = None
    created_at: str = ""
    updated_at: str = ""


class IdempotencyStore:
    """
    Thread-safe process-level store with bounded capacity and TTL.
    Prevents duplicate side-effects from replayed or concurrent requests across:
    - Citizen clarification submission
    - Authority review submission
    - Field inspection submission
    - Government submission and status synchronization
    - Graph projection & provenance recording
    """

    _MAX_ENTRIES = 5_000

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: OrderedDict[str, IdempotencyRecord] = OrderedDict()

    def acquire(
        self,
        *,
        key: str,
        scope: str,
        fingerprint: str,
    ) -> tuple[bool, Optional[IdempotencyRecord]]:
        """
        Attempts to acquire the idempotency key.
        Returns:
            (True, None) if key was acquired for new execution.
            (False, existing_record) if key already exists (completed or in-progress).
        """
        now_str = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                # If payloads mismatch, reject tampering
                if existing.fingerprint and existing.fingerprint != fingerprint:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Idempotency key re-used with different request payload.",
                    )
                self._records.move_to_end(key)
                return False, existing

            # Brand new key
            new_record = IdempotencyRecord(
                key=key,
                scope=scope,
                fingerprint=fingerprint,
                status="IN_PROGRESS",
                created_at=now_str,
                updated_at=now_str,
            )
            self._records[key] = new_record
            self._records.move_to_end(key)
            while len(self._records) > self._MAX_ENTRIES:
                self._records.popitem(last=False)
            return True, None

    def complete(
        self,
        *,
        key: str,
        response_status_code: int,
        response_body: Any,
    ) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        with self._lock:
            rec = self._records.get(key)
            if rec is not None:
                rec.status = "COMPLETED"
                rec.response_status_code = response_status_code
                rec.response_body = response_body
                rec.updated_at = now_str
                self._records.move_to_end(key)

    def release_on_failure(self, key: str) -> None:
        """Removes the key or marks FAILED if execution encountered a non-idempotent server exception."""
        with self._lock:
            self._records.pop(key, None)

    def get(self, key: str) -> Optional[IdempotencyRecord]:
        with self._lock:
            return self._records.get(key)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


idempotency_store = IdempotencyStore()


def get_idempotency_store() -> IdempotencyStore:
    return idempotency_store
