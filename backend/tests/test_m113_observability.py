"""
CVKI - Civic Vision & Knowledge Intelligence
Module 11.3: Observability, Audit Monitoring & Operational Metrics Tests
"""

from fastapi.testclient import TestClient
import pytest

from app.core.observability import (
    MetricsCollector,
    compute_percentiles,
    get_metrics_collector,
    redact_sensitive_dict,
)
from app.main import app
from app.models.roles import UserRole


@pytest.fixture
def client():
    return TestClient(app)


def test_percentile_calculation():
    vals = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p = compute_percentiles(vals)
    assert p["count"] == 10
    assert p["mean_ms"] == 55.0
    assert p["median_ms"] == 55.0
    assert p["max_ms"] == 100.0
    assert p["p95_ms"] > 90.0


def test_sensitive_data_redaction():
    payload = {
        "user_id": "usr_test123",
        "email": "citizen@example.com",
        "password": "super_secret_password_123",
        "auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_token",
        "api_key": "sec_cpgrams_api_key_8899",
        "safe_note": "A regular observation note",
    }
    redacted = redact_sensitive_dict(payload)
    assert redacted["user_id"] == "usr_test123"
    assert redacted["safe_note"] == "A regular observation note"
    assert "super_secret_password_123" not in redacted["password"]
    assert "dummy_token" not in redacted["auth_token"]
    assert "sec_cpgrams_api_key_8899" not in redacted["api_key"]


def test_health_endpoints(client):
    # GET /api/health
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    # GET /api/health/live and GET /api/live
    res_live1 = client.get("/api/health/live")
    assert res_live1.status_code == 200
    assert res_live1.json()["status"] == "live"

    res_live2 = client.get("/api/live")
    assert res_live2.status_code == 200
    assert res_live2.json()["status"] == "live"

    # GET /api/health/ready and GET /api/ready
    res_ready1 = client.get("/api/health/ready")
    assert res_ready1.status_code in (200, 503)
    assert "dependencies" in res_ready1.json()

    res_ready2 = client.get("/api/ready")
    assert res_ready2.status_code in (200, 503)


def test_http_request_id_and_correlation_id(client):
    res = client.get("/api/health", headers={"X-Correlation-ID": "corr-uuid-12345"})
    assert res.status_code == 200
    assert "X-Request-ID" in res.headers
    assert res.headers.get("X-Correlation-ID") == "corr-uuid-12345"


def test_metrics_collector_recording():
    collector = MetricsCollector()
    collector.record_api_request(method="GET", path="/api/health", status_code=200, duration_ms=1.5)
    collector.record_api_request(method="POST", path="/api/v1/cases", status_code=422, duration_ms=2.5, error_category="validation_error")
    collector.record_cv_inference(duration_ms=45.2)
    collector.record_decision_support(duration_ms=0.5, priority="P1")
    collector.record_authority_resolution(duration_ms=3.2, cache_hit=True)
    collector.record_authority_resolution(duration_ms=12.0, cache_hit=False)
    collector.record_field_inspection_audit(outcome="SUPPORTED")
    collector.record_human_review()

    summary = collector.get_metrics_summary()
    assert summary["api"]["requests_total"] == 2
    assert summary["api"]["errors_total"] == 1
    assert summary["api"]["error_categories"]["validation_error"] == 1
    assert summary["subsystems"]["cv_inference"]["count"] == 1
    assert summary["cache"]["hits"]["authority"] == 1
    assert summary["cache"]["misses"]["authority"] == 1
    assert summary["operational_outcomes"]["human_reviews_recorded"] == 1
    assert summary["operational_outcomes"]["field_inspection_audits"]["SUPPORTED"] == 1


def test_admin_metrics_endpoint_rbac(client):
    # Unauthenticated
    res = client.get("/api/v1/admin/metrics")
    assert res.status_code in (401, 403)
