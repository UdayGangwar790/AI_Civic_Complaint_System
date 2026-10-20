"""
CVKI - Module 9.7: End-to-End Pipeline Performance Benchmark

Measures local engineering baseline across 100 warmup-stabilized iterations for:
1. M9.4 Vernacular Normalization
2. M9.2 Cross-Modal Consistency Evaluation
3. M9.3 Active Clarification Resolution
4. M9.5 Visual Resolution Auditing
5. M9.6 Provenance Record Emission
6. M9.6 Knowledge Graph Synchronization
7. Complete End-to-End Pipeline (Citizen Input -> KG)
"""

from datetime import datetime, timezone
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas.multimodal import (
    CivicIssueContext,
    IssueCategory,
    MultimodalInput,
    VisualResolutionAuditRequest,
)
from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
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


def make_bench_cv_detection(class_name: str = "open_damaged_manhole") -> StandardDetectionResult:
    det = StandardDetection(
        class_id=0,
        class_name=class_name,
        confidence=0.91,
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


def run_e2e_benchmark(iterations: int = 100, warmup: int = 15):
    prov_repo = InMemoryProvenanceRepository()
    prov_engine = EvidenceProvenanceEngine(repository=prov_repo)
    set_provenance_engine(prov_engine)

    kg_repo = InMemoryKnowledgeGraphRepository()
    kg_service = CivicKnowledgeGraphService(repository=kg_repo)
    set_knowledge_graph_service(kg_service)

    integrator = MultimodalProvenanceKGIntegrator(prov_engine=prov_engine, kg_service=kg_service)
    set_multimodal_provenance_kg_integrator(integrator)

    case_ref = "CASE-BENCH-M97-E2E"
    text = "Road pe manhole khula hai emergency"
    cv_res = make_bench_cv_detection("open_damaged_manhole")

    # Warmup
    for _ in range(warmup):
        norm = multilingual_vernacular_normalizer.normalize(text)
        mm_in = MultimodalInput(request_id="warmup", text=norm.normalized_text, cv_result=cv_res)
        cons = cross_modal_consistency_engine.evaluate_consistency(mm_in)
        amb = cross_modal_consistency_engine.evaluate_ambiguity(mm_in, cons)
        active_clarification_resolver.resolve(mm_in, cons, amb)
        integrator.integrate_vernacular_normalization(case_ref, norm)

    # 1. Benchmark M9.4 Vernacular Normalization
    times_m94 = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        multilingual_vernacular_normalizer.normalize(text)
        t1 = time.perf_counter()
        times_m94.append((t1 - t0) * 1000)

    # 2. Benchmark M9.2 Consistency
    norm_res = multilingual_vernacular_normalizer.normalize(text)
    mm_input = MultimodalInput(
        request_id="bench_m92",
        text=norm_res.normalized_text,
        civic_issue_context=CivicIssueContext(reported_class="open_damaged_manhole"),
        cv_result=cv_res,
    )
    times_m92 = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        cross_modal_consistency_engine.evaluate_consistency(mm_input)
        t1 = time.perf_counter()
        times_m92.append((t1 - t0) * 1000)

    # 3. Benchmark M9.3 Clarification
    cons = cross_modal_consistency_engine.evaluate_consistency(mm_input)
    amb = cross_modal_consistency_engine.evaluate_ambiguity(mm_input, cons)
    times_m93 = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        active_clarification_resolver.resolve(mm_input, cons, amb)
        t1 = time.perf_counter()
        times_m93.append((t1 - t0) * 1000)

    # 4. Benchmark M9.5 Visual Audit
    audit_req = VisualResolutionAuditRequest(
        case_reference=case_ref,
        before_detection_result=cv_res,
        after_detection_result=make_bench_cv_detection("open_damaged_manhole"),
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    times_m95 = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        visual_resolution_auditor.audit(audit_req)
        t1 = time.perf_counter()
        times_m95.append((t1 - t0) * 1000)

    # 5. Benchmark M9.6 Provenance Record Emission
    times_m96_prov = []
    for i in range(iterations):
        t0 = time.perf_counter()
        integrator.record_vernacular_normalization_provenance(f"{case_ref}_{i}", norm_res)
        t1 = time.perf_counter()
        times_m96_prov.append((t1 - t0) * 1000)

    # 6. Benchmark M9.6 KG Synchronization
    times_m96_kg = []
    for i in range(iterations):
        t0 = time.perf_counter()
        kg_service.record_vernacular_normalization_graph(
            case_reference_id=case_ref,
            norm_id=f"norm_bench_{i}",
            original_text=text,
            normalized_text="open damaged manhole",
            detected_language="hi-Latn",
            script="latin",
            canonical_civic_concepts=["open_damaged_manhole"],
            confidence=0.94,
        )
        t1 = time.perf_counter()
        times_m96_kg.append((t1 - t0) * 1000)

    # 7. Benchmark Complete End-to-End Pipeline
    times_e2e = []
    for i in range(iterations):
        t0 = time.perf_counter()
        # Step 1: Citizen text -> Vernacular Normalizer (M9.4)
        norm = multilingual_vernacular_normalizer.normalize(text)
        # Step 2: Feed into MultimodalInput with CV detection (M8 -> M9.1)
        mm_in = MultimodalInput(
            request_id=f"req_e2e_{i}",
            text=norm.normalized_text,
            civic_issue_context=CivicIssueContext(reported_class="open_damaged_manhole"),
            cv_result=cv_res,
        )
        # Step 3: Evaluate Cross-Modal Consistency (M9.2)
        c_eval = cross_modal_consistency_engine.evaluate_consistency(mm_in)
        a_eval = cross_modal_consistency_engine.evaluate_ambiguity(mm_in, c_eval)
        # Step 4: Active Clarification Decision (M9.3)
        clar = active_clarification_resolver.resolve(mm_in, c_eval, a_eval)
        # Step 5: Provenance & KG Integration (M9.6)
        integrator.integrate_vernacular_normalization(case_ref, norm, norm_id=f"e2e_{i}")
        t1 = time.perf_counter()
        times_e2e.append((t1 - t0) * 1000)

    def print_metric(name: str, values: list[float]):
        print(f"\n--- {name} (N={len(values)}) ---")
        print(f"  Mean:   {statistics.mean(values):.4f} ms")
        print(f"  Median: {statistics.median(values):.4f} ms")
        print(f"  Min:    {min(values):.4f} ms")
        print(f"  Max:    {max(values):.4f} ms")

    print("\n==================================================")
    print("CVKI M9.7 — END-TO-END PIPELINE BENCHMARKS")
    print("==================================================")
    print_metric("M9.4 Vernacular Normalization", times_m94)
    print_metric("M9.2 Cross-Modal Consistency", times_m92)
    print_metric("M9.3 Active Clarification Resolution", times_m93)
    print_metric("M9.5 Visual Resolution Auditing", times_m95)
    print_metric("M9.6 Provenance Record Emission", times_m96_prov)
    print_metric("M9.6 Knowledge Graph Synchronization", times_m96_kg)
    print_metric("Complete End-to-End Pipeline (M9.4 -> M9.6)", times_e2e)
    print("\n==================================================")


if __name__ == "__main__":
    run_e2e_benchmark(iterations=100, warmup=15)
