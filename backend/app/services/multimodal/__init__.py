"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.1: Multimodal Intelligence SPI Package
"""

from app.services.multimodal.contracts import (
    AlignmentState,
    AmbiguityAssessment,
    AmbiguityState,
    AssertionType,
    CivicIntent,
    CivicIssueContext,
    ClarificationAnswer,
    ClarificationAnswerType,
    ClarificationQuestion,
    ClarificationQuestionType,
    ClarificationResult,
    ClarificationStatus,
    ConsistencyAssessmentState,
    EpistemicState,
    EvidenceAlignmentAssessment,
    EvidenceQuality,
    ExtractedCivicEntity,
    InformationOrigin,
    IssueCategory,
    MultimodalInput,
    MultimodalLocationContext,
    MultimodalMessage,
    MultimodalTaskType,
    ResolutionAuditOutcome,
    StandardMultimodalResult,
    VernacularNormalizationResult,
    VisualResolutionAuditRequest,
    VisualResolutionAuditResult,
)
from app.services.multimodal.base_provider import (
    MultimodalInferenceProvider,
    MultimodalProviderDescriptor,
)
from app.services.multimodal.mock_provider import MockMultimodalProvider
from app.services.multimodal.resolver import (
    MultimodalProviderNotFoundError,
    MultimodalProviderResolver,
    multimodal_provider_resolver,
)
from app.services.multimodal.consistency_engine import (
    CrossModalConsistencyEngine,
    cross_modal_consistency_engine,
)
from app.services.multimodal.clarification_resolver import (
    ActiveClarificationResolver,
    active_clarification_resolver,
)
from app.services.multimodal.vernacular_normalizer import (
    MultilingualVernacularNormalizer,
    multilingual_vernacular_normalizer,
)
from app.services.multimodal.visual_resolution_auditor import (
    VisualResolutionAuditor,
    visual_resolution_auditor,
)
from app.services.multimodal.security import (
    sanitize_multimodal_metadata,
    sanitize_text_pii,
)
from app.services.multimodal.provenance_kg_integrator import (
    MultimodalProvenanceKGIntegrator,
    get_multimodal_provenance_kg_integrator,
    multimodal_provenance_kg_integrator,
    set_multimodal_provenance_kg_integrator,
)

__all__ = [
    "ActiveClarificationResolver",
    "AlignmentState",
    "AmbiguityAssessment",
    "AmbiguityState",
    "AssertionType",
    "CivicIntent",
    "CivicIssueContext",
    "ClarificationAnswer",
    "ClarificationAnswerType",
    "ClarificationQuestion",
    "ClarificationQuestionType",
    "ClarificationResult",
    "ClarificationStatus",
    "ConsistencyAssessmentState",
    "CrossModalConsistencyEngine",
    "EpistemicState",
    "EvidenceAlignmentAssessment",
    "EvidenceQuality",
    "ExtractedCivicEntity",
    "InformationOrigin",
    "IssueCategory",
    "MultilingualVernacularNormalizer",
    "MultimodalInferenceProvider",
    "MultimodalInput",
    "MultimodalLocationContext",
    "MultimodalMessage",
    "MultimodalProvenanceKGIntegrator",
    "MultimodalProviderDescriptor",
    "MultimodalProviderNotFoundError",
    "MultimodalProviderResolver",
    "MultimodalTaskType",
    "MockMultimodalProvider",
    "ResolutionAuditOutcome",
    "StandardMultimodalResult",
    "VernacularNormalizationResult",
    "VisualResolutionAuditRequest",
    "VisualResolutionAuditResult",
    "VisualResolutionAuditor",
    "active_clarification_resolver",
    "cross_modal_consistency_engine",
    "get_multimodal_provenance_kg_integrator",
    "multilingual_vernacular_normalizer",
    "multimodal_provenance_kg_integrator",
    "multimodal_provider_resolver",
    "sanitize_multimodal_metadata",
    "sanitize_text_pii",
    "set_multimodal_provenance_kg_integrator",
    "visual_resolution_auditor",
]


