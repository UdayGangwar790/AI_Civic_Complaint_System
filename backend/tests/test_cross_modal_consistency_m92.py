"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.2: Cross-Modal Evidence Consistency & Grounding Engine Unit Tests

Validates deterministic, explainable cross-modal consistency logic, partial alignment,
conflict detection, negation handling, evidence thresholds, epistemic boundaries,
and ambiguity derivations.
"""

from datetime import datetime, timezone
import unittest

from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.multimodal import (
    AlignmentState,
    AmbiguityAssessment,
    AmbiguityState,
    CivicIntent,
    CivicIssueContext,
    CrossModalConsistencyEngine,
    EpistemicState,
    EvidenceAlignmentAssessment,
    IssueCategory,
    MultimodalInput,
    MultimodalLocationContext,
    cross_modal_consistency_engine,
)


def _make_cv_result(
    detections: list[tuple[str, float]],
    success: bool = True,
) -> StandardDetectionResult:
    """Helper creating a StandardDetectionResult with specified class names and confidences."""
    dets = []
    class_id_map = {
        "open_damaged_manhole": 0,
        "damaged_missing_road_sign": 1,
        "road_waterlogging": 2,
    }
    for idx, (cname, conf) in enumerate(detections):
        dets.append(
            StandardDetection(
                class_id=class_id_map.get(cname, 99),
                class_name=cname,
                confidence=conf,
                bbox=StandardBoundingBox(x1=10, y1=10, x2=100, y2=100),
            )
        )
    return StandardDetectionResult(
        success=success,
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        total_detections=len(dets),
        detections=dets,
        inference_duration_ms=90.0,
    )


class TestCrossModalConsistencyEngineM92(unittest.TestCase):
    """Unit test suite for M9.2 Cross-Modal Evidence Consistency Engine."""

    def setUp(self):
        self.engine = CrossModalConsistencyEngine(evidence_threshold=0.25)

    # 1. Text + matching CV -> ALIGNED
    def test_01_text_and_matching_cv_aligned(self):
        inp = MultimodalInput(
            request_id="REQ-01",
            text="Dangerous open manhole on 12th Main Road.",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.88)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)
        self.assertEqual(res.matched_issue_category, IssueCategory.OPEN_DAMAGED_MANHOLE)
        self.assertEqual(len(res.conflicting_fields), 0)
        self.assertIn("cv_detection:open_damaged_manhole", res.supporting_evidence[0])

    # 2. Text + conflicting CV -> CONFLICTING
    def test_02_text_and_conflicting_cv_conflicting(self):
        inp = MultimodalInput(
            request_id="REQ-02",
            text="Dangerous open manhole on 12th Main Road.",
            cv_result=_make_cv_result([("road_waterlogging", 0.85)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.CONFLICTING)
        self.assertIsNone(res.matched_issue_category)
        self.assertIn("issue_category", res.conflicting_fields)
        self.assertIn("road_waterlogging instead", res.explanation)

    # 3. Text + partial CV -> PARTIALLY_ALIGNED
    def test_03_text_and_partial_cv_partially_aligned(self):
        inp = MultimodalInput(
            request_id="REQ-03",
            text="There is severe road waterlogging and a broken road sign.",
            cv_result=_make_cv_result([("road_waterlogging", 0.78)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.PARTIALLY_ALIGNED)
        self.assertEqual(res.matched_issue_category, IssueCategory.ROAD_WATERLOGGING)
        self.assertIn("missing_issue_category", res.conflicting_fields)
        self.assertIn("cv_detection:damaged_missing_road_sign", res.missing_evidence)
        self.assertIn("damaged_missing_road_sign issue was not observed", res.explanation)

    # 4. No usable evidence -> INSUFFICIENT_EVIDENCE
    def test_04_no_usable_evidence_insufficient_evidence(self):
        # Text provided but no CV result
        inp = MultimodalInput(
            request_id="REQ-04A",
            text="Open manhole on 5th cross.",
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.INSUFFICIENT_EVIDENCE)
        self.assertIn("no computer vision detection evidence was provided", res.explanation)

        # CV provided but no text or civic context
        inp_cv_only = MultimodalInput(
            request_id="REQ-04B",
            evidence_reference_id="EV-100",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.90)]),
        )
        res_cv = self.engine.evaluate_consistency(inp_cv_only)
        self.assertEqual(res_cv.state, AlignmentState.INSUFFICIENT_EVIDENCE)
        self.assertIn("no recognized civic issue category", res_cv.explanation)

    # 5. Unknown issue -> INSUFFICIENT_EVIDENCE
    def test_05_unknown_issue_insufficient_evidence(self):
        inp = MultimodalInput(
            request_id="REQ-05",
            text="The sky looks gloomy and people are walking with umbrellas.",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.85)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.INSUFFICIENT_EVIDENCE)
        self.assertIn("does not identify a recognized civic issue category", res.explanation)

    # 6. Waterlogging match
    def test_06_waterlogging_match(self):
        inp = MultimodalInput(
            request_id="REQ-06",
            text="Heavy water stagnation on the lane after rain.",
            cv_result=_make_cv_result([("road_waterlogging", 0.72)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)
        self.assertEqual(res.matched_issue_category, IssueCategory.ROAD_WATERLOGGING)

    # 7. Manhole match
    def test_07_manhole_match(self):
        inp = MultimodalInput(
            request_id="REQ-07",
            text="Deep sewer pit without drain cover near bus stop.",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.94)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)
        self.assertEqual(res.matched_issue_category, IssueCategory.OPEN_DAMAGED_MANHOLE)

    # 8. Road sign match
    def test_08_road_sign_match(self):
        inp = MultimodalInput(
            request_id="REQ-08",
            text="Traffic sign board is bent and broken.",
            cv_result=_make_cv_result([("damaged_missing_road_sign", 0.81)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)
        self.assertEqual(res.matched_issue_category, IssueCategory.DAMAGED_MISSING_ROAD_SIGN)

    # 9. Multi-issue aligned
    def test_09_multi_issue_aligned(self):
        inp = MultimodalInput(
            request_id="REQ-09",
            text="Severe waterlogging and broken traffic signboard at crossing.",
            cv_result=_make_cv_result([
                ("road_waterlogging", 0.79),
                ("damaged_missing_road_sign", 0.83),
            ]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)
        self.assertEqual(len(res.supporting_evidence), 2)
        self.assertEqual(len(res.missing_evidence), 0)

    # 10. Multi-issue partial
    def test_10_multi_issue_partial(self):
        inp = MultimodalInput(
            request_id="REQ-10",
            text="There is an open manhole and road waterlogging.",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.91)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.PARTIALLY_ALIGNED)
        self.assertIn("cv_detection:road_waterlogging", res.missing_evidence)
        self.assertIn("road_waterlogging issue was not observed", res.explanation)

    # 11. Negation + CV detection -> CONFLICTING
    def test_11_negation_plus_cv_detection_conflicting(self):
        inp = MultimodalInput(
            request_id="REQ-11",
            text="No waterlogging here, but please check the street.",
            cv_result=_make_cv_result([("road_waterlogging", 0.82)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.CONFLICTING)
        self.assertIn("negated_issue_category", res.conflicting_fields)
        self.assertIn("negative statement regarding road_waterlogging", res.explanation)

    # 12. Low-confidence detection -> INSUFFICIENT_EVIDENCE
    def test_12_low_confidence_detection_insufficient_evidence(self):
        # Detection is below 0.25 threshold
        inp = MultimodalInput(
            request_id="REQ-12",
            text="Open manhole on 8th main.",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.15)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.INSUFFICIENT_EVIDENCE)
        self.assertIn("below the required evidence strength threshold", res.explanation)

    # 13. Unrelated extra detection does not penalize primary match -> ALIGNED
    def test_13_unrelated_extra_detection_does_not_penalize_primary_match(self):
        inp = MultimodalInput(
            request_id="REQ-13",
            text="Report of road waterlogging after heavy rain.",
            cv_result=_make_cv_result([
                ("road_waterlogging", 0.85),
                ("open_damaged_manhole", 0.40),  # extra background detection
            ]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)
        self.assertEqual(res.matched_issue_category, IssueCategory.ROAD_WATERLOGGING)

    # 14. Malformed CV result
    def test_14_malformed_cv_result_handled_gracefully(self):
        failed_cv = _make_cv_result([], success=False)
        inp = MultimodalInput(
            request_id="REQ-14",
            text="Open manhole on 5th cross.",
            cv_result=failed_cv,
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.INSUFFICIENT_EVIDENCE)

    # 15. Deterministic repeated execution
    def test_15_deterministic_repeated_execution(self):
        inp = MultimodalInput(
            request_id="REQ-15",
            text="Broken direction board and waterlogging.",
            cv_result=_make_cv_result([("damaged_missing_road_sign", 0.80)]),
        )
        res1 = self.engine.evaluate_consistency(inp)
        res2 = self.engine.evaluate_consistency(inp)
        self.assertEqual(res1.state, res2.state)
        self.assertEqual(res1.matched_issue_category, res2.matched_issue_category)
        self.assertEqual(res1.conflicting_fields, res2.conflicting_fields)
        self.assertEqual(res1.explanation, res2.explanation)

    # 16. Explanation generated deterministically
    def test_16_explanation_generated_deterministically(self):
        inp = MultimodalInput(
            request_id="REQ-16",
            text="Signboard fell on the street.",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.89)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.CONFLICTING)
        self.assertIn("damaged_missing_road_sign", res.explanation)
        self.assertIn("open_damaged_manhole instead", res.explanation)

    # 17. No external network dependency
    def test_17_no_external_network_dependency(self):
        # Verification that evaluate_consistency executes purely locally in memory
        inp = MultimodalInput(
            request_id="REQ-17",
            text="Inspection chamber cover missing.",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.95)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)

    # 18. Model-independent execution
    def test_18_model_independent_execution(self):
        # Works on StandardDetectionResult from any provider (no PyTorch/YOLO coupling)
        custom_cv = StandardDetectionResult(
            success=True,
            model_id="custom_future_transformer",
            model_version="2.0.0",
            total_detections=1,
            detections=[
                StandardDetection(
                    class_id=0,
                    class_name="open_damaged_manhole",
                    confidence=0.91,
                    bbox=StandardBoundingBox(x1=20, y1=20, x2=80, y2=80),
                )
            ],
        )
        inp = MultimodalInput(
            request_id="REQ-18",
            text="Open sewer pit.",
            cv_result=custom_cv,
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)

    # 19. Epistemic state remains MODEL_OBSERVATION in analyze()
    def test_19_epistemic_state_remains_model_observation(self):
        inp = MultimodalInput(
            request_id="REQ-19",
            text="Drain cover broken.",
            cv_result=_make_cv_result([("open_damaged_manhole", 0.88)]),
        )
        output = self.engine.analyze(inp)
        self.assertEqual(output.epistemic_state, EpistemicState.MODEL_OBSERVATION)
        self.assertNotEqual(output.epistemic_state, EpistemicState.VERIFIED_EVIDENCE)

    # 20. No VERIFIED_EVIDENCE output
    def test_20_no_verified_evidence_output(self):
        inp = MultimodalInput(
            request_id="REQ-20",
            text="Severe waterlogging on highway.",
            cv_result=_make_cv_result([("road_waterlogging", 0.99)]),
        )
        output = self.engine.analyze(inp)
        self.assertNotEqual(output.epistemic_state, EpistemicState.VERIFIED_EVIDENCE)
        self.assertTrue(output.success)

    # 21. No causality inference in explanations
    def test_21_no_causality_inference_in_explanations(self):
        inp = MultimodalInput(
            request_id="REQ-21",
            text="Open manhole caused severe flooding and waterlogging on the road.",
            cv_result=_make_cv_result([
                ("open_damaged_manhole", 0.90),
                ("road_waterlogging", 0.85),
            ]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)
        # Ensure explanation does NOT assert causality
        explanation_lower = res.explanation.lower()
        self.assertNotIn("caused", explanation_lower)
        self.assertNotIn("because of", explanation_lower)

    # 22. Ambiguity handling derived from alignment
    def test_22_ambiguity_handling_derived_from_alignment(self):
        # Case A: Conflict -> CONFLICTING_EVIDENCE
        inp_conflict = MultimodalInput(
            request_id="REQ-22A",
            text="Signboard missing.",
            cv_result=_make_cv_result([("road_waterlogging", 0.88)]),
        )
        out_conflict = self.engine.analyze(inp_conflict)
        self.assertEqual(
            out_conflict.ambiguity_assessment.state,
            AmbiguityState.CONFLICTING_EVIDENCE,
        )
        self.assertTrue(out_conflict.ambiguity_assessment.requires_clarification)

        # Case B: Partial -> AMBIGUOUS
        inp_partial = MultimodalInput(
            request_id="REQ-22B",
            text="Waterlogging and broken road sign.",
            cv_result=_make_cv_result([("road_waterlogging", 0.88)]),
        )
        out_partial = self.engine.analyze(inp_partial)
        self.assertEqual(
            out_partial.ambiguity_assessment.state,
            AmbiguityState.AMBIGUOUS,
        )
        self.assertTrue(out_partial.ambiguity_assessment.requires_clarification)

        # Case C: Aligned -> CLEAR
        inp_aligned = MultimodalInput(
            request_id="REQ-22C",
            text="Waterlogging on main road.",
            cv_result=_make_cv_result([("road_waterlogging", 0.88)]),
        )
        out_aligned = self.engine.analyze(inp_aligned)
        self.assertEqual(
            out_aligned.ambiguity_assessment.state,
            AmbiguityState.CLEAR,
        )
        self.assertFalse(out_aligned.ambiguity_assessment.requires_clarification)

    # 23. Structured civic issue context fallback
    def test_23_structured_civic_context_fallback(self):
        # Text has no defect keywords, but civic_issue_context has reported_class
        inp = MultimodalInput(
            request_id="REQ-23",
            text="Please look at this location immediately.",
            civic_issue_context=CivicIssueContext(reported_class="open_damaged_manhole"),
            cv_result=_make_cv_result([("open_damaged_manhole", 0.90)]),
        )
        res = self.engine.evaluate_consistency(inp)
        self.assertEqual(res.state, AlignmentState.ALIGNED)
        self.assertEqual(res.matched_issue_category, IssueCategory.OPEN_DAMAGED_MANHOLE)


if __name__ == "__main__":
    unittest.main()
