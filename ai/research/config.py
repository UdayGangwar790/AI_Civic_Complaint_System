"""
CVKI Research v2.x - R0 Experiment Configuration Format
Defines structured YAML/JSON configurations for research experiments.
Strictly requires unknown fields to be recorded as 'unknown'.
"""

import json
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field
import yaml


class DatasetConfig(BaseModel):
    id: str = Field(..., description="Dataset ID, e.g. D0")
    version: str = Field(default="1.0", description="Dataset version")
    train_split: str = Field(default="train", description="Split name used for optimization")
    val_split: str = Field(default="val", description="Split name used for hyperparameter selection")
    test_split: str = Field(default="test", description="Split name reserved for final held-out testing")


class ModelConfig(BaseModel):
    id: str = Field(..., description="Model ID, e.g. M1.13 or R2-YOLO-S-001")
    version: str = Field(default="1.0", description="Model version")
    architecture: str = Field(..., description="e.g. YOLOv8n, DETR-ResNet50")
    input_size: int = Field(default=640, description="Image input dimension")
    confidence_threshold: float = Field(default=0.25, description="Inference threshold")
    iou_threshold: float = Field(default=0.45, description="NMS IoU threshold")


class TrainingConfig(BaseModel):
    seed: int = Field(default=42, description="Random seed")
    epochs: int | str = Field(default="unknown", description="Training epochs or 'unknown'")
    batch_size: int | str = Field(default="unknown", description="Batch size or 'unknown'")
    learning_rate: float | str = Field(default="unknown", description="Learning rate or 'unknown'")
    optimizer: str = Field(default="unknown", description="Optimizer or 'unknown'")
    device: str = Field(default="unknown", description="Training compute device or 'unknown'")


class EvaluationConfig(BaseModel):
    metrics: list[str] = Field(
        default_factory=lambda: ["precision", "recall", "mAP50", "mAP50_95"],
        description="List of target evaluation metrics",
    )
    evaluated_on: str = Field(default="test", description="Target split (must be explicit: val or test)")
    reproducibility_class: str = Field(
        default="REPRODUCIBLE CONFIGURATION",
        description="'REPRODUCIBLE CONFIGURATION' or 'BITWISE REPRODUCIBLE'",
    )


class HypothesisFramework(BaseModel):
    question: str = Field(..., description="Core research question")
    hypothesis: str = Field(..., description="Falsifiable prediction")
    independent_variable: str = Field(..., description="Variable being manipulated")
    dependent_variables: list[str] = Field(..., description="Variables being measured")
    controls: list[str] = Field(..., description="Controlled environmental/experimental factors")
    expected_outcome: str = Field(..., description="Pre-experimental expected outcome")
    actual_outcome: str = Field(default="unknown", description="Observed outcome or 'unknown'")
    conclusion: str = Field(default="unknown", description="Scientific conclusion or 'unknown'")


class ExperimentConfig(BaseModel):
    """Structured configuration document for a CVKI Research v2.x experiment."""
    experiment_id: str = Field(..., description="e.g. CVR2-CV-001")
    experiment_type: str = Field(..., description="baseline, architectural, data_scaling, ablation")
    dataset: DatasetConfig
    model: ModelConfig
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    hypothesis: HypothesisFramework
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_yaml(self) -> str:
        return yaml.dump(self.model_dump(), sort_keys=False)

    def save_yaml(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, sort_keys=False)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), indent=2)

    def save_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2)

    @classmethod
    def from_yaml(cls, path_or_content: Path | str) -> "ExperimentConfig":
        p = Path(path_or_content)
        if p.exists() and p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        else:
            data = yaml.safe_load(str(path_or_content))
        return cls.model_validate(data)

    @classmethod
    def from_json(cls, path_or_content: Path | str) -> "ExperimentConfig":
        p = Path(path_or_content)
        if p.exists() and p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(str(path_or_content))
        return cls.model_validate(data)
