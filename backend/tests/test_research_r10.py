"""R10 final evidence synthesis, integrity, and epistemic audit tests."""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
R10_ROOT = REPO_ROOT / "ai" / "research" / "experiments" / "R10"
R8_FREEZE_SHA256 = "ab165c7e5d62a001103c160869c1879c7a7725c6c8f22529c991783ab494a249"
R9_FREEZE_SHA256 = "730f0e08b66d34391b3c3d3816cad1f9447775296895eba3af931d2f8ede2fad"
M113_SHA256 = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
R3_SHA256 = "72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28"
D0_COUNT = 605
D0_TREE_SHA256 = "e609ad2e701b1e668d5d1f9474be6b1e2a8240bc61a4adbe1fee096db4ec2658"
R5_MANIFEST_SHA256 = "d36bd0f653c5650f628ad26d9397b5e843154931f23177918235b94b2f899f0e"
R5_METRICS_SHA256 = "a07f0ac9271b5af85689346632e181201fb453918408539505ed23059c39b13e"
R6_MANIFEST_SHA256 = "2c793e05dbc068d0ea1907e466a352a06b0728330fef580cd20485464408b348"
R6_METRICS_SHA256 = "907fc80c19372d344f67b7eb9990169fd47d1315c812b98cdf743513feca7831"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _d0_tree_hash(root: Path) -> str:
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        relative_path = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative_path + b"\0" + _sha256(path).encode("ascii") + b"\n")
    return digest.hexdigest()


def test_final_integrity_of_frozen_baselines_and_r5_r6():
    references = {
        "ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt": M113_SHA256,
        "ai/research/experiments/R3/CVR2-CV-006/weights/best.pt": R3_SHA256,
        "ai/research/datasets/R5_controlled_shift/manifest.json": R5_MANIFEST_SHA256,
        "ai/research/experiments/R5/metrics.json": R5_METRICS_SHA256,
        "ai/research/datasets/R6_controlled_sequences/manifest.json": R6_MANIFEST_SHA256,
        "ai/research/experiments/R6/metrics.json": R6_METRICS_SHA256,
    }
    for relative_path, expected_hash in references.items():
        assert _sha256(REPO_ROOT / relative_path) == expected_hash
    d0 = REPO_ROOT / "ai/computer_vision/dataset_m1_13"
    assert sum(path.is_file() for path in d0.rglob("*")) == D0_COUNT
    assert _d0_tree_hash(d0) == D0_TREE_SHA256


def test_r8_r9_are_frozen_and_zero_case_limitations_propagate():
    r8_freeze = REPO_ROOT / "ai/research/experiments/R8/freeze_manifest.json"
    r9_freeze = REPO_ROOT / "ai/research/experiments/R9/freeze_manifest.json"
    assert _sha256(r8_freeze) == R8_FREEZE_SHA256
    assert _sha256(r9_freeze) == R9_FREEZE_SHA256
    assert _load(REPO_ROOT / "ai/research/experiments/R8/dataset_manifest.json")["case_count"] == 0
    assert _load(REPO_ROOT / "ai/research/experiments/R9/case_results.json")["case_count"] == 0
    assert _load(R10_ROOT / "experiment.json")["overall_verdict"] == "INSUFFICIENT_EVIDENCE"


def test_evaluation_table_covers_every_required_research_stage():
    metrics = _load(R10_ROOT / "metrics.json")
    stages = [row["stage"] for row in metrics["research_stage_table"]]
    assert stages == ["R0", "R1", "R2", "R2.1", "R3", "R4", "R5", "R6", "R7", "R8", "R9"]
    required = {
        "research_question",
        "dataset",
        "sample_size",
        "model_checkpoint",
        "threshold",
        "metrics",
        "validation_status",
        "main_finding",
        "main_limitation",
    }
    assert all(required <= row.keys() for row in metrics["research_stage_table"])


def test_claim_audit_uses_allowed_evidence_classifications():
    audit = _load(R10_ROOT / "claim_audit.json")
    allowed = {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "DESCRIPTIVE_ONLY",
        "NOT_SUPPORTED",
        "NOT_EVALUATED",
    }
    assert len(audit["claims"]) >= 10
    assert all(
        claim["classification"] in allowed
        and claim["evidence"]
        and claim["limitation"]
        for claim in audit["claims"]
    )


def test_reproducibility_audit_reports_missing_and_inconsistent_records():
    audit = _load(R10_ROOT / "reproducibility_audit.json")
    assert audit["status"] == "PARTIALLY_VALIDATED"
    assert len(audit["prior_experiments"]["r2_experiment_ids"]) == 5
    assert len(audit["prior_experiments"]["r3_experiment_ids"]) == 5
    assert audit["prior_experiments"]["recorded_random_seed"] == 42
    assert any("PLANNED" in item and "COMPLETED" in item for item in audit["missing_or_inconsistent_elements"])
    assert any("D1 source" in item for item in audit["missing_or_inconsistent_elements"])
    assert audit["additional_manifests"]["d1_dataset_manifest_sha256"] == _sha256(
        REPO_ROOT / "ai/research/datasets/D1/manifests/dataset_manifest.json"
    )
    for snapshot in audit["prior_experiments"]["sha256_snapshots"]:
        group = "R2" if snapshot["experiment_id"] <= "CVR2-CV-005" else "R3"
        base = REPO_ROOT / "ai/research/experiments" / group / snapshot["experiment_id"]
        for filename, hash_key in (
            ("experiment.json", "experiment_json"),
            ("metrics.json", "metrics_json"),
            ("config.yaml", "config_yaml"),
            ("environment.json", "environment_json"),
        ):
            assert _sha256(base / filename) == snapshot[hash_key]
        assert snapshot["random_seed"] == 42
        assert _load(base / "experiment.json")["status"] == snapshot["recorded_status"]
        assert _load(base / "metrics.json")["status"] == snapshot["metrics_status"]


def test_leakage_audit_does_not_claim_source_independence():
    audit = _load(R10_ROOT / "leakage_audit.json")
    assert audit["overall_status"] == "INCONCLUSIVE"
    assert audit["checks"]["d1_to_d0_exact_image_overlap"]["status"] == "PASS_RECOMPUTED"
    assert audit["checks"]["d1_to_d0_near_image_overlap"]["status"] == "PASS_RECOMPUTED"
    assert audit["checks"]["d1_source_overlap_independence"]["status"] == "INCONCLUSIVE"
    assert audit["checks"]["synthetic_r5_source_overlap"]["status"] == "KNOWN_DERIVATIVE_NOT_LEAKAGE_CLAIM"
    assert audit["checks"]["synthetic_r6_sequence_overlap"]["status"] == "KNOWN_DERIVATIVE_NOT_LEAKAGE_CLAIM"


def test_epistemic_invariants_and_human_review_are_preserved():
    audit = _load(R10_ROOT / "epistemic_audit.json")
    assert len(audit["invariants"]) == 10
    assert all(item["status"] == "PRESERVED_BY_PROTOCOL" for item in audit["invariants"])
    assert audit["human_review_required"] is True
    assert audit["autonomous_government_decision"] is False
    assert audit["automatic_case_resolution_or_dispatch"] is False


def test_final_regression_counts_are_exact_and_reported():
    experiment = _load(R10_ROOT / "experiment.json")
    counts = experiment["regression_summary"]
    assert counts["status"] == "COMPLETED"
    assert all(isinstance(counts[key], int) and counts[key] >= 0 for key in ("passed", "failed", "errors", "warnings"))
    assert counts["passed"] + counts["failed"] > 0


def test_r10_final_record_hashes_and_no_production_changes():
    manifest = _load(R10_ROOT / "freeze_manifest.json")
    assert manifest["freeze_status"] == "FINAL_RESEARCH_RECORD"
    for relative_path, expected_hash in manifest["files"].items():
        assert _sha256(R10_ROOT / relative_path) == expected_hash
    for relative_path, expected_hash in manifest["external_files"].items():
        assert _sha256(REPO_ROOT / relative_path) == expected_hash
    assert manifest["frozen_inputs"] == {
        "r8_freeze_manifest_sha256": R8_FREEZE_SHA256,
        "r9_freeze_manifest_sha256": R9_FREEZE_SHA256,
    }
    experiment = _load(R10_ROOT / "experiment.json")
    assert experiment["research_only"] is True
    assert experiment["production_integration"] is False
    assert experiment["final_state"]["NO GIT COMMIT"] is True
    assert experiment["final_state"]["NO GIT PUSH"] is True
