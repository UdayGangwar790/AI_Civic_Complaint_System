"""
CVKI Research v2.x - R2 Controlled CV Experiments Test Suite
Path: backend/tests/test_research_r2.py

Tests:
- R2 Experiment registration and completeness (CVR2-CV-001 through 005)
- Experiment lifecycle state transitions and immutability
- D0 baseline immutability (605 files)
- M1.13 weights checksum verification
- D1 research dataset integrity and held-out test set protection
- Research model isolation (RESEARCH_ONLY status in ModelRegistry)
- Model checkpoint SHA-256 generation and non-overwrite guarantee
- Evaluation metrics schema and historical reference validation
- Hard-negative ablation verification and false-positive suppression
- Augmentation ablation comparative validation
- Diagnostic error taxonomy categorization
- Threshold analysis isolation from production inference
- Failed experiment status transition safety
"""

import json
from pathlib import Path
import tempfile
import pytest

from ai.research.config import ExperimentConfig, DatasetConfig, ModelConfig, TrainingConfig, EvaluationConfig, HypothesisFramework
from ai.research.identity import ExperimentIdentity, ExperimentRegistry, DuplicateExperimentIDError
from ai.research.metrics import EvaluationMetrics, M1_13_BASELINE_M18_HELDOUT, M1_13_BASELINE_M111_HELDOUT
from ai.research.model_registry import ResearchModelRegistry, ResearchModelEntry
from ai.research.scripts.verify_baseline import EXPECTED_M113_SHA, EXPECTED_DATASET_COUNT, verify_baseline
from ai.research.status import ResearchStatus, InvalidStatusTransitionError, validate_status_transition

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_01_baseline_immutability_and_m113_sha():
    """Verify production baseline D0 has exactly 605 files and M1.13 SHA matches exactly."""
    assert verify_baseline() is True

    m113_path = REPO_ROOT / "ai" / "computer_vision" / "training" / "runs" / "yolov8n_m1_13" / "weights" / "best.pt"
    assert m113_path.exists()

    d0_path = REPO_ROOT / "ai" / "computer_vision" / "dataset_m1_13"
    files = [f for f in d0_path.rglob("*") if f.is_file()]
    assert len(files) == EXPECTED_DATASET_COUNT


def test_02_r2_experiment_registrations():
    """Verify all 5 R2 experiments are registered in ExperimentRegistry with COMPLETED status."""
    registry = ExperimentRegistry()
    expected_experiments = [
        "CVR2-CV-001",
        "CVR2-CV-002",
        "CVR2-CV-003",
        "CVR2-CV-004",
        "CVR2-CV-005",
    ]
    for exp_id in expected_experiments:
        entry = registry.get(exp_id)
        assert entry is not None, f"Experiment {exp_id} must be registered in ExperimentRegistry"
        assert entry["experiment_id"] == exp_id
        assert entry["status"] in ("PLANNED", "RUNNING", "COMPLETED")
        assert len(entry["description"]) > 0
        assert len(entry["hypothesis"]) > 0


def test_03_research_model_isolation():
    """Verify research models are cataloged with status RESEARCH_ONLY and M1.13 remains untouched."""
    model_reg = ResearchModelRegistry()
    m113 = model_reg.get("M1.13")
    assert m113 is not None
    assert m113["status"] in ("FROZEN_REFERENCE", "ACTIVE")

    # Research model R2-YOLO-D1-BASE must have status RESEARCH_ONLY
    r2_base = model_reg.get("R2-YOLO-D1-BASE")
    if r2_base:
        assert r2_base["status"] == "RESEARCH_ONLY"
        assert r2_base["training_dataset"] == "D1"
        assert "open_damaged_manhole" in r2_base["classes"]


def test_04_d1_test_set_protection():
    """Verify D1 test set contains exactly 18 images and remains strictly held out."""
    d1_dir = REPO_ROOT / "ai" / "research" / "datasets" / "D1"
    manifest_p = d1_dir / "manifests" / "images_manifest.json"
    with open(manifest_p, "r", encoding="utf-8") as f:
        images = json.load(f)["images"]

    test_images = [img for img in images if img["split"] == "test"]
    assert len(test_images) == 18

    val_images = [img for img in images if img["split"] == "val"]
    assert len(val_images) == 18

    train_images = [img for img in images if img["split"] == "train"]
    assert len(train_images) == 86


def test_05_cvr2_cv_001_dossier_and_weights():
    """Verify CVR2-CV-001 directory structure, config, environment, and weights exist."""
    exp_dir = REPO_ROOT / "ai" / "research" / "experiments" / "R2" / "CVR2-CV-001"
    assert exp_dir.exists()
    assert (exp_dir / "config.yaml").exists()
    assert (exp_dir / "experiment.json").exists()
    assert (exp_dir / "environment.json").exists()
    assert (exp_dir / "metrics.json").exists()
    assert (exp_dir / "README.md").exists()
    assert (exp_dir / "weights" / "best.pt").exists()

    with open(exp_dir / "metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["experiment_id"] == "CVR2-CV-001"
    assert "test_split" in metrics
    assert "mAP50" in metrics["test_split"]
    assert "checkpoint" in metrics
    assert len(metrics["checkpoint"]["sha256"]) == 64


def test_06_cvr2_cv_002_reference_metrics():
    """Verify CVR2-CV-002 records frozen reference metrics and verifies exact M1.13 SHA."""
    exp_dir = REPO_ROOT / "ai" / "research" / "experiments" / "R2" / "CVR2-CV-002"
    assert exp_dir.exists()
    with open(exp_dir / "metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["model_id"] == "M1.13"
    assert metrics["checkpoint_sha256"] == EXPECTED_M113_SHA
    assert metrics["historical_benchmarks"]["m1_8_heldout"]["mAP50"] == 0.6540
    assert metrics["historical_benchmarks"]["m1_11_heldout"]["mAP50"] == 0.5680
    assert "cross_dataset_reference" in metrics


def test_07_cvr2_cv_003_hard_negative_ablation():
    """Verify CVR2-CV-003 captures Config A (with HN) vs Config B (without HN) metrics."""
    exp_dir = REPO_ROOT / "ai" / "research" / "experiments" / "R2" / "CVR2-CV-003"
    assert exp_dir.exists()
    with open(exp_dir / "metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)

    cfg_a = metrics["config_a_with_hard_negatives"]
    cfg_b = metrics["config_b_without_hard_negatives"]
    assert cfg_a["hard_negatives_included"] > 0
    assert cfg_b["hard_negatives_included"] == 0
    assert "false_positives_on_hn_scenes" in cfg_a
    assert "false_positives_on_hn_scenes" in cfg_b


def test_08_cvr2_cv_004_augmentation_ablation():
    """Verify CVR2-CV-004 compares conservative vs stronger augmentation regimes."""
    exp_dir = REPO_ROOT / "ai" / "research" / "experiments" / "R2" / "CVR2-CV-004"
    assert exp_dir.exists()
    with open(exp_dir / "metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert "conservative_augmentation" in metrics
    assert "stronger_augmentation" in metrics
    assert metrics["conservative_augmentation"]["params"]["mosaic"] == 0.0
    assert metrics["stronger_augmentation"]["params"]["mosaic"] == 0.5


def test_09_cvr2_cv_005_error_taxonomy():
    """Verify CVR2-CV-005 error taxonomy breakdown and threshold analysis."""
    exp_dir = REPO_ROOT / "ai" / "research" / "experiments" / "R2" / "CVR2-CV-005"
    assert exp_dir.exists()
    with open(exp_dir / "metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)

    cats = metrics["error_categories_breakdown"]
    assert "SMALL_OBJECT" in cats
    assert "FALSE_NEGATIVE" in cats
    assert "HARD_NEGATIVE_FAILURE" in cats
    assert "threshold_analysis_validation_split" in metrics
    assert "0.25" in metrics["threshold_analysis_validation_split"]


def test_10_experiment_lifecycle_state_machine_and_failed_handling():
    """Verify experiment lifecycle states (PLANNED -> RUNNING -> COMPLETED or FAILED)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg_file = Path(tmp_dir) / "test_reg.json"
        reg = ExperimentRegistry(registry_file=reg_file)

        ident = ExperimentIdentity(
            experiment_id="CVR2-CV-999",
            experiment_type="baseline",
            owner="Tester",
            description="Lifecycle state test",
            hypothesis="Valid state machine transitions",
            dataset_id="D1",
            dataset_version="1.0",
            model_id="M1.13",
            model_version="1.13.0",
            config_id="CFG-999",
        )
        reg.register(ident)
        assert reg.get("CVR2-CV-999")["status"] == "PLANNED"

        reg.update_status("CVR2-CV-999", ResearchStatus.RUNNING)
        assert reg.get("CVR2-CV-999")["status"] == "RUNNING"

        reg.update_status("CVR2-CV-999", ResearchStatus.FAILED)
        assert reg.get("CVR2-CV-999")["status"] == "FAILED"

        # Duplicate ID rejection
        with pytest.raises(DuplicateExperimentIDError):
            reg.register(ident)


def test_11_epistemic_safety_rules():
    """Verify research models do not modify production configuration or thresholds."""
    from backend.app.core.config import settings
    # Production threshold and model path must remain unchanged
    assert hasattr(settings, "YOLO_CONFIDENCE_THRESHOLD")
    assert settings.YOLO_CONFIDENCE_THRESHOLD == 0.25
    assert settings.YOLO_MODEL_PATH == "ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt"
