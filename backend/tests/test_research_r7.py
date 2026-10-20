"""R7 frozen-reference, provenance, and epistemic-boundary acceptance tests."""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
R7_ROOT = REPO_ROOT / "ai" / "research" / "experiments" / "R7"

M113_SHA256 = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
R3_SHA256 = "72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28"
D0_FILE_COUNT = 605
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


def _load(name: str) -> dict:
    return json.loads((R7_ROOT / name).read_text(encoding="utf-8"))


def test_frozen_m113_sha256():
    checkpoint = (
        REPO_ROOT
        / "ai"
        / "computer_vision"
        / "training"
        / "runs"
        / "yolov8n_m1_13"
        / "weights"
        / "best.pt"
    )
    assert _sha256(checkpoint) == M113_SHA256


def test_frozen_r3_checkpoint_sha256():
    checkpoint = (
        REPO_ROOT
        / "ai"
        / "research"
        / "experiments"
        / "R3"
        / "CVR2-CV-006"
        / "weights"
        / "best.pt"
    )
    assert _sha256(checkpoint) == R3_SHA256


def test_d0_count_and_tree_integrity():
    d0_root = REPO_ROOT / "ai" / "computer_vision" / "dataset_m1_13"
    files = sorted(
        (path for path in d0_root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(d0_root).as_posix(),
    )
    assert len(files) == D0_FILE_COUNT

    digest = hashlib.sha256()
    for path in files:
        relative_path = path.relative_to(d0_root).as_posix().encode("utf-8")
        file_hash = _sha256(path).encode("ascii")
        digest.update(relative_path + b"\0" + file_hash + b"\n")
    assert digest.hexdigest() == D0_TREE_SHA256


def test_r5_r6_manifest_and_metrics_integrity():
    r5_manifest = REPO_ROOT / "ai/research/datasets/R5_controlled_shift/manifest.json"
    r5_metrics = REPO_ROOT / "ai/research/experiments/R5/metrics.json"
    r6_manifest = REPO_ROOT / "ai/research/datasets/R6_controlled_sequences/manifest.json"
    r6_metrics = REPO_ROOT / "ai/research/experiments/R6/metrics.json"
    assert _sha256(r5_manifest) == R5_MANIFEST_SHA256
    assert _sha256(r5_metrics) == R5_METRICS_SHA256
    assert _sha256(r6_manifest) == R6_MANIFEST_SHA256
    assert _sha256(r6_metrics) == R6_METRICS_SHA256
    assert (r5_manifest.parent / "MANIFEST.SHA256").read_text(
        encoding="ascii"
    ).startswith(R5_MANIFEST_SHA256)
    assert (r6_manifest.parent / "MANIFEST.SHA256").read_text(
        encoding="ascii"
    ).startswith(R6_MANIFEST_SHA256)


def test_no_fabricated_civic_evidence():
    cases = _load("case_set.json")
    assert cases["case_count"] == 0
    assert cases["records"] == []
    assert cases["no_fabricated_evidence"] is True
    assert cases["synthetic_context_created"] is False


def test_provenance_is_complete_for_every_cited_source():
    provenance = _load("provenance.json")
    sources = {source["source_id"]: source for source in provenance["sources"]}
    assert provenance["provenance_status"] == "COMPLETE_FOR_AUDITED_INPUTS"
    assert provenance["case_evidence_status"] == "NOT_AVAILABLE"
    for source in sources.values():
        source_path = REPO_ROOT / source["path"]
        if source_path.is_file():
            assert _sha256(source_path) == source["sha256"]
        elif source_path.is_dir():
            assert source["file_count"] == D0_FILE_COUNT
        else:
            raise AssertionError(f"Missing provenance source: {source['path']}")

    case_set = _load("case_set.json")
    for modality in case_set["modality_inventory"]:
        assert set(modality["provenance_refs"]) <= sources.keys()
    assert {"M1_13_CHECKPOINT", "D0_DATASET", "R3_CHECKPOINT"} <= sources.keys()


def test_user_reported_state_is_not_relabelled():
    modality = next(
        item
        for item in _load("case_set.json")["modality_inventory"]
        if item["modality"] == "USER_REPORTED"
    )
    assert modality["epistemic_state"] == "USER_REPORTED"
    assert modality["availability"] == "NOT_AVAILABLE"
    assert modality["provenance_refs"] == []


def test_cv_observation_state_remains_model_observation():
    modality = next(
        item
        for item in _load("case_set.json")["modality_inventory"]
        if item["modality"] == "CV_OBSERVATION"
    )
    assert modality["epistemic_state"] == "MODEL_OBSERVATION"
    assert modality["availability"] == "INSUFFICIENT_SAMPLE"
    assert modality["case_linked"] is False


def test_system_derived_context_is_not_physical_truth():
    modalities = _load("case_set.json")["modality_inventory"]
    derived = [
        item
        for item in modalities
        if item["epistemic_state"] == "SYSTEM_DERIVED"
    ]
    assert derived
    assert all(item["availability"] == "NOT_AVAILABLE" for item in derived)
    assert all(item["case_linked"] is False for item in derived)
    assert all(not item["provenance_refs"] for item in derived)


def test_weather_is_not_causal_evidence():
    weather = next(
        item
        for item in _load("case_set.json")["modality_inventory"]
        if item["modality"] == "WEATHER"
    )
    assert weather["availability"] == "NOT_AVAILABLE"
    assert weather["causal_inference_allowed"] is False


def test_rainfall_is_not_causal_evidence():
    rainfall = next(
        item
        for item in _load("case_set.json")["modality_inventory"]
        if item["modality"] == "RAINFALL"
    )
    assert rainfall["availability"] == "NOT_AVAILABLE"
    assert rainfall["causal_inference_allowed"] is False


def test_traffic_is_not_causal_evidence():
    traffic = next(
        item
        for item in _load("case_set.json")["modality_inventory"]
        if item["modality"] == "TRAFFIC"
    )
    assert traffic["availability"] == "NOT_AVAILABLE"
    assert traffic["causal_inference_allowed"] is False


def test_builder_attribution_requires_explicit_evidence():
    builder = next(
        item
        for item in _load("case_set.json")["modality_inventory"]
        if item["modality"] == "BUILDER_CONTRACTOR"
    )
    assert builder["availability"] == "NOT_AVAILABLE"
    assert builder["explicit_project_evidence_required"] is True
    assert builder["provenance_refs"] == []


def test_conflicts_are_preserved_for_human_review():
    import yaml

    policy = yaml.safe_load((R7_ROOT / "config.yaml").read_text(encoding="utf-8"))[
        "conflict_policy"
    ]
    assert policy["preserve_all_modality_observations"] is True
    assert policy["output_when_material_conflict"] == "CONFLICT_REQUIRES_REVIEW"
    assert policy["automatically_select_winning_modality"] is False
    assert policy["treat_disagreement_as_model_failure"] is False


def test_unavailable_modalities_are_explicit():
    inventory = _load("case_set.json")["modality_inventory"]
    assert inventory
    assert all(item["availability"] in {"NOT_AVAILABLE", "INSUFFICIENT_SAMPLE"} for item in inventory)
    assert all("provenance_refs" in item for item in inventory)


def test_human_review_remains_required():
    experiment = _load("experiment.json")
    import yaml

    config = yaml.safe_load((R7_ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert experiment["human_review_required"] is True
    assert config["human_review_required"] is True


def test_no_autonomous_lifecycle_mutation():
    experiment = _load("experiment.json")
    assert experiment["autonomous_decisions"] is False
    assert experiment["lifecycle_mutation"] is False
    assert experiment["final_state"]["NO GIT COMMIT"] is True
    assert experiment["final_state"]["NO GIT PUSH"] is True


def test_no_production_integration():
    experiment = _load("experiment.json")
    metrics = _load("metrics.json")
    assert experiment["research_only"] is True
    assert experiment["production_integration"] is False
    assert experiment["final_state"]["PRODUCTION INTEGRATION"] is False
    assert metrics["study_id"] == experiment["experiment_id"]


def test_all_experiments_and_ablation_arms_are_defined_without_claims():
    experiment = _load("experiment.json")
    comparison = _load("comparison.json")
    valid_statuses = {
        "VALIDATED",
        "PARTIALLY_VALIDATED",
        "NOT_VALIDATED",
        "DESCRIPTIVE_ONLY",
        "INSUFFICIENT_SAMPLE",
        "NOT_AVAILABLE",
    }
    assert [item["id"] for item in experiment["execution_order"]] == [
        f"CVR2-E-{index:03}" for index in range(1, 11)
    ]
    assert all(
        item["name"] and item["result"] and item["status"] in valid_statuses
        for item in experiment["execution_order"]
    )
    assert [item["id"] for item in comparison["arms"]] == list("ABCDEF")
    assert comparison["shared_case_count"] == 0
    assert comparison["results"] is None
    assert _load("metrics.json")["evaluation_type"] == "DESCRIPTIVE_ONLY"
