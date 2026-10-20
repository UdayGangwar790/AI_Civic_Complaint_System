"""
CVKI - Civic Vision & Knowledge Intelligence
M10 Batch 1 End-to-End Integration Test Suite
Verifies complete flow across M10.2 (Gateway) -> M10.3 (Playbooks) -> M10.4 (Decision Support)
with M9 (Multimodal), M8 (CV SPI), M6.4 (Provenance), and M6.5 (Knowledge Graph).
"""

from datetime import datetime, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.decision_support import (
    DecisionContext,
    DecisionEvidenceQuality,
    DecisionSupportResult,
)
from app.schemas.multimodal_gateway import MultimodalGatewayRequest
from app.services.action_playbook import get_action_playbook_registry
from app.services.complaint_case import (
    ComplaintCase,
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.decision_support import get_decision_support_engine
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.multimodal_gateway import get_multimodal_gateway_service


CITIZEN_1 = AuthenticatedUser(user_id="user_cit_e2e", email="cit_e2e@cvki.gov.in", role=UserRole.CITIZEN.value)
AUTHORITY_1 = AuthenticatedUser(user_id="user_auth_e2e", email="auth_e2e@cvki.gov.in", role=UserRole.AUTHORITY.value)
ADMIN_1 = AuthenticatedUser(user_id="user_admin_e2e", email="admin_e2e@cvki.gov.in", role=UserRole.ADMIN.value)


@pytest.fixture(autouse=True)
def setup_integration_env():
    orig_repo = complaint_case_module.case_repository
    mem_repo = InMemoryComplaintCaseRepository()
    set_case_repository(mem_repo)
    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    yield mem_repo
    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def _make_e2e_case(reference_id="CASE-E2E-001", user_id="user_cit_e2e", assigned_to="user_auth_e2e", priority="P2"):
    return ComplaintCase(
        reference_id=reference_id,
        user_id=user_id,
        status="submitted_to_cvki",
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": "open_damaged_manhole",
            "label": "Open Manhole",
            "severity": "high",
            "confidence": 0.89,
        },
        location={"latitude": 12.9716, "longitude": 77.5946, "city": "Bengaluru"},
        authority={
            "authority_status": "verified",
            "maintenance_authority": {"name": "BBMP Road Infrastructure Cell", "type": "Municipal"},
        },
        complaint={
            "title": "Sadak pe khula manhole",
            "description": "Sadak pe bohot bada khula manhole hai bohot khatra hai",
            "language": "hi",
        },
        follow_up={"guidance": "Persisted in CVKI repository."},
        assignment={"assigned_to_user_id": assigned_to} if assigned_to else None,
        priority_analysis={
            "priority_score": 85,
            "priority_level": priority,
            "risk_level": "High" if priority in ("P1", "P2") else "Medium",
        },
        recurrence_analysis={
            "recurrence_detected": True,
            "recurrence_count": 2,
            "recurrence_explanation": "Repeated manhole defect reports at junction",
        },
    )


def test_e2e_full_pipeline_citizen_to_decision_support(setup_integration_env):
    """
    Complete end-to-end trace:
    1. Case created in CVKI with Hinglish complaint text.
    2. Case analyzed through Multimodal Gateway:
       - M9.4 Normalizer translates/normalizes vernacular text.
       - M8 CV detection matches the defect.
       - M9.2 Consistency engine verifies alignment.
       - M9.6 Provenance and Knowledge Graph claims are linked.
    3. Decision Support evaluated for the case:
       - M10.3 Action Playbook matched (PB-MANHOLE-SAFETY-V1).
       - M10.4 Decision Support synthesizes full evidence context into explainable guidance.
       - Human review reasons populated.
       - Epistemic invariants verified (SYSTEM_DERIVED, no auto-resolve).
    """
    case = _make_e2e_case()
    setup_integration_env.save(case)

    client = TestClient(app)

    # Step 1: Multimodal Gateway Analysis
    det = StandardDetectionResult(
        success=True,
        detections=[
            StandardDetection(
                class_id=0,
                class_name="open_damaged_manhole",
                confidence=0.89,
                bbox=StandardBoundingBox(x1=25, y1=25, x2=220, y2=220),
            )
        ],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )

    mm_resp = client.post(
        f"{settings.API_V1_STR}/multimodal/cases/CASE-E2E-001/analyze",
        json={
            "text": "Sadak pe bohot bada khula manhole hai bohot khatra hai",
            "language_hint": "hi",
            "detection_result": det.model_dump(mode="json"),
        },
    )
    assert mm_resp.status_code == status.HTTP_200_OK
    mm_data = mm_resp.json()

    assert mm_data["normalized_text"] is not None
    assert "manhole" in mm_data["normalized_text"].lower()
    assert mm_data["epistemic_state"] == EpistemicState.SYSTEM_DERIVED.value
    assert len(mm_data["provenance_claims"]) > 0
    assert len(mm_data["kg_node_keys"]) > 0

    # Step 2: Decision Support Retrieval
    ds_resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-E2E-001")
    assert ds_resp.status_code == status.HTTP_200_OK
    ds_data = ds_resp.json()

    # Verify decision support output structure and values
    assert ds_data["case_reference"] == "CASE-E2E-001"
    assert any("PB-MANHOLE-SAFETY-V1" in pb for pb in ds_data["matched_playbooks"])
    assert ds_data["epistemic_state"] == EpistemicState.SYSTEM_DERIVED.value
    assert ds_data["human_review_required"] is True
    assert len(ds_data["recommended_actions"]) > 0
    assert len(ds_data["required_inspection"]) > 0
    assert "P2" in ds_data["explanation"]


def test_e2e_authority_evaluate_custom_context(setup_integration_env):
    """
    Verify authority officer can re-evaluate case decision support with weather context,
    while server-enforced priority tier cannot be forged or overridden.
    """
    case = _make_e2e_case(reference_id="CASE-E2E-AUTH", priority="P3")
    setup_integration_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)

    # Authority submits weather update and spoofed priority P1
    resp = client.post(
        f"{settings.API_V1_STR}/decision-support/cases/CASE-E2E-AUTH/evaluate",
        json={
            "priority_level": "P1",  # Spoofed - must be ignored
            "weather_condition": "Monsoon downpour flood warning",
            "traffic_level": "heavy",
        },
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # Weather context reflected
    assert "Monsoon downpour" in data["explanation"]
    # Priority preserved as server truth P2/P3 (from case)
    assert "P3" in data["explanation"]
    assert data["epistemic_state"] == EpistemicState.SYSTEM_DERIVED.value


def test_e2e_epistemic_invariants_across_all_modules():
    """
    Verify epistemic invariants hold across all M10 Batch 1 components:
    - Never declares physical ground truth.
    - Never auto-resolves or marks cases closed.
    - All outputs labeled SYSTEM_DERIVED.
    """
    registry = get_action_playbook_registry()
    playbooks = registry.list_playbooks()

    for pb in playbooks:
        # Check that no action item purports to close or auto-resolve
        for item in pb.recommended_actions + pb.mitigation_actions:
            assert "close" not in item.title.lower()
            assert "auto_resolve" not in item.action_id.lower()
            assert "CVKI" in item.epistemic_tag

        # Check prohibited assumptions exist
        assert len(pb.prohibited_assumptions) > 0

    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-INV-001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    res = engine.evaluate_case(ctx)
    assert res.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert res.human_review_required is True
    assert any("guidance" in u.lower() or "do not constitute an official municipal order" in u.lower() for u in res.uncertainty)
