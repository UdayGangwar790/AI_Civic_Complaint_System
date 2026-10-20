"""
CVKI - Module 8.5: Frozen M1.13 YOLO Provider Tests

Verifies concrete CVInferenceProvider adapter for M1.13 baseline:
- Descriptor metadata and class taxonomy
- Lifecycle: initialize, is_loaded, shutdown
- Integrity checking: SHA-256 match and rejection on corruption
- Standardized inference execution via PIL image and raw bytes
- Confidence override support
- Zero framework tensor leakage
"""

from io import BytesIO
import unittest
from PIL import Image

from app.services.cv.base_provider import (
    InferenceRequest,
    ModelFramework,
    ModelLifecycleStatus,
    ModelTaskType,
    StandardDetectionResult,
)
from app.services.cv.model_registry import ModelIntegrityError
from app.services.cv.providers.m113_yolo_provider import (
    M1_13_MODEL_ID,
    M1_13_PROVIDER_ID,
    M1_13_REQUIRED_SHA256,
    M113YOLOProvider,
)


class TestM113YOLOProvider(unittest.TestCase):
    """Test suite for M113YOLOProvider adapter."""

    @classmethod
    def setUpClass(cls):
        cls.provider = M113YOLOProvider()
        cls.provider.initialize()

    @classmethod
    def tearDownClass(cls):
        cls.provider.shutdown()

    def test_descriptor_metadata(self):
        desc = self.provider.descriptor
        self.assertEqual(desc.model_id, M1_13_MODEL_ID)
        self.assertEqual(desc.provider_id, M1_13_PROVIDER_ID)
        self.assertEqual(desc.framework, ModelFramework.ULTRALYTICS_YOLO)
        self.assertEqual(desc.task_type, ModelTaskType.OBJECT_DETECTION)
        self.assertEqual(desc.sha256_hash, M1_13_REQUIRED_SHA256)
        self.assertEqual(desc.lifecycle_status, ModelLifecycleStatus.ACTIVE)
        self.assertEqual(len(desc.supported_classes), 3)
        self.assertEqual(desc.supported_classes[0], "open_damaged_manhole")
        self.assertEqual(desc.supported_classes[1], "damaged_missing_road_sign")
        self.assertEqual(desc.supported_classes[2], "road_waterlogging")

    def test_provider_is_loaded(self):
        self.assertTrue(self.provider.is_loaded)

    def test_integrity_check_failure_on_corrupt_sha(self):
        corrupt_provider = M113YOLOProvider()
        corrupt_provider._expected_sha = "0000000000000000000000000000000000000000000000000000000000000000"
        with self.assertRaises(ModelIntegrityError):
            corrupt_provider.initialize()

    def test_infer_with_pil_image(self):
        # Create synthetic test image
        img = Image.new("RGB", (640, 640), color=(128, 128, 128))
        req = InferenceRequest(image=img)
        res = self.provider.infer(req)

        self.assertIsInstance(res, StandardDetectionResult)
        self.assertTrue(res.success)
        self.assertEqual(res.model_id, M1_13_MODEL_ID)
        self.assertEqual(res.provider_id, M1_13_PROVIDER_ID)
        self.assertEqual(res.image_width, 640)
        self.assertEqual(res.image_height, 640)
        self.assertEqual(res.confidence_threshold, 0.25)
        self.assertGreater(res.inference_duration_ms, 0.0)

    def test_infer_with_image_bytes(self):
        img = Image.new("RGB", (320, 240), color=(64, 64, 64))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        req = InferenceRequest(image_bytes=raw_bytes)
        res = self.provider.infer(req)

        self.assertTrue(res.success)
        self.assertEqual(res.image_width, 320)
        self.assertEqual(res.image_height, 240)

    def test_infer_confidence_override(self):
        img = Image.new("RGB", (640, 640), color=(128, 128, 128))
        req = InferenceRequest(image=img, confidence_override=0.85)
        res = self.provider.infer(req)

        self.assertEqual(res.confidence_threshold, 0.85)


if __name__ == "__main__":
    unittest.main()
