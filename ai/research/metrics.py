"""
CVKI Research v2.x - R0 Metric Schema & Canonical Baseline Reference
Standardizes evaluation metrics and records frozen historical baselines.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class EvaluationMetrics(BaseModel):
    """
    Standard schema for CVKI Research v2.x experimental metrics.
    Fields are optional so experiments only report metrics they legitimately produce.
    """
    # Primary detection metrics
    precision: Optional[float] = Field(default=None, description="Global precision [0.0 - 1.0]")
    recall: Optional[float] = Field(default=None, description="Global recall [0.0 - 1.0]")
    mAP50: Optional[float] = Field(default=None, description="Mean Average Precision at IoU 0.50")
    mAP50_95: Optional[float] = Field(default=None, description="Mean Average Precision at IoU 0.50:0.95")
    f1: Optional[float] = Field(default=None, description="Harmonic mean of precision and recall")

    # Per-class breakdowns (class_name -> metric)
    per_class_precision: Optional[dict[str, float]] = Field(default=None)
    per_class_recall: Optional[dict[str, float]] = Field(default=None)
    per_class_mAP50: Optional[dict[str, float]] = Field(default=None)
    per_class_mAP50_95: Optional[dict[str, float]] = Field(default=None)

    # Runtime & Efficiency
    inference_latency_ms: Optional[float] = Field(default=None, description="Average single-image latency (ms)")
    throughput_fps: Optional[float] = Field(default=None, description="Frames processed per second")
    gpu_memory_mb: Optional[float] = Field(default=None, description="Peak GPU VRAM consumed (MB)")
    cpu_memory_mb: Optional[float] = Field(default=None, description="Peak host RAM consumed (MB)")

    # Advanced / Epistemic Metrics (Future Research)
    false_positive_rate: Optional[float] = Field(default=None)
    false_negative_rate: Optional[float] = Field(default=None)
    confusion_matrix: Optional[list[list[int]]] = Field(default=None)
    calibration_error: Optional[float] = Field(default=None, description="Expected Calibration Error (ECE)")
    robustness_score: Optional[float] = Field(default=None, description="Perturbation robustness metric")

    # Evaluation Metadata
    evaluated_on: str = Field(default="test", description="Target split: val or test")
    metric_provenance: str = Field(
        default="EXPERIMENTAL_EVALUATION",
        description="'BASELINE_REFERENCE', 'HISTORICAL_EVALUATION', or 'EXPERIMENTAL_EVALUATION'",
    )
    notes: Optional[str] = Field(default=None)


# Canonical Frozen Baseline Record (M1.13)
# These represent historical evaluated results, stored explicitly as BASELINE_REFERENCE.
M1_13_BASELINE_M18_HELDOUT = EvaluationMetrics(
    precision=0.8380,
    recall=0.6120,
    mAP50=0.6540,
    mAP50_95=0.4870,
    f1=round(2 * (0.8380 * 0.6120) / (0.8380 + 0.6120), 4),
    evaluated_on="M1.8 held-out test split",
    metric_provenance="BASELINE_REFERENCE",
    notes="Historical evaluated baseline on initial benchmark split. Not a universal guarantee.",
)

M1_13_BASELINE_M111_HELDOUT = EvaluationMetrics(
    precision=0.6500,
    recall=0.5700,
    mAP50=0.5680,
    mAP50_95=0.4230,
    f1=round(2 * (0.6500 * 0.5700) / (0.6500 + 0.5700), 4),
    evaluated_on="M1.11 held-out test split",
    metric_provenance="BASELINE_REFERENCE",
    notes="Historical evaluated baseline on dual held-out test split with higher background clutter.",
)
