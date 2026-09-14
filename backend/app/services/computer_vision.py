import logging
from pathlib import Path
from typing import Any, Optional
from ultralytics import YOLO

from app.core.config import settings

logger = logging.getLogger("cvki.services.computer_vision")


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
        logger.info(f"Initiating YOLO model load from: {target_path}")

        # 1. Verify model file exists
        if not target_path.exists():
            error_msg = f"Model weights file not found at expected path: {target_path.name}"
            logger.error(error_msg)
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
            error_msg = f"Failed to load YOLO model: {str(exc)}"
            logger.error(error_msg, exc_info=True)
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
            raise RuntimeError(f"YOLO model is not loaded. Error state: {self._load_error}")
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
            "error": self._load_error or "Model is not loaded",
        }


# Singleton service instance
cv_model_service = YOLOModelService()


def detect_problems(image_path: str):
    """
    Placeholder for future Computer Vision inference interface (M2.2+).
    """
    raise NotImplementedError("CV detection logic not implemented yet.")