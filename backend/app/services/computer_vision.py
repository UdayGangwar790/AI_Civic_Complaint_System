import logging
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from PIL import Image, ImageDraw
from ultralytics import YOLO

from app.core.config import settings

logger = logging.getLogger("cvki.services.computer_vision")


class ModelUnavailableError(RuntimeError):
    """The configured model is not available for inference."""


class YOLOModelService:
    """
    Singleton service responsible for loading, managing, and exposing the
    verified YOLOv8 civic problem detection model.
    """

    def __init__(self):
        self._model: Optional[YOLO] = None
        self._is_loaded: bool = False
        self._load_error: Optional[str] = None
        self._model_name: str = "yolov8n"
        self._model_version: str = settings.YOLO_MODEL_VERSION
        self._class_names: dict[int, str] = {}
        self._num_classes: int = 0
        self._inference_lock = Lock()

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def model(self) -> Optional[YOLO]:
        return self._model

    def load_model(self, custom_path: Optional[str | Path] = None) -> bool:
        """
        Loads the YOLO model into memory once during application startup.
        Validates model file existence and exact civic class mapping.
        """
        target_path = Path(custom_path) if custom_path else settings.get_resolved_model_path()
        logger.info("Initiating YOLO model load.")

        # 1. Verify model file exists
        if not target_path.exists():
            error_msg = "Model weights file is missing."
            logger.error("YOLO model weights file is missing.")
            self._is_loaded = False
            self._load_error = error_msg
            self._model = None
            return False

        # 2. Attempt model loading
        try:
            model = YOLO(str(target_path))
            
            # Validate model names attribute
            if not hasattr(model, "names") or not isinstance(model.names, dict):
                raise ValueError("Loaded model does not contain a valid 'names' dictionary attribute.")

            # Validate class mapping
            class_mapping = {int(k): str(v) for k, v in model.names.items()}
            expected_classes = settings.EXPECTED_CLASSES
            
            for class_id, expected_name in expected_classes.items():
                if class_mapping.get(class_id) != expected_name:
                    raise ValueError(
                        f"Class mapping mismatch for ID {class_id}: "
                        f"expected '{expected_name}', got '{class_mapping.get(class_id)}'"
                    )

            self._model = model
            self._class_names = class_mapping
            self._num_classes = len(class_mapping)
            self._is_loaded = True
            self._load_error = None
            logger.info(
                f"YOLO model successfully loaded ({self._model_version}): "
                f"{self._num_classes} classes configured -> {self._class_names}"
            )
            return True

        except Exception as exc:
            error_msg = "Model loading failed."
            logger.error("YOLO model loading failed (error_type=%s).", type(exc).__name__)
            self._is_loaded = False
            self._load_error = error_msg
            self._model = None
            self._class_names = {}
            self._num_classes = 0
            return False

    def get_model(self) -> YOLO:
        """
        Returns the loaded model instance. Raises RuntimeError if not loaded.
        """
        if not self._is_loaded or self._model is None:
            raise ModelUnavailableError("YOLO model is not loaded.")
        return self._model

    def get_model_status(self) -> dict[str, Any]:
        """
        Returns safe metadata regarding model availability without leaking
        internal filesystem paths.
        """
        if self._is_loaded:
            return {
                "loaded": True,
                "status": "ready",
                "model_name": self._model_name,
                "model_version": self._model_version,
                "num_classes": self._num_classes,
                "classes": self._class_names,
            }
        return {
            "loaded": False,
            "status": "error",
            "model_name": self._model_name,
            "model_version": self._model_version,
            "num_classes": 0,
            "classes": {},
            "error": "Model is unavailable.",
        }

    def predict(self, image: Image.Image) -> list[dict[str, Any]]:
        """Run inference with the model loaded during application startup."""
        if not self._is_loaded:
            raise ModelUnavailableError("YOLO model is not loaded.")
        from app.services.cv.runtime import cv_runtime_service
        try:
            return cv_runtime_service.predict_legacy_dict(image)
        except Exception:
            model = self.get_model()
            with self._inference_lock:
                results = model(
                    image,
                    conf=settings.YOLO_CONFIDENCE_THRESHOLD,
                    device=settings.YOLO_DEVICE,
                    verbose=False,
                )
            detections: list[dict[str, Any]] = []
            image_width, image_height = image.size

            for result in results:
                if result.boxes is None:
                    continue
                boxes = result.boxes.xyxy.cpu().tolist()
                class_ids = result.boxes.cls.cpu().tolist()
                confidences = result.boxes.conf.cpu().tolist()
                for coordinates, class_id, confidence in zip(boxes, class_ids, confidences):
                    confidence = float(confidence)
                    if confidence < settings.YOLO_CONFIDENCE_THRESHOLD:
                        continue
                    x1, y1, x2, y2 = coordinates
                    detections.append(
                        {
                            "class_id": int(class_id),
                            "class_name": self._class_names.get(int(class_id), "unknown"),
                            "confidence": confidence,
                            "bbox": {
                                "x1": max(0, min(int(round(x1)), image_width)),
                                "y1": max(0, min(int(round(y1)), image_height)),
                                "x2": max(0, min(int(round(x2)), image_width)),
                                "y2": max(0, min(int(round(y2)), image_height)),
                            },
                        }
                    )
            return detections

    def annotate_image(
        self,
        image: Image.Image,
        detections: list[dict[str, Any]],
    ) -> Image.Image:
        """Draw the supplied detections on an in-memory copy of the image using decoupled renderer."""
        from app.services.cv.renderer import render_detections
        return render_detections(image, detections)


# Singleton service instance
cv_model_service = YOLOModelService()


def detect_problems(image: Image.Image) -> list[dict[str, Any]]:
    """Run inference through the shared application model service."""
    return cv_model_service.predict(image)