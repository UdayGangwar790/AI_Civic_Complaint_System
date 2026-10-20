"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.4: Evidence-Aware Decision Support Engine
"""

from datetime import datetime, timezone
import logging
from typing import Optional
from uuid import uuid4

from app.schemas.action_playbook import PlaybookActionItem
from app.schemas.decision_support import (
    DecisionContext,
    DecisionEvidenceQuality,
    DecisionSupportResult,
)
from app.services.action_playbook import get_action_playbook_registry
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.cv.base_provider import StandardDetectionResult

logger = logging.getLogger("cvki.decision_support")


def _get_primary_detection(detection_result: Optional[StandardDetectionResult]):
    if not detection_result or not detection_result.detections:
        return None
    return max(detection_result.detections, key=lambda d: d.confidence)


class CivicDecisionSupportEngine:
    """
    Central operational decision support engine for CVKI.
    Synthesizes M1–M9 evidence into explainable, structured action playbooks.
    Adheres strictly to epistemic safety invariants:
    - Never declares physical ground truth.
    - Never automatically resolves, closes, or escalates complaints.
    - Operates purely as decision support for authorized human reviewers.
    """

    def __init__(self):
        self._playbook_registry = get_action_playbook_registry()

    def evaluate_case(self, context: DecisionContext) -> DecisionSupportResult:
        """
        Evaluates the multimodal and operational context of a complaint case,
        matching relevant response playbooks and generating explainable triage recommendations.
        """
        # 1. Evaluate Evidence Quality
        evidence_quality, quality_reasons = self._assess_evidence_quality(context)

        # 2. Match Active Playbooks
        has_cv = bool(
            context.detection_result
            and context.detection_result.detections
            and len(context.detection_result.detections) > 0
        )
        has_rain = bool(
            context.weather_condition
            and any(term in context.weather_condition.lower() for term in ("rain", "flood", "shower", "storm"))
        )

        matched_results = self._playbook_registry.match_playbooks(
            issue_category=context.issue_category,
            has_cv_detection=has_cv,
            priority_level=context.priority_level,
            is_recurrent=context.is_recurrent,
            has_rain_context=has_rain,
            alignment_score=context.alignment_score,
        )

        matched_playbook_ids: list[str] = []
        recommended_actions: list[PlaybookActionItem] = []
        mitigation_actions: list[PlaybookActionItem] = []
        required_inspection: list[str] = []
        required_evidence: list[str] = []
        missing_evidence: list[str] = []
        uncertainties: list[str] = []
        human_review_reasons: list[str] = list(quality_reasons)

        # Consolidate actions and checkpoints across matched playbooks
        seen_action_ids: set[str] = set()

        for match in matched_results:
            matched_playbook_ids.append(f"{match.playbook_id} (v{match.playbook_version})")

            for action in match.recommended_actions:
                if action.action_id not in seen_action_ids:
                    seen_action_ids.add(action.action_id)
                    recommended_actions.append(action)

            for action in match.mitigation_actions:
                if action.action_id not in seen_action_ids:
                    seen_action_ids.add(action.action_id)
                    mitigation_actions.append(action)

            for cp in match.inspection_checkpoints:
                if cp not in required_inspection:
                    required_inspection.append(cp)

            for me in match.missing_evidence:
                if me not in missing_evidence:
                    missing_evidence.append(me)

            for assumption in match.prohibited_assumptions:
                if assumption not in uncertainties:
                    uncertainties.append(f"Prohibited Assumption: {assumption}")

        # 3. Contextual Evidence Rationale & Contributions
        supporting_evidence: list[dict] = []
        explanation_lines: list[str] = []

        explanation_lines.append(f"### Operational Decision Support Summary for Issue Category: {context.issue_category.value}")
        explanation_lines.append(f"- **Evidence Quality**: {evidence_quality.value}")

        # CV Evidence
        if has_cv:
            primary_det = _get_primary_detection(context.detection_result)
            conf_str = f"{primary_det.confidence:.2f}" if primary_det else "N/A"
            class_str = primary_det.class_name if primary_det else "detected"
            explanation_lines.append(f"- **Computer Vision**: Observed '{class_str}' defect with confidence {conf_str} (Model: {context.detection_result.model_id}).")
            supporting_evidence.append({
                "source": "computer_vision",
                "class_name": class_str,
                "confidence": conf_str,
                "model_id": context.detection_result.model_id,
            })
        else:
            missing_evidence.append("photographic_cv_detection")
            uncertainties.append("Visual confirmation of defect is currently absent.")

        # Citizen Report & Vernacular Context
        if context.normalized_text or context.citizen_text:
            text_preview = (context.normalized_text or context.citizen_text)[:120]
            explanation_lines.append(f"- **Citizen Description**: \"{text_preview}...\" (Verified vernacular normalization applied).")
            supporting_evidence.append({
                "source": "citizen_report",
                "text_summary": text_preview,
            })

        # Consistency Context
        if context.alignment_score is not None:
            explanation_lines.append(f"- **Cross-Modal Consistency**: Alignment score evaluated at {context.alignment_score:.2f}.")
            if context.alignment_score < 0.4:
                human_review_reasons.append("Cross-modal divergence between text and visual evidence requires manual review.")
                uncertainties.append("Citizen textual description conflicts with computer vision detection.")

        if context.clarification_needed:
            human_review_reasons.append("Active ambiguity clarification question is pending citizen response.")
            uncertainties.append("Case has unresolved ambiguity requiring citizen clarification.")

        # Priority & Operational Urgency (NOT unverified emergency)
        if context.priority_level:
            explanation_lines.append(f"- **Priority Tier**: Assigned operational tier '{context.priority_level}' based on infrastructure risk calculation.")
            if context.priority_level in ("P1", "P2"):
                explanation_lines.append("  *(Note: P1/P2 indicates higher operational response priority; physical emergency must be independently verified by field inspection).*")

        # Recurrence & Hotspot Context
        if context.is_recurrent:
            explanation_lines.append(f"- **Historical Recurrence**: Historical records indicate repeated defect occurrences at this location (Count: {context.recurrence_count}).")
            supporting_evidence.append({
                "source": "recurrence_intelligence",
                "count": context.recurrence_count,
            })
            if "Perform structural sub-base drainage audit" not in required_inspection:
                required_inspection.append("Verify whether chronic defect indicates underlying sub-base or pipe structural failure.")

        # Environmental Weather Context
        if has_rain:
            explanation_lines.append(f"- **Environmental Context**: Recent rainfall / wet conditions noted ('{context.weather_condition}'). Recent precipitation may be relevant operational context (Note: causality not inferred).")
            supporting_evidence.append({
                "source": "weather_context",
                "condition": context.weather_condition,
            })

        # Authority Context
        if context.authority_name:
            auth_status = "Verified" if context.is_authority_verified else "Preliminary / Unverified"
            explanation_lines.append(f"- **Responsible Authority**: Mapped to '{context.authority_name}' ({auth_status}).")
            if not context.is_authority_verified:
                human_review_reasons.append("Jurisdictional authority mapping requires administrative verification.")
                uncertainties.append("Assigned authority jurisdiction has not been officially confirmed.")

        # Government Status Context
        if context.government_status:
            explanation_lines.append(f"- **Reported Government Status**: External portal reports status '{context.government_status}' (Official external claim; physical repair unconfirmed).")
            if context.government_status.upper() in ("RESOLVED", "CLOSED"):
                human_review_reasons.append("External government status marked as resolved requires independent verification before case closure.")

        # Visual Audit Context
        if context.visual_audit_outcome:
            explanation_lines.append(f"- **Visual Resolution Audit**: Before/after comparison yielded outcome '{context.visual_audit_outcome}'.")
            if context.visual_audit_outcome in ("EVIDENCE_INCONCLUSIVE", "DEFECT_PERSISTS"):
                human_review_reasons.append(f"Visual audit outcome '{context.visual_audit_outcome}' requires on-site human verification.")

        # Fallback if no playbooks matched
        if not matched_playbook_ids:
            explanation_lines.append("- **Playbook Matching**: No category-specific playbook satisfied trigger criteria. Generic inspection protocol assigned.")
            required_inspection.append("Conduct baseline physical site inspection to ascertain defect category.")

        # Epistemic Safety Invariant Check
        uncertainties.append("Operational recommendations represent CVKI algorithmic guidance and do not constitute an official municipal order.")

        # Mandatory human review if any reasons present or by default for operational action
        human_review_required = True
        if not human_review_reasons:
            human_review_reasons.append("Standard protocol: all CVKI decision support recommendations require human authorization prior to dispatch.")

        return DecisionSupportResult(
            recommendation_id=str(uuid4()),
            case_reference=context.case_reference,
            matched_playbooks=matched_playbook_ids,
            recommended_actions=recommended_actions,
            mitigation_actions=mitigation_actions,
            required_inspection=required_inspection,
            required_evidence=list(set(required_evidence)),
            supporting_evidence=supporting_evidence,
            missing_evidence=list(set(missing_evidence)),
            explanation="\n".join(explanation_lines),
            uncertainty=uncertainties,
            evidence_quality=evidence_quality,
            epistemic_state=EpistemicState.SYSTEM_DERIVED,
            human_review_required=human_review_required,
            human_review_reasons=human_review_reasons,
            decision_version="1.0.0",
            generated_at=datetime.now(timezone.utc),
            provenance_reference=(
                f"claim:decision_rec:{context.case_reference}" if context.case_reference else None
            ),
        )

    def _assess_evidence_quality(self, ctx: DecisionContext) -> tuple[DecisionEvidenceQuality, list[str]]:
        """
        Determines the evidence quality tier based on data completeness and consistency.
        """
        reasons: list[str] = []

        has_cv = bool(ctx.detection_result and ctx.detection_result.detections)
        has_text = bool(ctx.normalized_text or ctx.citizen_text)

        # 1. Conflicting
        if ctx.alignment_score is not None and ctx.alignment_score < 0.35 and has_cv and has_text:
            reasons.append("Severe cross-modal divergence between citizen statement and computer vision detection.")
            return DecisionEvidenceQuality.CONFLICTING, reasons

        # 2. Missing
        if not has_cv and not has_text:
            reasons.append("Both visual defect imagery and descriptive complaint text are absent.")
            return DecisionEvidenceQuality.MISSING, reasons

        # 3. Strong
        if has_cv and has_text:
            primary_det = _get_primary_detection(ctx.detection_result)
            conf = primary_det.confidence if primary_det else 0.0
            align = ctx.alignment_score if ctx.alignment_score is not None else 0.7
            if conf >= 0.5 and align >= 0.6:
                return DecisionEvidenceQuality.STRONG, reasons

        # 4. Weak
        if has_cv:
            primary_det = _get_primary_detection(ctx.detection_result)
            if primary_det and primary_det.confidence < 0.3:
                reasons.append("Computer vision detection confidence is below operational threshold (conf < 0.30).")
                return DecisionEvidenceQuality.WEAK, reasons

        # 5. Partial
        if has_cv and not has_text:
            reasons.append("Visual evidence present without accompanying citizen context.")
            return DecisionEvidenceQuality.PARTIAL, reasons
        if has_text and not has_cv:
            reasons.append("Citizen report present without visual defect confirmation.")
            return DecisionEvidenceQuality.PARTIAL, reasons

        return DecisionEvidenceQuality.PARTIAL, reasons


decision_support_engine = CivicDecisionSupportEngine()


def get_decision_support_engine() -> CivicDecisionSupportEngine:
    """Returns the singleton instance of CivicDecisionSupportEngine."""
    return decision_support_engine
