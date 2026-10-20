"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.1: Deterministic Mock Multimodal Provider

Implements the MultimodalInferenceProvider SPI for test harnesses, local validation,
and architectural verification.
- Completely deterministic output
- Zero external network requests
- Zero vendor SDK dependencies
- Zero secret / API key requirements
- Establishes interfaces only; does not claim multimodal reasoning accuracy
"""

from datetime import datetime, timezone
import time
from typing import Optional

from app.services.multimodal.base_provider import (
    MultimodalInferenceProvider,
    MultimodalProviderDescriptor,
)
from app.services.multimodal.contracts import (
    AlignmentState,
    AmbiguityAssessment,
    AmbiguityState,
    CivicIntent,
    EpistemicState,
    EvidenceAlignmentAssessment,
    ExtractedCivicEntity,
    IssueCategory,
    MultimodalInput,
    MultimodalTaskType,
    StandardMultimodalResult,
)
from app.services.multimodal.security import sanitize_text_pii


class MockMultimodalProvider(MultimodalInferenceProvider):
    """
    Deterministic mock provider implementing MultimodalInferenceProvider SPI.
    Simulates a compliant multimodal reasoning engine for testing contract boundaries.
    """

    def __init__(
        self,
        provider_id: str = "mock_multimodal_provider",
        model_id: str = "mock_civic_multimodal",
        model_version: str = "0.1.0-mock",
        force_failure: bool = False,
    ):
        self._descriptor = MultimodalProviderDescriptor(
            provider_id=provider_id,
            model_id=model_id,
            model_version=model_version,
            supported_tasks=[
                MultimodalTaskType.COMPLAINT_ANALYSIS,
                MultimodalTaskType.CROSS_MODAL_VERIFICATION,
                MultimodalTaskType.CLARIFICATION_GENERATION,
                MultimodalTaskType.VERNACULAR_NORMALIZATION,
                MultimodalTaskType.RESOLUTION_AUDIT,
            ],
            supported_languages=["en", "hi", "hinglish"],
            capabilities=[
                "mock_inference",
                "deterministic_contract_testing",
                "simulated_failure_modes",
            ],
            is_deterministic=True,
            production_ready=False,
            model_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata={"environment": "testing", "engine": "mock_rules"},
        )
        self._loaded: bool = False
        self._force_failure = force_failure

    @property
    def descriptor(self) -> MultimodalProviderDescriptor:
        return self._descriptor

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def initialize(self) -> bool:
        if self._force_failure:
            self._loaded = False
            return False
        self._loaded = True
        return True

    def infer(self, input_data: MultimodalInput) -> StandardMultimodalResult:
        if not self._loaded:
            raise RuntimeError("Cannot execute inference: MockMultimodalProvider is not initialized.")

        started_at = time.perf_counter()

        # Sanitize text PII if text was provided
        clean_text = sanitize_text_pii(input_data.text) if input_data.text else ""

        # Determine issue category from CV result if available, else from context
        category = IssueCategory.UNKNOWN
        if input_data.cv_result and input_data.cv_result.detections:
            top_detection = input_data.cv_result.detections[0]
            cat_mapping = {
                "open_damaged_manhole": IssueCategory.OPEN_DAMAGED_MANHOLE,
                "damaged_missing_road_sign": IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
                "road_waterlogging": IssueCategory.ROAD_WATERLOGGING,
            }
            category = cat_mapping.get(top_detection.class_name, IssueCategory.OTHER_CIVIC_ISSUE)
        elif input_data.civic_issue_context and input_data.civic_issue_context.reported_class:
            cat_mapping = {
                "open_damaged_manhole": IssueCategory.OPEN_DAMAGED_MANHOLE,
                "damaged_missing_road_sign": IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
                "road_waterlogging": IssueCategory.ROAD_WATERLOGGING,
            }
            category = cat_mapping.get(
                input_data.civic_issue_context.reported_class,
                IssueCategory.OTHER_CIVIC_ISSUE,
            )

        # Extract mock entities from location context if present
        entities: list[ExtractedCivicEntity] = []
        if input_data.location_context:
            if input_data.location_context.road_name:
                entities.append(
                    ExtractedCivicEntity(
                        entity_name=input_data.location_context.road_name,
                        entity_type="road",
                        confidence=1.0,
                    )
                )
            if input_data.location_context.city:
                entities.append(
                    ExtractedCivicEntity(
                        entity_name=input_data.location_context.city,
                        entity_type="city",
                        confidence=1.0,
                    )
                )

        duration_ms = (time.perf_counter() - started_at) * 1000.0

        # Construct strictly bounded StandardMultimodalResult
        return StandardMultimodalResult(
            success=True,
            provider_id=self._descriptor.provider_id,
            model_id=self._descriptor.model_id,
            model_version=self._descriptor.model_version,
            model_hash=self._descriptor.model_hash,
            task=MultimodalTaskType.COMPLAINT_ANALYSIS,
            processing_time_ms=round(duration_ms, 2),
            timestamp=datetime.now(timezone.utc),
            language=input_data.language or "en",
            normalized_intent=CivicIntent.REPORT_ISSUE,
            issue_category=category,
            extracted_entities=entities,
            ambiguity_assessment=AmbiguityAssessment(
                state=AmbiguityState.NOT_EVALUATED,
                reasons=[],
                missing_information=[],
                requires_clarification=False,
            ),
            evidence_alignment=EvidenceAlignmentAssessment(
                state=AlignmentState.NOT_EVALUATED,
                matched_issue_category=category if category != IssueCategory.UNKNOWN else None,
                conflicting_fields=[],
                supporting_evidence=[],
                missing_evidence=[],
                explanation="M9.1 contract placeholder: cross-modal reasoning not evaluated in M9.1.",
            ),
            suggested_clarifications=[],
            explanation=f"Deterministic mock analysis for request {input_data.request_id}.",
            epistemic_state=EpistemicState.MODEL_OBSERVATION,
            metadata={"mock_execution": True, "text_length": len(clean_text)},
        )

    def shutdown(self) -> None:
        self._loaded = False
