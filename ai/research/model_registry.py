"""
CVKI Research v2.x - R0 Model Registry
Catalogs research model artifacts separately from the production baseline.
Maintains M1.13 as immutable FROZEN_REFERENCE without copying weights.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field


class ResearchModelEntry(BaseModel):
    model_id: str = Field(..., description="Unique model ID, e.g. M1.13, R2-YOLO-S-001, R2-DETR-001")
    model_version: str = Field(default="1.0.0")
    architecture: str = Field(..., description="e.g. YOLOv8n, DETR, RT-DETR, ViT")
    parameter_size: str = Field(default="unknown", description="Number of parameters (e.g. 3.2M) or 'unknown'")
    weights_path: str = Field(..., description="Path to checkpoint weights")
    parent_model: Optional[str] = Field(default=None, description="Lineage parent model ID or None")
    provider: str = Field(default="ultralytics_yolo", description="Standard provider identifier")
    task: str = Field(default="object_detection")
    input_size: int = Field(default=640)
    classes: list[str] = Field(..., description="Taxonomy of supported classes")
    training_dataset: str = Field(default="D0", description="Dataset ID used for training")
    training_config: str = Field(default="unknown")
    checksum: str = Field(..., description="SHA-256 hash of the weight file")
    status: str = Field(default="RESEARCH_ACTIVE", description="FROZEN_REFERENCE, RESEARCH_ACTIVE, RETIRED")
    registered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ResearchModelRegistry:
    """Registry maintaining research model artifacts with frozen M1.13 reference."""

    def __init__(self, registry_file: Path | str | None = None):
        if registry_file is None:
            self.registry_file = Path(__file__).resolve().parent / "registry" / "model_registry.json"
        else:
            self.registry_file = Path(registry_file)
        self._models: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    self._models = json.load(f)
            except Exception:
                self._models = {}
        else:
            self._models = {}

        if "M1.13" not in self._models:
            self._register_m113_reference()

    def _register_m113_reference(self) -> None:
        """Registers production M1.13 as frozen research reference."""
        m113 = ResearchModelEntry(
            model_id="M1.13",
            model_version="1.13.0",
            architecture="YOLOv8n",
            parameter_size="3.2M",
            weights_path="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
            parent_model="M1.8",
            provider="m113_yolo_provider",
            task="object_detection",
            input_size=640,
            classes=[
                "garbage", "pothole", "street_light_issue", "water_leakage",
                "fallen_tree", "damaged_signboard", "broken_bench", "open_damaged_manhole",
                "illegal_parking", "sewage_overflow", "encroachment", "unauthorized_posters",
                "loose_cables"
            ],
            training_dataset="D0",
            training_config="batch=16, imgsz=640, epochs=100",
            checksum="602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3",
            status="FROZEN_REFERENCE",
        )
        self._models["M1.13"] = m113.model_dump()
        self._save()

    def _save(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(self._models, f, indent=2)

    def register(self, entry: ResearchModelEntry) -> None:
        """Registers a new research model. M1.13 cannot be overwritten."""
        if entry.model_id == "M1.13":
            raise ValueError(
                "M1.13 is the FROZEN_REFERENCE model and cannot be modified. "
                "Research models must receive new identities (e.g. R2-YOLO-S-001, R2-DETR-001)."
            )
        if entry.model_id in self._models:
            raise ValueError(f"Model ID '{entry.model_id}' already registered. Use versioning.")
        self._models[entry.model_id] = entry.model_dump()
        self._save()

    def get(self, model_id: str) -> Optional[dict[str, Any]]:
        return self._models.get(model_id)

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._models.values())
