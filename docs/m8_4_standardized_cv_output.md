# CVKI — Module 8.4: Standardized Computer Vision Output Contract

## Executive Overview
Module 8.4 completes the standardized, model-independent Computer Vision Output Contract for CVKI. Downstream subsystems (Case Workflows, Evidence Provenance Engine M6.4, Knowledge Graph M6.5, Government Integration Adapters M6.6, Escalation Engine M7.1, Resolution Verification M7.2, and Civic Analytics M7.3) must never bind directly to model-specific internal objects or framework tensors (such as `ultralytics.engine.results.Results`, `torch.Tensor`, or YOLO bounding box formats).

Instead, all CV execution engines produce framework-agnostic `StandardDetectionResult` instances containing `StandardDetection` primitives and `StandardBoundingBox` geometries.

---

## Architectural Schema

### 1. StandardBoundingBox
- **Pixel Coordinates**: `x1`, `y1`, `x2`, `y2` representing non-negative integer boundaries in original image space.
- **Normalized Coordinates**: Optional `norm_x1`, `norm_y1`, `norm_x2`, `norm_y2` bounded strictly within `[0.0, 1.0]`.
- **Validation Constraints**: Coordinates reject negative values, inversion (`x1 > x2` or `y1 > y2`), and inverted normalized bounds.
- **Computed Geometry**: Convenience properties `width`, `height`, and `area`.

### 2. StandardDetection
- **Taxonomy Binding**:
  - `class_id`: Non-negative integer.
  - `class_name`: Semantic problem label (`open_damaged_manhole`, `damaged_missing_road_sign`, `road_waterlogging`).
  - `category`: Domain grouping (default `"road_hazard"`).
- **Evidence Confidence**: Strictly validated float within `[0.0, 1.0]`.
- **Bounding Box**: Attached `StandardBoundingBox`.
- **Extensible Context**: `metadata` dictionary preserving segmentation contours, tracking IDs, or sensor telemetry without schema breakage.

### 3. StandardDetectionResult
- **Execution Status**: `success` boolean.
- **Model Identity**: `model_id`, `model_version`, `model_hash` (cryptographic SHA-256).
- **Provider Identity**: `provider_id`.
- **Task Identity**: `task_type` (`ModelTaskType.OBJECT_DETECTION`, extensible to segmentation, video tracking, temporal sequences).
- **Detections**: `total_detections` count and list of `StandardDetection` instances.
- **Inference Telemetry**: `inference_duration_ms`, `inference_timestamp` (UTC datetime), `confidence_threshold`.
- **Source Dimensions**: `image_width` and `image_height`.
- **Extensible Metadata**: Bidirectionally synchronized `metadata` and `provider_metadata` dictionaries.

---

## Zero-Leakage Framework Decoupling
Neither PyTorch nor Ultralytics is imported anywhere within `base_provider.py`. The downstream system remains completely insulated against future framework replacements or migrations (e.g., to ONNX Runtime, HuggingFace Transformers, or video sequence models).
