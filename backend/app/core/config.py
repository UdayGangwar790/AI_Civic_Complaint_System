import os
import secrets
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


_DEVELOPMENT_JWT_SECRET = secrets.token_urlsafe(32)


def get_project_root() -> Path:
    """
    Locates the project root directory (CIVKI) by looking upwards from this file.
    """
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "ai").exists() and (parent / "setup.py").exists():
            return parent
    # Fallback to current working directory or grandparent of app
    return Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    PROJECT_NAME: str = "CVKI API"
    API_V1_STR: str = "/api/v1"
    
    # MongoDB Configuration
    MONGODB_URI: str = Field(default="mongodb://localhost:27017", repr=False)
    MONGODB_DB_NAME: str = "cvki"
    MONGODB_TIMEOUT_MS: int = Field(default=5000, gt=0)
    MONGODB_CONNECT_TIMEOUT_MS: int = Field(default=5000, gt=0)
    MONGODB_SOCKET_TIMEOUT_MS: int = Field(default=10000, gt=0)

    # Security / JWT Configuration
    ENVIRONMENT: str = "development"
    JWT_SECRET: str = Field(default=_DEVELOPMENT_JWT_SECRET, repr=False)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    AUTH_COOKIE_NAME: str = "cvki_access_token"
    CSRF_COOKIE_NAME: str = "cvki_csrf_token"
    COOKIE_SECURE: Optional[bool] = None
    COOKIE_SAMESITE: str = "lax"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Model Configuration
    YOLO_MODEL_PATH: str = "ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt"
    YOLO_MODEL_VERSION: str = "M1.13-yolov8n"
    YOLO_DEVICE: str = "cpu"
    YOLO_CONFIDENCE_THRESHOLD: float = 0.25
    MAX_IMAGE_UPLOAD_BYTES: int = Field(default=10 * 1024 * 1024, gt=0)
    MAX_IMAGE_PIXELS: int = Field(default=40_000_000, gt=0)
    MAX_REQUEST_BODY_BYTES: int = Field(default=12 * 1024 * 1024, gt=0)
    REVERSE_GEOCODER_URL: str = "https://nominatim.openstreetmap.org/reverse"
    REVERSE_GEOCODER_USER_AGENT: str = "CVKI/0.2 location foundation"
    REVERSE_GEOCODER_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)

    LOGIN_RATE_LIMIT_REQUESTS: int = Field(default=10, gt=0)
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    REGISTRATION_RATE_LIMIT_REQUESTS: int = Field(default=5, gt=0)
    REGISTRATION_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    INFERENCE_RATE_LIMIT_REQUESTS: int = Field(default=20, gt=0)
    INFERENCE_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    COMPLAINT_RATE_LIMIT_REQUESTS: int = Field(default=10, gt=0)
    COMPLAINT_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    DUPLICATE_CHECK_RATE_LIMIT_REQUESTS: int = Field(default=20, gt=0)
    DUPLICATE_CHECK_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    EXPENSIVE_SEARCH_RATE_LIMIT_REQUESTS: int = Field(default=30, gt=0)
    EXPENSIVE_SEARCH_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0)
    
    # Expected Class Mapping for CIVKI Model
    EXPECTED_CLASSES: dict[int, str] = {
        0: "open_damaged_manhole",
        1: "damaged_missing_road_sign",
        2: "road_waterlogging"
    }

    # M3.7 Duplicate Detection Configurable Engineering Thresholds
    DUPLICATE_SIMILARITY_THRESHOLD: float = 0.82
    POSSIBLE_DUPLICATE_SIMILARITY_THRESHOLD: float = 0.55
    DUPLICATE_DISTANCE_METERS: float = 150.0
    DUPLICATE_TIME_WINDOW_HOURS: float = 72.0

    # M3.8 Priority / Risk Intelligence Configurable Engineering Weights
    PRIORITY_BASE_SCORES: dict[str, int] = {
        "open_damaged_manhole": 50,
        "road_waterlogging": 35,
        "damaged_missing_road_sign": 25,
        "other_civic_issue": 20,
    }
    PRIORITY_WEIGHT_TEXT_RISK: int = 20
    PRIORITY_WEIGHT_REPEAT: int = 15
    PRIORITY_WEIGHT_LOCATION: int = 10
    PRIORITY_WEIGHT_CONFIDENCE: int = 5
    PRIORITY_WEIGHT_RECURRENCE: int = 5
    PRIORITY_P1_THRESHOLD: int = 80
    PRIORITY_P2_THRESHOLD: int = 60
    PRIORITY_P3_THRESHOLD: int = 40

    RECURRENCE_WINDOW_DAYS: int = Field(default=180, ge=1)
    HOTSPOT_WINDOW_DAYS: int = Field(default=30, ge=1)
    HOTSPOT_MIN_CASES: int = Field(default=3, ge=2)
    UNRESOLVED_RECOMMENDATION_DAYS: int = Field(default=30, ge=1)
    MAX_INTELLIGENCE_HISTORY_CANDIDATES: int = Field(default=5000, ge=100)

    @model_validator(mode="after")
    def validate_security_configuration(self):
        environment = self.ENVIRONMENT.strip().lower()
        if environment not in {"development", "test", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, or production.")
        self.ENVIRONMENT = environment

        same_site = self.COOKIE_SAMESITE.strip().lower()
        if same_site not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict, or none.")
        self.COOKIE_SAMESITE = same_site

        origins = self.allowed_cors_origins
        if "*" in origins:
            raise ValueError("CORS_ALLOWED_ORIGINS cannot contain '*' when credentials are enabled.")
        if environment == "production":
            secret = self.JWT_SECRET.strip()
            normalized_secret = secret.lower()
            if (
                len(secret) < 32
                or len(set(secret)) < 8
                or secret == _DEVELOPMENT_JWT_SECRET
                or any(marker in normalized_secret for marker in ("example", "change-me", "your_", "placeholder", "replace-with"))
            ):
                raise ValueError("Production requires a non-default JWT_SECRET of at least 32 characters.")
            if not origins:
                raise ValueError("Production requires at least one CORS_ALLOWED_ORIGINS entry.")
            if any(not origin.startswith("https://") for origin in origins):
                raise ValueError("Production CORS_ALLOWED_ORIGINS entries must use HTTPS.")
            if self.COOKIE_SECURE is False:
                raise ValueError("COOKIE_SECURE cannot be disabled in production.")

        if same_site == "none" and not self.auth_cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true.")
        return self

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def auth_cookie_secure(self) -> bool:
        if self.COOKIE_SECURE is not None:
            return self.COOKIE_SECURE
        return self.ENVIRONMENT.strip().lower() == "production"

    def get_resolved_model_path(self) -> Path:
        """
        Resolves the configured YOLO_MODEL_PATH to an absolute filesystem Path.
        """
        model_path = Path(self.YOLO_MODEL_PATH)
        if model_path.is_absolute():
            return model_path
        return get_project_root() / model_path

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        hide_input_in_errors = True


settings = Settings()
