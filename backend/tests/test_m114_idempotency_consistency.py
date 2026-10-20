"""
CVKI - Civic Vision & Knowledge Intelligence
Module 11.4: Data Integrity, Idempotency & Consistency Hardening Tests
"""

from fastapi import HTTPException
import pytest

from app.core.idempotency import (
    IdempotencyStore,
    compute_payload_fingerprint,
    get_idempotency_store,
)


def test_deterministic_payload_fingerprint():
    payload_a = {"case_reference": "CVKI-2026-0001", "action": "clarify", "notes": "Observation"}
    payload_b = {"notes": "Observation", "action": "clarify", "case_reference": "CVKI-2026-0001"}
    payload_c = {"case_reference": "CVKI-2026-0002", "action": "clarify", "notes": "Observation"}

    fp_a = compute_payload_fingerprint(payload_a)
    fp_b = compute_payload_fingerprint(payload_b)
    fp_c = compute_payload_fingerprint(payload_c)

    # Key order must not affect fingerprint
    assert fp_a == fp_b
    # Different payload must produce different fingerprint
    assert fp_a != fp_c


def test_idempotency_store_lifecycle():
    store = IdempotencyStore()
    key = "idem_test_key_001"
    fp = "fp_abc123"

    # 1. First acquire: succeeds
    acquired, rec = store.acquire(key=key, scope="test", fingerprint=fp)
    assert acquired is True
    assert rec is None

    # 2. Second acquire while in-progress: returns in-progress record
    acquired, rec = store.acquire(key=key, scope="test", fingerprint=fp)
    assert acquired is False
    assert rec is not None
    assert rec.status == "IN_PROGRESS"

    # 3. Complete execution
    store.complete(key=key, response_status_code=200, response_body={"result": "ok"})

    # 4. Third acquire: returns completed record
    acquired, rec = store.acquire(key=key, scope="test", fingerprint=fp)
    assert acquired is False
    assert rec.status == "COMPLETED"
    assert rec.response_status_code == 200
    assert rec.response_body == {"result": "ok"}


def test_idempotency_store_rejects_payload_tampering():
    store = IdempotencyStore()
    key = "idem_tamper_key"
    store.acquire(key=key, scope="test", fingerprint="original_fp")

    # Attempting to reuse same key with modified payload must raise 422
    with pytest.raises(HTTPException) as exc_info:
        store.acquire(key=key, scope="test", fingerprint="modified_tampered_fp")
    assert exc_info.value.status_code == 422


def test_idempotency_store_release_on_failure():
    store = IdempotencyStore()
    key = "idem_fail_key"
    store.acquire(key=key, scope="test", fingerprint="fp1")
    # Release on failure
    store.release_on_failure(key)
    # Re-acquire succeeds
    acquired, _ = store.acquire(key=key, scope="test", fingerprint="fp1")
    assert acquired is True
