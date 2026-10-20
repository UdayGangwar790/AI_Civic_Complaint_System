"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.6: Decision Provenance & Knowledge Graph Projection Tests
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
from app.schemas.field_inspection import (
    AuditOutcome,
    FieldInspectionAuditResult,
    FieldInspectionRecord,
    GeofenceResult,
    InspectionCompleteness,
    InspectionObservationItem,
)
from app.schemas.knowledge_graph import (
    NodeType,
    RelationType,
    canonical_case_key,
    canonical_decision_key,
    canonical_inspection_key,
    canonical_playbook_key,
)
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
)
from app.services.action_playbook import PlaybookActionItem
from app.services.complaint_case import (
    ComplaintCase,
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
from app.services.decision_projection import (
    DecisionProvenanceKGProjector,
    get_decision_projector,
)
from app.services.knowledge_graph import (
    InMemoryKnowledgeGraphRepository,
    get_knowledge_graph_service,
)
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.provenance_engine import (
    InMemoryProvenanceRepository,
    get_provenance_engine,
)


CITIZEN_1 = AuthenticatedUser(user_id="user_cit_1", email="cit1@cvki.gov.in", role=UserRole.CITIZEN.value)
CITIZEN_2 = AuthenticatedUser(user_id="user_cit_2", email="cit2@cvki.gov.in", role=UserRole.CITIZEN.value)
AUTHORITY_1 = AuthenticatedUser(user_id="user_auth_1", email="auth1@cvki.gov.in", role=UserRole.AUTHORITY.value)
ADMIN_1 = AuthenticatedUser(user_id="user_admin_1", email="admin@cvki.gov.in", role=UserRole.ADMIN.value)


@pytest.fixture(autouse=True)
def setup_projection_env():
    orig_repo = complaint_case_module.case_repository
    mem_repo = InMemoryComplaintCaseRepository()
    set_case_repository(mem_repo)

    # In-memory clean state for provenance and KG
    prov_engine = get_provenance_engine()
    prov_engine.repository = InMemoryProvenanceRepository()

    kg_service = get_knowledge_graph_service()
    kg_service.repository = InMemoryKnowledgeGraphRepository()

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    yield mem_repo
    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def _make_case(reference_id="CASE-PROJ-001", user_id="user_cit_1", assigned_to="user_auth_1"):
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
            "confidence": 0.88,
        },
        location={"latitude": 12.9716, "longitude": 77.5946, "city": "Bengaluru"},
        authority={
            "authority_status": "verified",
            "maintenance_authority": {"name": "BBMP Maintenance Cell"},
        },
        complaint={"title": "Open manhole", "description": "Large aperture defect", "language": "en"},
        follow_up={"guidance": "Saved in CVKI."},
        assignment={"assigned_to_user_id": assigned_to} if assigned_to else None,
    )


def _make_dummy_decision(rec_id="DEC-TEST-001"):
    return DecisionSupportResult(
        recommendation_id=rec_id,
        case_reference="CASE-PROJ-001",
        matched_playbooks=["PB-MANHOLE-SAFETY-V1 (v1.0.0)"],
        recommended_actions=[
            PlaybookActionItem(
                action_id="ACT-001",
                action_type="INSPECT",
                title="Immediate Site Inspection",
                description="Verify aperture",
            )
        ],
        mitigation_actions=[],
        required_inspection=["Check aperture dimensions"],
        explanation="High-risk open manhole detected.",
        evidence_quality=DecisionEvidenceQuality.STRONG,
        epistemic_state=EpistemicState.SYSTEM_DERIVED,
        human_review_required=True,
    )


def _make_dummy_inspection(insp_id="INSP-TEST-001", case_ref="CASE-PROJ-001"):
    now = datetime.now(timezone.utc)
    audit = FieldInspectionAuditResult(
        audit_id="AUD-001",
        outcome=AuditOutcome.SUPPORTED,
        completeness=InspectionCompleteness.COMPLETE,
        geofence_result=GeofenceResult.WITHIN_EXPECTED_AREA,
        distance_from_case_meters=15.0,
        supported_points=["All steps recorded", "Defect confirmed"],
        audit_explanation="Inspection corroborated defect.",
        audited_at=now,
    )
    return FieldInspectionRecord(
        inspection_id=insp_id,
        case_reference=case_ref,
        protocol_id="PROTOCOL-MANHOLE-V1",
        protocol_version="1.0.0",
        inspector_id="user_auth_1",
        observations=[
            InspectionObservationItem(step_id="STEP-01", observation_text="Verified aperture", defect_confirmed=True)
        ],
        location={"latitude": 12.9716, "longitude": 77.5946},
        inspection_timestamp=now,
        geofence_result=GeofenceResult.WITHIN_EXPECTED_AREA,
        completeness=InspectionCompleteness.COMPLETE,
        audit_result=audit,
        created_at=now,
    )


# --- 16 Required Tests ---

def test_01_decision_provenance():
    """Verify decision projection creates an EvidenceRecord with OPERATIONAL_DECISION_RECOMMENDATION."""
    projector = get_decision_projector()
    decision = _make_dummy_decision()
    prov, _, _ = projector.project_decision_recommendation("CASE-PROJ-001", decision)

    assert prov.claim_type == ClaimType.OPERATIONAL_DECISION_RECOMMENDATION
    assert prov.source_type == SourceType.SYSTEM_DERIVED
    assert prov.verification_state == VerificationState.SYSTEM_DERIVED
    assert prov.case_reference == "CASE-PROJ-001"


def test_02_playbook_provenance():
    """Verify matched playbooks and action counts are preserved in claim value."""
    projector = get_decision_projector()
    decision = _make_dummy_decision()
    prov, _, _ = projector.project_decision_recommendation("CASE-PROJ-001", decision)

    val = prov.metadata.get("claim_value")
    assert isinstance(val, dict)
    assert val["recommendation_id"] == "DEC-TEST-001"
    assert val["matched_playbooks"] == ["PB-MANHOLE-SAFETY-V1 (v1.0.0)"]
    assert val["action_count"] == 1


def test_03_inspection_provenance():
    """Verify field inspection projection creates an EvidenceRecord with FIELD_INSPECTION_AUDIT."""
    projector = get_decision_projector()
    insp = _make_dummy_inspection()
    prov, _, _ = projector.project_field_inspection(insp)

    assert prov.claim_type == ClaimType.FIELD_INSPECTION_AUDIT
    assert prov.source_type == SourceType.AUTHORITY_UPDATE
    assert prov.case_reference == "CASE-PROJ-001"
    assert prov.metadata["claim_value"]["inspection_id"] == "INSP-TEST-001"


def test_04_graph_node_creation():
    """Verify projection creates DECISION_RECOMMENDATION, OPERATIONAL_PLAYBOOK, and FIELD_INSPECTION nodes."""
    projector = get_decision_projector()
    decision = _make_dummy_decision()
    insp = _make_dummy_inspection()

    _, dec_nodes, _ = projector.project_decision_recommendation("CASE-PROJ-001", decision)
    _, insp_nodes, _ = projector.project_field_inspection(insp)

    dec_types = {n.node_type for n in dec_nodes}
    assert NodeType.DECISION_RECOMMENDATION in dec_types
    assert NodeType.OPERATIONAL_PLAYBOOK in dec_types

    insp_types = {n.node_type for n in insp_nodes}
    assert NodeType.FIELD_INSPECTION in insp_types


def test_05_graph_edge_creation():
    """Verify projection creates RECOMMENDS_PLAYBOOK and RELATED_TO edges."""
    projector = get_decision_projector()
    decision = _make_dummy_decision()
    insp = _make_dummy_inspection()

    _, _, dec_edges = projector.project_decision_recommendation("CASE-PROJ-001", decision)
    _, _, insp_edges = projector.project_field_inspection(insp)

    dec_rel_types = {e.relation_type for e in dec_edges}
    assert RelationType.RECOMMENDS_PLAYBOOK in dec_rel_types
    assert RelationType.HAS_ESCALATION_DECISION in dec_rel_types

    insp_rel_types = {e.relation_type for e in insp_edges}
    assert RelationType.RELATED_TO in insp_rel_types


def test_06_duplicate_prevention():
    """Verify re-projecting identical recommendation uses idempotent canonical keys without node duplication."""
    projector = get_decision_projector()
    decision = _make_dummy_decision("DEC-IDEM-001")

    _, nodes1, edges1 = projector.project_decision_recommendation("CASE-PROJ-001", decision)
    _, nodes2, edges2 = projector.project_decision_recommendation("CASE-PROJ-001", decision)

    kg = get_knowledge_graph_service()
    all_dec_nodes = [
        n for n in kg.repository.all_nodes()
        if n.canonical_key == canonical_decision_key("DEC-IDEM-001")
    ]
    assert len(all_dec_nodes) == 1


def test_07_versioning():
    """Verify multiple evaluations increment provenance versions while preserving historical records."""
    projector = get_decision_projector()
    prov_engine = get_provenance_engine()

    dec1 = _make_dummy_decision("DEC-V1")
    dec2 = _make_dummy_decision("DEC-V2")

    p1, _, _ = projector.project_decision_recommendation("CASE-VER-001", dec1)
    p2, _, _ = projector.project_decision_recommendation("CASE-VER-001", dec2)

    assert p1.version == 1
    assert p2.version == 2

    history = prov_engine.repository.find_history(
        "CASE-VER-001", ClaimType.OPERATIONAL_DECISION_RECOMMENDATION
    )
    assert len(history) == 2


def test_08_invalidation():
    """Verify handle_evidence_invalidation marks supporting decision nodes as stale."""
    projector = get_decision_projector()
    prov_engine = get_provenance_engine()
    kg = get_knowledge_graph_service()

    # Create dummy base evidence
    ev = prov_engine.build_evidence_record(
        case_reference="CASE-INV-001",
        claim_type=ClaimType.DETECTION,
        source="M1.13 CV",
        source_type=SourceType.CV_MODEL,
        explanation="Detected open manhole",
    )
    # Ensure evidence node in KG
    kg._ensure_node(
        node_type=NodeType.EVIDENCE,
        canonical_key=f"evidence:{ev.evidence_id}",
        display_name=f"Evidence: {ev.evidence_id}",
        case_reference="CASE-INV-001",
    )

    dec = _make_dummy_decision("DEC-SUPPORTED")
    projector.project_decision_recommendation("CASE-INV-001", dec, supporting_evidence_ids=[ev.evidence_id])

    # Invalidate evidence
    affected = projector.handle_evidence_invalidation(ev.evidence_id, "CASE-INV-001", reason="Camera lens obstructed")

    assert len(affected) > 0
    # Check decision node is marked stale
    dec_node = kg.repository.get_node_by_key(canonical_decision_key("DEC-SUPPORTED"))
    assert dec_node is not None
    assert dec_node.metadata.get("status") == "stale"
    assert "obstructed" in dec_node.metadata.get("stale_reason", "")


def test_09_stale_evidence_handling():
    """Verify edge verification state is downgraded to STALE upon evidence invalidation."""
    projector = get_decision_projector()
    prov_engine = get_provenance_engine()
    kg = get_knowledge_graph_service()

    ev = prov_engine.build_evidence_record(
        case_reference="CASE-STALE-001",
        claim_type=ClaimType.LOCATION,
        source="GPS",
        source_type=SourceType.GPS,
        explanation="Location reading",
    )
    kg._ensure_node(
        node_type=NodeType.EVIDENCE,
        canonical_key=f"evidence:{ev.evidence_id}",
        display_name="GPS reading",
        case_reference="CASE-STALE-001",
    )

    dec = _make_dummy_decision("DEC-STALE-001")
    projector.project_decision_recommendation("CASE-STALE-001", dec, supporting_evidence_ids=[ev.evidence_id])

    projector.handle_evidence_invalidation(ev.evidence_id, "CASE-STALE-001", reason="GPS drift observed")

    edges = kg.repository.find_edges_to(f"evidence:{ev.evidence_id}")
    assert any(e.verification_state == VerificationState.STALE for e in edges)


def test_10_conflict_propagation():
    """Verify conflicting field inspection sets verification state to NOT_VERIFIED."""
    projector = get_decision_projector()
    now = datetime.now(timezone.utc)
    audit = FieldInspectionAuditResult(
        audit_id="AUD-CONF",
        outcome=AuditOutcome.CONFLICTING,
        completeness=InspectionCompleteness.CONFLICTING,
        geofence_result=GeofenceResult.WITHIN_EXPECTED_AREA,
        conflicts_detected=["Discrepancy in defect report"],
        audit_explanation="Conflicting findings.",
        audited_at=now,
    )
    insp = FieldInspectionRecord(
        inspection_id="INSP-CONF-001",
        case_reference="CASE-CONF-001",
        protocol_id="PROTOCOL-MANHOLE-V1",
        protocol_version="1.0.0",
        inspector_id="user_auth_1",
        observations=[],
        inspection_timestamp=now,
        geofence_result=GeofenceResult.WITHIN_EXPECTED_AREA,
        completeness=InspectionCompleteness.CONFLICTING,
        conflicts=["Discrepancy in defect report"],
        audit_result=audit,
        created_at=now,
    )
    prov, _, edges = projector.project_field_inspection(insp)

    assert prov.verification_state == VerificationState.NOT_VERIFIED
    assert any(e.verification_state == VerificationState.NOT_VERIFIED for e in edges)


def test_11_rbac_decision_provenance(setup_projection_env):
    """Verify RBAC on GET /cases/{ref_id}/provenance route."""
    case1 = _make_case(reference_id="CASE-RBAC-01", user_id="user_cit_1", assigned_to="user_auth_1")
    setup_projection_env.save(case1)

    projector = get_decision_projector()
    dec = _make_dummy_decision("DEC-RBAC-01")
    projector.project_decision_recommendation("CASE-RBAC-01", dec)

    # Authority assigned: allowed
    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)
    resp1 = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-RBAC-01/provenance")
    assert resp1.status_code == status.HTTP_200_OK
    assert len(resp1.json()["provenance_records"]) > 0

    # Citizen 2 (not owner): forbidden
    app.dependency_overrides[get_current_user] = lambda: CITIZEN_2
    resp2 = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-RBAC-01/provenance")
    assert resp2.status_code == status.HTTP_403_FORBIDDEN


def test_12_rbac_decision_graph(setup_projection_env):
    """Verify RBAC on GET /cases/{ref_id}/graph route."""
    case1 = _make_case(reference_id="CASE-GRAPH-01", user_id="user_cit_1", assigned_to="user_auth_1")
    setup_projection_env.save(case1)

    projector = get_decision_projector()
    dec = _make_dummy_decision("DEC-GRAPH-01")
    projector.project_decision_recommendation("CASE-GRAPH-01", dec)

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)
    resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-GRAPH-01/graph")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0


def test_13_no_case_lifecycle_mutation(setup_projection_env):
    """Verify decision and inspection projection NEVER mutate complaint case status."""
    case = _make_case(reference_id="CASE-MUT-01", user_id="user_cit_1", assigned_to="user_auth_1")
    setup_projection_env.save(case)

    initial_status = case.status

    projector = get_decision_projector()
    dec = _make_dummy_decision("DEC-MUT-01")
    insp = _make_dummy_inspection("INSP-MUT-01", case_ref="CASE-MUT-01")

    projector.project_decision_recommendation("CASE-MUT-01", dec)
    projector.project_field_inspection(insp)

    refetched = complaint_case_module.case_repository.get("CASE-MUT-01")
    assert refetched.status == initial_status


def test_14_graph_traversal():
    """Verify get_case_decision_subgraph returns connected nodes and edges."""
    projector = get_decision_projector()
    dec = _make_dummy_decision("DEC-TRAV-01")
    projector.project_decision_recommendation("CASE-TRAV-001", dec)

    subgraph = projector.get_case_decision_subgraph("CASE-TRAV-001")
    assert subgraph["case_reference"] == "CASE-TRAV-001"

    node_keys = [n["canonical_key"] for n in subgraph["nodes"]]
    assert canonical_case_key("CASE-TRAV-001") in node_keys
    assert canonical_decision_key("DEC-TRAV-01") in node_keys
    assert canonical_playbook_key("PB-MANHOLE-SAFETY-V1") in node_keys


def test_15_explanation_reconstruction():
    """Verify explanation text is preserved in provenance claim records."""
    projector = get_decision_projector()
    dec = _make_dummy_decision("DEC-EXPL-01")
    dec.explanation = "Specific rationale: open manhole within school zone."

    prov, _, _ = projector.project_decision_recommendation("CASE-EXPL-001", dec)
    assert "school zone" in prov.explanation


def test_16_idempotent_projection():
    """Verify repeated projection calls produce consistent edge and node counts."""
    projector = get_decision_projector()
    dec = _make_dummy_decision("DEC-IDEM-02")

    for _ in range(3):
        projector.project_decision_recommendation("CASE-IDEM-002", dec)

    subgraph = projector.get_case_decision_subgraph("CASE-IDEM-002")
    dec_nodes = [n for n in subgraph["nodes"] if n["node_type"] == NodeType.DECISION_RECOMMENDATION.value]
    assert len(dec_nodes) == 1
