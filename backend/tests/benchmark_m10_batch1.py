"""
CVKI - Civic Vision & Knowledge Intelligence
M10 Batch 1 Performance Benchmark
Measures latency (Mean, Median, P90, P95, P99, Max) over 100 CPU iterations for:
- M10.2 Multimodal Gateway Processing
- M10.3 Action Playbook Matching
- M10.4 Civic Decision Support Evaluation
- End-to-End Pipeline Evaluation
"""

import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import statistics
import time
from app.schemas.decision_support import DecisionContext
from app.schemas.multimodal_gateway import MultimodalGatewayRequest
from app.services.action_playbook import get_action_playbook_registry
from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.decision_support import get_decision_support_engine
from app.services.multimodal.contracts import IssueCategory
from app.services.multimodal_gateway import get_multimodal_gateway_service


def calculate_metrics(latencies_ms: list[float]) -> dict[str, float]:
    sorted_l = sorted(latencies_ms)
    n = len(sorted_l)
    return {
        "iterations": n,
        "mean_ms": round(statistics.mean(sorted_l), 3),
        "median_ms": round(statistics.median(sorted_l), 3),
        "p90_ms": round(sorted_l[int(n * 0.90)], 3),
        "p95_ms": round(sorted_l[int(n * 0.95)], 3),
        "p99_ms": round(sorted_l[min(int(n * 0.99), n - 1)], 3),
        "max_ms": round(max(sorted_l), 3),
        "min_ms": round(min(sorted_l), 3),
    }


def run_benchmarks(iterations: int = 100):
    gateway_service = get_multimodal_gateway_service()
    playbook_registry = get_action_playbook_registry()
    decision_engine = get_decision_support_engine()

    det = StandardDetectionResult(
        success=True,
        detections=[
            StandardDetection(
                class_id=0,
                class_name="open_damaged_manhole",
                confidence=0.88,
                bbox=StandardBoundingBox(x1=20, y1=20, x2=200, y2=200),
            )
        ],
        total_detections=1,
        model_id="m1_13",
        model_version="1.13.0",
        provider_id="yolov8_m1_13",
    )

    mm_request = MultimodalGatewayRequest(
        text="Sadak pe khula manhole bohot khatra hai",
        language_hint="hi",
        detection_result=det,
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )

    decision_ctx = DecisionContext(
        case_reference="CASE-BENCH-001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=det,
        citizen_text="Dangerous open manhole on 5th main road",
        alignment_score=0.85,
        priority_level="P2",
        is_recurrent=True,
        recurrence_count=3,
        weather_condition="light drizzle",
    )

    # 1. Benchmark M10.3 Action Playbook Matching
    pb_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        playbook_registry.match_playbooks(
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            has_cv_detection=True,
            priority_level="P2",
            is_recurrent=True,
            has_rain_context=True,
            alignment_score=0.85,
        )
        pb_latencies.append((time.perf_counter() - t0) * 1000.0)

    # 2. Benchmark M10.4 Decision Support Evaluation
    ds_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        decision_engine.evaluate_case(decision_ctx)
        ds_latencies.append((time.perf_counter() - t0) * 1000.0)

    # 3. Benchmark M10.2 Multimodal Gateway Processing
    gw_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        gateway_service.process(mm_request)
        gw_latencies.append((time.perf_counter() - t0) * 1000.0)

    # 4. Benchmark Combined Pipeline (Gateway + Decision Support)
    e2e_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        gw_res = gateway_service.process(mm_request)
        align_score = 0.8
        if gw_res.alignment_assessment and hasattr(gw_res.alignment_assessment, "consistency_score"):
            align_score = gw_res.alignment_assessment.consistency_score
        ctx = DecisionContext(
            case_reference="CASE-BENCH-E2E",
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            detection_result=det,
            citizen_text=gw_res.normalized_text,
            alignment_score=align_score,
            priority_level="P2",
        )
        decision_engine.evaluate_case(ctx)
        e2e_latencies.append((time.perf_counter() - t0) * 1000.0)

    results = {
        "m10_3_action_playbook_matching": calculate_metrics(pb_latencies),
        "m10_4_decision_support_evaluation": calculate_metrics(ds_latencies),
        "m10_2_multimodal_gateway": calculate_metrics(gw_latencies),
        "m10_combined_pipeline_e2e": calculate_metrics(e2e_latencies),
    }

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("CVKI M10 BATCH 1 PERFORMANCE BENCHMARK (100 Iterations, CPU)")
    print("=" * 60)
    res = run_benchmarks(100)
    for module, metrics in res.items():
        print(f"\n--- {module.upper()} ---")
        for k, v in metrics.items():
            print(f"  {k:15}: {v}")
    print("\n" + "=" * 60)
