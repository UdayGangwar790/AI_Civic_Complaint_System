import os
import sys

sys.path.insert(0, os.path.abspath("backend"))

import statistics
import time


from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.multimodal.contracts import (
    ClarificationAnswer,
    ClarificationAnswerType,
    ClarificationQuestion,
    ClarificationQuestionType,
    MultimodalInput,
)
from app.services.multimodal.clarification_resolver import (
    ActiveClarificationResolver,
)
from app.services.multimodal.consistency_engine import (
    cross_modal_consistency_engine,
)

def benchmark_m93():
    ITERATIONS = 100

    # 1. Resolver initialization benchmark
    init_latencies = []
    # Warmup
    for _ in range(10):
        _ = ActiveClarificationResolver()
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        _ = ActiveClarificationResolver()
        t1 = time.perf_counter()
        init_latencies.append((t1 - t0) * 1000.0)

    # 2. Clarification question generation benchmark
    resolver = ActiveClarificationResolver()
    cv_res = StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=1,
        detections=[
            StandardDetection(
                class_id=0,
                class_name="road_waterlogging",
                confidence=0.88,
                bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=200),
            )
        ],
    )
    m_input = MultimodalInput(
        request_id="bench-01",
        text="Open manhole on the road",
        cv_result=cv_res,
    )
    align = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambig = cross_modal_consistency_engine.evaluate_ambiguity(m_input, align)

    # Warmup
    for _ in range(10):
        _ = resolver.resolve(m_input, align, ambig)

    gen_latencies = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        _ = resolver.resolve(m_input, align, ambig)
        t1 = time.perf_counter()
        gen_latencies.append((t1 - t0) * 1000.0)

    # 3. Answer validation benchmark
    q = ClarificationQuestion(
        question_id="cq_bench_01",
        question_text="Which issue best describes the problem you want to report?",
        target_field="issue_type",
        options=["Open/damaged manhole", "Road waterlogging", "Both", "Something else"],
        reason="Benchmark validation",
        answer_type=ClarificationAnswerType.SINGLE_CHOICE,
    )
    ans = ClarificationAnswer(
        question_id="cq_bench_01",
        selected_option="Open/damaged manhole",
        answer_type=ClarificationAnswerType.SINGLE_CHOICE,
    )
    # Warmup
    for _ in range(10):
        _ = resolver.validate_answer(ans, q)

    val_latencies = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        _ = resolver.validate_answer(ans, q)
        t1 = time.perf_counter()
        val_latencies.append((t1 - t0) * 1000.0)

    # 4. Repeated resolution cycle with history answers benchmark
    history = [ans]
    # Warmup
    for _ in range(10):
        _ = resolver.resolve(m_input, align, ambig, history_answers=history)

    cycle_latencies = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        _ = resolver.resolve(m_input, align, ambig, history_answers=history)
        t1 = time.perf_counter()
        cycle_latencies.append((t1 - t0) * 1000.0)

    def print_stats(name, lats):
        print(f"=== {name} (sample count: {len(lats)}) ===")
        print(f"  Mean:   {statistics.mean(lats):.4f} ms")
        print(f"  Median: {statistics.median(lats):.4f} ms")
        print(f"  Min:    {min(lats):.4f} ms")
        print(f"  Max:    {max(lats):.4f} ms")

    print_stats("Resolver Initialization", init_latencies)
    print_stats("Clarification Generation", gen_latencies)
    print_stats("Answer Validation", val_latencies)
    print_stats("Repeated Clarification Resolution", cycle_latencies)

if __name__ == "__main__":
    benchmark_m93()
