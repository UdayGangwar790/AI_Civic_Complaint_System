"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.2: Multimodal REST API Gateway Service
"""

from datetime import datetime, timezone
import logging
import time
from typing import Optional
from uuid import uuid4

from app.schemas.multimodal_gateway import (
    MultimodalGatewayRequest,
    MultimodalGatewayResponse,
)
from app.services.multimodal.contracts import (
    AlignmentState,
    CivicIssueContext,
    EpistemicState,
    IssueCategory,
    MultimodalInput,
    MultimodalTaskType,
    VisualResolutionAuditRequest,
)
from app.services.multimodal.consistency_engine import cross_modal_consistency_engine
from app.services.multimodal.clarification_resolver import active_clarification_resolver
from app.services.multimodal.vernacular_normalizer import multilingual_vernacular_normalizer
from app.services.multimodal.visual_resolution_auditor import visual_resolution_auditor
from app.services.multimodal.provenance_kg_integrator import get_multimodal_provenance_kg_integrator
from app.services.multimodal.security import sanitize_text_pii

logger = logging.getLogger("cvki.multimodal_gateway")


class MultimodalGatewayService:
    """
    Thin, bounded orchestration service that coordinates M9 multimodal engines:
    1. Multilingual Vernacular Normalizer (M9.4)
    2. Computer Vision Detection context (M8)
    3. Cross-Modal Evidence Consistency Engine (M9.2)
    4. Active Clarification Resolver (M9.3)
    5. Before/After Visual Resolution Auditor (M9.5, if before/after present)
    6. Provenance & Knowledge Graph Integrator (M9.6 / M6.4 / M6.5)
    """

    def __init__(self):
        self._vernacular_normalizer = multilingual_vernacular_normalizer
        self._consistency_engine = cross_modal_consistency_engine
        self._clarification_resolver = active_clarification_resolver
        self._visual_auditor = visual_resolution_auditor
        self._provenance_kg_integrator = get_multimodal_provenance_kg_integrator()

    def process(self, request: MultimodalGatewayRequest) -> MultimodalGatewayResponse:
        """
        Executes the multimodal pipeline deterministically.
        Guarantees:
        - No LLM hallucinations or external API dependencies.
        - Epistemic state is strictly SYSTEM_DERIVED.
        - No physical ground truth claims.
        """
        start_time = time.perf_counter()
        warnings: list[str] = []
        provenance_claims: list[str] = []
        kg_node_keys: list[str] = []

        # 1. PII and input sanitization
        clean_raw_text = sanitize_text_pii(request.text or "")
        normalized_text: Optional[str] = None
        vernacular_result = None

        # 2. M9.4 Multilingual Vernacular Normalization
        if clean_raw_text:
            vernacular_result = self._vernacular_normalizer.normalize(
                raw_text=clean_raw_text,
            )
            normalized_text = vernacular_result.normalized_text

            # Record vernacular normalization into provenance and KG if case reference is present
            if request.case_reference:
                try:
                    ev_rec, kg_node = self._provenance_kg_integrator.integrate_vernacular_normalization(
                        case_reference=request.case_reference,
                        result=vernacular_result,
                    )
                    provenance_claims.append(ev_rec.evidence_id)
                    kg_node_keys.append(kg_node.canonical_key)
                except Exception as exc:
                    logger.warning("Failed to record vernacular normalization in provenance/KG: %s", exc)
                    warnings.append(f"Provenance recording warning: {str(exc)}")

        # Effective text to evaluate
        effective_text = normalized_text or clean_raw_text

        # 3. Determine Issue Category from context or detections
        issue_category = request.issue_category or IssueCategory.UNKNOWN
        if issue_category == IssueCategory.UNKNOWN and request.detection_result:
            primary_det = None
            if request.detection_result.detections:
                primary_det = max(request.detection_result.detections, key=lambda d: d.confidence)
            if primary_det:
                name_upper = primary_det.class_name.upper()
                if "MANHOLE" in name_upper:
                    issue_category = IssueCategory.OPEN_DAMAGED_MANHOLE
                elif "SIGN" in name_upper:
                    issue_category = IssueCategory.DAMAGED_MISSING_ROAD_SIGN
                elif "WATER" in name_upper or "FLOOD" in name_upper:
                    issue_category = IssueCategory.ROAD_WATERLOGGING
                else:
                    issue_category = IssueCategory.OTHER_CIVIC_ISSUE

        issue_ctx = CivicIssueContext(
            category=issue_category,
            raw_text=clean_raw_text or None,
            normalized_text=normalized_text,
        )

        # Check if any input evidence exists
        has_any_input = bool(effective_text or clean_raw_text or request.detection_result or request.before_image_path)
        if not has_any_input:
            warnings.append("Request contains neither text description nor visual detection evidence.")
            duration_ms = (time.perf_counter() - start_time) * 1000
            return MultimodalGatewayResponse(
                case_reference=request.case_reference,
                warnings=warnings,
                epistemic_state=EpistemicState.SYSTEM_DERIVED,
                processing_time_ms=round(duration_ms, 3),
                generated_at=datetime.now(timezone.utc),
            )

        ev_ref_id = None
        if request.before_image_path:
            ev_ref_id = request.before_image_path.replace("/", "_").replace("\\", "_").replace(".", "_")

        # 4. Build M9 MultimodalInput
        mm_input = MultimodalInput(
            request_id=f"req_{uuid4().hex[:12]}",
            text=effective_text or (clean_raw_text if clean_raw_text else None),
            language=request.language_hint,
            location_context=request.location_context,
            civic_issue_context=issue_ctx,
            cv_result=request.detection_result,
            evidence_reference_id=ev_ref_id,
            metadata=request.metadata,
        )

        # 5. M9.2 Cross-Modal Consistency & Ambiguity
        alignment = self._consistency_engine.evaluate_consistency(mm_input)
        ambiguity = self._consistency_engine.evaluate_ambiguity(mm_input, alignment)

        # 6. M9.3 Active Clarification
        clarification_res = self._clarification_resolver.resolve(mm_input, alignment, ambiguity)

        # 7. M9.5 Before/After Visual Resolution Audit (if requested)
        visual_audit_res = None
        has_resolution_evidence = bool(
            (request.before_image_path and request.after_image_path)
            or (request.before_detection and request.after_detection)
        )

        if has_resolution_evidence:
            audit_req = VisualResolutionAuditRequest(
                case_reference=request.case_reference or f"CASE-{uuid4().hex[:8].upper()}",
                issue_category=issue_category,
                before_image_path=request.before_image_path,
                after_image_path=request.after_image_path,
                before_detection_result=request.before_detection or request.detection_result,
                after_detection_result=request.after_detection,
                before_timestamp=request.before_timestamp,
                after_timestamp=request.after_timestamp,
            )
            visual_audit_res = self._visual_auditor.audit(audit_req)

            # Record visual audit in provenance and KG if case reference is present
            if request.case_reference and visual_audit_res:
                try:
                    ev_rec, kg_node = self._provenance_kg_integrator.integrate_visual_audit(
                        case_reference=request.case_reference,
                        result=visual_audit_res,
                    )
                    provenance_claims.append(ev_rec.evidence_id)
                    kg_node_keys.append(kg_node.canonical_key)
                except Exception as exc:
                    logger.warning("Failed to record visual audit in provenance/KG: %s", exc)
                    warnings.append(f"Visual audit KG recording warning: {str(exc)}")

        # 8. Check for warnings
        if not clean_raw_text and not request.detection_result:
            warnings.append("Request contains neither text description nor visual detection evidence.")
        if alignment.state == AlignmentState.CONFLICTING and request.detection_result and clean_raw_text:
            warnings.append("Severe cross-modal divergence detected between citizen text and visual detection.")

        duration_ms = (time.perf_counter() - start_time) * 1000

        return MultimodalGatewayResponse(
            case_reference=request.case_reference,
            normalized_text=normalized_text,
            vernacular_result=vernacular_result,
            detection_result=request.detection_result,
            alignment_assessment=alignment,
            ambiguity_assessment=ambiguity,
            clarification_result=clarification_res,
            visual_audit_result=visual_audit_res,
            provenance_claims=list(set(provenance_claims)),
            kg_node_keys=list(set(kg_node_keys)),
            epistemic_state=EpistemicState.SYSTEM_DERIVED,
            warnings=warnings,
            processing_time_ms=round(duration_ms, 3),
            generated_at=datetime.now(timezone.utc),
        )


multimodal_gateway_service = MultimodalGatewayService()


def get_multimodal_gateway_service() -> MultimodalGatewayService:
    """Returns the singleton instance of MultimodalGatewayService."""
    return multimodal_gateway_service
