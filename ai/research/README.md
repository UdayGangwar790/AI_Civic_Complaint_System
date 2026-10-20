# CVKI Research v2.x — Framework & Infrastructure

Welcome to the **CVKI Research v2.x** workspace. This directory hosts the independent research infrastructure, experiment registries, dataset catalogs, and evaluation harnesses for scientific research beyond the frozen CVKI v1 production baseline.

---

## 1. What is CVKI Research v2.x & Why It Is Separate

CVKI v1 (Milestone M12) is officially **complete, finalized, and frozen**. In production civic operations, stability, deterministic decision boundaries, and verifiable model hashes are paramount.

**CVKI Research v2.x** provides a decoupled, unconstrained scientific exploration environment where researchers can investigate advanced computer vision architectures, expanded datasets, multilingual models, and multimodal methods without risking or mutating the production codebase.

```
┌───────────────────────────────────────────────┐
│     CVKI v1.0.0 (FROZEN PRODUCTION BASELINE)  │
│  - Model: M1.13 YOLOv8n (SHA-256 locked)      │
│  - Dataset: dataset_m1_13 (605 files locked)  │
│  - API Contracts: /api/v1/* locked            │
└───────────────────────┬───────────────────────┘
                        │ SPI Interface
                        ▼
┌───────────────────────────────────────────────┐
│           CVKI Research v2.x                  │
│  - Experiment Registry & Hypotheses           │
│  - Dataset Registry (D0, D1, D2...)           │
│  - Research Model Registry (R2-*)             │
│  - Standardized Comparative Benchmarking      │
└───────────────────────────────────────────────┘
```

---

## 2. Frozen Production Reference (M1.13 & D0)

The production baseline is protected by cryptographic integrity checks:
- **Model Checkpoint**: `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`
- **SHA-256 Hash**: `602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3`
- **Dataset (D0)**: `ai/computer_vision/dataset_m1_13` (Exactly 605 files)
- **Status in Registry**: `FROZEN_PRODUCTION_BASELINE` / `FROZEN_REFERENCE`

To verify that the baseline has not been altered:
```bash
python ai/research/scripts/verify_baseline.py
```

---

## 3. Directory Layout

```
ai/research/
├── configs/       # Experiment configuration specifications (YAML/JSON)
├── experiments/   # Individual experiment dossiers (metrics, env, reports)
├── datasets/      # Research dataset manifests and split definitions
├── benchmarks/    # Benchmark evaluation scripts
├── reports/       # Analytical research findings and synthesis papers
├── scripts/       # CLI tools (verify_baseline.py, compare_runs.py)
├── registry/      # Persistent registries (datasets, models, experiments)
└── README.md      # This guide
```

---

## 4. Experiment Identity & Naming Conventions

Every experiment is assigned a permanent, non-reusable identifier:
$$\text{CVR2-}<\text{TRACK}>-<\text{NUMBER:03d}>$$
- `CVR2-CV-001`: Computer Vision Track
- `CVR2-NLP-001`: Natural Language Processing Track
- `CVR2-DATA-001`: Dataset Curation & Scaling Track
- `CVR2-SYS-001`: System Architecture & Latency Track
- `CVR2-E-001`: General / Exploratory Track

Experiment IDs are tracked in `ai/research/registry/experiment_registry.json`. **Silent reuse of experiment IDs is strictly prohibited.**

---

## 5. Dataset & Model Versioning

- **Datasets**: Versioned as `D0` (production baseline), `D1` (expansion), `D2`, etc. Each entry in `dataset_registry.json` contains image count, split definitions, class vocabulary, and a composite inventory SHA-256 manifest.
- **Models**: Versioned under distinct identifiers, e.g. `R2-YOLO-S-001`, `R2-DETR-001`. They inherit the standard `CVInferenceProvider` interface without modifying production code.

---

## 6. Ten Research Safety Rules (Non-Negotiable)

1. **Never modify production baseline**: Do not retrain M1.13, alter its weights, or touch `dataset_m1_13`.
2. **Never overwrite a research experiment**: Once finalized, an experiment dossier is immutable.
3. **Never reuse experiment IDs**: Every scientific inquiry must claim a fresh ID.
4. **Never change test data after evaluation**: Changes to test sets require a new dataset version.
5. **Never report validation performance as test performance**: Model selection happens on `val`; `test` is evaluated once.
6. **Never compare experiments across disparate test sets**: Always state the exact evaluation split.
7. **Never fabricate missing metadata**: Record unknown variables explicitly as `'unknown'`.
8. **Never claim statistical significance without formal testing**: Report exact p-values or confidence intervals.
9. **Never claim state-of-the-art without external benchmarks**: Compare against controlled reference baselines.
10. **Never claim production readiness from local experiments**: Local engineering metrics are not field guarantees.

---

## 7. How to Conduct an Experiment

### Step 1: Formulate Hypothesis & Config
Create a configuration file in `ai/research/configs/<exp_id>.yaml`:
```yaml
experiment_id: CVR2-CV-002
experiment_type: architectural_exploration
dataset:
  id: D0
  version: "1.0"
model:
  id: R2-YOLO-S-001
  architecture: YOLOv8s
hypothesis:
  question: Does scaling from YOLOv8n to YOLOv8s improve recall on small manhole defects?
  hypothesis: Additional capacity in YOLOv8s will improve recall by >= 0.05.
  independent_variable: model parameter scale (YOLOv8n vs YOLOv8s)
  dependent_variables: [recall, mAP50, latency]
  controls: [same dataset D0, same seed 42, same 640 input resolution]
  expected_outcome: Recall increases from 0.612 to >0.66.
```

### Step 2: Initialize Experiment Dossier
```python
from ai.research import ExperimentStorage, ExperimentIdentity, ExperimentConfig

config = ExperimentConfig.from_yaml("ai/research/configs/CVR2-CV-002.yaml")
identity = ExperimentIdentity(
    experiment_id="CVR2-CV-002",
    experiment_type="architectural_exploration",
    owner="Researcher Name",
    description="Evaluating YOLOv8s capacity scaling on civic defects",
    hypothesis=config.hypothesis.hypothesis,
    dataset_id="D0",
    dataset_version="1.0",
    model_id="R2-YOLO-S-001",
    model_version="1.0.0",
    config_id="CFG-CVR2-002",
)

storage = ExperimentStorage()
storage.initialize_experiment_dossier(identity, config)
```

### Step 3: Execute & Finalize
Evaluate your model, then finalize the dossier:
```python
from ai.research import EvaluationMetrics

metrics = EvaluationMetrics(
    precision=0.8520,
    recall=0.6740,
    mAP50=0.6920,
    mAP50_95=0.5120,
    inference_latency_ms=8.4,
    evaluated_on="test",
)

storage.finalize_experiment(
    experiment_id="CVR2-CV-002",
    metrics=metrics,
    actual_outcome="Recall increased from 0.612 to 0.674; latency increased by 3.2ms.",
    conclusion="Hypothesis confirmed: capacity scaling significantly boosts recall on occluded defects.",
    weight_path="weights/r2_yolov8s_001.pt",
    weight_sha256="abcdef...",
)
```

### Step 4: Compare Experiments
```bash
python ai/research/scripts/compare_runs.py CVR2-CV-001 CVR2-CV-002
```

### Step 5: Archiving
Transition status to `ARCHIVED` via the status state machine when a research line reaches completion.
