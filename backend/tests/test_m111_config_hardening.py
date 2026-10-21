"""
CVKI - Civic Vision & Knowledge Intelligence
Module 11.1: Production Configuration & Environment Hardening Tests
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings


def test_environment_validation_rejects_invalid():
    with pytest.raises(ValidationError, match="ENVIRONMENT must be development, test, or production"):
        Settings(ENVIRONMENT="staging_invalid")


def test_production_rejects_default_or_weak_jwt_secret():
    with pytest.raises(ValidationError, match="Production requires a non-default JWT_SECRET"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="replace-with-a-random-secret-of-at-least-32-characters",
            CORS_ALLOWED_ORIGINS="https://civic.karnataka.gov.in",
            MONGODB_URI="mongodb://prod_user:prod_pass@mongo.internal:27017/cvki",
        )

    with pytest.raises(ValidationError, match="Production requires a non-default JWT_SECRET"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="short_secret",
            CORS_ALLOWED_ORIGINS="https://civic.karnataka.gov.in",
            MONGODB_URI="mongodb://prod_user:prod_pass@mongo.internal:27017/cvki",
        )


def test_production_rejects_insecure_cors():
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS entries must use HTTPS"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="abcdef1234567890abcdef1234567890_strong_secret!",
            CORS_ALLOWED_ORIGINS="http://insecure.example.com",
            MONGODB_URI="mongodb://prod_user:prod_pass@mongo.internal:27017/cvki",
        )

    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS cannot contain '\\*'"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="abcdef1234567890abcdef1234567890_strong_secret!",
            CORS_ALLOWED_ORIGINS="*",
            MONGODB_URI="mongodb://prod_user:prod_pass@mongo.internal:27017/cvki",
        )


def test_production_rejects_default_unauthenticated_mongodb_uri():
    with pytest.raises(ValidationError, match="Production requires an explicitly configured, secure MONGODB_URI"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="abcdef1234567890abcdef1234567890_strong_secret!",
            CORS_ALLOWED_ORIGINS="https://civic.karnataka.gov.in",
            MONGODB_URI="mongodb://localhost:27017",
            COOKIE_SECURE=True,
        )


def test_production_rejects_unconfigured_cpmgrams_when_enabled():
    with pytest.raises(ValidationError, match="CPGRAMS_ENABLED in production requires a valid CPGRAMS_API_KEY"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="abcdef1234567890abcdef1234567890_strong_secret!",
            CORS_ALLOWED_ORIGINS="https://civic.karnataka.gov.in",
            MONGODB_URI="mongodb://prod_user:prod_pass@mongo.internal:27017/cvki",
            CPGRAMS_ENABLED=True,
            CPGRAMS_API_KEY="",
            CPGRAMS_CLIENT_ID="client123",
            CPGRAMS_BASE_URL="https://pgportal.gov.in/api/v1",
            COOKIE_SECURE=True,
        )


def test_production_valid_configuration_succeeds():
    prod_settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET="abcdef1234567890abcdef1234567890_strong_production_secret!",
        CORS_ALLOWED_ORIGINS="https://civic.karnataka.gov.in,https://admin.civic.karnataka.gov.in",
        MONGODB_URI="mongodb://prod_user:prod_pass@mongo.internal:27017/cvki",
        COOKIE_SECURE=True,
        CPGRAMS_ENABLED=True,
        CPGRAMS_API_KEY="prod_official_cpgrams_api_key_48194",
        CPGRAMS_CLIENT_ID="MORTH_PROD_01",
        CPGRAMS_BASE_URL="https://pgportal.gov.in/api/v1",
    )
    assert prod_settings.ENVIRONMENT == "production"
    assert prod_settings.auth_cookie_secure is True
    assert len(prod_settings.allowed_cors_origins) == 2


def test_secrets_masked_in_repr():
    repr_str = repr(settings)
    assert settings.JWT_SECRET not in repr_str
    assert "JWT_SECRET" not in repr_str or "repr=False" in str(Settings.model_fields["JWT_SECRET"])
    assert settings.MONGODB_URI not in repr_str or "localhost:27017" not in repr_str
