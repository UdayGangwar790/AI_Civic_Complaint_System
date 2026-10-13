# CVKI — Civic Vision & Knowledge Intelligence

Civic Vision & Knowledge Intelligence (CVKI) is an explainable decision-support and civic-issue reporting platform. It integrates computer vision hazard detection, reverse geocoding, evidence-backed authority resolution, duplicate and recurrence intelligence, engineering priority triage, and resolution evidence auditing.

CVKI prepares citizen-facing draft information and operational triage intelligence; it does **not** automatically dispatch complaints to external government portals, nor does it replace official municipal inspections.

---

## 1. Problem Statement

Civic road hazard reporting typically suffers from three fundamental bottlenecks:
1. **Misclassification & Vagueness**: Citizen complaints often lack standard defect terminology, precise location coordinates, or objective visual evidence.
2. **Jurisdiction & Authority Fragmentation**: Roads within a single urban corridor often divide responsibility among municipal corporations, state highway departments, national highway authorities, and private concessionaires. Citizens rarely know which agency actually owns or maintains a specific road segment.
3. **Duplicate Confusion vs. Chronic Recurrence**: Existing systems either treat all nearby reports as duplicate noise (ignoring recurring physical infrastructure degradation) or treat every repeated submission as an independent event without historical context.

---

## 2. Solution Overview

CVKI establishes an end-to-end, multi-modal decision-support pipeline:
- **Visual Detection**: Uses a frozen, controlled YOLOv8n model (`M1.13`) to detect three specific road hazard classes.
- **Evidence-Driven Road-to-Authority Intelligence**: Disentangles road ownership from maintenance responsibility using verifiable official source records, restricting builder/contractor claims strictly to verified contract/tender documents.
- **Duplicate vs. Recurrence Disentanglement**: Separates short-window (<=72h) duplicates describing the same incident from long-window (180d) recurrence indicating chronic repeated reporting.
- **Explainable Engineering Priority (0–100)**: Triage heuristic combining visual confidence, severity, text keywords, location corridors, duplicates, and bounded recurrence contributions.
- **Resolution Evidence Lifecycle**: Enforces staff-authored inspection note attribution upon resolution, invalidating prior notes if a case is reopened.
- **Role-Based Workflows**: Separate operational portals for Citizens (tracking), Assigned Authorities (case management & notes), and Administrators (analytics, hotspots, assignment, and security audit).

---

## 3. Core Features

- **Multi-Modal Road Hazard Detection**: Detects `open_damaged_manhole`, `damaged_missing_road_sign`, and `road_waterlogging`.
- **GPS & Reverse Geocoding**: Extracts normalized road, city, and jurisdiction details from image metadata or device coordinates.
- **Evidence-Backed Authority Resolver**: Maps coordinates to `road_owner` and `maintenance_authority` with source citations and verification states (`verified`, `partially_verified`, `not_verified`).
- **Factual Complaint Drafting**: Generates neutral, structured complaints in multiple languages without speculative claims.
- **Persistent Case Management**: Unique chronological reference IDs (`CVKI-YYYYMMDD-XXXXXX`) stored in MongoDB with lifecycle transitions (`submitted_to_cvki`, `assigned`, `in_progress`, `resolved`, `closed`).
- **Advanced Civic Intelligence (M5.2)**: 180-day spatial recurrence analysis (250m Haversine / normalized road fallback) and 30-day reporting concentration hotspots.
- **Attributed Resolution Evidence**: Tracks staff inspection notes on case resolution and marks notes stale if a case is reopened.
- **Security & Privacy Auditing**: Request correlation IDs, strict role-based access control (RBAC), and owner-isolated case tracking.

---

## 4. System Architecture

```
[Citizen / Client]
       │
       ▼
[FastAPI Backend Application]
 ├── /api/v1/detection/predict   ──► Ultralytics YOLOv8n (M1.13 Frozen Checkpoint)
 ├── /api/v1/location/reverse    ──► Nominatim Geocoding & Road Normalizer
 ├── /api/v1/authority/resolve   ──► Evidence-Driven Authority Resolver (M5.1)
 ├── /api/v1/complaint/guidance  ──► Multi-Lingual Complaint Generator
 ├── /api/v1/complaint/cases     ──► Case Creation (Server-Side Recurrence & Priority Recomputed)
 ├── /api/v1/priority/score      ──► Public Bounded Priority Heuristic (0–100)
 ├── /api/v1/authority/cases     ──► Authority Portal (Scoped to Assigned Cases Only)
 └── /api/v1/admin/analytics     ──► Operational Analytics & 30-Day Road Hotspots
       │
       ▼
[MongoDB Persistence Store]
 ├── complaint_cases (cases, assignment, recurrence, resolution evidence)
 ├── audit_logs (request-correlated security and lifecycle audit records)
 └── notifications (in-app notifications for citizens and staff)
```

---

## 5. Technology Stack

- **Backend**: Python 3.13, FastAPI, Pydantic v2, Motor / PyMongo (MongoDB async driver).
- **Computer Vision / AI**: PyTorch, Ultralytics YOLOv8, Pillow.
- **Frontend**: React 18, Vite v8, Vanilla CSS (tokens, responsive layouts, role views), Lucide React.
- **Testing & Quality**: pytest, pytest-subtests, oxlint.

---

## 6. Computer Vision Pipeline & M1 Research Progression

The CV subsystem was evaluated and refined through four controlled research iterations:
1. **M1.8 Baseline (YOLOv8n)**: Initial baseline trained with default mosaic and scale augmentations.
2. **M1.11 Attempted Improvement**: Experimented with disabled mosaic (`mosaic=0`) and reduced scale jitter (`scale=0.15`). Resulted in small-object detection collapse (waterlogging test mAP50 dropped from 0.2951 to 0.0463).
3. **M1.12 Diagnostic Analysis**: Diagnosed the root cause of M1.11's recall degradation and established the need for contiguous bounding-box labeling.
4. **M1.13 Controlled Correction**: Restored multi-scale mosaic (`mosaic=1.0`), scale jitter (`scale=0.5`), and calibrated negative training samples.

### Dual Held-Out Evaluation Benchmark

| Benchmark Split | Metric | M1.8 Baseline | M1.11 Retrained | M1.13 Corrected | M1.13 Delta vs. Baseline |
|---|---|---|---|---|---|
| **Original M1.8 Test Set** (30 images) | Precision | 0.7797 | N/A (disjoint) | **0.8380** | **+5.83 pp** |
| | Recall | 0.5660 | N/A (disjoint) | **0.6120** | **+4.60 pp** |
| | mAP@0.5 | 0.6166 | N/A (disjoint) | **0.6540** | **+3.74 pp** |
| | mAP@0.5:0.95 | 0.4279 | N/A (disjoint) | **0.4870** | **+5.91 pp** |
| | Waterlogging mAP50 | 0.2951 | N/A (disjoint) | **0.3520** | **+5.69 pp** |
| **Improved M1.11 Test Set** (31 images) | Precision | N/A (disjoint) | 0.5785 | **0.6500** | **+7.15 pp** |
| | Recall | N/A (disjoint) | 0.3857 | **0.5700** | **+18.43 pp** |
| | mAP@0.5 | N/A (disjoint) | 0.4166 | **0.5680** | **+15.14 pp** |
| | Road Sign mAP50 | N/A (disjoint) | 0.5450 | **0.8430** | **+29.80 pp** |
| | Waterlogging mAP50 | N/A (disjoint) | 0.0463 | **0.0841** | **+3.78 pp** |

**Frozen M1.13 Model Checkpoint:**
- Path: `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`
- Verified SHA-256: `602160D4851E0D79C34CB23B828BDE474FC4C164EAF1A1C2A884CFB372F4BDA3`

---

## 7. Evidence-Driven Authority Intelligence (M5.1)

CVKI implements an explicit conceptual chain for authority mapping:
```
Issue ──► Coordinates ──► Road ──► Jurisdiction ──► Official Evidence ──► Road Owner ──► Maintenance Authority ──► Builder/Contractor (if evidenced)
```

- **Separation of Roles**: Road ownership does **not** imply maintenance responsibility; both are resolved independently.
- **Contractor Safeguard**: Builder/contractor attribution requires official contract/tender records and is never inferred from road ownership.
- **Verification States**: `verified` (both owner and maintainer verified), `partially_verified` (one role supported), `not_verified` (insufficient evidence).
- **Official Source Audit Trail**: Every resolved claim references verifiable registry citations.

---

## 8. Complaint Workflow & Case Lifecycle (M3.1–M4.5)

- **Drafting & Guidance**: Citizen uploads image, verifies detections, selects language, and receives structured draft text.
- **Case Creation**: Generates unique tracking ID, persists location and evidence, runs duplicate detection and recurrence analysis.
- **Lifecycle Graph**:
  - `submitted_to_cvki` ──► `assigned` ──► `in_progress` ──► `resolved` ──► `closed`
  - Reopening: `resolved` ──► `in_progress` (re-initiates review and updates evidence cutoff).
  - Terminal state: `closed` is immutable and cannot be modified.

---

## 9. Advanced Civic Intelligence (M5.2)

- **Recurrence Analysis**: Identifies same-category cases within 180 days (`RECURRENCE_WINDOW_DAYS`) and <= 250m Haversine distance, separated by > 72 hours.
- **Hotspots Analysis**: Aggregates road/city report concentrations over a rolling 30-day window (`HOTSPOT_WINDOW_DAYS`, min 3 reports).
- **Resolution Evidence States**:
  - `status_only`: Case is currently active/open.
  - `evidence_supported`: Case is marked resolved and contains an attributed staff note from the current resolution cycle.
  - `evidence_missing`: Case is marked resolved without a current note.
- **Trust Boundary Enforcement**: Case triage priority is recomputed server-side; client payloads cannot inject recurrence scores or override server triage.

---

## 10. Local Setup & Execution (Windows)

### Prerequisites
- Python 3.13 (64-bit)
- Node.js (v18+) and npm
- MongoDB Community Server running locally on port 27017

### Installation
```powershell
# 1. Clone repository & configure virtual environment
git clone https://github.com/UdayGangwar790/AI_Civic_Complaint_System.git
Set-Location AI_Civic_Complaint_System

py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 2. Configure frontend dependencies
npm --prefix frontend install

# 3. Environment configuration
Copy-Item .env.example backend\.env
```

### Running Backend & Frontend
Terminal 1 (Backend):
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir backend
```

Terminal 2 (Frontend):
```powershell
Set-Location frontend
npm run dev
```

Interactive API documentation is accessible at `http://localhost:8000/docs`.

---

## 11. Testing & Validation

Run the complete regression suite:
```powershell
# Full backend suite (397 tests)
.\.venv\Scripts\python.exe -m pytest backend/tests -v

# Frontend linting & production build
npm --prefix frontend run lint
npm --prefix frontend run build
```

---

## 12. Security & Privacy Principles

- **No Fabricated Data**: Authority names, contractor details, government contacts, and URLs are never hallucinated.
- **Trust Boundaries**: Public endpoints do not trust client-supplied priority scores, duplicate flags, or recurrence counts.
- **Citizen Privacy**: Citizens only have access to their own complaint history; administrative intelligence and other users' records are isolated.
- **Scoped Authority Access**: Authorities can only inspect cases assigned to them; other case IDs are omitted from authority responses.
- **Request Correlation**: Audit logs record timestamps, actor IDs, roles, and correlation IDs for all state-changing actions.

---

## 13. Limitations

- **Dataset Scale**: The computer vision model was trained on a controlled 300-image dataset; generalization across extreme weather or nighttime conditions is unverified.
- **Waterlogging Boundaries**: Due to reflection and illumination variability, waterlogging detection remains less precise than manhole or road sign detection.
- **Registry Freshness**: Authority intelligence relies on the accuracy of configured local records; missing registries return `not_verified`.
- **No External Portal Dispatch**: CVKI generates structured packages; it does not automatically submit complaints to live government APIs.
- **Engineering Heuristic**: Priority scores are triage aids for human staff, not emergency dispatch guarantees.

---

## 14. Future Research

- **Semantic Segmentation**: Moving from bounding boxes to pixel-level masks for waterlogging and pothole volume estimation.
- **Federated GIS Integration**: Dynamic querying of live municipal and national road inventory GIS feature services.
- **Edge Deployment**: Exporting M1.13 to ONNX Runtime and TFLite for on-device mobile inference.
- **C2PA Image Provenance**: Embedding cryptographic signatures in inspection photos to verify photo authenticity.
