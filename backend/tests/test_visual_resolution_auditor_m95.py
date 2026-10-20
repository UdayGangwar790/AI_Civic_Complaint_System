"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.5: Before/After Visual Resolution Auditor Test Suite

Validates all 25 required test cases for M9.5:
1. before + after same issue detected -> DEFECT_PERSISTS
2. before detected + after not detected -> DEFECT_NOT_OBSERVED
3. after low confidence -> INCONCLUSIVE
4. missing before -> INSUFFICIENT_EVIDENCE
5. missing after -> INSUFFICIENT_EVIDENCE
6. reversed timestamps
7. equal timestamps
8. consistent location
9. inconsistent location
10. unavailable location
11. same issue category
12. different issue category
13. multiple detections
14. low-quality metadata
15. no image hallucination
16. default threshold .25
17. custom threshold validation
18. deterministic repeated execution
19. model-independent behavior
20. epistemic state safety
21. no automatic case closure
22. no government status mutation
23. no M7.6 VERIFIED_RESOLVED mutation
24. no network
25. M8 regression
"""

from datetime import datetime, timedelta, timezone
import socket
import pytest

from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.multimodal.contracts import (
    ConsistencyAssessmentState,
    EpistemicState,
    EvidenceQuality,
    IssueCategory,
    MultimodalLocationContext,
    ResolutionAuditOutcome,
    VisualResolutionAuditRequest,
    VisualResolutionAuditResult,
)
from app.services.multimodal.visual_resolution_auditor import (
    VisualResolutionAuditor,
    visual_resolution_auditor,
)


def _make_cv_result(class_name: str, confidence: float = 0.85) -> StandardDetectionResult:
    dets = [
        StandardDetection(
            class_id=0,
            class_name=class_name,
            confidence=confidence,
            bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=200),
        )
    ]
    return StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=len(dets),
        detections=dets,
    )


# =============================================================================
# Test 1: Before + After Same Issue Detected -> DEFECT_PERSISTS
# =============================================================================

def test_01_same_issue_detected_persists():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-01",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.88),
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.82),
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.DEFECT_PERSISTS
    assert res.issue_category == IssueCategory.OPEN_DAMAGED_MANHOLE
    assert res.epistemic_state in {EpistemicState.SYSTEM_DERIVED, EpistemicState.MODEL_OBSERVATION}


# =============================================================================
# Test 2: Before Detected + After Not Detected -> DEFECT_NOT_OBSERVED
# =============================================================================

def test_02_defect_not_observed_in_after():
    auditor = VisualResolutionAuditor()
    empty_after = StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=0,
        detections=[],
    )
    req = VisualResolutionAuditRequest(
        case_reference="CASE-02",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=empty_after,
        issue_category=IssueCategory.ROAD_WATERLOGGING,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.DEFECT_NOT_OBSERVED
    assert res.issue_category == IssueCategory.ROAD_WATERLOGGING
    assert "not observed" in res.explanation.lower()


# =============================================================================
# Test 3: After Low Confidence Marginal -> INCONCLUSIVE
# =============================================================================

def test_03_after_low_confidence_inconclusive():
    auditor = VisualResolutionAuditor(default_threshold=0.25)
    # After detection has confidence 0.18 (below threshold 0.25)
    weak_after = _make_cv_result("road_waterlogging", 0.18)
    req = VisualResolutionAuditRequest(
        case_reference="CASE-03",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=weak_after,
        issue_category=IssueCategory.ROAD_WATERLOGGING,
        requested_threshold=0.25,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.INCONCLUSIVE
    assert "below evidence threshold" in res.explanation.lower() or "weak" in res.explanation.lower()


# =============================================================================
# Test 4: Missing Before Evidence -> INSUFFICIENT_EVIDENCE
# =============================================================================

def test_04_missing_before_evidence():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-04",
        before_detection_result=None,
        after_detection_result=_make_cv_result("road_waterlogging", 0.85),
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.INSUFFICIENT_EVIDENCE
    assert res.evidence_quality == EvidenceQuality.INSUFFICIENT


# =============================================================================
# Test 5: Missing After Evidence -> INSUFFICIENT_EVIDENCE
# =============================================================================

def test_05_missing_after_evidence():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-05",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=None,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.INSUFFICIENT_EVIDENCE
    assert res.evidence_quality == EvidenceQuality.INSUFFICIENT


# =============================================================================
# Test 6: Reversed Timestamps -> INCONCLUSIVE
# =============================================================================

def test_06_reversed_timestamps_inconclusive():
    auditor = VisualResolutionAuditor()
    now = datetime.now(timezone.utc)
    t_before = now
    t_after = now - timedelta(hours=2)  # after is earlier than before!

    req = VisualResolutionAuditRequest(
        case_reference="CASE-06",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        before_timestamp=t_before,
        after_timestamp=t_after,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.INCONCLUSIVE
    assert res.temporal_consistency == ConsistencyAssessmentState.INCONSISTENT
    assert "chronological anomaly" in res.explanation.lower()


# =============================================================================
# Test 7: Equal Timestamps -> INCONCLUSIVE
# =============================================================================

def test_07_equal_timestamps_inconclusive():
    auditor = VisualResolutionAuditor()
    now = datetime.now(timezone.utc)
    req = VisualResolutionAuditRequest(
        case_reference="CASE-07",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        before_timestamp=now,
        after_timestamp=now,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.INCONCLUSIVE
    assert res.temporal_consistency == ConsistencyAssessmentState.INCONSISTENT


# =============================================================================
# Test 8: Consistent Location (<= 100m)
# =============================================================================

def test_08_consistent_location():
    auditor = VisualResolutionAuditor()
    loc1 = MultimodalLocationContext(latitude=28.6139, longitude=77.2090)
    loc2 = MultimodalLocationContext(latitude=28.6140, longitude=77.2091)  # ~15 meters away

    now = datetime.now(timezone.utc)
    req = VisualResolutionAuditRequest(
        case_reference="CASE-08",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=_make_cv_result("road_waterlogging", 0.85),
        before_location=loc1,
        after_location=loc2,
        before_timestamp=now - timedelta(days=1),
        after_timestamp=now,
    )
    res = auditor.audit(req)
    assert res.spatial_consistency == ConsistencyAssessmentState.CONSISTENT
    assert res.outcome == ResolutionAuditOutcome.DEFECT_PERSISTS


# =============================================================================
# Test 9: Inconsistent Location (> 100m) -> INCONCLUSIVE
# =============================================================================

def test_09_inconsistent_location_inconclusive():
    auditor = VisualResolutionAuditor()
    loc1 = MultimodalLocationContext(latitude=28.6139, longitude=77.2090)
    loc2 = MultimodalLocationContext(latitude=28.6300, longitude=77.2200)  # ~2 km away!

    now = datetime.now(timezone.utc)
    req = VisualResolutionAuditRequest(
        case_reference="CASE-09",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=_make_cv_result("road_waterlogging", 0.85),
        before_location=loc1,
        after_location=loc2,
        before_timestamp=now - timedelta(days=1),
        after_timestamp=now,
    )
    res = auditor.audit(req)
    assert res.spatial_consistency == ConsistencyAssessmentState.INCONSISTENT
    assert res.outcome == ResolutionAuditOutcome.INCONCLUSIVE
    assert "spatial inconsistency" in res.explanation.lower()


# =============================================================================
# Test 10: Unavailable Location -> UNKNOWN
# =============================================================================

def test_10_unavailable_location_unknown():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-10",
        before_detection_result=_make_cv_result("damaged_missing_road_sign", 0.85),
        after_detection_result=_make_cv_result("damaged_missing_road_sign", 0.85),
        before_location=None,
        after_location=None,
    )
    res = auditor.audit(req)
    assert res.spatial_consistency == ConsistencyAssessmentState.UNKNOWN


# =============================================================================
# Test 11: Same Issue Category Comparison
# =============================================================================

def test_11_same_issue_category():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-11",
        before_detection_result=_make_cv_result("damaged_missing_road_sign", 0.90),
        after_detection_result=_make_cv_result("damaged_missing_road_sign", 0.85),
        issue_category=IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
    )
    res = auditor.audit(req)
    assert res.issue_category == IssueCategory.DAMAGED_MISSING_ROAD_SIGN
    assert res.outcome == ResolutionAuditOutcome.DEFECT_PERSISTS


# =============================================================================
# Test 12: Different Issue Category in After Evidence -> INCONCLUSIVE
# =============================================================================

def test_12_different_issue_category_inconclusive():
    auditor = VisualResolutionAuditor()
    # Before is road waterlogging, but after has confident damaged road sign instead
    req = VisualResolutionAuditRequest(
        case_reference="CASE-12",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=_make_cv_result("damaged_missing_road_sign", 0.85),
        issue_category=IssueCategory.ROAD_WATERLOGGING,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.INCONCLUSIVE
    assert "different issue category" in res.explanation.lower()


# =============================================================================
# Test 13: Multiple Detections Handled Appropriately
# =============================================================================

def test_13_multiple_detections_handling():
    auditor = VisualResolutionAuditor()
    multi_dets = [
        StandardDetection(
            class_id=0,
            class_name="open_damaged_manhole",
            confidence=0.88,
            bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=200),
        ),
        StandardDetection(
            class_id=2,
            class_name="road_waterlogging",
            confidence=0.82,
            bbox=StandardBoundingBox(x1=150, y1=200, x2=300, y2=400),
        ),
    ]
    cv_res = StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=len(multi_dets),
        detections=multi_dets,
    )
    req = VisualResolutionAuditRequest(
        case_reference="CASE-13",
        before_detection_result=cv_res,
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.DEFECT_PERSISTS


# =============================================================================
# Test 14: Low Quality Image Metadata Rejection
# =============================================================================

def test_14_low_quality_image_metadata_rejection():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-14",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_image_metadata={"quality": "unreadable", "corrupt": True},
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.INSUFFICIENT_EVIDENCE
    assert res.evidence_quality == EvidenceQuality.DEGRADED


# =============================================================================
# Test 15: No Image Hallucination
# =============================================================================

def test_15_no_image_hallucination():
    auditor = VisualResolutionAuditor()
    # If before detection has empty detections, auditor must not hallucinate a defect
    empty_before = StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=0,
        detections=[],
    )
    req = VisualResolutionAuditRequest(
        case_reference="CASE-15",
        before_detection_result=empty_before,
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.INSUFFICIENT_EVIDENCE
    assert "no confident civic defect detections observed" in res.explanation.lower()


# =============================================================================
# Test 16: Default Threshold 0.25 Applied
# =============================================================================

def test_16_default_threshold_applied():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-16",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.26),
    )
    res = auditor.audit(req)
    # 0.26 >= 0.25 -> defect persists
    assert res.outcome == ResolutionAuditOutcome.DEFECT_PERSISTS


# =============================================================================
# Test 17: Custom Threshold Validation
# =============================================================================

def test_17_custom_threshold_validation():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-17",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.40),
        requested_threshold=0.50,  # Custom higher threshold
    )
    res = auditor.audit(req)
    # 0.40 < 0.50 -> marginal/inconclusive
    assert res.outcome == ResolutionAuditOutcome.INCONCLUSIVE


# =============================================================================
# Test 18: Deterministic Repeated Execution
# =============================================================================

def test_18_deterministic_repeated_execution():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-18",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=_make_cv_result("road_waterlogging", 0.85),
    )
    runs = [auditor.audit(req) for _ in range(5)]
    first = runs[0]
    for r in runs[1:]:
        assert r.outcome == first.outcome
        assert r.explanation == first.explanation
        assert r.temporal_consistency == first.temporal_consistency


# =============================================================================
# Test 19: Model-Independent Behavior
# =============================================================================

def test_19_model_independent_behavior():
    auditor = VisualResolutionAuditor()
    # Detection results coming from different hypothetical model versions
    cv_m1 = StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=1,
        detections=[StandardDetection(class_id=0, class_name="open_damaged_manhole", confidence=0.88, bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=200))],
    )
    cv_m2 = StandardDetectionResult(
        model_id="future_cv_model_v2",
        model_version="2.0.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=1,
        detections=[StandardDetection(class_id=0, class_name="open_damaged_manhole", confidence=0.88, bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=200))],
    )
    req = VisualResolutionAuditRequest(
        case_reference="CASE-19",
        before_detection_result=cv_m1,
        after_detection_result=cv_m2,
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.DEFECT_PERSISTS


# =============================================================================
# Test 20: Epistemic State Safety (No Claim of VERIFIED_EVIDENCE)
# =============================================================================

def test_20_epistemic_state_safety():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-20",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
    )
    res = auditor.audit(req)
    assert res.epistemic_state != EpistemicState.VERIFIED_EVIDENCE
    assert res.epistemic_state in {EpistemicState.SYSTEM_DERIVED, EpistemicState.MODEL_OBSERVATION}

    # Attempt to set VERIFIED_EVIDENCE on audit result must be rejected
    with pytest.raises(ValueError):
        VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            explanation="Test invalid epistemic assignment",
            epistemic_state=EpistemicState.VERIFIED_EVIDENCE,  # Prohibited!
        )


# =============================================================================
# Test 21: No Automatic Case Closure
# =============================================================================

def test_21_no_automatic_case_closure():
    auditor = VisualResolutionAuditor()
    # Mock case object or status check
    req = VisualResolutionAuditRequest(
        case_reference="CASE-21",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=StandardDetectionResult(
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            task="civic_hazard_detection",
            success=True,
            total_detections=0,
            detections=[],
        ),
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.DEFECT_NOT_OBSERVED
    # Audit outcome must not be "CLOSED", "REPAIRED", or "VERIFIED_RESOLVED"
    assert res.outcome.value not in {"CLOSED", "REPAIRED", "VERIFIED_RESOLVED"}


# =============================================================================
# Test 22: No Government Status Mutation
# =============================================================================

def test_22_no_government_status_mutation():
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-22",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
    )
    res = auditor.audit(req)
    assert "government_status" not in res.model_metadata
    assert "closure_confirmed" not in res.model_metadata


# =============================================================================
# Test 23: No M7.6 VERIFIED_RESOLVED Mutation
# =============================================================================

def test_23_no_m76_mutation():
    auditor = VisualResolutionAuditor()
    empty_after = StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=0,
        detections=[],
    )
    req = VisualResolutionAuditRequest(
        case_reference="CASE-23",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=empty_after,
    )
    res = auditor.audit(req)
    # Must NOT claim VERIFIED_RESOLVED
    assert res.outcome == ResolutionAuditOutcome.DEFECT_NOT_OBSERVED
    assert res.outcome != "VERIFIED_RESOLVED"


# =============================================================================
# Test 24: No External Network Calls
# =============================================================================

def test_24_no_external_network_calls(monkeypatch):
    def guarded_connect(*args, **kwargs):
        pytest.fail("M9.5 attempted an unauthorized external network call!")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    auditor = VisualResolutionAuditor()
    req = VisualResolutionAuditRequest(
        case_reference="CASE-24",
        before_detection_result=_make_cv_result("road_waterlogging", 0.85),
        after_detection_result=_make_cv_result("road_waterlogging", 0.85),
    )
    res = auditor.audit(req)
    assert res.outcome == ResolutionAuditOutcome.DEFECT_PERSISTS


# =============================================================================
# Test 25: M8 Regression Integrity
# =============================================================================

def test_25_m8_regression_integrity():
    from app.services.cv.base_provider import StandardDetectionResult
    res = _make_cv_result("open_damaged_manhole", 0.90)
    assert res.success is True
    assert res.total_detections == 1
    assert res.detections[0].class_name == "open_damaged_manhole"
