# CVKI Module 10.4: Evidence-Aware Decision Support Engine

## 1. Overview
Module 10.4 synthesizes evidence from across CVKI modules into an explainable, structured triage recommendation for municipal authorities and field personnel.

### Pipeline Synthesis
- **M1/M8 CV Intelligence**: Detection class, confidence, bounding boxes
- **M9.4 Vernacular Intelligence**: Normalized text, detected language
- **M9.2 Consistency Intelligence**: Cross-modal alignment assessment
- **M9.3 Active Clarification**: Ambiguity and pending clarification signals
- **M9.5 Visual Resolution Audit**: Before/after physical repair outcome
- **M4/M5 Geospatial & Recurrence**: Recurrence counts, repeat defect indicators
- **M10.3 Playbook Intelligence**: Matched action items, mitigation measures, checkpoints

## 2. Evidence Quality Assessment
Every case is classified into one of seven deterministic evidence quality tiers:
1. `STRONG`: High-confidence CV detection and aligned citizen report.
2. `PARTIAL`: Visual evidence present without citizen text, or text present without CV detection.
3. `WEAK`: Visual detection confidence below operational threshold (< 0.30) or low text clarity.
4. `MISSING`: Both visual imagery and descriptive text absent.
5. `CONFLICTING`: Severe cross-modal divergence between citizen report and visual detection.
6. `STALE`: Evidence collected outside operational validity window.
7. `UNAVAILABLE`: Upstream data source or provider unreachable.

## 3. Endpoints & Access Control
- `GET /api/v1/decision-support/cases/{reference_id}`: Retrieves decision support recommendations.
- `POST /api/v1/decision-support/cases/{reference_id}/evaluate`: Re-evaluates case with contextual weather or traffic updates. Client overrides of priority and recurrence are strictly ignored in favor of server truth.

## 4. Epistemic Safety Guarantees
- `epistemic_state = SYSTEM_DERIVED` unconditionally.
- `human_review_required = True` on all decision support recommendations.
- Never asserts physical ground truth or municipal legal orders.
- Never automatically executes case resolution, closure, or field dispatch.
