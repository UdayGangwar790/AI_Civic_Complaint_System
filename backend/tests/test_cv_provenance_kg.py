"""
CVKI - Module 8.7: Computer Vision Provenance & Knowledge Graph Integration Tests

Verifies:
1. Provenance Engine (M6.4) generates Detection Evidence containing standardized model
   identity (model_id, model_version, model_hash, provider_id) and observation semantics.
2. Semantic boundaries: CV output represents model observation, NOT physical ground truth.
3. Knowledge Graph (M6.5) creates DETECTION nodes with model and provider metadata,
   linked via DETECTED_AS and GENERATED_FROM edges.
4. Invalidation propagation: Invalidated evidence properly reflects in graph state.
5. RBAC safety: Case-level isolation prevents cross-citizen inspection of evidence chains.
"""

from datetime import datetime, timezone
import unittest

from app.schemas.authority import AuthorityParty, AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.schemas.knowledge_graph import NodeType, RelationType
from app.schemas.provenance import (
    ClaimType,
    EvidenceRecord,
    SourceType,
    VerificationState,
)
from app.services.knowledge_graph import (
    CivicKnowledgeGraphService,
    InMemoryKnowledgeGraphRepository,
)
from app.services.provenance_engine import (
    EvidenceProvenanceEngine,
    InMemoryProvenanceRepository,
)


def build_sample_case(case_ref: str = "CASE-2026-M8-001", user_id: str = "citizen_001") -> ComplaintCase:
    loc = ComplaintLocation(
        road="Janpath Road",
        area="Connaught Place",
        city="New Delhi",
        district="New Delhi",
        state="Delhi",
        latitude=28.6139,
        longitude=77.2090,
        accuracy_m=12.5,
    )
    auth = AuthorityResult(
        authority_status="verified",
        authority_name="New Delhi Municipal Council (NDMC)",
        responsible_department="Road Maintenance Division",
        official_portal_url="https://ndmc.gov.in",
        maintenance_authority=AuthorityParty(
            name="New Delhi Municipal Council (NDMC)",
            type="municipal_corporation",
            source="Official Road Register",
            official_portal_url="https://ndmc.gov.in",
        ),
        road_owner=AuthorityParty(
            name="Government of NCT of Delhi",
            type="state_government",
            source="Delhi Gazette",
            official_portal_url="https://delhi.gov.in",
        ),
    )
    now = datetime.now(timezone.utc)
    return ComplaintCase(
        reference_id=case_ref,
        user_id=user_id,
        status="submitted_to_cvki",
        created_at=now,
        issue=CaseIssue(
            class_name="open_damaged_manhole",
            label="Open / Damaged Manhole",
            severity="high",
            confidence=0.88,
        ),
        location=loc,
        authority=auth,
        complaint=CaseComplaint(
            language="en",
            title="Hazardous open manhole near Janpath metro station",
            description="Open manhole uncovered on main road causing severe risk to motorists.",
        ),
        follow_up=FollowUp(guidance="Registered in CVKI."),
        evidence=["det_box_manhole_001"],
    )


class TestCVProvenanceAndKnowledgeGraph(unittest.TestCase):
    """Test suite for CV provenance and knowledge graph integration."""

    def setUp(self):
        self.prov_repo = InMemoryProvenanceRepository()
        self.provenance = EvidenceProvenanceEngine(repository=self.prov_repo)
        self.kg_repo = InMemoryKnowledgeGraphRepository()
        self.kg = CivicKnowledgeGraphService(repository=self.kg_repo)

    def test_01_provenance_detection_evidence_contract(self):
        case = build_sample_case()
        resp = self.provenance.generate_case_provenance_chain(case)
        records = resp.claims

        # Find detection record
        det_records = [r for r in records if r.claim_type == ClaimType.DETECTION]
        self.assertEqual(len(det_records), 1)
        rec = det_records[0]

        # Verify source and types
        self.assertEqual(rec.source_type, SourceType.CV_MODEL)
        self.assertIn("m1.13-yolov8n", rec.source)

        # Verify standardized metadata attributes
        meta = rec.metadata
        self.assertEqual(meta["model_id"], "m1.13-yolov8n")
        self.assertIn(meta["model_version"], {"1.13", "1.13.0", "M1.13-yolov8n"})
        self.assertEqual(meta["model_hash"], "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3")
        self.assertIn(meta["provider_id"], {"m113_yolo_provider", "yolov8_provider"})
        self.assertEqual(meta["observation_type"], "model_observation")
        self.assertFalse(meta["ground_truth"])  # Must not claim physical ground truth

    def test_02_semantic_boundary_confidence_is_evidence_strength(self):
        case = build_sample_case()
        resp = self.provenance.generate_case_provenance_chain(case)
        det_rec = [r for r in resp.claims if r.claim_type == ClaimType.DETECTION][0]

        # Verify that confidence is recorded as observation strength
        self.assertEqual(det_rec.metadata["confidence"], 0.88)
        self.assertIn("88%", det_rec.explanation)

    def test_03_knowledge_graph_detection_node_and_relationships(self):
        case = build_sample_case()
        subgraph = self.kg.build_case_graph(case)

        # 1. Detection node exists
        det_nodes = [n for n in subgraph.nodes if n.node_type == NodeType.DETECTION]
        self.assertEqual(len(det_nodes), 1)
        det_node = det_nodes[0]
        self.assertEqual(det_node.metadata["model_id"], "m1.13-yolov8n")
        self.assertIn(det_node.metadata["provider_id"], {"m113_yolo_provider", "yolov8_provider"})
        self.assertEqual(det_node.metadata["observation_type"], "model_observation")

        # 2. Case -> Issue edge (DETECTED_AS)
        detected_as_edges = [e for e in subgraph.edges if e.relation_type == RelationType.DETECTED_AS]
        self.assertEqual(len(detected_as_edges), 1)

        # 3. Case -> Detection edge (GENERATED_FROM)
        gen_edges = [e for e in subgraph.edges if e.relation_type == RelationType.GENERATED_FROM]
        self.assertEqual(len(gen_edges), 1)
        self.assertEqual(gen_edges[0].source_type, SourceType.CV_MODEL)

    def test_04_invalidation_handling(self):
        """When CV evidence is invalidated, graph reflects unverified state."""
        case = build_sample_case()
        resp = self.provenance.generate_case_provenance_chain(case)

        # Invalidate detection evidence
        det_ev = [r for r in resp.claims if r.claim_type == ClaimType.DETECTION][0]
        det_ev.verification_state = VerificationState.NOT_VERIFIED
        det_ev.status = "invalidated"
        det_ev.invalidation_reason = "Human inspector confirmed false positive manhole reflection."

        subgraph = self.kg.build_case_graph(case, provenance=resp)
        detected_as_edges = [e for e in subgraph.edges if e.relation_type == RelationType.DETECTED_AS]
        self.assertEqual(len(detected_as_edges), 1)
        self.assertEqual(detected_as_edges[0].verification_state, VerificationState.NOT_VERIFIED)

    def test_05_rbac_and_isolation(self):
        case_a = build_sample_case(case_ref="CASE-A", user_id="citizen_a")
        case_b = build_sample_case(case_ref="CASE-B", user_id="citizen_b")

        resp_a = self.provenance.generate_case_provenance_chain(case_a)
        resp_b = self.provenance.generate_case_provenance_chain(case_b)

        # Case references are strictly segregated
        self.assertTrue(all(r.case_reference == "CASE-A" for r in resp_a.claims))
        self.assertTrue(all(r.case_reference == "CASE-B" for r in resp_b.claims))

        # Ensure no internal filesystem paths leak into evidence records
        raw_repr = str(resp_a.claims)
        self.assertNotIn("Users", raw_repr)
        self.assertNotIn("best.pt", raw_repr)


if __name__ == "__main__":
    unittest.main()
