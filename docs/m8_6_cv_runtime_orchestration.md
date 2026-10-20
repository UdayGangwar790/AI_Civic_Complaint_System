# CVKI — Module 8.6: Computer Vision Runtime & API Orchestration

## Executive Summary
Module 8.6 introduces `CVInferenceService` and `ProviderResolver`, decoupling the application runtime and HTTP routing layers from model-specific execution logic.

Before M8.6, API endpoints directly coupled to `YOLOModelService`, invoking Ultralytics execution and in-memory YOLO boxes. Under M8.6, the detection API invokes the model-agnostic `CVInferenceService`, which dynamically resolves approved providers via the `ProviderResolver`, validates model lifecycle states via `ModelRegistry`, executes inference returning `StandardDetectionResult`, and renders visual bounding boxes via decoupled `renderer.py`.

---

## Architectural Workflow

```
   HTTP Request (POST /api/v1/detection/predict)
                        ↓
            Detection API Router
                        ↓
             CVInferenceService
                        ↓
           ┌────────────┴────────────┐
           ↓                         ↓
   ModelRegistry (M8.3)      ProviderResolver (M8.6)
   (Resolve Active Model)    (Resolve Approved Provider)
           └────────────┬────────────┘
                        ↓
                M113YOLOProvider
                        ↓
             StandardDetectionResult
                        ↓
        ┌───────────────┴───────────────┐
        ↓                               ↓
 Annotation Renderer          DetectionResponse
 (Base64 PNG Data URL)        (FastAPI REST Contract)
```

---

## Component Specifications

### 1. ProviderResolver
- **Controlled Whitelist**: Maps canonical provider IDs (`m113_yolo_provider`, `yolov8_provider`) to authorized provider factories.
- **Strict Security Guardrails**: Forbids client-supplied Python classes, dynamic import paths, filesystem traversal, or arbitrary code loading. Unapproved provider requests raise `ProviderNotFoundError`.
- **Instance Caching**: Caches initialized provider singletons, preventing redundant model instantiation and memory overhead across concurrent requests.

### 2. CVInferenceService
- **Model Resolution**: Queries `ModelRegistry.get_active_model()` (defaulting safely to active baseline `m1.13-yolov8n`).
- **Controlled Lifecycle**: Ensures model readiness via `is_loaded`, initializing weights once into memory.
- **Standardized Execution**: Produces `StandardDetectionResult` completely isolated from framework tensors.
- **Safe Inspection**: `get_model_status()` sanitizes model metadata, strictly blocking internal filesystem paths (`best.pt`, directories, drive names) from leaking to API clients.
- **Backward Compatibility**: Provides legacy dictionary mapping and image rendering wrappers (`predict_legacy_dict`, `predict_image`) ensuring zero breakage for frontend clients and existing test suites.

### 3. Decoupled Annotation Renderer
- Located in `backend/app/services/cv/renderer.py`.
- Uses Pillow (`PIL.ImageDraw`) to render high-visibility crimson bounding boxes, labels, and confidence tags.
- Returns standard Base64 Data URLs (`data:image/png;base64,...`) without relying on OpenCV, Torchvision, or Ultralytics plotting functions.
