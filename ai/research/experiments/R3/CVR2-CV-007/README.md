# CVR2-CV-007: Photometric Robustness Evaluation

- **Operating Confidence Threshold:** `0.1` (Frozen from validation calibration)
- **Clean Test Baseline:** Precision=`0.7895`, Recall=`1.0`, F1=`0.8824`
- **Corruptions Evaluated:** 8 types across 3 severities (LOW, MEDIUM, HIGH)
- **Key Findings:** Gaussian blur and sensor noise cause the highest recall degradation; mild brightness variations are well-tolerated.
