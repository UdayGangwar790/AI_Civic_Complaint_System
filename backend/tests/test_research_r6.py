"""R6 temporal sequence integrity and metric-definition tests."""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from ai.research.r5_controlled_shift import (
    D1_ROOT,
    M113_SHA256,
    R3_CHECKPOINT,
    R3_SHA256,
    sha256_file,
)
from ai.research.r6_temporal_study import (
    EVALUATION_IOU,
    EXPERIMENT_ROOT,
    FRAME_COUNT,
    MASTER_SEED,
    PRIMARY_THRESHOLD,
    R6_ROOT,
    SECONDARY_THRESHOLD,
    SEQUENCE_TYPES,
    TEMPORAL_RULES,
    _filter_event,
    _make_frame,
    _seed,
    _temporal_metrics,
    _associate_false_positive_tracks,
)
from ai.research.r5_controlled_shift import CLASS_NAMES, parse_yolo_label_text

REPO_ROOT = Path(__file__).resolve().parents[2]
D0_ROOT = REPO_ROOT / "ai" / "computer_vision" / "dataset_m1_13"
R5_MANIFEST_SHA256 = (
    "d36bd0f653c5650f628ad26d9397b5e843154931f23177918235b94b2f899f0e"
)
R5_METRICS_SHA256 = (
    "a07f0ac9271b5af85689346632e181201fb453918408539505ed23059c39b13e"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_frozen_artifact_hashes_and_r5_unchanged():
    m113 = (
        REPO_ROOT
        / "ai"
        / "computer_vision"
        / "training"
        / "runs"
        / "yolov8n_m1_13"
        / "weights"
        / "best.pt"
    )
    assert sha256_file(m113) == M113_SHA256
    assert sha256_file(R3_CHECKPOINT) == R3_SHA256
    assert sha256_file(REPO_ROOT / "ai/research/datasets/R5_controlled_shift/manifest.json") == R5_MANIFEST_SHA256
    assert sha256_file(REPO_ROOT / "ai/research/experiments/R5/metrics.json") == R5_METRICS_SHA256


def test_d0_frozen_count_and_r6_research_isolation():
    assert sum(path.is_file() for path in D0_ROOT.rglob("*")) == 605
    assert not R6_ROOT.resolve().is_relative_to(D0_ROOT.resolve())
    assert not EXPERIMENT_ROOT.resolve().is_relative_to(
        (REPO_ROOT / "backend").resolve()
    )
    assert not (D0_ROOT / "R6_controlled_sequences").exists()


def test_deterministic_frame_generation_and_ordering():
    source_image_path = D1_ROOT / "images" / "d1_road_waterlogging_015.jpg"
    label_path = D1_ROOT / "labels" / "d1_road_waterlogging_015.txt"
    source_hash = sha256_file(source_image_path)
    source_objects = [
        {
            "object_id": index,
            "class_id": class_id,
            "xywh_normalized": [x, y, width, height],
        }
        for index, (class_id, x, y, width, height) in enumerate(
            parse_yolo_label_text(label_path.read_text(encoding="utf-8"))
        )
    ]
    with Image.open(source_image_path) as opened:
        source_image = opened.convert("RGB")
    for sequence_type in SEQUENCE_TYPES:
        for frame_id in range(FRAME_COUNT):
            seed = _seed(source_hash, sequence_type, frame_id)
            assert seed == _seed(source_hash, sequence_type, frame_id)
            first = _make_frame(
                source_image, source_objects, sequence_type, frame_id, seed
            )
            second = _make_frame(
                source_image, source_objects, sequence_type, frame_id, seed
            )
            assert np.array_equal(np.asarray(first[0]), np.asarray(second[0]))
            assert first[1:] == second[1:]


def test_temporal_filter_rules_and_gap_metrics():
    assert _filter_event([False, True, True, False], "2_FRAME_PERSISTENCE") == (
        True,
        2,
    )
    assert _filter_event([True, False, True], "3_FRAME_PERSISTENCE") == (
        False,
        None,
    )
    assert _filter_event(
        [True, False, True], "1_FRAME_GAP_TOLERANCE"
    ) == (True, 2)
    assert _filter_event([False, True, False], "NO_TEMPORAL_FILTER") == (
        True,
        1,
    )
    frames = []
    detection = [True, False, True, True, False]
    for frame_id, found in enumerate(detection):
        prediction = (
            [
                {
                    "class_id": 2,
                    "class_name": "road_waterlogging",
                    "confidence": 0.8,
                    "box": [10.0, 10.0, 30.0, 30.0],
                }
            ]
            if found
            else []
        )
        frames.append(
            {
                "frame_id": frame_id,
                "inference_ms": 10.0,
                "ground_truth": [
                    {"object_id": 7, "class_id": 2, "box": [10, 10, 30, 30]}
                ],
                "predictions": prediction,
            }
        )
    result = _temporal_metrics(frames, PRIMARY_THRESHOLD, 1)
    rules = result["event_results_by_rule"]
    assert rules["2_FRAME_PERSISTENCE"]["detected_ground_truth_events"] == 1
    assert rules["3_FRAME_PERSISTENCE"]["detected_ground_truth_events"] == 0
    assert rules["1_FRAME_GAP_TOLERANCE"]["detected_ground_truth_events"] == 1
    assert result["detection_gap_count"] == 2
    assert result["recovery_rate"] == 0.5
    assert result["frame_TP"] + result["frame_FN"] == 5
    assert result["frame_processing_fraction"] == 1.0


def test_false_positive_association_is_deterministic_and_gap_tolerant():
    frames = [
        [
            {"class_id": 2, "confidence": 0.2, "box": [1, 1, 20, 20]},
        ],
        [],
        [
            {"class_id": 2, "confidence": 0.3, "box": [2, 1, 21, 20]},
        ],
    ]
    first = _associate_false_positive_tracks(frames)
    second = _associate_false_positive_tracks(frames)
    assert first == second
    assert len(first) == 1
    assert len(first[0]["observations"]) == 2


def test_manifest_labels_provenance_thresholds_and_no_production_activation():
    manifest = _load(R6_ROOT / "manifest.json")
    metrics = _load(EXPERIMENT_ROOT / "metrics.json")
    experiment = _load(EXPERIMENT_ROOT / "experiment.json")
    manifest_sha = sha256_file(R6_ROOT / "manifest.json")
    assert manifest["dataset_id"] == "R6_controlled_sequences"
    assert manifest["data_type"] == "CONTROLLED_SYNTHETIC_TEMPORAL_EVALUATION"
    assert manifest["real_world_video_evaluation"] == "REAL_WORLD_VIDEO_EVALUATION_NOT_AVAILABLE"
    assert manifest["frame_count"] == 18 * len(SEQUENCE_TYPES) * FRAME_COUNT
    assert len(manifest["records"]) == manifest["frame_count"]
    assert (R6_ROOT / "MANIFEST.SHA256").read_text(encoding="ascii").startswith(
        manifest_sha
    )
    assert metrics["sequence_manifest_sha256"] == manifest_sha
    assert metrics["evaluation_code_sha256"] == sha256_file(
        REPO_ROOT / "ai/research/r6_temporal_study.py"
    )
    assert experiment["evaluation_code_sha256"] == metrics["evaluation_code_sha256"]
    assert experiment["metrics_sha256"] == sha256_file(
        EXPERIMENT_ROOT / "metrics.json"
    )
    assert metrics["confidence_threshold"] == PRIMARY_THRESHOLD
    assert metrics["secondary_confidence_threshold"] == SECONDARY_THRESHOLD
    assert metrics["IoU_threshold"] == EVALUATION_IOU
    assert metrics["production_integration"] is False
    assert metrics["research_only"] is True
    assert experiment["production_integration"] is False
    assert experiment["sequence_manifest_sha256"] == manifest_sha
    for record in manifest["records"]:
        image = R6_ROOT / record["generated_image"]
        label = R6_ROOT / record["generated_label"]
        source_image = D1_ROOT / record["source_image"]
        source_label = D1_ROOT / record["source_label"]
        assert record["manifest_reference"] == "manifest.json"
        assert record["frame_id"] == record["temporal_order"]
        assert sha256_file(source_image) == record["source_image_sha256"]
        assert sha256_file(source_label) == record["source_label_sha256"]
        assert sha256_file(image) == record["generated_image_sha256"]
        assert sha256_file(label) == record["generated_label_sha256"]
        boxes = parse_yolo_label_text(label.read_text(encoding="utf-8"))
        assert all(class_id in CLASS_NAMES for class_id, *_ in boxes)
        assert len(boxes) == len(record["ground_truth_objects"])
        assert record["seed"] is not None


def test_all_requested_experiments_have_provenance_records():
    experiment_ids = [f"CVR2-CV-{number:03d}" for number in range(17, 25)]
    for experiment_id in experiment_ids:
        record = _load(EXPERIMENT_ROOT / f"{experiment_id}.json")
        assert record["experiment_id"] == experiment_id
        assert record["source_dataset"] == "D1"
        assert record["source_hash"]
        assert record["sequence_generation_method"]
        assert record["seed"] == MASTER_SEED
        assert record["frame_count"] == FRAME_COUNT
        assert record["model_hash"] == R3_SHA256
        assert record["checkpoint_hash"] == R3_SHA256
        assert record["confidence_threshold"] == PRIMARY_THRESHOLD
        assert record["IoU_threshold"] == EVALUATION_IOU
        assert record["temporal_association_rule"]
        assert record["temporal_filter"] == list(TEMPORAL_RULES)
        assert record["output_manifest_sha256"]
        assert record["environment"]
        assert record["timestamp"]


def test_frame_metrics_threshold_recording_and_sample_support():
    metrics = _load(EXPERIMENT_ROOT / "metrics.json")
    assert metrics["class_support_status"]["open_damaged_manhole"] == "INSUFFICIENT_SAMPLE"
    assert metrics["class_support_status"]["damaged_missing_road_sign"] == "INSUFFICIENT_SAMPLE"
    assert metrics["class_support_status"]["road_waterlogging"] == "VALID_SAMPLE"
    for sequence_type, result in metrics["sequence_results"].items():
        assert result["frame_count"] == 18 * FRAME_COUNT
        assert result["primary_frame_metrics"]["TP"] + result["primary_frame_metrics"]["FN"] == result["primary_frame_metrics"]["ground_truth_box_count"]
        assert len(result["frame_level_records"]) == result["frame_count"]
        for frame in result["frame_level_records"]:
            assert frame["operating_points"]["primary"]["confidence_threshold"] == PRIMARY_THRESHOLD
            assert frame["operating_points"]["secondary"]["confidence_threshold"] == SECONDARY_THRESHOLD
            assert frame["operating_points"]["primary"]["IoU_threshold"] == EVALUATION_IOU
        assert set(result["temporal_by_sampling_stride"]) == {"1", "2", "3"}
        assert set(result["temporal_by_sampling_stride"]["1"]["event_results_by_rule"]) == set(TEMPORAL_RULES)
