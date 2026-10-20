# CVKI M12.3: Research Reproducibility & Experiment Registry

This document establishes the official research reproducibility record, experiment registry, and evaluation lineage for the CVKI (Civic Visual Knowledge Intelligence) platform at the M12 release baseline.

---

## 1. Frozen Baseline Model Metadata

The production Computer Vision detection baseline is strictly frozen at iteration **M1.13**.

| Attribute | Specification |
| :--- | :--- |
| **Model Architecture** | Ultralytics YOLOv8 Nano (`YOLOv8n`) |
| **Weights Path** | `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt` |
| **SHA-256 Hash** | `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3` |
| **Number of Classes** | 13 Civic Defect Classes |
| **Class Vocabulary** | `garbage`, `pothole`, `street_light_issue`, `water_leakage`, `fallen_tree`, `damaged_signboard`, `broken_bench`, `open_damaged_manhole`, `illegal_parking`, `sewage_overflow`, `encroachment`, `unauthorized_posters`, `loose_cables` |
| **Dataset Path** | `ai/computer_vision/dataset_m1_13` |
| **Total Dataset Files** | Exactly 605 files (images + labels + split manifests) |
| **Inference Configuration**| `confidence_threshold = 0.25`, `iou_threshold = 0.45`, `image_size = 640` |
| **Epistemic Classification**| `MODEL_OBSERVATION` (strictly unverified until corroborated or inspected) |
| **Lifecycle State** | `FROZEN_PRODUCTION_BASELINE` |

---

## 2. Historical Evaluation Baselines

The table below documents historical performance metrics evaluated on held-out test splits.

| Model Checkpoint | Evaluation Benchmark Split | Precision | Recall | mAP@50 | mAP@50-95 | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **M1.13 (Frozen)** | **M1.8 Held-Out** | **0.8380** | **0.6120** | **0.6540** | **0.4870** | High precision, reliable bounding boxes on core civic defects |
| **M1.13 (Frozen)** | **M1.11 Held-Out** | **0.6500** | **0.5700** | **0.5680** | **0.4230** | Dual held-out cross-validation set with higher background complexity |

> [!IMPORTANT]
> **Scientific Interpretation Disclaimer**:
> These numbers represent historical evaluated baselines obtained under controlled dataset conditions on specific benchmark splits. They MUST NOT be re-interpreted as universal performance guarantees across arbitrary municipal environments, extreme weather events, nighttime conditions, or low-resolution camera sensors.

---

## 3. Experiment Lineage & Failure/Recovery Methodology

The evolution from M1.8 through M1.11 to M1.13 represents a critical engineering lesson in data hygiene and validation rigor:

```
[M1.8 Initial Baseline]
  - 13 civic classes
  - Solid initial test metrics
       │
       ▼
[M1.11 Degraded Experiment]
  - Aggressive inclusion of noisy, uncurated data
  - Metric drop: Precision and mAP degraded
  - Diagnosis: Label noise, ambiguous boundaries, domain shift
       │
       ▼
[Root-Cause Diagnosis & Curation Protocol]
  - Elimination of ambiguous multi-label conflicts
  - Verification of all 605 samples
  - Re-balancing of class representation
       │
       ▼
[M1.13 Correction & Dual Held-Out Evaluation]
  - Precision restored to 0.8380 on M1.8 held-out
  - Solid performance (0.6500 P / 0.5680 mAP50) on M1.11 held-out
  - Locked as permanent CVKI v1 baseline
```

### Diagnosis of the M1.11 Degradation:
1. **Label Inconsistency**: Heuristic labeling of wet roads as "water_leakage" and general ground textures as "garbage" introduced high false-positive rates.
2. **Bounding Box Jitter**: Unrefined bounding boxes weakened IoU overlap metrics.
3. **Corrective Action**: Enacted strict curation criteria, pruning corrupt and low-information samples to establish the clean 605-file `dataset_m1_13`.

---

## 4. Environment & Execution Baseline

- **Training Framework**: Ultralytics YOLOv8 (PyTorch 2.x).
- **Execution Target**: Python 3.13+ on Windows / Linux x86_64.
- **Hardware Architecture**: Evaluated on single NVIDIA GPU (CUDA 12) with CPU fallback support for edge/local test environments.
- **Standardized Inference**: Wrapped via `CVModelInterface` (`ai/computer_vision/standardized_interface.py`) ensuring unified JSON output schema regardless of underlying backend.

---

## 5. Architectural Distinction: Historical vs Frozen vs Future

1. **Historical Experiments**: M1.1 through M1.12 exploratory runs and intermediate checkpoints. Preserved for lineage and analytical audit.
2. **Current Frozen Baseline**: M1.13 weights and dataset. Non-negotiable invariant for CVKI v1 product release. No modifications permitted.
3. **Future Research (Post-M12)**: Separate, versioned pipelines (e.g. CVKI Research v2) utilizing the `CVModelInterface` abstraction without mutating or compromising the v1 baseline.
