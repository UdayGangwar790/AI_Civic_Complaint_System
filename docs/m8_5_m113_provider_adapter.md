# CVKI — Module 8.5: Frozen M1.13 YOLO Provider Adapter

## Executive Summary
Module 8.5 implements the concrete provider adapter `M113YOLOProvider` wrapping the frozen M1.13 baseline checkpoint:
`ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`
Cryptographic SHA-256: `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3`.

This adapter strictly enforces the **YOLO Isolation Rule**:
Only `M113YOLOProvider` may import and depend on `ultralytics`, `YOLO`, `Results`, `Boxes`, or PyTorch tensor primitives. Downstream services and APIs interact exclusively with `CVInferenceProvider` and `StandardDetectionResult`.

---

## Architectural Details

### 1. Provider Identity & Metadata
- **Class**: `M113YOLOProvider(CVInferenceProvider)`
- **Model ID**: `m1.13-yolov8n`
- **Provider ID**: `m113_yolo_provider`
- **Model Version**: `1.13.0`
- **Framework**: `ModelFramework.ULTRALYTICS_YOLO`
- **Task Type**: `ModelTaskType.OBJECT_DETECTION`
- **Default Confidence**: `0.25` (preserves existing production baseline)

### 2. Class Taxonomy Binding
The provider validates and enforces the fixed 3-class civic taxonomy:
- `0`: `open_damaged_manhole`
- `1`: `damaged_missing_road_sign`
- `2`: `road_waterlogging`

### 3. Model Integrity Verification
Upon `initialize()`, the adapter:
1. Resolves model reference via `resolve_safe_model_reference`, blocking path traversal tokens.
2. Computes the streaming SHA-256 checksum across the weights file.
3. Compares the digest against `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3`. If mismatched, raises `ModelIntegrityError`.
4. Validates native model class dictionary against the required 3-class mapping.

### 4. Lifecycle & Thread Safety
- Multi-threaded execution is synchronized via thread locks.
- `infer()` accepts either a PIL Image or raw `image_bytes`, processes inference with confidence thresholds, measures elapsed duration in milliseconds, and constructs a `StandardDetectionResult`.
- `shutdown()` safely unloads weights and resets memory footprint.

---

## Parity Verification Results
Controlled parity validation compared `YOLOModelService.predict()` and `M113YOLOProvider.infer()` across representative held-out dataset images (manholes, road signs, waterlogging hazards, and synthetic negatives):
- **Detection Count Agreement**: 100% exact match.
- **Class ID & Label Agreement**: 100% exact match.
- **Pixel Coordinate Agreement**: Exact integer equality (`x1`, `y1`, `x2`, `y2`).
- **Confidence Agreement**: Strict floating point equality within `1e-4`.
- **Threshold Consistency**: Identical behavior at default `0.25` and on confidence overrides.
