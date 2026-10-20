# CVKI M12.7: Complete API Reference

This document provides the canonical API reference for the CVKI platform backend at Release Baseline M12.

All API routes are prefixed by `/api/v1` (with health and metrics hosted under `/api/health` and `/metrics`).

---

## 1. System Health & Observability

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health/live` | None | Liveness probe verifying process is responsive |
| `GET` | `/api/health/ready` | None | Readiness probe verifying DB connectivity and model availability |
| `GET` | `/metrics` | None (or Scrape Token) | Prometheus-formatted runtime and operational metrics |

---

## 2. Authentication & User Management

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | None | Register new citizen account |
| `POST` | `/api/v1/auth/login` | None | Authenticate user; returns JWT token + secure session cookie |
| `POST` | `/api/v1/auth/refresh` | Bearer Token | Refresh active session token |
| `GET` | `/api/v1/auth/me` | Bearer Token | Get authenticated user identity and role |

---

## 3. Computer Vision & Hazard Detection

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/detection/predict` | Optional | Execute standardized hazard detection on uploaded image (`M1.13` YOLOv8n) |
| `GET` | `/api/v1/detection/models` | None | List active and registered CV models in the model registry |
| `GET` | `/api/v1/detection/model-status`| Admin | Safe health status and checksum verification of loaded model |

---

## 4. Location & Authority Resolution

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/location/reverse` | None | Reverse geocode coordinates to structured road, corridor, and city |
| `POST` | `/api/v1/authority/resolve` | None | Resolve responsible road owner, maintenance authority, and concessionaire |
| `GET` | `/api/v1/authority/sources` | Authority / Admin | Query verified government registry sources and citations |

---

## 5. Complaint Case Lifecycle

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/complaint/cases` | Citizen | Submit a new complaint case with image, location, and description |
| `GET` | `/api/v1/complaint/cases/{ref}`| Owner / Authority | Retrieve case details, priority score, and current status |
| `POST` | `/api/v1/complaint/guidance` | None | Generate multi-lingual factual guidance draft for citizen report |
| `GET` | `/api/v1/complaint/history` | Citizen | List complaints submitted by authenticated citizen |

---

## 6. Multimodal Intelligence & Active Clarification

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/multimodal/process` | Citizen / Authority | Ingest multimodal report; evaluate text, CV, and location alignment |
| `POST` | `/api/v1/multimodal/consistency`| Citizen / Authority | Cross-modal consistency evaluation between visual and verbal claims |
| `POST` | `/api/v1/multimodal/clarify` | Citizen | Submit response to active clarification question (tagged `USER_REPORTED`) |

---

## 7. Decision Support & Operational Playbooks

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/decision-support/evaluate`| Authority / Admin | Generate action playbook recommendations and triage strategy |
| `POST` | `/api/v1/decision-support/cases/{ref}/review` | Authority | Record human review decision (`ACCEPTED`, `MODIFIED`, `REJECTED`) |
| `POST` | `/api/v1/decision-support/cases/{ref}/clarify` | Citizen / Authority | Submit targeted clarification notes for active case decision |
| `GET` | `/api/v1/decision-support/cases/{ref}/graph` | Authority / Admin | Query bounded knowledge graph subgraph surrounding case |
| `GET` | `/api/v1/decision-support/cases/{ref}/provenance` | Authority / Admin | Retrieve cryptographic SHA-256 evidence provenance chain |

---

## 8. Field Inspection & Verification

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/field-inspection/protocol` | Authority | Generate standardized physical verification checklist with geofence |
| `POST` | `/api/v1/field-inspection/submit` | Field Inspector | Submit completed inspection checklist, coordinates, and photo evidence |
| `GET` | `/api/v1/field-inspection/records/{id}` | Authority | Retrieve field inspection record and automated completeness audit |

---

## 9. Government Integration & Analytics

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/government/integrations`| Admin | Status of external portal adapters (CPGRAMS, state portals) |
| `POST` | `/api/v1/government/sync/{ref}` | Authority / Admin | Trigger status synchronization with external municipal portal |
| `GET` | `/api/v1/admin/analytics` | Admin | Aggregate incident analytics, resolution velocity, and recurring corridors |
| `GET` | `/api/v1/admin/hotspots` | Admin | 30-day reporting concentration hotspots and recurring infrastructure defects |
