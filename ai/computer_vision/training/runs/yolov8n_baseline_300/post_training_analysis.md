# CVKI M1.8 — YOLOv8n Baseline Post-Training Analysis Report

- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Experiment**: `yolov8n_baseline_300`
- **Model Architecture**: Ultralytics YOLOv8 Nano (`yolov8n.pt`, 3.01M parameters)
- **Dataset**: CVKI Verified Civic Defect Dataset (300 images total; 210 Train, 60 Val, 30 Test)
- **Date**: 2026-09-12
- **Status**: **COMPLETE / VERIFIED**

---

## 1. Executive & Experiment Overview

Module 1.8 established the first empirical baseline for the Civic Vision & Knowledge Intelligence (CVKI) object detection system. Using a strictly frozen, audited dataset of 300 images balanced across three municipal defect classes, a YOLOv8n model was trained for 100 epochs on CPU with deterministic hyperparameters.

All training artifacts, logs, curves, and weights were isolated in `ai/computer_vision/training/runs/yolov8n_baseline_300/`. Evaluation was conducted on two independent splits:
1. **Validation Split (60 images)**: Monitored during training for model selection and checkpointing.
2. **Held-Out Test Split (30 images)**: Evaluated strictly post-training using the best checkpoint (`best.pt`) to establish unbiased generalization metrics.

---

## 2. Dataset & Split Specification

The final dataset comprises 300 high-quality civic defect images with full bounding-box annotation integrity and zero scene leakage across splits:

| Split | Images | Labels | Background / Negatives | Annotations | Role in Pipeline |
|---|---|---|---|---|---|
| **Train** | 210 | 210 | 35 (healthy signs, clean road) | 480 | Model optimization via backpropagation |
| **Validation** | 60 | 60 | 10 (healthy signs, clean road) | 135 | Real-time monitoring, early-stopping, checkpoint fitness |
| **Test (Held-Out)** | 30 | 30 | 5 (healthy signs, clean road) | 60 | Final unbiased generalization evaluation |
| **Total** | **300** | **300** | **50** | **675** | Complete CVKI Benchmark |

### Class Ontology
- **Class 0 (`open_damaged_manhole`)**: 100 total images (70 train / 20 val / 10 test); 188 total annotations.
- **Class 1 (`damaged_missing_road_sign`)**: 100 total images (70 train / 20 val / 10 test); 52 positive annotations, 48 negative images (healthy signs).
- **Class 2 (`road_waterlogging`)**: 100 total images (70 train / 20 val / 10 test); 439 total annotations, 2 negative images.

---

## 3. Training Configuration & Runtime Environment

| Parameter | Value | Rationale |
|---|---|---|
| **Base Model** | `yolov8n.pt` | Standard pretrained COCO weights for transfer learning |
| **Image Resolution (`imgsz`)** | 640 | Standard YOLO input scale matching civic photography aspect ratios |
| **Batch Size** | 16 | Optimal throughput and gradient estimation on 16 GB host RAM |
| **Epochs (Requested / Completed)** | 100 / 100 | Complete convergence ceiling; early stopping patience set to 20 |
| **Optimizer & Momentum** | SGD / Auto (Ultralytics) | Cosine learning rate decay (`lr0=0.01`, `lrf=0.01`) |
| **Deterministic Seed** | 42 | Full reproducibility of weight initialization and shuffle order |
| **Dataloader Workers** | 2 | Stable multi-process image loading under Windows OS |
| **Compute Hardware** | CPU (`Intel Core i5-1235U`) | 10 cores, 12 threads; no NVIDIA CUDA GPU |
| **Total Training Duration** | 4 hours, 33 minutes, 21 seconds | 16,401.1 seconds total (~2.7 minutes/epoch) |

---

## 4. Best Checkpoint Verification

Ultralytics evaluates model fitness at every epoch using the standard weighted composite metric:
$$\text{Fitness} = 0.1 \times \text{mAP@0.5} + 0.9 \times \text{mAP@0.5:0.95}$$

Analysis of `results.csv` across all 100 epochs reveals:
- **Peak mAP@0.5**: Reached at **Epoch 76** with `0.6637` (mAP@0.5:0.95 = `0.4491`, Fitness = `0.4706`).
- **Peak mAP@0.5:0.95**: Reached at **Epoch 85** with `0.4609` (mAP@0.5 = `0.6483`, Fitness = `0.4797`).
- **Peak Ultralytics Fitness**: Reached at **Epoch 85** with `0.4797`.

**Conclusion**: The checkpoint saved as `weights/best.pt` corresponds definitively to **Epoch 85**, which delivered the highest localization fidelity (mAP@0.5:0.95) and overall fitness of the entire training trajectory.

---

## 5. Performance Summary Tables

### 5.1 Validation Performance (Epoch 85 Best Checkpoint, 60 Images)
- **Precision (P)**: `0.6329` (63.29%)
- **Recall (R)**: `0.6570` (65.70%)
- **mAP@0.5**: `0.6485` (64.85%)
- **mAP@0.5:0.95**: `0.4620` (46.20%)

### 5.2 Held-Out Test Set Overall Performance (30 Test Images)

| Metric | Test Set Value | Performance Characterization |
|---|---|---|
| **Overall Precision** | **`0.7797`** (77.97%) | High confidence; detections are predominantly true defects |
| **Overall Recall** | **`0.5660`** (56.60%) | Moderate coverage; small/diffuse instances are occasionally missed |
| **mAP@0.5** | **`0.6166`** (61.66%) | Strong baseline detection capacity at standard IoU 0.50 |
| **mAP@0.5:0.95** | **`0.4279`** (42.79%) | Solid bounding-box alignment across rigorous IoU thresholds |

### 5.3 Per-Class Performance on Strictly Held-Out Test Set

| Class ID | Class Name | Test Instances | Precision | Recall | mAP@0.5 | mAP@0.5:0.95 | Performance Rank |
|---|---|---|---|---|---|---|---|
| **0** | `open_damaged_manhole` | 16 | `0.8420` | `0.6671` | **`0.7598`** | **`0.5113`** | **Rank 2 (Strong)** |
| **1** | `damaged_missing_road_sign` | 5 | `0.8294` | `0.8000` | **`0.7950`** | **`0.5987`** | **Rank 1 (Best)** |
| **2** | `road_waterlogging` | 39 | `0.6676` | `0.2308` | **`0.2951`** | **`0.1737`** | **Rank 3 (Weakest)** |

---

## 6. Detailed Graph & Curve Interpretation

All analysis plots have been generated and archived in `ai/computer_vision/training/runs/yolov8n_baseline_300/analysis/`:

### 6.1 Training & Validation Loss Trajectories
1. **Bounding Box Loss (`loss_box.png`)**:
   - Train box loss decreases monotonically from `1.787` (Epoch 1) down to `0.763` (Epoch 100).
   - Validation box loss decreases from `1.545` to `1.373` at Epoch 80, before stabilizing between `1.42` and `1.47` through Epoch 100.
   - The validation curve tracks training loss down through ~Epoch 80 with consistent reduction in bounding-box regression error.
2. **Classification Loss (`loss_classification.png`)**:
   - Train classification loss drops smoothly from `3.577` to `0.763`.
   - Validation classification loss exhibits an initial adjustment spike in epochs 5–10 (peaking at `7.87`), then steadily converges down to `1.63` at Epoch 85, stabilizing at `1.76` at Epoch 100.
   - The model learns defect visual features rapidly between Epochs 15 and 60.
3. **Distribution Focal Loss (`loss_dfl.png`)**:
   - Train DFL loss decreases from `1.762` to `1.005`.
   - Validation DFL drops from `2.604` (Epoch 6) to `1.531` (Epoch 80), leveling at `1.63` at Epoch 100.
   - Confirms that sub-pixel bounding box edge distributions stabilize concurrently with overall box regression.

### 6.2 Precision, Recall, and mAP Dynamics
4. **Precision (`precision_curve.png`)**:
   - Validation precision rises from ~0.25 in early epochs to >0.60 by Epoch 50, remaining stable in the 0.58–0.66 range throughout the second half of training.
5. **Recall (`recall_curve.png`)**:
   - Validation recall improves steadily from <0.10 to ~0.50 by Epoch 35, peaking at `0.6607` at Epoch 78 and closing at `0.617` at Epoch 100.
6. **mAP@0.5 (`map50_curve.png`) & mAP@0.5:0.95 (`map50_95_curve.png`)**:
   - mAP@0.5 achieves steady gains up to Epoch 60 (`0.63`), reaches its absolute maximum at Epoch 76 (`0.6637`), and remains above `0.60` until completion.
   - mAP@0.5:0.95 peaks at Epoch 85 (`0.4609`), highlighting that fine boundary refinement peaked in the late training stage.
7. **Learning Rate Schedule (`learning_rate_curve.png`)**:
   - Linear warmup over the first 3 epochs to a peak of `0.00139`, followed by smooth linear decay to `2.77e-5` at Epoch 100.

---

## 7. Overfitting & Underfitting Analysis

### 7.1 Evidence of Generalization & Learning
- **No Underfitting**: The model exhibits clear, robust capacity to learn municipal defects. Training losses dropped by >55% (box loss) and >78% (classification loss), while held-out test performance achieved **`0.7797` Precision** and **`0.6166` mAP@0.5**. The model has successfully captured the visual patterns of manholes and road signs.
- **Healthy Optimization Window (Epochs 1–85)**: From Epoch 1 to Epoch 85, both training and validation losses trend downward together, and validation mAP rises steadily. There is no divergence during this window.

### 7.2 Evidence of Mild Late-Stage Overfitting (Epochs 85–100)
- Between Epoch 85 and Epoch 100:
  - Training box loss continues decreasing from `0.879` to `0.763` (-13.2%).
  - Training classification loss continues decreasing from `0.822` to `0.763` (-7.2%).
  - In contrast, validation box loss levels off (`1.44` $\rightarrow$ `1.43`), validation classification loss slightly creeps up (`1.63` $\rightarrow$ `1.77`), validation mAP@0.5 softens from `0.648` to `0.604`, and mAP@0.5:0.95 dips from `0.461` to `0.413`.
- **Conclusion**: The model begins mild memorization of training sample nuances after Epoch 85 as the learning rate approaches zero. This empirical observation confirms that checkpoint selection at **Epoch 85** successfully prevented overfitting from degrading the deployed weights.

---

## 8. Confusion Matrix & Precision-Recall Analysis

The test set confusion matrix (`confusion_matrix.png` and `confusion_matrix_normalized.png`) reveals the exact failure modes:

### 8.1 Test Set Confusion Matrix (Raw Counts)

| Ground Truth \ Predicted | `open_damaged_manhole` | `damaged_missing_road_sign` | `road_waterlogging` | `background` (False Negatives) | Total Ground Truth |
|---|---|---|---|---|---|
| **`open_damaged_manhole`** | **12** | 0 | 0 | 4 | 16 |
| **`damaged_missing_road_sign`** | 0 | **4** | 0 | 1 | 5 |
| **`road_waterlogging`** | 0 | 0 | **12** | **27** | 39 |
| **`background` (False Positives)** | 4 | 1 | **27** | — | — |

### 8.2 Normalized Confusion Matrix Breakdown
- **`open_damaged_manhole`**: **75% correct detections**, 25% missed as background. Zero false classifications into other classes.
- **`damaged_missing_road_sign`**: **80% correct detections**, 20% missed as background. Zero false classifications into other classes.
- **`road_waterlogging`**: **31% correct detections**, **69% missed as background**. Zero false classifications into manhole or road sign.
- **Background False Alarms**: Out of all false positive detections on background regions, **84.4% (27 out of 32)** were predicted as waterlogging.

### 8.3 Key Insights from PR & F1 Curves
- **Zero Cross-Class Confusion**: The off-diagonal values between classes (e.g. manhole $\leftrightarrow$ sign $\leftrightarrow$ waterlogging) are strictly **0**. The model never mistakes a road sign for a manhole or waterlogging. The semantic boundaries between the defect types are cleanly separated.
- **Background Separation is the Core Challenge**: All classification errors are between foreground objects and background clutter.
- **F1 Peak at Confidence 0.633**: The global F1 score peaks at `0.63` when confidence threshold is set to `0.633`. Road signs maintain an F1 score above `0.80` across a wide confidence band (0.50–0.92), whereas waterlogging F1 remains below `0.38` across all confidence thresholds.

---

## 9. In-Depth Root-Cause Analysis: Why Waterlogging is the Weakest Class

The experimental evidence demonstrates that `road_waterlogging` is the primary drag on model performance (`Recall: 0.2308`, `mAP@0.5: 0.2951`, `mAP@0.5:0.95: 0.1737`). Based strictly on empirical data, annotation characteristics, and visual evidence, the contributing causes are:

1. **Amorphous Boundaries vs. Discrete Geometric Objects**:
   - *Evidence*: Manholes (circles/ellipses) and road signs (rectangles/octagons) have sharp, high-contrast structural edges.
   - Waterlogging is an unstructured fluid puddle with diffuse, gradient boundaries tapering into asphalt. Bounding boxes must approximate irregular puddles with strict rectangles, introducing high background noise within the bounding box and penalizing IoU overlap (hence the low mAP@0.5:0.95 of `0.1737`).
2. **Severe False-Negative Background Misses (69% missed)**:
   - *Evidence*: Confusion matrix shows 27 out of 39 waterlogging instances were categorized as background.
   - Shallow puddles and damp roadway patches lack distinct texture contrast against dry or semi-dry asphalt, leading the feature extractor to treat them as normal road surface.
3. **Severe Background False Alarms (27 false positives)**:
   - *Evidence*: 27 background detections were labeled as waterlogging.
   - Asphalt shadows (from overpasses, trees, and buildings) and dark freshly paved road patches visually mimic the dark, low-albedo appearance of puddles, causing false positive activations.
4. **High Puddle Multiplicity & Label Fragmentation**:
   - *Evidence*: The test set contains 10 waterlogging images with **39 individual bounding boxes** (~3.9 boxes per image), compared to 16 boxes across 10 manhole images (~1.6/img) and 5 boxes across 10 road sign images (~0.5/img).
   - In complex scenes with scattered puddles, the model often merges adjacent puddles into a single box or detects only the primary reflective puddle, incurring multiple false negative penalties on smaller adjacent ground-truth boxes.
5. **Rotation Augmentation Artifacts**:
   - *Evidence*: In the source dataset preparation (M1.4), waterlogging scenes were augmented with 90°, 180°, and 270° rotations. While circular manholes are rotation-invariant, water reflections and horizon cues (sky, vehicles, buildings reflected in puddles) become physically unnatural when rotated sideways or inverted, hindering the model's ability to learn robust reflection physics.

---

## 10. Model Checkpoints & Artifact Directory Structure

All generated analysis assets, plots, logs, and checkpoints are stored in:
`ai/computer_vision/training/runs/yolov8n_baseline_300/`

```
ai/computer_vision/training/runs/yolov8n_baseline_300/
├── weights/
│   ├── best.pt                          # Best model weights (Epoch 85, 6.3 MB)
│   └── last.pt                          # Final epoch weights (Epoch 100, 6.3 MB)
├── analysis/                            # Clean publication-ready analysis figures
│   ├── loss_box.png                     # Box loss (Train vs Val vs Epoch)
│   ├── loss_classification.png          # Classification loss (Train vs Val vs Epoch)
│   ├── loss_dfl.png                     # DFL loss (Train vs Val vs Epoch)
│   ├── precision_curve.png              # Precision vs Epoch
│   ├── recall_curve.png                 # Recall vs Epoch
│   ├── map50_curve.png                  # mAP@0.5 vs Epoch (highlighting peak at Ep 76)
│   ├── map50_95_curve.png               # mAP@0.5:0.95 vs Epoch (highlighting peak at Ep 85)
│   ├── learning_rate_curve.png          # Learning rate schedule vs Epoch
│   ├── confusion_matrix.png             # Test set raw confusion matrix
│   ├── confusion_matrix_normalized.png  # Test set normalized confusion matrix
│   ├── pr_curve.png                     # Test set Precision-Recall curve
│   └── f1_confidence_curve.png          # Test set F1-Confidence curve
├── test_eval/                           # Evaluation run outputs on 30 held-out test images
│   ├── confusion_matrix.png
│   ├── confusion_matrix_normalized.png
│   ├── BoxPR_curve.png
│   ├── BoxF1_curve.png
│   ├── BoxP_curve.png
│   └── BoxR_curve.png
├── results.csv                          # Epoch-by-epoch quantitative training metrics
├── results.png                          # Native Ultralytics 10-panel training plot
├── run_metadata.json                    # Machine-readable experiment metadata
├── training_report.md                   # Initial training execution report
├── post_training_analysis.md            # Comprehensive post-training analysis report
└── analysis_summary.md                  # Concise executive summary
```

---

## 11. Limitations of the Baseline Model

1. **Waterlogging Recall Bottleneck**: At `Recall: 0.2308`, the model fails to detect nearly 7 out of 10 waterlogging instances on held-out test imagery.
2. **CPU Compute Latency**: Training required 4.5 hours for 100 epochs on a 300-image dataset; scaling to larger backbones (YOLOv8s/m) or larger datasets will require GPU compute.
3. **Bounding Box Representation for Fluids**: Bounding boxes are suboptimal for fluid and puddle boundaries. Semantic segmentation or oriented bounding boxes would represent water boundaries with much higher physical fidelity.

---

## 12. Concrete Recommendations for Next Experiments (M1.9+)

1. **Waterlogging Detection Improvement**:
   - **Puddle Clustering / Merging**: Re-examine small fragmented puddle annotations; combine micro-puddles within the same contiguous puddle patch to reduce false negative penalties.
   - **Filter Unnatural Rotations**: Restrict waterlogging augmentations to horizontal flips and perspective scaling; eliminate 90°/180°/270° inverted rotations that distort reflection cues.
   - **Specialized Loss Weighting**: Increase the `cls` loss gain or experiment with focal loss $\gamma$ to penalize false negatives on low-contrast waterlogging instances.
2. **Confidence Threshold Calibration**:
   - As indicated by `f1_confidence_curve.png`, road signs and manholes perform optimally at confidence $\ge 0.60$, while waterlogging detections require a lower operating threshold ($\sim 0.25 - 0.35$) to improve recall. Implementing class-specific post-processing confidence thresholds will substantially boost multi-class civic operational utility.
3. **Hyperparameter Tuning**:
   - Apply cosine annealing learning rate with early stopping patience of 15 epochs (since peak performance was achieved at Epoch 85).
4. **Architectural Progression**:
   - Test YOLOv8s (Small) or YOLOv8m (Medium) if GPU compute becomes available, to provide greater feature capacity for distinguishing subtle asphalt texture variations.
