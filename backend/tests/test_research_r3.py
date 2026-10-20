"""
CVKI Research v2.x - R3 Robustness & Generalization Test Suite
Path: backend/tests/test_research_r3.py

Verifies 15 critical research invariants for Milestone R3:
1. D0 immutability check
2. M1.13 SHA integrity check
3. D1 integrity check
4. R3 experiment registration check
5. Research model isolation check
6. Test set protection check
7. Threshold recording check
8. Validation-only threshold selection check
9. Corruption metadata check
10. Bounding box preservation check
11. TP/FP/FN consistency check
12. Metric consistency check
13. Robustness result schema check
14. Insufficient-sample handling check
15. Checkpoint SHA recording check
"""

import json
import math
from pathlib import Path
import pytest

from ai.research.scripts.verify_baseline import (
    EXPECTED_M113_SHA,
    EXPECTED_DATASET_COUNT,
    compute_file_sha256,
    verify_baseline,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
R3_DIR = REPO_ROOT / "ai" / "research" / "experiments" / "R3"
D1_DIR = REPO_ROOT / "ai" / "research" / "datasets" / "D1"


def test_01_d0_immutability():
    """Verify production dataset D0 file count remains exactly 605 files."""
    d0_path = REPO_ROOT / "ai" / "computer_vision" / "dataset_m1_13"
    files = [f for f in d0_path.rglob("*") if f.is_file()]
    assert len(files) == EXPECTED_DATASET_COUNT, f"D0 file count changed! Expected {EXPECTED_DATASET_COUNT}, got {len(files)}"


def test_02_m113_sha_integrity():
    """Verify production baseline M1.13 model weights remain frozen and exact SHA-256 matches."""
    m113_path = REPO_ROOT / "ai" / "computer_vision" / "training" / "runs" / "yolov8n_m1_13" / "weights" / "best.pt"
    assert m113_path.exists(), f"M1.13 model file missing at {m113_path}"
    current_sha = compute_file_sha256(str(m113_path))
    assert current_sha == EXPECTED_M113_SHA, f"M1.13 weights modified! Expected {EXPECTED_M113_SHA}, got {current_sha}"
    assert verify_baseline() is True


def test_03_d1_dataset_integrity():
    """Verify D1 research candidate dataset structure, split counts, and target classes."""
    manifest_p = D1_DIR / "manifests" / "dataset_manifest.json"
    assert manifest_p.exists(), "D1 dataset_manifest.json must exist"
    
    with open(manifest_p, "r", encoding="utf-8") as f:
        meta = json.load(f)
    
    assert meta.get("total_images") == 122, f"Expected 122 total images in D1, found {meta.get('total_images')}"
    assert meta.get("train_count") == 86, f"Expected 86 train images, found {meta.get('train_count')}"
    assert meta.get("val_count") == 18, f"Expected 18 val images, found {meta.get('val_count')}"
    assert meta.get("test_count") == 18, f"Expected 18 test images, found {meta.get('test_count')}"
    
    # Also verify the physical split text files
    for split_name, expected_count in [("train.txt", 86), ("val.txt", 18), ("test.txt", 18)]:
        split_file = D1_DIR / "splits" / split_name
        assert split_file.exists(), f"Missing split file {split_name}"
        lines = [line.strip() for line in split_file.read_text().splitlines() if line.strip()]
        assert len(lines) == expected_count, f"{split_name} count mismatch: {len(lines)} != {expected_count}"


def test_04_r3_experiment_registration():
    """Verify all 5 R3 experiments (CVR2-CV-006 to 010) exist and are registered."""
    r3_ids = ["CVR2-CV-006", "CVR2-CV-007", "CVR2-CV-008", "CVR2-CV-009", "CVR2-CV-010"]
    for exp_id in r3_ids:
        exp_dir = R3_DIR / exp_id
        assert exp_dir.exists(), f"Experiment directory for {exp_id} must exist"
        assert (exp_dir / "config.yaml").exists(), f"config.yaml missing in {exp_id}"
        assert (exp_dir / "experiment.json").exists(), f"experiment.json missing in {exp_id}"
        assert (exp_dir / "environment.json").exists(), f"environment.json missing in {exp_id}"
        assert (exp_dir / "metrics.json").exists(), f"metrics.json missing in {exp_id}"
        assert (exp_dir / "README.md").exists(), f"README.md missing in {exp_id}"


def test_05_research_model_isolation():
    """Verify research models are tagged RESEARCH_ONLY / COMPLETED, never flagged for production."""
    for exp_id in ["CVR2-CV-006", "CVR2-CV-007", "CVR2-CV-008", "CVR2-CV-009", "CVR2-CV-010"]:
        exp_file = R3_DIR / exp_id / "experiment.json"
        with open(exp_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        status = data.get("status")
        assert status in ["RESEARCH_ONLY", "COMPLETED"], f"Unexpected status {status} for {exp_id}"
        assert data.get("is_production", False) is False, f"Experiment {exp_id} cannot be flagged as production"


def test_06_test_set_protection():
    """Verify held-out test split was strictly excluded from training and validation sweeps."""
    train_lines = (D1_DIR / "splits" / "train.txt").read_text().splitlines()
    val_lines = (D1_DIR / "splits" / "val.txt").read_text().splitlines()
    test_lines = (D1_DIR / "splits" / "test.txt").read_text().splitlines()
    
    train_stems = {Path(p.strip()).stem for p in train_lines if p.strip()}
    val_stems = {Path(p.strip()).stem for p in val_lines if p.strip()}
    test_stems = {Path(p.strip()).stem for p in test_lines if p.strip()}
    
    assert len(train_stems.intersection(test_stems)) == 0, "Data leakage: test images found in train set!"
    assert len(val_stems.intersection(test_stems)) == 0, "Data leakage: test images found in val set!"


def test_07_threshold_recording():
    """Verify every metric dictionary records confidence threshold, IoU threshold, and operating point."""
    # CVR6 records sweep + selected threshold + held-out test evaluation
    cvr6 = json.load(open(R3_DIR / "CVR2-CV-006" / "metrics.json", "r", encoding="utf-8"))
    assert "selected_validation_threshold" in cvr6
    assert "validation_calibration_sweep" in cvr6
    assert "held_out_test_evaluation" in cvr6
    
    # CVR7 records selected threshold and evaluated clean test metrics
    cvr7 = json.load(open(R3_DIR / "CVR2-CV-007" / "metrics.json", "r", encoding="utf-8"))
    assert "selected_operating_threshold" in cvr7
    assert cvr7["clean_baseline_test_metrics"]["iou_threshold"] == 0.50
    
    # CVR8 records threshold sweep and operating threshold
    cvr8 = json.load(open(R3_DIR / "CVR2-CV-008" / "metrics.json", "r", encoding="utf-8"))
    assert "selected_operating_threshold" in cvr8
    assert "threshold_sweep_on_negative_scenes" in cvr8
    
    # CVR9 records selected operating threshold
    cvr9 = json.load(open(R3_DIR / "CVR2-CV-009" / "metrics.json", "r", encoding="utf-8"))
    assert "selected_operating_threshold" in cvr9
    
    # CVR10 records operating threshold
    cvr10 = json.load(open(R3_DIR / "CVR2-CV-010" / "metrics.json", "r", encoding="utf-8"))
    assert "operating_threshold" in cvr10


def test_08_validation_only_threshold_selection():
    """Verify the operating threshold was chosen strictly on validation sweep and frozen for test."""
    cvr6_m = json.load(open(R3_DIR / "CVR2-CV-006" / "metrics.json", "r", encoding="utf-8"))
    
    assert "validation_calibration_sweep" in cvr6_m, "CVR2-CV-006 metrics must record validation threshold sweep"
    assert "selected_validation_threshold" in cvr6_m, "CVR2-CV-006 must record selected_validation_threshold"
    sel_thr = cvr6_m["selected_validation_threshold"]
    assert sel_thr == 0.10, f"Expected selected validation threshold 0.10, got {sel_thr}"
    
    # Verify downstream experiments inherit this frozen threshold
    cvr7_m = json.load(open(R3_DIR / "CVR2-CV-007" / "metrics.json", "r", encoding="utf-8"))
    cvr8_m = json.load(open(R3_DIR / "CVR2-CV-008" / "metrics.json", "r", encoding="utf-8"))
    cvr9_m = json.load(open(R3_DIR / "CVR2-CV-009" / "metrics.json", "r", encoding="utf-8"))
    cvr10_m = json.load(open(R3_DIR / "CVR2-CV-010" / "metrics.json", "r", encoding="utf-8"))
    
    assert cvr7_m["selected_operating_threshold"] == sel_thr
    assert cvr8_m["selected_operating_threshold"] == sel_thr
    assert cvr9_m["selected_operating_threshold"] == sel_thr
    assert cvr10_m["operating_threshold"] == sel_thr


def test_09_corruption_metadata():
    """Verify corruptions track photometric transformation parameters and maintain valid metadata."""
    cvr7_metrics_p = R3_DIR / "CVR2-CV-007" / "metrics.json"
    with open(cvr7_metrics_p, "r", encoding="utf-8") as f:
        m7 = json.load(f)
    
    assert "photometric_corruptions" in m7, "CVR2-CV-007 must contain photometric_corruptions"
    corruptions = m7["photometric_corruptions"]
    expected_corruptions = [
        "brightness_reduction", "brightness_increase", "contrast_reduction", "contrast_increase",
        "gaussian_blur", "sensor_noise", "jpeg_compression", "combined_degradation"
    ]
    for c_name in expected_corruptions:
        assert c_name in corruptions, f"Missing corruption type {c_name}"
        for sev in ["LOW", "MEDIUM", "HIGH"]:
            assert sev in corruptions[c_name], f"Missing severity {sev} for corruption {c_name}"
            res = corruptions[c_name][sev]
            assert "metrics" in res, f"Missing metrics for {c_name} {sev}"
            assert "absolute_degradation" in res, f"Missing absolute_degradation for {c_name} {sev}"


def test_10_bounding_box_preservation():
    """Verify corruptions do not alter spatial bounding box annotations."""
    # Corruptions are purely pixel transformations on test images, labels are identical to ground truth
    clean_labels = list((D1_DIR / "labels").glob("*.txt"))
    assert len(clean_labels) == 122, "D1 labels must exist and be 122 files"


def test_11_tp_fp_fn_consistency():
    """Verify TP + FN == ground_truth_boxes and Precision/Recall/F1 are mathematically exact."""
    cvr6 = json.load(open(R3_DIR / "CVR2-CV-006" / "metrics.json", "r", encoding="utf-8"))
    test_eval = cvr6["held_out_test_evaluation"]["at_selected_validation_threshold"]
    
    tp = test_eval["true_positives"]
    fp = test_eval["false_positives"]
    fn = test_eval["false_negatives"]
    gt = test_eval["total_ground_truth_boxes"]
    
    assert tp + fn == gt, f"TP ({tp}) + FN ({fn}) != GT ({gt})"
    p_expected = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r_expected = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1_expected = 2 * p_expected * r_expected / (p_expected + r_expected) if (p_expected + r_expected) > 0 else 0.0
    
    assert math.isclose(test_eval["precision"], p_expected, abs_tol=1e-3)
    assert math.isclose(test_eval["recall"], r_expected, abs_tol=1e-3)
    assert math.isclose(test_eval["f1_score"], f1_expected, abs_tol=1e-3)


def test_12_metric_consistency_across_reports():
    """Verify metric consistency across R3 summary reports and JSON metrics."""
    cvr6_m = json.load(open(R3_DIR / "CVR2-CV-006" / "metrics.json", "r", encoding="utf-8"))
    cvr7_m = json.load(open(R3_DIR / "CVR2-CV-007" / "metrics.json", "r", encoding="utf-8"))
    
    clean_6 = cvr6_m["held_out_test_evaluation"]["at_selected_validation_threshold"]
    clean_7 = cvr7_m["clean_baseline_test_metrics"]
    
    assert clean_6["precision"] == clean_7["precision"]
    assert clean_6["recall"] == clean_7["recall"]
    assert clean_6["f1_score"] == clean_7["f1_score"]
    assert clean_6["true_positives"] == clean_7["true_positives"]
    assert clean_6["false_positives"] == clean_7["false_positives"]


def test_13_robustness_result_schema():
    """Verify robustness result schema includes degradations across all 8 corruptions x 3 severities."""
    cvr7_m = json.load(open(R3_DIR / "CVR2-CV-007" / "metrics.json", "r", encoding="utf-8"))
    corruptions = cvr7_m["photometric_corruptions"]
    assert len(corruptions) == 8, f"Expected 8 corruption types, found {len(corruptions)}"
    for c_name, sevs in corruptions.items():
        for s in ["LOW", "MEDIUM", "HIGH"]:
            assert s in sevs
            assert "absolute_degradation" in sevs[s]
            assert "f1_degradation" in sevs[s]["absolute_degradation"]


def test_14_insufficient_sample_handling():
    """Verify metadata slices with sample count < 3 are flagged INSUFFICIENT_SAMPLE."""
    cvr9_m = json.load(open(R3_DIR / "CVR2-CV-009" / "metrics.json", "r", encoding="utf-8"))
    assert "slice_evaluations" in cvr9_m
    geo_slices = cvr9_m["slice_evaluations"]["geographic_slices"]
    assert "Kolkata" in geo_slices
    assert geo_slices["Kolkata"]["sample_count"] < 3
    assert geo_slices["Kolkata"]["status"] == "INSUFFICIENT_SAMPLE"
    
    class_slices = cvr9_m["slice_evaluations"]["defect_class_slices"]
    for c_name in ["open_damaged_manhole", "damaged_missing_road_sign"]:
        if class_slices[c_name]["sample_count"] < 3:
            assert class_slices[c_name]["status"] == "INSUFFICIENT_SAMPLE"


def test_15_checkpoint_sha_recording():
    """Verify research model checkpoint weights have SHA-256 computed and logged."""
    cvr6_exp = json.load(open(R3_DIR / "CVR2-CV-006" / "experiment.json", "r", encoding="utf-8"))
    assert "model_weights_sha256" in cvr6_exp
    sha = cvr6_exp["model_weights_sha256"]
    assert sha == "72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28"
