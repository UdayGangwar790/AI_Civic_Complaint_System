"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.2: Multimodal REST API Gateway Test Suite
"""

from datetime import datetime, timezone
import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.api.v1.multimodal import router as multimodal_router
from app.core.config import settings
from app.models.roles import UserRole
from app.schemas.complaint_case import ComplaintCase
from app.schemas.multimodal_gateway import (
    MultimodalGatewayRequest,
    MultimodalGatewayResponse,
)
from app.services.complaint_case import case_repository
from app.services.multimodal.contracts import (
    AlignmentState,
    ClarificationStatus,
    EpistemicState,
    IssueCategory,
    MultimodalLocationContext,
    ResolutionAuditOutcome,
)
from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.multimodal_gateway import get_multimodal_gateway_service

# Build isolated test FastAPI app
app = FastAPI()
app.include_router(multimodal_router, prefix=f"{settings.API_V1_STR}/multimodal")

# Test users
CITIZEN_USER = AuthenticatedUser(
    user_id="user_cit_1",
    email="citizen@example.com",
    role=UserRole.CITIZEN.value,
)
OTHER_CITIZEN_USER = AuthenticatedUser(
    user_id="user_cit_2",
    email="other_citizen@example.com",
    role=UserRole.CITIZEN.value,
)
AUTHORITY_USER = AuthenticatedUser(
    user_id="user_auth_1",
    email="officer@bbmp.gov.in",
    role=UserRole.AUTHORITY.value,
)
OTHER_AUTHORITY_USER = AuthenticatedUser(
    user_id="user_auth_2",
    email="other_officer@bbmp.gov.in",
    role=UserRole.AUTHORITY.value,
)
ADMIN_USER = AuthenticatedUser(
    user_id="user_admin_1",
    email="admin@cvki.gov.in",
    role=UserRole.ADMIN.value,
)


from app.services.complaint_case import (
    InMemoryComplaintCaseRepository,
    set_case_repository,
    case_repository,
)
import app.services.complaint_case as complaint_case_module

@pytest.fixture(autouse=True)
def setup_test_env():
    orig_repo = complaint_case_module.case_repository
    mem_repo = InMemoryComplaintCaseRepository()
    set_case_repository(mem_repo)
    app.dependency_overrides[get_current_user] = lambda: CITIZEN_USER
    yield mem_repo
    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def _make_dummy_case(reference_id="CASE-MM-001", user_id="user_cit_1", assigned_to="user_auth_1"):
    return ComplaintCase(
        reference_id=reference_id,
        user_id=user_id,
        status="submitted_to_cvki",
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": "open_damaged_manhole",
            "label": "Open Manhole",
            "severity": "medium",
            "confidence": 0.88,
        },
        location={"latitude": 12.9716, "longitude": 77.5946, "city": "Bengaluru"},
        authority={
            "authority_name": "BBMP",
            "confidence": 0.9,
            "verified": True,
            "authority_status": "verified",
        },
        complaint={"title": "Open manhole", "description": "Dangerous open manhole on 5th main", "language": "en"},
        follow_up={"guidance": "Saved in CVKI."},
        assignment={"assigned_to_user_id": assigned_to} if assigned_to else None,
    )


def test_1_authentication_required():
    """Verify endpoint rejects unauthenticated requests."""
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.post(f"{settings.API_V1_STR}/multimodal/analyze", json={"text": "hello"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_2_rbac_citizen_access():
    """Verify citizen role can access standalone analyze endpoint."""
    client = TestClient(app)
    resp = client.post(f"{settings.API_V1_STR}/multimodal/analyze", json={"text": "Road has broken manhole"})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["epistemic_state"] == EpistemicState.SYSTEM_DERIVED.value


def test_3_citizen_ownership_enforcement(setup_test_env):
    """Verify citizen cannot analyze a case owned by another citizen."""
    case = _make_dummy_case(reference_id="CASE-MM-OWNER", user_id="user_cit_2")
    setup_test_env.save(case)

    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/cases/CASE-MM-OWNER/analyze",
        json={"text": "Check status"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_4_authority_assignment_enforcement(setup_test_env):
    """Verify authority can only analyze cases assigned to them."""
    case = _make_dummy_case(reference_id="CASE-MM-AUTH", user_id="user_cit_1", assigned_to="user_auth_1")
    setup_test_env.save(case)

    # Authorized authority
    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_USER
    client = TestClient(app)
    resp = client.post(f"{settings.API_V1_STR}/multimodal/cases/CASE-MM-AUTH/analyze", json={})
    assert resp.status_code == status.HTTP_200_OK

    # Unassigned authority
    app.dependency_overrides[get_current_user] = lambda: OTHER_AUTHORITY_USER
    resp_unauth = client.post(f"{settings.API_V1_STR}/multimodal/cases/CASE-MM-AUTH/analyze", json={})
    assert resp_unauth.status_code == status.HTTP_403_FORBIDDEN


def test_5_admin_unrestricted_access(setup_test_env):
    """Verify admin role can analyze any case."""
    case = _make_dummy_case(reference_id="CASE-MM-ADMIN", user_id="user_cit_99")
    setup_test_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    client = TestClient(app)
    resp = client.post(f"{settings.API_V1_STR}/multimodal/cases/CASE-MM-ADMIN/analyze", json={})
    assert resp.status_code == status.HTTP_200_OK


def test_6_invalid_payload_handling():
    """Verify malformed JSON or invalid types return 422."""
    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/analyze",
        json={"detection_result": "not_an_object"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_7_oversized_text_handling():
    """Verify text exceeding 2000 chars is rejected."""
    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/analyze",
        json={"text": "a" * 2500},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_8_missing_evidence_warning():
    """Verify request with empty text and no detection returns warning."""
    client = TestClient(app)
    resp = client.post(f"{settings.API_V1_STR}/multimodal/analyze", json={})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert any("neither text description nor visual detection" in w for w in data["warnings"])


def test_9_m94_vernacular_normalization_integration():
    """Verify Hinglish vernacular text is properly normalized through the gateway."""
    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/analyze",
        json={"text": "sadak pe khula manhole hai bohot khatra", "language_hint": "hi"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["normalized_text"] is not None
    assert "manhole" in data["normalized_text"].lower()
    assert data["vernacular_result"]["detected_language"] in ("hi", "hinglish")


def test_10_m92_consistency_alignment_integration():
    """Verify cross-modal consistency evaluation executes and returns alignment assessment."""
    det = StandardDetectionResult(
        success=True,
        detections=[
            StandardDetection(
                class_id=0,
                class_name="open_damaged_manhole",
                confidence=0.85,
                bbox=StandardBoundingBox(x1=10, y1=10, x2=100, y2=100),
            )
        ],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )
    req = MultimodalGatewayRequest(
        text="There is a dangerous open manhole in the middle of the street",
        detection_result=det,
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    svc = get_multimodal_gateway_service()
    res = svc.process(req)
    assert res.alignment_assessment is not None
    assert res.alignment_assessment.state in (AlignmentState.ALIGNED, AlignmentState.PARTIALLY_ALIGNED)


def test_11_m93_active_clarification_integration():
    """Verify ambiguity triggers active clarification questions in gateway response."""
    det = StandardDetectionResult(
        success=True,
        detections=[
            StandardDetection(
                class_id=0,
                class_name="open_damaged_manhole",
                confidence=0.45,
                bbox=StandardBoundingBox(x1=10, y1=10, x2=100, y2=100),
            )
        ],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )
    # Contradictory text mentioning waterlogging
    req = MultimodalGatewayRequest(
        text="Severe waterlogging on the road completely flooded",
        detection_result=det,
        issue_category=IssueCategory.ROAD_WATERLOGGING,
    )
    svc = get_multimodal_gateway_service()
    res = svc.process(req)
    assert res.clarification_result is not None
    assert res.clarification_result.status == ClarificationStatus.QUESTION_PRESENTED


def test_12_m95_visual_resolution_audit_integration():
    """Verify before/after image pairs execute visual resolution auditing."""
    before_det = StandardDetectionResult(
        success=True,
        detections=[
            StandardDetection(
                class_id=0,
                class_name="open_damaged_manhole",
                confidence=0.90,
                bbox=StandardBoundingBox(x1=20, y1=20, x2=200, y2=200),
            )
        ],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )
    after_det = StandardDetectionResult(
        success=True,
        detections=[],  # Cleaned / repaired
        total_detections=0,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )
    req = MultimodalGatewayRequest(
        case_reference="CASE-AUDIT-001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        before_image_path="ev_before.jpg",
        after_image_path="ev_after.jpg",
        before_detection=before_det,
        after_detection=after_det,
    )
    svc = get_multimodal_gateway_service()
    res = svc.process(req)
    assert res.visual_audit_result is not None
    assert res.visual_audit_result.outcome == ResolutionAuditOutcome.DEFECT_NOT_OBSERVED


def test_13_provenance_integration(setup_test_env):
    """Verify provenance claims are captured and listed in gateway response."""
    case = _make_dummy_case(reference_id="CASE-PROV-001", user_id="user_cit_1")
    setup_test_env.save(case)

    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/cases/CASE-PROV-001/analyze",
        json={"text": "sadak pe khula dhakkan hai", "language_hint": "hi"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert len(data["provenance_claims"]) > 0


def test_14_knowledge_graph_integration(setup_test_env):
    """Verify knowledge graph node keys are captured during case analysis."""
    case = _make_dummy_case(reference_id="CASE-KG-001", user_id="user_cit_1")
    setup_test_env.save(case)

    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/cases/CASE-KG-001/analyze",
        json={"text": "manhole cover broken", "language_hint": "en"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert len(data["kg_node_keys"]) > 0


def test_15_epistemic_state_preservation():
    """Verify epistemic state is strictly SYSTEM_DERIVED and cannot be overridden."""
    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/analyze",
        json={"text": "test complaint", "metadata": {"epistemic_state": "GROUND_TRUTH"}},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["epistemic_state"] == EpistemicState.SYSTEM_DERIVED.value


def test_16_no_duplicate_evidence_recording():
    """Verify executing analyze repeatedly on identical input does not fail."""
    svc = get_multimodal_gateway_service()
    req = MultimodalGatewayRequest(
        case_reference="CASE-IDEMPOTENT-001",
        text="dangerous open manhole",
    )
    res1 = svc.process(req)
    res2 = svc.process(req)
    assert res1.normalized_text == res2.normalized_text
    assert res1.epistemic_state == res2.epistemic_state


def test_17_no_cross_tenant_leakage(setup_test_env):
    """Verify user cannot specify another user's case in standalone analyze route."""
    case = _make_dummy_case(reference_id="CASE-TENANT-001", user_id="user_cit_2")
    setup_test_env.save(case)

    # user_cit_1 tries to analyze CASE-TENANT-001
    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/analyze",
        json={"case_reference": "CASE-TENANT-001", "text": "tamper attempt"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_18_backward_compatibility():
    """Verify MultimodalGatewayRequest without new before/after fields operates normally."""
    req = MultimodalGatewayRequest(text="Standard single description")
    svc = get_multimodal_gateway_service()
    res = svc.process(req)
    assert res.visual_audit_result is None
    assert res.normalized_text is not None


def test_19_error_handling_case_not_found():
    """Verify analyzing non-existent case returns 404."""
    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/multimodal/cases/NON-EXISTENT-CASE/analyze",
        json={"text": "hello"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_20_deterministic_output():
    """Verify identical inputs yield identical normalization and alignment results."""
    svc = get_multimodal_gateway_service()
    req = MultimodalGatewayRequest(
        text="raaste pe paani bhar gaya hai",
        language_hint="hi",
        issue_category=IssueCategory.ROAD_WATERLOGGING,
    )
    res_a = svc.process(req)
    res_b = svc.process(req)
    assert res_a.normalized_text == res_b.normalized_text
    assert res_a.alignment_assessment.state == res_b.alignment_assessment.state
    assert res_a.ambiguity_assessment.state == res_b.ambiguity_assessment.state
