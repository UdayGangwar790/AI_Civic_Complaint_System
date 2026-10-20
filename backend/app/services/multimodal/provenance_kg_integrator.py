"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.6: Provenance & Knowledge Graph Integration

Connects M9.4 (Vernacular Normalization) and M9.5 (Visual Resolution Auditing)
to M6.4 (Evidence Provenance Engine) and M6.5 (Civic Knowledge Graph).

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. M9.6 is an integration layer, not an autonomous decider.
2. Normalization confidence is lexical confidence only.
3. Model observation != physical ground truth.
4. DEFECT_NOT_OBSERVED != repair confirmed.
5. Invalidation must be preserved deterministically without deleting audit history.
6. RBAC and privacy: No PII, credentials, or internal filesystem paths exposed.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Optional
import uuid

from app.services.multimodal.contracts import (
    AssertionType,
    EpistemicState,
    ResolutionAuditOutcome,
    VernacularNormalizationResult,
    VisualResolutionAuditRequest,
    VisualResolutionAuditResult,
)
from app.schemas.knowledge_graph import (
    KnowledgeNode,
    KnowledgeEdge,
    NodeType,
    RelationType,
    canonical_case_key,
    canonical_vernacular_normalization_key,
    canonical_visual_audit_key,
    canonical_issue_key,
    canonical_evidence_key,
)
from app.schemas.provenance import (
    ClaimType,
    EvidenceRecord,
    SourceType,
    VerificationState,
    calculate_evidence_hash,
)
from app.services.provenance_engine import get_provenance_engine, EvidenceProvenanceEngine
from app.services.knowledge_graph import get_knowledge_graph_service, CivicKnowledgeGraphService as KnowledgeGraphService

logger = logging.getLogger("cvki.multimodal.provenance_kg_integrator")

FROZEN_CV_MODEL_HASH = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"


class MultimodalProvenanceKGIntegrator:
    """
    Coordinates provenance recording (M6.4) and knowledge graph synchronization (M6.5)
    for M9 multimodal outputs (vernacular normalization and visual resolution auditing).
    """

    def __init__(
        self,
        prov_engine: Optional[EvidenceProvenanceEngine] = None,
        kg_service: Optional[KnowledgeGraphService] = None,
    ):
        self._prov_engine = prov_engine
        self._kg_service = kg_service

    @property
    def prov_engine(self) -> EvidenceProvenanceEngine:
        return self._prov_engine or get_provenance_engine()

    @property
    def kg_service(self) -> KnowledgeGraphService:
        return self._kg_service or get_knowledge_graph_service()

    # =========================================================================
    # M9.4: Vernacular Normalization Provenance
    # =========================================================================

    def record_vernacular_normalization_provenance(
        self,
        case_reference: str,
        result: VernacularNormalizationResult,
        observed_at: Optional[datetime] = None,
    ) -> EvidenceRecord:
        """
        Creates an EvidenceRecord in M6.4 for an M9.4 VernacularNormalizationResult.

        Epistemic Bound:
        - Original citizen text remains USER_REPORTED.
        - Normalized interpretation is SYSTEM_DERIVED.
        - NEVER promoted to VERIFIED_EVIDENCE.
        - Lexical confidence != defect existence probability.
        """
        now = datetime.now(timezone.utc)
        engine_id = (
            result.metadata.get("engine_identity")
            or getattr(result, "engine_identity", "m9_4_vernacular_normalizer")
        )

        # Assertion / verification mapping
        # Negated or uncertain expressions must never be marked verified or fully supported
        is_negated = result.assertion_type == AssertionType.NEGATED
        is_uncertain = result.assertion_type == AssertionType.UNCERTAIN

        if is_negated or is_uncertain or not result.issue_candidates:
            verification_state = VerificationState.NOT_VERIFIED
        else:
            verification_state = VerificationState.SYSTEM_DERIVED

        # Extract canonical concepts as string list
        canonical_concepts = [
            c.value if hasattr(c, "value") else str(c) for c in result.issue_candidates
        ]

        # Deterministic payload for fingerprint
        fingerprint_content = {
            "original_text": result.original_text,
            "normalized_text": result.normalized_text,
            "detected_language": result.detected_language,
            "script": result.script,
            "canonical_civic_concepts": canonical_concepts,
            "assertion_type": result.assertion_type.value,
            "negated_candidates": [c.value if hasattr(c, "value") else str(c) for c in result.negated_candidates],
            "lexical_confidence": round(result.confidence, 4),
            "engine": engine_id,
        }

        evidence_hash = calculate_evidence_hash(
            claim_type=ClaimType.VERNACULAR_NORMALIZATION.value,
            matched_attribute="vernacular_normalization",
            source=f"{engine_id} Vernacular Normalizer",
            source_type=SourceType.SYSTEM_DERIVED.value,
            value=fingerprint_content,
        )

        # Check for existing duplicate active record to prevent redundant entries
        existing_history = self.prov_engine.repository.find_history(
            case_reference, ClaimType.VERNACULAR_NORMALIZATION
        )
        for existing in existing_history:
            if existing.status == "active" and existing.evidence_hash == evidence_hash:
                logger.debug(
                    "Reusing existing active vernacular normalization record '%s' for case '%s'.",
                    existing.evidence_id,
                    case_reference,
                )
                return existing

        explanation = (
            result.explanation
            or f"Citizen report vernacular expression normalized to canonical concepts: {canonical_concepts} (assertion: {result.assertion_type.value})."
        )

        metadata: dict[str, Any] = {
            "original_text": result.original_text,
            "normalized_text": result.normalized_text,
            "detected_language": result.detected_language,
            "script": result.script,
            "canonical_civic_concepts": canonical_concepts,
            "assertion_type": result.assertion_type.value,
            "negated_candidates": [c.value if hasattr(c, "value") else str(c) for c in result.negated_candidates],
            "lexical_normalization_confidence": result.confidence,
            "normalization_engine_identity": engine_id,
            "confidence_type": "lexical_confidence",  # Explicitly not defect probability
            "epistemic_state": "USER_REPORTED_SYSTEM_DERIVED",
            "ground_truth": False,
        }

        # Bounded metadata: sanitize any user PII / secret paths if accidentally passed
        metadata.pop("password", None)
        metadata.pop("token", None)
        metadata.pop("secret", None)

        record = EvidenceRecord(
            evidence_id=f"ev_vnorm_{uuid.uuid4().hex[:14]}",
            case_reference=case_reference,
            claim_type=ClaimType.VERNACULAR_NORMALIZATION,
            matched_attribute="vernacular_normalization",
            source=f"{engine_id} Vernacular Normalizer",
            source_type=SourceType.SYSTEM_DERIVED,
            provider="CVKI Multimodal Subsystem (M9.4)",
            observed_at=observed_at or now,
            retrieved_at=now,
            freshness="fresh",
            status="active",
            verification_state=verification_state,
            explanation=explanation,
            evidence_hash=evidence_hash,
            version=len(existing_history) + 1,
            metadata=metadata,
        )

        return self.prov_engine.repository.save(record)

    # =========================================================================
    # M9.5: Visual Resolution Audit Provenance
    # =========================================================================

    def record_visual_audit_provenance(
        self,
        case_reference: str,
        result: VisualResolutionAuditResult,
        audit_request: Optional[VisualResolutionAuditRequest] = None,
        observed_at: Optional[datetime] = None,
    ) -> EvidenceRecord:
        """
        Creates an EvidenceRecord in M6.4 for an M9.5 VisualResolutionAuditResult.

        Epistemic Bound:
        - NEVER automatically marked VERIFIED.
        - DEFECT_PERSISTS -> SYSTEM_DERIVED
        - DEFECT_NOT_OBSERVED -> SYSTEM_DERIVED (NEVER repair confirmed)
        - INCONCLUSIVE / INSUFFICIENT_EVIDENCE -> NOT_VERIFIED
        """
        now = datetime.now(timezone.utc)
        engine_id = (
            result.model_metadata.get("engine_identity")
            or "m9_5_visual_resolution_auditor"
        )
        issue_cat_str = (
            result.issue_category.value
            if hasattr(result.issue_category, "value")
            else str(result.issue_category)
        )
        outcome_str = (
            result.outcome.value
            if hasattr(result.outcome, "value")
            else str(result.outcome)
        )

        # Enforce Epistemic Safety: Never promote to VERIFIED
        if outcome_str in ("DEFECT_PERSISTS", "DEFECT_NOT_OBSERVED"):
            verification_state = VerificationState.SYSTEM_DERIVED
        else:
            verification_state = VerificationState.NOT_VERIFIED

        fingerprint_content = {
            "case_reference": case_reference,
            "outcome": outcome_str,
            "issue_category": issue_cat_str,
            "evidence_quality": result.evidence_quality.value if hasattr(result.evidence_quality, "value") else str(result.evidence_quality),
            "temporal_consistency": result.temporal_consistency.value if hasattr(result.temporal_consistency, "value") else str(result.temporal_consistency),
            "spatial_consistency": result.spatial_consistency.value if hasattr(result.spatial_consistency, "value") else str(result.spatial_consistency),
            "engine": engine_id,
            "model_hash": result.model_metadata.get("model_hash", FROZEN_CV_MODEL_HASH),
        }

        evidence_hash = calculate_evidence_hash(
            claim_type=ClaimType.VISUAL_RESOLUTION_AUDIT.value,
            matched_attribute="visual_resolution_audit",
            source=f"{engine_id} Visual Auditor",
            source_type=SourceType.SYSTEM_DERIVED.value,
            value=fingerprint_content,
        )

        # Check existing history
        existing_history = self.prov_engine.repository.find_history(
            case_reference, ClaimType.VISUAL_RESOLUTION_AUDIT
        )
        for existing in existing_history:
            if existing.status == "active" and existing.evidence_hash == evidence_hash:
                logger.debug(
                    "Reusing existing active visual audit record '%s' for case '%s'.",
                    existing.evidence_id,
                    case_reference,
                )
                return existing

        explanation = (
            result.explanation
            or f"Visual resolution audit for case {case_reference}: outcome {outcome_str}."
        )

        metadata: dict[str, Any] = {
            "outcome": outcome_str,
            "issue_category": issue_cat_str,
            "before_observation": result.before_observation,
            "after_observation": result.after_observation,
            "evidence_quality": result.evidence_quality.value if hasattr(result.evidence_quality, "value") else str(result.evidence_quality),
            "temporal_consistency": result.temporal_consistency.value if hasattr(result.temporal_consistency, "value") else str(result.temporal_consistency),
            "spatial_consistency": result.spatial_consistency.value if hasattr(result.spatial_consistency, "value") else str(result.spatial_consistency),
            "before_model_identity": result.model_metadata.get("before_model_identity", "m1.13-yolov8n"),
            "after_model_identity": result.model_metadata.get("after_model_identity", "m1.13-yolov8n"),
            "model_hash": result.model_metadata.get("model_hash", FROZEN_CV_MODEL_HASH),
            "thresholds": result.model_metadata.get("thresholds", {}),
            "limitations": result.limitations,
            "epistemic_state": "MODEL_OBSERVATION",
            "is_repair_confirmed": False,  # Strict safeguard: never automated repair confirmation
            "ground_truth": False,
        }

        record = EvidenceRecord(
            evidence_id=f"ev_vaudit_{uuid.uuid4().hex[:14]}",
            case_reference=case_reference,
            claim_type=ClaimType.VISUAL_RESOLUTION_AUDIT,
            matched_attribute="visual_resolution_audit",
            source=f"{engine_id} Visual Auditor",
            source_type=SourceType.SYSTEM_DERIVED,
            provider="CVKI Multimodal Subsystem (M9.5)",
            observed_at=observed_at or now,
            retrieved_at=now,
            freshness="fresh",
            status="active",
            verification_state=verification_state,
            explanation=explanation,
            evidence_hash=evidence_hash,
            version=len(existing_history) + 1,
            metadata=metadata,
        )

        return self.prov_engine.repository.save(record)

    # =========================================================================
    # Combined Atomic KG Integration
    # =========================================================================

    def integrate_vernacular_normalization(
        self,
        case_reference: str,
        result: VernacularNormalizationResult,
        norm_id: Optional[str] = None,
    ) -> tuple[EvidenceRecord, KnowledgeNode]:
        """
        Atomically records vernacular normalization into M6.4 provenance and M6.5 knowledge graph.
        """
        evidence_record = self.record_vernacular_normalization_provenance(case_reference, result)

        active_norm_id = norm_id or getattr(result, "normalization_id", None) or uuid.uuid4().hex[:12]
        canonical_concepts = [
            c.value if hasattr(c, "value") else str(c) for c in result.issue_candidates
        ]

        kg_node = self.kg_service.record_vernacular_normalization_graph(
            case_reference_id=case_reference,
            norm_id=active_norm_id,
            original_text=result.original_text,
            normalized_text=result.normalized_text,
            detected_language=result.detected_language,
            script=result.script,
            canonical_civic_concepts=canonical_concepts,
            assertion_type=result.assertion_type.value,
            confidence=result.confidence,
            evidence_id=evidence_record.evidence_id,
            explanation=result.explanation,
        )

        return evidence_record, kg_node

    def integrate_visual_audit(
        self,
        case_reference: str,
        result: VisualResolutionAuditResult,
        audit_id: Optional[str] = None,
        before_detection_key: Optional[str] = None,
        after_detection_key: Optional[str] = None,
    ) -> tuple[EvidenceRecord, KnowledgeNode]:
        """
        Atomically records visual resolution audit into M6.4 provenance and M6.5 knowledge graph.
        """
        evidence_record = self.record_visual_audit_provenance(case_reference, result)

        active_audit_id = audit_id or getattr(result, "audit_id", None) or uuid.uuid4().hex[:12]
        issue_cat_str = (
            result.issue_category.value
            if hasattr(result.issue_category, "value")
            else str(result.issue_category)
        )
        outcome_str = (
            result.outcome.value
            if hasattr(result.outcome, "value")
            else str(result.outcome)
        )
        quality_str = (
            result.evidence_quality.value
            if hasattr(result.evidence_quality, "value")
            else str(result.evidence_quality)
        )

        temporal_ok = result.temporal_consistency.value == "CONSISTENT" if hasattr(result.temporal_consistency, "value") else True
        spatial_ok = result.spatial_consistency.value == "CONSISTENT" if hasattr(result.spatial_consistency, "value") else True

        kg_node = self.kg_service.record_visual_audit_graph(
            case_reference_id=case_reference,
            audit_id=active_audit_id,
            outcome=outcome_str,
            evidence_quality=quality_str,
            issue_category=issue_cat_str,
            temporal_consistency=temporal_ok,
            spatial_consistency=spatial_ok,
            evidence_id=evidence_record.evidence_id,
            before_detection_key=before_detection_key,
            after_detection_key=after_detection_key,
            explanation=result.explanation,
            metadata={
                "before_observation": result.before_observation,
                "after_observation": result.after_observation,
                "limitations": result.limitations,
                "model_metadata": result.model_metadata,
            },
        )

        return evidence_record, kg_node

    # =========================================================================
    # Provenance Invalidation & Graph Propagation
    # =========================================================================

    def invalidate_m9_evidence(
        self,
        evidence_id: str,
        reason: str,
        actor_user_id: str = "system",
        actor_role: str = "admin",
    ) -> Optional[EvidenceRecord]:
        """
        Invalidates an M9 evidence record in M6.4 without deleting historical evidence.
        Downstream graph explanations referencing this evidence will reflect NOT_VERIFIED.
        """
        return self.prov_engine.invalidate_evidence(
            evidence_id=evidence_id,
            reason=reason,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )


multimodal_provenance_kg_integrator = MultimodalProvenanceKGIntegrator()


def get_multimodal_provenance_kg_integrator() -> MultimodalProvenanceKGIntegrator:
    """Returns singleton MultimodalProvenanceKGIntegrator instance."""
    return multimodal_provenance_kg_integrator


def set_multimodal_provenance_kg_integrator(
    integrator: MultimodalProvenanceKGIntegrator,
) -> None:
    """Overrides singleton instance (for testing)."""
    global multimodal_provenance_kg_integrator
    multimodal_provenance_kg_integrator = integrator
