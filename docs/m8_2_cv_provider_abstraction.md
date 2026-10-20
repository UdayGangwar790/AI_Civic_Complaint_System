# CVKI — Module 8.2: CV Provider Abstraction SPI Documentation

**Module:** M8.2  
**Component:** Computer Vision Provider Abstraction SPI (`CVInferenceProvider`)  
**Status:** IMPLEMENTED (SPI Abstraction Only — Production Inference Untouched)  
**Baseline Model:** M1.13 YOLOv8n (Frozen Baseline Checkpoint)  
**M1.13 SHA-256:** `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3` (Verified Unchanged)

---

## 1. Purpose

Module M8.2 establishes a framework-agnostic **Service Provider Interface (SPI)** and standardized data contracts for Computer Vision inference engines in the CVKI platform.

In Modules M1 through M7, computer vision detection was tied directly to a concrete singleton service (`YOLOModelService`) which imported `ultralytics.YOLO` and parsed proprietary `Results.boxes` tensor structures. While this was necessary to stand up the initial end-to-end civic prototype, continuing this direct coupling into M9–M12 would severely constrain the system:
1. It would prevent switching or upgrading to future vision architectures (Vision Transformers, RT-DETR, multi-frame video temporal models, object tracking, or instance segmentation).
2. It would force downstream subsystems (Evidence Provenance Engine, Civic Knowledge Graph, Government Adapters) to depend on YOLO-specific conventions.
3. It would blur the boundary between production serving and future post-M12 supercomputing research.

M8.2 resolves this by defining an abstract, model-agnostic provider contract (`CVInferenceProvider`) and generic detection schemas without modifying the existing production M1.13 inference path.

---

## 2. Why Provider Abstraction Is Required

### 2.1 Strategic Context
Heavy computer vision research—including larger multi-class road defect datasets, video sequence modeling, temporal optical flow, and hyperparameter searches—is intentionally deferred until **AFTER Module M12**, when supercomputing resources become available.

To guarantee that M8 through M12 develop cleanly without hardcoding YOLOv8 internals, M8 establishes a clean abstraction boundary. When upgraded models are trained post-M12, they will implement this SPI and plug into the platform seamlessly without requiring alterations to API routers, frontend components, or backend database schemas.

### 2.2 Framework Decoupling
The base provider abstraction in `backend/app/services/cv/base_provider.py` contains:
- **ZERO imports** of `ultralytics`, `torch`, or any proprietary CV engine.
- Complete independence from GPU/CPU tensor layouts.
- Pure Python and Pydantic v2 data models for maximum serializability and validation safety.

---

## 3. CVInferenceProvider Contract

The abstract provider interface defines a standard five-phase lifecycle:

```python
class CVInferenceProvider(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> ModelDescriptor:
        """Returns the ModelDescriptor identifying this provider's model and capabilities."""
        pass

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Returns True if the model weights are loaded and ready to serve inference requests."""
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """Initializes the model, loads weights into memory, and verifies readiness."""
        pass

    @abstractmethod
    def infer(self, request: InferenceRequest) -> StandardDetectionResult:
        """Executes inference on the provided request and returns a StandardDetectionResult."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Releases all model resources, memory maps, or device sessions cleanly."""
        pass
```

### Lifecycle Semantics:
1. **Descriptor (`descriptor`)**: Provides immutable metadata regarding model identity (`model_id`, `model_name`, `model_version`), task type, framework, SHA-256 hash, supported classes, and default confidence thresholds.
2. **Readiness Probe (`is_loaded`)**: Non-blocking boolean property indicating whether weights are memory-mapped and inference can execute safely.
3. **Initialization (`initialize()`)**: Idempotent method executed during application startup or provider registration. Loads weights and verifies model integrity.
4. **Inference (`infer()`)**: Thread-safe execution method accepting an `InferenceRequest` and returning a standardized `StandardDetectionResult`.
5. **Teardown (`shutdown()`)**: Graceful resource reclamation releasing memory maps, CUDA contexts, or thread locks.

---

## 4. Generic Request and Result Concepts

### 4.1 Input: `InferenceRequest`
A flexible input wrapper accommodating:
- `image`: Pillow `Image` object or array-like visual representation.
- `image_bytes`: Encoded binary payload (JPEG, PNG, WEBP).
- `confidence_override`: Optional per-request threshold overriding model defaults.
- `timestamp`: UTC timestamp of the capture or submission event.
- `metadata`: Extensible dictionary for future context (frame sequence index, camera telemetry, GPS coordinates).

### 4.2 Output: `StandardDetectionResult`
A framework-agnostic result container:
- `success`: Boolean execution flag.
- `model_id`: Unique identifier of the executing model.
- `model_version`: Artifact release version string.
- `total_detections`: Integer count of detected objects meeting threshold.
- `detections`: List of `StandardDetection` objects.
- `inference_duration_ms`: Execution latency in milliseconds.
- `image_width` / `image_height`: Resolved image dimensions.
- `metadata`: Extensible metadata dictionary for future temporal context, frame counts, or tracking history.

### 4.3 Detection Primitive: `StandardDetection`
- `class_id`: Integer taxonomy ID.
- `class_name`: Semantic class label (e.g. `"open_damaged_manhole"`).
- `confidence`: Calibrated confidence score strictly in `[0.0, 1.0]`.
- `bbox`: `StandardBoundingBox` with pixel coordinates `(x1, y1, x2, y2)` and optional normalized coordinates `(norm_x1, norm_y1, norm_x2, norm_y2)`. Enforces `x1 <= x2`, `y1 <= y2`, and non-negative boundaries.
- `category`: Domain grouping (defaults to `"road_hazard"`).
- `metadata`: Extensible dictionary for future segmentation polygons or tracking track IDs.

---

## 5. Mock Provider Testing

The provider SPI was rigorously verified using an isolated in-memory `MockCivicDetectionProvider` in `backend/tests/test_cv_provider_abstraction.py`.

The 10-point test suite proved that:
1. `CVInferenceProvider` cannot be instantiated directly without implementing abstract methods (`TypeError`).
2. Concrete providers implement the SPI cleanly.
3. `ModelDescriptor` exposes complete model metadata.
4. `initialize()` transitions state to loaded.
5. `is_loaded` reports readiness accurately.
6. `infer()` accepts `InferenceRequest` and produces valid `StandardDetectionResult`.
7. `shutdown()` releases state and prevents uninitialized inference.
8. The provider interface does not import or require Ultralytics or Torch.
9. Normalized detection and bounding box structures serialize and deserialize without loss.
10. Strict Pydantic validation rejects negative coordinates, inverted bounding boxes, or out-of-range confidence scores.

---

## 6. Current Production Baseline Remains Unchanged

**CRITICAL INVARIANT:**  
The existing production computer vision pipeline was **NOT modified** in Module M8.2:
- [backend/app/services/computer_vision.py](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/services/computer_vision.py) (`YOLOModelService`) remains active and untouched.
- `POST /api/v1/detection/predict` continues serving live M1.13 inference via the legacy singleton.
- `GET /api/v1/model/status` continues returning the active M1.13 status.
- FastAPI `lifespan` in [backend/app/main.py](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/backend/app/main.py) continues loading M1.13 at startup.
- The browser frontend in [frontend/src/App.jsx](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/frontend/src/App.jsx) continues operating without change.
- All existing tests in `test_detection_api.py` and `test_model_integration.py` continue to pass 100%.

---

## 7. Upcoming Modules

- **Module M8.3 — Model Registry:**
  Will introduce `ModelRegistry` and descriptor management. It will register the frozen M1.13 baseline with SHA-256 verification and manage active provider dispatch.
- **Module M8.4 — Standardized Schemas & Contracts:**
  Will extend and formalize standardized contracts across API layers if needed.
- **Module M8.5 — M1.13 YOLOv8 Provider Adapter:**
  Will encapsulate the frozen M1.13 checkpoint into a concrete `YOLOv8InferenceProvider` implementing `CVInferenceProvider`.
- **Module M8.6 — Compatibility Integration & Orchestration:**
  Will transition the FastAPI detection route to the new provider architecture while preserving 100% backwards compatibility.

---

## 8. Explicit Limitations of M8.2

1. **No Runtime Model Switching**: M8.2 only establishes the interface; dynamic provider switching requires M8.3 ModelRegistry.
2. **No M1.13 Migration Yet**: M1.13 has not been wrapped in `YOLOv8InferenceProvider` (scheduled for M8.5).
3. **No Video/Tracking Execution**: Video buffering, temporal persistence, and tracking algorithms are deferred until post-M12 research; M8.2 only provides extensible data fields (`metadata`) so future implementations do not break the schema.
