import io
import json
import base64
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from unittest.mock import patch

from app.main import app
from app.core.config import settings
from app.services.computer_vision import cv_model_service


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPRESENTATIVE_IMAGES = {
    "manhole": PROJECT_ROOT / "ai/computer_vision/dataset/images/test/manhole_img-14.jpg",
    "road_sign": PROJECT_ROOT / "ai/computer_vision/dataset/images/test/roadsign_IMG_8666_jpg.rf.e79ba09cf8bbb4ca1d2e1e223e5244be.jpg",
    "waterlogging": PROJECT_ROOT / "ai/computer_vision/dataset/images/test/waterlogging_waterloggingt-103-_jpg.rf.10009ec111cdef89d0e5a8fae80e493c.jpg",
    "negative_candidate": PROJECT_ROOT / "ai/computer_vision/dataset/images/test/roadsign_IMG_8100_jpg.rf.efaa0d300ce6c59199fb9f6203b98715.jpg",
}


def image_bytes(color: tuple[int, int, int] = (0, 0, 0)) -> bytes:
    image = Image.new("RGB", (320, 240), color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def gif_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), (0, 0, 0))
    output = io.BytesIO()
    image.save(output, format="GIF")
    return output.getvalue()


def decode_annotated_image(data_url: str) -> Image.Image:
    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        raise AssertionError("Annotated output is not a PNG data URL")
    image = Image.open(io.BytesIO(base64.b64decode(data_url[len(prefix):])))
    image.load()
    return image


class TestDetectionAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_valid_image_response_schema_and_coordinates(self):
        response = self.client.post(
            "/api/v1/detection/predict",
            files={"file": ("sample.png", image_bytes(), "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["model_version"], "M1.13-yolov8n")
        self.assertEqual(data["total_detections"], len(data["detections"]))
        annotated = decode_annotated_image(data["annotated_image"])
        self.assertEqual(annotated.format, "PNG")
        self.assertEqual(annotated.size, (320, 240))
        for detection in data["detections"]:
            self.assertIsInstance(detection["class_id"], int)
            self.assertIn(detection["class_id"], {0, 1, 2})
            self.assertIsInstance(detection["class_name"], str)
            self.assertIsInstance(detection["confidence"], float)
            self.assertGreaterEqual(detection["confidence"], 0.0)
            self.assertLessEqual(detection["confidence"], 1.0)
            box = detection["bbox"]
            self.assertLessEqual(0, box["x1"])
            self.assertLessEqual(box["x1"], box["x2"])
            self.assertLessEqual(box["x2"], 320)
            self.assertLessEqual(0, box["y1"])
            self.assertLessEqual(box["y1"], box["y2"])
            self.assertLessEqual(box["y2"], 240)

    def test_blank_image_returns_no_detection_structure(self):
        response = self.client.post(
            "/api/v1/detection/predict",
            files={"file": ("blank.png", image_bytes(), "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_detections"], 0)
        self.assertEqual(data["detections"], [])

    def test_invalid_non_image_upload(self):
        response = self.client.post(
            "/api/v1/detection/predict",
            files={"file": ("not-an-image.jpg", b"plain text", "image/jpeg")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "The uploaded file is not a readable image.")

    def test_empty_upload(self):
        response = self.client.post(
            "/api/v1/detection/predict",
            files={"file": ("empty.png", b"", "image/png")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "The uploaded file is empty.")

    def test_unsupported_image_format(self):
        response = self.client.post(
            "/api/v1/detection/predict",
            files={"file": ("sample.gif", gif_bytes(), "image/gif")},
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("Unsupported image format", response.json()["detail"])

    def test_model_unavailable(self):
        original_state = cv_model_service._is_loaded
        try:
            cv_model_service._is_loaded = False
            response = self.client.post(
                "/api/v1/detection/predict",
                files={"file": ("sample.png", image_bytes(), "image/png")},
            )
        finally:
            cv_model_service._is_loaded = original_state
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Detection model is unavailable.")

    def test_oversized_upload_is_rejected(self):
        with patch.object(settings, "MAX_IMAGE_UPLOAD_BYTES", 16):
            response = self.client.post(
                "/api/v1/detection/predict",
                files={"file": ("large.png", image_bytes(), "image/png")},
            )
        self.assertEqual(response.status_code, 413)

    def test_excessive_pixel_dimensions_are_rejected(self):
        with patch.object(settings, "MAX_IMAGE_PIXELS", 100):
            response = self.client.post(
                "/api/v1/detection/predict",
                files={"file": ("large-dimensions.png", image_bytes(), "image/png")},
            )
        self.assertEqual(response.status_code, 413)

    def test_representative_real_images_preserve_response_integrity(self):
        expected_classes = {
            0: "open_damaged_manhole",
            1: "damaged_missing_road_sign",
            2: "road_waterlogging",
        }
        for image_path in REPRESENTATIVE_IMAGES.values():
            self.assertTrue(image_path.is_file(), image_path)
            with Image.open(image_path) as image:
                image_width, image_height = image.size
            response = self.client.post(
                "/api/v1/detection/predict",
                files={"file": (image_path.name, image_path.read_bytes(), "image/jpeg")},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            json.dumps(data)
            self.assertTrue(data["success"])
            self.assertEqual(data["model_version"], settings.YOLO_MODEL_VERSION)
            self.assertEqual(data["total_detections"], len(data["detections"]))
            annotated = decode_annotated_image(data["annotated_image"])
            self.assertEqual(annotated.format, "PNG")
            self.assertEqual(annotated.size, (image_width, image_height))
            if image_path == REPRESENTATIVE_IMAGES["manhole"]:
                with Image.open(image_path) as original:
                    self.assertNotEqual(annotated.tobytes(), original.convert("RGB").tobytes())
            for detection in data["detections"]:
                self.assertIn(detection["class_id"], expected_classes)
                self.assertEqual(detection["class_name"], expected_classes[detection["class_id"]])
                self.assertGreaterEqual(detection["confidence"], 0.0)
                self.assertLessEqual(detection["confidence"], 1.0)
                box = detection["bbox"]
                self.assertTrue(0 <= box["x1"] < box["x2"] <= image_width)
                self.assertTrue(0 <= box["y1"] < box["y2"] <= image_height)

    def test_genuine_negative_image_returns_no_detections(self):
        image_path = REPRESENTATIVE_IMAGES["negative_candidate"]
        response = self.client.post(
            "/api/v1/detection/predict",
            files={"file": (image_path.name, image_path.read_bytes(), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        with Image.open(image_path) as original:
            original_size = original.size
        annotated = decode_annotated_image(data["annotated_image"])
        self.assertEqual(data["total_detections"], 0)
        self.assertEqual(data["detections"], [])
        self.assertEqual(annotated.size, original_size)
        self.assertEqual(annotated.format, "PNG")
        with Image.open(image_path) as original:
            self.assertEqual(annotated.tobytes(), original.convert("RGB").tobytes())

    def test_malformed_image_is_rejected_without_internal_details(self):
        response = self.client.post(
            "/api/v1/detection/predict",
            files={"file": ("malformed.png", b"\x89PNG\r\n\x00", "image/png")},
        )
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"]
        self.assertNotIn("C:\\", detail)
        self.assertNotIn("Traceback", detail)

    def test_oversized_upload_is_rejected_before_image_processing(self):
        response = self.client.post(
            "/api/v1/detection/predict",
            files={"file": ("oversized.png", b"x" * (settings.MAX_IMAGE_UPLOAD_BYTES + 1), "image/png")},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "The uploaded image exceeds the maximum allowed size.")

    def test_configured_threshold_is_respected_on_real_inference(self):
        image_path = REPRESENTATIVE_IMAGES["manhole"]
        original_threshold = settings.YOLO_CONFIDENCE_THRESHOLD
        try:
            settings.YOLO_CONFIDENCE_THRESHOLD = 0.25
            baseline = self.client.post(
                "/api/v1/detection/predict",
                files={"file": (image_path.name, image_path.read_bytes(), "image/jpeg")},
            ).json()
            settings.YOLO_CONFIDENCE_THRESHOLD = 0.75
            filtered = self.client.post(
                "/api/v1/detection/predict",
                files={"file": (image_path.name, image_path.read_bytes(), "image/jpeg")},
            ).json()
        finally:
            settings.YOLO_CONFIDENCE_THRESHOLD = original_threshold

        self.assertGreater(baseline["total_detections"], filtered["total_detections"])
        self.assertTrue(all(item["confidence"] >= 0.75 for item in filtered["detections"]))


if __name__ == "__main__":
    unittest.main()