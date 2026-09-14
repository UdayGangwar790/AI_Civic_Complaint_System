# CVKI Module 2.1 — YOLOv8 Model Backend Integration

This document outlines the architecture, configuration, and verification of the computer vision model integration within the CVKI FastAPI backend.

---

## 1. Model Source & Provenance

The production computer vision detector integrated into the backend is the frozen, verified **M1.13 YOLOv8n** model checkpoint:

- **Filesystem Path (Read-Only)**: `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`
- **Model Checkpoint**: Epoch 61 `best.pt` (M1.13 Controlled Correction Experiment)
- **Model Size**: ~6.3 MB
- **Backbone Architecture**: Ultralytics YOLOv8n (nano detection model)
- **Civic Problem Classes (Exact Mapping)**:
  - `0`: `open_damaged_manhole`
  - `1`: `damaged_missing_road_sign`
  - `2`: `road_waterlogging`

---

## 2. Backend Loading Mechanism & Lifespan Architecture

To optimize performance and resource usage, the model is **loaded once into memory during application startup** rather than being reloaded per HTTP request:

1. **Singleton Service (`backend/app/services/computer_vision.py`)**:
   - `cv_model_service` (`YOLOModelService`) maintains single-instance model ownership across the process lifecycle.
   - Verifies checkpoint existence and confirms class mappings match the expected civic categories.
   - Exposes safe, sanitized metadata without leaking internal server filesystem paths.

2. **FastAPI Lifespan Context Manager (`backend/app/main.py`)**:
   - Modern `@asynccontextmanager lifespan(app: FastAPI)` triggers model initialization before the HTTP server accepts incoming requests.
   - If model initialization succeeds, the model is flagged as `ready`.
   - If loading fails (e.g. missing weight file), the failure is logged and the service gracefully reports `503 Service Unavailable` on the status endpoint while keeping the core `/api/health` endpoint responsive.

---

## 3. Configuration & Environment Variables

Model parameters are configuration-driven via `backend/app/core/config.py` using `pydantic-settings`:

| Setting Variable | Default Value | Description |
|---|---|---|
| `YOLO_MODEL_PATH` | `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt` | Path to weights file (resolved relative to workspace root) |
| `YOLO_MODEL_VERSION` | `M1.13-yolov8n` | Model version identifier |
| `YOLO_DEVICE` | `cpu` | Inference target device (`cpu` or `cuda`) |

These variables can be overridden in the `.env` file or via system environment variables.

---

## 4. API Endpoints for Health & Model Verification

### A. General Health Check
- **Endpoint**: `GET /api/health`
- **Method**: `GET`
- **Description**: Verifies backend HTTP service availability.
- **Example Response (HTTP 200)**:
  ```json
  {
    "status": "ok",
    "service": "CVKI backend"
  }
  ```

### B. Model Status & Readiness
- **Endpoint**: `GET /api/v1/model/status` (also aliased at `GET /api/model/status`)
- **Method**: `GET`
- **Description**: Verifies whether the YOLOv8 model is loaded in memory and returns metadata.
- **Example Response when Ready (HTTP 200)**:
  ```json
  {
    "loaded": true,
    "status": "ready",
    "model_name": "yolov8n",
    "model_version": "M1.13-yolov8n",
    "num_classes": 3,
    "classes": {
      "0": "open_damaged_manhole",
      "1": "damaged_missing_road_sign",
      "2": "road_waterlogging"
    }
  }
  ```
- **Example Response when Unavailable (HTTP 503)**:
  ```json
  {
    "loaded": false,
    "status": "error",
    "model_name": "yolov8n",
    "model_version": "M1.13-yolov8n",
    "num_classes": 0,
    "classes": {},
    "error": "Model weights file not found at expected path: best.pt"
  }
  ```

---

## 5. How to Run & Test Locally

1. **Run Unit & Integration Tests**:
   ```bash
   .venv/Scripts/python.exe -m unittest backend/tests/test_model_integration.py -v
   ```

2. **Start Backend Server**:
   ```bash
   .venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

3. **Query Endpoints**:
   ```bash
   curl http://127.0.0.1:8000/api/health
   curl http://127.0.0.1:8000/api/v1/model/status
   ```
