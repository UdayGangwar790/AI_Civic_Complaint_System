import os
from pathlib import Path
from pydantic_settings import BaseSettings


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
    
    # Model Configuration
    YOLO_MODEL_PATH: str = "ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt"
    YOLO_MODEL_VERSION: str = "M1.13-yolov8n"
    YOLO_DEVICE: str = "cpu"
    
    # Expected Class Mapping for CIVKI Model
    EXPECTED_CLASSES: dict[int, str] = {
        0: "open_damaged_manhole",
        1: "damaged_missing_road_sign",
        2: "road_waterlogging"
    }

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


settings = Settings()
