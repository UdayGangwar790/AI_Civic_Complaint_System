"""
CVKI - Civic Vision & Knowledge Intelligence
Module 11.5: Production Readiness & Scalability Engineering Benchmark
Measures local engineering performance across 12 core subsystems + concurrent load stress.
"""

import os
from pathlib import Path
import sys

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math
import statistics
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.core.security import create_access_token
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
from app.services.action_playbook import get_action_playbook_registry
from app.services.complaint_case import InMemoryComplaintCaseRepository, set_case_repository
import app.services.complaint_case as complaint_case_module
from app.services.decision_projection import get_decision_projector
from app.services.decision_support import get_decision_support_engine
from app.services.field_inspection import (
    get_audit_engine,
    get_field_inspection_repository,
    get_protocol_generator,
)
from app.services.government_adapter import AdapterSubmissionResult, IntegrationState
from app.services.government_integration_service import government_integration_service
from app.services.knowledge_graph import get_knowledge_graph_service
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.multimodal_gateway import get_multimodal_gateway_service
from app.services.provenance_engine import get_provenance_engine


NUM_ITERATIONS = 100
CONCURRENCY_LEVELS = [10, 50, 100]


def calc_stats(latencies_ms: list[float], errors: int = 0) -> dict:
    if not latencies_ms:
        return {"n": 0, "mean": 0, "median": 0, "p95": 0, "p99": 0, "max": 0, "errors": errors}
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
    print("=" * 70)
    print("CVKI M11.5 PRODUCTION READINESS & SCALABILITY BENCHMARK")
    print(f"Iterations: {NUM_ITERATIONS} per tier | Concurrency: {CONCURRENCY_LEVELS}")
    print("NOTICE: Local engineering baseline only. Not production municipal scale.")
    print("=" * 70)

    client = TestClient(app)
    admin_user = AuthenticatedUser(user_id="admin_bench", email="admin@cvki.gov.in", role=UserRole.ADMIN.value)
    app.dependency_overrides[get_current_user] = lambda: admin_user

    # Setup repositories
    case_repo = InMemoryComplaintCaseRepository()
    set_case_repository(case_repo)
    prov_engine = get_provenance_engine()
    kg_service = get_knowledge_graph_service()
    gateway = get_multimodal_gateway_service()
    ds_engine = get_decision_support_engine()
    proto_gen = get_protocol_generator()
    audit_eng = get_audit_engine()
    projector = get_decision_projector()

    results = {}

    # 1. Health Endpoints
    lats = []
    errs = 0
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        resp = client.get("/api/health/live")
        dur = (time.perf_counter() - t0) * 1000
        if resp.status_code == 200:
            lats.append(dur)
        else:
            errs += 1
    results["1_health_liveness"] = calc_stats(lats, errs)

    # 2. Authentication Token Verification
    lats = []
    errs = 0
    token = create_access_token(user_id="usr_bench", email="bench@cvki.gov.in", role=UserRole.CITIZEN.value)
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        from app.core.security import decode_access_token
        try:
            payload = decode_access_token(token)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["2_auth_token_decode"] = calc_stats(lats, errs)

    # 3. Case Creation & Retrieval
    lats = []
    errs = 0
    for i in range(NUM_ITERATIONS):
        ref = f"BENCH-CASE-{i:04d}"
        case_obj = ComplaintCase(
            reference_id=ref,
            user_id="usr_bench",
            created_at=datetime.now(timezone.utc),
            status="in_progress",
            issue={
                "class_id": 0,
                "class_name": "open_damaged_manhole",
                "label": "Open Damaged Manhole",
                "severity": "high",
                "confidence": 0.88,
            },
            location={"latitude": 12.9716, "longitude": 77.5946, "road": "MG Road", "area": "Central"},
            priority_analysis={"priority_level": "P1", "priority_score": 85.0, "risk_level": "Critical"},
            authority={"authority_status": "verified", "maintenance_authority": {"name": "BBMP", "type": "Municipal"}},
            complaint={"title": "Open manhole", "description": "Dangerous open manhole on road", "language": "en"},
            follow_up={"guidance": "Standard municipal dispatch"},
        )
        t0 = time.perf_counter()
        case_repo.save(case_obj)
        retrieved = case_repo.get(ref)
        dur = (time.perf_counter() - t0) * 1000
        if retrieved:
            lats.append(dur)
        else:
            errs += 1
    results["3_case_store_and_retrieve"] = calc_stats(lats, errs)

    # 4. Multimodal Gateway
    lats = []
    errs = 0
    mm_req = MultimodalGatewayRequest(
        text="Raste par khula manhole hai kripya theek karein",
        language_hint="hi",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            res = gateway.process(mm_req)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["4_multimodal_gateway"] = calc_stats(lats, errs)

    # 5. Decision Support
    lats = []
    errs = 0
    ctx = DecisionContext(
        case_reference="BENCH-CASE-0001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        priority_level="P1",
        citizen_text="Emergency open manhole",
        latitude=12.9716,
        longitude=77.5946,
    )
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            res = ds_engine.evaluate_case(ctx)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["5_decision_support"] = calc_stats(lats, errs)

    # 6. Action Playbook Registry Lookup
    lats = []
    errs = 0
    playbook_reg = get_action_playbook_registry()
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            matches = playbook_reg.match_playbooks(
                issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
                has_cv_detection=True,
                priority_level="P1",
            )
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["6_playbook_match"] = calc_stats(lats, errs)

    # 7. Field Inspection Protocol Generation
    lats = []
    errs = 0
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            proto = proto_gen.generate_protocol(
                case_reference="BENCH-CASE-0001",
                issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
                case_location={"latitude": 12.9716, "longitude": 77.5946},
            )
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["7_field_protocol_generation"] = calc_stats(lats, errs)

    # 8. Field Inspection Audit
    lats = []
    errs = 0
    sub_req = FieldInspectionSubmissionRequest(
        protocol_id=proto.protocol_id,
        inspection_timestamp=datetime.now(timezone.utc),
        observations=[
            InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Cover missing.", defect_confirmed=True),
            InspectionObservationItem(step_id="STEP-MANHOLE-02", observation_text="Depth ~1.2m.", defect_confirmed=True),
            InspectionObservationItem(step_id="STEP-MANHOLE-03", observation_text="Cone barrier deployed.", defect_confirmed=True),
            InspectionObservationItem(step_id="STEP-MANHOLE-04", observation_text="High pedestrian volume near bus stop.", defect_confirmed=True),
        ],
        location={"latitude": 12.9716, "longitude": 77.5946},
    )
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            audit_res = audit_eng.audit_submission(protocol=proto, submission=sub_req, inspector_id="insp_bench")
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["8_field_inspection_audit"] = calc_stats(lats, errs)

    # 9. Provenance Event Recording
    lats = []
    errs = 0
    for i in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            ev = prov_engine.build_evidence_record(
                case_reference=f"BENCH-CASE-{i:04d}",
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
    results["9_provenance_recording"] = calc_stats(lats, errs)

    # 10. Knowledge Graph Projection
    lats = []
    errs = 0
    dec_res = ds_engine.evaluate_case(ctx)
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            projector.project_decision_recommendation("BENCH-CASE-0001", dec_res)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["10_kg_decision_projection"] = calc_stats(lats, errs)

    # 11. Knowledge Graph Retrieval
    lats = []
    errs = 0
    for _ in range(NUM_ITERATIONS):
        t0 = time.perf_counter()
        try:
            g = kg_service.get_case_graph("BENCH-CASE-0001", max_depth=3, max_nodes=50)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["11_kg_subgraph_retrieval"] = calc_stats(lats, errs)

    # 12. Full E2E Pipeline
    lats = []
    errs = 0
    for i in range(NUM_ITERATIONS):
        case_id = f"E2E-BENCH-{i:04d}"
        t0 = time.perf_counter()
        try:
            # Step A: Multimodal Gateway
            mm_out = gateway.process(mm_req)
            # Step B: Decision Support
            ds_out = ds_engine.evaluate_case(ctx)
            # Step C: Protocol & Audit
            p = proto_gen.generate_protocol(case_id, IssueCategory.OPEN_DAMAGED_MANHOLE)
            a = audit_eng.audit_submission(p, sub_req, "insp_bench")
            # Step D: KG Projection
            projector.project_decision_recommendation(case_id, ds_out)
            projector.project_field_inspection(a)
            dur = (time.perf_counter() - t0) * 1000
            lats.append(dur)
        except Exception:
            errs += 1
    results["12_complete_m10_e2e_pipeline"] = calc_stats(lats, errs)

    # 13. Concurrency Benchmarks (10, 50, 100 workers on Health + Decision Support)
    concurrency_results = {}
    for conc in CONCURRENCY_LEVELS:
        lat_conc = []
        err_conc = 0

        def worker_task(_):
            t_start = time.perf_counter()
            r = ds_engine.evaluate_case(ctx)
            return (time.perf_counter() - t_start) * 1000

        with ThreadPoolExecutor(max_workers=conc) as pool:
            futures = [pool.submit(worker_task, i) for i in range(conc)]
            for fut in futures:
                try:
                    lat_conc.append(fut.result())
                except Exception:
                    err_conc += 1
        concurrency_results[f"concurrency_{conc}_workers"] = calc_stats(lat_conc, err_conc)

    print("\n--- BENCHMARK RESULTS SUMMARY ---")
    for tier, s in results.items():
        print(f"[{tier}] N={s['n']} | Mean={s['mean_ms']}ms | Med={s['median_ms']}ms | P95={s['p95_ms']}ms | P99={s['p99_ms']}ms | Max={s['max_ms']}ms | Errs={s['errors']}")

    print("\n--- CONCURRENT STRESS BENCHMARK ---")
    for c_level, s in concurrency_results.items():
        print(f"[{c_level}] N={s['n']} | Mean={s['mean_ms']}ms | Med={s['median_ms']}ms | P95={s['p95_ms']}ms | P99={s['p99_ms']}ms | Max={s['max_ms']}ms | Errs={s['errors']}")

    return results, concurrency_results


if __name__ == "__main__":
    run_benchmark()
