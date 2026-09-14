# CVKI M1.7 — YOLOv8 Training Preparation Report

- **Date**: 2026-09-12
- **Module**: M1.7 — YOLOv8 Training Preparation (Strictly Non-Executable / Read-Only Preparation)
- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Final Status**: **M1.7 STATUS: READY WITH REQUIREMENTS**

---

## 1. Dataset Verification

The final dataset at `ai/computer_vision/dataset/` was verified and confirmed ready for training ingestion:
- **Canonical `data.yaml` Path**: `C:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/dataset/data.yaml`
- **Total Images**: 300
- **Total Labels**: 300
- **Split Distribution**:
  - `train`: 210 images (70 Manhole, 70 Road Sign, 70 Waterlogging)
  - `val`: 60 images (20 Manhole, 20 Road Sign, 20 Waterlogging)
  - `test`: 30 images (10 Manhole, 10 Road Sign, 10 Waterlogging)
- **Classes**:
  - `0`: `open_damaged_manhole` (100 images, 188 boxes)
  - `1`: `damaged_missing_road_sign` (100 images, 52 boxes, 48 negatives)
  - `2`: `road_waterlogging` (100 images, 439 boxes, 2 negatives)
- **Dataset Read-Only Status**: Fully certified and locked; zero modifications permitted during training preparation.

---

## 2. Environment & System Architecture

- **Operating System**: Windows 11 Home / Pro (Build 10.0.26200-SP0, 64-bit)
- **Platform Architecture**: AMD64 / Intel64
- **Working Directory**: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision`

---

## 3. Hardware Inspection

- **CPU**: 12th Gen Intel(R) Core(TM) i5-1235U
  - Physical Cores: 10 (2 Performance cores, 8 Efficient cores)
  - Logical Processors: 12 threads
- **RAM**: 16.0 GB (16,869,351,424 bytes physical memory)
  - Sufficient headroom for memory-mapped dataset loading and batch sizes up to 32.
- **GPU**: Intel(R) UHD Graphics (Integrated Graphics)
  - Driver Version: 32.0.101.7080
  - Dedicated / Shared VRAM: ~2.0 GB shared memory

---

## 4. Python Runtime

- **Version**: Python 3.14.2 (tags/v3.14.2, Dec 5 2025, 64-bit)
- **Executable Location**: `C:\Python314\python.exe`
- **Pip Version**: Pip 25.3
- **Virtual Environment**: None (system installation)

---

## 5. PyTorch Status

- **Installed**: **No**
- **Torch CUDA Status**: Unavailable (PyTorch not currently present in Python environment)
- **Required Action**: PyTorch must be installed before running M1.8 training.

---

## 6. Ultralytics / YOLO Status

- **Installed**: **No**
- **Required Action**: `ultralytics` package must be installed prior to running training scripts.

---

## 7. CUDA Status & Device Strategy

- **NVIDIA Hardware**: None detected (`nvidia-smi` not found; no discrete NVIDIA GPU).
- **CUDA Support**: Not available on this machine.
- **Planned Device Strategy**:
  ```
  planned device = CPU
  ```
  Ultralytics will be directed to train on the 10-core Intel Core i5 CPU using `device='cpu'`.

---

## 8. Proposed YOLOv8 Model

- **Model Specification**: `yolov8n.pt` (YOLOv8 Nano)
- **Parameter Count**: ~3.2 Million parameters
- **Rationale**:
  1. **Dataset Sizing**: With 300 total images (210 training), a nano architecture prevents rapid memorization and overfitting.
  2. **CPU Execution Feasibility**: Nano trains significantly faster per epoch on CPU compared to Small (11.2M), Medium (25.9M), or Large (43.7M).
  3. **Standard Baseline**: Serves as the primary reference baseline for all civic vision tasks in CVKI.
- **Weights Download**: **Not downloaded yet** (will be fetched automatically upon first authorized training run in M1.8).

---

## 9. Proposed Baseline Hyperparameters

Configured in `ai/computer_vision/training/configs/yolov8n_baseline.yaml`:

| Hyperparameter | Value | Description |
|---|---|---|
| `model` | `yolov8n.pt` | Pretrained base architecture |
| `data` | `dataset/data.yaml` | Absolute path to CVKI dataset config |
| `epochs` | `100` | Maximum transfer learning iterations |
| `imgsz` | `640` | Scaled input resolution |
| `batch` | `16` | CPU memory-efficient batch size |
| `patience` | `20` | Early stopping threshold |
| `seed` | `42` | Fixed seed for reproducible run |
| `deterministic` | `true` | Deterministic algorithmic selection |
| `device` | `cpu` | Explicit CPU execution |
| `workers` | `4` | Dataloader thread allocation |
| `plots` | `true` | Automated evaluation curves generation |

---

## 10. Training Directory Structure

```
ai/computer_vision/training/
├── configs/
│   └── yolov8n_baseline.yaml       --> Declarative training parameters
├── scripts/
│   └── train_yolov8.py             --> Fully parameterized, non-executed training runner
├── runs/
│   └── .gitkeep                    --> Isolated output directory for checkpoints and metrics
├── README.md                       --> Training execution and architectural guide
└── training_environment.md         --> System, hardware, and dependency audit record
```

---

## 11. Reproducibility Assurance

- All experiments use deterministic seed **`42`**.
- Dataset split remains fixed and audited by `dataset_manifest.json`.
- Training script preserves configuration YAML alongside outputs in `runs/`.

---

## 12. Expected Evaluation Metrics (M1.8)

When training is executed in M1.8, the following validation metrics will be collected and recorded:
- Overall Precision (P), Recall (R), mAP@0.5, and mAP@0.5:0.95
- Class-specific metrics:
  - `open_damaged_manhole`: AP50, AP50:95
  - `damaged_missing_road_sign`: AP50, AP50:95
  - `road_waterlogging`: AP50, AP50:95
- Training and validation loss curves (`box_loss`, `cls_loss`, `dfl_loss`)
- Normalized Confusion Matrix

---

## 13. Missing Requirements & Pre-Flight Checklist

Before M1.8 training can commence, the following package installations are required:
1. `pip install torch torchvision`
2. `pip install ultralytics`

*Note: In accordance with M1.7 instructions, no packages were installed and no model weights were downloaded.*

---

## 14. Training Readiness Conclusion

The project training scaffold, configuration files, device strategy, execution scripts, and output destinations are 100% prepared and structured. Training is ready to proceed immediately upon package installation approval in M1.8.

**FINAL STATUS: M1.7 STATUS: READY WITH REQUIREMENTS**
