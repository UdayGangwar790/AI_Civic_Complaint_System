"""
CVKI Research v2.x - R0 Dataset Registry
Manages versioned datasets, split discipline, and protects the frozen D0 baseline.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field

from ai.research.checksum import generate_dataset_manifest


class SplitDefinition(BaseModel):
    train_count: int | str = Field(default="unknown")
    val_count: int | str = Field(default="unknown")
    test_count: int | str = Field(default="unknown")
    split_strategy: str = Field(
        default="held_out_stratified",
        description="Mechanism used to partition splits without data leakage",
    )


class DatasetEntry(BaseModel):
    dataset_id: str = Field(..., description="Unique dataset identifier, e.g. D0, D1, D2")
    dataset_version: str = Field(default="1.0")
    description: str = Field(...)
    source: str = Field(..., description="Data origin or collection lineage")
    license: str = Field(default="Internal Research / CC-BY-NC")
    class_schema: list[str] = Field(..., description="List of recognized defect classes")
    image_count: int = Field(...)
    label_count: int | str = Field(default="unknown")
    split_definition: SplitDefinition = Field(default_factory=SplitDefinition)
    creation_date: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_dataset: Optional[str] = Field(default=None, description="Lineage parent dataset or None")
    checksum_inventory: dict[str, Any] = Field(default_factory=dict, description="Manifest checksum data")
    known_limitations: list[str] = Field(default_factory=list)
    status: str = Field(default="RESEARCH_ACTIVE", description="FROZEN_PRODUCTION_BASELINE or RESEARCH_ACTIVE")


class DatasetRegistry:
    """Registry maintaining catalog of versioned datasets with D0 protection."""

    def __init__(self, registry_file: Path | str | None = None):
        if registry_file is None:
            self.registry_file = Path(__file__).resolve().parent / "registry" / "dataset_registry.json"
        else:
            self.registry_file = Path(registry_file)
        self._datasets: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    self._datasets = json.load(f)
            except Exception:
                self._datasets = {}
        else:
            self._datasets = {}
        
        # Ensure D0 is registered
        if "D0" not in self._datasets:
            self._register_d0_baseline()

    def _register_d0_baseline(self) -> None:
        """Registers the frozen production baseline D0."""
        d0_entry = DatasetEntry(
            dataset_id="D0",
            dataset_version="1.0",
            description="CVKI M1.13 Frozen Production Baseline Dataset",
            source="Curated civic road hazard photographs (M1.8 + M1.13 recovery)",
            license="CVKI Production Proprietary / Open Civic Data",
            class_schema=[
                "garbage", "pothole", "street_light_issue", "water_leakage",
                "fallen_tree", "damaged_signboard", "broken_bench", "open_damaged_manhole",
                "illegal_parking", "sewage_overflow", "encroachment", "unauthorized_posters",
                "loose_cables"
            ],
            image_count=605,
            label_count=605,
            split_definition=SplitDefinition(
                train_count="unknown",
                val_count="unknown",
                test_count="unknown",
                split_strategy="M1.13 verified split",
            ),
            creation_date="2026-10-19T00:00:00Z",
            parent_dataset="ai/computer_vision/dataset_m1_13",
            checksum_inventory={"file_count": 605, "path": "ai/computer_vision/dataset_m1_13"},
            known_limitations=[
                "Daytime lighting bias",
                "Fixed 13-class taxonomy",
                "Limited sample density per minor class"
            ],
            status="FROZEN_PRODUCTION_BASELINE",
        )
        self._datasets["D0"] = d0_entry.model_dump()
        self._save()

    def _save(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(self._datasets, f, indent=2)

    def register(self, entry: DatasetEntry) -> None:
        """Registers a new research dataset. D0 cannot be overwritten."""
        if entry.dataset_id == "D0":
            raise ValueError(
                "D0 is the FROZEN_PRODUCTION_BASELINE and cannot be modified or re-registered. "
                "Research datasets must use D1, D2, D3, etc."
            )
        if entry.dataset_id in self._datasets:
            raise ValueError(f"Dataset '{entry.dataset_id}' already registered. Datasets must be versioned.")
        self._datasets[entry.dataset_id] = entry.model_dump()
        self._save()

    def get(self, dataset_id: str) -> Optional[dict[str, Any]]:
        return self._datasets.get(dataset_id)

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._datasets.values())
