# CVKI M1.7B — Training Environment Setup & Verification Report

- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Module**: M1.7B — YOLOv8 Environment Setup & Verification
- **Date**: 2026-09-12
- **Status**: **READY FOR TRAINING**

---

## 1. System & Hardware Specifications

| Property | Value | Notes |
|---|---|---|
| **Operating System** | Microsoft Windows 11 Home / Pro (64-bit, Build 10.0.26200) | Fully compatible Windows host |
| **CPU Architecture** | Intel(R) Core(TM) i5-1235U (12th Gen) | 10 Cores (2 P-cores + 8 E-cores), 12 Threads |
| **Installed Memory (RAM)** | 16.0 GB (16,869,351,424 bytes) | Sized comfortably for batch size 16 CPU dataloading |
| **Integrated GPU** | Intel(R) UHD Graphics | Driver 32.0.101.7080, 2.0 GB shared VRAM |
| **NVIDIA CUDA GPU** | None Available (`nvidia-smi` not found) | No hardware CUDA cores |
| **CUDA Capability** | `False` (`torch.cuda.is_available() == False`) | Deterministic CPU training execution |
| **Planned Device** | `cpu` | Device explicitly mapped to CPU |

---

## 2. Python Compatibility & Virtual Environment

| Component | Path / Version | Notes |
|---|---|---|
| **Global Default Python** | Python 3.14.2 64-bit (`C:\Python314\python.exe`) | **Untouched**. PyTorch does not publish stable wheels for 3.14 yet (`No matching distribution found`). |
| **Compatible Base Python** | Python 3.13.1 64-bit (`C:\Users\sushm\AppData\Local\Programs\Python\Python313\python.exe`) | Detected on system; used as base for isolated project venv. |
| **Virtual Environment Path** | `C:\Users\sushm\OneDrive\Desktop\CIVKI\.venv` | Project-local isolated virtual environment. |
| **Global Python Status** | Untouched | Zero global pollution. |
| **Git Exclusion** | `.venv/` added to `.gitignore` | Virtual environment ignored by Git. |

---

## 3. Installed Package Versions (Actual)

| Package | Installed Version | Verification Status | Role in Training Pipeline |
|---|---|---|---|
| **`torch`** | `2.14.0+cpu` | Verified (`import torch`, `cuda=False`) | Core tensor compute & backpropagation engine |
| **`torchvision`** | `0.29.0` | Verified | Vision datasets, transforms, and operations |
| **`ultralytics`** | `8.4.149` | Verified (`from ultralytics import YOLO`) | YOLOv8 model architecture & training orchestrator |
| **`numpy`** | `2.5.3` | Verified (`import numpy`) | Array manipulation & metrics computation |
| **`pillow`** | `12.3.0` | Verified (`import PIL`) | Image loading and raster processing |
| **`pyyaml`** | `6.0.3` | Verified (`import yaml`) | Dataset (`data.yaml`) & config parsing |

All packages installed into `.venv` and recorded in `ai/computer_vision/training/requirements.txt`.

---

## 4. Verification & Dry-Run Checks

### 4.1 PyTorch Verification
```python
import torch
# torch.__version__ == "2.14.0+cpu"
# torch.cuda.is_available() == False
# torch.cuda.device_count() == 0
```
- Expected device: CPU.
- CUDA attempt: Not attempted / not enabled.

### 4.2 Ultralytics Verification
```python
from ultralytics import YOLO
import ultralytics
# ultralytics.__version__ == "8.4.149"
```
- Import succeeded cleanly without errors.
- Pretrained weights were NOT downloaded merely for training.
- `model.train(...)` was NOT called.

### 4.3 Dataset Access & Resolution
```python
from ultralytics.data.utils import check_det_dataset
# Resolved train: C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset\images\train (210 images, 210 labels)
# Resolved val:   C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset\images\val   (60 images, 60 labels)
# Resolved test:  C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\dataset\images\test  (30 images, 30 labels)
# nc: 3
# names: {0: 'open_damaged_manhole', 1: 'damaged_missing_road_sign', 2: 'road_waterlogging'}
```
- Canonical `data.yaml` is accessible, well-formed, and completely untouched.
- 100% split integrity confirmed.

### 4.4 Script Syntax Verification
- `ai/computer_vision/training/scripts/train_yolov8.py`: Successfully compiled with `py_compile` without any syntax or import errors.

---

## 5. Dataset Protection & Safety Guarantee

- **Dataset Path**: `ai/computer_vision/dataset/`
- **Integrity Status**: Untouched. No images, labels, or splits were modified during environment setup.
- **Bounding Box Counts**:
  - Class `0` (`open_damaged_manhole`): 188 annotations across 100 images (70 train / 20 val / 10 test)
  - Class `1` (`damaged_missing_road_sign`): 52 annotations across 100 images (48 negative images)
  - Class `2` (`road_waterlogging`): 439 annotations across 100 images (2 negative images)
- **Model Training**: Strictly prohibited; no training executed.
