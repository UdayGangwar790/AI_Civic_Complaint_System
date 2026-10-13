import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.location import (
    LocationProviderError,
    LocationProviderRateLimited,
    LocationProviderTimeout,
    ReverseGeocodingResult,
)


class TestLocationAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    @patch("app.services.location.reverse_geocoder.reverse_geocode")
    def test_valid_coordinates_return_normalized_provider_response(self, mock_reverse):
        mock_reverse.return_value = ReverseGeocodingResult(
            display_name="Civic Road, Sample City",
            road="Civic Road",
            area="Central Area",
            city="Sample City",
            district="Sample District",
            municipality="Sample Municipality",
            state="Sample State",
            country="Sample Country",
        )
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["latitude"], 12.34)
        self.assertEqual(response.json()["longitude"], 56.78)
        self.assertEqual(response.json()["road"], "Civic Road")
        self.assertEqual(response.json()["district"], "Sample District")
        self.assertEqual(response.json()["resolution_status"], "resolved")
        self.assertEqual(response.json()["jurisdiction"], {
            "level": "administrative_context",
            "name": "Sample Municipality",
            "source": "OpenStreetMap Nominatim",
            "confidence": None,
        })
        mock_reverse.assert_called_once_with(12.34, 56.78)

    @patch("app.services.location.reverse_geocoder.reverse_geocode")
    def test_road_missing_returns_partial_context_and_message(self, mock_reverse):
        mock_reverse.return_value = ReverseGeocodingResult(city="Sample City", state="Sample State")
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=12.34&longitude=56.78")
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(data["road"])
        self.assertEqual(data["resolution_status"], "partial")
        self.assertEqual(data["message"], "Road information could not be resolved for these coordinates.")

    @patch("app.services.location.reverse_geocoder.reverse_geocode")
    def test_partial_administrative_response_preserves_available_fields(self, mock_reverse):
        mock_reverse.return_value = ReverseGeocodingResult(road="Known Road", district="Known District")
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=12.34&longitude=56.78")
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["road"], "Known Road")
        self.assertEqual(data["district"], "Known District")
        self.assertIsNone(data["city"])
        self.assertEqual(data["resolution_status"], "resolved")

    @patch("app.services.location.reverse_geocoder.reverse_geocode")
    def test_unresolved_provider_result_has_unknown_jurisdiction(self, mock_reverse):
        mock_reverse.return_value = ReverseGeocodingResult()
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=12.34&longitude=56.78")
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(data["jurisdiction"])
        self.assertEqual(data["resolution_status"], "unresolved")
        self.assertIsNotNone(data["message"])

    def test_invalid_latitude_is_rejected(self):
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=91&longitude=0")
        self.assertEqual(response.status_code, 422)

    def test_invalid_longitude_is_rejected(self):
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=0&longitude=181")
        self.assertEqual(response.status_code, 422)

    def test_missing_parameters_are_rejected(self):
        response = self.client.get("/api/v1/location/reverse-geocode")
        self.assertEqual(response.status_code, 422)

    @patch("app.api.v1.location.reverse_geocode", side_effect=LocationProviderTimeout)
    def test_provider_timeout_is_safe(self, mock_reverse):
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["detail"], "Location provider timed out.")
        mock_reverse.assert_called_once()

    @patch("app.api.v1.location.reverse_geocode", side_effect=LocationProviderError)
    def test_provider_error_is_safe(self, mock_reverse):
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Location information is temporarily unavailable.")
        self.assertNotIn("Traceback", response.text)
        mock_reverse.assert_called_once()

    @patch("app.api.v1.location.reverse_geocode", side_effect=LocationProviderRateLimited)
    def test_provider_rate_limit_is_safe(self, mock_reverse):
        response = self.client.get("/api/v1/location/reverse-geocode?latitude=12.34&longitude=56.78")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], "Location provider rate limit reached.")
        mock_reverse.assert_called_once()

    @patch("app.services.location.urlopen", side_effect=TimeoutError)
    def test_nominatim_timeout_uses_configured_timeout_and_returns_gateway_timeout(self, mock_urlopen):
        response = self.client.get(
            "/api/v1/location/reverse-geocode?latitude=12.34&longitude=56.78"
        )
        self.assertEqual(response.status_code, 504)
        self.assertNotIn("road", response.json())
        self.assertEqual(
            mock_urlopen.call_args.kwargs["timeout"],
            settings.REVERSE_GEOCODER_TIMEOUT_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
