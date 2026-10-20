"""
CVKI Research v2.x - R0 Experiment Identity System
Ensures deterministic naming, mandatory provenance metadata, and strict uniqueness guarantees.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

from ai.research.status import ResearchStatus


EXPERIMENT_ID_REGEX = re.compile(r"^CVR2-(CV|NLP|DATA|SYS|E)-[0-9]{3,}$")


class DuplicateExperimentIDError(ValueError):
    """Raised when an experiment ID is reused or already registered."""
    pass


class ExperimentIdentity(BaseModel):
    """
    Mandatory metadata schema for every CVKI Research v2.x experiment.
    All fields are required. Unknown values must be explicitly marked 'unknown'.
    """
    experiment_id: str = Field(..., description="Unique deterministic identifier, e.g. CVR2-CV-001")
    research_version: str = Field(default="2.0.0", description="Research lineage release version")
    experiment_type: str = Field(..., description="e.g. baseline, architectural_exploration, ablation")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 creation timestamp",
    )
    status: ResearchStatus = Field(default=ResearchStatus.PLANNED, description="Current experiment lifecycle state")
    owner: str = Field(..., description="Author / researcher responsible")
    description: str = Field(..., description="High-level description of experiment goal")
    hypothesis: str = Field(..., description="Falsifiable hypothesis being tested")
    dataset_id: str = Field(..., description="Registered dataset ID, e.g. D0")
    dataset_version: str = Field(..., description="Dataset version, e.g. 1.0")
    model_id: str = Field(..., description="Registered model ID, e.g. M1.13, R2-YOLO-S-001")
    model_version: str = Field(..., description="Model version string")
    config_id: str = Field(..., description="Associated configuration identifier")
    random_seed: int = Field(default=42, description="Seed for reproducibility")
    hardware: str = Field(default="unknown", description="Execution hardware or 'unknown'")
    software_environment: str = Field(default="unknown", description="Environment spec or 'unknown'")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Observed evaluation metrics")
    artifact_paths: list[str] = Field(default_factory=list, description="List of generated artifacts")
    parent_experiment: Optional[str] = Field(default=None, description="Lineage parent experiment ID or None")
    notes: str = Field(default="", description="Experimental annotations")

    @field_validator("experiment_id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if not EXPERIMENT_ID_REGEX.match(v):
            raise ValueError(
                f"Invalid experiment_id '{v}'. Must match pattern 'CVR2-(CV|NLP|DATA|SYS|E)-<NUMBER:3+ digits>' "
                f"(e.g. 'CVR2-CV-001', 'CVR2-DATA-002')."
            )
        return v


class ExperimentRegistry:
    """Persistent ledger tracking all assigned experiment IDs to prevent reuse."""

    def __init__(self, registry_file: Path | str | None = None):
        if registry_file is None:
            self.registry_file = Path(__file__).resolve().parent / "registry" / "experiment_registry.json"
        else:
            self.registry_file = Path(registry_file)
        self._experiments: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    self._experiments = json.load(f)
            except Exception:
                self._experiments = {}
        else:
            self._experiments = {}

    def _save(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(self._experiments, f, indent=2)

    def is_registered(self, experiment_id: str) -> bool:
        return experiment_id in self._experiments

    def register(self, identity: ExperimentIdentity) -> None:
        """Register a new experiment identity. Raises DuplicateExperimentIDError if already exists."""
        if identity.experiment_id in self._experiments:
            raise DuplicateExperimentIDError(
                f"Experiment ID '{identity.experiment_id}' already registered! Experiment IDs must never be reused."
            )
        self._experiments[identity.experiment_id] = identity.model_dump()
        self._save()

    def get(self, experiment_id: str) -> Optional[dict[str, Any]]:
        return self._experiments.get(experiment_id)

    def update_status(self, experiment_id: str, new_status: ResearchStatus) -> None:
        """Updates experiment status after validating status transition."""
        from ai.research.status import validate_status_transition

        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment '{experiment_id}' not found in registry.")
        
        current = ResearchStatus(self._experiments[experiment_id]["status"])
        validate_status_transition(current, new_status)
        self._experiments[experiment_id]["status"] = new_status.value
        self._save()

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._experiments.values())
