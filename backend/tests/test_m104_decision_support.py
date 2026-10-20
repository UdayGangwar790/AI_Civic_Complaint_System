"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.4: Evidence-Aware Decision Support Engine Tests
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
from app.services.decision_support import (
    CivicDecisionSupportEngine,
    get_decision_support_engine,
)
from app.services.multimodal.contracts import EpistemicState, IssueCategory


CITIZEN_1 = AuthenticatedUser(user_id="user_cit_1", email="cit1@cvki.gov.in", role=UserRole.CITIZEN.value)
CITIZEN_2 = AuthenticatedUser(user_id="user_cit_2", email="cit2@cvki.gov.in", role=UserRole.CITIZEN.value)
AUTHORITY_1 = AuthenticatedUser(user_id="user_auth_1", email="auth1@cvki.gov.in", role=UserRole.AUTHORITY.value)
ADMIN_1 = AuthenticatedUser(user_id="user_admin_1", email="admin@cvki.gov.in", role=UserRole.ADMIN.value)


@pytest.fixture(autouse=True)
def setup_decision_support_env():
    orig_repo = complaint_case_module.case_repository
    mem_repo = InMemoryComplaintCaseRepository()
    set_case_repository(mem_repo)
    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    yield mem_repo
    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def _make_case(reference_id="CASE-DS-001", user_id="user_cit_1", assigned_to="user_auth_1", class_name="open_damaged_manhole", priority="P2"):
    return ComplaintCase(
        reference_id=reference_id,
        user_id=user_id,
        status="submitted_to_cvki",
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": class_name,
            "label": "Open Manhole",
            "severity": "high",
            "confidence": 0.88,
        },
        location={"latitude": 12.9716, "longitude": 77.5946, "city": "Bengaluru"},
        authority={
            "authority_name": "BBMP",
            "confidence": 0.9,
            "verified": True,
            "authority_status": "verified",
        },
        complaint={"title": "Hazardous road issue", "description": "Large dangerous opening", "language": "en"},
        follow_up={"guidance": "Saved in CVKI."},
        assignment={"assigned_to_user_id": assigned_to} if assigned_to else None,
        priority_analysis={
            "priority_score": 82,
            "priority_level": priority,
            "risk_level": "High" if priority in ("P1", "P2") else "Medium",
        } if priority else None,
        recurrence_analysis={
            "recurrence_detected": True,
            "recurrence_count": 3,
            "recurrence_explanation": "Historical defect recurrence",
        } if priority == "P1" else None,
    )


def _make_cv_result(class_name="open_damaged_manhole", confidence=0.85):
    return StandardDetectionResult(
        success=True,
        detections=[
            StandardDetection(
                class_id=0,
                class_name=class_name,
                confidence=confidence,
                bbox=StandardBoundingBox(x1=10, y1=10, x2=100, y2=100),
            )
        ],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )


# --- 30 Required Tests ---

def test_1_strong_evidence_evaluation():
    """Verify strong evidence quality when both CV and aligned text are present."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=_make_cv_result(confidence=0.88),
        citizen_text="Dangerous open manhole on 5th cross road",
        alignment_score=0.85,
    )
    res = engine.evaluate_case(ctx)
    assert res.evidence_quality == DecisionEvidenceQuality.STRONG
    assert len(res.recommended_actions) > 0
    assert any("PB-MANHOLE-SAFETY-V1" in pb for pb in res.matched_playbooks)


def test_2_partial_evidence_cv_only():
    """Verify partial evidence quality when only CV detection is available."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-002",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=_make_cv_result(confidence=0.85),
    )
    res = engine.evaluate_case(ctx)
    assert res.evidence_quality == DecisionEvidenceQuality.PARTIAL
    assert any("visual evidence present without accompanying citizen context" in r.lower() for r in res.human_review_reasons)


def test_3_partial_evidence_text_only():
    """Verify partial evidence quality when only citizen text is available."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-003",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        citizen_text="There is a deep manhole cover missing here",
    )
    res = engine.evaluate_case(ctx)
    assert res.evidence_quality == DecisionEvidenceQuality.PARTIAL
    assert "photographic_cv_detection" in res.missing_evidence


def test_4_missing_evidence_both_absent():
    """Verify missing evidence quality when neither CV nor text is provided."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-004",
        issue_category=IssueCategory.UNKNOWN,
    )
    res = engine.evaluate_case(ctx)
    assert res.evidence_quality == DecisionEvidenceQuality.MISSING
    assert any("both visual defect imagery and descriptive complaint text are absent" in r.lower() for r in res.human_review_reasons)


def test_5_conflicting_evidence():
    """Verify conflicting evidence quality when alignment score indicates divergence."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-005",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=_make_cv_result(),
        citizen_text="The entire street is flooded with knee deep water",
        alignment_score=0.20,
    )
    res = engine.evaluate_case(ctx)
    assert res.evidence_quality == DecisionEvidenceQuality.CONFLICTING
    assert any("cross-modal divergence" in r.lower() for r in res.human_review_reasons)


def test_6_weak_evidence():
    """Verify weak evidence quality when CV detection confidence is very low."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-006",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=_make_cv_result(confidence=0.25),
    )
    res = engine.evaluate_case(ctx)
    assert res.evidence_quality == DecisionEvidenceQuality.WEAK
    assert any("confidence is below operational threshold" in r.lower() for r in res.human_review_reasons)


def test_7_manhole_playbook_matching():
    """Verify manhole category matches safety playbook with barricade mitigation."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-007",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=_make_cv_result(),
    )
    res = engine.evaluate_case(ctx)
    assert any("PB-MANHOLE-SAFETY-V1" in pb for pb in res.matched_playbooks)
    assert any("barricade" in a.title.lower() for a in res.mitigation_actions)


def test_8_waterlogging_playbook_matching():
    """Verify waterlogging category matches drainage playbook."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-008",
        issue_category=IssueCategory.ROAD_WATERLOGGING,
        detection_result=_make_cv_result(class_name="road_waterlogging"),
    )
    res = engine.evaluate_case(ctx)
    assert any("PB-WATERLOGGING-DRAIN-V1" in pb for pb in res.matched_playbooks)
    assert any("inlet" in a.title.lower() or "drain" in a.title.lower() for a in res.recommended_actions)


def test_9_road_sign_playbook_matching():
    """Verify road sign category matches sign hazard playbook."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-009",
        issue_category=IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
        detection_result=_make_cv_result(class_name="damaged_road_sign"),
    )
    res = engine.evaluate_case(ctx)
    assert any("PB-ROAD-SIGN-HAZARD-V1" in pb for pb in res.matched_playbooks)
    assert any("pole" in cp.lower() or "sightline" in cp.lower() or "stability" in cp.lower() or "deflection" in cp.lower() for cp in res.required_inspection)


def test_10_generic_fallback_playbook():
    """Verify unknown category falls back to generic playbook with baseline inspection."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-010",
        issue_category=IssueCategory.UNKNOWN,
    )
    res = engine.evaluate_case(ctx)
    assert any("PB-GENERIC-CIVIC-V1" in pb for pb in res.matched_playbooks)
    assert any("baseline" in cp.lower() or "walkthrough" in cp.lower() or "confirm" in cp.lower() for cp in res.required_inspection)


def test_11_epistemic_state_always_system_derived():
    """Verify epistemic state is strictly SYSTEM_DERIVED on all results."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-011",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    res = engine.evaluate_case(ctx)
    assert res.epistemic_state == EpistemicState.SYSTEM_DERIVED


def test_12_never_claims_physical_ground_truth():
    """Verify caveats clearly assert recommendations do not claim physical ground truth."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-012",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    res = engine.evaluate_case(ctx)
    assert any("guidance" in u.lower() or "do not constitute an official municipal order" in u.lower() for u in res.uncertainty)


def test_13_never_automatically_resolves_case():
    """Verify no recommended or mitigation action purports to auto-resolve case."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-013",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=_make_cv_result(),
    )
    res = engine.evaluate_case(ctx)
    all_actions = res.recommended_actions + res.mitigation_actions
    for act in all_actions:
        assert "auto_resolve" not in act.action_id.lower()
        assert "close_complaint" not in act.action_id.lower()


def test_14_prohibited_assumptions_included():
    """Verify prohibited cognitive assumptions are communicated in uncertainties."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-014",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    res = engine.evaluate_case(ctx)
    assert any("prohibited assumption" in u.lower() for u in res.uncertainty)


def test_15_mandatory_human_review_flag():
    """Verify human_review_required flag is strictly True."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(case_reference="CASE-015", issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)
    res = engine.evaluate_case(ctx)
    assert res.human_review_required is True


def test_16_human_review_reasons_populated():
    """Verify human_review_reasons list is non-empty with clear justification."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(case_reference="CASE-016", issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)
    res = engine.evaluate_case(ctx)
    assert len(res.human_review_reasons) > 0


def test_17_recurrence_intelligence_boost():
    """Verify historical recurrence adds specific structural inspection checkpoint."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-017",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        is_recurrent=True,
        recurrence_count=4,
    )
    res = engine.evaluate_case(ctx)
    assert any("recurrence" in s.get("source", "").lower() for s in res.supporting_evidence)
    assert any("sub-base" in cp.lower() or "structural" in cp.lower() for cp in res.required_inspection)


def test_18_rain_environmental_context():
    """Verify recent precipitation context adds operational weather note."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-018",
        issue_category=IssueCategory.ROAD_WATERLOGGING,
        weather_condition="heavy monsoon rain shower",
    )
    res = engine.evaluate_case(ctx)
    assert any("weather" in s.get("source", "").lower() for s in res.supporting_evidence)
    assert "precipitation" in res.explanation.lower()


def test_19_priority_tier_explanation():
    """Verify assigned priority tier is transparently explained in explanation text."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-019",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        priority_level="P1",
    )
    res = engine.evaluate_case(ctx)
    assert "P1" in res.explanation
    assert "operational tier" in res.explanation.lower()


def test_20_unverified_authority_warning():
    """Verify unverified authority jurisdiction triggers a human review reason."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-020",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        authority_name="BBMP_StormWater",
        is_authority_verified=False,
    )
    res = engine.evaluate_case(ctx)
    assert any("jurisdictional authority" in r.lower() for r in res.human_review_reasons)


def test_21_external_government_status_context():
    """Verify external portal status is captured with caution note."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-021",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        government_status="work_order_generated",
    )
    res = engine.evaluate_case(ctx)
    assert "work_order_generated" in res.explanation
    assert "external claim" in res.explanation.lower()


def test_22_visual_audit_outcome_integration():
    """Verify visual resolution audit outcome triggers review when defect persists."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-022",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        visual_audit_outcome="DEFECT_PERSISTS",
    )
    res = engine.evaluate_case(ctx)
    assert any("DEFECT_PERSISTS" in r for r in res.human_review_reasons)


def test_23_clarification_pending_flag():
    """Verify pending ambiguity clarification flags uncertainty in decision support."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-023",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        clarification_needed=True,
    )
    res = engine.evaluate_case(ctx)
    assert any("ambiguity" in u.lower() for u in res.uncertainty)


def test_24_get_case_decision_support_api(setup_decision_support_env):
    """Verify GET /cases/{ref_id} retrieves synthesized decision support for case."""
    case = _make_case(reference_id="CASE-API-001", user_id="user_cit_1")
    setup_decision_support_env.save(case)

    client = TestClient(app)
    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-API-001")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["case_reference"] == "CASE-API-001"
    assert data["epistemic_state"] == EpistemicState.SYSTEM_DERIVED.value
    assert len(data["recommended_actions"]) > 0


def test_25_evaluate_case_api_strips_client_priority_override(setup_decision_support_env):
    """Verify POST /cases/{ref_id}/evaluate preserves server priority against client override."""
    case = _make_case(reference_id="CASE-API-002", user_id="user_cit_1", priority="P3")
    setup_decision_support_env.save(case)

    client = TestClient(app)
    # Client attempts to spoof priority to P1
    resp = client.post(
        f"{settings.API_V1_STR}/decision-support/cases/CASE-API-002/evaluate",
        json={"priority_level": "P1", "weather_condition": "rain storm"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    # Server-derived P3 should be preserved in the explanation
    assert "P3" in data["explanation"]
    assert "rain storm" in data["explanation"]


def test_26_rbac_citizen_access_own_case(setup_decision_support_env):
    """Verify citizen role can access decision support for their own case."""
    case = _make_case(reference_id="CASE-API-OWN", user_id="user_cit_1")
    setup_decision_support_env.save(case)

    client = TestClient(app)
    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-API-OWN")
    assert resp.status_code == status.HTTP_200_OK


def test_27_rbac_citizen_forbidden_other_case(setup_decision_support_env):
    """Verify citizen receives 403 trying to access another citizen's case."""
    case = _make_case(reference_id="CASE-API-OTHER", user_id="user_cit_2")
    setup_decision_support_env.save(case)

    client = TestClient(app)
    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-API-OTHER")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_28_rbac_authority_access_assigned_case(setup_decision_support_env):
    """Verify authority role can access assigned case."""
    case = _make_case(reference_id="CASE-API-ASSIGNED", user_id="user_cit_2", assigned_to="user_auth_1")
    setup_decision_support_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)
    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-API-ASSIGNED")
    assert resp.status_code == status.HTTP_200_OK


def test_29_rbac_admin_unrestricted_access(setup_decision_support_env):
    """Verify admin role can access any complaint case decision support."""
    case = _make_case(reference_id="CASE-API-ADMIN", user_id="user_cit_99")
    setup_decision_support_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: ADMIN_1
    client = TestClient(app)
    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-API-ADMIN")
    assert resp.status_code == status.HTTP_200_OK


def test_30_deterministic_evaluation():
    """Verify decision support engine produces deterministic output across runs."""
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CASE-DET-001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=_make_cv_result(),
        citizen_text="Open drain on sidewalk",
    )
    res1 = engine.evaluate_case(ctx)
    res2 = engine.evaluate_case(ctx)

    assert res1.evidence_quality == res2.evidence_quality
    assert res1.matched_playbooks == res2.matched_playbooks
    assert len(res1.recommended_actions) == len(res2.recommended_actions)
    assert len(res1.required_inspection) == len(res2.required_inspection)
