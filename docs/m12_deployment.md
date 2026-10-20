# CVKI M12.8: Deployment & Operational Readiness Guide

This guide details the deployment prerequisites, operational startup sequence, configuration enforcement, and environment validation rules for the CVKI platform.

---

## 1. Deployment Topology & Current Baseline

> [!IMPORTANT]
> **Deployment Status**:  
> **Cloud deployment not configured.**  
> Containerized (Docker / Kubernetes) infrastructure is not packaged in the current repository baseline. The system is validated for local engineering environments, staging servers, and self-hosted Linux/Windows server deployments using Python 3.13+ virtual environments and Node.js Vite runtime.

---

## 2. Infrastructure Requirements

- **Runtime Engine**: Python 3.13+ (Backend), Node.js v18+ (Frontend).
- **Database**: MongoDB 6.0+ (Standalone or Replica Set).
- **Compute / GPU**: Minimum 4 CPU cores, 8GB RAM. Dedicated NVIDIA GPU with CUDA 12 support recommended for high-volume CV inference, though CPU execution fallback is fully supported via Ultralytics YOLOv8.
- **Network**: Outbound HTTPS connectivity for OpenStreetMap Nominatim reverse geocoding and Open-Meteo weather APIs (or local mock services in air-gapped environments).

---

## 3. Configuration & Environment Variables

All settings are managed via `.env` and loaded securely through Pydantic `BaseSettings`:

### 3.1 Security Hardening Invariants
- `ENVIRONMENT`: Must be set to `production` in live environments.
- `JWT_SECRET`: Must be a cryptographically secure random string (minimum 32 characters). In production mode, startup fails immediately if a default or weak secret is detected.
- `COOKIE_SECURE`: Must be `true` in production to enforce HTTPS-only transmission.
- `CORS_ALLOWED_ORIGINS`: Comma-separated allowed origins. In production, wildcard `*` with credentials is explicitly rejected.

### 3.2 Service Endpoints & Model Configuration
- `MONGODB_URI`: Target database connection URI (e.g., `mongodb://localhost:27017`).
- `YOLO_MODEL_PATH`: Must point to the frozen checkpoint (`ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`).
- `MAX_IMAGE_UPLOAD_BYTES`: Request body size limit for image uploads (default `10485760` bytes / 10MB).

---

## 4. Startup & Execution Instructions

### 4.1 Backend Service
```bash
# Activate virtual environment
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate

# Install requirements
pip install -r backend/requirements.txt

# Start backend using Uvicorn
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4.2 Frontend Web Interface
```bash
cd frontend
npm install
npm run build     # Production static build to frontend/dist
# Or for local development:
npm run dev
```

---

## 5. Health Check & Observability Validation

Once deployed, the following endpoints confirm deployment readiness:

1. **Liveness Check**:
   ```bash
   curl -f http://localhost:8000/api/health/live
   # Expects: {"status": "ok", "timestamp": "..."}
   ```
2. **Readiness Check**:
   ```bash
   curl -f http://localhost:8000/api/health/ready
   # Expects: {"status": "ready", "database": "connected", "model": "loaded"}
   ```
3. **Metrics Exposition**:
   ```bash
   curl http://localhost:8000/metrics
   # Returns Prometheus metrics: cvki_requests_total, cvki_inference_duration_seconds, etc.
   ```

---

## 6. Reverse Proxy & Graceful Shutdown

- **Reverse Proxy**: Deploy behind NGINX or Caddy. Ensure `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Request-ID` headers are passed to preserve correlation logging and IP rate limiting.
- **Graceful Shutdown**: The FastAPI lifespan context manager handles SIGTERM/SIGINT by flushing active database operations, releasing model memory, and terminating background sync tasks safely.
