"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.9: End-to-End Integration Test Suite
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import status
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.decision_support import (
    CitizenClarifyRequest,
    DecisionContext,
    DecisionEvidenceQuality,
    RecommendationReviewRequest,
)
from app.schemas.field_inspection import (
    AuditOutcome,
    FieldInspectionSubmissionRequest,
    InspectionCompleteness,
    InspectionObservationItem,
)
from app.schemas.multimodal_gateway import MultimodalGatewayRequest
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
    calculate_evidence_hash,
)
from app.services.complaint_case import (
    ComplaintCase,
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
from app.services.cv.base_provider import StandardBoundingBox, StandardDetection, StandardDetectionResult
from app.services.decision_projection import get_decision_projector
from app.services.decision_support import get_decision_support_engine
from app.services.field_inspection import (
    get_audit_engine,
    get_field_inspection_repository,
    get_protocol_generator,
)
from app.services.knowledge_graph import get_knowledge_graph_service
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.multimodal_gateway import get_multimodal_gateway_service
from app.services.provenance_engine import get_provenance_engine


CITIZEN_1 = AuthenticatedUser(user_id="citizen_e2e_1", email="cit1@cvki.gov.in", role=UserRole.CITIZEN.value)
CITIZEN_2 = AuthenticatedUser(user_id="citizen_e2e_2", email="cit2@cvki.gov.in", role=UserRole.CITIZEN.value)
AUTHORITY_1 = AuthenticatedUser(user_id="auth_e2e_1", email="auth1@cvki.gov.in", role=UserRole.AUTHORITY.value)
AUTHORITY_2 = AuthenticatedUser(user_id="auth_e2e_2", email="auth2@cvki.gov.in", role=UserRole.AUTHORITY.value)
ADMIN_1 = AuthenticatedUser(user_id="admin_e2e_1", email="admin@cvki.gov.in", role=UserRole.ADMIN.value)


@pytest.fixture(autouse=True)
def setup_e2e_environment():
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

    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def _make_e2e_case(
    reference_id: str = "CASE-E2E-100",
    user_id: str = "citizen_e2e_1",
    assigned_to: str = "auth_e2e_1",
    class_name: str = "open_damaged_manhole",
    status_val: str = "in_progress",
    priority: str = "P1",
) -> ComplaintCase:
    return ComplaintCase(
        reference_id=reference_id,
        user_id=user_id,
        status=status_val,
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": class_name,
            "label": "Open Damaged Manhole",
            "severity": "high",
            "confidence": 0.92,
            "bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9},
        },
        location={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "road": "MG Road",
            "area": "Shivajinagar",
            "city": "Bengaluru",
        },
        authority={
            "authority_status": "verified",
            "maintenance_authority": {"name": "BBMP Stormwater", "type": "Municipal"},
        },
        complaint={"title": "Raste par khula gutter manhole", "description": "Bahut gehra aur khatarnak manhole khula hai", "language": "hi"},
        follow_up={"guidance": "Barricade immediately"},
        priority_analysis={
            "priority_level": priority,
            "priority_score": 90.0,
            "risk_level": "High",
        },
        assignment={"assigned_to_user_id": assigned_to} if assigned_to else None,
        metadata={"tenant_id": "bengaluru_bbmp"},
    )


# =========================================================================
# 10.9.1 PRIMARY FULL-PIPELINE E2E FLOW
# =========================================================================

def test_01_primary_e2e_full_lifecycle(setup_e2e_environment):
    """
    Executes the comprehensive E2E lifecycle across all CVKI modules:
    Citizen vernacular input -> M10.2 Gateway -> M9.4 Normalizer -> M8 CV ->
    M9.2 Consistency -> M9.3 Clarification -> M10.4 Decision Support ->
    M10.3 Playbook -> M10.5 Inspection Protocol -> M10.5 Audit ->
    M10.6 Projection -> M10.7 Review -> Citizen Clarification -> Context Update.
    """
    case_ref = "CASE-FULL-E2E"
    case = _make_e2e_case(reference_id=case_ref)
    setup_e2e_environment["case_repo"].save(case)

    # 1. Citizen submits multimodal intake through M10.2 Gateway
    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    gw_req = MultimodalGatewayRequest(
        case_reference=case_ref,
        text="Raste par khula manhole hai bahut khatarnak",
        language_hint="hi",
        before_image_path="evidence/baseline_manhole_01.jpg",
    )
    gw_resp = client.post(f"{settings.API_V1_STR}/multimodal/analyze", json=gw_req.model_dump(mode="json"))
    assert gw_resp.status_code == status.HTTP_200_OK
    gw_data = gw_resp.json()
    assert gw_data["normalized_text"] is not None
    assert gw_data["alignment_assessment"] is not None
    assert gw_data["epistemic_state"] == EpistemicState.SYSTEM_DERIVED.value

    # 2. Authority retrieves Decision Support recommendations (M10.4 + M10.3)
    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    dec_resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/{case_ref}")
    assert dec_resp.status_code == status.HTTP_200_OK
    dec_data = dec_resp.json()
    assert dec_data["epistemic_state"] == EpistemicState.SYSTEM_DERIVED.value
    assert dec_data["human_review_required"] is True
    assert len(dec_data["matched_playbooks"]) > 0
    assert any("PB-MANHOLE" in pb for pb in dec_data["matched_playbooks"])

    # 3. Field Inspector retrieves tailored inspection protocol (M10.5)
    proto_resp = client.get(f"{settings.API_V1_STR}/inspection/cases/{case_ref}/protocol")
    assert proto_resp.status_code == status.HTTP_200_OK
    proto_data = proto_resp.json()
    assert proto_data["issue_category"] == IssueCategory.OPEN_DAMAGED_MANHOLE.value
    assert len(proto_data["inspection_steps"]) >= 3

    # 4. Field Inspector conducts on-site check and submits report (M10.5)
    sub_payload = {
        "protocol_id": proto_data["protocol_id"],
        "protocol_version": proto_data["protocol_version"],
        "observations": [
            {"step_id": proto_data["inspection_steps"][0]["step_id"], "observation_text": "Manhole cover completely displaced", "defect_confirmed": True},
            {"step_id": proto_data["inspection_steps"][1]["step_id"], "observation_text": "Frame damaged along rim", "defect_confirmed": True},
            {"step_id": proto_data["inspection_steps"][2]["step_id"], "observation_text": "Temporary hazard cones placed", "defect_confirmed": True},
        ],
        "evidence_items": ["photo_manhole_field_01.jpg", "depth_measurement_01.jpg"],
        "location": {"latitude": 12.9716, "longitude": 77.5946},
        "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        "notes": "Traffic police alerted on site.",
    }
    insp_resp = client.post(f"{settings.API_V1_STR}/inspection/cases/{case_ref}/submit", json=sub_payload)
    assert insp_resp.status_code == status.HTTP_201_CREATED
    insp_data = insp_resp.json()
    assert insp_data["audit_result"]["outcome"] in (AuditOutcome.SUPPORTED.value, AuditOutcome.PARTIALLY_SUPPORTED.value)
    assert insp_data["audit_result"]["completeness"] in (InspectionCompleteness.COMPLETE.value, InspectionCompleteness.PARTIAL.value)

    # 5. Verify Decision & Inspection Projected into KG and Provenance (M10.6)
    prov_resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/{case_ref}/provenance")
    assert prov_resp.status_code == status.HTTP_200_OK
    prov_records = prov_resp.json()["provenance_records"]
    assert len(prov_records) >= 2

    graph_resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/{case_ref}/graph")
    assert graph_resp.status_code == status.HTTP_200_OK
    graph_data = graph_resp.json()
    node_types = {n.get("type") or n.get("node_type") for n in graph_data.get("nodes", [])}
    assert "case" in node_types or "decision_recommendation" in node_types

    # 6. Authority reviews recommendation (M10.7)
    rev_payload = {
        "review_status": "ACCEPTED",
        "review_notes": "Emergency cordoning confirmed on site. Work order requisitioned.",
        "decision_action_taken": "Contractor dispatched for frame replacement.",
    }
    rev_resp = client.post(f"{settings.API_V1_STR}/decision-support/cases/{case_ref}/review", json=rev_payload)
    assert rev_resp.status_code == status.HTTP_200_OK
    assert rev_resp.json()["case_status_unchanged"] == "in_progress"

    # 7. Citizen accesses privacy-preserving Citizen View (M10.7)
    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    cit_view_resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/{case_ref}/citizen-view")
    assert cit_view_resp.status_code == status.HTTP_200_OK
    cit_view = cit_view_resp.json()
    assert cit_view["public_location"]["latitude_approx"] == 12.972
    assert "latitude" not in cit_view["public_location"]
    assert "disclaimer" in cit_view

    # 8. Citizen submits clarification response
    clar_resp = client.post(
        f"{settings.API_V1_STR}/decision-support/cases/{case_ref}/clarify",
        json={"question_id": "q_clar_gen", "free_text": "Opposite to petrol bunk on left lane."},
    )
    assert clar_resp.status_code == status.HTTP_200_OK
    assert clar_resp.json()["epistemic_state"] == EpistemicState.USER_REPORTED.value


# =========================================================================
# 10.9.2 PROVENANCE INTEGRITY & TAMPER DETECTION
# =========================================================================

def test_02_provenance_tamper_detection(setup_e2e_environment):
    """
    Verifies cryptographic hash-chain integrity and ensures tampering
    with an evidence payload is detected by recalculating the SHA-256 fingerprint.
    """
    prov_engine = get_provenance_engine()
    case_ref = "CASE-PROV-TAMPER"

    rec1 = prov_engine.build_evidence_record(
        case_reference=case_ref,
        claim_type=ClaimType.OPERATIONAL_DECISION_RECOMMENDATION,
        source="M10.4 Engine",
        source_type=SourceType.SYSTEM_DERIVED,
        explanation="Initial decision recommendation",
        verification_state=VerificationState.SYSTEM_DERIVED,
        claim_value={"priority": "P1", "matched": "PB-MANHOLE-SAFETY-V1"},
    )
    assert rec1.evidence_hash is not None

    # Verify that the calculated hash matches the record
    original_calc_hash = calculate_evidence_hash(
        claim_type=rec1.claim_type.value,
        matched_attribute=rec1.matched_attribute,
        source=rec1.source,
        source_type=rec1.source_type.value,
        value={"priority": "P1", "matched": "PB-MANHOLE-SAFETY-V1"},
        explanation=rec1.explanation,
    )
    assert rec1.evidence_hash == original_calc_hash

    # TAMPER TEST: Recalculate with modified payload
    tampered_hash = calculate_evidence_hash(
        claim_type=rec1.claim_type.value,
        matched_attribute=rec1.matched_attribute,
        source=rec1.source,
        source_type=rec1.source_type.value,
        value={"priority": "P4_TAMPERED", "matched": "PB-MANHOLE-SAFETY-V1"},
        explanation=rec1.explanation,
    )
    assert rec1.evidence_hash != tampered_hash, "Tamper attempt failed to diverge the cryptographic digest!"


# =========================================================================
# 10.9.3 KNOWLEDGE GRAPH RELATIONAL PROJECTION E2E
# =========================================================================

def test_03_knowledge_graph_relational_hierarchy(setup_e2e_environment):
    """
    Verifies that projected case decisions establish proper relational hierarchy:
    CASE -> DECISION_RECOMMENDATION -> ACTION_PLAYBOOK -> RECOMMENDED_ACTION.
    """
    case_ref = "CASE-KG-HIERARCHY"
    case = _make_e2e_case(reference_id=case_ref)
    setup_e2e_environment["case_repo"].save(case)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)

    # Trigger decision support
    client.get(f"{settings.API_V1_STR}/decision-support/cases/{case_ref}")

    # Inspect graph
    graph_resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/{case_ref}/graph")
    assert graph_resp.status_code == status.HTTP_200_OK
    graph = graph_resp.json()

    node_keys = {n.get("canonical_key") or n.get("id") or n.get("node_id") for n in graph.get("nodes", [])}
    assert any(case_ref in str(k) for k in node_keys)
    assert len(graph.get("edges", [])) > 0


# =========================================================================
# 10.9.4 FAILURE PATH TESTING (SAFE FAILING INVARIANTS)
# =========================================================================

@pytest.mark.parametrize("failure_scenario,ctx_kwargs", [
    ("missing_cv", {"detection_result": None, "citizen_text": "Some text"}),
    ("low_confidence_cv", {
        "detection_result": StandardDetectionResult(
            success=True,
            detections=[StandardDetection(class_id=0, class_name="open_damaged_manhole", confidence=0.15, bbox=StandardBoundingBox(x1=0, y1=0, x2=1, y2=1))],
            total_detections=1,
            model_id="m1_13",
            model_version="1.13.0",
            provider_id="yolov8_m1_13",
        ),
        "citizen_text": "Vague report",
    }),
    ("inconsistent_text_cv", {
        "detection_result": StandardDetectionResult(
            success=True,
            detections=[StandardDetection(class_id=0, class_name="open_damaged_manhole", confidence=0.85, bbox=StandardBoundingBox(x1=0, y1=0, x2=1, y2=1))],
            total_detections=1,
            model_id="m1_13",
            model_version="1.13.0",
            provider_id="yolov8_m1_13",
        ),
        "citizen_text": "Freshly painted smooth road surface without issues",
        "alignment_score": 0.12,
    }),
    ("unverified_authority", {"authority_name": "Unregistered Contractor", "is_authority_verified": False}),
    ("inconclusive_visual_audit", {"visual_audit_outcome": "EVIDENCE_INCONCLUSIVE"}),
])
def test_04_failure_paths_fail_safely(failure_scenario, ctx_kwargs):
    """
    Every failure path must fail safely:
    - human_review_required MUST be True.
    - epistemic_state MUST remain SYSTEM_DERIVED.
    - Never asserts ground truth or automatically marks resolved.
    """
    ctx = DecisionContext(
        case_reference=f"CASE-FAIL-{failure_scenario}",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        **ctx_kwargs,
    )
    engine = get_decision_support_engine()
    decision = engine.evaluate_case(ctx)

    assert decision.human_review_required is True, f"Failed safe failure on scenario: {failure_scenario}"
    assert decision.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert decision.epistemic_state != EpistemicState.VERIFIED_EVIDENCE
    assert len(decision.human_review_reasons) > 0
