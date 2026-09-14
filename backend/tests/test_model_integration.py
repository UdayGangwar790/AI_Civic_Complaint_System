import unittest
from fastapi.testclient import TestClient

import backend.app
from app.main import app
from app.services.computer_vision import YOLOModelService, cv_model_service
from app.core.config import settings


class TestModelIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Enter TestClient context manager to trigger FastAPI lifespan startup events.
        """
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        """
        Exit TestClient context manager to trigger lifespan shutdown events.
        """
        cls.client_cm.__exit__(None, None, None)

    def test_01_health_check_endpoint(self):
        """
        Verify existing GET /api/health endpoint returns 200 OK and expected structure.
        """
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "CVKI backend")

    def test_02_root_endpoint(self):
        """
        Verify root endpoint GET / returns welcome message.
        """
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("CVKI Backend API", data["message"])

    def test_03_model_status_endpoint(self):
        """
        Verify GET /api/v1/model/status returns 200 OK, loaded=True, and exact class mappings.
        """
        response = self.client.get("/api/v1/model/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # 1. Verification of load state
        self.assertTrue(data["loaded"])
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["model_name"], "yolov8n")
        self.assertEqual(data["model_version"], "M1.13-yolov8n")
        self.assertEqual(data["num_classes"], 3)

        # 2. Exact class mapping verification
        classes = {int(k): v for k, v in data["classes"].items()}
        self.assertEqual(classes[0], "open_damaged_manhole")
        self.assertEqual(classes[1], "damaged_missing_road_sign")
        self.assertEqual(classes[2], "road_waterlogging")
        self.assertEqual(len(classes), 3)

        # 3. Security check: Ensure internal server filesystem paths are NOT exposed
        raw_str = str(data)
        self.assertNotIn("weights", raw_str)
        self.assertNotIn("best.pt", raw_str)
        self.assertNotIn("Users", raw_str)
        self.assertNotIn("runs", raw_str)

    def test_04_model_status_alias_endpoint(self):
        """
        Verify GET /api/model/status alias also returns 200 OK and matches v1 response.
        """
        v1_resp = self.client.get("/api/v1/model/status")
        alias_resp = self.client.get("/api/model/status")
        self.assertEqual(alias_resp.status_code, 200)
        self.assertEqual(alias_resp.json(), v1_resp.json())

    def test_05_model_missing_error_handling(self):
        """
        Verify isolated YOLOModelService correctly handles missing model files.
        """
        isolated_service = YOLOModelService()
        success = isolated_service.load_model(custom_path="non_existent_weights_xyz123.pt")
        self.assertFalse(success)
        self.assertFalse(isolated_service.is_loaded)

        status = isolated_service.get_model_status()
        self.assertFalse(status["loaded"])
        self.assertEqual(status["status"], "error")
        self.assertIn("not found", status["error"].lower())
        self.assertEqual(status["num_classes"], 0)

        with self.assertRaises(RuntimeError) as ctx:
            isolated_service.get_model()
        self.assertIn("not loaded", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
