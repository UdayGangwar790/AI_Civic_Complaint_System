"""
CVKI Research v2.x - R0 Infrastructure & Framework Tests
Verifies experiment identity, configuration, registries, metrics, checksums,
lifecycle state machine, and baseline protection.
"""

import json
from pathlib import Path
import tempfile
import pytest

from ai.research import (
    DatasetConfig,
    DatasetEntry,
    DatasetRegistry,
    DuplicateExperimentIDError,
    EvaluationConfig,
    EvaluationMetrics,
    ExperimentConfig,
    ExperimentIdentity,
    ExperimentRegistry,
    ExperimentStorage,
    HypothesisFramework,
    InvalidStatusTransitionError,
    M1_13_BASELINE_M111_HELDOUT,
    M1_13_BASELINE_M18_HELDOUT,
    ModelConfig,
    ResearchModelEntry,
    ResearchModelRegistry,
    ResearchStatus,
    SplitDefinition,
    TrainingConfig,
    capture_environment,
    compare_experiments,
    compute_file_sha256,
    generate_dataset_manifest,
    validate_status_transition,
    verify_dataset_manifest,
)


def test_01_experiment_id_validation_and_uniqueness():
    """Verify experiment ID format enforcement and duplicate rejection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg_file = Path(tmp_dir) / "test_reg.json"
        registry = ExperimentRegistry(registry_file=reg_file)

        # Valid ID
        ident1 = ExperimentIdentity(
            experiment_id="CVR2-CV-001",
            experiment_type="baseline",
            owner="Research Team",
            description="Baseline YOLOv8n check",
            hypothesis="Model meets accuracy thresholds",
            dataset_id="D0",
            dataset_version="1.0",
            model_id="M1.13",
            model_version="1.13.0",
            config_id="CFG-001",
        )
        registry.register(ident1)
        assert registry.is_registered("CVR2-CV-001")

        # Duplicate ID rejection
        with pytest.raises(DuplicateExperimentIDError):
            registry.register(ident1)

        # Malformed ID rejection
        with pytest.raises(ValueError):
            ExperimentIdentity(
                experiment_id="INVALID-ID-123",
                experiment_type="baseline",
                owner="Tester",
                description="desc",
                hypothesis="hyp",
                dataset_id="D0",
                dataset_version="1.0",
                model_id="M1.13",
                model_version="1.0",
                config_id="CFG",
            )


def test_02_config_validation_and_unknown_handling():
    """Verify YAML/JSON serialization and explicit 'unknown' representation."""
    cfg = ExperimentConfig(
        experiment_id="CVR2-DATA-001",
        experiment_type="data_scaling",
        dataset=DatasetConfig(id="D0", version="1.0"),
        model=ModelConfig(id="M1.13", architecture="YOLOv8n"),
        training=TrainingConfig(seed=123, epochs="unknown"),
        evaluation=EvaluationConfig(evaluated_on="test"),
        hypothesis=HypothesisFramework(
            question="What is the effect of data scaling?",
            hypothesis="Scaling data improves generalization.",
            independent_variable="dataset size",
            dependent_variables=["mAP50", "recall"],
            controls=["same seed", "same architecture"],
            expected_outcome="mAP50 increases by >= 0.03",
        ),
    )

    yaml_str = cfg.to_yaml()
    loaded_cfg = ExperimentConfig.from_yaml(yaml_str)
    assert loaded_cfg.experiment_id == "CVR2-DATA-001"
    assert loaded_cfg.training.epochs == "unknown"
    assert loaded_cfg.training.seed == 123


def test_03_dataset_registry_and_d0_baseline_protection():
    """Verify D0 baseline is immutable and protected from modifications."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg_file = Path(tmp_dir) / "datasets.json"
        registry = DatasetRegistry(registry_file=reg_file)

        # Verify D0 auto-registration
        d0 = registry.get("D0")
        assert d0 is not None
        assert d0["status"] == "FROZEN_PRODUCTION_BASELINE"
        assert d0["image_count"] == 605

        # Attempt to overwrite D0 must fail
        with pytest.raises(ValueError, match="D0 is the FROZEN_PRODUCTION_BASELINE"):
            registry.register(
                DatasetEntry(
                    dataset_id="D0",
                    description="tampered",
                    source="bad",
                    class_schema=["pothole"],
                    image_count=100,
                )
            )

        # Register valid research expansion D1
        d1 = DatasetEntry(
            dataset_id="D1",
            dataset_version="1.0",
            description="CVKI Research Expansion Corpus 1",
            source="Synthetic + Augmented",
            class_schema=d0["class_schema"],
            image_count=1200,
            split_definition=SplitDefinition(train_count=900, val_count=150, test_count=150),
        )
        registry.register(d1)
        assert registry.get("D1")["image_count"] == 1200


def test_04_model_registry_and_m113_reference_protection():
    """Verify M1.13 reference is immutable and research models receive new IDs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg_file = Path(tmp_dir) / "models.json"
        registry = ResearchModelRegistry(registry_file=reg_file)

        # Verify M1.13 reference
        m113 = registry.get("M1.13")
        assert m113 is not None
        assert m113["status"] == "FROZEN_REFERENCE"
        assert m113["checksum"] == "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"

        # Attempt to overwrite M1.13 must fail
        with pytest.raises(ValueError, match="M1.13 is the FROZEN_REFERENCE"):
            registry.register(
                ResearchModelEntry(
                    model_id="M1.13",
                    architecture="Custom",
                    weights_path="fake/path",
                    classes=["pothole"],
                    checksum="fake_sha",
                )
            )

        # Register valid research model
        r2_model = ResearchModelEntry(
            model_id="R2-YOLO-S-001",
            architecture="YOLOv8s",
            weights_path="ai/research/weights/yolov8s_exp1.pt",
            classes=m113["classes"],
            checksum="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        )
        registry.register(r2_model)
        assert registry.get("R2-YOLO-S-001")["architecture"] == "YOLOv8s"


def test_05_metric_schema_and_baseline_reference():
    """Verify standard metric schema and frozen baseline values."""
    assert M1_13_BASELINE_M18_HELDOUT.precision == 0.8380
    assert M1_13_BASELINE_M18_HELDOUT.mAP50 == 0.6540
    assert M1_13_BASELINE_M18_HELDOUT.metric_provenance == "BASELINE_REFERENCE"

    assert M1_13_BASELINE_M111_HELDOUT.precision == 0.6500
    assert M1_13_BASELINE_M111_HELDOUT.mAP50 == 0.5680
    assert M1_13_BASELINE_M111_HELDOUT.metric_provenance == "BASELINE_REFERENCE"


def test_06_checksum_and_dataset_manifest():
    """Verify checksum calculation and manifest drift detection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "img1.txt").write_text("image 1 content")
        (tmp_path / "img2.txt").write_text("image 2 content")

        manifest = generate_dataset_manifest(tmp_path)
        assert manifest["file_count"] == 2
        assert len(manifest["files"]) == 2

        # Verify valid manifest
        is_valid, errors = verify_dataset_manifest(tmp_path, manifest)
        assert is_valid is True
        assert len(errors) == 0

        # Tamper: add file
        (tmp_path / "img3.txt").write_text("unexpected file")
        is_valid, errors = verify_dataset_manifest(tmp_path, manifest)
        assert is_valid is False
        assert any("File count mismatch" in e for e in errors)


def test_07_experiment_lifecycle_state_machine():
    """Verify state transitions and invalid state transition rejection."""
    # Valid flow
    validate_status_transition(ResearchStatus.PLANNED, ResearchStatus.RUNNING)
    validate_status_transition(ResearchStatus.RUNNING, ResearchStatus.COMPLETED)
    validate_status_transition(ResearchStatus.COMPLETED, ResearchStatus.ARCHIVED)

    # Valid failure flow
    validate_status_transition(ResearchStatus.RUNNING, ResearchStatus.FAILED)
    validate_status_transition(ResearchStatus.FAILED, ResearchStatus.ARCHIVED)

    # Invalid transitions
    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(ResearchStatus.PLANNED, ResearchStatus.COMPLETED)

    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(ResearchStatus.FAILED, ResearchStatus.COMPLETED)

    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(ResearchStatus.ARCHIVED, ResearchStatus.RUNNING)


def test_08_experiment_storage_and_dossier():
    """Verify dossier creation, hypothesis documentation, and weight references."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = ExperimentStorage(base_experiments_dir=tmp_dir)

        ident = ExperimentIdentity(
            experiment_id="CVR2-SYS-001",
            experiment_type="benchmark",
            owner="Research Eng",
            description="Latency benchmarking",
            hypothesis="Quantization reduces latency without mAP degradation",
            dataset_id="D0",
            dataset_version="1.0",
            model_id="M1.13",
            model_version="1.13.0",
            config_id="CFG-SYS-001",
        )
        cfg = ExperimentConfig(
            experiment_id="CVR2-SYS-001",
            experiment_type="benchmark",
            dataset=DatasetConfig(id="D0"),
            model=ModelConfig(id="M1.13", architecture="YOLOv8n"),
            hypothesis=HypothesisFramework(
                question="Does INT8 quantization preserve mAP50?",
                hypothesis="INT8 quantization maintains mAP50 within 1% of FP32.",
                independent_variable="quantization precision",
                dependent_variables=["latency", "mAP50"],
                controls=["same hardware", "same test set"],
                expected_outcome="Latency drops by 40%, mAP drops < 0.01",
            ),
        )

        exp_dir = storage.initialize_experiment_dossier(ident, cfg)
        assert (exp_dir / "config.yaml").exists()
        assert (exp_dir / "experiment.json").exists()
        assert (exp_dir / "environment.json").exists()
        assert (exp_dir / "README.md").exists()

        # Finalize
        storage.finalize_experiment(
            experiment_id="CVR2-SYS-001",
            metrics=EvaluationMetrics(
                precision=0.8350,
                recall=0.6090,
                mAP50=0.6510,
                inference_latency_ms=4.2,
            ),
            actual_outcome="Latency reduced from 7.1ms to 4.2ms (-40.8%); mAP50 fell by 0.003.",
            conclusion="Hypothesis confirmed: quantization delivers major speedup with negligible mAP loss.",
            weight_path="weights/quantized.engine",
            weight_sha256="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        )

        assert (exp_dir / "metrics.json").exists()
        with open(exp_dir / "experiment.json") as f:
            data = json.load(f)
            assert data["status"] == "COMPLETED"
            assert any("weight_ref:" in a for a in data["artifact_paths"])


def test_09_experiment_comparison():
    """Verify objective comparison table generation without automated winner bias."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = ExperimentStorage(base_experiments_dir=tmp_dir)

        # Experiment A
        id_a = ExperimentIdentity(
            experiment_id="CVR2-E-001",
            experiment_type="baseline",
            owner="A",
            description="Run A",
            hypothesis="H A",
            dataset_id="D0",
            dataset_version="1.0",
            model_id="M1.13",
            model_version="1.0",
            config_id="C-A",
        )
        cfg_a = ExperimentConfig(
            experiment_id="CVR2-E-001",
            experiment_type="baseline",
            dataset=DatasetConfig(id="D0"),
            model=ModelConfig(id="M1.13", architecture="YOLOv8n"),
            hypothesis=HypothesisFramework(
                question="Q", hypothesis="H", independent_variable="V",
                dependent_variables=["M"], controls=["C"], expected_outcome="E",
            ),
        )
        storage.initialize_experiment_dossier(id_a, cfg_a)
        storage.finalize_experiment(
            "CVR2-E-001",
            EvaluationMetrics(precision=0.83, recall=0.61, mAP50=0.65, inference_latency_ms=7.0),
            "Outcome A", "Conclusion A",
        )

        # Experiment B
        id_b = ExperimentIdentity(
            experiment_id="CVR2-E-002",
            experiment_type="test",
            owner="B",
            description="Run B",
            hypothesis="H B",
            dataset_id="D0",
            dataset_version="1.0",
            model_id="R2-TEST",
            model_version="1.0",
            config_id="C-B",
        )
        cfg_b = ExperimentConfig(
            experiment_id="CVR2-E-002",
            experiment_type="test",
            dataset=DatasetConfig(id="D0"),
            model=ModelConfig(id="R2-TEST", architecture="CustomNet"),
            hypothesis=HypothesisFramework(
                question="Q", hypothesis="H", independent_variable="V",
                dependent_variables=["M"], controls=["C"], expected_outcome="E",
            ),
        )
        storage.initialize_experiment_dossier(id_b, cfg_b)
        storage.finalize_experiment(
            "CVR2-E-002",
            EvaluationMetrics(precision=0.86, recall=0.65, mAP50=0.68, inference_latency_ms=9.5),
            "Outcome B", "Conclusion B",
        )

        res = compare_experiments(["CVR2-E-001", "CVR2-E-002"], base_dir=tmp_dir)
        assert res["experiments_count"] == 2
        assert "CVR2-E-001" in res["markdown_table"]
        assert "CVR2-E-002" in res["markdown_table"]
        assert "Winner" not in res["markdown_table"]  # No biased automated winner declaration


def test_10_environment_capture_truthfulness():
    """Verify environment capture reports true system data and no fabricated git data."""
    env = capture_environment()
    assert "python_version" in env
    assert "os" in env
    assert "libraries" in env
    assert "git_commit" in env
    assert env["libraries"]["pydantic"] != "unknown"
