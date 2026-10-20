"""
CVKI - M9.5 Performance Benchmark Script
Benchmarks VisualResolutionAuditor operations across 100 warmup-stabilized iterations.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("backend"))

from datetime import datetime, timedelta, timezone
import statistics
import time

from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.multimodal.contracts import (
    IssueCategory,
    MultimodalLocationContext,
    VisualResolutionAuditRequest,
)
from app.services.multimodal.visual_resolution_auditor import (
    VisualResolutionAuditor,
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


def benchmark_m95():
    ITERATIONS = 100
    auditor = VisualResolutionAuditor()

    now = datetime.now(timezone.utc)
    req = VisualResolutionAuditRequest(
        case_reference="BENCH-M95-01",
        before_detection_result=_make_cv_result("road_waterlogging", 0.88),
        after_detection_result=_make_cv_result("road_waterlogging", 0.82),
        before_timestamp=now - timedelta(days=2),
        after_timestamp=now,
        before_location=MultimodalLocationContext(latitude=28.6139, longitude=77.2090),
        after_location=MultimodalLocationContext(latitude=28.6140, longitude=77.2091),
        issue_category=IssueCategory.ROAD_WATERLOGGING,
    )

    # Warmup
    for _ in range(10):
        _ = auditor.audit(req)

    # 1. Audit comparison latency
    audit_latencies = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        _ = auditor.audit(req)
        t1 = time.perf_counter()
        audit_latencies.append((t1 - t0) * 1000.0)

    # 2. Repeated comparisons across multiple outcomes (persists, not observed, inconclusive)
    req_not_obs = VisualResolutionAuditRequest(
        case_reference="BENCH-M95-02",
        before_detection_result=_make_cv_result("open_damaged_manhole", 0.85),
        after_detection_result=StandardDetectionResult(
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            task="civic_hazard_detection",
            success=True,
            total_detections=0,
            detections=[],
        ),
        before_timestamp=now - timedelta(days=1),
        after_timestamp=now,
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )

    req_inconclusive = VisualResolutionAuditRequest(
        case_reference="BENCH-M95-03",
        before_detection_result=_make_cv_result("damaged_missing_road_sign", 0.85),
        after_detection_result=_make_cv_result("damaged_missing_road_sign", 0.15),
        requested_threshold=0.25,
        before_timestamp=now - timedelta(days=1),
        after_timestamp=now,
        issue_category=IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
    )

    mixed_reqs = [req, req_not_obs, req_inconclusive]
    repeated_latencies = []
    for _ in range(ITERATIONS):
        r = mixed_reqs[_ % len(mixed_reqs)]
        t0 = time.perf_counter()
        _ = auditor.audit(r)
        t1 = time.perf_counter()
        repeated_latencies.append((t1 - t0) * 1000.0)

    def print_stats(name, lats):
        print(f"=== {name} (sample count: {len(lats)}) ===")
        print(f"  Mean:   {statistics.mean(lats):.4f} ms")
        print(f"  Median: {statistics.median(lats):.4f} ms")
        print(f"  Min:    {min(lats):.4f} ms")
        print(f"  Max:    {max(lats):.4f} ms")

    print_stats("M9.5 Visual Resolution Audit", audit_latencies)
    print_stats("M9.5 Repeated Varied Audit Comparison", repeated_latencies)


if __name__ == "__main__":
    benchmark_m95()
