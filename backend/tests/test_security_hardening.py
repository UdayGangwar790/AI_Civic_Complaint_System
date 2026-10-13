import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.csrf import create_csrf_token
from app.core.security import create_access_token
from app.core.rate_limit import rate_limiter
from app.api.v1.auth import _set_auth_cookies
from app.main import app
from fastapi import Response


class TestSecurityHardening(unittest.TestCase):
    def setUp(self):
        rate_limiter.reset()
        self.client = TestClient(app)
        self.auth_token = create_access_token("usr_csrf_test", "csrf@example.com")
        self.csrf_token = create_csrf_token(self.auth_token)
        self.client.cookies.set(settings.AUTH_COOKIE_NAME, self.auth_token)
        self.client.cookies.set(settings.CSRF_COOKIE_NAME, self.csrf_token)

    def tearDown(self):
        rate_limiter.reset()

    def test_valid_csrf_allows_cookie_authenticated_mutation(self):
        response = self.client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(response.status_code, 204)

    def test_missing_csrf_token_is_rejected(self):
        response = self.client.post("/api/v1/auth/logout")
        self.assertEqual(response.status_code, 403)

    def test_invalid_csrf_token_is_rejected(self):
        response = self.client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": "invalid"},
        )
        self.assertEqual(response.status_code, 403)

    def test_safe_get_does_not_require_csrf(self):
        for method in ("GET", "HEAD", "OPTIONS"):
            with self.subTest(method=method):
                response = self.client.request(method, "/")
                self.assertNotEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_invalid_and_expired_cookie_tokens_are_rejected(self):
        self.client.cookies.set(settings.AUTH_COOKIE_NAME, "invalid")
        invalid = self.client.get("/api/v1/auth/me")
        self.assertEqual(invalid.status_code, 401)

        from datetime import timedelta

        expired = create_access_token(
            "usr_expired_test",
            "expired@example.com",
            expires_delta=timedelta(seconds=-1),
        )
        self.client.cookies.set(settings.AUTH_COOKIE_NAME, expired)
        rejected = self.client.get("/api/v1/auth/me")
        self.assertEqual(rejected.status_code, 401)

    def test_production_cookie_defaults_are_secure(self):
        secret = "A strong random production secret 4921!"
        config = Settings(
            _env_file=None,
            ENVIRONMENT="production",
            JWT_SECRET=secret,
            CORS_ALLOWED_ORIGINS="https://cvki.example.gov",
        )
        self.assertTrue(config.auth_cookie_secure)
        self.assertEqual(config.COOKIE_SAMESITE, "lax")
        self.assertNotIn(secret, repr(config))

    def test_auth_cookie_is_secure_in_production(self):
        original_environment = settings.ENVIRONMENT
        original_cookie_secure = settings.COOKIE_SECURE
        try:
            settings.ENVIRONMENT = "production"
            settings.COOKIE_SECURE = None
            response = Response()
            _set_auth_cookies(response, self.auth_token)
            auth_cookie = next(
                value for value in response.headers.getlist("set-cookie")
                if value.startswith(f"{settings.AUTH_COOKIE_NAME}=")
            )
            self.assertIn("HttpOnly", auth_cookie)
            self.assertIn("Secure", auth_cookie)
            self.assertIn("SameSite=lax", auth_cookie)
        finally:
            settings.ENVIRONMENT = original_environment
            settings.COOKIE_SECURE = original_cookie_secure

    def test_configured_cors_origin_is_allowed(self):
        response = self.client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": settings.allowed_cors_origins[0],
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            settings.allowed_cors_origins[0],
        )

    def test_production_rejects_missing_or_example_jwt_secret(self):
        for secret in ("", "your_super_secret_jwt_key_at_least_32_bytes_long", "short", "s" * 48):
            with self.subTest(secret=secret):
                with self.assertRaises(ValidationError):
                    Settings(
                        _env_file=None,
                        ENVIRONMENT="production",
                        JWT_SECRET=secret,
                        CORS_ALLOWED_ORIGINS="https://cvki.example.gov",
                    )

    def test_validation_error_does_not_render_secret(self):
        secret = "your_super_secret_jwt_key_at_least_32_bytes_long"
        try:
            Settings(
                _env_file=None,
                ENVIRONMENT="production",
                JWT_SECRET=secret,
                CORS_ALLOWED_ORIGINS="https://cvki.example.gov",
            )
        except ValidationError as exc:
            self.assertNotIn(secret, str(exc))

    def test_wildcard_cors_origin_is_rejected_with_credentials(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                ENVIRONMENT="development",
                JWT_SECRET="A strong random development-style secret 4921!",
                CORS_ALLOWED_ORIGINS="*",
            )

    def test_same_site_none_requires_secure_cookie(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                ENVIRONMENT="development",
                JWT_SECRET="s" * 48,
                COOKIE_SAMESITE="none",
                COOKIE_SECURE=False,
            )

    def test_production_rejects_disabled_secure_cookie(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                ENVIRONMENT="production",
                JWT_SECRET="A strong random production secret 4921!",
                COOKIE_SECURE=False,
                CORS_ALLOWED_ORIGINS="https://cvki.example.gov",
            )

    def test_rate_limiter_returns_429_with_retry_after(self):
        for _ in range(settings.LOGIN_RATE_LIMIT_REQUESTS):
            self.assertIsNone(
                rate_limiter.check(
                    scope="login",
                    client_key="testclient",
                    limit=settings.LOGIN_RATE_LIMIT_REQUESTS,
                    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
                )
            )

        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "not-a-real-password"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_validation_response_does_not_echo_submitted_secret(self):
        secret = "do-not-reflect-this-value"
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": "citizen@example.com",
                "password": secret,
                "role": secret,
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)
        self.assertNotIn('"input"', response.text)

    def test_unexpected_error_response_does_not_expose_exception_text(self):
        secret = "private-database-detail"
        client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "app.api.v1.location.reverse_geocode",
            side_effect=RuntimeError(secret),
        ):
            response = client.get(
                "/api/v1/location/reverse-geocode?latitude=1&longitude=2"
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "An unexpected server error occurred.",
        )
        self.assertNotIn(secret, response.text)

    def test_authentication_database_failure_returns_503(self):
        with patch("app.services.user.get_database", return_value=None):
            register_response = self.client.post(
                "/api/v1/auth/register",
                json={
                    "email": "new-citizen@example.com",
                    "password": "valid-password-123",
                },
            )
            self.assertEqual(register_response.status_code, 503)

            profile_response = self.client.get("/api/v1/auth/me")
            self.assertEqual(profile_response.status_code, 503)

    def test_request_body_limit_rejects_oversized_request(self):
        with patch.object(settings, "MAX_REQUEST_BODY_BYTES", 16):
            response = self.client.post(
                "/api/v1/auth/register",
                content=b"x" * 17,
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.json()["detail"],
            "Request body exceeds the maximum allowed size.",
        )


if __name__ == "__main__":
    unittest.main()
