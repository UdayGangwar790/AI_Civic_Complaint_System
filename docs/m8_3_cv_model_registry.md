# CVKI — Module 8.3: CV Model Registry & Lifecycle Management

**Module:** M8.3  
**Component:** Computer Vision Model Registry (`ModelRegistry`)  
**Status:** IMPLEMENTED (Metadata & Lifecycle Only — Production Inference Untouched)  
**Baseline Model:** M1.13 YOLOv8n (Frozen Baseline Checkpoint)  
**M1.13 SHA-256:** `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3` (**VERIFIED EXACT**)

---

## 1. Purpose

Module M8.3 establishes a centralized, thread-safe **Computer Vision Model Registry** responsible for model identity, cryptographic checksum verification, evaluation benchmarks, and deterministic lifecycle management.

In Modules M1 through M7, the production vision model was identified purely via configuration strings (`settings.YOLO_MODEL_VERSION`) and hardcoded filesystem paths (`settings.YOLO_MODEL_PATH`). This design lacked formal model provenance, prevented multi-model version tracking, had no stateful promotion/rollback controls, and risked accidental configuration drift.

M8.3 introduces the `ModelRegistry` service, formalizing model identity as a first-class citizen while keeping the existing production inference path (`YOLOModelService`) completely intact.

---

## 2. Model Identity Design

In CVKI CV 2.0, a computer vision model is uniquely identified by its semantic identity rather than a mutable file path or arbitrary filename.

The registry tracks:
- `model_id`: Unique canonical string (e.g., `"m1.13-yolov8n"`). Must be alphanumeric with `.`, `_`, or `-`.
- `model_name`: Human-readable architecture or family name (e.g., `"CVKI YOLOv8n Baseline"`).
- `model_version`: Structured semantic release string (e.g., `"1.13"`).
- `provider_id`: Identifier of the provider engine capable of executing this model (e.g., `"yolov8_provider"`).
- `framework`: Canonical framework enum (`ModelFramework.ULTRALYTICS_YOLO`, `ONNX_RUNTIME`, `HUGGINGFACE_TRANSFORMER`).
- `task_type`: Vision task (`ModelTaskType.OBJECT_DETECTION`, `INSTANCE_SEGMENTATION`, `VIDEO_TRACKING`).
- `sha256_hash`: 64-character lowercase hexadecimal hash uniquely fingerprinting the model weights artifact.
- `model_reference`: Safe internal path reference relative to the project root (e.g., `"ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt"`).
- `supported_classes`: Mapping of integer class IDs to semantic labels (`{0: "open_damaged_manhole", ...}`).
- `default_confidence_threshold`: Configured threshold for prediction filtering (defaults to `0.25`).

---

## 3. Registry Architecture

```
                       [ ModelRegistry (Singleton Service) ]
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
        ▼                                ▼                                ▼
[ Model Catalog ]             [ State Machine ]               [ Integrity Engine ]
 - In-memory index             - Deterministic legal           - Cryptographic SHA-256
 - Thread-safe (Lock)            state transitions               file verification
 - Fast O(1) lookups           - Controlled activation         - Zero file mutations
 - Seeded with M1.13             and retirement                - Path traversal defense
```

### Storage Decision
Following the established architectural pattern of [authority_registry.py](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/services/authority_registry.py) and [government_registry.py](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/services/government_registry.py), the `ModelRegistry` operates as a **thread-safe, in-memory catalog** seeded with immutable baseline descriptors. This ensures:
1. Ultra-fast, zero-overhead lookups during request dispatch without database latency.
2. Complete determinism and test isolation via `reset()`.
3. Zero risk of database schema corruption or desynchronization with filesystem weights.

---

## 4. Lifecycle State Machine

The registry enforces strict, deterministic lifecycle states to prevent unverified or broken models from being deployed.

### States
- `REGISTERED`: Model metadata cataloged; not yet validated or tested.
- `VALIDATING`: Cryptographic checksum and runtime compatibility checks in progress.
- `EVALUATED`: Benchmark evaluation metrics verified on held-out test splits.
- `ACTIVE`: Designated as the single active production model.
- `RETIRED`: Deprecated model that has been superseded by a newer model release.
- `DISABLED`: Administratively deactivated model (terminal state).

### Legal Transitions
```
REGISTERED ──► VALIDATING ──► EVALUATED ──► ACTIVE ──► RETIRED ──► DISABLED
                   │                                     ▲
                   └──► DISABLED                         │
                                                         │ (Explicit Rollback)
                                                         └──────────┘
```

| Source State | Target State | Description |
|---|---|---|
| `REGISTERED` | `VALIDATING` | Checksum and artifact presence verification initiated. |
| `REGISTERED` | `DISABLED` | Rejected before validation due to malformed specs. |
| `VALIDATING` | `EVALUATED` | Offline benchmarks confirmed on held-out test sets. |
| `VALIDATING` | `DISABLED` | Failed checksum or compatibility validation. |
| `EVALUATED` | `ACTIVE` | Explicit promotion to active production model. |
| `EVALUATED` | `DISABLED` | Rejected during pre-deployment evaluation review. |
| `ACTIVE` | `RETIRED` | Superseded by newly promoted active model. |
| `ACTIVE` | `DISABLED` | Emergency administrative decommission. |
| `RETIRED` | `ACTIVE` | Controlled operational rollback to a prior verified model. |
| `RETIRED` | `DISABLED` | Permanent decommission. |
| `DISABLED` | *(None)* | Terminal state; models cannot transition out of `DISABLED`. |

Attempting any transition outside this table raises `InvalidLifecycleTransitionError`.

---

## 5. SHA Integrity & Security Boundaries

### 5.1 SHA-256 Format & Verification
- All registered SHA-256 hashes must be strictly 64 hexadecimal characters (`^[0-9a-f]{64}$`).
- `verify_model_integrity(model_id)` reads the physical artifact chunk-by-chunk (64 KB buffers) to calculate the real SHA-256 and assert exact equality with the registered hash.
- **Verification is read-only**: the physical weights file is never written to, moved, or altered.

### 5.2 Model Reference Safety & Path Traversal Defense
`resolve_safe_model_reference(reference)` enforces absolute path safety:
1. Rejects null bytes (`\0`) and parent traversal tokens (`..`).
2. Resolves relative references strictly against `get_project_root()`.
3. Verifies using `path.relative_to(project_root)` that the target resides inside the repository workspace.
4. Prevents arbitrary file-loader exploits.

---

## 6. Evaluation Metadata

Evaluation benchmarks are captured using structured Pydantic models:
- `SplitEvaluationMetrics`: `split_name`, `precision`, `recall`, `map50`, `map50_95`, `per_class_metrics`.
- `ModelEvaluationMetadata`: `experiment_id`, `dataset_version`, `evaluation_date`, `duration`, `completed_epochs`, `best_epoch`, `best_fitness`, `validation_metrics`, `held_out_splits`.

**Preservation Invariant:** All metric fields are optional floats. Missing metrics remain `None` and are **never** coerced to `0.0`, preventing metric fabrication.

---

## 7. M1.13 Production Baseline Registration

The frozen M1.13 model is seeded as the permanent initial baseline:
- `model_id`: `"m1.13-yolov8n"`
- `model_name`: `"CVKI YOLOv8n Baseline"`
- `model_version`: `"1.13"`
- `provider_id`: `"yolov8_provider"`
- `framework`: `"ultralytics_yolo"`
- `task_type`: `"object_detection"`
- `sha256_hash`: `"602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"`
- `model_reference`: `"ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt"`
- `supported_classes`: `{0: "open_damaged_manhole", 1: "damaged_missing_road_sign", 2: "road_waterlogging"}`
- `default_confidence_threshold`: `0.25`
- `lifecycle_status`: `ACTIVE`
- `evaluation_metadata`: Populated with exact, verified metrics from `m1_13_summary.json`:
  - `val_m1_13`: P=0.726, R=0.590, mAP50=0.643, mAP50-95=0.417
  - `m1_8_held_out_test`: P=0.838, R=0.612, mAP50=0.654, mAP50-95=0.487
  - `m1_11_improved_held_out_test`: P=0.650, R=0.570, mAP50=0.568, mAP50-95=0.423

---

## 8. Active Model Semantics & Non-Automatic Promotion

1. **No Automatic Activation:** Registering a model via `register_model()` places it in `REGISTERED` status regardless of requested parameters.
2. **Explicit Activation Required:** Only an explicit call to `activate_model()` (transitioning from `EVALUATED` or `RETIRED`) can promote a model to `ACTIVE`.
3. **Single Active Model Invariant:** Exactly ONE model is `ACTIVE` at any given time. Promoting Model B automatically transitions the previously active Model A to `RETIRED`.
4. **Controlled Rollback:** A `RETIRED` model can be re-promoted to `ACTIVE` through `activate_model()`, providing deterministic operational rollback.

---

## 9. Current Production Runtime Invariant

> ### **CRITICAL NOTICE: PRODUCTION RUNTIME UNTOUCHED**
> Module M8.3 does **NOT** alter the production inference execution path:
> - Production requests (`POST /api/v1/detection/predict`) continue using `YOLOModelService` in [computer_vision.py](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/services/computer_vision.py).
> - `ModelRegistry` is currently metadata-only and does not load weights into PyTorch memory.
> - `YOLOModelService` operates completely independently of `ModelRegistry`.
> - Integration between `ModelRegistry` and the inference engine will occur in **M8.5 (Adapter)** and **M8.6 (Orchestrator)**.

---

## 10. Downstream Dependencies

- **M8.4 (Standardized Schemas):** Will standardize inference responses across API boundaries.
- **M8.5 (M1.13 Provider Adapter):** Will package M1.13 inside `YOLOv8InferenceProvider` implementing `CVInferenceProvider`.
- **M8.6 (Runtime Orchestrator):** Will connect `CVInferenceService` to `ModelRegistry.get_active_model()` to dynamically dispatch requests to the active provider.
