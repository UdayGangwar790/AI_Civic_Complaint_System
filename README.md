# CVKI — Civic Vision & Knowledge Intelligence

CVKI is a civic-issue reporting application with a React/Vite frontend, a FastAPI backend, MongoDB persistence, and a fixed YOLOv8 model for three issue classes:

- `open_damaged_manhole`
- `damaged_missing_road_sign`
- `road_waterlogging`

The implemented M0–M4 workflows include image detection, location capture and reverse geocoding, complaint drafting and case tracking, duplicate and priority analysis, authority-scoped case operations, notifications, analytics, and audit events. The application prepares citizen-facing information; it does **not** submit complaints to government systems.

This repository is an implementation, not a production-readiness certification. Review the limitations below before deployment.

## Local setup (Windows)

Prerequisites: Python 3.13, Node.js/npm, MongoDB, and the model file at `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`.

From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm --prefix frontend install
Copy-Item .env.example backend\.env
```

Edit `backend\.env` for the local environment, especially `MONGODB_URI`. The development JWT secret is not suitable for production. Start MongoDB, then start the backend in one terminal:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Start the frontend in another terminal:

```powershell
Set-Location frontend
npm run dev
```

The frontend uses `http://localhost:8000` by default. Set `VITE_API_BASE_URL` when the API is hosted elsewhere. The API documentation is available at `http://localhost:8000/docs`; `/health` is a liveness check and `/ready` reports whether MongoDB and the model are available.

## Tests and frontend checks

From the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest
Set-Location ..\frontend
npm run lint
npm run build
```

## Important limitations

- No live official road-authority registry is configured. The default authority provider returns `not_verified` without authority claims or source records. Client-supplied authority claims are ignored for draft, guidance, and case creation.
- Complaint and government-portal guidance are drafts only. CVKI does not submit complaints externally.
- Reverse geocoding uses the configured Nominatim-compatible service; service availability and external usage requirements apply.
- Rate limiting is in-process and is not shared among multiple backend workers.
- Audit records include request correlation metadata but are not tamper-evident.
- The frontend lint command currently exits successfully with three React effect warnings. The production build succeeds with a warning that the main JavaScript bundle exceeds 500 kB.
- Local development defaults must be replaced with deployment-specific secrets, HTTPS, database controls, CORS origins, and operational monitoring before any production use.

## Project layout

- `frontend/` — React and Vite user interface
- `backend/app/` — FastAPI routes, schemas, persistence, and services
- `backend/tests/` — pytest regression suite
- `ai/computer_vision/` — model, inference code, and dataset/training assets
- `docs/` — module and verification documentation
