# CVKI — Module 8.7: Computer Vision Provenance & Knowledge Graph Integration

## Executive Summary
Module 8.7 integrates computer vision detections into the existing Evidence Provenance Engine (M6.4) and Civic Knowledge Graph (M6.5).

Critically, Module 8.7 establishes clear **Semantic Boundaries**:
A computer vision inference is formally registered as a **Model Observation**. It represents algorithmic feature correlation and model output confidence (evidence strength); it does NOT constitute physical ground truth, legal certainty, statutory confirmation, or government verification.

---

## Architectural Schema & Subsystem Linkage

```
               StandardDetectionResult (M8.4 / M8.5)
                                 ↓
                     Complaint Case Pipeline
                                 ↓
            ┌────────────────────┴────────────────────┐
            ↓                                         ↓
 Evidence Provenance Engine (M6.4)        Civic Knowledge Graph (M6.5)
            ↓                                         ↓
   ClaimType.DETECTION Node                   KnowledgeNode (DETECTION)
   - source_type: CV_MODEL                    - model_id: m1.13-yolov8n
   - model_id: m1.13-yolov8n                  - model_version: M1.13-yolov8n
   - model_version: M1.13-yolov8n             - provider_id: m113_yolo_provider
   - model_hash: 602160d4...                  - observation_type: model_obs
   - provider_id: m113_yolo_provider          - Relationships:
   - observation_type: model_obs                 * Case -DETECTED_AS-> Issue
   - ground_truth: False                         * Case -GENERATED_FROM-> Detection
```

---

## Provenance Integration Details (M6.4)
- **Claim Representation**: `ClaimType.DETECTION` records:
  - `source_type`: `SourceType.CV_MODEL`
  - `source`: Dynamic model string (e.g., `m1.13-yolov8n Detection Model`).
  - `claim_value`: Semantic class name (e.g., `open_damaged_manhole`).
  - `metadata`: Contains `confidence`, `model_id`, `model_version`, `model_hash`, `provider_id`, `task_type`, and bounding box coordinates.
- **Evidence Confidence Meaning**: `confidence` reflects statistical evidence strength. It does not alter priority score algorithms or emergency response escalation policies independently of verified multi-source corroboration.

---

## Knowledge Graph Integration Details (M6.5)
- **Node Topology**:
  - `NodeType.CASE`: Root entity with status and canonical reference.
  - `NodeType.CIVIC_ISSUE`: Semantic issue category.
  - `NodeType.DETECTION`: Explicit observation node cataloging model identity and provider ID.
- **Edge Semantics**:
  - `RelationType.DETECTED_AS`: Connects Case to Civic Issue with `VerificationState` derived from underlying evidence.
  - `RelationType.GENERATED_FROM`: Connects Case to Detection Node, stamped with `SourceType.CV_MODEL`.
- **Invalidation Consistency**: When human inspectors or authority updates invalidate evidence (`VerificationState.NOT_VERIFIED` or status `invalidated`), graph edges reflect the unverified state and do not treat invalidated model observations as active support.

---

## Security & RBAC Enforcement
- **Citizen Isolation**: Citizens can view only their own complaint provenance chains (`case.user_id == authenticated_user.id`).
- **Authority Scope**: Municipal authorities can access evidence chains only for cases in their jurisdictional assignments.
- **No Path Leakage**: Internal file paths (such as `best.pt`, Windows drive letters, or weight storage directories) are never written to MongoDB collections or exposed in API representations.
