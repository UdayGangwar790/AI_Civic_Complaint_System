import asyncio
from datetime import datetime, timedelta, timezone
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.authority import AuthorityParty, AuthorityResult
from app.schemas.civic_intelligence import (
    CaseIntelligenceResponse,
    RecurrenceAnalysis,
    ResolutionEvidenceRecord,
)
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseAssignment,
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.schemas.duplicate import DuplicateCheckResponse
from app.schemas.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeNode,
    NodeType,
    RelationType,
    canonical_authority_key,
    canonical_builder_key,
    canonical_case_key,
    canonical_complaint_key,
    canonical_detection_key,
    canonical_edge_key,
    canonical_hotspot_key,
    canonical_issue_key,
    canonical_jurisdiction_key,
    canonical_location_key,
    canonical_rainfall_key,
    canonical_recurrence_key,
    canonical_resolution_key,
    canonical_road_key,
    canonical_road_segment_key,
    canonical_weather_key,
)
from app.schemas.provenance import (
    ClaimType,
    EvidenceRecord,
    SourceType,
    VerificationState,
    calculate_evidence_hash,
)
from app.services.authority import resolve_authority_for_location
import app.services.complaint_case as complaint_case_module
from app.services.knowledge_graph import (
    CivicKnowledgeGraphService,
    InMemoryKnowledgeGraphRepository,
    get_knowledge_graph_service,
    set_knowledge_graph_service,
)
from app.services.provenance_engine import (
    EvidenceProvenanceEngine,
    InMemoryProvenanceRepository,
    set_provenance_engine,
)


def _build_test_case(
    ref_id: str,
    user_id: str = "usr_citizen_001",
    lat: float = 12.9716,
    lon: float = 77.5946,
    issue_class: str = "pothole",
    road: str = "MG Road",
    assigned_to: str | None = None,
    created_at: datetime | None = None,
    builder: str | None = None,
    tender_id: str | None = None,
    resolved: bool = False,
    verified_authority: bool = True,
    is_duplicate: bool = False,
    is_possible_duplicate: bool = False,
) -> ComplaintCase:
    now = created_at or datetime.now(timezone.utc)
    complaint_loc = ComplaintLocation(
        road=road,
        area="Central Business District",
        city="Bengaluru",
        district="Bengaluru Urban",
        state="Karnataka",
        latitude=lat,
        longitude=lon,
    )
    auth = resolve_authority_for_location(complaint_loc)
    if not auth:
        auth = AuthorityResult(
            authority_id="auth_bbmp_default",
            authority_name="Bruhat Bengaluru Mahanagara Palike (BBMP)",
            maintenance_authority=AuthorityParty(
                name="Bruhat Bengaluru Mahanagara Palike (BBMP)",
                type="municipal_corporation",
                source="BBMP Master Road Registry",
                official_portal_url="https://bbmp.gov.in/roads",
            ),
            road_owner=AuthorityParty(
                name="Government of Karnataka",
                type="state_government",
                source="Karnataka State Gazette",
                official_portal_url="https://karnataka.gov.in",
            ),
            jurisdiction="Bengaluru Urban",
            authority_status="verified" if verified_authority else "not_verified",
        )
    else:
        if not auth.maintenance_authority:
            auth.maintenance_authority = AuthorityParty(
                name="Bruhat Bengaluru Mahanagara Palike (BBMP)",
                type="municipal_corporation",
                source="BBMP Master Road Registry",
                official_portal_url="https://bbmp.gov.in/roads",
            )
        if not auth.road_owner:
            auth.road_owner = AuthorityParty(
                name="Government of Karnataka",
                type="state_government",
                source="Karnataka State Gazette",
                official_portal_url="https://karnataka.gov.in",
            )
        auth.authority_status = "verified" if verified_authority else "not_verified"

    if builder:
        auth.builder_or_contractor = AuthorityParty(
            name=builder,
            source=f"Tender Registry: {tender_id}" if tender_id else "Unverified Civic Submission",
        )

    assignment = None
    if assigned_to:
        assignment = CaseAssignment(
            assigned_to_user_id=assigned_to,
            assigned_at=now,
            assigned_by_user_id="usr_admin",
            assignment_status="assigned",
        )

    res_evidence = []
    if resolved:
        res_evidence = [
            ResolutionEvidenceRecord(
                note="Pothole filled with cold mix asphalt and compacted to grade.",
                recorded_at=now + timedelta(days=2),
                recorded_by_role="authority",
            )
        ]

    dup_analysis = None
    if is_duplicate:
        dup_analysis = DuplicateCheckResponse(
            classification="duplicate",
            similarity_score=0.96,
            matched_reference_id="CIV-2026-0001",
            issue_match=True,
            reason="Exact match with CIV-2026-0001 within 5 meters and same day.",
        )
    elif is_possible_duplicate:
        dup_analysis = DuplicateCheckResponse(
            classification="possible_duplicate",
            similarity_score=0.62,
            matched_reference_id="CIV-2026-0001",
            issue_match=True,
            reason="Similar defect in vicinity but outside deterministic match window.",
        )

    rec_analysis = RecurrenceAnalysis(
        recurrence_detected=True,
        recurrence_count=3,
        related_historical_case_ids=["CIV-2026-0001", "CIV-2026-0002"],
        recurrence_window_days=180,
        history_scan_complete=True,
        recurrence_explanation="3 previous defects detected in 180-day window within 250m.",
    )

    return ComplaintCase(
        reference_id=ref_id,
        user_id=user_id,
        status="resolved" if resolved else "in_progress",
        created_at=now,
        issue=CaseIssue(
            class_name=issue_class,
            label=issue_class.replace("_", " ").title(),
            severity="high",
            confidence=0.92,
        ),
        location=complaint_loc,
        authority=auth,
        assignment=assignment,
        complaint=CaseComplaint(
            language="en",
            title=f"Severe {issue_class} on {road}",
            description=f"Deep {issue_class} posing severe hazard to two-wheelers.",
        ),
        follow_up=FollowUp(guidance="Saved in CVKI."),
        resolution_evidence=res_evidence,
        duplicate_analysis=dup_analysis,
        recurrence_analysis=rec_analysis,
        evidence=["det_box_pothole_001"],
    )


class TestCivicKnowledgeGraphM65(unittest.TestCase):
    def setUp(self):
        self.original_overrides = dict(app.dependency_overrides)
        self.client = TestClient(app)

        self.kg_repo = InMemoryKnowledgeGraphRepository()
        self.kg_service = CivicKnowledgeGraphService(repository=self.kg_repo)
        set_knowledge_graph_service(self.kg_service)

        self.prov_repo = InMemoryProvenanceRepository()
        self.prov_engine = EvidenceProvenanceEngine(repository=self.prov_repo)
        set_provenance_engine(self.prov_engine)

        self.original_case_repo = complaint_case_module.case_repository
        self.case_repo = complaint_case_module.InMemoryComplaintCaseRepository()
        complaint_case_module.set_case_repository(self.case_repo)

    def tearDown(self):
        complaint_case_module.set_case_repository(self.original_case_repo)
        app.dependency_overrides = self.original_overrides

    # --------------------------------------------------
    # A. Node Schema
    # --------------------------------------------------
    def test_a_node_schema(self):
        node = KnowledgeNode(
            node_id="node_test_01",
            node_type=NodeType.ROAD,
            canonical_key="road:mg_road:bengaluru",
            display_name="MG Road",
            metadata={"city": "Bengaluru", "type": "arterial"},
            case_references=["CIV-2026-0001"],
        )
        self.assertEqual(node.node_type, NodeType.ROAD)
        self.assertEqual(node.canonical_key, "road:mg_road:bengaluru")
        self.assertEqual(node.display_name, "MG Road")
        self.assertIn("CIV-2026-0001", node.case_references)
        self.assertIsNotNone(node.created_at)

    # --------------------------------------------------
    # B. Edge Schema
    # --------------------------------------------------
    def test_b_edge_schema(self):
        edge = KnowledgeEdge(
            edge_id="edge_test_01",
            canonical_edge_key="edge:road:mg_road:bengaluru:MAINTAINED_BY:authority:bbmp",
            from_node="road:mg_road:bengaluru",
            to_node="authority:bbmp",
            relation_type=RelationType.MAINTAINED_BY,
            verification_state=VerificationState.VERIFIED,
            evidence_ids=["ev-001"],
            source="BBMP Master Registry",
            source_type=SourceType.GOVERNMENT_REGISTRY,
        )
        self.assertEqual(edge.relation_type, RelationType.MAINTAINED_BY)
        self.assertEqual(edge.verification_state, VerificationState.VERIFIED)
        self.assertEqual(edge.evidence_ids, ["ev-001"])

    # --------------------------------------------------
    # C. Canonical Node Identity
    # --------------------------------------------------
    def test_c_canonical_node_identity(self):
        self.assertEqual(canonical_road_key("  M.G. Road  ", " Bengaluru "), "road:mg_road:bengaluru")
        self.assertEqual(canonical_case_key("CIV-2026-0042"), "case:CIV-2026-0042")
        self.assertEqual(canonical_authority_key("Bruhat Bengaluru Mahanagara Palike"), "authority:bruhat_bengaluru_mahanagara_palike")
        # Coordinate 4-decimal bucket
        self.assertEqual(canonical_location_key(12.971612, 77.594689), "location:12.9716:77.5947")
        self.assertEqual(canonical_jurisdiction_key("Bengaluru Urban"), "jurisdiction:bengaluru_urban")
        self.assertEqual(canonical_builder_key("Larsen & Toubro Ltd."), "builder:larsen_and_toubro_ltd")

    # --------------------------------------------------
    # D. Deterministic Edge Identity
    # --------------------------------------------------
    def test_d_deterministic_edge_identity(self):
        k1 = canonical_edge_key("road:mg_road:bengaluru", RelationType.MAINTAINED_BY, "authority:bbmp")
        k2 = canonical_edge_key("road:mg_road:bengaluru", "MAINTAINED_BY", "authority:bbmp")
        self.assertEqual(k1, k2)
        self.assertEqual(k1, "edge:road:mg_road:bengaluru:MAINTAINED_BY:authority:bbmp")

    # --------------------------------------------------
    # E. Case Graph Creation
    # --------------------------------------------------
    def test_e_case_graph_creation(self):
        case = _build_test_case("CIV-2026-1001", road="Old Airport Road")
        subgraph = self.kg_service.build_case_graph(case)

        self.assertGreater(len(subgraph.nodes), 4)
        self.assertGreater(len(subgraph.edges), 3)

        node_types = {n.node_type for n in subgraph.nodes}
        self.assertIn(NodeType.CASE, node_types)
        self.assertIn(NodeType.CIVIC_ISSUE, node_types)
        self.assertIn(NodeType.LOCATION, node_types)
        self.assertIn(NodeType.ROAD, node_types)
        self.assertIn(NodeType.MAINTENANCE_AUTHORITY, node_types)

        rel_types = {e.relation_type for e in subgraph.edges}
        self.assertIn(RelationType.DETECTED_AS, rel_types)
        self.assertIn(RelationType.LOCATED_AT, rel_types)
        self.assertIn(RelationType.ON_ROAD, rel_types)
        self.assertIn(RelationType.MAINTAINED_BY, rel_types)

    # --------------------------------------------------
    # F. Graph Rebuild Idempotency
    # --------------------------------------------------
    def test_f_graph_rebuild_idempotency(self):
        case = _build_test_case("CIV-2026-1002")
        self.case_repo.save(case)
        g1 = self.kg_service.build_case_graph(case)
        node_count_1 = len(g1.nodes)
        edge_count_1 = len(g1.edges)

        # Rebuild 1st time
        g2 = self.kg_service.rebuild_case_graph("CIV-2026-1002", case=case)
        self.assertEqual(len(g2.nodes), node_count_1)
        self.assertEqual(len(g2.edges), edge_count_1)

        # Rebuild 2nd time
        g3 = self.kg_service.rebuild_case_graph("CIV-2026-1002", case=case)
        self.assertEqual(len(g3.nodes), node_count_1)
        self.assertEqual(len(g3.edges), edge_count_1)

        # Ensure keys match exactly
        self.assertEqual({n.canonical_key for n in g1.nodes}, {n.canonical_key for n in g3.nodes})
        self.assertEqual({e.canonical_edge_key for e in g1.edges}, {e.canonical_edge_key for e in g3.edges})

    # --------------------------------------------------
    # G. Road Relationship
    # --------------------------------------------------
    def test_g_road_relationship(self):
        case = _build_test_case("CIV-2026-1003", road="Outer Ring Road")
        subgraph = self.kg_service.build_case_graph(case)

        road_edges = [e for e in subgraph.edges if e.relation_type == RelationType.ON_ROAD]
        self.assertEqual(len(road_edges), 1)
        road_edge = road_edges[0]
        self.assertEqual(road_edge.to_node, "road:outer_ring_road:bengaluru")
        self.assertIn(road_edge.verification_state, (VerificationState.VERIFIED, VerificationState.PARTIALLY_VERIFIED))

    # --------------------------------------------------
    # H. Jurisdiction Relationship
    # --------------------------------------------------
    def test_h_jurisdiction_relationship(self):
        case = _build_test_case("CIV-2026-1004")
        subgraph = self.kg_service.build_case_graph(case)

        jurisdiction_edges = [e for e in subgraph.edges if e.relation_type == RelationType.WITHIN_JURISDICTION]
        self.assertGreaterEqual(len(jurisdiction_edges), 1)
        self.assertTrue(jurisdiction_edges[0].to_node.startswith("jurisdiction:"))

    # --------------------------------------------------
    # I. Authority Relationship
    # --------------------------------------------------
    def test_i_authority_relationship(self):
        case = _build_test_case("CIV-2026-1005")
        subgraph = self.kg_service.build_case_graph(case)

        auth_edges = [e for e in subgraph.edges if e.relation_type == RelationType.MAINTAINED_BY]
        self.assertGreaterEqual(len(auth_edges), 1)
        auth_edge = auth_edges[0]
        self.assertTrue(auth_edge.to_node.startswith("authority:"))
        self.assertIn(auth_edge.verification_state, (VerificationState.VERIFIED, VerificationState.PARTIALLY_VERIFIED))

    # --------------------------------------------------
    # J. Builder Safety (Strict Anti-Inference)
    # --------------------------------------------------
    def test_j_builder_safety(self):
        # Case WITHOUT explicit tender/contract -> BUILT_BY edge must NOT exist
        case_no_builder = _build_test_case("CIV-2026-1006_no_builder", builder=None)
        sub_no_builder = self.kg_service.build_case_graph(case_no_builder)
        builder_edges = [e for e in sub_no_builder.edges if e.relation_type == RelationType.BUILT_BY]
        self.assertEqual(len(builder_edges), 0)

        # Case WITH tender_id and builder -> BUILT_BY edge created safely
        case_with_builder = _build_test_case(
            "CIV-2026-1006_builder",
            builder="L&T Infrastructure",
            tender_id="TND-KAR-2024-8841",
        )
        sub_with_builder = self.kg_service.build_case_graph(case_with_builder)
        b_edges = [e for e in sub_with_builder.edges if e.relation_type == RelationType.BUILT_BY]
        self.assertEqual(len(b_edges), 1)
        self.assertEqual(b_edges[0].to_node, canonical_builder_key("L&T Infrastructure"))
        self.assertEqual(b_edges[0].source_type, SourceType.TENDER_REGISTRY)

    # --------------------------------------------------
    # K. Provenance Reference
    # --------------------------------------------------
    def test_k_provenance_reference(self):
        case = _build_test_case("CIV-2026-1007")
        subgraph = self.kg_service.build_case_graph(case)

        evidence_backed_relations = {
            RelationType.DETECTED_AS,
            RelationType.LOCATED_AT,
            RelationType.ON_ROAD,
            RelationType.MAINTAINED_BY,
        }
        for edge in subgraph.edges:
            self.assertIsInstance(edge.evidence_ids, list)
            if edge.relation_type in evidence_backed_relations and edge.verification_state == VerificationState.VERIFIED:
                self.assertGreater(len(edge.evidence_ids), 0)

    # --------------------------------------------------
    # L. Verification-State Preservation
    # --------------------------------------------------
    def test_l_verification_state_preservation(self):
        case = _build_test_case("CIV-2026-1008", verified_authority=False)
        subgraph = self.kg_service.build_case_graph(case)

        auth_edge = next((e for e in subgraph.edges if e.relation_type == RelationType.MAINTAINED_BY), None)
        self.assertIsNotNone(auth_edge)
        # Graph must NOT fabricate verified status for an unverified claim
        self.assertNotEqual(auth_edge.verification_state, VerificationState.VERIFIED)

    # --------------------------------------------------
    # M. Stale Evidence Handling
    # --------------------------------------------------
    def test_m_stale_evidence_handling(self):
        case = _build_test_case("CIV-2026-1009")
        ext_ctx = {
            "weather": {
                "weather_code": 800,
                "description": "Clear sky",
                "temperature_c": 26.5,
                "humidity_percent": 65,
                "provider": "open_meteo",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "status": "cached_stale",
            }
        }
        subgraph = self.kg_service.build_case_graph(case, external_context=ext_ctx)

        weather_edge = next((e for e in subgraph.edges if e.relation_type == RelationType.HAS_WEATHER_CONTEXT), None)
        self.assertIsNotNone(weather_edge)
        self.assertEqual(weather_edge.verification_state, VerificationState.PARTIALLY_VERIFIED)

    # --------------------------------------------------
    # N. Invalidated Evidence Handling
    # --------------------------------------------------
    def test_n_invalidated_evidence_handling(self):
        # Register and invalidate an evidence record in M6.4 repository
        ev = self.prov_engine.build_evidence_record(
            claim_type=ClaimType.MAINTENANCE_AUTHORITY,
            source="Old Municipal Register",
            source_type=SourceType.GOVERNMENT_REGISTRY,
            matched_attribute="maintenance_authority",
            explanation="Defunct Municipal Board jurisdiction.",
            verification_state=VerificationState.NOT_VERIFIED,
        )
        self.prov_engine.invalidate_evidence(
            evidence_id=ev.evidence_id,
            reason="Superseded by Karnataka Municipal Act Amendment",
        )
        inv = self.prov_repo.find_by_id(ev.evidence_id)
        self.assertIsNotNone(inv)
        self.assertEqual(inv.status, "invalidated")

        # Test edge backed by invalidated evidence record
        node1 = self.kg_service._ensure_node(NodeType.ROAD, "road:test_rd:bengaluru", "Test Road")
        node2 = self.kg_service._ensure_node(NodeType.MAINTENANCE_AUTHORITY, "authority:old_auth", "Old Authority")
        edge = self.kg_service._ensure_edge(
            from_node=node1,
            to_node=node2,
            relation_type=RelationType.MAINTAINED_BY,
            verification_state=VerificationState.NOT_VERIFIED,
            evidence_ids=[ev.evidence_id],
            source_type=SourceType.GOVERNMENT_REGISTRY,
            explanation="Historical relationship.",
        )

        explanation = self.kg_service.explain_relationship(edge.edge_id)
        self.assertIsNotNone(explanation)
        self.assertIn(ev.evidence_id, explanation.evidence_ids)

        # Missing edge raises LookupError
        with self.assertRaises(LookupError):
            self.kg_service.explain_relationship("edge_test_missing")

    # --------------------------------------------------
    # O. M6.2 Geospatial Integration
    # --------------------------------------------------
    def test_o_geospatial_integration(self):
        case = _build_test_case("CIV-2026-1010", road="Hosur Road")
        subgraph = self.kg_service.build_case_graph(case)

        loc_node = next((n for n in subgraph.nodes if n.node_type == NodeType.LOCATION), None)
        self.assertIsNotNone(loc_node)
        self.assertIn("12.9716", loc_node.canonical_key)

        road_node = next((n for n in subgraph.nodes if n.node_type == NodeType.ROAD), None)
        self.assertIsNotNone(road_node)
        self.assertEqual(road_node.canonical_key, "road:hosur_road:bengaluru")

    # --------------------------------------------------
    # P. M6.3 External Context Integration
    # --------------------------------------------------
    def test_p_external_context_integration(self):
        case = _build_test_case("CIV-2026-1011")
        ext_ctx = {
            "weather": {
                "weather_code": 800,
                "description": "Clear sky",
                "temperature_c": 26.5,
                "humidity_percent": 65,
                "provider": "open_meteo",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "freshness": "fresh",
            },
            "rainfall": {
                "rainfall_1h_mm": 12.4,
                "rainfall_24h_mm": 45.2,
                "provider": "imd_open_data",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "freshness": "fresh",
            },
        }
        subgraph = self.kg_service.build_case_graph(case, external_context=ext_ctx)

        weather_node = next((n for n in subgraph.nodes if n.node_type == NodeType.WEATHER_CONTEXT), None)
        rainfall_node = next((n for n in subgraph.nodes if n.node_type == NodeType.RAINFALL_CONTEXT), None)

        self.assertIsNotNone(weather_node)
        self.assertIsNotNone(rainfall_node)

    # --------------------------------------------------
    # Q. M6.4 Provenance Integration
    # --------------------------------------------------
    def test_q_provenance_integration(self):
        case = _build_test_case("CIV-2026-1012")
        subgraph = self.kg_service.build_case_graph(case)

        road_edge = next((e for e in subgraph.edges if e.relation_type == RelationType.ON_ROAD), None)
        self.assertIsNotNone(road_edge)

        explanation = self.kg_service.explain_relationship(road_edge.edge_id)
        self.assertIsNotNone(explanation)
        self.assertEqual(explanation.relation_type, RelationType.ON_ROAD)
        self.assertGreater(len(explanation.limitations), 0)

    # --------------------------------------------------
    # R. M5.2 Recurrence Integration
    # --------------------------------------------------
    def test_r_recurrence_integration(self):
        case = _build_test_case("CIV-2026-1013")
        subgraph = self.kg_service.build_case_graph(case)

        rec_edges = [e for e in subgraph.edges if e.relation_type == RelationType.RECURRENCE_OF]
        self.assertGreaterEqual(len(rec_edges), 1)
        rec_edge = rec_edges[0]
        self.assertEqual(rec_edge.verification_state, VerificationState.SYSTEM_DERIVED)

    # --------------------------------------------------
    # S. Hotspot Integration
    # --------------------------------------------------
    def test_s_hotspot_integration(self):
        case = _build_test_case("CIV-2026-1014")
        intelligence = CaseIntelligenceResponse(
            reference_id="CIV-2026-1014",
            recurrence=RecurrenceAnalysis(recurrence_detected=False, recurrence_explanation="None"),
            recent_location_case_count=8,
            recent_location_unresolved_count=5,
            hotspot_detected=True,
            hotspot_explanation="Dense cluster in MG Road corridor.",
            resolution_evidence_state="status_only",
            resolution_evidence_explanation="Status only",
        )
        subgraph = self.kg_service.build_case_graph(case, intelligence=intelligence)

        hotspot_edges = [e for e in subgraph.edges if e.relation_type == RelationType.PART_OF_HOTSPOT]
        self.assertGreaterEqual(len(hotspot_edges), 1)
        self.assertEqual(hotspot_edges[0].verification_state, VerificationState.SYSTEM_DERIVED)

    # --------------------------------------------------
    # T. Duplicate Relationship Integration
    # --------------------------------------------------
    def test_t_duplicate_relationship(self):
        case_dup = _build_test_case("CIV-2026-1015", is_duplicate=True)
        sub_dup = self.kg_service.build_case_graph(case_dup)

        dup_edge = next((e for e in sub_dup.edges if e.relation_type == RelationType.DUPLICATE_OF), None)
        self.assertIsNotNone(dup_edge)
        self.assertEqual(dup_edge.to_node, "case:CIV-2026-0001")

        # Possible duplicate should NOT create DUPLICATE_OF edge
        case_possible = _build_test_case("CIV-2026-1016", is_possible_duplicate=True)
        sub_possible = self.kg_service.build_case_graph(case_possible)
        self.assertIsNone(next((e for e in sub_possible.edges if e.relation_type == RelationType.DUPLICATE_OF), None))

    # --------------------------------------------------
    # U. Complaint Relationship
    # --------------------------------------------------
    def test_u_complaint_relationship(self):
        case = _build_test_case("CIV-2026-1017")
        subgraph = self.kg_service.build_case_graph(case)

        comp_edge = next((e for e in subgraph.edges if e.relation_type == RelationType.HAS_COMPLAINT), None)
        self.assertIsNotNone(comp_edge)
        self.assertEqual(comp_edge.verification_state, VerificationState.VERIFIED)

    # --------------------------------------------------
    # V. Resolution Relationship
    # --------------------------------------------------
    def test_v_resolution_relationship(self):
        case = _build_test_case("CIV-2026-1018", resolved=True)
        subgraph = self.kg_service.build_case_graph(case)

        res_edge = next((e for e in subgraph.edges if e.relation_type == RelationType.HAS_RESOLUTION), None)
        self.assertIsNotNone(res_edge)
        self.assertEqual(res_edge.verification_state, VerificationState.VERIFIED)

    # --------------------------------------------------
    # W. Graph Traversal Limits
    # --------------------------------------------------
    def test_w_traversal_limits(self):
        case = _build_test_case("CIV-2026-1019")
        self.kg_service.build_case_graph(case)

        # Depth 1 traversal
        sub_d1 = self.kg_service.get_case_graph("CIV-2026-1019", max_depth=1)
        self.assertLess(len(sub_d1.nodes), 10)

        # Max nodes bound
        sub_bounded = self.kg_service.get_case_graph("CIV-2026-1019", max_nodes=3)
        self.assertLessEqual(len(sub_bounded.nodes), 3)

    # --------------------------------------------------
    # X. Citizen RBAC
    # --------------------------------------------------
    def test_x_citizen_rbac(self):
        case = _build_test_case("CIV-2026-1020", user_id="usr_citizen_42")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_citizen_42",
            role=UserRole.CITIZEN.value,
            email="citizen42@test.org",
        )
        response = self.client.get("/api/v1/knowledge-graph/cases/CIV-2026-1020")
        app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)

    # --------------------------------------------------
    # Y. Authority RBAC
    # --------------------------------------------------
    def test_y_authority_rbac(self):
        case = _build_test_case("CIV-2026-1021", assigned_to="usr_authority_bbmp")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_authority_bbmp",
            role=UserRole.AUTHORITY.value,
            email="authority@bbmp.gov.in",
        )
        response = self.client.get("/api/v1/knowledge-graph/cases/CIV-2026-1021")
        app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)

    # --------------------------------------------------
    # Z. Admin RBAC
    # --------------------------------------------------
    def test_z_admin_rbac(self):
        case = _build_test_case("CIV-2026-1022", user_id="usr_citizen_other")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_admin_001",
            role=UserRole.ADMIN.value,
            email="admin@cvki.org",
        )
        response = self.client.get("/api/v1/knowledge-graph/cases/CIV-2026-1022")
        app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)

    # --------------------------------------------------
    # AA. Cross-User Denial (403)
    # --------------------------------------------------
    def test_aa_cross_user_denial(self):
        case = _build_test_case("CIV-2026-1023", user_id="usr_citizen_owner")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_citizen_attacker",
            role=UserRole.CITIZEN.value,
            email="attacker@test.org",
        )
        response = self.client.get("/api/v1/knowledge-graph/cases/CIV-2026-1023")
        app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 403)
        self.assertIn("own cases", response.json()["detail"].lower())

    # --------------------------------------------------
    # AB. Cross-Authority Denial (403)
    # --------------------------------------------------
    def test_ab_cross_authority_denial(self):
        case = _build_test_case("CIV-2026-1024", assigned_to="usr_auth_ward_1")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_auth_ward_99",
            role=UserRole.AUTHORITY.value,
            email="ward99@gov.in",
        )
        response = self.client.get("/api/v1/knowledge-graph/cases/CIV-2026-1024")
        app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 403)

    # --------------------------------------------------
    # AC. Relationship Explanation
    # --------------------------------------------------
    def test_ac_relationship_explanation(self):
        case = _build_test_case("CIV-2026-1025")
        subgraph = self.kg_service.build_case_graph(case)
        edge = subgraph.edges[0]

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_admin", role=UserRole.ADMIN.value, email="admin@cvki.org"
        )
        response = self.client.get(f"/api/v1/knowledge-graph/relationships/{edge.edge_id}")
        app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["edge_id"], edge.edge_id)
        self.assertIn("explanation", data)
        self.assertIn("limitations", data)

    # --------------------------------------------------
    # AD. Graph Consistency Validation
    # --------------------------------------------------
    def test_ad_graph_consistency_validation(self):
        case = _build_test_case("CIV-2026-1026")
        self.kg_service.build_case_graph(case)

        violations = self.kg_service.validate_graph_consistency()
        self.assertEqual(violations, [])

    # --------------------------------------------------
    # AE. No Fabricated Relationships
    # --------------------------------------------------
    def test_ae_no_fabricated_relationships(self):
        # Case with missing road information
        case = _build_test_case("CIV-2026-1027", road="")
        case.location.road = ""
        subgraph = self.kg_service.build_case_graph(case)

        # There must be NO road node created for empty road
        road_nodes = [n for n in subgraph.nodes if n.node_type == NodeType.ROAD]
        self.assertEqual(len(road_nodes), 0)

    # --------------------------------------------------
    # AF. No Causal Rainfall Edge
    # --------------------------------------------------
    def test_af_no_causal_rainfall_edge(self):
        case = _build_test_case("CIV-2026-1028")
        ext_ctx = {
            "rainfall": {
                "rainfall_1h_mm": 12.4,
                "rainfall_24h_mm": 45.2,
                "provider": "imd_open_data",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "freshness": "fresh",
            }
        }
        subgraph = self.kg_service.build_case_graph(case, external_context=ext_ctx)

        rainfall_edges = [e for e in subgraph.edges if e.relation_type == RelationType.HAS_RAINFALL_CONTEXT]
        self.assertGreaterEqual(len(rainfall_edges), 1)
        for e in rainfall_edges:
            expl = (e.explanation or "").lower()
            self.assertNotIn("caused", expl)
            self.assertNotIn("causing", expl)
            self.assertNotIn("responsible for", expl)

    # --------------------------------------------------
    # AG. Rebuild Determinism
    # --------------------------------------------------
    def test_ag_rebuild_determinism(self):
        case = _build_test_case("CIV-2026-1029")
        g1 = self.kg_service.build_case_graph(case)
        g2 = self.kg_service.rebuild_case_graph("CIV-2026-1029", case=case)

        keys1 = sorted([e.canonical_edge_key for e in g1.edges])
        keys2 = sorted([e.canonical_edge_key for e in g2.edges])
        self.assertEqual(keys1, keys2)

    # --------------------------------------------------
    # AH. No Duplicate Edges
    # --------------------------------------------------
    def test_ah_no_duplicate_edges(self):
        edge1 = KnowledgeEdge(
            edge_id="edge_dup_1",
            canonical_edge_key="edge:nodeA:MAINTAINED_BY:nodeB",
            from_node="nodeA",
            to_node="nodeB",
            relation_type=RelationType.MAINTAINED_BY,
        )
        edge2 = KnowledgeEdge(
            edge_id="edge_dup_2",
            canonical_edge_key="edge:nodeA:MAINTAINED_BY:nodeB",
            from_node="nodeA",
            to_node="nodeB",
            relation_type=RelationType.MAINTAINED_BY,
        )
        self.kg_repo.save_edge(edge1)
        self.kg_repo.save_edge(edge2)

        saved = self.kg_repo.get_edge_by_key("edge:nodeA:MAINTAINED_BY:nodeB")
        self.assertIsNotNone(saved)
        # Should be updated to edge2 or kept singular, not duplicated
        self.assertEqual(len(self.kg_repo.all_edges()), 1)

    # --------------------------------------------------
    # AI. Privacy Filtering
    # --------------------------------------------------
    def test_ai_privacy_filtering(self):
        case = _build_test_case("CIV-2026-1030", user_id="usr_citizen_secret")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_citizen_secret",
            role=UserRole.CITIZEN.value,
            email="secret@domain.com",
        )
        response = self.client.get("/api/v1/knowledge-graph/cases/CIV-2026-1030")
        app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        data = response.json()
        for node in data["nodes"]:
            self.assertNotEqual(node["node_type"], "user_actor")
            self.assertNotIn("email", node.get("metadata", {}))
            self.assertNotIn("user_id", node.get("metadata", {}))

    # --------------------------------------------------
    # AJ. Performance Baseline
    # --------------------------------------------------
    def test_aj_performance_baseline(self):
        case = _build_test_case("CIV-2026-1031")

        # 1. Case graph creation benchmark
        t0 = time.perf_counter()
        subgraph = self.kg_service.build_case_graph(case)
        creation_ms = (time.perf_counter() - t0) * 1000

        # 2. Case graph retrieval benchmark
        t1 = time.perf_counter()
        retrieved = self.kg_service.get_case_graph("CIV-2026-1031")
        retrieval_ms = (time.perf_counter() - t1) * 1000

        # 3. Graph rebuild benchmark
        t2 = time.perf_counter()
        rebuilt = self.kg_service.rebuild_case_graph("CIV-2026-1031", case=case)
        rebuild_ms = (time.perf_counter() - t2) * 1000

        # 4. Traversal benchmark
        t3 = time.perf_counter()
        traversed = self.kg_service.get_subgraph("case:civ-2026-1031", max_depth=3)
        traversal_ms = (time.perf_counter() - t3) * 1000

        self.assertLess(creation_ms, 100.0, f"Graph creation exceeded threshold: {creation_ms:.2f}ms")
        self.assertLess(retrieval_ms, 50.0, f"Graph retrieval exceeded threshold: {retrieval_ms:.2f}ms")
        self.assertLess(rebuild_ms, 100.0, f"Graph rebuild exceeded threshold: {rebuild_ms:.2f}ms")
        self.assertLess(traversal_ms, 50.0, f"Graph traversal exceeded threshold: {traversal_ms:.2f}ms")


if __name__ == "__main__":
    unittest.main()
