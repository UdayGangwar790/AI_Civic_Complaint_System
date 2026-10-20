"""R9 protocol-only evaluation and frozen-input acceptance tests."""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
R9_ROOT = REPO_ROOT / "ai" / "research" / "experiments" / "R9"
R8_ROOT = REPO_ROOT / "ai" / "research" / "experiments" / "R8"

R8_FREEZE_SHA256 = "ab165c7e5d62a001103c160869c1879c7a7725c6c8f22529c991783ab494a249"
R8_DATASET_SHA256 = "c63d427251ee12cf8d284c3f29a5fa6ad0f3c051b713186582b467ee2f45b2f6"
M113_SHA256 = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
R3_SHA256 = "72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28"
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


def test_r8_dataset_integrity_and_freeze():
    r8_experiment = _load(R8_ROOT / "experiment.json")
    r8_dataset = _load(R8_ROOT / "dataset_manifest.json")
    r8_freeze = R8_ROOT / "freeze_manifest.json"
    assert _sha256(r8_freeze) == R8_FREEZE_SHA256
    assert _sha256(R8_ROOT / "dataset_manifest.json") == R8_DATASET_SHA256
    assert r8_experiment["status"] == "CASE_DATASET_NOT_AVAILABLE"
    assert r8_dataset["case_count"] == 0
    assert r8_dataset["records"] == []
    for relative_path, expected_hash in _load(r8_freeze)["files"].items():
        assert _sha256(R8_ROOT / relative_path) == expected_hash


def test_frozen_m113_r3_r5_r6_integrity():
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


def test_r9_marks_empirical_evaluation_unavailable_without_fabrication():
    experiment = _load(R9_ROOT / "experiment.json")
    result = _load(R9_ROOT / "case_results.json")
    metrics = _load(R9_ROOT / "metrics.json")
    assert experiment["eligible_case_count"] == 0
    assert experiment["empirical_evaluation_status"] == "NOT_VALIDATED"
    assert experiment["overall_status"] == "CASE_DATASET_NOT_AVAILABLE"
    assert result["case_count"] == 0
    assert result["results"] == []
    assert metrics["multimodal_accuracy"] == "NOT_REPORTED"
    assert metrics["ground_truth_available"] is False
    assert all(metric["value"] is None for metric in metrics["metrics"].values())


def test_all_six_baselines_are_defined_without_preferred_arm():
    comparison = _load(R9_ROOT / "comparison.json")
    config = (R9_ROOT / "config.yaml").read_text(encoding="utf-8")
    assert [baseline["id"] for baseline in comparison["baselines"]] == [
        "BASELINE_A",
        "BASELINE_B",
        "BASELINE_C",
        "BASELINE_D",
        "BASELINE_E",
        "BASELINE_F",
    ]
    assert comparison["common_case_count"] == 0
    assert comparison["results"] is None
    assert comparison["preferred_baseline_assumed"] is False
    assert "preferred_arm_assumed: false" in config


def test_epistemic_states_conflicts_and_uncertainty_are_preserved():
    experiment = _load(R9_ROOT / "experiment.json")
    invariants = experiment["epistemic_invariants"]
    assert all(value is False for key, value in invariants.items() if key != "human_review_required")
    assert invariants["human_review_required"] is True
    config = (R9_ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "ALIGNED, PARTIAL, CONFLICT, AMBIGUOUS, MISSING" in config
    assert "CONFLICT_REQUIRES_REVIEW" in config
    assert "auto_select_winner: false" in config
    assert "uncertainty" in config


def test_authority_and_environmental_rules_remain_restricted():
    config = (R9_ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "builder_supported_only_by_explicit_tender_contract_concession_project_document_or_official_registry: true" in config
    assert config.count("causal_inference_allowed: false") == 2
    assert "human_review_value: REQUIRED" in config


def test_provenance_references_match_frozen_sources():
    provenance = _load(R9_ROOT / "provenance.json")
    for source in provenance["frozen_inputs"]:
        assert _sha256(REPO_ROOT / source["path"]) == source["sha256"]
    assert _load(R9_ROOT / "case_results.json")["input_dataset_manifest_sha256"] == R8_DATASET_SHA256


def test_no_autonomous_decision_or_production_mutation():
    experiment = _load(R9_ROOT / "experiment.json")
    assert experiment["research_only"] is True
    assert experiment["production_integration"] is False
    assert experiment["autonomous_decisions"] is False
    assert experiment["human_review_required"] is True
    assert experiment["final_state"]["NO GIT COMMIT"] is True
    assert experiment["final_state"]["NO GIT PUSH"] is True


def test_r9_freeze_hashes_all_research_records():
    manifest = _load(R9_ROOT / "freeze_manifest.json")
    assert manifest["freeze_status"] == "FROZEN_RESEARCH_RECORD"
    assert manifest["r8_freeze_manifest_sha256"] == R8_FREEZE_SHA256
    for relative_path, expected_hash in manifest["files"].items():
        assert _sha256(R9_ROOT / relative_path) == expected_hash
