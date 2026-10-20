"""
CVKI - Module 9.6: Provenance & Knowledge Graph Integration Benchmark

Measures local engineering baselines for:
1. M9.4 Provenance Record Creation
2. M9.5 Provenance Record Creation
3. M9.6 Knowledge Graph Insertion
4. M9.6 Subgraph Retrieval
5. M9.6 Case Graph Rebuild
6. M9.6 Relationship Explanation

Using 100 warmup-stabilized iterations.
"""

from datetime import datetime, timezone
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas.authority import AuthorityParty, AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.schemas.multimodal import (
    AssertionType,
    ConsistencyAssessmentState,
    EpistemicState,
    EvidenceQuality,
    IssueCategory,
    ResolutionAuditOutcome,
    VernacularNormalizationResult,
    VisualResolutionAuditResult,
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
from app.services.multimodal.provenance_kg_integrator import (
    MultimodalProvenanceKGIntegrator,
    set_multimodal_provenance_kg_integrator,
)


def create_benchmark_case(case_ref: str = "CASE-BENCH-M96") -> ComplaintCase:
    loc = ComplaintLocation(
        road="MG Road",
        city="Bengaluru",
        state="Karnataka",
        latitude=12.9716,
        longitude=77.5946,
        accuracy_m=10.0,
    )
    auth = AuthorityResult(
        authority_status="verified",
        authority_name="BBMP",
        responsible_department="Roads",
        official_portal_url="https://bbmp.gov.in",
        maintenance_authority=AuthorityParty(
            name="BBMP",
            type="municipal_corporation",
            jurisdiction="Bengaluru",
            source="BBMP Registry",
        ),
    )
    issue = CaseIssue(
        class_name="open_damaged_manhole",
        confidence=0.91,
        severity="high",
        label="Open / Damaged Manhole",
    )
    complaint = CaseComplaint(
        title="Open manhole",
        description="Hazardous open manhole",
        category="Road Safety",
        language="en",
    )
    follow_up = FollowUp(history=[], resolved=False, guidance="Registered in CVKI.")
    return ComplaintCase(
        case_id="case_bench_m96",
        reference_id=case_ref,
        user_id="bench_user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        status="submitted_to_cvki",
        location=loc,
        issue=issue,
        complaint=complaint,
        authority=auth,
        follow_up=follow_up,
    )


def run_benchmark(iterations: int = 100, warmup: int = 15):
    prov_repo = InMemoryProvenanceRepository()
    prov_engine = EvidenceProvenanceEngine(repository=prov_repo)
    set_provenance_engine(prov_engine)

    kg_repo = InMemoryKnowledgeGraphRepository()
    kg_service = CivicKnowledgeGraphService(repository=kg_repo)
    set_knowledge_graph_service(kg_service)

    integrator = MultimodalProvenanceKGIntegrator(prov_engine=prov_engine, kg_service=kg_service)
    set_multimodal_provenance_kg_integrator(integrator)

    case = create_benchmark_case()
    case_ref = case.reference_id

    norm_res = VernacularNormalizationResult(
        original_text="manhole khula hai",
        normalized_text="open damaged manhole",
        detected_language="hi-Latn",
        issue_candidates=[IssueCategory.OPEN_DAMAGED_MANHOLE],
        confidence=0.94,
    )

    audit_res = VisualResolutionAuditResult(
        outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        evidence_quality=EvidenceQuality.SUFFICIENT,
        temporal_consistency=ConsistencyAssessmentState.CONSISTENT,
        spatial_consistency=ConsistencyAssessmentState.CONSISTENT,
        explanation="Defect is not observed.",
        epistemic_state=EpistemicState.MODEL_OBSERVATION,
    )

    # Warmup
    for _ in range(warmup):
        integrator.record_vernacular_normalization_provenance(case_ref, norm_res)
        integrator.record_visual_audit_provenance(case_ref, audit_res)
        kg_service.build_case_graph(case)
        kg_service.get_case_graph(case_ref)
        kg_service.rebuild_case_graph(case_ref, case=case)

    # 1. Benchmark M9.4 Provenance Creation
    times_norm_prov = []
    for i in range(iterations):
        res_i = VernacularNormalizationResult(
            original_text=f"manhole khula hai variant {i}",
            normalized_text="open damaged manhole",
            detected_language="hi-Latn",
            issue_candidates=[IssueCategory.OPEN_DAMAGED_MANHOLE],
            confidence=0.94,
        )
        t0 = time.perf_counter()
        integrator.record_vernacular_normalization_provenance(case_ref, res_i)
        t1 = time.perf_counter()
        times_norm_prov.append((t1 - t0) * 1000)

    # 2. Benchmark M9.5 Provenance Creation
    times_audit_prov = []
    for i in range(iterations):
        audit_i = VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            evidence_quality=EvidenceQuality.SUFFICIENT,
            explanation=f"Audit comparison sample {i}",
            epistemic_state=EpistemicState.MODEL_OBSERVATION,
        )
        t0 = time.perf_counter()
        integrator.record_visual_audit_provenance(case_ref, audit_i)
        t1 = time.perf_counter()
        times_audit_prov.append((t1 - t0) * 1000)

    # 3. Benchmark Graph Insertion
    times_graph_insert = []
    for i in range(iterations):
        t0 = time.perf_counter()
        integrator.integrate_vernacular_normalization(case_ref, norm_res, norm_id=f"norm_bench_{i}")
        t1 = time.perf_counter()
        times_graph_insert.append((t1 - t0) * 1000)

    # 4. Benchmark Subgraph Retrieval
    times_graph_retrieval = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        kg_service.get_case_graph(case_ref, max_depth=2)
        t1 = time.perf_counter()
        times_graph_retrieval.append((t1 - t0) * 1000)

    # 5. Benchmark Graph Rebuild
    times_graph_rebuild = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        kg_service.rebuild_case_graph(case_ref, case=case)
        t1 = time.perf_counter()
        times_graph_rebuild.append((t1 - t0) * 1000)

    # 6. Benchmark Relationship Explanation
    ev_rec, kg_node = integrator.integrate_vernacular_normalization(case_ref, norm_res, norm_id="expl_bench")
    edge_key = f"edge:case:{case_ref}:HAS_VERNACULAR_NORMALIZATION:{kg_node.canonical_key}"
    times_explanation = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        kg_service.explain_relationship(edge_key)
        t1 = time.perf_counter()
        times_explanation.append((t1 - t0) * 1000)

    def print_metric(name: str, values: list[float]):
        print(f"\n--- {name} (N={len(values)}) ---")
        print(f"  Mean:   {statistics.mean(values):.4f} ms")
        print(f"  Median: {statistics.median(values):.4f} ms")
        print(f"  Min:    {min(values):.4f} ms")
        print(f"  Max:    {max(values):.4f} ms")

    print("\n==================================================")
    print("CVKI M9.6 — LOCAL ENGINEERING BENCHMARKS")
    print("==================================================")
    print_metric("M9.4 Provenance Record Creation", times_norm_prov)
    print_metric("M9.5 Provenance Record Creation", times_audit_prov)
    print_metric("M9.6 Graph Insertion (Vernacular Norm)", times_graph_insert)
    print_metric("M9.6 Subgraph Retrieval (depth=2)", times_graph_retrieval)
    print_metric("M9.6 Graph Rebuild", times_graph_rebuild)
    print_metric("M9.6 Relationship Explanation", times_explanation)
    print("\n==================================================")


if __name__ == "__main__":
    run_benchmark(iterations=100, warmup=15)
