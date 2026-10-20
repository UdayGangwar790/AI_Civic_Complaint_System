# CVKI — Module 9.1: Multimodal Intelligence SPI & Standard Contracts

## 1. Motivation
The completion of Module 8 (Computer Vision 2.0) established a framework-agnostic SPI (`CVInferenceProvider`) and isolated the frozen M1.13 production model. However, CVKI's textual complaint understanding layer (M3.6) remained bounded by a rule-based regex keyword matcher (`rule_based_multilingual_lexicon_baseline`), leaving a major epistemic gap between visual detections and citizen text.

Module 9.1 establishes the foundational **Multimodal Intelligence Service Provider Interface (SPI)** and standardized contracts. Analogous to M8's computer vision decoupling, M9.1 decouples multimodal reasoning from any specific model, runtime engine, or cloud vendor SDK (OpenAI, Gemini, Claude, Ollama, HuggingFace).

> **Core Principle:**  
> *"M9.1 establishes interfaces and contracts; it does not establish multimodal reasoning accuracy."*

---

## 2. Architecture Overview
M9.1 introduces a clean architectural abstraction layer:

```text
[Citizen Input: Text + Location + Prior History]
[Visual Defect Context: StandardDetectionResult from M8]
                       │
                       ▼
            [MultimodalInput Contract]
                       │
                       ▼
      [MultimodalInferenceProvider SPI]
         ├── descriptor()
         ├── is_loaded()
         ├── initialize()
         ├── infer(MultimodalInput) ──► StandardMultimodalResult
         └── shutdown()
                       ▲
                       │ Controlled Whitelist Registration
      [MultimodalProviderResolver]
         └── Approved Providers: ["mock_multimodal_provider", ...]
```

### Decoupling Rules Enforced
1. **Zero Vendor Lock-In:** Downstream code interacts exclusively with `StandardMultimodalResult`.
2. **Zero Provider SDK Imports:** The package `backend/app/services/multimodal/` strictly contains no imports of `openai`, `anthropic`, `google-generativeai`, `transformers`, `torch`, or `ultralytics`.
3. **Epistemic Boundary:** Model observations are strictly tagged as `MODEL_OBSERVATION` and cannot masquerade as verified physical ground truth.

---

## 3. Input Contract (`MultimodalInput`)
The `MultimodalInput` model in `contracts.py` standardizes all data passed to multimodal inference:

- `request_id`: Bounded alphanumeric string (`[A-Za-z0-9._-]{1,128}`) for audit correlation.
- `text`: Optional citizen complaint or dialogue text (strictly capped at 5,000 characters).
- `language`: Optional language code hint (`en`, `hi`, `hinglish`).
- `evidence_reference_id`: Controlled internal storage identifier (validated against path traversal and external URL injection).
- `cv_result`: Optional `StandardDetectionResult` conforming to the M8 standardized contract.
- `civic_issue_context`: Structured civic metadata (`reported_class`, `severity`, `hazard_description`).
- `location_context`: Structured geospatial attributes (`road_name`, `locality`, `city`, coordinates).
- `conversation_context`: Bounded history (up to 30 messages) of `MultimodalMessage` (`citizen`, `assistant`, `system`).
- `origin`: Explicit tagging (`USER_PROVIDED`, `MODEL_DERIVED`, `SYSTEM_DERIVED`).
- `metadata`: Bounded dictionary (max 50 keys, scrubbed of credential patterns).

At least one of `text`, `cv_result`, or `evidence_reference_id` must be present.

---

## 4. Output Contract (`StandardMultimodalResult`)
The `StandardMultimodalResult` model represents model-independent reasoning:

- `success`: Execution status boolean.
- `provider_id`: Unique provider implementation identifier.
- `model_id`: Model instance identifier.
- `model_version`: Semantic release version.
- `model_hash`: Cryptographic SHA-256 hash where available.
- `task`: Task category (`COMPLAINT_ANALYSIS`, `CROSS_MODAL_VERIFICATION`, etc.).
- `processing_time_ms`: Execution latency in milliseconds.
- `timestamp`: UTC execution timestamp.
- `language`: Recognized interaction language.
- `normalized_intent`: Controlled `CivicIntent` enum (`REPORT_ISSUE`, `UPDATE_EXISTING_REPORT`, `ASK_STATUS`, `PROVIDE_CLARIFICATION`, `VERIFY_RESOLUTION`, `UNKNOWN`).
- `issue_category`: Controlled `IssueCategory` enum aligned with M1.13 classes.
- `extracted_entities`: List of `ExtractedCivicEntity` (road, landmark, defect, locality).
- `ambiguity_assessment`: Structured `AmbiguityAssessment` (`state`, `reasons`, `missing_information`, `requires_clarification`).
- `evidence_alignment`: Structured `EvidenceAlignmentAssessment` (`state`, `matched_issue_category`, `conflicting_fields`, `supporting_evidence`, `missing_evidence`, `explanation`).
- `suggested_clarifications`: Targeted non-leading questions for the citizen.
- `explanation`: Transparent summary of reasoning.
- `epistemic_state`: Explicit epistemic tag (default: `MODEL_OBSERVATION`).
- `metadata`: Extensible execution details.

---

## 5. Epistemic States
To prevent automated systems from conflating probabilistic model outputs with objective reality, M9.1 defines seven mutually exclusive epistemic states:

1. `USER_REPORTED`: Unverified claims authored by citizens.
2. `MODEL_OBSERVATION`: Inferences generated by an AI model.
3. `SYSTEM_DERIVED`: Deterministic rules or database aggregations.
4. `VERIFIED_EVIDENCE`: Authenticated ground truth (e.g. staff site inspection notes).
5. `NOT_EVALUATED`: Stage has not yet been processed.
6. `UNKNOWN`: Insufficient signals to classify.
7. `INCONCLUSIVE`: Conflicting signals preventing determination.

> **Integrity Guard:** `StandardMultimodalResult` validator rejects any attempt by a model to return `VERIFIED_EVIDENCE`.

---

## 6. Provider Interface (`MultimodalInferenceProvider`)
The abstract base class defines the complete operational lifecycle:

```python
class MultimodalInferenceProvider(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> MultimodalProviderDescriptor: ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool: ...

    @abstractmethod
    def initialize(self) -> bool: ...

    @abstractmethod
    def infer(self, input_data: MultimodalInput) -> StandardMultimodalResult: ...

    @abstractmethod
    def shutdown(self) -> None: ...
```

---

## 7. Mock Provider (`MockMultimodalProvider`)
A deterministic mock provider is provided in `mock_provider.py` to enable comprehensive testing without external network connections:
- Declares capability tokens and supported tasks.
- Operates 100% locally and deterministically.
- Returns structured `StandardMultimodalResult` with default `AmbiguityState.NOT_EVALUATED` and `AlignmentState.NOT_EVALUATED`.
- Validates input contracts and applies PII redaction.
- Supports failure simulation for resilience testing.

---

## 8. Security Boundaries
1. **No Path Traversal:** `evidence_reference_id` strictly rejects `..`, `/`, `\`, and null bytes.
2. **No Arbitrary Network Fetch:** `evidence_reference_id` strictly rejects URL schemes (`http://`, `https://`, `file://`, `ftp://`).
3. **PII Sanitization:** Utility functions in `security.py` redact email addresses and phone numbers from user text.
4. **Credential Leakage Shield:** Metadata payloads are recursively inspected; keys matching `password`, `secret`, `token`, `jwt`, `auth`, `credential`, `session`, or `cookie` are categorically rejected or redacted.
5. **No Dynamic Code Execution:** `MultimodalProviderResolver` permits only pre-approved, server-registered factories. Dynamic module imports from client strings are forbidden.

---

## 9. Testing & Validation
All 16 unit tests in `backend/tests/test_multimodal_spi_m91.py` pass:
- Valid and invalid input contracts.
- Input bounds (5,000 char maximum text, 128 char request_id).
- Epistemic integrity validation (forbidding `VERIFIED_EVIDENCE` from models).
- Ambiguity and Evidence Alignment contract structures.
- Mock provider lifecycle and deterministic inference.
- Provider resolver whitelist enforcement.
- Security constraints: path traversal and external URL rejection.
- Text PII redaction (emails and phones) and metadata credential scrubbing.

M8 regression verification confirmed 100% pass rate across 64 unit tests (`test_cv_*.py`).

---

## 10. Backward Compatibility
- **Zero Impact on M8:** `StandardDetectionResult` is imported as a read-only input type; no changes were made to M8 data structures.
- **Zero Impact on M1.13:** The production model checkpoint (`best.pt`, SHA-256 `602160d4...`) remains frozen and unmodified.
- **Zero Impact on APIs:** No existing FastAPI endpoints were altered.

---

## 11. What M9.1 Deliberately Does NOT Implement
In strict adherence to the M9.1 scope:
- **NO cross-modal reasoning logic:** Alignment fields return `NOT_EVALUATED`.
- **NO active clarification dialogue generation:** Suggested clarifications return an empty list.
- **NO vernacular normalization:** Text is passed through without linguistic alteration.
- **NO before/after visual change detection:** Resolution audit tasks are defined in contract only.
- **NO provenance engine integration:** New claim types will be linked in M9.6.
- **NO knowledge graph integration:** New graph nodes will be populated in M9.6.
- **NO external LLM or VLM SDK dependencies:** The system remains completely self-contained.

---

## 12. Future M9.2 Dependency
Module 9.2 (Cross-Modal Evidence Consistency & Grounding Engine) will build directly upon M9.1 by:
1. Consuming `MultimodalInput` containing both `text` and `cv_result`.
2. Implementing the first concrete cross-modal comparison logic to populate `EvidenceAlignmentAssessment` (`ALIGNED`, `CONFLICTING`, `PARTIALLY_ALIGNED`).
3. Emitting a grounded multimodal evaluation without mutating underlying model weights.
