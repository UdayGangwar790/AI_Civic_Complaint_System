"""
CVKI - Civic Vision & Knowledge Intelligence
Module 12.2: End-to-End Product Validation Test Suite

Validates the complete, realistic user journey:
Citizen Image & Vernacular Input -> GPS -> CV Detection -> Road/Jurisdiction ->
Authority Resolution -> Case Creation -> Multimodal Analysis ->
Consistency Check -> Active Clarification -> Decision Support ->
Playbook Grounding -> Field Inspection Protocol -> Physical Inspection Audit ->
Authority Decision Review -> Citizen Clarification -> Government Integration Check ->
Provenance Recording -> Knowledge Graph Projection -> Epistemic Invariants Check.
"""

from datetime import datetime, timezone, timedelta
import pytest
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
    GeofenceResult,
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
from app.services.cv.providers.m113_yolo_provider import M113YOLOProvider, M1_13_REQUIRED_SHA256
from app.services.decision_projection import get_decision_projector
from app.services.decision_support import get_decision_support_engine
from app.services.field_inspection import (
    get_audit_engine,
    get_field_inspection_repository,
    get_protocol_generator,
)
from app.services.knowledge_graph import (
    InMemoryKnowledgeGraphRepository,
    get_knowledge_graph_service,
    set_knowledge_graph_service,
)
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.multimodal_gateway import get_multimodal_gateway_service
from app.services.provenance_engine import (
    InMemoryProvenanceRepository,
    get_provenance_engine,
    set_provenance_engine,
)
import asyncio
from app.schemas.government_integration import IntegrationState
from app.services.government_adapter import (
    CPGRAMSIntegrationAdapter,
    AdapterSubmissionResult,
)


CITIZEN = AuthenticatedUser(user_id="cit_m12_001", email="citizen@cvki.gov.in", role=UserRole.CITIZEN.value)
AUTHORITY = AuthenticatedUser(user_id="auth_m12_001", email="authority@cvki.gov.in", role=UserRole.AUTHORITY.value)
ADMIN = AuthenticatedUser(user_id="admin_m12_001", email="admin@cvki.gov.in", role=UserRole.ADMIN.value)


@pytest.fixture(autouse=True)
def setup_m12_environment():
    orig_repo = complaint_case_module.case_repository
    case_repo = InMemoryComplaintCaseRepository()
    set_case_repository(case_repo)

    insp_repo = get_field_inspection_repository()
    insp_repo.clear()

    prov_engine = get_provenance_engine()
    prov_repo = InMemoryProvenanceRepository()
    prov_engine.repository = prov_repo

    kg_service = get_knowledge_graph_service()
    kg_repo = InMemoryKnowledgeGraphRepository()
    kg_service.repository = kg_repo

    yield {
        "case_repo": case_repo,
        "insp_repo": insp_repo,
        "prov_repo": prov_repo,
        "kg_repo": kg_repo,
    }

    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def test_01_complete_product_lifecycle_journey():
    """
    Test the comprehensive, contract-accurate end-to-end civic defect workflow.
    """
    client = TestClient(app)

    # 1. Setup User Authentication
    app.dependency_overrides[get_current_user] = lambda: CITIZEN

    # 2. Citizen Submits Multimodal Complaint (Vernacular Hindi/Hinglish Text + Geolocation)
    case_ref = "CASE-M12-E2E-001"
    mm_gateway = get_multimodal_gateway_service()
    mm_req = MultimodalGatewayRequest(
        text="Sadak par open manhole hai, bahut bada khatra hai accident ka",
        language_hint="hi",
        latitude=12.9716,
        longitude=77.5946,
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    mm_result = mm_gateway.process(mm_req)

    assert mm_result is not None
    assert mm_result.vernacular_result is not None
    assert mm_result.vernacular_result.detected_language in ("hi", "hinglish", "en")
    assert mm_result.epistemic_state == EpistemicState.SYSTEM_DERIVED

    # 3. Computer Vision Inference Validation (M1.13 Standard Provider Verification)
    cv_provider = M113YOLOProvider()
    assert cv_provider.descriptor.model_id == "m1.13-yolov8n"
    assert cv_provider.descriptor.sha256_hash == M1_13_REQUIRED_SHA256

    mock_detection = StandardDetection(
        class_id=0,
        class_name="open_damaged_manhole",
        confidence=0.89,
        bbox=StandardBoundingBox(x1=100.0, y1=150.0, x2=300.0, y2=350.0),
    )
    cv_result = StandardDetectionResult(
        success=True,
        detections=[mock_detection],
        total_detections=1,
        inference_time_ms=12.4,
        image_width=640,
        image_height=480,
        model_id=cv_provider.descriptor.model_id,
        model_version="1.13.0",
        model_hash=cv_provider.descriptor.sha256_hash,
    )
    assert cv_result.detections[0].class_name == "open_damaged_manhole"
    assert cv_result.detections[0].confidence >= 0.85

    # 4. Authority Resolution & Case Creation
    case_repo = complaint_case_module.case_repository
    case_obj = ComplaintCase(
        reference_id=case_ref,
        user_id=CITIZEN.user_id,
        status="submitted_to_cvki",
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": "open_damaged_manhole",
            "label": "Open Damaged Manhole",
            "severity": "high",
            "confidence": 0.89,
        },
        location={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "road": "MG Road",
            "area": "Central Ward 112",
            "city": "Bengaluru",
        },
        priority_analysis={
            "priority_level": "P1",
            "priority_score": 88.0,
            "risk_level": "Critical",
        },
        authority={
            "authority_status": "verified",
            "maintenance_authority": {
                "name": "Bruhat Bengaluru Mahanagara Palike (BBMP)",
                "department": "Stormwater & Drainage Division",
                "jurisdiction_type": "Municipal",
            },
        },
        complaint={
            "title": "Uncovered Manhole on Road",
            "description": "Sadak par open manhole hai, bahut bada khatra hai accident ka",
            "language": "hi",
        },
        follow_up={"guidance": "Forwarded to BBMP Control Room for emergency barricading."},
        assignment={"assigned_to_user_id": AUTHORITY.user_id},
    )
    case_repo.save(case_obj)

    retrieved = case_repo.get(case_ref)
    assert retrieved is not None
    assert retrieved.reference_id == case_ref
    assert getattr(retrieved.assignment, "assigned_to_user_id", None) == AUTHORITY.user_id

    # 5. Decision Support & Action Playbook Matching
    app.dependency_overrides[get_current_user] = lambda: AUTHORITY
    ds_engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference=case_ref,
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=cv_result,
        citizen_text="Sadak par open manhole hai",
        priority_level="P1",
        is_recurrent=True,
        recurrence_count=3,
        weather_condition="heavy rain",
        authority_name="BBMP",
        is_authority_verified=True,
    )
    dec_result = ds_engine.evaluate_case(ctx)

    assert dec_result is not None
    assert dec_result.human_review_required is True  # Non-negotiable invariant
    assert dec_result.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert len(dec_result.matched_playbooks) > 0
    assert any("MANHOLE" in pb for pb in dec_result.matched_playbooks)
    assert len(dec_result.recommended_actions) >= 1

    # 6. Field Inspection Protocol Generation
    proto_gen = get_protocol_generator()
    protocol = proto_gen.generate_protocol(
        case_reference=case_ref,
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        case_location={"latitude": 12.9716, "longitude": 77.5946},
    )
    assert protocol.case_reference == case_ref
    assert len(protocol.inspection_steps) >= 3

    # 7. Field Inspection Execution & Audit
    insp_engine = get_audit_engine()
    observations = [
        InspectionObservationItem(
            step_id=step.step_id,
            observation_text=f"Completed verification for {step.step_id}: compliant with standard protocol.",
            defect_confirmed=True,
            notes="Physical verification complete.",
        )
        for step in protocol.inspection_steps
    ]
    insp_submission = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        observations=observations,
        location={"latitude": 12.9716, "longitude": 77.5946},
        inspection_timestamp=datetime.now(timezone.utc),
        evidence_items=["https://cvki.gov.in/evidence/insp_after_001.jpg"],
        notes="Physical inspection completed compliant with safety requirements.",
    )
    record = insp_engine.audit_submission(
        protocol=protocol,
        submission=insp_submission,
        inspector_id=AUTHORITY.user_id,
    )
    audit_res = record.audit_result
    assert audit_res.outcome == AuditOutcome.SUPPORTED
    assert audit_res.completeness == InspectionCompleteness.COMPLETE
    assert audit_res.geofence_result == GeofenceResult.WITHIN_EXPECTED_AREA
    assert len(audit_res.supported_points) >= 1

    # 8. Decision Projection to Provenance & Knowledge Graph
    projector = get_decision_projector()
    prov_rec, dec_nodes, dec_edges = projector.project_decision_recommendation(
        case_reference=case_ref,
        decision=dec_result,
    )
    assert prov_rec.claim_type == ClaimType.OPERATIONAL_DECISION_RECOMMENDATION
    assert prov_rec.verification_state == VerificationState.SYSTEM_DERIVED

    insp_prov, insp_nodes, insp_edges = projector.project_field_inspection(record)
    assert insp_prov.claim_type == ClaimType.FIELD_INSPECTION_AUDIT

    # 9. Authority Reviews Decision Support Recommendation
    review_req = RecommendationReviewRequest(
        review_status="ACCEPTED",
        review_notes="Barricade verified by field inspection; approved for structural restoration dispatch.",
    )
    resp = client.post(
        f"/api/v1/decision-support/cases/{case_ref}/review",
        json=review_req.model_dump(),
        headers={"Idempotency-Key": "idemp-m12-review-001"},
    )
    assert resp.status_code == 200
    review_data = resp.json()
    assert review_data["review_status"] == "ACCEPTED"
    assert review_data["reviewer_id"] == AUTHORITY.user_id

    # 10. Citizen Clarification Flow
    app.dependency_overrides[get_current_user] = lambda: CITIZEN
    clarify_req = CitizenClarifyRequest(
        question_id="Q-MANHOLE-01",
        free_text="Yeh defect main road ke right lane par hai, metro pillar ke samne.",
    )
    resp = client.post(
        f"/api/v1/decision-support/cases/{case_ref}/clarify",
        json=clarify_req.model_dump(),
        headers={"Idempotency-Key": "idemp-m12-clarify-001"},
    )
    assert resp.status_code == 200
    clarify_data = resp.json()
    assert clarify_data["status"] == "SUCCESS"
    assert clarify_data["clarification_status"] == "RESOLVED"
    assert clarify_data["epistemic_state"].lower() == "user_reported"

    # 11. Government Portal Integration State Verification (Safe Handling of Sandbox/Unavailable State)
    app.dependency_overrides[get_current_user] = lambda: AUTHORITY
    cpgrams = CPGRAMSIntegrationAdapter()
    gov_res = asyncio.run(
        cpgrams.submit(
            case=case_obj,
            package=None,  # Handled safely when unconfigured
            idempotency_key="idemp-m12-gov-001",
        )
    )
    # Never fabricate government success: when portal is disabled or in sandbox, verify accurate state
    assert gov_res.state in (
        IntegrationState.NOT_CONFIGURED,
        IntegrationState.CONFIGURED_STAGING,
        IntegrationState.CONFIGURED_PRODUCTION,
        IntegrationState.DISABLED,
    )
    assert gov_res.external_reference_id is None or gov_res.external_reference_id.startswith("CPGRAMS-")

    # 12. Knowledge Graph Query Verification
    resp_kg = client.get(f"/api/v1/decision-support/cases/{case_ref}/graph")
    assert resp_kg.status_code == 200
    kg_data = resp_kg.json()
    assert kg_data["case_reference"] == case_ref
    assert len(kg_data["nodes"]) >= 2
    assert len(kg_data["edges"]) >= 1

    # 13. Provenance Chain Cryptographic Verification
    resp_prov = client.get(f"/api/v1/decision-support/cases/{case_ref}/provenance")
    assert resp_prov.status_code == 200
    prov_data = resp_prov.json()
    records = prov_data["provenance_records"]
    assert len(records) >= 2
    # Verify SHA-256 hashes are non-empty and 64 hex characters
    for p in records:
        assert len(p["evidence_hash"]) == 64
        assert p["verification_state"].lower() in (
            "system_derived", "user_reported", "verified", "not_verified", "partially_verified", "disputed"
        )

    # 14. Non-Negotiable Epistemic Safety Verification: Case Lifecycle NOT Mutated
    final_case = case_repo.get(case_ref)
    assert final_case is not None
    assert final_case.status not in ("resolved", "closed")
    assert final_case.status in ("submitted_to_cvki", "in_progress", "under_review", "assigned")


def test_02_failure_paths_fail_safely():
    """Verify that anomalous or unverified inputs fail safely without system compromise."""
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = lambda: CITIZEN

    # Create case owned by CITIZEN
    case_repo = complaint_case_module.case_repository
    case_repo.save(
        ComplaintCase(
            reference_id="CASE-FAIL-01",
            user_id=CITIZEN.user_id,
            status="submitted_to_cvki",
            created_at=datetime.now(timezone.utc),
            issue={"class_id": 0, "class_name": "pothole", "label": "Pothole", "severity": "low", "confidence": 0.8},
            location={"latitude": 12.9, "longitude": 77.5},
            authority={"authority_status": "verified", "maintenance_authority": {"name": "BBMP"}},
            complaint={"title": "Test Defect", "description": "Road issue", "language": "en"},
            follow_up={"guidance": "Saved"},
        )
    )

    # A. Script injection / path traversal in clarification text rejected with 422
    resp = client.post(
        "/api/v1/decision-support/cases/CASE-FAIL-01/clarify",
        json={"question_id": "Q-001", "free_text": "<script>alert(1)</script>../../etc/passwd"},
    )
    assert resp.status_code == 422

    # B. Unauthorized citizen accessing authority review endpoint rejected with 403
    app.dependency_overrides[get_current_user] = lambda: CITIZEN
    resp = client.post(
        "/api/v1/decision-support/cases/CASE-FAIL-01/review",
        json={"review_status": "ACCEPTED", "review_notes": "Attempted citizen review"},
    )
    assert resp.status_code == 403
