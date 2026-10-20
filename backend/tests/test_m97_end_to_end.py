"""
CVKI - Module 9.7: End-to-End Multimodal System Validation Tests

Validates the complete CVKI M9 chain:
Citizen Input -> M3.6/M9.4 Vernacular Normalizer -> M8 CV Output ->
M9.2 Cross-Modal Consistency -> M9.3 Active Clarification ->
M9.5 Visual Resolution Audit -> M6.4 Provenance -> M6.5 Knowledge Graph

12 Mandatory Scenarios:
1. English straightforward complaint
2. Hinglish complaint
3. Hindi complaint
4. Negation handling (no unearned defect assertion)
5. Uncertainty handling (bounded USER_REPORTED)
6. Cross-modal CV conflict (neutral clarification, no accusations)
7. Partial cross-modal alignment (bounded clarification)
8. Before/after visual persistence (DEFECT_PERSISTS, no repair confirmation)
9. Before/after visual absence (DEFECT_NOT_OBSERVED, strictly not REPAIR_CONFIRMED)
10. After evidence conflict (INCONCLUSIVE)
11. Missing after evidence (INSUFFICIENT_EVIDENCE)
12. Invalidated evidence handling (invalidation propagates, no verified conclusion)
"""

from datetime import datetime, timedelta, timezone
import unittest

from app.schemas.authority import AuthorityParty, AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.schemas.knowledge_graph import (
    NodeType,
    RelationType,
    canonical_case_key,
)
from app.schemas.multimodal import (
    AlignmentState,
    AmbiguityState,
    AssertionType,
    CivicIssueContext,
    ClarificationStatus,
    ConsistencyAssessmentState,
    EpistemicState,
    EvidenceQuality,
    IssueCategory,
    MultimodalInput,
    ResolutionAuditOutcome,
    VernacularNormalizationResult,
    VisualResolutionAuditRequest,
    VisualResolutionAuditResult,
)
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
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
from app.services.multimodal.consistency_engine import cross_modal_consistency_engine
from app.services.multimodal.clarification_resolver import active_clarification_resolver
from app.services.multimodal.vernacular_normalizer import multilingual_vernacular_normalizer
from app.services.multimodal.visual_resolution_auditor import visual_resolution_auditor
from app.services.multimodal.provenance_kg_integrator import (
    MultimodalProvenanceKGIntegrator,
    set_multimodal_provenance_kg_integrator,
)


def create_e2e_case(case_ref: str = "CASE-2026-M97-001", user_id: str = "citizen_97") -> ComplaintCase:
    loc = ComplaintLocation(
        road="Hosur Road",
        area="Electronic City",
        city="Bengaluru",
        district="Bengaluru Urban",
        state="Karnataka",
        latitude=12.8452,
        longitude=77.6602,
        accuracy_m=8.0,
    )
    auth = AuthorityResult(
        authority_status="verified",
        authority_name="BBMP",
        responsible_department="Road Works Division",
        official_portal_url="https://bbmp.gov.in",
        maintenance_authority=AuthorityParty(
            name="BBMP",
            type="municipal_corporation",
            jurisdiction="Bengaluru",
            source="BBMP Portal",
        ),
    )
    issue = CaseIssue(
        class_name="open_damaged_manhole",
        confidence=0.93,
        severity="high",
        label="Open / Damaged Manhole",
    )
    complaint = CaseComplaint(
        title="Open manhole on Hosur Road",
        description="Hazardous open manhole near junction",
        category="Road Safety",
        language="en",
    )
    follow_up = FollowUp(history=[], resolved=False, guidance="Registered in CVKI.")
    return ComplaintCase(
        case_id="case_m97_e2e_001",
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


def make_standard_cv_detection(class_name: str, confidence: float = 0.90) -> StandardDetectionResult:
    det = StandardDetection(
        class_id=0,
        class_name=class_name,
        confidence=confidence,
        bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=150),
    )
    return StandardDetectionResult(
        success=True,
        model_id="m1.13-yolov8n",
        model_version="M1.13-yolov8n",
        model_hash="602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3",
        provider_id="m113_yolo_provider",
        total_detections=1,
        detections=[det],
        inference_duration_ms=18.5,
        metadata={"task_type": "object_detection"},
    )


class TestM97EndToEndSystemValidation(unittest.TestCase):
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

        self.case_ref = "CASE-2026-M97-001"
        self.case = create_e2e_case(self.case_ref)

    # -------------------------------------------------------------------------
    # Scenario 1: English Straightforward Complaint
    # -------------------------------------------------------------------------
    def test_scenario_01_english_straightforward_complaint(self):
        text = "Open manhole near the road junction."
        # M9.4: Normalization
        norm_res = multilingual_vernacular_normalizer.normalize(text)
        self.assertEqual(norm_res.assertion_type, AssertionType.ASSERTED)
        self.assertIn(IssueCategory.OPEN_DAMAGED_MANHOLE, norm_res.issue_candidates)
        self.assertEqual(norm_res.epistemic_state, EpistemicState.USER_REPORTED)

        # M8: Standard CV Detection
        cv_res = make_standard_cv_detection("open_damaged_manhole", confidence=0.92)

        # M9.2: Cross-Modal Consistency
        mm_input = MultimodalInput(
            request_id="req_s1",
            text=text,
            cv_result=cv_res,
        )
        consistency = cross_modal_consistency_engine.evaluate_consistency(mm_input)
        ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(mm_input, consistency)
        self.assertEqual(consistency.state, AlignmentState.ALIGNED)
        self.assertEqual(consistency.matched_issue_category, IssueCategory.OPEN_DAMAGED_MANHOLE)

        # M9.3: Active Clarification -> Clear, nothing to ask
        clarif = active_clarification_resolver.resolve(mm_input, consistency, ambiguity)
        self.assertEqual(clarif.status, ClarificationStatus.NOT_REQUIRED)
        self.assertEqual(len(clarif.questions), 0)

        # M9.6: Provenance & KG Integration
        ev_rec, kg_node = self.integrator.integrate_vernacular_normalization(self.case_ref, norm_res)
        self.assertEqual(ev_rec.verification_state, VerificationState.SYSTEM_DERIVED)
        self.assertEqual(kg_node.node_type, NodeType.VERNACULAR_NORMALIZATION)

    # -------------------------------------------------------------------------
    # Scenario 2: Hinglish Complaint
    # -------------------------------------------------------------------------
    def test_scenario_02_hinglish_complaint(self):
        text = "road pe paani jama hai bahut zyada"
        norm_res = multilingual_vernacular_normalizer.normalize(text)
        self.assertIn(norm_res.detected_language, ("hinglish", "hi-Latn"))
        self.assertIn(IssueCategory.ROAD_WATERLOGGING, norm_res.issue_candidates)
        self.assertEqual(norm_res.epistemic_state, EpistemicState.USER_REPORTED)

        cv_res = make_standard_cv_detection("road_waterlogging", confidence=0.88)
        # Feed normalized text and civic context from M9.4
        mm_input = MultimodalInput(
            request_id="req_s2",
            text=norm_res.normalized_text,
            civic_issue_context=CivicIssueContext(reported_class="road_waterlogging"),
            cv_result=cv_res,
        )
        consistency = cross_modal_consistency_engine.evaluate_consistency(mm_input)
        self.assertEqual(consistency.state, AlignmentState.ALIGNED)

    # -------------------------------------------------------------------------
    # Scenario 3: Hindi Devanagari Complaint
    # -------------------------------------------------------------------------
    def test_scenario_03_hindi_devanagari_complaint(self):
        text = "सड़क पर पानी भरा हुआ है"
        norm_res = multilingual_vernacular_normalizer.normalize(text)
        self.assertEqual(norm_res.detected_language, "hi")
        self.assertEqual(norm_res.script, "devanagari")
        self.assertIn(IssueCategory.ROAD_WATERLOGGING, norm_res.issue_candidates)
        self.assertEqual(norm_res.epistemic_state, EpistemicState.USER_REPORTED)

    # -------------------------------------------------------------------------
    # Scenario 4: Negation (Safety Guard)
    # -------------------------------------------------------------------------
    def test_scenario_04_negation_handling(self):
        text = "manhole khula nahi hai yahan"
        norm_res = multilingual_vernacular_normalizer.normalize(text)
        self.assertEqual(norm_res.assertion_type, AssertionType.NEGATED)
        self.assertEqual(len(norm_res.issue_candidates), 0)
        self.assertIn(IssueCategory.OPEN_DAMAGED_MANHOLE, norm_res.negated_candidates)

        # Provenance must be NOT_VERIFIED, never positive claim
        ev_rec = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm_res)
        self.assertEqual(ev_rec.verification_state, VerificationState.NOT_VERIFIED)

    # -------------------------------------------------------------------------
    # Scenario 5: Uncertainty
    # -------------------------------------------------------------------------
    def test_scenario_05_uncertainty_handling(self):
        text = "shayad road pe paani bhara hai"
        norm_res = multilingual_vernacular_normalizer.normalize(text)
        self.assertEqual(norm_res.assertion_type, AssertionType.UNCERTAIN)
        self.assertEqual(norm_res.epistemic_state, EpistemicState.USER_REPORTED)

        ev_rec = self.integrator.record_vernacular_normalization_provenance(self.case_ref, norm_res)
        self.assertEqual(ev_rec.verification_state, VerificationState.NOT_VERIFIED)

    # -------------------------------------------------------------------------
    # Scenario 6: Cross-Modal Conflict
    # -------------------------------------------------------------------------
    def test_scenario_06_cv_conflict(self):
        text = "Deep open manhole on the street"
        # CV observes waterlogging, not open manhole
        cv_res = make_standard_cv_detection("road_waterlogging", confidence=0.91)
        mm_input = MultimodalInput(request_id="req_s6", text=text, cv_result=cv_res)

        consistency = cross_modal_consistency_engine.evaluate_consistency(mm_input)
        ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(mm_input, consistency)
        self.assertEqual(consistency.state, AlignmentState.CONFLICTING)

        clarif = active_clarification_resolver.resolve(mm_input, consistency, ambiguity)
        self.assertIn(clarif.status, (ClarificationStatus.QUESTION_PRESENTED, ClarificationStatus.CLARIFICATION_REQUIRED))
        self.assertTrue(len(clarif.questions) > 0)
        # Neutral question: must NOT accuse citizen of fraud or lying
        q_text = clarif.questions[0].question_text.lower()
        self.assertNotIn("fraud", q_text)
        self.assertNotIn("lying", q_text)
        self.assertNotIn("false", q_text)

    # -------------------------------------------------------------------------
    # Scenario 7: Partial Cross-Modal Alignment
    # -------------------------------------------------------------------------
    def test_scenario_07_partial_alignment(self):
        text = "There is a damaged road sign and waterlogging here"
        # CV observes only the damaged road sign
        cv_res = make_standard_cv_detection("damaged_missing_road_sign", confidence=0.89)
        mm_input = MultimodalInput(request_id="req_s7", text=text, cv_result=cv_res)

        consistency = cross_modal_consistency_engine.evaluate_consistency(mm_input)
        ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(mm_input, consistency)
        self.assertEqual(consistency.state, AlignmentState.PARTIALLY_ALIGNED)

        clarif = active_clarification_resolver.resolve(mm_input, consistency, ambiguity)
        self.assertIn(clarif.status, (ClarificationStatus.QUESTION_PRESENTED, ClarificationStatus.CLARIFICATION_REQUIRED, ClarificationStatus.NOT_REQUIRED))

    # -------------------------------------------------------------------------
    # Scenario 8: Before/After Visual Resolution Audit: Defect Persists
    # -------------------------------------------------------------------------
    def test_scenario_08_before_after_persistence(self):
        t_before = datetime.now(timezone.utc) - timedelta(days=2)
        t_after = datetime.now(timezone.utc)
        before_cv = make_standard_cv_detection("open_damaged_manhole", confidence=0.92)
        after_cv = make_standard_cv_detection("open_damaged_manhole", confidence=0.87)

        req = VisualResolutionAuditRequest(
            case_reference=self.case_ref,
            before_detection_result=before_cv,
            after_detection_result=after_cv,
            before_timestamp=t_before,
            after_timestamp=t_after,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        )
        audit_res = visual_resolution_auditor.audit(req)
        self.assertEqual(audit_res.outcome, ResolutionAuditOutcome.DEFECT_PERSISTS)
        self.assertIn(audit_res.epistemic_state, (EpistemicState.SYSTEM_DERIVED, EpistemicState.MODEL_OBSERVATION))

        ev_rec, kg_node = self.integrator.integrate_visual_audit(self.case_ref, audit_res)
        self.assertEqual(ev_rec.verification_state, VerificationState.SYSTEM_DERIVED)
        self.assertFalse(ev_rec.metadata["is_repair_confirmed"])

    # -------------------------------------------------------------------------
    # Scenario 9: Before/After Visual Resolution Audit: Defect Not Observed
    # -------------------------------------------------------------------------
    def test_scenario_09_before_after_not_observed(self):
        t_before = datetime.now(timezone.utc) - timedelta(days=3)
        t_after = datetime.now(timezone.utc)
        before_cv = make_standard_cv_detection("road_waterlogging", confidence=0.90)
        # Empty after detections
        after_cv = StandardDetectionResult(
            success=True,
            model_id="m1.13-yolov8n",
            model_version="M1.13-yolov8n",
            model_hash="602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3",
            provider_id="m113_yolo_provider",
            total_detections=0,
            detections=[],
        )

        req = VisualResolutionAuditRequest(
            case_reference=self.case_ref,
            before_detection_result=before_cv,
            after_detection_result=after_cv,
            before_timestamp=t_before,
            after_timestamp=t_after,
            issue_category=IssueCategory.ROAD_WATERLOGGING,
        )
        audit_res = visual_resolution_auditor.audit(req)
        self.assertEqual(audit_res.outcome, ResolutionAuditOutcome.DEFECT_NOT_OBSERVED)
        # CRITICAL Epistemic Guard: Never promoted to REPAIR_CONFIRMED
        self.assertNotEqual(audit_res.epistemic_state, EpistemicState.VERIFIED_EVIDENCE)

        ev_rec, kg_node = self.integrator.integrate_visual_audit(self.case_ref, audit_res)
        self.assertFalse(ev_rec.metadata["is_repair_confirmed"])
        self.assertEqual(ev_rec.verification_state, VerificationState.SYSTEM_DERIVED)

    # -------------------------------------------------------------------------
    # Scenario 10: After Evidence Conflict
    # -------------------------------------------------------------------------
    def test_scenario_10_after_evidence_conflict(self):
        t_before = datetime.now(timezone.utc) - timedelta(days=1)
        t_after = datetime.now(timezone.utc)
        before_cv = make_standard_cv_detection("road_waterlogging", confidence=0.91)
        # After image shows damaged sign instead of audited category
        after_cv = make_standard_cv_detection("damaged_missing_road_sign", confidence=0.88)

        req = VisualResolutionAuditRequest(
            case_reference=self.case_ref,
            before_detection_result=before_cv,
            after_detection_result=after_cv,
            before_timestamp=t_before,
            after_timestamp=t_after,
            issue_category=IssueCategory.ROAD_WATERLOGGING,
        )
        audit_res = visual_resolution_auditor.audit(req)
        self.assertEqual(audit_res.outcome, ResolutionAuditOutcome.INCONCLUSIVE)

    # -------------------------------------------------------------------------
    # Scenario 11: Missing After Evidence
    # -------------------------------------------------------------------------
    def test_scenario_11_missing_after_evidence(self):
        t_before = datetime.now(timezone.utc) - timedelta(days=1)
        before_cv = make_standard_cv_detection("open_damaged_manhole", confidence=0.90)

        req = VisualResolutionAuditRequest(
            case_reference=self.case_ref,
            before_detection_result=before_cv,
            after_detection_result=None,
            before_timestamp=t_before,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        )
        audit_res = visual_resolution_auditor.audit(req)
        self.assertEqual(audit_res.outcome, ResolutionAuditOutcome.INSUFFICIENT_EVIDENCE)

    # -------------------------------------------------------------------------
    # Scenario 12: Invalidated Evidence
    # -------------------------------------------------------------------------
    def test_scenario_12_invalidated_evidence(self):
        text = "manhole khula hai"
        norm_res = multilingual_vernacular_normalizer.normalize(text)
        ev_rec, kg_node = self.integrator.integrate_vernacular_normalization(
            self.case_ref, norm_res, norm_id="s12_norm"
        )
        self.assertEqual(ev_rec.status, "active")

        # Invalidate
        invalidated = self.integrator.invalidate_m9_evidence(
            ev_rec.evidence_id, reason="Citizen withdrew complaint"
        )
        self.assertEqual(invalidated.status, "invalidated")
        self.assertEqual(invalidated.verification_state, VerificationState.NOT_VERIFIED)

        # Knowledge graph explanation check
        edge_key = f"edge:{canonical_case_key(self.case_ref)}:HAS_VERNACULAR_NORMALIZATION:{kg_node.canonical_key}"
        expl = self.kg_service.explain_relationship(edge_key)
        self.assertEqual(expl.verification_state, VerificationState.NOT_VERIFIED)

    # -------------------------------------------------------------------------
    # Epistemic Safety Audit
    # -------------------------------------------------------------------------
    def test_epistemic_safety_audit(self):
        # 1. Vernacular normalization != verification
        norm = multilingual_vernacular_normalizer.normalize("pothole on road")
        self.assertNotEqual(norm.epistemic_state, EpistemicState.VERIFIED_EVIDENCE)
        self.assertEqual(norm.epistemic_state, EpistemicState.USER_REPORTED)

        # 2. Consistency alignment != verification
        cv = make_standard_cv_detection("road_waterlogging")
        mm = MultimodalInput(request_id="ep_test", text="water on road", cv_result=cv)
        cons = cross_modal_consistency_engine.evaluate_consistency(mm)
        amb = cross_modal_consistency_engine.evaluate_ambiguity(mm, cons)
        self.assertNotEqual(cons.state.value, "verified")

        # 3. Clarification != verification
        clarif = active_clarification_resolver.resolve(mm, cons, amb)
        self.assertNotEqual(clarif.epistemic_state, EpistemicState.VERIFIED_EVIDENCE)

        # 4. Visual audit != repair confirmation
        audit = visual_resolution_auditor.audit(
            VisualResolutionAuditRequest(case_reference=self.case_ref, before_detection_result=cv, after_detection_result=None)
        )
        self.assertNotEqual(audit.epistemic_state, EpistemicState.VERIFIED_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
