"""
CVKI - Module 8.4: Standardized Computer Vision Output Contract Tests

Tests verification of framework-agnostic data contracts:
- Valid detection creation
- Multiple detections handling
- Empty detections handling
- Confidence validation boundaries [0.0, 1.0]
- Bounding box geometry and inversion validation
- JSON serialization and deserialization
- Extensible metadata handling
- Image dimensions and inference timing metadata
- Model identity and provider metadata synchronization
- Determinism and immutability checks
"""

import json
from datetime import datetime, timezone
import unittest
from pydantic import ValidationError

from app.services.cv.base_provider import (
    ModelTaskType,
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)


class TestStandardBoundingBox(unittest.TestCase):
    """Test suite for StandardBoundingBox schema and coordinate validation."""

    def test_valid_bounding_box(self):
        bbox = StandardBoundingBox(x1=10, y1=20, x2=100, y2=150)
        self.assertEqual(bbox.x1, 10)
        self.assertEqual(bbox.y1, 20)
        self.assertEqual(bbox.x2, 100)
        self.assertEqual(bbox.y2, 150)
        self.assertEqual(bbox.width, 90)
        self.assertEqual(bbox.height, 130)
        self.assertEqual(bbox.area, 90 * 130)

    def test_zero_area_bounding_box(self):
        """Points and lines with x1 == x2 or y1 == y2 are geometrically valid non-negative coordinates."""
        bbox = StandardBoundingBox(x1=50, y1=50, x2=50, y2=50)
        self.assertEqual(bbox.width, 0)
        self.assertEqual(bbox.height, 0)
        self.assertEqual(bbox.area, 0)

    def test_negative_coordinates_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            StandardBoundingBox(x1=-5, y1=10, x2=50, y2=60)
        self.assertIn("cannot be negative", str(ctx.exception))

        with self.assertRaises(ValidationError) as ctx:
            StandardBoundingBox(x1=5, y1=-10, x2=50, y2=60)
        self.assertIn("cannot be negative", str(ctx.exception))

    def test_inverted_coordinates_rejected(self):
        # x1 > x2
        with self.assertRaises(ValidationError) as ctx:
            StandardBoundingBox(x1=120, y1=20, x2=100, y2=150)
        self.assertIn("x1 (120) cannot exceed x2 (100)", str(ctx.exception))

        # y1 > y2
        with self.assertRaises(ValidationError) as ctx:
            StandardBoundingBox(x1=10, y1=200, x2=100, y2=150)
        self.assertIn("y1 (200) cannot exceed y2 (150)", str(ctx.exception))

    def test_normalized_coordinates_valid(self):
        bbox = StandardBoundingBox(
            x1=64, y1=48, x2=192, y2=144,
            norm_x1=0.1, norm_y1=0.1, norm_x2=0.3, norm_y2=0.3
        )
        self.assertEqual(bbox.norm_x1, 0.1)
        self.assertEqual(bbox.norm_x2, 0.3)

    def test_inverted_normalized_coordinates_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            StandardBoundingBox(
                x1=10, y1=10, x2=50, y2=50,
                norm_x1=0.8, norm_y1=0.1, norm_x2=0.2, norm_y2=0.5
            )
        self.assertIn("norm_x1", str(ctx.exception))


class TestStandardDetection(unittest.TestCase):
    """Test suite for StandardDetection atomic detection contracts."""

    def test_valid_detection(self):
        bbox = StandardBoundingBox(x1=50, y1=60, x2=150, y2=180)
        det = StandardDetection(
            class_id=0,
            class_name="open_damaged_manhole",
            confidence=0.854,
            bbox=bbox,
            category="road_hazard",
            metadata={"source_sensor": "dashcam_1"},
        )
        self.assertEqual(det.class_id, 0)
        self.assertEqual(det.class_name, "open_damaged_manhole")
        self.assertAlmostEqual(det.confidence, 0.854)
        self.assertEqual(det.bbox.x1, 50)
        self.assertEqual(det.category, "road_hazard")
        self.assertEqual(det.metadata["source_sensor"], "dashcam_1")

    def test_confidence_boundaries(self):
        bbox = StandardBoundingBox(x1=0, y1=0, x2=10, y2=10)

        # 0.0 is valid
        det_zero = StandardDetection(class_id=1, class_name="damaged_missing_road_sign", confidence=0.0, bbox=bbox)
        self.assertEqual(det_zero.confidence, 0.0)

        # 1.0 is valid
        det_one = StandardDetection(class_id=2, class_name="road_waterlogging", confidence=1.0, bbox=bbox)
        self.assertEqual(det_one.confidence, 1.0)

        # < 0.0 rejected
        with self.assertRaises(ValidationError):
            StandardDetection(class_id=0, class_name="test", confidence=-0.01, bbox=bbox)

        # > 1.0 rejected
        with self.assertRaises(ValidationError):
            StandardDetection(class_id=0, class_name="test", confidence=1.0001, bbox=bbox)

    def test_empty_class_name_rejected(self):
        bbox = StandardBoundingBox(x1=0, y1=0, x2=10, y2=10)
        with self.assertRaises(ValidationError):
            StandardDetection(class_id=0, class_name="", confidence=0.5, bbox=bbox)


class TestStandardDetectionResult(unittest.TestCase):
    """Test suite for StandardDetectionResult and aggregate metadata contract."""

    def test_empty_detections_result(self):
        res = StandardDetectionResult(
            success=True,
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            total_detections=0,
            detections=[],
            inference_duration_ms=12.5,
            image_width=640,
            image_height=480,
            confidence_threshold=0.25,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.total_detections, 0)
        self.assertEqual(len(res.detections), 0)
        self.assertEqual(res.image_width, 640)
        self.assertEqual(res.image_height, 480)
        self.assertEqual(res.confidence_threshold, 0.25)
        self.assertIsInstance(res.inference_timestamp, datetime)

    def test_multiple_detections_result(self):
        d1 = StandardDetection(
            class_id=0,
            class_name="open_damaged_manhole",
            confidence=0.88,
            bbox=StandardBoundingBox(x1=20, y1=30, x2=80, y2=90),
        )
        d2 = StandardDetection(
            class_id=2,
            class_name="road_waterlogging",
            confidence=0.74,
            bbox=StandardBoundingBox(x1=100, y1=150, x2=300, y2=350),
        )
        res = StandardDetectionResult(
            success=True,
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            model_hash="602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3",
            provider_id="m113_yolo_provider",
            task_type=ModelTaskType.OBJECT_DETECTION,
            total_detections=2,
            detections=[d1, d2],
            inference_duration_ms=18.4,
            image_width=640,
            image_height=480,
            confidence_threshold=0.25,
            provider_metadata={"device": "cpu", "precision": "fp32"},
        )
        self.assertEqual(res.total_detections, 2)
        self.assertEqual(res.detections[0].class_name, "open_damaged_manhole")
        self.assertEqual(res.detections[1].class_name, "road_waterlogging")
        self.assertEqual(res.model_hash, "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3")
        self.assertEqual(res.provider_id, "m113_yolo_provider")
        self.assertEqual(res.task_type, ModelTaskType.OBJECT_DETECTION)
        self.assertEqual(res.metadata["device"], "cpu")

    def test_metadata_bidirectional_synchronization(self):
        res1 = StandardDetectionResult(
            success=True,
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            total_detections=0,
            provider_metadata={"key_a": "val_a"},
        )
        self.assertEqual(res1.metadata.get("key_a"), "val_a")

        res2 = StandardDetectionResult(
            success=True,
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            total_detections=0,
            metadata={"key_b": "val_b"},
        )
        self.assertEqual(res2.provider_metadata.get("key_b"), "val_b")

    def test_json_serialization_and_deserialization(self):
        d1 = StandardDetection(
            class_id=1,
            class_name="damaged_missing_road_sign",
            confidence=0.912,
            bbox=StandardBoundingBox(x1=10, y1=15, x2=45, y2=80, norm_x1=0.1, norm_y1=0.15, norm_x2=0.45, norm_y2=0.8),
            metadata={"occlusion": 0.15},
        )
        res = StandardDetectionResult(
            success=True,
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            model_hash="602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3",
            provider_id="m113_yolo_provider",
            task_type="object_detection",
            total_detections=1,
            detections=[d1],
            inference_duration_ms=21.2,
            image_width=100,
            image_height=100,
            confidence_threshold=0.25,
            provider_metadata={"runtime": "local_cpu"},
        )

        json_str = res.model_dump_json()
        self.assertIsInstance(json_str, str)
        raw_dict = json.loads(json_str)

        self.assertEqual(raw_dict["model_id"], "m1.13-yolov8n")
        self.assertEqual(raw_dict["total_detections"], 1)
        self.assertEqual(raw_dict["detections"][0]["class_name"], "damaged_missing_road_sign")
        self.assertEqual(raw_dict["detections"][0]["bbox"]["x2"], 45)

        # Roundtrip deserialization
        reconstructed = StandardDetectionResult.model_validate_json(json_str)
        self.assertEqual(reconstructed.model_id, res.model_id)
        self.assertEqual(reconstructed.total_detections, 1)
        self.assertEqual(reconstructed.detections[0].confidence, 0.912)
        self.assertEqual(reconstructed.detections[0].bbox.width, 35)
        self.assertEqual(reconstructed.detections[0].bbox.height, 65)

    def test_deterministic_output_contract(self):
        """Repeated serialization produces identical JSON keys and structure."""
        res = StandardDetectionResult(
            success=True,
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            total_detections=0,
            detections=[],
            inference_duration_ms=10.0,
            inference_timestamp=datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc),
        )
        d1 = res.model_dump()
        d2 = res.model_dump()
        self.assertEqual(d1, d2)


if __name__ == "__main__":
    unittest.main()
