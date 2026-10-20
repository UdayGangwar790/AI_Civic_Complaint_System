"""
CVKI - Final Milestone M12.6 Performance & Reliability Benchmark
Comprehensive evaluation of core subsystems + concurrency stress baselines.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.security import create_access_token, decode_access_token
from app.main import app
from app.models.roles import UserRole
from app.schemas.complaint_case import ComplaintCase
from app.schemas.decision_support import DecisionContext
from app.schemas.field_inspection import (
    FieldInspectionSubmissionRequest,
    InspectionObservationItem,
)
from app.schemas.multimodal_gateway import MultimodalGatewayRequest
from app.schemas.provenance import ClaimType, SourceType, VerificationState
from app.services.authority import resolve_authority
from app.services.complaint_case import InMemoryComplaintCaseRepository, set_case_repository
from app.services.cv.base_provider import InferenceRequest
from app.services.cv.providers.m113_yolo_provider import M113YOLOProvider
from app.services.decision_projection import get_decision_projector
from app.services.decision_support import get_decision_support_engine
from app.services.field_inspection import get_audit_engine, get_protocol_generator
from app.services.knowledge_graph import get_knowledge_graph_service
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.multimodal_gateway import get_multimodal_gateway_service
from app.services.provenance_engine import get_provenance_engine

NUM_ITERATIONS = 100
CONCURRENCY_WORKERS = [10, 50, 100]


def calc_stats(latencies_ms: list[float], errors: int = 0) -> dict:
    if not latencies_ms:
        return {"n": 0, "mean_ms": 0, "median_ms": 0, "p95_ms": 0, "p99_ms": 0, "max_ms": 0, "errors": errors}
    s = sorted(latencies_ms)
    n = len(s)
    mean_val = statistics.mean(s)
    median_val = statistics.median(s)
    p95_idx = min(int(n * 0.95), n - 1)
    p99_idx = min(int(n * 0.99), n - 1)
    return {
        "n": n,
        "mean_ms": round(mean_val, 3),
        "median_ms": round(median_val, 3),
        "p95_ms": round(s[p95_idx], 3),
        "p99_ms": round(s[p99_idx], 3),
        "max_ms": round(s[-1], 3),
        "errors": errors,
    }


def run_benchmark():
    print("=" * 80)
    print("CVKI M12.6 FINAL PERFORMANCE & RELIABILITY BENCHMARK")
    print(f"Iterations: {NUM_ITERATIONS} per tier | Concurrency stress: {CONCURRENCY_WORKERS}")
    print("NOTICE: Local engineering baseline only. Not municipal-scale capacity or real-time guarantees.")
    print("=" * 80)

    client = TestClient(app)
    admin_user = AuthenticatedUser(user_id="bench_admin", email="admin@cvki.gov.in", role=UserRole.ADMIN.value)
    app.dependency_overrides[get_current_user] = lambda: admin_user

    case_repo = InMemoryComplaintCaseRepository()
    set_case_repository(case_repo)

    # Services
    gateway = get_multimodal_gateway_service()
    ds_engine = get_decision_support_engine()
    proto_gen = get_protocol_generator()
    audit_engine = get_audit_engine()
    projector = get_decision_projector()
    prov_engine = get_provenance_engine()
    kg_service = get_knowledge_graph_service()

    # Initialize CV provider
    cv_provider = M113YOLOProvider()
    cv_provider.initialize()
    dummy_img = Image.new("RGB", (640, 640), color=(128, 128, 128))

    results = {}

    # Tier 1: Health Liveness
    print("Running Tier 1: Health Liveness...")
    lats, errs = [], 0
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        resp = client.get("/api/health/live")
        dur = (time.perf_counter() - t0) * 1000
        if resp.status_code == 200:
            lats.append(dur)
        else:
            errs += 1
    results["1_health"] = calc_stats(lats, errs)

    # Tier 2: Authentication Token Decode
    print("Running Tier 2: Authentication Token Decode...")
    lats, errs = [], 0
    sample_token = create_access_token(user_id="bench_user", email="bench@cvki.gov.in", role=UserRole.CITIZEN.value)
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            decode_access_token(sample_token)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["2_authentication"] = calc_stats(lats, errs)

    # Tier 3: CV Inference (M1.13 Standardized Interface)
    print("Running Tier 3: CV Inference (M1.13)...")
    lats, errs = [], 0
    cv_req = InferenceRequest(image=dummy_img, confidence_threshold=0.25)
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            cv_res = cv_provider.infer(cv_req)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["3_cv_inference"] = calc_stats(lats, errs)

    # Tier 4: Multimodal Gateway
    print("Running Tier 4: Multimodal Gateway...")
    lats, errs = [], 0
    mm_req = MultimodalGatewayRequest(
        text="Sadak par open manhole hai aur pani beh raha hai",
        language_hint="hi",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            gateway.process(mm_req)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["4_multimodal_gateway"] = calc_stats(lats, errs)

    # Tier 5: Authority Resolution
    print("Running Tier 5: Authority Resolution...")
    lats, errs = [], 0
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            resolve_authority(
                latitude=12.9716,
                longitude=77.5946,
                context={"road_name": "MG Road", "city": "Bengaluru"},
                live=False,
            )
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["5_authority_resolution"] = calc_stats(lats, errs)

    # Tier 6: Decision Support
    print("Running Tier 6: Decision Support...")
    lats, errs = [], 0
    ds_ctx = DecisionContext(
        case_reference="M12-BENCH-001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        priority_level="P1",
        citizen_text="Hazardous open manhole",
        latitude=12.9716,
        longitude=77.5946,
    )
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            ds_engine.evaluate_case(ds_ctx)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["6_decision_support"] = calc_stats(lats, errs)

    # Tier 7: Field Inspection Protocol & Audit
    print("Running Tier 7: Field Inspection...")
    lats, errs = [], 0
    proto = proto_gen.generate_protocol("M12-BENCH-001", IssueCategory.OPEN_DAMAGED_MANHOLE, {"latitude": 12.9716, "longitude": 77.5946})
    obs = [
        InspectionObservationItem(
            step_id=s.step_id,
            observation_text="Verified baricade and defect boundaries.",
            defect_confirmed=True,
        )
        for s in proto.inspection_steps
    ]
    sub = FieldInspectionSubmissionRequest(
        protocol_id=proto.protocol_id,
        observations=obs,
        location={"latitude": 12.9716, "longitude": 77.5946},
        inspection_timestamp=datetime.now(timezone.utc),
    )
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            audit_engine.audit_submission(proto, sub, "bench_inspector")
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["7_field_inspection"] = calc_stats(lats, errs)

    # Tier 8: Provenance Recording
    print("Running Tier 8: Provenance...")
    lats, errs = [], 0
    for i in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            ev = prov_engine.build_evidence_record(
                case_reference=f"M12-BENCH-{i:04d}",
                claim_type=ClaimType.DETECTION,
                source="M1.13 CV",
                source_type=SourceType.CV_MODEL,
                explanation="Defect detected",
                verification_state=VerificationState.NOT_VERIFIED,
                claim_value={"class_name": "open_damaged_manhole", "confidence": 0.88},
            )
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["8_provenance"] = calc_stats(lats, errs)

    # Tier 9: Knowledge Graph Query & Projection
    print("Running Tier 9: Knowledge Graph...")
    lats, errs = [], 0
    # Seed a graph node
    dec_seed = ds_engine.evaluate_case(ds_ctx)
    projector.project_decision_recommendation("M12-BENCH-001", dec_seed)
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            kg_service.get_case_graph("M12-BENCH-001", max_depth=3, max_nodes=50)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["9_knowledge_graph"] = calc_stats(lats, errs)

    # Tier 10: Complete End-to-End Workflow
    print("Running Tier 10: Complete E2E Workflow...")
    lats, errs = [], 0
    for i in range(NUM_ITERATIONS):
        ref = f"E2E-M12-{i:04d}"
        t0 = time.perf_counter()
        try:
            # 1. Store case
            case_obj = ComplaintCase(
                reference_id=ref,
                user_id="bench_user",
                created_at=datetime.now(timezone.utc),
                status="in_progress",
                issue={"class_id": 0, "class_name": "open_damaged_manhole", "label": "Open Damaged Manhole", "severity": "high", "confidence": 0.88},
                location={"latitude": 12.9716, "longitude": 77.5946, "road": "MG Road"},
                priority_analysis={"priority_level": "P1", "priority_score": 85.0, "risk_level": "Critical"},
                authority={"authority_status": "verified", "maintenance_authority": {"name": "BBMP"}},
                complaint={"title": "Open manhole", "description": "Severe manhole defect", "language": "en"},
                follow_up={"guidance": "Standard municipal dispatch"},
            )
            case_repo.save(case_obj)
            # 2. Multimodal gateway
            gateway.process(mm_req)
            # 3. Decision support
            ds_res = ds_engine.evaluate_case(DecisionContext(case_reference=ref, issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE, priority_level="P1"))
            # 4. Field protocol & audit
            p = proto_gen.generate_protocol(ref, IssueCategory.OPEN_DAMAGED_MANHOLE, {"latitude": 12.9716, "longitude": 77.5946})
            sub_i = FieldInspectionSubmissionRequest(
                protocol_id=p.protocol_id,
                observations=obs,
                location={"latitude": 12.9716, "longitude": 77.5946},
                inspection_timestamp=datetime.now(timezone.utc),
            )
            rec = audit_engine.audit_submission(p, sub_i, "bench_inspector")
            # 5. Projection
            projector.project_decision_recommendation(ref, ds_res)
            projector.project_field_inspection(rec)
            # 6. KG retrieval
            kg_service.get_case_graph(ref, max_depth=3, max_nodes=50)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception as e:
            errs += 1
    results["10_complete_e2e"] = calc_stats(lats, errs)

    # Concurrency Stress Testing
    print("\nRunning Concurrency Stress Testing...")
    concurrency_results = {}
    for workers in CONCURRENCY_WORKERS:
        total_requests = workers * 5  # 5 requests per worker
        print(f"  Stress testing with {workers} workers ({total_requests} requests)...")
        c_lats, c_errs = [], 0

        def worker_task(idx):
            t_start = time.perf_counter()
            resp = client.get("/api/health/live")
            t_dur = (time.perf_counter() - t_start) * 1000
            return t_dur, resp.status_code == 200

        with ThreadPoolExecutor(max_workers=workers) as executor:
            task_results = list(executor.map(worker_task, range(total_requests)))

        for dur, ok in task_results:
            if ok:
                c_lats.append(dur)
            else:
                c_errs += 1
        concurrency_results[f"{workers}_workers"] = calc_stats(c_lats, c_errs)

    cv_provider.shutdown()

    # Summary Output
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS (M12 FINAL)")
    print("=" * 80)
    print(f"{'Tier / Subsystem':<28} | {'N':>4} | {'Mean (ms)':>10} | {'Median':>8} | {'P95 (ms)':>9} | {'P99 (ms)':>9} | {'Max (ms)':>9} | {'Errors':>6}")
    print("-" * 95)
    for name, s in results.items():
        print(f"{name:<28} | {s['n']:>4} | {s['mean_ms']:>10.3f} | {s['median_ms']:>8.3f} | {s['p95_ms']:>9.3f} | {s['p99_ms']:>9.3f} | {s['max_ms']:>9.3f} | {s['errors']:>6}")

    print("\n" + "-" * 80)
    print("CONCURRENCY BENCHMARK RESULTS")
    print("-" * 80)
    for name, s in concurrency_results.items():
        print(f"{name:<28} | {s['n']:>4} | {s['mean_ms']:>10.3f} | {s['median_ms']:>8.3f} | {s['p95_ms']:>9.3f} | {s['p99_ms']:>9.3f} | {s['max_ms']:>9.3f} | {s['errors']:>6}")
    print("=" * 80)

    # Save benchmark results as JSON artifact for documentation
    output_path = Path(backend_dir) / "tests" / "benchmark_m12_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"subsystems": results, "concurrency": concurrency_results}, f, indent=2)
    print(f"Results written to: {output_path}")


if __name__ == "__main__":
    run_benchmark()
