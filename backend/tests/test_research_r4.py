"""Research-only guardrails for the R4 D2 admission failure."""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
R4_DIR = REPO_ROOT / "ai" / "research" / "experiments" / "R4"
D1_DIR = REPO_ROOT / "ai" / "research" / "datasets" / "D1"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def test_frozen_reference_attestation_records_supplied_values():
    attestation = load_json(R4_DIR / "frozen_reference_attestation.json")

    assert attestation["status"] == "UPSTREAM_INTEGRITY_GATE_PASSED_NOT_RECOMPUTED"
    assert attestation["d0"] == {"file_count": 605, "status": "FROZEN"}
    assert attestation["m1_13"]["sha256"] == (
        "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
    )
    assert attestation["r3_checkpoint"]["sha256"] == (
        "72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28"
    )


def test_d1_asset_hashes_and_composite_manifest_are_unchanged():
    images_manifest = load_json(D1_DIR / "manifests" / "images_manifest.json")
    labels_manifest = load_json(D1_DIR / "manifests" / "labels_manifest.json")
    dataset_manifest = load_json(D1_DIR / "manifests" / "dataset_manifest.json")
    composite = hashlib.sha256()

    assert images_manifest["count"] == 122
    assert labels_manifest["count"] == 122

    for manifest, key in ((images_manifest, "images"), (labels_manifest, "labels")):
        for entry in manifest[key]:
            asset = D1_DIR / entry["relative_path"]
            assert asset.is_file(), f"Missing D1 asset: {entry['relative_path']}"
            actual_sha = hashlib.sha256(asset.read_bytes()).hexdigest()
            assert actual_sha == entry["sha256"], f"D1 asset changed: {entry['relative_path']}"

    for entry in sorted(images_manifest["images"], key=lambda item: item["relative_path"]):
        composite.update(f"{entry['relative_path']}:{entry['sha256']}\n".encode("utf-8"))
    for entry in sorted(labels_manifest["labels"], key=lambda item: item["relative_path"]):
        composite.update(f"{entry['relative_path']}:{entry['sha256']}\n".encode("utf-8"))

    assert composite.hexdigest() == dataset_manifest["composite_sha256"]
    assert composite.hexdigest() == (
        "c93dc3c2f3c25fe09c1f6aa23bce91684d60528694ef7036f2d7932c9775f68e"
    )


def test_d2_manifest_and_annotations_are_not_fabricated():
    audit = load_json(R4_DIR / "dataset_construction_audit.json")

    assert not (REPO_ROOT / "ai" / "research" / "datasets" / "D2").exists()
    assert audit["dataset_created"] is False
    assert audit["dataset_checksum"] is None
    assert audit["annotation_audit"] == {
        "status": "NOT_APPLICABLE_NO_D2_ANNOTATIONS",
        "annotation_count": 0,
    }
    assert audit["admitted_assets"] == 0


def test_d2_leakage_audit_does_not_claim_independence():
    audit = load_json(R4_DIR / "dataset_construction_audit.json")
    duplicate_audit = audit["duplicate_audit"]

    assert duplicate_audit["exact_duplicates"] == "NOT_RUN_NO_D2_ASSETS"
    assert duplicate_audit["near_duplicates"] == "NOT_RUN_NO_D2_ASSETS"
    assert duplicate_audit["same_sequence"] == "NOT_RUN_NO_D2_ASSETS"
    assert duplicate_audit["transformed_copies"] == "NOT_RUN_NO_D2_ASSETS"
    assert duplicate_audit["shared_source_imagery"] == "NOT_ESTABLISHED"
    assert duplicate_audit["independence_established"] is False


def test_d2_class_distribution_is_not_presented_as_balanced():
    audit = load_json(R4_DIR / "dataset_construction_audit.json")

    assert audit["class_distribution"] == {
        "0_open_damaged_manhole": 0,
        "1_damaged_missing_road_sign": 0,
        "2_road_waterlogging": 0,
        "status": "D2_NOT_CREATED; counts are zero admitted assets, not an evaluated class distribution",
    }


def test_thresholds_and_provenance_are_recorded_for_each_experiment():
    experiments = load_json(R4_DIR / "experiments.json")["experiments"]
    expected_ids = {
        "CVR2-CV-011",
        "CVR2-CV-012",
        "CVR2-CV-013",
        "CVR2-CV-014",
        "CVR2-CV-015",
    }

    assert {experiment["experiment_id"] for experiment in experiments} == expected_ids
    for experiment in experiments:
        assert experiment["dataset_id"] == "D2"
        assert experiment["dataset_checksum"] is None
        assert experiment["model_id"] == "R3-CVR2-CV-006"
        assert experiment["checkpoint_SHA256"] == (
            "72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28"
        )
        assert experiment["confidence_threshold"] == 0.1
        assert experiment["secondary_confidence_threshold"] == 0.25
        assert experiment["IoU_threshold"] == 0.5
        assert experiment["evaluation_split"]
        assert experiment["source"]
        assert experiment["license"]
        assert experiment["geography"]
        assert experiment["environment"]
        assert experiment["timestamp"]


def test_final_evaluation_is_protected_and_no_metrics_are_claimed():
    experiments = load_json(R4_DIR / "experiments.json")
    audit = load_json(R4_DIR / "dataset_construction_audit.json")
    metrics = experiments["metrics"]

    assert audit["evaluation_manifest_frozen"] is False
    assert audit["evaluation_performed"] is False
    assert metrics["status"] == "NOT_EVALUATED"
    for metric in (
        "image_count",
        "ground_truth_box_count",
        "precision",
        "recall",
        "F1",
        "mAP50",
        "mAP50_95",
        "TP",
        "FP",
        "FN",
        "macro_precision",
        "macro_recall",
        "macro_F1",
        "micro_precision",
        "micro_recall",
    ):
        assert metrics[metric] is None
    if metrics["TP"] is not None:
        assert metrics["TP"] + metrics["FN"] == metrics["ground_truth_box_count"]


def test_r4_is_research_only_and_cannot_activate_production():
    experiments = load_json(R4_DIR / "experiments.json")

    assert experiments["research_only"] is True
    assert experiments["production_integration"] is False
    assert all(
        experiment["production_integration"] is False
        for experiment in experiments["experiments"]
    )


def test_cross_dataset_evaluation_reports_required_unavailable_status():
    experiments = load_json(R4_DIR / "experiments.json")["experiments"]
    by_id = {experiment["experiment_id"]: experiment for experiment in experiments}

    assert by_id["CVR2-CV-011"]["status"] == "D2_NOT_AVAILABLE"
    assert by_id["CVR2-CV-013"]["status"] == "CROSS_DATASET_EVALUATION_NOT_AVAILABLE"
    assert by_id["CVR2-CV-012"]["status"] == "NOT_RUN_NO_VALID_D2"
    assert by_id["CVR2-CV-014"]["status"] == "NOT_RUN_NO_VALID_D2"
    assert by_id["CVR2-CV-015"]["status"] == "NOT_RUN_NO_VALID_D2"
