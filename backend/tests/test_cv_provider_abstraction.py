"""
CVKI - Civic Vision & Knowledge Intelligence
Module 8.2: Computer Vision Provider Abstraction SPI Unit Tests
"""

import unittest
from datetime import datetime, timezone
import sys

from pydantic import ValidationError

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


class MockCivicDetectionProvider(CVInferenceProvider):
    """
    Minimal mock computer vision provider implementing CVInferenceProvider SPI.
    Simulates a generic road hazard detection engine without any external dependencies.
    """

    def __init__(
        self,
        model_id: str = "mock_civic_detector",
        model_name: str = "MockCivicNet",
        model_version: str = "0.1.0-mock",
    ):
        self._descriptor = ModelDescriptor(
            model_id=model_id,
            model_name=model_name,
            model_version=model_version,
            framework=ModelFramework.MOCK,
            task_type=ModelTaskType.OBJECT_DETECTION,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            weights_path="models/mock_weights.bin",
            supported_classes={
                0: "open_damaged_manhole",
                1: "damaged_missing_road_sign",
                2: "road_waterlogging",
            },
            confidence_threshold_default=0.30,
            lifecycle_status=ModelLifecycleStatus.CANDIDATE,
            created_at=datetime.now(timezone.utc),
            metadata={"architecture": "MockConvNet", "parameters": 1200000},
        )
        self._loaded: bool = False

    @property
    def descriptor(self) -> ModelDescriptor:
        return self._descriptor

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def initialize(self) -> bool:
        self._loaded = True
        return True

    def infer(self, request: InferenceRequest) -> StandardDetectionResult:
        if not self._loaded:
            raise RuntimeError("Cannot execute inference: Mock provider is not initialized.")

        threshold = (
            request.confidence_override
            if request.confidence_override is not None
            else self._descriptor.confidence_threshold_default
        )

        detections = []
        candidate_confidence = 0.92
        if candidate_confidence >= threshold:
            detections.append(
                StandardDetection(
                    class_id=0,
                    class_name="open_damaged_manhole",
                    confidence=candidate_confidence,
                    bbox=StandardBoundingBox(
                        x1=100,
                        y1=100,
                        x2=300,
                        y2=300,
                        norm_x1=0.156,
                        norm_y1=0.208,
                        norm_x2=0.468,
                        norm_y2=0.625,
                    ),
                    category="road_hazard",
                    metadata={"synthetic": True},
                )
            )

        return StandardDetectionResult(
            success=True,
            model_id=self._descriptor.model_id,
            model_version=self._descriptor.model_version,
            total_detections=len(detections),
            detections=detections,
            inference_duration_ms=4.5,
            image_width=640,
            image_height=480,
            metadata={"engine": "mock_runtime", "threshold_used": threshold},
        )

    def shutdown(self) -> None:
        self._loaded = False


class TestCVProviderAbstraction(unittest.TestCase):
    """
    Validates that the CV Provider Abstraction SPI operates correctly as an independent
    framework-agnostic contract.
    """

    def test_01_abstract_provider_cannot_be_instantiated(self):
        """Verify CVInferenceProvider is an abstract class that cannot be directly instantiated."""
        with self.assertRaises(TypeError) as ctx:
            CVInferenceProvider()  # type: ignore[abstract]
        err_msg = str(ctx.exception)
        self.assertIn("Can't instantiate abstract class", err_msg)
        self.assertTrue(
            any(method in err_msg for method in ["descriptor", "infer", "initialize", "is_loaded", "shutdown"])
        )

    def test_02_mock_provider_implements_spi(self):
        """Verify a concrete mock provider implementing all abstract methods instantiates cleanly."""
        provider = MockCivicDetectionProvider()
        self.assertIsInstance(provider, CVInferenceProvider)
        self.assertFalse(provider.is_loaded)

    def test_03_mock_provider_exposes_descriptor(self):
        """Verify descriptor contract returns complete model metadata."""
        provider = MockCivicDetectionProvider()
        descriptor = provider.descriptor
        self.assertIsInstance(descriptor, ModelDescriptor)
        self.assertEqual(descriptor.model_id, "mock_civic_detector")
        self.assertEqual(descriptor.model_name, "MockCivicNet")
        self.assertEqual(descriptor.model_version, "0.1.0-mock")
        self.assertEqual(descriptor.framework, ModelFramework.MOCK)
        self.assertEqual(descriptor.task_type, ModelTaskType.OBJECT_DETECTION)
        self.assertEqual(descriptor.confidence_threshold_default, 0.30)
        self.assertEqual(len(descriptor.supported_classes), 3)
        self.assertEqual(descriptor.supported_classes[0], "open_damaged_manhole")

    def test_04_mock_provider_initialize(self):
        """Verify initialize lifecycle method transitions provider to ready state."""
        provider = MockCivicDetectionProvider()
        self.assertFalse(provider.is_loaded)
        success = provider.initialize()
        self.assertTrue(success)
        self.assertTrue(provider.is_loaded)

    def test_05_mock_provider_reports_readiness(self):
        """Verify is_loaded reflects true operational readiness state."""
        provider = MockCivicDetectionProvider()
        self.assertFalse(provider.is_loaded)
        provider.initialize()
        self.assertTrue(provider.is_loaded)

    def test_06_mock_provider_returns_standard_detection_result(self):
        """Verify provider executes infer() and returns standard contract result."""
        provider = MockCivicDetectionProvider()
        provider.initialize()

        req = InferenceRequest(confidence_override=0.25)
        result = provider.infer(req)

        self.assertIsInstance(result, StandardDetectionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.model_id, "mock_civic_detector")
        self.assertEqual(result.model_version, "0.1.0-mock")
        self.assertEqual(result.total_detections, 1)
        self.assertEqual(len(result.detections), 1)

        det = result.detections[0]
        self.assertIsInstance(det, StandardDetection)
        self.assertEqual(det.class_id, 0)
        self.assertEqual(det.class_name, "open_damaged_manhole")
        self.assertEqual(det.confidence, 0.92)
        self.assertEqual(det.bbox.x1, 100)
        self.assertEqual(det.bbox.y1, 100)
        self.assertEqual(det.bbox.x2, 300)
        self.assertEqual(det.bbox.y2, 300)
        self.assertEqual(det.bbox.norm_x1, 0.156)

    def test_07_mock_provider_shutdown(self):
        """Verify shutdown releases state and subsequent infer calls fail cleanly."""
        provider = MockCivicDetectionProvider()
        provider.initialize()
        self.assertTrue(provider.is_loaded)

        provider.shutdown()
        self.assertFalse(provider.is_loaded)

        with self.assertRaises(RuntimeError) as ctx:
            provider.infer(InferenceRequest())
        self.assertIn("not initialized", str(ctx.exception))

    def test_08_provider_interface_does_not_require_ultralytics(self):
        """Verify provider base abstraction does not import or depend on Ultralytics or Torch."""
        import app.services.cv.base_provider as base_mod

        # Inspect module annotations and attributes
        mod_dict = base_mod.__dict__
        self.assertNotIn("ultralytics", mod_dict)
        self.assertNotIn("YOLO", mod_dict)
        self.assertNotIn("torch", mod_dict)

        # Inspect file source code for any hardcoded framework imports
        import inspect
        source = inspect.getsource(base_mod)
        self.assertNotIn("import ultralytics", source)
        self.assertNotIn("from ultralytics", source)
        self.assertNotIn("import torch", source)
        self.assertNotIn("from torch", source)

    def test_09_provider_contract_accepts_normalized_detection_data(self):
        """Verify StandardDetection and StandardBoundingBox serialization and deserialization."""
        bbox = StandardBoundingBox(
            x1=20,
            y1=40,
            x2=180,
            y2=220,
            norm_x1=0.05,
            norm_y1=0.10,
            norm_x2=0.45,
            norm_y2=0.55,
        )
        detection = StandardDetection(
            class_id=1,
            class_name="damaged_missing_road_sign",
            confidence=0.885,
            bbox=bbox,
            category="road_infrastructure",
            metadata={"track_id": 42, "custom_score": 0.99},
        )

        det_dict = detection.model_dump()
        self.assertEqual(det_dict["class_id"], 1)
        self.assertEqual(det_dict["class_name"], "damaged_missing_road_sign")
        self.assertEqual(det_dict["bbox"]["x1"], 20)
        self.assertEqual(det_dict["bbox"]["norm_x1"], 0.05)
        self.assertEqual(det_dict["metadata"]["track_id"], 42)

        # Roundtrip parse
        reconstructed = StandardDetection.model_validate(det_dict)
        self.assertEqual(reconstructed.class_name, detection.class_name)
        self.assertEqual(reconstructed.bbox.x2, 180)

    def test_10_invalid_confidence_and_bbox_validation(self):
        """Verify strict validation rules on confidence intervals and coordinate ordering."""
        # 1. Negative confidence
        with self.assertRaises(ValidationError):
            StandardDetection(
                class_id=0,
                class_name="open_damaged_manhole",
                confidence=-0.05,
                bbox=StandardBoundingBox(x1=0, y1=0, x2=10, y2=10),
            )

        # 2. Confidence > 1.0
        with self.assertRaises(ValidationError):
            StandardDetection(
                class_id=0,
                class_name="open_damaged_manhole",
                confidence=1.05,
                bbox=StandardBoundingBox(x1=0, y1=0, x2=10, y2=10),
            )

        # 3. Negative bounding box coordinates
        with self.assertRaises(ValidationError):
            StandardBoundingBox(x1=-10, y1=0, x2=100, y2=100)

        # 4. Inverted x coordinates (x1 > x2)
        with self.assertRaises(ValidationError):
            StandardBoundingBox(x1=150, y1=10, x2=50, y2=100)

        # 5. Inverted y coordinates (y1 > y2)
        with self.assertRaises(ValidationError):
            StandardBoundingBox(x1=10, y1=200, x2=100, y2=50)

        # 6. Valid zero-width or single point box (degenerate allowed)
        valid_point = StandardBoundingBox(x1=50, y1=50, x2=50, y2=50)
        self.assertEqual(valid_point.x1, valid_point.x2)


if __name__ == "__main__":
    unittest.main()
