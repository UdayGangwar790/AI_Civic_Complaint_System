"""
CVKI - Civic Vision & Knowledge Intelligence
M10 Batch 2 Performance Benchmarks: M10.5, M10.6, M10.7
LOCAL ENGINEERING BASELINE
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
from app.services.complaint_case import (
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
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


def run_benchmarks(iterations: int = 100):
    print("=" * 60)
    print("CVKI M10 BATCH 2 PERFORMANCE BENCHMARKS")
    print("LOCAL ENGINEERING BASELINE (>=100 iterations)")
    print("=" * 60)

    # Setup isolated memory state
    orig_repo = complaint_case_module.case_repository
    case_repo = InMemoryComplaintCaseRepository()
    set_case_repository(case_repo)

    insp_repo = get_field_inspection_repository()
    insp_repo.clear()

    prov_engine = get_provenance_engine()
    prov_engine.repository.clear()

    kg = get_knowledge_graph_service()
    kg.repository.clear()

    # 1. Benchmark: M10.5 Protocol Generation
    gen = get_protocol_generator()
    times_proto = []
    for i in range(iterations):
        t0 = time.perf_counter()
        proto = gen.generate_protocol(
            case_reference=f"BENCH-CASE-{i}",
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            case_location={"latitude": 12.9716, "longitude": 77.5946},
        )
        t1 = time.perf_counter()
        times_proto.append((t1 - t0) * 1000.0)

    # 2. Benchmark: M10.5 Audit Engine
    audit_engine = get_audit_engine()
    proto = gen.generate_protocol(
        case_reference="BENCH-CASE-0",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        case_location={"latitude": 12.9716, "longitude": 77.5946},
    )
    submission = FieldInspectionSubmissionRequest(
        protocol_id=proto.protocol_id,
        protocol_version=proto.protocol_version,
        observations=[
            InspectionObservationItem(
                step_id=proto.inspection_steps[0].step_id,
                observation_text="Manhole opening observed with missing lid.",
                defect_confirmed=True,
            )
        ],
        evidence_items=["photo1.jpg", "photo2.jpg"],
        location={"latitude": 12.9716, "longitude": 77.5946},
        inspection_timestamp=datetime.now(timezone.utc),
    )
    times_audit = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        audit_res = audit_engine.audit_submission(proto, submission, inspector_id="bench_inspector")
        t1 = time.perf_counter()
        times_audit.append((t1 - t0) * 1000.0)

    # 3. Benchmark: M10.6 Projection (Decision & Inspection into Provenance and KG)
    projector = get_decision_projector()
    decision = DecisionSupportResult(
        recommendation_id="DEC-BENCH-001",
        case_reference="CASE-BENCH-PROJ",
        matched_playbooks=["PB-MANHOLE-SAFETY-V1 (v1.0.0)"],
        recommended_actions=[],
        mitigation_actions=[],
        required_inspection=["Check opening"],
        required_evidence=["Photos"],
        supporting_evidence=[],
        missing_evidence=[],
        explanation="Benchmark decision projection",
        uncertainty=[],
        evidence_quality=DecisionEvidenceQuality.STRONG,
        epistemic_state=EpistemicState.SYSTEM_DERIVED,
        human_review_required=True,
    )
    times_proj = []
    for i in range(iterations):
        t0 = time.perf_counter()
        projector.project_decision_recommendation(f"CASE-BENCH-PROJ-{i}", decision)
        t1 = time.perf_counter()
        times_proj.append((t1 - t0) * 1000.0)

    # 4. Benchmark: M10.7 API Retrieval
    case = ComplaintCase(
        reference_id="CASE-API-BENCH",
        user_id="user_cit_1",
        status="under_review",
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": "open_damaged_manhole",
            "label": "Open Manhole",
            "severity": "high",
            "confidence": 0.88,
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
        complaint={"title": "Hazardous road issue", "description": "Large dangerous opening", "language": "en"},
        follow_up={"guidance": "Saved in CVKI."},
        assignment={"assigned_to_user_id": "auth_bench_1"},
    )
    case_repo.save(case)

    auth_user = AuthenticatedUser(
        user_id="auth_bench_1",
        email="auth_bench_1@cvki.gov.in",
        role=UserRole.AUTHORITY.value,
        scopes=["cases:read"],
    )
    app.dependency_overrides[get_current_user] = lambda: auth_user
    client = TestClient(app)
    times_api = []
    try:
        for _ in range(iterations):
            t0 = time.perf_counter()
            resp = client.get(f"{settings.API_V1_STR}/decision-support/cases/CASE-API-BENCH")
            t1 = time.perf_counter()
            assert resp.status_code == 200
            times_api.append((t1 - t0) * 1000.0)
    finally:
        app.dependency_overrides.clear()
        set_case_repository(orig_repo)

    results = [
        compute_metrics(times_proto, "M10.5 Protocol Generation"),
        compute_metrics(times_audit, "M10.5 Field Inspection Audit"),
        compute_metrics(times_proj, "M10.6 Decision & Graph Projection"),
        compute_metrics(times_api, "M10.7 API Retrieval"),
    ]

    print("\nResults Summary (all metrics in milliseconds):")
    print(f"{'Operation':<35} | {'N':<5} | {'Mean':<8} | {'Median':<8} | {'P95':<8} | {'P99':<8} | {'Max':<8}")
    print("-" * 90)
    for r in results:
        print(f"{r['operation']:<35} | {r['sample_count']:<5} | {r['mean_ms']:<8} | {r['median_ms']:<8} | {r['p95_ms']:<8} | {r['p99_ms']:<8} | {r['max_ms']:<8}")

    return results


if __name__ == "__main__":
    run_benchmarks(100)
