# CVKI Module 10.2: Multimodal REST API Gateway & Pipeline Integration

## 1. Overview
Module 10.2 provides a unified, secure REST API entrypoint into the CVKI multimodal intelligence pipeline. It orchestrates:
- M9.4 Multilingual Vernacular Normalizer (Hindi/Hinglish to canonical civic terms)
- M8 Computer Vision SPI & Inference Provider
- M9.2 Cross-Modal Evidence Consistency & Grounding Engine
- M9.3 Active Clarification & Ambiguity Resolver
- M9.5 Before/After Visual Resolution Auditing
- M9.6 / M6.4 Cryptographic Provenance Engine
- M9.6 / M6.5 Knowledge Graph Engine

## 2. API Endpoints

### 2.1 Standalone Analysis
`POST /api/v1/multimodal/analyze`
- Evaluates raw citizen text, optional image paths, and visual detection results.
- Returns normalized text, cross-modal alignment assessment, clarification questions (if ambiguous), visual resolution audit results (if before/after images provided), provenance claims, and KG node keys.
- Rate limited and authenticated (Citizen, Authority, Admin).

### 2.2 Case-Linked Analysis
`POST /api/v1/multimodal/cases/{reference_id}/analyze`
- Associates analysis with an existing persisted `ComplaintCase`.
- Enforces strict role-based access control (RBAC):
  - **Citizen**: Can only analyze cases they created.
  - **Authority**: Can only analyze cases assigned to their user ID.
  - **Admin**: Unrestricted access.
- Automatically generates provenance claim linked to `case_reference`.

## 3. Epistemic Safety & Invariants
- `epistemic_state` is unconditionally enforced as `SYSTEM_DERIVED`.
- Gateway never declares physical ground truth and never performs automatic case resolution or closure.
- Input validation prevents oversized payloads (> 2000 characters) and path traversal in evidence references.
