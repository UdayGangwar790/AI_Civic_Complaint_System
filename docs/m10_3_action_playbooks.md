# CVKI Module 10.3: Civic Action Playbook Knowledge Base & Schema

## 1. Overview
Module 10.3 establishes a deterministic, structured knowledge base of civic response playbooks. It provides authorized human decision-makers (dispatchers, inspectors, engineers) with standardized, evidence-grounded action recommendations.

Crucially:
- **Zero Generative Hallucination**: Playbooks are versioned, deterministic schemas, not uncontrolled LLM text.
- **Decision Support Boundary**: Action items are clearly labeled as algorithmic suggestions, not official government orders or legal mandates.
- **Prohibited Assumptions**: Every playbook declares explicit cognitive caveats (e.g. do not assume manhole cover was stolen without physical proof).

## 2. Built-in Civic Playbooks

| Playbook ID | Version | Category | Primary Focus |
|---|---|---|---|
| `PB-MANHOLE-SAFETY-V1` | 1.0.0 | `OPEN_DAMAGED_MANHOLE` | Immediate aperture barricading, physical depth measurement, frame inspection, utility conduit routing |
| `PB-WATERLOGGING-DRAIN-V1` | 1.0.0 | `ROAD_WATERLOGGING` | Catch basin inspection within 50m, debris de-silting, portable dewatering pump evaluation |
| `PB-ROAD-SIGN-HAZARD-V1` | 1.0.0 | `DAMAGED_MISSING_ROAD_SIGN` | Pole vertical stability check, sightline clearing, standard retro-reflective plate requisition |
| `PB-GENERIC-CIVIC-V1` | 1.0.0 | `OTHER_CIVIC_ISSUE`, `UNKNOWN` | General walkthrough verification, landmark identification, jurisdiction ascertainment |

## 3. Schema & Matching Logic
- **`PlaybookTriggerConditions`**: Evaluates `allowed_categories`, `min_priority`, `requires_cv_detection`, `requires_rain_context`, and `requires_recurrence`.
- **`PlaybookEvidenceRequirements`**: Specifies mandatory and recommended evidence, plus on-site physical inspection checkpoints.
- **`ActionPlaybookRegistry`**: In-memory, thread-safe, extensible registry allowing custom playbook registration and deterministic scoring.
