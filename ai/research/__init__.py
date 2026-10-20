"""
CVKI Research v2.x - Core Research Toolkit Package
Provides deterministic infrastructure for scientific civic AI experiments.
"""

from ai.research.checksum import (
    compute_file_sha256,
    generate_dataset_manifest,
    verify_dataset_manifest,
)
from ai.research.comparison import compare_experiments
from ai.research.config import (
    DatasetConfig,
    EvaluationConfig,
    ExperimentConfig,
    HypothesisFramework,
    ModelConfig,
    TrainingConfig,
)
from ai.research.dataset_registry import DatasetEntry, DatasetRegistry, SplitDefinition
from ai.research.environment import capture_environment, get_git_revision
from ai.research.identity import (
    DuplicateExperimentIDError,
    ExperimentIdentity,
    ExperimentRegistry,
)
from ai.research.metrics import (
    EvaluationMetrics,
    M1_13_BASELINE_M111_HELDOUT,
    M1_13_BASELINE_M18_HELDOUT,
)
from ai.research.model_registry import ResearchModelEntry, ResearchModelRegistry
from ai.research.status import (
    InvalidStatusTransitionError,
    ResearchStatus,
    validate_status_transition,
)
from ai.research.storage import ExperimentStorage

__version__ = "2.0.0"

__all__ = [
    "ResearchStatus",
    "InvalidStatusTransitionError",
    "validate_status_transition",
    "ExperimentIdentity",
    "DuplicateExperimentIDError",
    "ExperimentRegistry",
    "ExperimentConfig",
    "DatasetConfig",
    "ModelConfig",
    "TrainingConfig",
    "EvaluationConfig",
    "HypothesisFramework",
    "compute_file_sha256",
    "generate_dataset_manifest",
    "verify_dataset_manifest",
    "capture_environment",
    "get_git_revision",
    "EvaluationMetrics",
    "M1_13_BASELINE_M18_HELDOUT",
    "M1_13_BASELINE_M111_HELDOUT",
    "DatasetEntry",
    "SplitDefinition",
    "DatasetRegistry",
    "ResearchModelEntry",
    "ResearchModelRegistry",
    "ExperimentStorage",
    "compare_experiments",
]
