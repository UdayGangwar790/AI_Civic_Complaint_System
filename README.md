# CVKI — Civic Visual Knowledge Intelligence

**Version**: 1.0.0 (Release Baseline M12)  
**Objective**: Evidence-Aware Civic Decision Support & Operational Action Intelligence

Civic Visual Knowledge Intelligence (**CVKI**) is an explainable decision-support and civic action intelligence platform. It bridges multimodal citizen reporting (images, GPS coordinates, vernacular text) with automated computer vision hazard detection, evidence-backed authority resolution, deterministic action playbooks, field inspection verification, cryptographic provenance, and civic knowledge graph projections.

> [!IMPORTANT]
> **Operational & Epistemic Boundaries**:
> - **Decision Support, Not Autonomous Governance**: CVKI generates structured recommendations, action playbooks, and draft correspondence for official human review. It does **not** autonomously dispatch municipal work crews, authorize public expenditures, or modify real-world infrastructure.
> - **Human Review Mandatory**: All operational recommendations enforce `human_review_required = True`.
> - **No Autonomous Case Resolution**: Neither statistical computer vision detections nor citizen reports constitute physical verification. Physical case resolution requires formal field inspection audit or authorized officer sign-off.
> - **Not a Replacement**: CVKI is not an autonomous civic authority and does not replace municipal engineers, administrators, or field inspectors.

---

## 1. Complete End-to-End Workflow

The platform operates across a 15-stage audited civic intelligence lifecycle:

```
1. Citizen Report
   │  (Uploads defect photo, device GPS coordinates, and vernacular description)
   ▼
2. Computer Vision Detection
   │  (Ultralytics YOLOv8n M1.13 frozen baseline detects 13 civic hazard classes)
   ▼
3. Reverse Geocoding & Road Context
   │  (OpenStreetMap / Nominatim extracts normalized road name, corridor, and jurisdiction)
   ▼
4. Evidence-Backed Authority Resolution
   │  (Disentangles road owner, maintenance authority, and contractor via official records)
   ▼
5. Case Persistence & Case Reference
   │  (Generates chronological reference ID, stores structured case in MongoDB)
   ▼
6. Multimodal & Vernacular Normalization
   │  (Rule-based NLP maps multi-lingual terms to canonical civic defect categories)
   ▼
7. Cross-Modal Consistency Analysis
   │  (Evaluates semantic agreement between visual detections and verbal claims)
   ▼
8. Active Clarification
   │  (Presents targeted questions to citizen when visual and verbal claims disagree)
   ▼
9. Decision Support & Operational Triage
   │  (Calculates priority score 0–100 combining severity, road tier, and recurrence)
   ▼
10. Action Playbook Matching
    │  (Selects deterministic remediation workflows, materials, and safety protocols)
    ▼
11. Field Inspection Protocol Generation
    │  (Generates step-by-step physical inspection checklist with geofenced bounds)
    ▼
12. Field Inspection Execution & Audit
    │  (Audits field inspector submissions for geofence compliance and verification completeness)
    ▼
13. Authority Review Portal
    │  (Authorized municipal staff reviews recommendations: ACCEPTED, MODIFIED, or REJECTED)
    ▼
14. Government Portal Integration
    │  (Safely submits to CPGRAMS / state portals with idempotent tracking and fallback state)
    ▼
15. Provenance Ledger & Civic Knowledge Graph
       (Appends SHA-256 evidence records and projects relational nodes into property graph)
```

---

## 2. Technical Architecture & Core Modules

| Module | Subsystem | Implementation Details |
| :--- | :--- | :--- |
| **M1 / M8** | **Computer Vision Baseline** | Ultralytics YOLOv8n (`M1.13` frozen checkpoint). Normalized coordinates, zero tensor leakage. |
| **M2 / M5 / M6**| **Geospatial & Authority Intelligence** | Road normalization, 250m Haversine spatial recurrence, official registry verification. |
| **M3 / M4** | **Persistence & RBAC** | MongoDB async driver (Motor), JWT bearer tokens, role enforcement (`CITIZEN`, `AUTHORITY`, `ADMIN`). |
| **M7** | **Government Integration** | Pluggable adapters (CPGRAMS, state portals), exponential backoff, dead-letter queue. |
| **M9** | **Multimodal Intelligence** | Rule-based vernacular normalizer (7 languages/scripts), cross-modal consistency evaluator. |
| **M10** | **Decision Support & Field Inspection** | Action playbooks, geofenced inspection protocols, completeness audit, provenance projection. |
| **M11** | **Production Readiness & Observability**| Prometheus metrics, structured correlation logging, health/readiness endpoints, rate limiting. |
| **M12** | **Validation, Benchmarking & Freeze** | End-to-end verification, reproducibility registry, security/epistemic audits, baseline freeze. |

---

## 3. Computer Vision Model Invariants

The computer vision detection baseline is frozen at iteration **M1.13**:
- **Model Checkpoint**: `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`
- **SHA-256 Hash**: `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3`
- **Dataset**: `ai/computer_vision/dataset_m1_13` (Exactly 605 files)
- **Supported Classes (13)**: `garbage`, `pothole`, `street_light_issue`, `water_leakage`, `fallen_tree`, `damaged_signboard`, `broken_bench`, `open_damaged_manhole`, `illegal_parking`, `sewage_overflow`, `encroachment`, `unauthorized_posters`, `loose_cables`.
- **Historical Evaluations**:
  - M1.8 Held-Out: Precision = 0.8380, Recall = 0.6120, mAP50 = 0.6540, mAP50-95 = 0.4870
  - M1.11 Held-Out: Precision = 0.6500, Recall = 0.5700, mAP50 = 0.5680, mAP50-95 = 0.4230
- **Disclaimer**: These metrics represent historical evaluation baselines under specific dataset conditions, not universal guarantees of real-world accuracy across arbitrary municipal lighting, weather, or sensor variations.

---

## 4. Epistemic Safety & Decision Boundaries

CVKI strictly enforces mathematical non-equivalences across all decision layers:
- $\text{MODEL\_OBSERVATION} \neq \text{VERIFIED\_EVIDENCE}$
- $\text{USER\_REPORTED} \neq \text{VERIFIED\_EVIDENCE}$
- $\text{SYSTEM\_DERIVED} \neq \text{Physical Ground Truth}$
- $\text{CV Confidence} \neq \text{Civic Severity}$
- $\text{Government Portal Status: RESOLVED} \neq \text{Automatic CVKI Physical Resolution}$

### Enforced Protections
1. Recommendations require explicit officer review (`human_review_required = True`).
2. No autonomous dispatch, closure, or fiscal commitment.
3. Citizen responses to clarification queries are tagged `USER_REPORTED`.
4. Cryptographic SHA-256 hashes prevent evidence log retrofitting.

---

## 5. Security & Privacy Hardening

- **No Secrets in Source**: All keys and connection strings loaded from environment variables.
- **Server-Side Authorization**: Administrative routes enforce role validation at the dependency injection level.
- **SSRF & Payload Defenses**: Outbound requests restricted to pre-approved domains; private IP / cloud metadata addresses (`169.254.169.254`) blocked; request bodies strictly bounded.
- **Citizen Privacy**: Public map views inject 50–100m coordinate jitter to prevent individual residence identification; PII stripped from public knowledge graphs.

---

## 6. Quick Start & Execution

### 6.1 Prerequisites
- Python 3.13+
- Node.js v18+
- MongoDB 6.0+

### 6.2 Backend Setup
```bash
# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Start backend server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6.3 Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### 6.4 Verification & Benchmarking
```bash
# Run full product end-to-end validation test
pytest backend/tests/test_m12_product_e2e.py -v

# Run targeted security & epistemic audits
pytest backend/tests/test_m108_security_hardening.py backend/tests/test_m108_epistemic_safety.py -v

# Run M12 performance & concurrency benchmark
python backend/tests/benchmark_m12_final.py
```

---

## 7. Known Limitations & Technical Debt

- **Visual Detection Scope**: Fixed 13-class taxonomy; no 3D depth estimation or volumetric pothole measurement; daytime bias in dataset.
- **NLP Normalization**: Rule-based normalization handles common vernacular expressions across 7 languages, but does not parse deep contextual slang or dialectical variation.
- **Government Portals**: External APIs (CPGRAMS, state systems) may be unconfigured or undergo sandbox downtime; CVKI gracefully degrades to `UNKNOWN_OUTCOME` or queueing rather than fabricating success.
- **Deployment**: Local engineering baseline validated; cloud deployment and multi-region clustering not pre-packaged.

For comprehensive details, see [`docs/m12_known_limitations.md`](docs/m12_known_limitations.md).

---

## 8. Documentation Index

- [Complete System Audit (M12.1)](docs/m12_1_system_audit.md)
- [Research Reproducibility & Experiment Registry (M12.3)](docs/m12_reproducibility.md)
- [Final Security & Privacy Audit (M12.4)](docs/m12_security_audit.md)
- [Final Epistemic Safety Audit (M12.5)](docs/m12_epistemic_safety_audit.md)
- [Final System Architecture (M12.7)](docs/m12_final_architecture.md)
- [API Reference (M12.7)](docs/m12_api_reference.md)
- [Deployment Guide (M12.7 / M12.8)](docs/m12_deployment.md)
- [User Guide (M12.7)](docs/m12_user_guide.md)
- [Developer Guide (M12.7)](docs/m12_developer_guide.md)
- [Known Limitations (M12.7)](docs/m12_known_limitations.md)
- [Final Research & Product Evaluation (M12.9)](docs/m12_final_evaluation.md)
- [CVKI v1 Final Freeze & Sign-Off (M12.10)](docs/m12_final_signoff.md)
