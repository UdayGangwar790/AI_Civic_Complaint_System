"""
CVKI - Civic Vision & Knowledge Intelligence
M10 Full Performance Benchmarks: M10.2 to M10.7 & E2E Pipeline
LOCAL ENGINEERING BASELINE (>=100 iterations)
"""

import os
from pathlib import Path
import sys

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from datetime import datetime, timezone
import statistics
import time
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.complaint_case import ComplaintCase
from app.schemas.decision_support import (
    DecisionContext,
    DecisionEvidenceQuality,
    DecisionSupportResult,
)
from app.schemas.field_inspection import (
    AuditOutcome,
    FieldInspectionAuditResult,
    FieldInspectionRecord,
    FieldInspectionSubmissionRequest,
    GeofenceResult,
    InspectionCompleteness,
    InspectionObservationItem,
)
from app.schemas.multimodal_gateway import MultimodalGatewayRequest
from app.services.complaint_case import (
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
from app.services.cv.base_provider import StandardBoundingBox, StandardDetection, StandardDetectionResult
from app.services.decision_projection import get_decision_projector
from app.services.decision_support import get_decision_support_engine
from app.services.field_inspection import (
    get_audit_engine,
    get_field_inspection_repository,
    get_protocol_generator,
)
from app.services.knowledge_graph import (
    InMemoryKnowledgeGraphRepository,
    get_knowledge_graph_service,
)
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.multimodal_gateway import get_multimodal_gateway_service
from app.services.provenance_engine import (
    InMemoryProvenanceRepository,
    get_provenance_engine,
)


def compute_metrics(times_ms: list[float], name: str) -> dict:
    sorted_times = sorted(times_ms)
    n = len(sorted_times)
    p95_idx = int(n * 0.95)
    p99_idx = int(n * 0.99)
    return {
        "operation": name,
        "sample_count": n,
        "mean_ms": round(statistics.mean(sorted_times), 3),
        "median_ms": round(statistics.median(sorted_times), 3),
        "p95_ms": round(sorted_times[min(p95_idx, n - 1)], 3),
        "p99_ms": round(sorted_times[min(p99_idx, n - 1)], 3),
        "max_ms": round(max(sorted_times), 3),
    }


def run_full_benchmarks(iterations: int = 100):
    print("=" * 70)
    print("CVKI M10 COMPREHENSIVE PERFORMANCE BENCHMARKS")
    print("LOCAL ENGINEERING BASELINE (100 iterations)")
    print("=" * 70)

    # Isolated memory state
    orig_repo = complaint_case_module.case_repository
    case_repo = InMemoryComplaintCaseRepository()
    set_case_repository(case_repo)

    insp_repo = get_field_inspection_repository()
    insp_repo.clear()

    prov_engine = get_provenance_engine()
    prov_engine.repository.clear()

    kg = get_knowledge_graph_service()
    kg.repository.clear()

    # Create dummy base case
    case = ComplaintCase(
        reference_id="CASE-FULL-BENCH",
        user_id="user_cit_bench",
        status="in_progress",
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": "open_damaged_manhole",
            "label": "Open Damaged Manhole",
            "severity": "high",
            "confidence": 0.91,
            "bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9},
        },
        location={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "road": "MG Road",
            "area": "Central",
            "city": "Bengaluru",
        },
        authority={
            "authority_status": "verified",
            "maintenance_authority": {"name": "BBMP Road Maintenance", "type": "Municipal"},
        },
        complaint={"title": "Open manhole", "description": "Dangerous open manhole on road", "language": "en"},
        follow_up={"guidance": "Barricade area"},
        assignment={"assigned_to_user_id": "user_auth_bench"},
        metadata={"tenant_id": "bengaluru_bbmp"},
    )
    case_repo.save(case)

    # 1. Benchmark: M10.2 Multimodal Gateway
    gw_service = get_multimodal_gateway_service()
    gw_req = MultimodalGatewayRequest(
        case_reference="CASE-FULL-BENCH",
        text="Open damaged manhole cover on main carriage road",
        language_hint="en",
    )
    times_gw = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        gw_service.process(gw_req)
        times_gw.append((time.perf_counter() - t0) * 1000.0)

    # 2. Benchmark: M10.4 Decision Support Evaluation
    engine = get_decision_support_engine()
    det = StandardDetection(class_id=0, class_name="open_damaged_manhole", confidence=0.88, bbox=StandardBoundingBox(x1=0, y1=0, x2=1, y2=1))
    det_res = StandardDetectionResult(success=True, detections=[det], total_detections=1, model_id="m1_13", model_version="1.13.0", provider_id="yolov8_m1_13")
    ctx = DecisionContext(
        case_reference="CASE-FULL-BENCH",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        detection_result=det_res,
        citizen_text="Open damaged manhole cover on main carriage road",
        priority_level="P1",
    )
    times_ds = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        engine.evaluate_case(ctx)
        times_ds.append((time.perf_counter() - t0) * 1000.0)

    # 3. Benchmark: M10.5 Protocol Generation
    gen = get_protocol_generator()
    times_proto = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        gen.generate_protocol(
            case_reference="CASE-FULL-BENCH",
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            case_location={"latitude": 12.9716, "longitude": 77.5946},
        )
        times_proto.append((time.perf_counter() - t0) * 1000.0)

    # 4. Benchmark: M10.5 Field Inspection Audit
    proto = gen.generate_protocol(
        case_reference="CASE-FULL-BENCH",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        case_location={"latitude": 12.9716, "longitude": 77.5946},
    )
    audit_engine = get_audit_engine()
    sub = FieldInspectionSubmissionRequest(
        protocol_id=proto.protocol_id,
        protocol_version=proto.protocol_version,
        observations=[
            InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Cover missing", defect_confirmed=True),
            InspectionObservationItem(step_id="STEP-MANHOLE-02", observation_text="Rim broken", defect_confirmed=True),
        ],
        evidence_items=["photo1.jpg", "depth.jpg"],
        location={"latitude": 12.9716, "longitude": 77.5946},
        inspection_timestamp=datetime.now(timezone.utc),
    )
    times_audit = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        audit_engine.audit_submission(proto, sub, inspector_id="user_auth_bench")
        times_audit.append((time.perf_counter() - t0) * 1000.0)

    # 5. Benchmark: M10.6 Decision & Graph Projection
    projector = get_decision_projector()
    decision_sample = engine.evaluate_case(ctx)
    times_proj = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        projector.project_decision_recommendation("CASE-FULL-BENCH", decision_sample)
        times_proj.append((time.perf_counter() - t0) * 1000.0)

    # 6. Benchmark: M10.7 API Retrieval
    auth_user = AuthenticatedUser(
        user_id="user_auth_bench",
        email="bench@cvki.gov.in",
        role=UserRole.AUTHORITY.value,
    )
    app.dependency_overrides[get_current_user] = lambda: auth_user
    client = TestClient(app)

    times_api = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-FULL-BENCH")
        assert resp.status_code == 200
        times_api.append((time.perf_counter() - t0) * 1000.0)

    # 7. Benchmark: Complete M10 E2E Flow
    times_e2e = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        # Step A: Multimodal intake
        gw_service.process(gw_req)
        # Step B: Decision Support synthesis
        dec = engine.evaluate_case(ctx)
        # Step C: Protocol generation
        p = gen.generate_protocol("CASE-FULL-BENCH", IssueCategory.OPEN_DAMAGED_MANHOLE, {"latitude": 12.9716, "longitude": 77.5946})
        # Step D: Field inspection audit
        rec = audit_engine.audit_submission(p, sub, inspector_id="user_auth_bench")
        # Step E: Knowledge graph & provenance projection
        projector.project_decision_recommendation("CASE-FULL-BENCH", dec)
        projector.project_field_inspection(rec)
        times_e2e.append((time.perf_counter() - t0) * 1000.0)

    app.dependency_overrides.clear()
    set_case_repository(orig_repo)

    results = [
        compute_metrics(times_gw, "M10.2 Multimodal Gateway"),
        compute_metrics(times_ds, "M10.4 Decision Support"),
        compute_metrics(times_proto, "M10.5 Protocol Generation"),
        compute_metrics(times_audit, "M10.5 Field Inspection Audit"),
        compute_metrics(times_proj, "M10.6 Decision & Graph Projection"),
        compute_metrics(times_api, "M10.7 API Retrieval"),
        compute_metrics(times_e2e, "Complete M10 E2E Pipeline"),
    ]

    print("\nResults Summary (all metrics in milliseconds):")
    header = f"{'Operation':<35} | {'N':<5} | {'Mean':<8} | {'Median':<8} | {'P95':<8} | {'P99':<8} | {'Max':<8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['operation']:<35} | {r['sample_count']:<5} | {r['mean_ms']:<8} | {r['median_ms']:<8} | "
            f"{r['p95_ms']:<8} | {r['p99_ms']:<8} | {r['max_ms']:<8}"
        )
    return results


if __name__ == "__main__":
    run_full_benchmarks(100)
