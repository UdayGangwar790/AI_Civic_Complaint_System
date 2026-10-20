"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.7: Authority Decision Support & Citizen Clarification UI API Tests
"""

from datetime import datetime, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.complaint_case import ComplaintCase
from app.schemas.decision_support import (
    CitizenClarifyRequest,
    DecisionEvidenceQuality,
    DecisionSupportResult,
    RecommendationReviewRequest,
)
from app.schemas.field_inspection import (
    InspectionObservationItem,
)
from app.services.complaint_case import (
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
from app.services.field_inspection import (
    InMemoryFieldInspectionRepository,
    get_field_inspection_repository,
)
from app.services.knowledge_graph import (
    InMemoryKnowledgeGraphRepository,
    get_knowledge_graph_service,
)
from app.services.provenance_engine import (
    InMemoryProvenanceRepository,
    get_provenance_engine,
)


def _auth(user_id: str, role: str, scopes: list[str] | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id,
        email=f"{user_id}@cvki.gov.in",
        role=role,
        scopes=scopes or [],
    )


@pytest.fixture(autouse=True)
def setup_m107_env():
    orig_repo = complaint_case_module.case_repository
    case_repo = InMemoryComplaintCaseRepository()
    set_case_repository(case_repo)

    insp_repo = get_field_inspection_repository()
    insp_repo.clear()

    prov_engine = get_provenance_engine()
    prov_engine.repository.clear()

    kg = get_knowledge_graph_service()
    kg.repository.clear()

    yield {
        "case_repo": case_repo,
        "insp_repo": insp_repo,
        "prov_repo": prov_engine.repository,
        "kg_repo": kg.repository,
    }
    set_case_repository(orig_repo)


def _make_case(
    reference_id: str,
    user_id: str = "citizen_1",
    assigned_to: str = "authority_1",
    class_name: str = "open_damaged_manhole",
    status_val: str = "under_review",
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


# -------------------------------------------------------------------------
# Test Cases 1 - 5: RBAC & Tenant Access
# -------------------------------------------------------------------------

def test_01_authority_sees_assigned_case(setup_m107_env):
    """Authority can retrieve decision support for assigned case."""
    case = _make_case("CASE-AUTH-01", user_id="cit_101", assigned_to="auth_user_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_user_1", UserRole.AUTHORITY.value, ["cases:read", "decision:read"])
    client = TestClient(app)
    try:
        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-AUTH-01")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["case_reference"] == "CASE-AUTH-01"
        assert len(data["recommended_actions"]) > 0
    finally:
        app.dependency_overrides.clear()


def test_02_admin_sees_authorized_case(setup_m107_env):
    """Admin has unrestricted access to decision support."""
    case = _make_case("CASE-ADM-01", user_id="cit_101", assigned_to="auth_other")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("admin_1", UserRole.ADMIN.value, ["admin:all"])
    client = TestClient(app)
    try:
        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-ADM-01")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["case_reference"] == "CASE-ADM-01"
    finally:
        app.dependency_overrides.clear()


def test_03_citizen_sees_own_case(setup_m107_env):
    """Citizen can access their own case decision support and citizen-view."""
    case = _make_case("CASE-CIT-01", user_id="cit_owner", assigned_to="auth_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("cit_owner", UserRole.CITIZEN.value, ["cases:read"])
    client = TestClient(app)
    try:
        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-CIT-01/citizen-view")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["case_reference"] == "CASE-CIT-01"
        assert "simplified_explanation" in data
        assert "public_location" in data
        # Coordinates must be approximated (~3 decimal places)
        loc = data["public_location"]
        assert "latitude_approx" in loc
        assert loc["latitude_approx"] == 12.972
    finally:
        app.dependency_overrides.clear()


def test_04_citizen_cannot_access_other_citizen_data(setup_m107_env):
    """Citizen is forbidden from accessing another citizen's case."""
    case = _make_case("CASE-OTHER-01", user_id="cit_owner", assigned_to="auth_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("cit_attacker", UserRole.CITIZEN.value, ["cases:read"])
    client = TestClient(app)
    try:
        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-OTHER-01")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
    finally:
        app.dependency_overrides.clear()


def test_05_authority_cannot_access_unassigned_case(setup_m107_env):
    """Authority cannot access case assigned to another officer/tenant."""
    case = _make_case("CASE-TENANT-01", user_id="cit_1", assigned_to="auth_officer_A", tenant_id="dept_road")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_officer_B", UserRole.AUTHORITY.value, ["cases:read"])
    client = TestClient(app)
    try:
        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-TENANT-01")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
    finally:
        app.dependency_overrides.clear()


# -------------------------------------------------------------------------
# Test Cases 6 - 7: Citizen Clarification & Inspection Workflow
# -------------------------------------------------------------------------

def test_06_clarification_submission(setup_m107_env):
    """Citizen submits clarification response; verify USER_REPORTED epistemic state and no status change."""
    case = _make_case("CASE-CLAR-01", user_id="cit_clar_user", status_val="under_review")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("cit_clar_user", UserRole.CITIZEN.value, ["cases:read", "cases:write"])
    client = TestClient(app)
    try:
        payload = {
            "question_id": "cq_issue_type_1234abcd",
            "selected_option": "Open/damaged manhole",
            "language": "en",
        }
        resp = client.post(f"{settings.API_V1_STR}/decision-support/cases/CASE-CLAR-01/clarify", json=payload)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["epistemic_state"].upper() == "USER_REPORTED"
        assert data["clarification_status"] == "RESOLVED"

        # Invariant check: case status MUST NOT be marked resolved
        c = setup_m107_env["case_repo"].get("CASE-CLAR-01")
        assert c.status == "under_review"
    finally:
        app.dependency_overrides.clear()


def test_07_inspection_workflow(setup_m107_env):
    """Authority opens protocol, submits inspection, and views audit outcome."""
    case = _make_case("CASE-INSP-FLOW", user_id="cit_1", assigned_to="auth_insp_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_insp_1", UserRole.AUTHORITY.value, ["inspection:read", "inspection:write"])
    client = TestClient(app)
    try:
        # Step A: Get protocol
        proto_resp = client.get(f"{settings.API_V1_STR}/inspection/cases/CASE-INSP-FLOW/protocol")
        assert proto_resp.status_code == status.HTTP_200_OK
        proto = proto_resp.json()
        assert proto["case_reference"] == "CASE-INSP-FLOW"
        assert len(proto["inspection_steps"]) > 0

        # Step B: Submit inspection
        first_step_id = proto["inspection_steps"][0]["step_id"]
        submit_payload = {
            "protocol_id": proto["protocol_id"],
            "protocol_version": proto["protocol_version"],
            "observations": [
                {
                    "step_id": first_step_id,
                    "observation_text": "Manhole cover completely missing; rim damaged",
                    "defect_confirmed": True,
                    "notes": "Verified hazard on curb side",
                }
            ],
            "evidence_items": ["photo_overview.jpg", "photo_closeup.jpg"],
            "location": {"latitude": 12.9716, "longitude": 77.5946},
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        sub_resp = client.post(f"{settings.API_V1_STR}/inspection/cases/CASE-INSP-FLOW/submit", json=submit_payload)
        assert sub_resp.status_code == status.HTTP_201_CREATED
        data = sub_resp.json()
        assert data["audit_result"]["outcome"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")
        assert data["geofence_result"] == "WITHIN_EXPECTED_AREA"
    finally:
        app.dependency_overrides.clear()


# -------------------------------------------------------------------------
# Test Cases 8 - 10: Decision, Provenance & Knowledge Graph Retrieval
# -------------------------------------------------------------------------

def test_08_decision_retrieval(setup_m107_env):
    """Authority retrieves actionable decision support recommendations."""
    case = _make_case("CASE-DEC-RET", assigned_to="auth_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_1", UserRole.AUTHORITY.value, ["cases:read"])
    client = TestClient(app)
    try:
        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-DEC-RET")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "recommendation_id" in data
        assert data["human_review_required"] is True
        assert len(data["recommended_actions"]) > 0
    finally:
        app.dependency_overrides.clear()


def test_09_provenance_retrieval(setup_m107_env):
    """Authority retrieves audit provenance trail for a case."""
    case = _make_case("CASE-PROV-RET", assigned_to="auth_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_1", UserRole.AUTHORITY.value, ["cases:read"])
    client = TestClient(app)
    try:
        # Trigger evaluation to project into provenance
        client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-PROV-RET")

        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-PROV-RET/provenance")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["case_reference"] == "CASE-PROV-RET"
        assert len(data["provenance_records"]) > 0
    finally:
        app.dependency_overrides.clear()


def test_10_graph_retrieval(setup_m107_env):
    """Authority retrieves knowledge graph projection for a case."""
    case = _make_case("CASE-GRAPH-RET", assigned_to="auth_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_1", UserRole.AUTHORITY.value, ["cases:read"])
    client = TestClient(app)
    try:
        client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-GRAPH-RET")

        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-GRAPH-RET/graph")
        assert resp.status_code == status.HTTP_200_OK
        subgraph = resp.json()
        assert "nodes" in subgraph
        assert "edges" in subgraph
        assert len(subgraph["nodes"]) > 0
    finally:
        app.dependency_overrides.clear()


# -------------------------------------------------------------------------
# Test Cases 11 - 14: Stale, Conflict, Missing Evidence & General RBAC
# -------------------------------------------------------------------------

def test_11_stale_evidence_handling(setup_m107_env):
    """Evaluate decision support with stale contextual evidence."""
    case = _make_case("CASE-STALE-UI", assigned_to="auth_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_1", UserRole.AUTHORITY.value, ["cases:read"])
    client = TestClient(app)
    try:
        eval_payload = {
            "case_reference": "CASE-STALE-UI",
            "weather_condition": "stale sensor report",
        }
        resp = client.post(f"{settings.API_V1_STR}/decision-support/cases/CASE-STALE-UI/evaluate", json=eval_payload)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "recommendation_id" in data
    finally:
        app.dependency_overrides.clear()


def test_12_conflict_display(setup_m107_env):
    """Verify conflicting evidence triggers clarification requirement and CONFLICTING quality."""
    case = _make_case("CASE-CONF-UI", assigned_to="auth_1", class_name="open_damaged_manhole")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_1", UserRole.AUTHORITY.value, ["cases:read"])
    client = TestClient(app)
    try:
        eval_payload = {
            "case_reference": "CASE-CONF-UI",
            "alignment_score": 0.15,
            "ambiguity_score": 0.85,
            "clarification_needed": True,
        }
        resp = client.post(f"{settings.API_V1_STR}/decision-support/cases/CASE-CONF-UI/evaluate", json=eval_payload)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["evidence_quality"] == DecisionEvidenceQuality.CONFLICTING.value
        assert any("conflict" in u.lower() or "discrepancy" in u.lower() for u in data["uncertainty"])
    finally:
        app.dependency_overrides.clear()


def test_13_missing_evidence_display(setup_m107_env):
    """Verify missing evidence items are listed explicitly in decision support."""
    case = _make_case("CASE-MISS-UI", assigned_to="auth_1")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_1", UserRole.AUTHORITY.value, ["cases:read"])
    client = TestClient(app)
    try:
        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-MISS-UI")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "missing_evidence" in data
        assert isinstance(data["missing_evidence"], list)
    finally:
        app.dependency_overrides.clear()


def test_14_authority_review_recommendation(setup_m107_env):
    """Authority marks recommendation reviewed; case lifecycle status remains unchanged."""
    case = _make_case("CASE-REV-01", assigned_to="auth_reviewer", status_val="under_review")
    setup_m107_env["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: _auth("auth_reviewer", UserRole.AUTHORITY.value, ["cases:read", "cases:write"])
    client = TestClient(app)
    try:
        payload = {
            "review_status": "REVIEWED",
            "review_notes": "Reviewed on-site priority. Barricading crew dispatched.",
            "decision_action_taken": "DISPATCH_SAFETY_BARRIER",
        }
        resp = client.post(f"{settings.API_V1_STR}/decision-support/cases/CASE-REV-01/review", json=payload)
        assert resp.status_code == status.HTTP_200_OK
        res_data = resp.json()
        assert res_data["status"] == "SUCCESS"
        assert res_data["review_status"] == "REVIEWED"
        assert res_data["reviewer_id"] == "auth_reviewer"
        assert res_data["case_status_unchanged"] == "under_review"

        # Verify case status was NOT mutated
        c = setup_m107_env["case_repo"].get("CASE-REV-01")
        assert c.status == "under_review"
    finally:
        app.dependency_overrides.clear()
