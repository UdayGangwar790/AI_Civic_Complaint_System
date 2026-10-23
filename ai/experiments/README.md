# CVKI Research & Experiment Registry

This directory contains the experiment registry and tracking metadata for CVKI Computer Vision and NLP model iterations.

## Frozen Baseline: M1.13
- **Model Architecture**: YOLOv8n (Ultralytics)
- **Weights File**: `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`
- **SHA-256**: `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3`
- **Dataset**: `ai/computer_vision/dataset_m1_13` (Exactly 605 files)
- **Status**: FROZEN_PRODUCTION_BASELINE

## Historical Evaluation Benchmarks
Historical evaluation results on held-out test splits:

| Evaluation Split | Precision | Recall | mAP@50 | mAP@50-95 |
| :--- | :--- | :--- | :--- | :--- |
| **M1.8 Held-Out** | 0.8380 | 0.6120 | 0.6540 | 0.4870 |
| **M1.11 Held-Out** | 0.6500 | 0.5700 | 0.5680 | 0.4230 |

> **Important**: These metrics represent historical local evaluation baselines under specific dataset conditions. They are **not** universal guarantees of real-world accuracy across arbitrary municipal environments or extreme lighting/weather variations.

## Experiment Lineage & Methodology
1. **M1.8**: Established initial baseline for 13 civic categories.
2. **M1.11**: An experimental dataset expansion resulted in metric degradation due to label noise and background distribution shifts.
3. **M1.13 Recovery**: Strict data hygiene, deduplication, and bounding box quality auditing recovered model performance, validated across dual held-out test sets.

For complete documentation, see [`docs/m12_reproducibility.md`](../../docs/m12_reproducibility.md).
