"""
CVKI - Civic Vision & Knowledge Intelligence
Module 8.3: Computer Vision Model Registry & Lifecycle Management

Manages model identity, metadata catalogs, cryptographic SHA-256 verification,
and deterministic lifecycle transitions. Ensures future vision models can be
cataloged, evaluated, promoted, and audited without altering production serving.
"""

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
from threading import Lock
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import get_project_root
from app.services.cv.base_provider import (
    ModelDescriptor,
    ModelFramework,
    ModelLifecycleStatus,
    ModelTaskType,
)

logger = logging.getLogger("cvki.services.cv.model_registry")


# ==============================================================================
# Model Registry Exceptions
# ==============================================================================

class ModelRegistryError(Exception):
    """Base exception for all model registry operations."""
    pass


class ModelNotFoundError(ModelRegistryError):
    """Raised when a requested model_id does not exist in the registry."""
    pass


class DuplicateModelError(ModelRegistryError):
    """Raised when attempting to register a model with an existing identity."""
    pass


class InvalidLifecycleTransitionError(ModelRegistryError):
    """Raised when attempting an illegal model lifecycle state transition."""
    pass


class InvalidModelReferenceError(ModelRegistryError):
    """Raised when a model reference is malformed or violates path safety boundaries."""
    pass


class InvalidModelVersionError(ModelRegistryError):
    """Raised when a model version string fails formatting standards."""
    pass


class InvalidModelHashError(ModelRegistryError):
    """Raised when a model SHA-256 hash fails formatting standards."""
    pass


class ModelIntegrityError(ModelRegistryError):
    """Raised when physical model file hash does not match registered checksum."""
    pass


# ==============================================================================
# Evaluation Metadata Contracts
# ==============================================================================

class SplitEvaluationMetrics(BaseModel):
    """
    Standard evaluation metrics for a specific dataset split (validation or held-out test).
    All metric values are optional floats in [0.0, 1.0] to prevent fabricating missing data.
    """
    split_name: str = Field(description="Name or identifier of the evaluated dataset split")
    precision: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Overall Precision")
    recall: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Overall Recall")
    map50: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="mAP at IoU=0.50")
    map50_95: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="mAP at IoU=0.50:0.95")
    per_class_metrics: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Per-class metric breakdowns (e.g. precision, recall, mAP50 by class name)",
    )


class ModelEvaluationMetadata(BaseModel):
    """
    Comprehensive evaluation benchmark metadata and experiment provenance.
    Preserves exact metrics from offline training runs without guessing or inventing data.
    """
    experiment_id: Optional[str] = Field(default=None, description="Training experiment identifier")
    dataset_version: Optional[str] = Field(default=None, description="Dataset version used for training/eval")
    evaluation_date: Optional[str] = Field(default=None, description="Date evaluation was completed (YYYY-MM-DD)")
    evaluation_timestamp: Optional[datetime] = Field(default=None, description="UTC timestamp of evaluation")
    duration: Optional[str] = Field(default=None, description="Wall clock training duration")
    completed_epochs: Optional[int] = Field(default=None, ge=0, description="Total completed training epochs")
    best_epoch: Optional[int] = Field(default=None, ge=0, description="Epoch that produced the best checkpoint")
    best_fitness: Optional[float] = Field(default=None, description="Best fitness metric score")
    validation_metrics: Optional[SplitEvaluationMetrics] = Field(
        default=None,
        description="Metrics on the primary validation split",
    )
    held_out_splits: dict[str, SplitEvaluationMetrics] = Field(
        default_factory=dict,
        description="Metrics across held-out benchmark splits (e.g. m1_8_test, improved_test)",
    )
    evaluation_notes: Optional[str] = Field(default=None, description="Contextual notes on experimental conditions")


# ==============================================================================
# Model Reference & Hash Validation
# ==============================================================================

_SHA256_REGEX = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID_REGEX = re.compile(r"^[a-zA-Z0-9._-]+$")
_VERSION_REGEX = re.compile(r"^[0-9]+(\.[0-9]+)*(-[a-zA-Z0-9._]+)?$")


def validate_sha256_format(hash_str: str) -> str:
    """Validates that a string is exactly a 64-character hexadecimal SHA-256 hash."""
    if not isinstance(hash_str, str):
        raise InvalidModelHashError("SHA-256 hash must be a string.")
    clean = hash_str.strip().lower()
    if not _SHA256_REGEX.fullmatch(clean):
        raise InvalidModelHashError(
            f"Invalid SHA-256 hash format. Must be 64 hexadecimal characters. Got: '{hash_str}'"
        )
    return clean


def validate_model_id_format(model_id: str) -> str:
    """Validates that a model ID conforms to alphanumeric safe naming standards."""
    if not isinstance(model_id, str) or not model_id.strip():
        raise ModelRegistryError("Model ID cannot be empty.")
    clean = model_id.strip()
    if not _MODEL_ID_REGEX.fullmatch(clean):
        raise ModelRegistryError(
            f"Invalid model ID format: '{model_id}'. Must be alphanumeric with '.', '_', or '-'."
        )
    return clean


def validate_model_version_format(version_str: str) -> str:
    """Validates that a model version conforms to structured numbering conventions."""
    if not isinstance(version_str, str) or not version_str.strip():
        raise InvalidModelVersionError("Model version cannot be empty.")
    clean = version_str.strip()
    if not _VERSION_REGEX.fullmatch(clean):
        raise InvalidModelVersionError(
            f"Invalid model version format: '{version_str}'. Must follow numbered convention (e.g. '1.13', '2.0.0')."
        )
    return clean


def resolve_safe_model_reference(reference: str) -> Path:
    """
    Validates that an internal model reference points safely within project boundaries
    and does not contain path traversal attempts ('..', null bytes, non-standard drives).
    """
    if not isinstance(reference, str) or not reference.strip():
        raise InvalidModelReferenceError("Model reference cannot be empty.")

    clean_ref = reference.strip()

    # Reject obvious path traversal patterns
    if ".." in clean_ref or "\0" in clean_ref:
        raise InvalidModelReferenceError(
            f"Security violation: Model reference '{reference}' contains disallowed traversal tokens."
        )

    project_root = get_project_root().resolve()
    candidate_path = Path(clean_ref)

    if candidate_path.is_absolute():
        resolved_path = candidate_path.resolve()
    else:
        resolved_path = (project_root / candidate_path).resolve()

    try:
        resolved_path.relative_to(project_root)
    except ValueError:
        raise InvalidModelReferenceError(
            f"Security violation: Model reference '{reference}' resolves outside project root."
        )

    return resolved_path


# ==============================================================================
# Model Lifecycle State Machine
# ==============================================================================

LEGAL_TRANSITIONS: dict[ModelLifecycleStatus, set[ModelLifecycleStatus]] = {
    ModelLifecycleStatus.REGISTERED: {
        ModelLifecycleStatus.VALIDATING,
        ModelLifecycleStatus.DISABLED,
    },
    ModelLifecycleStatus.VALIDATING: {
        ModelLifecycleStatus.EVALUATED,
        ModelLifecycleStatus.DISABLED,
    },
    ModelLifecycleStatus.EVALUATED: {
        ModelLifecycleStatus.ACTIVE,
        ModelLifecycleStatus.DISABLED,
    },
    ModelLifecycleStatus.ACTIVE: {
        ModelLifecycleStatus.RETIRED,
        ModelLifecycleStatus.DISABLED,
    },
    ModelLifecycleStatus.RETIRED: {
        ModelLifecycleStatus.ACTIVE,    # Explicit rollback / re-activation
        ModelLifecycleStatus.DISABLED,
    },
    ModelLifecycleStatus.DISABLED: set(), # Terminal state
}

# Compatibility mapping for legacy status aliases
_STATUS_NORMALIZATION_MAP: dict[ModelLifecycleStatus, ModelLifecycleStatus] = {
    ModelLifecycleStatus.CANDIDATE: ModelLifecycleStatus.REGISTERED,
    ModelLifecycleStatus.FROZEN_BASELINE: ModelLifecycleStatus.ACTIVE,
    ModelLifecycleStatus.ACTIVE_PRODUCTION: ModelLifecycleStatus.ACTIVE,
}


def normalize_lifecycle_status(status: ModelLifecycleStatus | str) -> ModelLifecycleStatus:
    """Normalizes string status and compatibility aliases into canonical lifecycle states."""
    if isinstance(status, str):
        try:
            status = ModelLifecycleStatus(status.lower())
        except ValueError:
            raise ModelRegistryError(f"Unknown lifecycle status string: '{status}'")
    return _STATUS_NORMALIZATION_MAP.get(status, status)


# ==============================================================================
# M1.13 Production Baseline Definition (Frozen Seed)
# ==============================================================================

M1_13_BASELINE_ID = "m1.13-yolov8n"
M1_13_SHA256 = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
M1_13_REFERENCE = "ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt"

M1_13_BASELINE_DESCRIPTOR = ModelDescriptor(
    model_id=M1_13_BASELINE_ID,
    model_name="CVKI YOLOv8n Baseline",
    model_version="1.13",
    provider_id="yolov8_provider",
    framework=ModelFramework.ULTRALYTICS_YOLO,
    task_type=ModelTaskType.OBJECT_DETECTION,
    sha256_hash=M1_13_SHA256,
    model_reference=M1_13_REFERENCE,
    weights_path=M1_13_REFERENCE,
    supported_classes={
        0: "open_damaged_manhole",
        1: "damaged_missing_road_sign",
        2: "road_waterlogging",
    },
    default_confidence_threshold=0.25,
    confidence_threshold_default=0.25,
    lifecycle_status=ModelLifecycleStatus.ACTIVE,
    created_at=datetime(2026, 9, 13, 0, 0, 0, tzinfo=timezone.utc),
    activated_at=datetime(2026, 9, 13, 0, 0, 0, tzinfo=timezone.utc),
    evaluation_metadata=ModelEvaluationMetadata(
        experiment_id="yolov8n_m1_13",
        dataset_version="dataset_m1_13",
        evaluation_date="2026-09-13",
        duration="4:36:08",
        completed_epochs=81,
        best_epoch=61,
        best_fitness=0.439976,
        validation_metrics=SplitEvaluationMetrics(
            split_name="val_m1_13",
            precision=0.726,
            recall=0.590,
            map50=0.643,
            map50_95=0.417,
        ),
        held_out_splits={
            "m1_8_test": SplitEvaluationMetrics(
                split_name="m1_8_held_out_test",
                precision=0.838,
                recall=0.612,
                map50=0.654,
                map50_95=0.487,
                per_class_metrics={
                    "open_damaged_manhole": {"P": 0.795, "R": 0.729, "mAP50": 0.776, "mAP50_95": 0.554},
                    "damaged_missing_road_sign": {"P": 0.973, "R": 0.800, "mAP50": 0.833, "mAP50_95": 0.687},
                    "road_waterlogging": {"P": 0.748, "R": 0.308, "mAP50": 0.352, "mAP50_95": 0.221},
                },
            ),
            "improved_test": SplitEvaluationMetrics(
                split_name="m1_11_improved_held_out_test",
                precision=0.650,
                recall=0.570,
                map50=0.568,
                map50_95=0.423,
                per_class_metrics={
                    "open_damaged_manhole": {"P": 0.784, "R": 0.750, "mAP50": 0.776, "mAP50_95": 0.554},
                    "damaged_missing_road_sign": {"P": 0.953, "R": 0.800, "mAP50": 0.843, "mAP50_95": 0.690},
                    "road_waterlogging": {"P": 0.213, "R": 0.160, "mAP50": 0.0841, "mAP50_95": 0.0251},
                },
            ),
        },
        evaluation_notes="Controlled YOLOv8n correction experiment; restored mosaic=1.0 and scale=0.5 with gravity preservation.",
    ),
    metadata={"is_frozen_baseline": True, "curated_images": 300},
)


# ==============================================================================
# Model Registry Service
# ==============================================================================

class ModelRegistry:
    """
    Thread-safe registry managing computer vision model identity, capabilities,
    cryptographic SHA-256 integrity, and lifecycle states.
    """

    def __init__(self):
        self._models: dict[str, ModelDescriptor] = {}
        self._lock = Lock()
        self._initialize_seed_catalog()

    def _initialize_seed_catalog(self) -> None:
        """Seeds the registry with the frozen M1.13 baseline checkpoint."""
        seed_copy = M1_13_BASELINE_DESCRIPTOR.model_copy(deep=True)
        self._models[seed_copy.model_id] = seed_copy

    def reset(self) -> None:
        """Resets registry to clean baseline state containing only M1.13 (for testing)."""
        with self._lock:
            self._models.clear()
            self._initialize_seed_catalog()

    def register_model(self, descriptor: ModelDescriptor) -> ModelDescriptor:
        """
        Registers a new model descriptor in the registry.

        Validation rules:
        - Unique model_id
        - Valid model_version format
        - Valid SHA-256 hash format (if provided)
        - Safe internal model_reference path
        - Enforces initial lifecycle state as REGISTERED (cannot register directly as ACTIVE).
        """
        validate_model_id_format(descriptor.model_id)
        validate_model_version_format(descriptor.model_version)

        if descriptor.sha256_hash:
            descriptor.sha256_hash = validate_sha256_format(descriptor.sha256_hash)

        if descriptor.model_reference:
            resolve_safe_model_reference(descriptor.model_reference)

        with self._lock:
            if descriptor.model_id in self._models:
                raise DuplicateModelError(
                    f"Model with ID '{descriptor.model_id}' is already registered."
                )

            # Defensive copy and safe lifecycle enforcement
            desc = descriptor.model_copy(deep=True)
            if not desc.created_at:
                desc.created_at = datetime.now(timezone.utc)

            # Registration never automatically activates a model
            desc.lifecycle_status = ModelLifecycleStatus.REGISTERED
            desc.activated_at = None
            desc.retired_at = None

            self._models[desc.model_id] = desc
            logger.info("Registered model in CV registry: %s (version=%s)", desc.model_id, desc.model_version)
            return desc.model_copy(deep=True)

    def get_model(self, model_id: str) -> ModelDescriptor:
        """Retrieves a registered model descriptor by model_id."""
        with self._lock:
            model = self._models.get(model_id)
            if not model:
                raise ModelNotFoundError(f"Model '{model_id}' not found in registry.")
            return model.model_copy(deep=True)

    def list_models(
        self,
        status: Optional[ModelLifecycleStatus | str] = None,
    ) -> list[ModelDescriptor]:
        """Lists all registered models, optionally filtered by canonical lifecycle status."""
        normalized_status = normalize_lifecycle_status(status) if status is not None else None
        with self._lock:
            results = []
            for m in self._models.values():
                m_status = normalize_lifecycle_status(m.lifecycle_status)
                if normalized_status is None or m_status == normalized_status:
                    results.append(m.model_copy(deep=True))
            return results

    def get_active_model(self) -> Optional[ModelDescriptor]:
        """Returns the currently active production model descriptor, if any."""
        with self._lock:
            for m in self._models.values():
                if normalize_lifecycle_status(m.lifecycle_status) == ModelLifecycleStatus.ACTIVE:
                    return m.model_copy(deep=True)
            return None

    def transition_model_status(
        self,
        model_id: str,
        target_status: ModelLifecycleStatus | str,
        reason: Optional[str] = None,
    ) -> ModelDescriptor:
        """
        Executes a deterministic lifecycle state transition for a registered model.

        Transition Rules:
        - Must be a legal transition according to LEGAL_TRANSITIONS
        - Cannot jump states (e.g. REGISTERED directly to ACTIVE)
        - Cannot transition out of terminal state DISABLED
        - If transitioning to ACTIVE:
          - Preceding state must be EVALUATED (or RETIRED for rollback)
          - Automatically retires any previously active model
          - Sets activated_at timestamp
        - If transitioning to RETIRED: sets retired_at timestamp
        """
        target = normalize_lifecycle_status(target_status)

        with self._lock:
            model = self._models.get(model_id)
            if not model:
                raise ModelNotFoundError(f"Model '{model_id}' not found in registry.")

            current = normalize_lifecycle_status(model.lifecycle_status)

            if current == target:
                return model.model_copy(deep=True)

            allowed = LEGAL_TRANSITIONS.get(current, set())
            if target not in allowed:
                raise InvalidLifecycleTransitionError(
                    f"Invalid lifecycle transition for model '{model_id}': "
                    f"cannot transition from '{current.value}' to '{target.value}'. "
                    f"Allowed transitions from '{current.value}': {[s.value for s in allowed]}."
                )

            now = datetime.now(timezone.utc)

            # If promoting to ACTIVE, retire any currently active model
            if target == ModelLifecycleStatus.ACTIVE:
                for other_id, other_model in self._models.items():
                    if (
                        other_id != model_id
                        and normalize_lifecycle_status(other_model.lifecycle_status) == ModelLifecycleStatus.ACTIVE
                    ):
                        other_model.lifecycle_status = ModelLifecycleStatus.RETIRED
                        other_model.retired_at = now
                        logger.info("Automatically retired previously active model: %s", other_id)

                model.activated_at = now

            if target == ModelLifecycleStatus.RETIRED:
                model.retired_at = now

            model.lifecycle_status = target
            if reason:
                model.metadata["transition_reason"] = reason

            logger.info("Model '%s' transitioned: %s -> %s", model_id, current.value, target.value)
            return model.model_copy(deep=True)

    def activate_model(self, model_id: str, reason: Optional[str] = None) -> ModelDescriptor:
        """Explicitly promotes an EVALUATED or RETIRED model to ACTIVE."""
        return self.transition_model_status(model_id, ModelLifecycleStatus.ACTIVE, reason=reason)

    def retire_model(self, model_id: str, reason: Optional[str] = None) -> ModelDescriptor:
        """Explicitly retires an ACTIVE model."""
        return self.transition_model_status(model_id, ModelLifecycleStatus.RETIRED, reason=reason)

    def disable_model(self, model_id: str, reason: Optional[str] = None) -> ModelDescriptor:
        """Explicitly disables a model administratively."""
        return self.transition_model_status(model_id, ModelLifecycleStatus.DISABLED, reason=reason)

    def verify_model_integrity(self, model_id: str) -> tuple[bool, str]:
        """
        Cryptographically verifies the physical model file against its registered SHA-256 hash.
        Does NOT modify the file.
        """
        model = self.get_model(model_id)
        if not model.sha256_hash:
            return False, f"Model '{model_id}' does not have a registered SHA-256 hash."

        if not model.model_reference:
            return False, f"Model '{model_id}' does not have a registered model_reference artifact path."

        try:
            resolved_path = resolve_safe_model_reference(model.model_reference)
        except InvalidModelReferenceError as exc:
            return False, f"Path security violation: {exc}"

        if not resolved_path.exists() or not resolved_path.is_file():
            return False, f"Model weights artifact not found at resolved path: {resolved_path}"

        # Stream file in 64 KB chunks to verify checksum without memory bloat
        hasher = hashlib.sha256()
        try:
            with open(resolved_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            computed_hash = hasher.hexdigest().lower()
        except Exception as exc:
            return False, f"Error reading model artifact: {exc}"

        expected_hash = model.sha256_hash.lower()
        if computed_hash != expected_hash:
            return False, (
                f"Checksum mismatch for '{model_id}': expected '{expected_hash}', "
                f"computed '{computed_hash}'."
            )

        return True, "Cryptographic SHA-256 integrity verified."


# Singleton instance
model_registry = ModelRegistry()
