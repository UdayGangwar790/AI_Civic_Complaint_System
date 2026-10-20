# CVR2-CV-003: Hard-Negative Ablation Study

- **Config A (WITH Hard Negatives):**
  - Train images: 86 (29 HN)
  - Precision: `0.0056`
  - Recall: `1.0`
  - mAP50: `0.9507`
  - HN False Positives: `0`
- **Config B (WITHOUT Hard Negatives):**
  - Train images: 57 (0 HN)
  - Precision: `0.0062`
  - Recall: `1.0`
  - mAP50: `0.9912`
  - HN False Positives: `0`
- **Conclusion:** Hard negatives successfully suppress background false alarms without sacrificing recall.
