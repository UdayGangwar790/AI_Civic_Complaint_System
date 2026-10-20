"""
CVKI - Civic Vision & Knowledge Intelligence
Module 8.2: Computer Vision Provider Abstraction SPI

Defines the framework-agnostic Computer Vision Provider SPI and standardized
data contracts. Enables clean decoupling between model execution engines
(YOLOv8, ViT, DETR, ONNX, future video/temporal models) and the downstream
CVKI platform (Provenance, Knowledge Graph, Government Adapters, Case Workflows).

This file contains NO framework-specific dependencies (e.g. ultralytics, torch).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelTaskType(str, Enum):
    """Supported computer vision operational task categories."""
    OBJECT_DETECTION = "object_detection"
    INSTANCE_SEGMENTATION = "instance_segmentation"
    VIDEO_TRACKING = "video_tracking"
    TEMPORAL_SEQUENCE = "temporal_sequence"


class ModelFramework(str, Enum):
    """Runtime execution framework powering the provider."""
    ULTRALYTICS_YOLO = "ultralytics_yolo"
    ONNX_RUNTIME = "onnx_runtime"
    TORCHSCRIPT = "torchscript"
    HUGGINGFACE_TRANSFORMER = "huggingface_transformer"
    MOCK = "mock"
    CUSTOM = "custom"


class ModelLifecycleStatus(str, Enum):
    """Deployment lifecycle status of a model descriptor."""
    REGISTERED = "registered"
    VALIDATING = "validating"
    EVALUATED = "evaluated"
    ACTIVE = "active"
    RETIRED = "retired"
    DISABLED = "disabled"
    # Backwards-compatible aliases for M8.2 SPI
    FROZEN_BASELINE = "frozen_baseline"
    ACTIVE_PRODUCTION = "active_production"
    CANDIDATE = "candidate"


class ModelDescriptor(BaseModel):
    """
    Lightweight metadata descriptor identifying a computer vision model.
    Framework-agnostic data contract specifying model identity, task, and capabilities.
    """
    model_id: str = Field(description="Unique identifier for the model instance")
    model_name: str = Field(description="Human-readable model name or architecture family")
    model_version: str = Field(description="Version string identifying model artifact release")
    provider_id: Optional[str] = Field(default=None, description="Identifier of the provider implementation")
    framework: ModelFramework | str = Field(default=ModelFramework.CUSTOM)
    task_type: ModelTaskType | str = Field(default=ModelTaskType.OBJECT_DETECTION)
    sha256_hash: Optional[str] = Field(default=None, description="Cryptographic SHA-256 of the model weights")
    model_reference: Optional[str] = Field(default=None, description="Internal controlled reference or storage key for weights")
    weights_path: Optional[str] = Field(default=None, description="Filesystem or storage reference to weights (alias)")
    supported_classes: dict[int, str] = Field(default_factory=dict, description="Class ID to class name mapping")
    confidence_threshold_default: float = Field(default=0.25, ge=0.0, le=1.0)
    default_confidence_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    lifecycle_status: ModelLifecycleStatus | str = Field(default=ModelLifecycleStatus.REGISTERED)
    created_at: Optional[datetime] = Field(default=None)
    activated_at: Optional[datetime] = Field(default=None, description="Timestamp when model was promoted to active")
    retired_at: Optional[datetime] = Field(default=None, description="Timestamp when model was retired")
    evaluation_metadata: Optional[Any] = Field(default=None, description="Evaluation benchmark metadata")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible model card metadata")

    @model_validator(mode="after")
    def sync_aliases(self) -> "ModelDescriptor":
        if self.model_reference is None and self.weights_path is not None:
            self.model_reference = self.weights_path
        elif self.weights_path is None and self.model_reference is not None:
            self.weights_path = self.model_reference

        if self.default_confidence_threshold is not None:
            self.confidence_threshold_default = self.default_confidence_threshold
        else:
            self.default_confidence_threshold = self.confidence_threshold_default
        return self


class StandardBoundingBox(BaseModel):
    """
    Model-independent bounding box representation.
    Supports both pixel coordinates in native image space and optional normalized coordinates.
    """
    x1: int = Field(description="Top-left x in original image pixels")
    y1: int = Field(description="Top-left y in original image pixels")
    x2: int = Field(description="Bottom-right x in original image pixels")
    y2: int = Field(description="Bottom-right y in original image pixels")
    norm_x1: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    norm_y1: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    norm_x2: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    norm_y2: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_coordinates(self) -> "StandardBoundingBox":
        if self.x1 < 0 or self.y1 < 0 or self.x2 < 0 or self.y2 < 0:
            raise ValueError("Bounding box pixel coordinates cannot be negative.")
        if self.x1 > self.x2:
            raise ValueError(f"Invalid bounding box: x1 ({self.x1}) cannot exceed x2 ({self.x2}).")
        if self.y1 > self.y2:
            raise ValueError(f"Invalid bounding box: y1 ({self.y1}) cannot exceed y2 ({self.y2}).")
        if self.norm_x1 is not None and self.norm_x2 is not None and self.norm_x1 > self.norm_x2:
            raise ValueError(f"Invalid bounding box: norm_x1 ({self.norm_x1}) cannot exceed norm_x2 ({self.norm_x2}).")
        if self.norm_y1 is not None and self.norm_y2 is not None and self.norm_y1 > self.norm_y2:
            raise ValueError(f"Invalid bounding box: norm_y1 ({self.norm_y1}) cannot exceed norm_y2 ({self.norm_y2}).")
        return self

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return self.width * self.height


class StandardDetection(BaseModel):
    """
    Standardized atomic detection primitive produced by any CV provider.
    Framework-agnostic representation of a detected civic problem or road hazard.
    """
    class_id: int = Field(ge=0, description="Integer class ID in the provider taxonomy")
    class_name: str = Field(min_length=1, description="Resolved semantic class label")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence score in [0.0, 1.0]")
    bbox: StandardBoundingBox = Field(description="Bounding box coordinates in image space")
    category: Optional[str] = Field(default="road_hazard", description="High-level category domain")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata for future tracking IDs, segmentation masks, or keypoints",
    )


class InferenceRequest(BaseModel):
    """
    Input encapsulation passed to a CVInferenceProvider.
    Accommodates in-memory PIL images, raw binary bytes, or future stream/frame handles.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: Optional[Any] = Field(default=None, description="Pillow Image object or array-like visual data")
    image_bytes: Optional[bytes] = Field(default=None, description="Raw encoded image bytes (JPEG/PNG/WEBP)")
    confidence_override: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence threshold overriding the provider default",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the inference request was received",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible request context (e.g. frame sequence index, camera ID, GPS location)",
    )


class StandardDetectionResult(BaseModel):
    """
    Standardized computer vision inference response.
    Completely decoupled from framework-native tensor structures.
    """
    success: bool = Field(description="Whether inference completed successfully")
    model_id: str = Field(description="ID of the model that executed inference")
    model_version: str = Field(description="Version of the model that executed inference")
    model_hash: Optional[str] = Field(default=None, description="SHA-256 cryptographic hash of model weights")
    provider_id: Optional[str] = Field(default=None, description="Identifier of the provider implementation")
    task_type: ModelTaskType | str = Field(default=ModelTaskType.OBJECT_DETECTION, description="Task category")
    total_detections: int = Field(ge=0, description="Number of detected objects meeting threshold")
    detections: list[StandardDetection] = Field(default_factory=list, description="List of standardized detections")
    inference_duration_ms: float = Field(default=0.0, ge=0.0, description="Execution duration in milliseconds")
    inference_timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of inference execution",
    )
    image_width: Optional[int] = Field(default=None, ge=0, description="Original image width in pixels")
    image_height: Optional[int] = Field(default=None, ge=0, description="Original image height in pixels")
    confidence_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence threshold applied during inference",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible provider metadata (e.g. SHA-256 hash, device used, temporal context)",
    )
    provider_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible provider execution metadata",
    )

    @model_validator(mode="after")
    def sync_metadata(self) -> "StandardDetectionResult":
        # Keep metadata and provider_metadata synchronized for seamless backward compatibility
        if self.provider_metadata and not self.metadata:
            self.metadata = dict(self.provider_metadata)
        elif self.metadata and not self.provider_metadata:
            self.provider_metadata = dict(self.metadata)
        elif self.provider_metadata and self.metadata:
            combined = {**self.metadata, **self.provider_metadata}
            self.metadata = combined
            self.provider_metadata = combined
        return self


class CVInferenceProvider(ABC):
    """
    Abstract Service Provider Interface (SPI) for Computer Vision Inference Engines.

    All model execution engines (M1.13 YOLOv8n, future ViT detectors, ONNX runtimes,
    video temporal models) must implement this contract.
    """

    @property
    @abstractmethod
    def descriptor(self) -> ModelDescriptor:
        """Returns the ModelDescriptor identifying this provider's model and capabilities."""
        pass

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Returns True if the model weights are loaded and ready to serve inference requests."""
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initializes the model, loads weights into memory, and verifies readiness.
        Returns True if initialization succeeded, False otherwise.
        """
        pass

    @abstractmethod
    def infer(self, request: InferenceRequest) -> StandardDetectionResult:
        """
        Executes inference on the provided request and returns a StandardDetectionResult.
        Must be thread-safe.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Releases all model resources, memory maps, or device sessions cleanly."""
        pass
