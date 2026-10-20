"""R5 controlled perturbation reproducibility and isolation tests."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from ai.research.r5_controlled_shift import (
    CLASS_NAMES,
    D1_ROOT,
    EXCLUDED_TRANSFORMATIONS,
    EVALUATION_IOU,
    M113_SHA256,
    PRIMARY_THRESHOLD,
    R3_CHECKPOINT,
    R3_SHA256,
    R5_ROOT,
    SECONDARY_THRESHOLD,
    TRANSFORM_PARAMETERS,
    apply_transform,
    crop_yolo_labels,
    derive_seed,
    parse_yolo_label_text,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
R5_EXPERIMENT_DIR = REPO_ROOT / "ai" / "research" / "experiments" / "R5"
M113_CHECKPOINT = (
    REPO_ROOT
    / "ai"
    / "computer_vision"
    / "training"
    / "runs"
    / "yolov8n_m1_13"
    / "weights"
    / "best.pt"
)
D0_ROOT = REPO_ROOT / "ai" / "computer_vision" / "dataset_m1_13"


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def test_frozen_m113_checkpoint_sha256():
    assert sha256_file(M113_CHECKPOINT) == M113_SHA256


def test_frozen_r3_checkpoint_sha256():
    assert R3_CHECKPOINT.is_file()
    assert sha256_file(R3_CHECKPOINT) == R3_SHA256


def test_d0_frozen_file_count_and_research_output_isolation():
    assert D0_ROOT.is_dir()
    assert sum(1 for path in D0_ROOT.rglob("*") if path.is_file()) == 605
    assert not R5_ROOT.resolve().is_relative_to(D0_ROOT.resolve())
    assert not (REPO_ROOT / "ai" / "computer_vision" / "dataset_m1_13" / "R5_controlled_shift").exists()


def test_deterministic_transformations_and_seeds():
    source_list = (D1_ROOT / "splits" / "test.txt").read_text(encoding="utf-8").splitlines()
    source = D1_ROOT / source_list[0]
    with Image.open(source) as opened:
        image = opened.convert("RGB")
        for transformation, severities in TRANSFORM_PARAMETERS.items():
            for severity in severities:
                seed = derive_seed(sha256_file(source), transformation, severity)
                first = np.asarray(apply_transform(image, transformation, severity, seed))
                second = np.asarray(apply_transform(image, transformation, severity, seed))
                assert np.array_equal(first, second), f"Nondeterministic: {transformation}/{severity}"
                assert first.shape == second.shape == (image.height, image.width, 3)


def test_source_to_generated_mapping_hashes_and_label_preservation():
    manifest = _load(R5_ROOT / "manifest.json")
    assert manifest["dataset_id"] == "R5_controlled_shift"
    assert manifest["data_type"] == "synthetic_controlled_perturbations_of_D1_research_test_images"
    assert manifest["external_real_world_dataset"] is False
    assert manifest["source_split"] == "test"
    assert manifest["excluded_transformations"] == EXCLUDED_TRANSFORMATIONS
    assert manifest["transformed_image_count"] == len(manifest["records"])
    assert manifest["transformed_image_count"] == manifest["source_image_count"] * (
        1 + len(TRANSFORM_PARAMETERS) * 3
    )

    for record in manifest["records"]:
        source_image = D1_ROOT / record["source_image"]
        source_label = D1_ROOT / record["source_label"]
        generated_image = R5_ROOT / record["generated_image"]
        generated_label = R5_ROOT / record["generated_label"]
        assert record["source_split"] == "test"
        assert sha256_file(source_image) == record["source_image_sha256"]
        assert sha256_file(source_label) == record["source_label_sha256"]
        assert sha256_file(generated_image) == record["generated_image_sha256"]
        assert sha256_file(generated_label) == record["generated_label_sha256"]
        assert record["generation_timestamp"]
        assert record["transformation"] == "clean" or record["random_seed"] is not None
        boxes = parse_yolo_label_text(generated_label.read_text(encoding="utf-8"))
        if record["transformation"] != "crop":
            assert record["generated_label_sha256"] == record["source_label_sha256"]
        else:
            assert len(boxes) == len(parse_yolo_label_text(source_label.read_text(encoding="utf-8")))
        assert all(box[0] in CLASS_NAMES for box in boxes)

    manifest_sha = sha256_file(R5_ROOT / "manifest.json")
    assert (R5_ROOT / "MANIFEST.SHA256").read_text(encoding="ascii").startswith(manifest_sha)


def test_crop_labels_are_adjusted_without_truncating_ground_truth():
    text = "2 0.5 0.5 0.4 0.4\n"
    transformed = crop_yolo_labels(text, 0.9)
    boxes = parse_yolo_label_text(transformed)
    assert len(boxes) == 1
    assert boxes[0][0] == 2
    assert np.allclose(boxes[0][1:], (0.5, 0.5, 0.4 / 0.9, 0.4 / 0.9))
    assert "crop_viewpoint" in EXCLUDED_TRANSFORMATIONS


def test_no_d0_mutation_and_no_production_integration():
    experiment = _load(R5_EXPERIMENT_DIR / "experiment.json")
    metrics = _load(R5_EXPERIMENT_DIR / "metrics.json")

    assert experiment["research_only"] is True
    assert experiment["production_integration"] is False
    assert experiment["excluded_transformations"] == EXCLUDED_TRANSFORMATIONS
    assert metrics["external_real_world_dataset"] is False
    assert metrics["data_type"] == "controlled synthetic perturbations"
    assert all(
        record["generated_image"].startswith(("clean/", *TRANSFORM_PARAMETERS.keys()))
        for record in _load(R5_ROOT / "manifest.json")["records"]
    )


def test_frozen_threshold_protocol_is_recorded_without_condition_tuning():
    experiment = _load(R5_EXPERIMENT_DIR / "experiment.json")
    metrics = _load(R5_EXPERIMENT_DIR / "metrics.json")

    assert experiment["thresholds"] == {
        "primary_confidence": PRIMARY_THRESHOLD,
        "secondary_confidence": SECONDARY_THRESHOLD,
        "IoU": EVALUATION_IOU,
        "no_per_condition_tuning": True,
    }
    for condition in metrics["conditions"].values():
        assert condition["primary"]["confidence_threshold"] == PRIMARY_THRESHOLD
        assert condition["secondary"]["confidence_threshold"] == SECONDARY_THRESHOLD
        assert condition["primary"]["IoU_threshold"] == EVALUATION_IOU
        assert condition["secondary"]["IoU_threshold"] == EVALUATION_IOU


def test_provenance_and_output_manifest_hash_completeness():
    experiment = _load(R5_EXPERIMENT_DIR / "experiment.json")
    metrics = _load(R5_EXPERIMENT_DIR / "metrics.json")
    manifest = _load(R5_ROOT / "manifest.json")

    assert experiment["experiment_id"] == "CVR2-CV-016"
    assert experiment["generation_manifest_sha256"] == sha256_file(R5_ROOT / "manifest.json")
    assert metrics["dataset_manifest_sha256"] == experiment["generation_manifest_sha256"]
    assert metrics["source_dataset"] == "D1"
    assert metrics["source_image_count"] == manifest["source_image_count"]
    assert metrics["output_manifest_sha256"] == experiment["output_manifest_sha256"]
    assert metrics["source_dataset_composite_sha256"] == manifest["source_dataset_composite_sha256"]
    assert metrics["source_dataset_manifest_file_sha256"] == sha256_file(
        D1_ROOT / "manifests" / "dataset_manifest.json"
    )
    assert metrics["model_sha256"] == R3_SHA256
    assert metrics["checkpoint_sha256"] == R3_SHA256
    assert metrics["m1_13_sha256"] == M113_SHA256
    assert metrics["d0_file_count_reference"] == 605
    assert metrics["evaluation_code_sha256"] == sha256_file(
        REPO_ROOT / "ai" / "research" / "r5_controlled_shift.py"
    )
    assert experiment["evaluation_code_sha256"] == metrics["evaluation_code_sha256"]
    assert experiment["m1_13_sha256"] == M113_SHA256
    assert experiment["d0_file_count_reference"] == 605
    assert metrics["environment"]
    assert metrics["timestamp"]
    assert all(
        condition["average_precision_evaluation"]["evaluator"]
        == "Ultralytics DetectionValidator"
        and condition["average_precision_evaluation"]["confidence_floor"] == 0.001
        for condition in metrics["conditions"].values()
    )
    assert all(
        condition["generated_manifest_sha256"] == experiment["generation_manifest_sha256"]
        and condition["source_dataset"] == "D1"
        and condition["source_split"] == "test"
        for condition in metrics["conditions"].values()
    )


def test_tp_fn_ground_truth_invariant_and_class_sample_status():
    metrics = _load(R5_EXPERIMENT_DIR / "metrics.json")
    for condition in metrics["conditions"].values():
        for operating_point in ("primary", "secondary"):
            result = condition[operating_point]
            assert result["TP"] + result["FN"] == result["ground_truth_box_count"]
            assert result["image_count"] == manifest_source_count()

    support = metrics["summary"]["class_support"]
    assert support["road_waterlogging"] > 0
    assert metrics["summary"]["insufficient_sample_classes"] == [
        "open_damaged_manhole",
        "damaged_missing_road_sign",
    ]
    for condition in metrics["conditions"].values():
        assert condition["primary"]["per_class"]["open_damaged_manhole"]["status"] == "INSUFFICIENT_SAMPLE"
        assert condition["primary"]["per_class"]["damaged_missing_road_sign"]["status"] == "INSUFFICIENT_SAMPLE"


def test_clean_reference_ap_matches_frozen_r3_heldout_record():
    metrics = _load(R5_EXPERIMENT_DIR / "metrics.json")
    clean = metrics["conditions"]["clean:clean"]["primary"]

    assert clean["image_count"] == 18
    assert clean["ground_truth_box_count"] == 15
    assert np.isclose(clean["mAP50"], 0.99125, atol=1e-6)
    assert np.isclose(clean["mAP50_95"], 0.7924805555555555, atol=1e-6)


def manifest_source_count() -> int:
    return _load(R5_ROOT / "manifest.json")["source_image_count"]
