# CVKI Module 10.5: Field Inspection Protocol & Audit Engine

## 1. Overview
Module 10.5 formalizes field inspection workflows for municipal engineering crews and civic inspectors. It provides structured, deterministic inspection protocols and audits field submissions against photographic, geospatial, and temporal evidence without claiming physical ground truth.

### Key Capabilities
- **Deterministic Protocol Generation**: Generates targeted field inspection protocols based on category-specific action playbooks (M10.3) and synthesized decision context (M10.4).
- **Physical Verification Checkpoints**: Enumerates explicit physical checkpoints (e.g. aperture measurement, debris blockage check, structural integrity) with clear safety prerequisites.
- **Automated Submission Auditing**: Validates completed inspection reports against GPS proximity (< 150m), timestamp validity (within 24h), photographic evidence, and checklist completeness.
- **Epistemic Invariance**: Inspector observations remain classified as `FIELD_OBSERVATION`. Automated audits assign `SYSTEM_DERIVED` evaluation without asserting unobserved physical ground truth.

## 2. Inspection Protocol Schema
Each generated protocol (`FieldInspectionProtocol`) includes:
- `protocol_id`: Deterministic UUID identifier.
- `case_reference_id`: Associated civic complaint reference.
- `category`: Civic defect category.
- `required_checkpoints`: Sequence of physical checks, measurement fields, and required photographic angles.
- `safety_guidelines`: Mandatory PPE and hazard notices (e.g. reflective vests, atmospheric gas testing).
- `equipment_needed`: Required municipal tools (e.g. manhole hook, depth gauge, dewatering pump).
- `epistemic_state`: `SYSTEM_DERIVED`.

## 3. Submission Audit & Outcome Determination
When an inspector submits an inspection report (`FieldInspectionSubmission`), the audit engine evaluates:
1. **Defect Confirmation**: Did physical inspection confirm, refute, or mark the issue as inconclusive?
2. **Geospatial Proximity**: Was the inspection logged within operational tolerance (<= 150m) of the reported coordinates?
3. **Evidence Completeness**: Were required checkpoint photos attached and validated?
4. **Follow-Up Necessity**: Does the defect require immediate contractor requisition, emergency barricading, or routine scheduling?

Outcomes:
- `CONFIRMED`: Defect physically verified on site with matching photographic and geospatial proof.
- `REFUTED`: Defect verified absent or false positive.
- `INCONCLUSIVE`: Inadequate visual evidence, site inaccessible, or severe geospatial discrepancy.

## 4. Endpoints & Permissions
- `GET /api/v1/inspection/protocol/{reference_id}`: Generates or retrieves protocol for field personnel (`authority`, `admin`).
- `POST /api/v1/inspection/submit`: Submits completed inspection checklist and runs automated audit (`authority`, `admin`).
- `GET /api/v1/inspection/audit/{audit_id}`: Retrieves completed audit report and compliance metrics (`authority`, `admin`).

## 5. Epistemic Safety Invariants
- Field inspection records never execute autonomous case closure or contractor dispatch.
- Audit outcomes provide structured evidence to human dispatchers; final municipal sign-off requires human authorization.
