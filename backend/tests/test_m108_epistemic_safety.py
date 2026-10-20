"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.8: Epistemic Safety Invariant Test Suite
"""

import pytest
from datetime import datetime, timezone
from typing import Optional
from fastapi import status
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.decision_support import DecisionContext, DecisionEvidenceQuality
from app.schemas.provenance import ClaimType, SourceType, VerificationState
from app.services.complaint_case import (
    ComplaintCase,
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
from app.services.decision_support import get_decision_support_engine
from app.services.field_inspection import (
    FieldInspectionSubmissionRequest,
    InspectionObservationItem,
    get_audit_engine,
    get_field_inspection_repository,
    get_protocol_generator,
)
from app.services.decision_projection import get_decision_projector
from app.services.provenance_engine import get_provenance_engine
from app.services.cv.base_provider import StandardBoundingBox, StandardDetection, StandardDetectionResult
from app.services.multimodal.contracts import EpistemicState, IssueCategory


CITIZEN_1 = AuthenticatedUser(user_id="user_cit_1", email="cit1@cvki.gov.in", role=UserRole.CITIZEN.value)
AUTHORITY_1 = AuthenticatedUser(user_id="user_auth_1", email="auth1@cvki.gov.in", role=UserRole.AUTHORITY.value)


@pytest.fixture(autouse=True)
def setup_epistemic_env():
    orig_repo = complaint_case_module.case_repository
    mem_repo = InMemoryComplaintCaseRepository()
    set_case_repository(mem_repo)

    insp_repo = get_field_inspection_repository()
    insp_repo.clear()

    yield mem_repo
    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def _make_case(
    reference_id: str = "CASE-EPI-001",
    user_id: str = "user_cit_1",
    assigned_to: str = "user_auth_1",
    class_name: str = "open_damaged_manhole",
    status: str = "in_progress",
    status_val: Optional[str] = None,
    tenant_id: str = "tenant_a",
) -> ComplaintCase:
    effective_status = status_val or status
    return ComplaintCase(
        reference_id=reference_id,
        user_id=user_id,
        status=effective_status,
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": class_name,
            "label": "Open Manhole",
            "severity": "high",
            "confidence": 0.95,
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


def test_01_model_observation_cannot_become_verified_evidence():
    """1. High-confidence CV detection remains MODEL_OBSERVATION and never VERIFIED_EVIDENCE."""
    det = StandardDetection(
        class_id=0,
        class_name="open_damaged_manhole",
        confidence=0.99,
        bbox=StandardBoundingBox(x1=0, y1=0, x2=1, y2=1),
    )
    res = StandardDetectionResult(
        success=True,
        detections=[det],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )
    ctx = DecisionContext(
        case_reference="CASE-01",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=res,
    )
    engine = get_decision_support_engine()
    decision = engine.evaluate_case(ctx)
    assert decision.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert decision.epistemic_state != EpistemicState.VERIFIED_EVIDENCE


def test_02_citizen_clarification_remains_user_reported(setup_epistemic_env):
    """2. Citizen clarification answer is strictly tagged USER_REPORTED in Provenance."""
    case = _make_case("CASE-CLAR-EPI", user_id="user_cit_1")
    setup_epistemic_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    resp = client.post(
        f"{settings.API_V1_STR}/decision-support/cases/CASE-CLAR-EPI/clarify",
        json={"question_id": "q_clar_01", "free_text": "The lid is entirely missing from the frame."},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["epistemic_state"] == EpistemicState.USER_REPORTED.value

    # Verify in Provenance records
    prov_engine = get_provenance_engine()
    records = prov_engine.repository.find_by_case("CASE-CLAR-EPI")
    assert any(
        r.verification_state == VerificationState.NOT_VERIFIED and
        r.metadata.get("epistemic_state") == EpistemicState.USER_REPORTED.value
        for r in records
    )


def test_03_system_derived_recommendation_never_asserts_ground_truth():
    """3. Decision support recommendation is explicitly tagged SYSTEM_DERIVED and human review is required."""
    ctx = DecisionContext(
        case_reference="CASE-SYS-01",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        citizen_text="Manhole missing lid",
    )
    engine = get_decision_support_engine()
    decision = engine.evaluate_case(ctx)

    assert decision.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert decision.human_review_required is True
    assert "operational decision support" in decision.explanation.lower()


def test_04_field_inspection_audit_cannot_mutate_case_lifecycle(setup_epistemic_env):
    """4. Submitting a confirmed field inspection audit does NOT mutate the case status."""
    case = _make_case("CASE-INSP-STATUS", status="in_progress", assigned_to="user_auth_1")
    setup_epistemic_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)

    resp = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-INSP-STATUS/submit",
        json={
            "protocol_id": "PROTOCOL-MANHOLE-V1",
            "protocol_version": "1.0.0",
            "observations": [
                {"step_id": "STEP-MANHOLE-01", "observation_text": "Confirmed physical defect", "defect_confirmed": True}
            ],
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED

    fresh_case = setup_epistemic_env.get("CASE-INSP-STATUS")
    assert fresh_case.status == "in_progress"
    assert fresh_case.status != "resolved"
    assert fresh_case.status != "closed"


def test_05_government_resolved_status_cannot_close_case(setup_epistemic_env):
    """5. An external government status observation 'RESOLVED' does NOT automatically close CVKI case."""
    case = _make_case("CASE-GOV-STATUS", status="in_progress")
    setup_epistemic_env.save(case)

    ctx = DecisionContext(
        case_reference="CASE-GOV-STATUS",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        government_status="RESOLVED",
    )
    engine = get_decision_support_engine()
    decision = engine.evaluate_case(ctx)

    assert decision.human_review_required is True
    assert any("government" in r.lower() or "physical" in r.lower() or "verification" in r.lower() for r in decision.human_review_reasons)

    case_in_db = setup_epistemic_env.get("CASE-GOV-STATUS")
    assert case_in_db.status == "in_progress"


def test_06_weather_evidence_cannot_create_causal_claims():
    """6. Contextual weather evidence cannot claim causal defect creation, only contextual risk."""
    ctx = DecisionContext(
        case_reference="CASE-WEATHER-01",
        issue_category=IssueCategory.ROAD_WATERLOGGING,
        weather_condition="heavy rain",
    )
    engine = get_decision_support_engine()
    decision = engine.evaluate_case(ctx)

    assert "environmental context" in decision.explanation.lower()
    assert "causality not inferred" in decision.explanation.lower()
    assert decision.epistemic_state == EpistemicState.SYSTEM_DERIVED


def test_07_cv_confidence_cannot_be_interpreted_as_severity():
    """7. Low severity issue with 0.99 CV confidence remains low severity (confidence != severity)."""
    det = StandardDetection(
        class_id=1,
        class_name="damaged_missing_road_sign",
        confidence=0.99,  # Very high confidence
        bbox=StandardBoundingBox(x1=0, y1=0, x2=1, y2=1),
    )
    res = StandardDetectionResult(
        success=True,
        detections=[det],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )
    ctx = DecisionContext(
        case_reference="CASE-SEV-01",
        issue_category=IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
        detection_result=res,
        priority_level="P4",  # Low priority defect
    )
    engine = get_decision_support_engine()
    decision = engine.evaluate_case(ctx)

    # High confidence does not falsely promote P4 to emergency P1
    assert decision.evidence_quality in (DecisionEvidenceQuality.STRONG, DecisionEvidenceQuality.PARTIAL)
    assert not any("emergency" in a.title.lower() for a in decision.recommended_actions)


def test_08_recommendation_disclaimer_and_non_statutory_boundary(setup_epistemic_env):
    """8. Citizen and Authority interfaces present explicit statutory advisory disclaimers."""
    case = _make_case("CASE-DISC-01", user_id="user_cit_1")
    setup_epistemic_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-DISC-01/citizen-view")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "disclaimer" in data
    assert "statutory" in data["disclaimer"].lower() or "advisory" in data["disclaimer"].lower()


def test_09_human_review_required_invariant():
    """9. human_review_required must remain True on all generated decision support outputs."""
    engine = get_decision_support_engine()

    for category in [
        IssueCategory.OPEN_DAMAGED_MANHOLE,
        IssueCategory.ROAD_WATERLOGGING,
        IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
        IssueCategory.OTHER_CIVIC_ISSUE,
    ]:
        ctx = DecisionContext(case_reference=f"CASE-{category.value}", issue_category=category)
        decision = engine.evaluate_case(ctx)
        assert decision.human_review_required is True, f"human_review_required failed for {category}"
        assert len(decision.human_review_reasons) > 0


def test_10_evidence_invalidation_propagates_to_dependent_recommendations(setup_epistemic_env):
    """10. When supporting evidence is absent or conflicting, evidence quality downgrades."""
    engine = get_decision_support_engine()

    # Conflicting evidence: CV sees manhole, but text insists on clear sidewalk
    det = StandardDetection(
        class_id=0,
        class_name="open_damaged_manhole",
        confidence=0.90,
        bbox=StandardBoundingBox(x1=0, y1=0, x2=1, y2=1),
    )
    res = StandardDetectionResult(
        success=True,
        detections=[det],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )
    ctx = DecisionContext(
        case_reference="CASE-CONF-01",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=res,
        citizen_text="The street is completely clear and newly paved, no potholes or open manholes anywhere.",
        alignment_score=0.15,
        clarification_needed=True,
    )
    decision = engine.evaluate_case(ctx)

    # Downgrades evidence quality to CONFLICTING
    assert decision.evidence_quality == DecisionEvidenceQuality.CONFLICTING
    assert any("conflict" in u.lower() or "divergence" in r.lower() for u in decision.uncertainty for r in decision.human_review_reasons)
