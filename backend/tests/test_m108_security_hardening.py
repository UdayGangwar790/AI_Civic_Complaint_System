"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.8: Security, Privacy & Epistemic Hardening Test Suite
"""

import pytest
from datetime import datetime, timezone
from fastapi import status
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.services.complaint_case import (
    ComplaintCase,
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
from app.services.field_inspection import (
    get_field_inspection_repository,
    get_audit_engine,
    get_protocol_generator,
)
from app.services.decision_projection import get_decision_projector
from app.services.multimodal.contracts import IssueCategory


CITIZEN_1 = AuthenticatedUser(user_id="user_cit_1", email="cit1@cvki.gov.in", role=UserRole.CITIZEN.value)
CITIZEN_2 = AuthenticatedUser(user_id="user_cit_2", email="cit2@cvki.gov.in", role=UserRole.CITIZEN.value)
AUTHORITY_1 = AuthenticatedUser(user_id="user_auth_1", email="auth1@cvki.gov.in", role=UserRole.AUTHORITY.value)
AUTHORITY_2 = AuthenticatedUser(user_id="user_auth_2", email="auth2@cvki.gov.in", role=UserRole.AUTHORITY.value)
ADMIN_1 = AuthenticatedUser(user_id="user_admin_1", email="admin@cvki.gov.in", role=UserRole.ADMIN.value)


@pytest.fixture(autouse=True)
def setup_security_env():
    orig_repo = complaint_case_module.case_repository
    mem_repo = InMemoryComplaintCaseRepository()
    set_case_repository(mem_repo)

    insp_repo = get_field_inspection_repository()
    insp_repo.clear()

    yield mem_repo
    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def _make_case(
    reference_id: str = "CASE-SEC-001",
    user_id: str = "user_cit_1",
    assigned_to: str = "user_auth_1",
    class_name: str = "open_damaged_manhole",
    status_val: str = "in_progress",
    tenant_id: str = "tenant_a",
) -> ComplaintCase:
    return ComplaintCase(
        reference_id=reference_id,
        user_id=user_id,
        status=status_val,
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": class_name,
            "label": "Open Manhole",
            "severity": "high",
            "confidence": 0.88,
        },
        location={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "road": "MG Road",
            "area": "Central",
            "city": "Bengaluru",
        },
        authority={
            "authority_status": "verified",
            "maintenance_authority": {"name": "BBMP Road Maintenance", "type": "Municipal"},
        },
        complaint={"title": "Hazardous road issue", "description": "Large dangerous opening", "language": "en"},
        follow_up={"guidance": "Saved in CVKI."},
        assignment={"assigned_to_user_id": assigned_to} if assigned_to else None,
        metadata={"tenant_id": tenant_id},
    )


# =========================================================================
# 10.8.1 AUTHORIZATION & RBAC
# =========================================================================

def test_01_unauthenticated_requests_blocked(setup_security_env):
    """Unauthenticated calls to M10 protected endpoints must return 401."""
    case = _make_case("CASE-UNAUTH-01")
    setup_security_env.save(case)

    # Ensure no dependency overrides
    app.dependency_overrides.clear()
    client = TestClient(app)

    routes = [
        ("GET", f"{settings.API_V1_STR}/decision-support/cases/CASE-UNAUTH-01"),
        ("GET", f"{settings.API_V1_STR}/decision-support/cases/CASE-UNAUTH-01/provenance"),
        ("GET", f"{settings.API_V1_STR}/decision-support/cases/CASE-UNAUTH-01/graph"),
        ("GET", f"{settings.API_V1_STR}/decision-support/cases/CASE-UNAUTH-01/citizen-view"),
        ("POST", f"{settings.API_V1_STR}/decision-support/cases/CASE-UNAUTH-01/review"),
        ("GET", f"{settings.API_V1_STR}/inspection/cases/CASE-UNAUTH-01/protocol"),
        ("POST", f"{settings.API_V1_STR}/inspection/cases/CASE-UNAUTH-01/submit"),
        ("POST", f"{settings.API_V1_STR}/multimodal/analyze"),
    ]

    for method, route in routes:
        if method == "GET":
            resp = client.get(route)
        else:
            resp = client.post(route, json={})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED, f"Route {route} allowed unauthenticated access!"


def test_02_citizen_cannot_access_internal_provenance(setup_security_env):
    """Citizen must not be able to retrieve internal provenance records."""
    case = _make_case("CASE-CIT-PROV", user_id="user_cit_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-CIT-PROV/provenance")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "strictly prohibited" in resp.json()["detail"].lower()


def test_03_citizen_cannot_access_decision_knowledge_graph(setup_security_env):
    """Citizen must not be able to retrieve internal decision knowledge graph."""
    case = _make_case("CASE-CIT-GRAPH", user_id="user_cit_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-CIT-GRAPH/graph")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "strictly prohibited" in resp.json()["detail"].lower()


def test_04_citizen_cannot_access_private_inspection_records(setup_security_env):
    """Citizen must not be able to retrieve private field inspection records."""
    case = _make_case("CASE-CIT-INSP", user_id="user_cit_1", assigned_to="user_auth_1")
    setup_security_env.save(case)

    # Authority submits an inspection
    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)
    post_resp = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-CIT-INSP/submit",
        json={
            "protocol_id": "PROTOCOL-MANHOLE-V1",
            "protocol_version": "1.0.0",
            "observations": [
                {"step_id": "STEP-MANHOLE-01", "observation_text": "Aperture exposed", "defect_confirmed": True}
            ],
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert post_resp.status_code == status.HTTP_201_CREATED
    insp_id = post_resp.json()["inspection_id"]

    # Citizen tries to fetch that private inspection
    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    get_resp = client.get(f"{settings.API_V1_STR}/inspection/{insp_id}")
    assert get_resp.status_code == status.HTTP_403_FORBIDDEN
    assert "strictly prohibited" in get_resp.json()["detail"].lower()


def test_05_cross_user_citizen_access_blocked(setup_security_env):
    """Citizen 2 cannot view Citizen 1's case citizen view."""
    case = _make_case("CASE-CROSS-CIT", user_id="user_cit_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_2
    client = TestClient(app)

    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-CROSS-CIT/citizen-view")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_06_cross_authority_access_blocked(setup_security_env):
    """Authority 2 cannot access case assigned to Authority 1."""
    case = _make_case("CASE-CROSS-AUTH", user_id="user_cit_1", assigned_to="user_auth_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_2
    client = TestClient(app)

    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-CROSS-AUTH")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_07_citizen_cannot_submit_authority_review(setup_security_env):
    """Citizens are forbidden from reviewing decision recommendations."""
    case = _make_case("CASE-NO-REV", user_id="user_cit_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    resp = client.post(
        f"{settings.API_V1_STR}/decision-support/cases/CASE-NO-REV/review",
        json={"review_status": "ACCEPTED", "review_notes": "Citizen attempts to sign off"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# =========================================================================
# 10.8.2 INPUT VALIDATION
# =========================================================================

def test_08_invalid_coordinates_rejected(setup_security_env):
    """Out-of-bound latitude (> 90 or < -90) or longitude (> 180 or < -180) must be rejected."""
    case = _make_case("CASE-COORD-01", assigned_to="user_auth_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)

    # Invalid latitude 95.0
    resp1 = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-COORD-01/submit",
        json={
            "protocol_id": "PROTOCOL-MANHOLE-V1",
            "protocol_version": "1.0.0",
            "observations": [{"step_id": "STEP-MANHOLE-01", "observation_text": "Bad coords"}],
            "location": {"latitude": 95.0, "longitude": 77.0},
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp1.status_code in (status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST)

    # Invalid longitude 205.0
    resp2 = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-COORD-01/submit",
        json={
            "protocol_id": "PROTOCOL-MANHOLE-V1",
            "protocol_version": "1.0.0",
            "observations": [{"step_id": "STEP-MANHOLE-01", "observation_text": "Bad coords"}],
            "location": {"latitude": 12.0, "longitude": 205.0},
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp2.status_code in (status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST)


def test_09_path_traversal_in_evidence_rejected(setup_security_env):
    """Path traversal sequences (e.g. ../../etc/passwd) in evidence items must be rejected."""
    case = _make_case("CASE-TRAV-01", assigned_to="user_auth_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)

    resp = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-TRAV-01/submit",
        json={
            "protocol_id": "PROTOCOL-MANHOLE-V1",
            "protocol_version": "1.0.0",
            "observations": [{"step_id": "STEP-MANHOLE-01", "observation_text": "Traversal attempt"}],
            "evidence_items": ["../../../../etc/shadow"],
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code in (status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST)


def test_10_malformed_review_status_rejected(setup_security_env):
    """Unsupported review status values must be rejected."""
    case = _make_case("CASE-REV-ENUM", assigned_to="user_auth_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)

    resp = client.post(
        f"{settings.API_V1_STR}/decision-support/cases/CASE-REV-ENUM/review",
        json={"review_status": "ILLEGAL_STATUS_INJECTION", "review_notes": "Attempting invalid enum"},
    )
    assert resp.status_code in (status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST)


# =========================================================================
# 10.8.3 SSRF PREVENTION
# =========================================================================

def test_11_ssrf_attacks_blocked(setup_security_env):
    """SSRF attacks targeting localhost, 127.0.0.1, or cloud metadata 169.254.169.254 must be rejected."""
    case = _make_case("CASE-SSRF-01", assigned_to="user_auth_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)

    malicious_urls = [
        "http://localhost:8080/admin",
        "http://127.0.0.1:8000/internal",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379",
    ]

    for bad_url in malicious_urls:
        resp = client.post(
            f"{settings.API_V1_STR}/inspection/cases/CASE-SSRF-01/submit",
            json={
                "protocol_id": "PROTOCOL-MANHOLE-V1",
                "protocol_version": "1.0.0",
                "observations": [{"step_id": "STEP-MANHOLE-01", "observation_text": "SSRF test"}],
                "evidence_items": [bad_url],
                "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert resp.status_code in (status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST), (
            f"SSRF URL '{bad_url}' was not rejected!"
        )


# =========================================================================
# 10.8.4 XSS / INJECTION SAFETY
# =========================================================================

def test_12_script_injection_in_clarification_rejected(setup_security_env):
    """Malicious HTML script tags in clarification answers must be rejected."""
    case = _make_case("CASE-XSS-01", user_id="user_cit_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    resp = client.post(
        f"{settings.API_V1_STR}/decision-support/cases/CASE-XSS-01/clarify",
        json={
            "question_id": "q_test",
            "free_text": "<script>alert('xss')</script>",
            "language": "en",
        },
    )
    assert resp.status_code in (status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST)


# =========================================================================
# 10.8.5 PRIVACY PRESERVATION
# =========================================================================

def test_13_citizen_view_fuzzes_location(setup_security_env):
    """Citizen view must approximate coordinates to ~100m (3 decimal places) and omit raw coords."""
    case = _make_case("CASE-PRIV-01", user_id="user_cit_1")
    setup_security_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-PRIV-01/citizen-view")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    pub_loc = data["public_location"]
    # Approximate coords present
    assert "latitude_approx" in pub_loc
    assert "longitude_approx" in pub_loc
    assert pub_loc["latitude_approx"] == 12.972  # 12.9716 rounded to 3 decimal places
    assert pub_loc["longitude_approx"] == 77.595  # 77.5946 rounded to 3 decimal places
    # Raw exact coordinates must NOT be present
    assert "latitude" not in pub_loc
    assert "longitude" not in pub_loc
