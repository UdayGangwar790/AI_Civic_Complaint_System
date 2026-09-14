# CVKI M1.8 — Baseline Training Analysis Summary

- **Run Name**: `yolov8n_baseline_300`
- **Architecture**: YOLOv8n (3.01M parameters)
- **Dataset**: CVKI 300 Images (210 Train / 60 Val / 30 Test)
- **Status**: **COMPLETE / VERIFIED**

---

### Key Summary Points

| Category | Finding / Metric | Notes |
|---|---|---|
| **Best Epoch** | **Epoch 85** | Reached highest fitness (`0.4797`) and peak mAP@0.5:0.95 (`0.4609`) |
| **Overall Test Precision** | **`0.7797`** (77.97%) | High detection precision; low false discovery rate |
| **Overall Test Recall** | **`0.5660`** (56.60%) | Constrained primarily by waterlogging false negatives |
| **Overall Test mAP@0.5** | **`0.6166`** (61.66%) | Strong baseline civic defect recognition |
| **Overall Test mAP@0.5:0.95** | **`0.4279`** (42.79%) | Solid bounding-box alignment across rigorous IoU thresholds |
| **Best Performing Class** | **`damaged_missing_road_sign`** | **Precision: `0.8294` \| Recall: `0.8000` \| mAP50: `0.7950` \| mAP50-95: `0.5987`** |
| **Runner-Up Class** | **`open_damaged_manhole`** | **Precision: `0.8420` \| Recall: `0.6671` \| mAP50: `0.7598` \| mAP50-95: `0.5113`** |
| **Weakest Class** | **`road_waterlogging`** | **Precision: `0.6676` \| Recall: `0.2308` \| mAP50: `0.2951` \| mAP50-95: `0.1737`** |
| **Main Limitation** | **Waterlogging Background Confusion** | 69% of waterlogging instances missed as background; 27 background false alarms |
| **Recommended Next Improvement** | **Class-Specific Thresholds & Augmentation Refinement** | Lower operating confidence for waterlogging (0.25–0.35); eliminate inverted rotation augmentations |

---

### Artifact Reference
- **Analysis Directory**: [`analysis/`](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/training/runs/yolov8n_baseline_300/analysis)
- **Full Report**: [`post_training_analysis.md`](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/training/runs/yolov8n_baseline_300/post_training_analysis.md)
- **Best Weights**: [`weights/best.pt`](file:///c:/Users/sushm/OneDrive/Desktop/CIVKI/ai/computer_vision/training/runs/yolov8n_baseline_300/weights/best.pt)
