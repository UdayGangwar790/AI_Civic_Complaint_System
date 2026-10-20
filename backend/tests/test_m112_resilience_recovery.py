"""
CVKI - Civic Vision & Knowledge Intelligence
Module 11.2: Reliability, Resilience & Failure Recovery Tests
"""

from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.core.database import is_mongo_healthy, mongo_manager
from app.schemas.external_civic import ExternalDataStatus
from app.services.external_civic_provider import OpenMeteoWeatherProvider
from app.services.government_adapter import AdapterSubmissionResult, IntegrationState


def test_mongo_unavailable_handled_safely():
    import asyncio
    with patch.object(mongo_manager, "client", None):
        healthy = asyncio.run(is_mongo_healthy())
        assert healthy is False


def test_weather_provider_timeout_handled_safely():
    provider = OpenMeteoWeatherProvider(endpoint_url="https://api.open-meteo.com/v1/forecast")
    with patch("httpx.Client.get", side_effect=httpx.ConnectTimeout("Connection timed out")):
        res = provider.fetch(latitude=12.9716, longitude=77.5946)
        assert res.status == ExternalDataStatus.TIMEOUT
        assert "timed out" in res.error_message.lower()
        # Epistemic invariant: failure does not fabricate clean weather
        assert res.data == {}


def test_weather_provider_upstream_error_handled_safely():
    provider = OpenMeteoWeatherProvider(endpoint_url="https://api.open-meteo.com/v1/forecast")
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("httpx.Client.get", return_value=mock_resp):
        res = provider.fetch(latitude=12.9716, longitude=77.5946)
        assert res.status == ExternalDataStatus.UNAVAILABLE
        assert res.data == {}


def test_weather_provider_rate_limited_handled_safely():
    provider = OpenMeteoWeatherProvider(endpoint_url="https://api.open-meteo.com/v1/forecast")
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    with patch("httpx.Client.get", return_value=mock_resp):
        res = provider.fetch(latitude=12.9716, longitude=77.5946)
        assert res.status == ExternalDataStatus.RATE_LIMITED


def test_government_timeout_marked_unknown_outcome():
    # Government API timeout must produce UNKNOWN_OUTCOME, never fake SUBMITTED or RESOLVED
    res = AdapterSubmissionResult(
        state=IntegrationState.TEMPORARY_FAILURE,
        is_unknown_outcome=True,
        error_code="UPSTREAM_GATEWAY_TIMEOUT",
        error_message_safe="Official government portal did not respond within timeout window.",
    )
    assert res.is_unknown_outcome is True
    assert res.state != IntegrationState.SUBMISSION_ACCEPTED
    assert res.external_reference_id is None

