# CVKI M12.7: Developer & Contributor Guide

This document provides developer guidelines, code organization standards, architectural conventions, and testing instructions for engineering contributors to CVKI.

---

## 1. Codebase Organization

```
CVKI/
├── ai/
│   ├── computer_vision/
│   │   ├── dataset_m1_13/           # Frozen M1.13 dataset (605 files)
│   │   ├── standardized_interface.py # Standardized inference wrapper
│   │   └── training/runs/yolov8n_m1_13/weights/best.pt # Frozen baseline weights
│   └── experiments/
│       ├── registry.json             # AI experiment registry & lineage
│       └── README.md
├── backend/
│   ├── app/
│   │   ├── api/                      # FastAPI routers (/auth, /complaint, /decision_support, etc.)
│   │   ├── core/                     # Security, config, logging middleware
│   │   ├── models/                   # Enums, roles, and database models
│   │   ├── schemas/                  # Pydantic v2 contract schemas
│   │   └── services/                 # Core domain services (cv, authority, multimodal, ds, prov, kg)
│   └── tests/                        # Comprehensive test & benchmark suites
├── frontend/
│   ├── src/                          # React / TypeScript UI components
│   └── package.json
└── docs/                             # Architecture, audit, and release specifications
```

---

## 2. Core Service Provider Interfaces (SPI)

### 2.1 Computer Vision Provider (`app/services/cv/base_provider.py`)
All CV models must implement `CVInferenceProvider`:
- Must return `StandardDetectionResult` with bounding boxes in normalized `[0, 1]` coordinates.
- **Invariant**: Zero framework tensor leakage (e.g. PyTorch `torch.Tensor` or Ultralytics `Boxes` must never escape the adapter layer into domain services).
- Must declare immutable `ModelDescriptor` with model ID, SHA-256 hash, and lifecycle status.

### 2.2 Government Integration Adapter (`app/services/government_adapter.py`)
All portal integrations (CPGRAMS, state portals) implement `GovernmentIntegrationAdapter`:
- Must implement idempotent dispatch via `idempotency_key`.
- Must handle network timeouts gracefully by returning `IntegrationState.UNAVAILABLE` or `DISABLED`.
- **Invariant**: Never fabricate external success; do not automatically update local physical verification state based solely on remote webhook payloads.

---

## 3. Epistemic Safety Invariants for Developers

When contributing to decision-support, prioritization, or triage engines:

1. **Tag All Claims**:
   - Statistical CV outputs must be tagged `EpistemicState.MODEL_OBSERVATION`.
   - Citizen text must be tagged `EpistemicState.USER_REPORTED`.
   - Algorithmic outputs must be tagged `EpistemicState.SYSTEM_DERIVED`.
   - Only formal inspector sign-offs may be tagged `EpistemicState.VERIFIED`.
2. **Mandatory Human Review**:
   - `DecisionSupportResult.human_review_required` must unconditionally evaluate to `True`.
3. **No Autonomous Lifecycle Commits**:
   - Do not write code that transitions a complaint case to `RESOLVED` or `CLOSED` automatically inside recommendation or prediction services.

---

## 4. Running Tests & Benchmarks

### 4.1 Running the Full Test Suite
```bash
# Run all backend tests with verbosity
pytest backend/tests -v

# Run targeted subsystem suites
pytest backend/tests/test_m12_product_e2e.py -v
pytest backend/tests/test_m108_security_hardening.py -v
pytest backend/tests/test_m108_epistemic_safety.py -v
```

### 4.2 Running Local Engineering Benchmarks
```bash
python backend/tests/benchmark_m12_final.py
```
Outputs latency distributions (Mean, Median, P95, P99, Max) and concurrency metrics across 10 core subsystems.

---

## 5. Coding Standards & Lints
- **Python**: PEP 8 compliance, explicit typing on all function signatures, strict Pydantic v2 schemas.
- **Frontend**: ESLint verification with zero errors (`npm run lint`), TypeScript strict checking.
- **Git Hygiene**: Clean status, zero uncommitted stray artifacts, zero hardcoded credentials or API keys.
