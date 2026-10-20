"""
CVKI Computer Vision Subsystem Package.
Module 8: Model-Agnostic CV 2.0 Architecture.
"""

from app.services.cv.base_provider import (
    CVInferenceProvider,
    InferenceRequest,
    ModelDescriptor,
    ModelFramework,
    ModelLifecycleStatus,
    ModelTaskType,
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.cv.model_registry import (
    DuplicateModelError,
    InvalidLifecycleTransitionError,
    InvalidModelHashError,
    InvalidModelReferenceError,
    InvalidModelVersionError,
    ModelEvaluationMetadata,
    ModelIntegrityError,
    ModelNotFoundError,
    ModelRegistry,
    ModelRegistryError,
    SplitEvaluationMetrics,
    model_registry,
    resolve_safe_model_reference,
    validate_model_id_format,
    validate_model_version_format,
    validate_sha256_format,
)

from app.services.cv.providers.m113_yolo_provider import M113YOLOProvider
from app.services.cv.renderer import render_annotated_png_data_url, render_detections
from app.services.cv.runtime import (
    CVInferenceService,
    ModelUnavailableError as CVModelUnavailableError,
    ProviderNotFoundError,
    ProviderResolver,
    cv_runtime_service,
)

__all__ = [
    "CVInferenceProvider",
    "CVInferenceService",
    "CVModelUnavailableError",
    "DuplicateModelError",
    "InferenceRequest",
    "InvalidLifecycleTransitionError",
    "InvalidModelHashError",
    "InvalidModelReferenceError",
    "InvalidModelVersionError",
    "M113YOLOProvider",
    "ModelDescriptor",
    "ModelEvaluationMetadata",
    "ModelFramework",
    "ModelIntegrityError",
    "ModelLifecycleStatus",
    "ModelNotFoundError",
    "ModelRegistry",
    "ModelRegistryError",
    "ModelTaskType",
    "ProviderNotFoundError",
    "ProviderResolver",
    "SplitEvaluationMetrics",
    "StandardBoundingBox",
    "StandardDetection",
    "StandardDetectionResult",
    "cv_runtime_service",
    "model_registry",
    "render_annotated_png_data_url",
    "render_detections",
    "resolve_safe_model_reference",
    "validate_model_id_format",
    "validate_model_version_format",
    "validate_sha256_format",
]

