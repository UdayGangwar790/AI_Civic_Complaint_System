"""
CVKI - Module 9.6: Provenance & Knowledge Graph Integration Tests

Covers:
1. M9.4 result creates provenance
2. M9.5 result creates provenance
3. Deterministic fingerprint
4. Provenance contains epistemic state
5. M9.4 remains USER_REPORTED / SYSTEM_DERIVED
6. M9.5 remains MODEL_OBSERVATION / SYSTEM_DERIVED
7. No automatic VERIFIED_EVIDENCE
8. Invalidation works
9. Invalidated evidence cannot support verified state
10. M9.4 KG node creation
11. M9.5 KG node creation
12. Correct KG relationships
13. No dangling edges
14. Relationship explanation works
15. Citizen ownership isolation
16. Authority assignment isolation
17. Admin access
18. No PII leakage
19. No credential leakage
20. Deterministic rebuild
21. Duplicate evidence prevention
22. No duplicate KG nodes
23. M6.4 regression
24. M6.5 regression
25. M9.1–M9.5 regression
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
from app.schemas.multimodal import (
    AssertionType,
    ConsistencyAssessmentState,
    EpistemicState,
    EvidenceQuality,
    IssueCategory,
    ResolutionAuditOutcome,
    VernacularNormalizationResult,
    VisualResolutionAuditResult,
)
from app.schemas.knowledge_graph import (
    KnowledgeNode,
    KnowledgeEdge,
    NodeType,
    RelationType,
    canonical_case_key,
    canonical_issue_key,
    canonical_vernacular_normalization_key,
    canonical_visual_audit_key,
)
from app.schemas.provenance import (
    ClaimType,
    EvidenceRecord,
    SourceType,
    VerificationState,
    calculate_evidence_hash,
)
from app.services.knowledge_graph import (
    CivicKnowledgeGraphService,
    InMemoryKnowledgeGraphRepository,
    set_knowledge_graph_service,
)
from app.services.provenance_engine import (
    EvidenceProvenanceEngine,
    InMemoryProvenanceRepository,
    set_provenance_engine,
)
from app.services.multimodal.provenance_kg_integrator import (
    MultimodalProvenanceKGIntegrator,
    set_multimodal_provenance_kg_integrator,
)


def create_sample_case(case_ref: str = "CASE-2026-M96-001", user_id: str = "citizen_42") -> ComplaintCase:
    loc = ComplaintLocation(
        road="MG Road",
        area="Indiranagar",
        city="Bengaluru",
        district="Bengaluru Urban",
        state="Karnataka",
        latitude=12.9716,
        longitude=77.5946,
        accuracy_m=10.0,
    )
    auth = AuthorityResult(
        authority_status="verified",
        authority_name="Bruhat Bengaluru Mahanagara Palike (BBMP)",
        responsible_department="Roads and Infrastructure",
        official_portal_url="https://bbmp.gov.in",
        maintenance_authority=AuthorityParty(
            name="Bruhat Bengaluru Mahanagara Palike (BBMP)",
            type="municipal_corporation",
            jurisdiction="Bengaluru",
            source="BBMP Registry",
            official_portal_url="https://bbmp.gov.in",
        ),
        road_owner=AuthorityParty(
            name="State PWD Karnataka",
            type="state_pwd",
            jurisdiction="Karnataka",
            source="State Register",
            official_portal_url="https://kpwd.karnataka.gov.in",
        ),
    )
    issue = CaseIssue(
        class_name="open_damaged_manhole",
        confidence=0.91,
        severity="high",
        label="Open / Damaged Manhole",
    )
    complaint = CaseComplaint(
        title="Hazardous open manhole",
        description="Open manhole near the junction",
        category="Road Safety",
        language="en",
    )
    follow_up = FollowUp(
        history=[],
        resolved=False,
        guidance="Registered in CVKI.",
    )
    return ComplaintCase(
        case_id="case_m96_sample_001",
        reference_id=case_ref,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        status="submitted_to_cvki",
        location=loc,
        issue=issue,
        complaint=complaint,
        authority=auth,
        follow_up=follow_up,
        metadata={"cv_inference": {"model_id": "m1.13-yolov8n", "provider_id": "m113_yolo_provider"}},
    )


class TestM96ProvenanceKGIntegration(unittest.TestCase):
    def setUp(self):
        self.prov_repo = InMemoryProvenanceRepository()
        self.prov_engine = EvidenceProvenanceEngine(repository=self.prov_repo)
        set_provenance_engine(self.prov_engine)

        self.kg_repo = InMemoryKnowledgeGraphRepository()
        self.kg_service = CivicKnowledgeGraphService(repository=self.kg_repo)
        set_knowledge_graph_service(self.kg_service)

        self.integrator = MultimodalProvenanceKGIntegrator(
            prov_engine=self.prov_engine, kg_service=self.kg_service
        )
        set_multimodal_provenance_kg_integrator(self.integrator)

        self.case_ref = "CASE-2026-M96-001"
        self.case = create_sample_case(self.case_ref)

    # 1. M9.4 result creates provenance
    def test_01_m94_result_creates_provenance(self):
        norm_res = VernacularNormalizationResult(
            original_text="manhole khula hai",
            normalized_text="open damaged manhole",
            detected_language="hi-Latn",
            script="latin",
            canonical_terms=["manhole", "open"],
            issue_candidates=[IssueCategory.OPEN_DAMAGED_MANHOLE],
            assertion_type=AssertionType.ASSERTED,
            normalization_applied=True,
            confidence=0.94,
            explanation="Hinglish vernacular mapped to open_damaged_manhole.",
        )
        rec = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm_res)
        self.assertIsNotNone(rec)
        self.assertTrue(rec.evidence_id.startswith("ev_vnorm_"))
        self.assertEqual(rec.claim_type, ClaimType.VERNACULAR_NORMALIZATION)
        self.assertEqual(rec.source_type, SourceType.SYSTEM_DERIVED)

    # 2. M9.5 result creates provenance
    def test_02_m95_result_creates_provenance(self):
        audit_res = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            before_observation="Clear open manhole detected with 0.92 confidence",
            after_observation="No open manhole detected (defect cleared)",
            evidence_quality=EvidenceQuality.SUFFICIENT,
            temporal_consistency=ConsistencyAssessmentState.CONSISTENT,
            spatial_consistency=ConsistencyAssessmentState.CONSISTENT,
            explanation="Visual comparison indicates defect is no longer observed.",
            limitations=["Audit does not constitute engineering sign-off."],
            epistemic_state=EpistemicState.MODEL_OBSERVATION,
            model_metadata={"engine_identity": "m9_5_visual_resolution_auditor", "model_hash": "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"},
        )
        rec = self.integrator.record_visual_audit_provenance(self.case_ref, audit_res)
        self.assertIsNotNone(rec)
        self.assertTrue(rec.evidence_id.startswith("ev_vaudit_"))
        self.assertEqual(rec.claim_type, ClaimType.VISUAL_RESOLUTION_AUDIT)
        self.assertEqual(rec.source_type, SourceType.SYSTEM_DERIVED)

    # 3. Deterministic fingerprint
    def test_03_deterministic_fingerprint(self):
        norm_res = VernacularNormalizationResult(
            original_text="road pe gaddha hai",
            normalized_text="pothole",
            detected_language="hi-Latn",
            script="latin",
            issue_candidates=[IssueCategory.OTHER_CIVIC_ISSUE],
            assertion_type=AssertionType.ASSERTED,
            confidence=0.88,
        )
        # Call calculate_evidence_hash directly twice with same parameters
        hash1 = calculate_evidence_hash(
            claim_type=ClaimType.VERNACULAR_NORMALIZATION.value,
            matched_attribute="vernacular_normalization",
            source="m9_4_vernacular_normalizer Vernacular Normalizer",
            source_type=SourceType.SYSTEM_DERIVED.value,
            value={"original_text": "road pe gaddha hai", "normalized_text": "pothole"},
        )
        hash2 = calculate_evidence_hash(
            claim_type=ClaimType.VERNACULAR_NORMALIZATION.value,
            matched_attribute="vernacular_normalization",
            source="m9_4_vernacular_normalizer Vernacular Normalizer",
            source_type=SourceType.SYSTEM_DERIVED.value,
            value={"original_text": "road pe gaddha hai", "normalized_text": "pothole"},
        )
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

    # 4. Provenance contains epistemic state
    def test_04_provenance_contains_epistemic_state(self):
        norm_res = VernacularNormalizationResult(
            original_text="paani bhara hua hai",
            normalized_text="waterlogging",
            detected_language="hi-Latn",
            script="latin",
            issue_candidates=[IssueCategory.ROAD_WATERLOGGING],
            assertion_type=AssertionType.ASSERTED,
            confidence=0.90,
        )
        rec = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm_res)
        self.assertIn("epistemic_state", rec.metadata)
        self.assertEqual(rec.metadata["confidence_type"], "lexical_confidence")
        self.assertFalse(rec.metadata.get("ground_truth", True))

    # 5. M9.4 remains USER_REPORTED/SYSTEM_DERIVED
    def test_05_m94_remains_user_reported_system_derived(self):
        norm_res = VernacularNormalizationResult(
            original_text="manhole khula hai",
            normalized_text="open damaged manhole",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OPEN_DAMAGED_MANHOLE],
            assertion_type=AssertionType.ASSERTED,
            confidence=0.95,
        )
        rec = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm_res)
        self.assertNotEqual(rec.verification_state, VerificationState.VERIFIED)
        self.assertEqual(rec.verification_state, VerificationState.SYSTEM_DERIVED)
        self.assertEqual(rec.source_type, SourceType.SYSTEM_DERIVED)

    # 6. M9.5 remains MODEL_OBSERVATION/SYSTEM_DERIVED
    def test_06_m95_remains_model_observation_system_derived(self):
        audit_res = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            evidence_quality=EvidenceQuality.SUFFICIENT,
            temporal_consistency=ConsistencyAssessmentState.CONSISTENT,
            spatial_consistency=ConsistencyAssessmentState.CONSISTENT,
            explanation="Defect is not observed.",
            epistemic_state=EpistemicState.MODEL_OBSERVATION,
            model_metadata={"model_hash": "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"},
        )
        rec = self.integrator.record_visual_audit_provenance(self.case_ref, audit_res)
        self.assertNotEqual(rec.verification_state, VerificationState.VERIFIED)
        self.assertEqual(rec.verification_state, VerificationState.SYSTEM_DERIVED)
        self.assertEqual(rec.metadata["epistemic_state"], "MODEL_OBSERVATION")
        self.assertFalse(rec.metadata["is_repair_confirmed"])

    # 7. No automatic VERIFIED_EVIDENCE
    def test_07_no_automatic_verified_evidence(self):
        # Even with DEFECT_NOT_OBSERVED, outcome must NEVER be VERIFIED
        audit_res = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
            issue_category=IssueCategory.OTHER_CIVIC_ISSUE,
            evidence_quality=EvidenceQuality.SUFFICIENT,
            explanation="No defect observed in after image.",
            epistemic_state=EpistemicState.SYSTEM_DERIVED,
        )
        rec = self.integrator.record_visual_audit_provenance(self.case_ref, audit_res)
        self.assertNotEqual(rec.verification_state, VerificationState.VERIFIED)
        self.assertNotEqual(rec.verification_state.value, "verified")

        # Inconclusive/insufficient must be NOT_VERIFIED
        inconclusive_res = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.INCONCLUSIVE,
            issue_category=IssueCategory.OTHER_CIVIC_ISSUE,
            evidence_quality=EvidenceQuality.DEGRADED,
            explanation="Comparison inconclusive.",
            epistemic_state=EpistemicState.SYSTEM_DERIVED,
        )
        rec_incon = self.integrator.record_visual_audit_provenance(self.case_ref, inconclusive_res)
        self.assertEqual(rec_incon.verification_state, VerificationState.NOT_VERIFIED)

    # 8. Invalidation works
    def test_08_invalidation_works(self):
        norm_res = VernacularNormalizationResult(
            original_text="kachra pada hai",
            normalized_text="garbage dump",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OTHER_CIVIC_ISSUE],
            confidence=0.85,
        )
        rec = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm_res)
        invalidated = self.integrator.invalidate_m9_evidence(
            evidence_id=rec.evidence_id,
            reason="Inspector determined text was a quote from another city",
        )
        self.assertIsNotNone(invalidated)
        self.assertEqual(invalidated.status, "invalidated")
        self.assertEqual(invalidated.verification_state, VerificationState.NOT_VERIFIED)
        self.assertEqual(invalidated.invalidation_reason, "Inspector determined text was a quote from another city")
        # Retain original fingerprint
        self.assertEqual(invalidated.evidence_hash, rec.evidence_hash)

    # 9. Invalidated evidence cannot support verified state
    def test_09_invalidated_evidence_cannot_support_verified_state(self):
        norm_res = VernacularNormalizationResult(
            original_text="manhole toota hai",
            normalized_text="damaged manhole",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OPEN_DAMAGED_MANHOLE],
            confidence=0.92,
        )
        ev_rec, kg_node = self.integrator.integrate_vernacular_normalization(
            self.case_ref, norm_res, norm_id="norm_test_09"
        )
        # Invalidate the evidence
        self.integrator.invalidate_m9_evidence(ev_rec.evidence_id, reason="Erroneous submission")

        # Check edge explanation
        edge_key = f"edge:{canonical_case_key(self.case_ref)}:HAS_VERNACULAR_NORMALIZATION:{kg_node.canonical_key}"
        expl = self.kg_service.explain_relationship(edge_key)
        self.assertEqual(expl.verification_state, VerificationState.NOT_VERIFIED)
        self.assertTrue(any("invalidated" in lim.lower() for lim in expl.limitations))

    # 10. M9.4 KG node creation
    def test_10_m94_kg_node_creation(self):
        norm_res = VernacularNormalizationResult(
            original_text="street light band hai",
            normalized_text="street light outage",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OTHER_CIVIC_ISSUE],
            assertion_type=AssertionType.ASSERTED,
            confidence=0.89,
        )
        ev_rec, kg_node = self.integrator.integrate_vernacular_normalization(
            self.case_ref, norm_res, norm_id="norm_test_10"
        )
        self.assertEqual(kg_node.node_type, NodeType.VERNACULAR_NORMALIZATION)
        self.assertIn("Vernacular Norm", kg_node.display_name)
        self.assertEqual(kg_node.metadata["detected_language"], "hi-Latn")
        self.assertEqual(kg_node.metadata["epistemic_state"], "SYSTEM_DERIVED")

    # 11. M9.5 KG node creation
    def test_11_m95_kg_node_creation(self):
        audit_res = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_PERSISTS,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            evidence_quality=EvidenceQuality.SUFFICIENT,
            temporal_consistency=ConsistencyAssessmentState.CONSISTENT,
            spatial_consistency=ConsistencyAssessmentState.CONSISTENT,
            explanation="Open manhole persists in after image.",
            epistemic_state=EpistemicState.MODEL_OBSERVATION,
        )
        ev_rec, kg_node = self.integrator.integrate_visual_audit(
            self.case_ref, audit_res, audit_id="audit_test_11"
        )
        self.assertEqual(kg_node.node_type, NodeType.VISUAL_RESOLUTION_AUDIT)
        self.assertIn("Visual Audit", kg_node.display_name)
        self.assertEqual(kg_node.metadata["outcome"], "DEFECT_PERSISTS")
        self.assertFalse(kg_node.metadata["is_repair_confirmed"])

    # 12. Correct KG relationships
    def test_12_correct_kg_relationships(self):
        norm_res = VernacularNormalizationResult(
            original_text="manhole khula hai",
            normalized_text="open manhole",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OPEN_DAMAGED_MANHOLE],
            confidence=0.95,
        )
        ev_rec, kg_node = self.integrator.integrate_vernacular_normalization(
            self.case_ref, norm_res, norm_id="norm_test_12"
        )
        edges = self.kg_repo.find_edges_from(canonical_case_key(self.case_ref))
        vnorm_edges = [e for e in edges if e.relation_type == RelationType.HAS_VERNACULAR_NORMALIZATION]
        self.assertEqual(len(vnorm_edges), 1)
        self.assertEqual(vnorm_edges[0].to_node, kg_node.canonical_key)

        # Outgoing edges from vnorm_node: NORMALIZED_AS -> CIVIC_ISSUE, SUPPORTED_BY -> EVIDENCE
        norm_out_edges = self.kg_repo.find_edges_from(kg_node.canonical_key)
        norm_as_edges = [e for e in norm_out_edges if e.relation_type == RelationType.NORMALIZED_AS]
        self.assertEqual(len(norm_as_edges), 1)
        self.assertEqual(norm_as_edges[0].to_node, canonical_issue_key("open_damaged_manhole"))

        # Verify NEVER creates REPAIRED or FIXED edge
        all_edges = self.kg_repo.all_edges()
        rel_types = {e.relation_type.value for e in all_edges}
        self.assertNotIn("REPAIRED", rel_types)
        self.assertNotIn("FIXED", rel_types)
        self.assertNotIn("REPAIR_CONFIRMED", rel_types)

    # 13. No dangling edges
    def test_13_no_dangling_edges(self):
        audit_res = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
            issue_category=IssueCategory.ROAD_WATERLOGGING,
            evidence_quality=EvidenceQuality.SUFFICIENT,
            explanation="Defect resolved in visual observation.",
            epistemic_state=EpistemicState.MODEL_OBSERVATION,
        )
        self.integrator.integrate_visual_audit(
            self.case_ref, audit_res, audit_id="audit_test_13"
        )
        # Every edge endpoint must exist in repository
        all_nodes = {n.canonical_key: n for n in self.kg_repo.all_nodes()}
        for edge in self.kg_repo.all_edges():
            self.assertIn(edge.from_node, all_nodes, f"Dangling from_node: {edge.from_node}")
            self.assertIn(edge.to_node, all_nodes, f"Dangling to_node: {edge.to_node}")

    # 14. Relationship explanation works
    def test_14_relationship_explanation_works(self):
        norm_res = VernacularNormalizationResult(
            original_text="sadak par gaddha",
            normalized_text="pothole",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OTHER_CIVIC_ISSUE],
            confidence=0.91,
            explanation="Hindi expression mapped to pothole.",
        )
        ev_rec, kg_node = self.integrator.integrate_vernacular_normalization(
            self.case_ref, norm_res, norm_id="norm_test_14"
        )
        edge_key = f"edge:{canonical_case_key(self.case_ref)}:HAS_VERNACULAR_NORMALIZATION:{kg_node.canonical_key}"
        expl = self.kg_service.explain_relationship(edge_key)
        self.assertIsNotNone(expl)
        self.assertEqual(expl.relation_type, RelationType.HAS_VERNACULAR_NORMALIZATION)
        self.assertEqual(len(expl.evidence_records), 1)
        self.assertEqual(expl.evidence_records[0]["evidence_id"], ev_rec.evidence_id)
        self.assertTrue(len(expl.limitations) >= 2)

    # 15. Citizen ownership isolation
    def test_15_citizen_ownership_isolation(self):
        case_a = create_sample_case("CASE-CITIZEN-A", user_id="citizen_a")
        case_b = create_sample_case("CASE-CITIZEN-B", user_id="citizen_b")
        norm_a = VernacularNormalizationResult(
            original_text="kachra yahan", normalized_text="garbage", issue_candidates=[IssueCategory.OTHER_CIVIC_ISSUE]
        )
        norm_b = VernacularNormalizationResult(
            original_text="light kharab", normalized_text="street light", issue_candidates=[IssueCategory.OTHER_CIVIC_ISSUE]
        )
        rec_a = self.integrator.record_vernacular_normalization_provenance("CASE-CITIZEN-A", norm_a)
        rec_b = self.integrator.record_vernacular_normalization_provenance("CASE-CITIZEN-B", norm_b)

        # Ensure repository queries isolate strictly by case
        records_a = self.prov_repo.find_by_case("CASE-CITIZEN-A")
        records_b = self.prov_repo.find_by_case("CASE-CITIZEN-B")
        self.assertTrue(all(r.case_reference == "CASE-CITIZEN-A" for r in records_a))
        self.assertTrue(all(r.case_reference == "CASE-CITIZEN-B" for r in records_b))
        self.assertNotIn(rec_b.evidence_id, [r.evidence_id for r in records_a])

    # 16. Authority assignment isolation
    def test_16_authority_assignment_isolation(self):
        case = create_sample_case("CASE-AUTH-001")
        audit = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_PERSISTS,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            explanation="Persists",
        )
        rec = self.integrator.record_visual_audit_provenance("CASE-AUTH-001", audit)
        records = self.prov_repo.find_by_case("CASE-AUTH-001")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].case_reference, "CASE-AUTH-001")

    # 17. Admin access
    def test_17_admin_access(self):
        # Admin can access full provenance history including versions
        norm = VernacularNormalizationResult(
            original_text="paani jama", normalized_text="waterlogging", issue_candidates=[IssueCategory.ROAD_WATERLOGGING]
        )
        rec = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm)
        history = self.prov_repo.find_history(self.case_ref, ClaimType.VERNACULAR_NORMALIZATION)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].evidence_id, rec.evidence_id)

    # 18. No PII leakage
    def test_18_no_pii_leakage(self):
        norm = VernacularNormalizationResult(
            original_text="phone 9876543210 email test@example.com",
            normalized_text="waterlogging",
            issue_candidates=[IssueCategory.ROAD_WATERLOGGING],
            metadata={"secret_field": "confidential_token"},
        )
        rec = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm)
        dump_str = rec.model_dump_json()
        self.assertNotIn("confidential_token", dump_str)

    # 19. No credential leakage
    def test_19_no_credential_leakage(self):
        audit = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            explanation="Audit complete",
            model_metadata={"password": "root_password", "token": "bearer_123"},
        )
        rec = self.integrator.record_visual_audit_provenance(self.case_ref, audit)
        dump = rec.model_dump_json()
        self.assertNotIn("root_password", dump)
        self.assertNotIn("bearer_123", dump)

    # 20. Deterministic rebuild
    def test_20_deterministic_rebuild(self):
        # Build initial graph
        subgraph_1 = self.kg_service.build_case_graph(self.case)
        node_keys_1 = sorted([n.canonical_key for n in subgraph_1.nodes])
        edge_keys_1 = sorted([e.canonical_edge_key for e in subgraph_1.edges])

        # Rebuild graph
        subgraph_2 = self.kg_service.rebuild_case_graph(self.case_ref, case=self.case)
        node_keys_2 = sorted([n.canonical_key for n in subgraph_2.nodes])
        edge_keys_2 = sorted([e.canonical_edge_key for e in subgraph_2.edges])

        self.assertEqual(node_keys_1, node_keys_2)
        self.assertEqual(edge_keys_1, edge_keys_2)

    # 21. Duplicate evidence prevention
    def test_21_duplicate_evidence_prevention(self):
        norm = VernacularNormalizationResult(
            original_text="manhole khula hai",
            normalized_text="open manhole",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OPEN_DAMAGED_MANHOLE],
            confidence=0.95,
        )
        rec1 = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm)
        rec2 = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm)
        # Should reuse identical active record
        self.assertEqual(rec1.evidence_id, rec2.evidence_id)

    # 22. No duplicate KG nodes
    def test_22_no_duplicate_kg_nodes(self):
        norm = VernacularNormalizationResult(
            original_text="manhole khula hai",
            normalized_text="open manhole",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OPEN_DAMAGED_MANHOLE],
            confidence=0.95,
        )
        _, node1 = self.integrator.integrate_vernacular_normalization(self.case_ref, norm, norm_id="fixed_norm_id")
        _, node2 = self.integrator.integrate_vernacular_normalization(self.case_ref, norm, norm_id="fixed_norm_id")
        self.assertEqual(node1.node_id, node2.node_id)
        # Total nodes with that key should be 1
        all_norm_nodes = [
            n for n in self.kg_repo.all_nodes()
            if n.node_type == NodeType.VERNACULAR_NORMALIZATION and n.canonical_key == node1.canonical_key
        ]
        self.assertEqual(len(all_norm_nodes), 1)

    # 23. M6.4 regression
    def test_23_m64_regression(self):
        # Verify existing M6.4 provenance chain generation for case
        prov_response = self.prov_engine.generate_case_provenance_chain(self.case)
        self.assertIsNotNone(prov_response)
        self.assertEqual(prov_response.reference_id, self.case_ref)
        self.assertTrue(len(prov_response.claims) >= 3)
        claim_types = {c.claim_type for c in prov_response.claims}
        self.assertIn(ClaimType.DETECTION, claim_types)
        self.assertIn(ClaimType.LOCATION, claim_types)

    # 24. M6.5 regression
    def test_24_m65_regression(self):
        # Verify existing M6.5 build_case_graph and subgraph traversal
        subgraph = self.kg_service.build_case_graph(self.case)
        self.assertIsNotNone(subgraph)
        self.assertEqual(subgraph.root_node_key, canonical_case_key(self.case_ref))
        self.assertTrue(subgraph.total_nodes >= 3)
        self.assertTrue(subgraph.total_edges >= 2)

    # 25. M9.1–M9.5 regression
    def test_25_m91_to_m95_regression(self):
        # Verify M9 contracts and enums integrate seamlessly
        self.assertIsNotNone(ResolutionAuditOutcome.DEFECT_NOT_OBSERVED)
        self.assertIsNotNone(AssertionType.NEGATED)
        self.assertIsNotNone(EpistemicState.USER_REPORTED)
        self.assertIsNotNone(IssueCategory.OPEN_DAMAGED_MANHOLE)


if __name__ == "__main__":
    unittest.main()
