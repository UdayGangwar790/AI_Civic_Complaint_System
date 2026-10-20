"""
CVKI - Module 8.6: Computer Vision Runtime & API Orchestration Tests

Tests:
1. ProviderResolver: registration, caching, rejection of arbitrary/unapproved provider IDs
2. CVInferenceService: model registry resolution, provider initialization, is_loaded
3. Standard inference execution and Base64 PNG annotation generation
4. Legacy dictionary output bridge for backward compatibility
5. Safe model status inspection without internal path leakage
6. Architectural demonstration of future model replacement using mock provider
"""

import unittest
from PIL import Image

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
from app.services.cv.model_registry import ModelRegistry
from app.services.cv.runtime import (
    CVInferenceService,
    ModelUnavailableError,
    ProviderNotFoundError,
    ProviderResolver,
)


class MockFutureTransformerProvider(CVInferenceProvider):
    """
    Mock provider simulating a future ViT/DETR/Transformer-based civic hazard detector.
    Demonstrates architectural future model replacement without downstream code modifications.
    """

    def __init__(self):
        self._is_loaded = False

    @property
    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor(
            model_id="future-transformer-v1",
            model_name="Future Civic Vision Transformer",
            model_version="2.0.0",
            provider_id="mock_transformer_provider",
            framework=ModelFramework.HUGGINGFACE_TRANSFORMER,
            task_type=ModelTaskType.OBJECT_DETECTION,
            supported_classes={
                0: "open_damaged_manhole",
                1: "damaged_missing_road_sign",
                2: "road_waterlogging",
            },
            confidence_threshold_default=0.30,
            lifecycle_status=ModelLifecycleStatus.ACTIVE,
        )

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def initialize(self) -> bool:
        self._is_loaded = True
        return True

    def infer(self, request: InferenceRequest) -> StandardDetectionResult:
        if not self._is_loaded:
            raise RuntimeError("Mock provider not initialized.")

        # Simulate standard detection output
        bbox = StandardBoundingBox(x1=50, y1=50, x2=200, y2=200)
        det = StandardDetection(
            class_id=0,
            class_name="open_damaged_manhole",
            confidence=0.92,
            bbox=bbox,
            category="road_hazard",
        )
        return StandardDetectionResult(
            success=True,
            model_id="future-transformer-v1",
            model_version="2.0.0",
            provider_id="mock_transformer_provider",
            task_type=ModelTaskType.OBJECT_DETECTION,
            total_detections=1,
            detections=[det],
            inference_duration_ms=45.0,
            image_width=640,
            image_height=480,
            confidence_threshold=0.30,
            provider_metadata={"attention_heads": 12},
        )

    def shutdown(self) -> None:
        self._is_loaded = False


class TestCVRuntime(unittest.TestCase):
    """Test suite for CV runtime and orchestration service."""

    def setUp(self):
        self.resolver = ProviderResolver()
        self.registry = ModelRegistry()
        self.service = CVInferenceService(registry=self.registry, resolver=self.resolver)

    def tearDown(self):
        self.service.shutdown()

    def test_provider_resolver_approved_providers(self):
        # M1.13 provider resolves cleanly
        provider = self.resolver.resolve_provider("m113_yolo_provider")
        self.assertIsNotNone(provider)

        # Provider instance is cached
        provider_cached = self.resolver.resolve_provider("m113_yolo_provider")
        self.assertIs(provider, provider_cached)

    def test_provider_resolver_rejects_arbitrary_or_unapproved_id(self):
        with self.assertRaises(ProviderNotFoundError) as ctx:
            self.resolver.resolve_provider("malicious_unapproved_provider")
        self.assertIn("not an approved server-side provider", str(ctx.exception))

        with self.assertRaises(ProviderNotFoundError):
            self.resolver.resolve_provider("../../etc/passwd")

    def test_cv_runtime_initialization_and_inference(self):
        # Service resolves active M1.13 baseline automatically
        img = Image.new("RGB", (640, 480), color=(100, 100, 100))
        req = InferenceRequest(image=img)

        result = self.service.infer(req)
        self.assertTrue(result.success)
        self.assertEqual(result.model_id, "m1.13-yolov8n")
        self.assertEqual(result.image_width, 640)
        self.assertEqual(result.image_height, 480)
        self.assertTrue(self.service.is_loaded)

    def test_predict_image_with_annotated_rendering(self):
        img = Image.new("RGB", (320, 240), color=(50, 50, 50))
        result, data_url = self.service.predict_image(img)

        self.assertTrue(result.success)
        self.assertTrue(data_url.startswith("data:image/png;base64,"))

    def test_predict_legacy_dict_format(self):
        img = Image.new("RGB", (320, 240), color=(50, 50, 50))
        legacy_list = self.service.predict_legacy_dict(img)

        self.assertIsInstance(legacy_list, list)

    def test_safe_model_status_no_internal_path_leakage(self):
        status = self.service.get_model_status()
        self.assertTrue(status["loaded"])
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["num_classes"], 3)

        raw_str = str(status)
        self.assertNotIn("Users", raw_str)
        self.assertNotIn("runs", raw_str)
        self.assertNotIn("weights", raw_str)
        self.assertNotIn("best.pt", raw_str)

    def test_future_model_replacement_demonstration(self):
        """
        Architectural validation: Registering a future transformer provider allows
        the CV runtime to execute inference and produce identical StandardDetectionResult
        contracts without any changes to downstream consumers.
        """
        # 1. Register mock transformer provider factory
        self.resolver.register_provider_factory(
            "mock_transformer_provider",
            lambda: MockFutureTransformerProvider(),
        )

        # 2. Register future model descriptor and activate it
        desc = ModelDescriptor(
            model_id="future-vit-v2",
            model_name="Future Civic Vision Transformer",
            model_version="2.0.0",
            provider_id="mock_transformer_provider",
            framework=ModelFramework.HUGGINGFACE_TRANSFORMER,
            task_type=ModelTaskType.OBJECT_DETECTION,
            supported_classes={
                0: "open_damaged_manhole",
                1: "damaged_missing_road_sign",
                2: "road_waterlogging",
            },
            lifecycle_status=ModelLifecycleStatus.REGISTERED,
        )
        self.registry.register_model(desc)
        self.registry.transition_model_status("future-vit-v2", ModelLifecycleStatus.VALIDATING)
        self.registry.transition_model_status("future-vit-v2", ModelLifecycleStatus.EVALUATED)
        self.registry.activate_model("future-vit-v2", reason="Promote next-gen ViT detector")

        # 3. Create isolated runtime with updated registry state
        future_service = CVInferenceService(registry=self.registry, resolver=self.resolver)

        img = Image.new("RGB", (640, 480), color=(80, 80, 80))
        std_result, data_url = future_service.predict_image(img)

        # 4. Verify runtime consumed future provider seamlessly
        self.assertTrue(std_result.success)
        self.assertEqual(std_result.model_id, "future-transformer-v1")
        self.assertEqual(std_result.provider_id, "mock_transformer_provider")
        self.assertEqual(std_result.total_detections, 1)
        self.assertEqual(std_result.detections[0].class_name, "open_damaged_manhole")
        self.assertTrue(data_url.startswith("data:image/png;base64,"))
        future_service.shutdown()


if __name__ == "__main__":
    unittest.main()
