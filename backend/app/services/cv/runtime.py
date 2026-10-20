"""
CVKI - Civic Vision & Knowledge Intelligence
Module 8.6: Computer Vision Runtime & API Orchestration Service

Orchestrates framework-agnostic computer vision inference:
1. Resolves active model descriptor via ModelRegistry
2. Resolves approved provider implementation via ProviderResolver (no arbitrary code execution)
3. Caches initialized provider lifecycle (avoids repeated model loading per request)
4. Executes inference producing StandardDetectionResult
5. Exposes model availability status without path or credential leakage
6. Provides seamless backward-compatibility adapters for existing API endpoints
"""

import logging
from threading import Lock
from typing import Any, Callable, Optional, Type
from PIL import Image

from app.core.config import settings
from app.services.cv.base_provider import (
    CVInferenceProvider,
    InferenceRequest,
    ModelDescriptor,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.cv.model_registry import ModelRegistry, model_registry
from app.services.cv.providers.m113_yolo_provider import M113YOLOProvider
from app.services.cv.renderer import render_annotated_png_data_url

logger = logging.getLogger("cvki.services.cv.runtime")


class ProviderNotFoundError(RuntimeError):
    """Raised when an unapproved or unregistered provider_id is requested."""
    pass


class ModelUnavailableError(RuntimeError):
    """Raised when the active model or provider is not ready to serve inference."""
    pass


class ProviderResolver:
    """
    Controlled registry and factory for approved CVInferenceProvider implementations.
    Strictly forbids dynamic class importing, path traversal, or client-specified code loading.
    """

    def __init__(self):
        self._provider_registry: dict[str, Callable[[], CVInferenceProvider]] = {}
        self._active_instances: dict[str, CVInferenceProvider] = {}
        self._lock = Lock()

        # Register server-side approved providers
        self.register_provider_factory("m113_yolo_provider", lambda: M113YOLOProvider())
        self.register_provider_factory("yolov8_provider", lambda: M113YOLOProvider())

    def register_provider_factory(
        self,
        provider_id: str,
        factory: Callable[[], CVInferenceProvider],
    ) -> None:
        """Registers an authorized provider factory."""
        with self._lock:
            self._provider_registry[provider_id.strip().lower()] = factory

    def resolve_provider(self, provider_id: str) -> CVInferenceProvider:
        """
        Resolves an approved provider instance by ID. Caches active instance for thread safety.
        Rejects arbitrary or unrecognized provider IDs.
        """
        normalized_id = provider_id.strip().lower()
        with self._lock:
            if normalized_id in self._active_instances:
                return self._active_instances[normalized_id]

            factory = self._provider_registry.get(normalized_id)
            if factory is None:
                raise ProviderNotFoundError(
                    f"Provider '{provider_id}' is not an approved server-side provider. "
                    f"Approved providers: {list(self._provider_registry.keys())}"
                )

            instance = factory()
            self._active_instances[normalized_id] = instance
            logger.info("Instantiated and cached approved CV provider: %s", normalized_id)
            return instance

    def reset(self) -> None:
        """Shuts down active provider instances and clears cache."""
        with self._lock:
            for pid, instance in self._active_instances.items():
                try:
                    instance.shutdown()
                except Exception as exc:
                    logger.warning("Error shutting down provider '%s': %s", pid, exc)
            self._active_instances.clear()


class CVInferenceService:
    """
    Model-agnostic computer vision runtime orchestration service.
    Coordinates model resolution, provider lifecycle, inference execution, and compatibility bridges.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        resolver: Optional[ProviderResolver] = None,
    ):
        self._registry = registry or model_registry
        self._resolver = resolver or ProviderResolver()
        self._active_provider: Optional[CVInferenceProvider] = None
        self._lock = Lock()

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @property
    def resolver(self) -> ProviderResolver:
        return self._resolver

    def get_active_provider(self) -> CVInferenceProvider:
        """
        Resolves and initializes the active inference provider based on ModelRegistry state.
        Ensures model weights are resident in memory.
        """
        with self._lock:
            if self._active_provider is not None and self._active_provider.is_loaded:
                return self._active_provider

            # 1. Resolve active model descriptor
            active_model = self._registry.get_active_model()
            if active_model is None:
                # Fallback to registered M1.13 baseline if not explicitly set active
                try:
                    active_model = self._registry.get_model("m1.13-yolov8n")
                except Exception:
                    raise ModelUnavailableError("No active computer vision model registered in registry.")

            provider_id = active_model.provider_id or "m113_yolo_provider"

            # 2. Resolve approved provider
            provider = self._resolver.resolve_provider(provider_id)

            # 3. Initialize provider if not already loaded
            if not provider.is_loaded:
                success = provider.initialize()
                if not success or not provider.is_loaded:
                    raise ModelUnavailableError(f"Failed to initialize provider '{provider_id}'.")

            self._active_provider = provider
            return provider

    @property
    def is_loaded(self) -> bool:
        """Returns True if the active provider is initialized and ready for inference."""
        try:
            provider = self.get_active_provider()
            return provider.is_loaded
        except Exception:
            return False

    def get_model_status(self) -> dict[str, Any]:
        """
        Returns safe, sanitized metadata regarding model status for health probes and API clients.
        Never leaks filesystem paths, credentials, or internal directory structures.
        """
        try:
            provider = self.get_active_provider()
            desc = provider.descriptor
            return {
                "loaded": provider.is_loaded,
                "status": "ready" if provider.is_loaded else "not_ready",
                "model_name": desc.model_name,
                "model_version": desc.model_version,
                "num_classes": len(desc.supported_classes),
                "classes": desc.supported_classes,
                "model_id": desc.model_id,
                "provider_id": desc.provider_id,
                "framework": str(desc.framework),
            }
        except Exception as exc:
            return {
                "loaded": False,
                "status": "error",
                "model_name": "unknown",
                "model_version": settings.YOLO_MODEL_VERSION,
                "num_classes": 0,
                "classes": {},
                "error": "Detection model is unavailable.",
            }

    def infer(self, request: InferenceRequest) -> StandardDetectionResult:
        """
        Executes inference using the resolved active provider.
        Returns a validated StandardDetectionResult.
        """
        provider = self.get_active_provider()
        try:
            return provider.infer(request)
        except Exception as exc:
            logger.error("CV Runtime inference execution failed: %s", exc)
            raise

    def predict_image(
        self,
        image: Image.Image,
        confidence_override: Optional[float] = None,
    ) -> tuple[StandardDetectionResult, str]:
        """
        Convenience execution bridge for API endpoints:
        Executes inference and renders the annotated Base64 PNG data URL.
        """
        req = InferenceRequest(image=image, confidence_override=confidence_override)
        result = self.infer(req)
        annotated_data_url = render_annotated_png_data_url(image, result.detections)
        return result, annotated_data_url

    def predict_legacy_dict(
        self,
        image: Image.Image,
        confidence_override: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """
        Legacy compatibility adapter returning detection dictionaries matching
        the legacy YOLOModelService.predict() output format.
        """
        req = InferenceRequest(image=image, confidence_override=confidence_override)
        result = self.infer(req)

        legacy_detections: list[dict[str, Any]] = []
        for det in result.detections:
            legacy_detections.append(
                {
                    "class_id": det.class_id,
                    "class_name": det.class_name,
                    "confidence": det.confidence,
                    "bbox": {
                        "x1": det.bbox.x1,
                        "y1": det.bbox.y1,
                        "x2": det.bbox.x2,
                        "y2": det.bbox.y2,
                    },
                }
            )
        return legacy_detections

    def shutdown(self) -> None:
        """Shuts down all cached provider resources cleanly."""
        with self._lock:
            if self._active_provider is not None:
                self._active_provider.shutdown()
                self._active_provider = None
            self._resolver.reset()


# Shared singleton CV Runtime Service instance
cv_runtime_service = CVInferenceService()
