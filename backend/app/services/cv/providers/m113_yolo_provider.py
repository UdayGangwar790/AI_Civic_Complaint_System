"""
CVKI - Civic Vision & Knowledge Intelligence
Module 8.5: Frozen M1.13 YOLOv8n Provider Adapter

Implements the CVInferenceProvider SPI for the frozen production baseline:
YOLOv8n trained in run yolov8n_m1_13.

Isolates all Ultralytics/YOLO/Torch dependencies within this module boundary.
All outputs are strictly converted to StandardDetectionResult.
"""

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import logging
from pathlib import Path
from threading import Lock
import time
from typing import Any, Optional

from PIL import Image
from ultralytics import YOLO

from app.core.config import settings
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
    ModelEvaluationMetadata,
    ModelIntegrityError,
    SplitEvaluationMetrics,
    resolve_safe_model_reference,
)

logger = logging.getLogger("cvki.cv.providers.m113_yolo")

# Non-negotiable M1.13 Production Constants
M1_13_MODEL_ID = "m1.13-yolov8n"
M1_13_MODEL_NAME = "M1.13 Civic Hazard YOLOv8n"
M1_13_VERSION = settings.YOLO_MODEL_VERSION  # "1.13.0"
M1_13_PROVIDER_ID = "m113_yolo_provider"
M1_13_REQUIRED_SHA256 = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
M1_13_EXPECTED_CLASSES: dict[int, str] = {
    0: "open_damaged_manhole",
    1: "damaged_missing_road_sign",
    2: "road_waterlogging",
}
M1_13_DEFAULT_CONFIDENCE = 0.25


class M113YOLOProvider(CVInferenceProvider):
    """
    Concrete adapter wrapping the frozen M1.13 YOLOv8n detector.
    Satisfies CVInferenceProvider contract without leaking YOLO internals.
    """

    def __init__(
        self,
        weights_reference: Optional[str] = None,
        verify_sha_on_load: bool = True,
        confidence_threshold: float = M1_13_DEFAULT_CONFIDENCE,
    ):
        self._model_id = M1_13_MODEL_ID
        self._provider_id = M1_13_PROVIDER_ID
        self._weights_reference = (
            weights_reference
            if weights_reference is not None
            else "ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt"
        )
        self._verify_sha_on_load = verify_sha_on_load
        self._confidence_threshold = confidence_threshold
        self._expected_sha = M1_13_REQUIRED_SHA256

        self._model: Optional[YOLO] = None
        self._is_loaded: bool = False
        self._load_error: Optional[str] = None
        self._lock = Lock()
        self._class_names: dict[int, str] = dict(M1_13_EXPECTED_CLASSES)

    @property
    def descriptor(self) -> ModelDescriptor:
        """Returns the ModelDescriptor identifying this M1.13 baseline provider."""
        eval_meta = ModelEvaluationMetadata(
            experiment_id="yolov8n_m1_13",
            training_dataset_version="dataset_m1_13",
            training_epochs=50,
            primary_validation=SplitEvaluationMetrics(
                split_name="validation",
                precision=0.726,
                recall=0.590,
                map50=0.643,
                map50_95=0.417,
            ),
            held_out_validation=[
                SplitEvaluationMetrics(
                    split_name="m1_8_test",
                    precision=0.838,
                    recall=0.612,
                    map50=0.654,
                    map50_95=0.487,
                ),
                SplitEvaluationMetrics(
                    split_name="m1_11_test",
                    precision=0.650,
                    recall=0.570,
                    map50=0.568,
                    map50_95=0.423,
                ),
            ],
            metrics_notes="Frozen production baseline evaluation metrics.",
        )

        return ModelDescriptor(
            model_id=self._model_id,
            model_name=M1_13_MODEL_NAME,
            model_version=M1_13_VERSION,
            provider_id=self._provider_id,
            framework=ModelFramework.ULTRALYTICS_YOLO,
            task_type=ModelTaskType.OBJECT_DETECTION,
            sha256_hash=self._expected_sha,
            model_reference=self._weights_reference,
            supported_classes=self._class_names,
            confidence_threshold_default=self._confidence_threshold,
            lifecycle_status=ModelLifecycleStatus.ACTIVE,
            evaluation_metadata=eval_meta,
            metadata={
                "architecture": "YOLOv8n",
                "backbone": "CSPDarknet",
                "input_resolution": 640,
                "production_baseline": True,
            },
        )

    @property
    def is_loaded(self) -> bool:
        """Returns True if the underlying YOLO model is initialized and resident in memory."""
        return self._is_loaded and self._model is not None

    def initialize(self) -> bool:
        """
        Loads the frozen M1.13 model weights into memory.
        Enforces path boundary safety, cryptographic SHA integrity, and class taxonomy validation.
        """
        with self._lock:
            if self._is_loaded and self._model is not None:
                return True

            logger.info("Initializing M1.13 YOLO Provider (weights_ref=%s)...", self._weights_reference)

            try:
                # 1. Resolve path through safe reference boundary
                resolved_path = resolve_safe_model_reference(self._weights_reference)
                if not resolved_path.exists() or not resolved_path.is_file():
                    raise FileNotFoundError(f"M1.13 weights file does not exist: {resolved_path}")

                # 2. Cryptographic SHA-256 verification
                if self._verify_sha_on_load:
                    hasher = hashlib.sha256()
                    with open(resolved_path, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher.update(chunk)
                    computed_sha = hasher.hexdigest().lower()
                    if computed_sha != self._expected_sha:
                        raise ModelIntegrityError(
                            f"Model weights integrity failure! Computed: {computed_sha}, "
                            f"Expected: {self._expected_sha}"
                        )

                # 3. Instantiate native YOLO model
                yolo_instance = YOLO(str(resolved_path))

                # 4. Validate native class contract
                if not hasattr(yolo_instance, "names") or not isinstance(yolo_instance.names, dict):
                    raise ValueError("Loaded model does not contain a valid 'names' dictionary attribute.")

                native_classes = {int(k): str(v) for k, v in yolo_instance.names.items()}
                for class_id, expected_name in M1_13_EXPECTED_CLASSES.items():
                    if native_classes.get(class_id) != expected_name:
                        raise ValueError(
                            f"M1.13 class mapping mismatch for ID {class_id}: "
                            f"expected '{expected_name}', got '{native_classes.get(class_id)}'"
                        )

                self._model = yolo_instance
                self._class_names = native_classes
                self._is_loaded = True
                self._load_error = None
                logger.info("M1.13 YOLO Provider successfully initialized and verified.")
                return True

            except Exception as exc:
                self._is_loaded = False
                self._model = None
                self._load_error = str(exc)
                logger.error("M1.13 YOLO Provider initialization failed: %s", exc)
                raise

    def infer(self, request: InferenceRequest) -> StandardDetectionResult:
        """
        Executes inference against an input image.
        Accepts PIL Image or raw bytes, runs YOLO detection, and transforms native
        output into a standardized, model-agnostic StandardDetectionResult.
        """
        if not self.is_loaded:
            raise RuntimeError("M113YOLOProvider is not initialized. Call initialize() before infer().")

        # 1. Resolve image input
        pil_image: Optional[Image.Image] = None
        if request.image is not None and isinstance(request.image, Image.Image):
            pil_image = request.image
        elif request.image_bytes is not None:
            pil_image = Image.open(BytesIO(request.image_bytes)).convert("RGB")
        else:
            raise ValueError("InferenceRequest must provide either 'image' (PIL Image) or 'image_bytes'.")

        image_width, image_height = pil_image.size
        effective_conf = (
            request.confidence_override
            if request.confidence_override is not None
            else getattr(settings, "YOLO_CONFIDENCE_THRESHOLD", self._confidence_threshold)
        )

        start_time = time.perf_counter()

        # 2. Execute inference under model execution lock
        with self._lock:
            native_results = self._model(
                pil_image,
                conf=effective_conf,
                device=settings.YOLO_DEVICE,
                verbose=False,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # 3. Standardize detections
        standard_detections: list[StandardDetection] = []
        for result in native_results:
            if result.boxes is None:
                continue

            boxes = result.boxes.xyxy.cpu().tolist()
            class_ids = result.boxes.cls.cpu().tolist()
            confidences = result.boxes.conf.cpu().tolist()

            for coords, cid_float, conf_float in zip(boxes, class_ids, confidences):
                confidence = float(conf_float)
                if confidence < effective_conf:
                    continue

                raw_x1, raw_y1, raw_x2, raw_y2 = coords
                x1 = max(0, min(int(round(raw_x1)), image_width))
                y1 = max(0, min(int(round(raw_y1)), image_height))
                x2 = max(0, min(int(round(raw_x2)), image_width))
                y2 = max(0, min(int(round(raw_y2)), image_height))

                # Normalize safely
                norm_x1 = round(x1 / image_width, 4) if image_width > 0 else 0.0
                norm_y1 = round(y1 / image_height, 4) if image_height > 0 else 0.0
                norm_x2 = round(x2 / image_width, 4) if image_width > 0 else 0.0
                norm_y2 = round(y2 / image_height, 4) if image_height > 0 else 0.0

                bbox = StandardBoundingBox(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    norm_x1=norm_x1,
                    norm_y1=norm_y1,
                    norm_x2=norm_x2,
                    norm_y2=norm_y2,
                )

                class_id = int(cid_float)
                class_name = self._class_names.get(class_id, "unknown")

                standard_detections.append(
                    StandardDetection(
                        class_id=class_id,
                        class_name=class_name,
                        confidence=round(confidence, 4),
                        bbox=bbox,
                        category="road_hazard",
                        metadata={},
                    )
                )

        return StandardDetectionResult(
            success=True,
            model_id=self._model_id,
            model_version=M1_13_VERSION,
            model_hash=self._expected_sha,
            provider_id=self._provider_id,
            task_type=ModelTaskType.OBJECT_DETECTION,
            total_detections=len(standard_detections),
            detections=standard_detections,
            inference_duration_ms=round(duration_ms, 2),
            inference_timestamp=datetime.now(timezone.utc),
            image_width=image_width,
            image_height=image_height,
            confidence_threshold=effective_conf,
            provider_metadata={
                "device": settings.YOLO_DEVICE,
                "framework": "ultralytics_yolo",
                "weights_reference": self._weights_reference,
            },
        )

    def shutdown(self) -> None:
        """Releases underlying model resources and memory."""
        with self._lock:
            self._model = None
            self._is_loaded = False
            self._load_error = None
            logger.info("M1.13 YOLO Provider successfully shut down.")
