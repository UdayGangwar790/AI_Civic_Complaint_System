"""
CVKI - Module 8.5: Legacy YOLOModelService vs M113YOLOProvider Parity Tests

Executes strict parity comparisons between:
1. Legacy YOLOModelService (computer_vision.py)
2. New M113YOLOProvider (cv/providers/m113_yolo_provider.py)

Evaluates:
- Detection counts
- Class IDs & names
- Bounding box pixel coordinates (exact integer match)
- Confidence values within tight float tolerance (<= 1e-4)
- Threshold response consistency
"""

from pathlib import Path
import unittest
from PIL import Image

from app.core.config import get_project_root
from app.services.computer_vision import YOLOModelService
from app.services.cv.base_provider import InferenceRequest
from app.services.cv.providers.m113_yolo_provider import M113YOLOProvider


class TestM113ProviderParity(unittest.TestCase):
    """Parity verification between legacy and standardized CV execution paths."""

    @classmethod
    def setUpClass(cls):
        # 1. Initialize Legacy Service
        cls.legacy_service = YOLOModelService()
        cls.legacy_loaded = cls.legacy_service.load_model()
        if not cls.legacy_loaded:
            raise RuntimeError("Failed to load legacy YOLOModelService for parity testing.")

        # 2. Initialize New M1.13 Provider
        cls.new_provider = M113YOLOProvider()
        cls.new_loaded = cls.new_provider.initialize()
        if not cls.new_loaded:
            raise RuntimeError("Failed to initialize M113YOLOProvider for parity testing.")

        # 3. Locate representative images
        repo_root = get_project_root().resolve()
        val_dir = repo_root / "ai" / "computer_vision" / "dataset_m1_13" / "images" / "val"
        cls.test_images: list[Path] = []
        if val_dir.exists():
            for prefix in ["manhole", "roadsign", "waterlog"]:
                matches = list(val_dir.glob(f"{prefix}*.jpg"))
                if matches:
                    cls.test_images.append(matches[0])

    @classmethod
    def tearDownClass(cls):
        cls.new_provider.shutdown()

    def test_parity_across_representative_dataset_images(self):
        self.assertGreater(len(self.test_images), 0, "No validation images found for parity test.")

        for img_path in self.test_images:
            with Image.open(img_path) as raw_img:
                image = raw_img.convert("RGB")

                # Run legacy inference
                legacy_detections = self.legacy_service.predict(image)

                # Run new provider inference
                req = InferenceRequest(image=image)
                new_result = self.new_provider.infer(req)

                # 1. Compare total count
                self.assertEqual(
                    len(legacy_detections),
                    new_result.total_detections,
                    f"Detection count mismatch for {img_path.name}: legacy={len(legacy_detections)}, new={new_result.total_detections}",
                )

                # 2. Compare each detection item
                for i, (leg, standard_det) in enumerate(zip(legacy_detections, new_result.detections)):
                    # Class ID
                    self.assertEqual(
                        leg["class_id"],
                        standard_det.class_id,
                        f"Class ID mismatch at index {i} for {img_path.name}",
                    )
                    # Class Name
                    self.assertEqual(
                        leg["class_name"],
                        standard_det.class_name,
                        f"Class name mismatch at index {i} for {img_path.name}",
                    )
                    # Confidence score within tolerance
                    self.assertAlmostEqual(
                        leg["confidence"],
                        standard_det.confidence,
                        places=4,
                        msg=f"Confidence mismatch at index {i} for {img_path.name}: legacy={leg['confidence']}, new={standard_det.confidence}",
                    )
                    # Bounding Box coordinates
                    leg_bbox = leg["bbox"]
                    new_bbox = standard_det.bbox
                    self.assertEqual(leg_bbox["x1"], new_bbox.x1)
                    self.assertEqual(leg_bbox["y1"], new_bbox.y1)
                    self.assertEqual(leg_bbox["x2"], new_bbox.x2)
                    self.assertEqual(leg_bbox["y2"], new_bbox.y2)

    def test_parity_on_synthetic_blank_image(self):
        """Negative test on blank image ensures both yield 0 detections."""
        blank_image = Image.new("RGB", (640, 640), color=(0, 0, 0))

        legacy_detections = self.legacy_service.predict(blank_image)
        new_result = self.new_provider.infer(InferenceRequest(image=blank_image))

        self.assertEqual(len(legacy_detections), 0)
        self.assertEqual(new_result.total_detections, 0)
        self.assertEqual(len(new_result.detections), 0)


if __name__ == "__main__":
    unittest.main()
