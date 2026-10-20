# CVKI Module 10.6: Decision Provenance & Knowledge Graph Projection

## 1. Overview
Module 10.6 bridges the M10 Evidence-Aware Decision Support Engine with CVKI's core Evidence Provenance ledger (M6.4/M9.6) and Civic Knowledge Graph (M6.5/M9.6). It guarantees full cryptographic audibility and spatial-relational transparency for all algorithmic recommendations.

### Key Objectives
- **Cryptographic Provenance**: Every decision recommendation and human review is anchored as an immutable `EvidenceRecord` in the M6.4 provenance chain with SHA-256 integrity digests.
- **Relational Graph Projection**: Decision recommendations, playbooks, action items, and inspections are projected into the Civic Knowledge Graph as structured nodes and edges.
- **Epistemic Rigor**: Preserves strict separation between `MODEL_OBSERVATION`, `USER_REPORTED`, `FIELD_OBSERVATION`, `SYSTEM_DERIVED`, and `VERIFIED_EVIDENCE`.

## 2. Provenance Chain Integration
### Event Types Added
- `DECISION_RECOMMENDATION_GENERATED`: Recorded when M10.4 synthesizes evidence and generates a structured triage recommendation.
- `PLAYBOOK_MATCHED`: Captures the specific playbook, version, and trigger rules evaluated.
- `FIELD_INSPECTION_AUDITED`: Logs field inspection submissions and automated verification results.
- `AUTHORITY_REVIEWED`: Records municipal officer acceptance, override, or dismissal of recommendations.

### Evidence Record Invariants
- Each record has an immutable `record_id`, `case_reference_id`, `producer_module` (`M10.4_DECISION_SUPPORT`, `M10.5_INSPECTION`, `M10.6_PROJECTION`), timestamp, and payload SHA-256 hash.
- Previous record hash linking ensures tamper-evident chain continuity.

## 3. Civic Knowledge Graph Projection
### New Graph Node Types
- `DECISION_RECOMMENDATION`: Represents the synthesized recommendation (priority, quality tier, explanation).
- `ACTION_PLAYBOOK`: Represents the specific civic action playbook matched.
- `RECOMMENDED_ACTION`: Granular action item with urgency and responsible department.
- `FIELD_INSPECTION`: Inspection event with audit outcome, GPS coordinates, and inspector identity.

### New Graph Relation Types
- `EVALUATED_BY`: Links `CIVIC_CASE` to `DECISION_RECOMMENDATION`.
- `GOVERNED_BY_PLAYBOOK`: Links `DECISION_RECOMMENDATION` to `ACTION_PLAYBOOK`.
- `PROPOSES_ACTION`: Links `DECISION_RECOMMENDATION` to `RECOMMENDED_ACTION`.
- `INSPECTED_UNDER`: Links `FIELD_INSPECTION` to `ACTION_PLAYBOOK`.
- `VERIFIED_BY_INSPECTION`: Links `CIVIC_CASE` to `FIELD_INSPECTION`.

## 4. Endpoints & Graph Traversal
- `GET /api/v1/decision-support/cases/{reference_id}/provenance`: Returns the cryptographic evidence records associated with decision generation and review.
- `GET /api/v1/decision-support/cases/{reference_id}/graph`: Returns sub-graph nodes and edges representing the decision context, linked playbooks, and inspection history.

## 5. Epistemic Safety Guarantees
- Graph projections are declarative representations of algorithmic synthesis; they do not mutate live complaint status or override jurisdictional assignment.
- Verified status in graph edges is only asserted when supported by cryptographically verified field inspection audit records.
