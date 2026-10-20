"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.5: Before/After Visual Resolution Auditor

Performs deterministic, model-independent comparison of before-and-after visual
evidence to determine whether a previously observed civic defect persists or is not observed.

CRITICAL EPISTEMIC PRINCIPLE:
Visual comparison produces an EVIDENCE SIGNAL, NOT PHYSICAL GROUND TRUTH.
- DEFECT_NOT_OBSERVED denotes the defect was not observed in the available after-image;
  it does NOT confirm the repair is physically complete.
- DEFECT_PERSISTS denotes visual evidence remains consistent with the defect;
  it does NOT assert government repair failure.
- Never outputs REPAIR_CONFIRMED or FULLY_FIXED.
- Epistemic state is strictly SYSTEM_DERIVED or MODEL_OBSERVATION.
"""

from datetime import datetime, timezone
import logging
import math
from typing import Any, Optional

from app.services.cv.base_provider import StandardDetectionResult
from app.services.multimodal.contracts import (
    ConsistencyAssessmentState,
    EpistemicState,
    EvidenceQuality,
    IssueCategory,
    MultimodalLocationContext,
    ResolutionAuditOutcome,
    VisualResolutionAuditRequest,
    VisualResolutionAuditResult,
)

logger = logging.getLogger("cvki.services.multimodal.visual_audit")

DEFAULT_AUDIT_THRESHOLD = 0.25
MAX_CONSISTENT_DISTANCE_METERS = 100.0


def _haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class VisualResolutionAuditor:
    """
    Model-independent Before/After Visual Resolution Auditor (M9.5).
    Operates strictly on StandardDetectionResult contracts without direct torch/ultralytics imports.
    """

    def __init__(self, default_threshold: float = DEFAULT_AUDIT_THRESHOLD):
        self._default_threshold = default_threshold

    def audit(self, request: VisualResolutionAuditRequest) -> VisualResolutionAuditResult:
        """
        Executes before/after visual resolution comparison.
        Returns a strictly bounded VisualResolutionAuditResult.
        """
        threshold = request.requested_threshold or self._default_threshold
        limitations: list[str] = [
            "Visual audit is an evidence observation signal and does not establish physical ground truth.",
            "Defect non-observation in after-image does not guarantee complete structural repair.",
        ]

        # Step 1: Evidence Existence & Completeness
        if not request.before_detection_result or not request.after_detection_result:
            missing_modality = "before" if not request.before_detection_result else "after"
            return VisualResolutionAuditResult(
                outcome=ResolutionAuditOutcome.INSUFFICIENT_EVIDENCE,
                issue_category=request.issue_category or IssueCategory.UNKNOWN,
                evidence_quality=EvidenceQuality.INSUFFICIENT,
                temporal_consistency=ConsistencyAssessmentState.UNKNOWN,
                spatial_consistency=ConsistencyAssessmentState.UNKNOWN,
                explanation=f"Insufficient visual evidence: missing {missing_modality} detection evidence result.",
                limitations=limitations,
                epistemic_state=EpistemicState.SYSTEM_DERIVED,
                model_metadata={"threshold": threshold, "missing": missing_modality},
            )

        # Step 2: Quality Metadata Verification
        before_meta = request.before_image_metadata or {}
        after_meta = request.after_image_metadata or {}

        if before_meta.get("corrupt") or after_meta.get("corrupt") or \
           before_meta.get("quality") in {"unreadable", "incomplete"} or \
           after_meta.get("quality") in {"unreadable", "incomplete"}:
            return VisualResolutionAuditResult(
                outcome=ResolutionAuditOutcome.INSUFFICIENT_EVIDENCE,
                issue_category=request.issue_category or IssueCategory.UNKNOWN,
                evidence_quality=EvidenceQuality.DEGRADED,
                temporal_consistency=ConsistencyAssessmentState.UNKNOWN,
                spatial_consistency=ConsistencyAssessmentState.UNKNOWN,
                explanation="Visual evidence quality is degraded or unreadable; cannot conduct reliable comparison.",
                limitations=limitations,
                epistemic_state=EpistemicState.SYSTEM_DERIVED,
                model_metadata={"threshold": threshold, "evidence_quality": "degraded"},
            )

        # Step 3: Temporal Consistency Verification
        temporal_state = ConsistencyAssessmentState.UNKNOWN
        if request.before_timestamp and request.after_timestamp:
            if request.after_timestamp <= request.before_timestamp:
                temporal_state = ConsistencyAssessmentState.INCONSISTENT
                return VisualResolutionAuditResult(
                    outcome=ResolutionAuditOutcome.INCONCLUSIVE,
                    issue_category=request.issue_category or IssueCategory.UNKNOWN,
                    evidence_quality=EvidenceQuality.SUFFICIENT,
                    temporal_consistency=temporal_state,
                    spatial_consistency=ConsistencyAssessmentState.UNKNOWN,
                    explanation=(
                        f"Chronological anomaly: after-image timestamp ({request.after_timestamp.isoformat()}) "
                        f"is not strictly later than before-image timestamp ({request.before_timestamp.isoformat()})."
                    ),
                    limitations=limitations,
                    epistemic_state=EpistemicState.SYSTEM_DERIVED,
                    model_metadata={"threshold": threshold, "temporal_check": "failed"},
                )
            else:
                temporal_state = ConsistencyAssessmentState.CONSISTENT

        # Step 4: Spatial Consistency Verification
        spatial_state = ConsistencyAssessmentState.UNKNOWN
        if request.before_location and request.after_location and \
           request.before_location.latitude is not None and request.before_location.longitude is not None and \
           request.after_location.latitude is not None and request.after_location.longitude is not None:
            distance = _haversine_distance_meters(
                request.before_location.latitude,
                request.before_location.longitude,
                request.after_location.latitude,
                request.after_location.longitude,
            )
            if distance <= MAX_CONSISTENT_DISTANCE_METERS:
                spatial_state = ConsistencyAssessmentState.CONSISTENT
            else:
                spatial_state = ConsistencyAssessmentState.INCONSISTENT
                return VisualResolutionAuditResult(
                    outcome=ResolutionAuditOutcome.INCONCLUSIVE,
                    issue_category=request.issue_category or IssueCategory.UNKNOWN,
                    evidence_quality=EvidenceQuality.SUFFICIENT,
                    temporal_consistency=temporal_state,
                    spatial_consistency=spatial_state,
                    explanation=(
                        f"Spatial inconsistency: before and after images were captured at different locations "
                        f"({distance:.1f}m apart, exceeding allowed {MAX_CONSISTENT_DISTANCE_METERS}m tolerance)."
                    ),
                    limitations=limitations,
                    epistemic_state=EpistemicState.SYSTEM_DERIVED,
                    model_metadata={"threshold": threshold, "distance_meters": distance},
                )

        # Step 5: Extract Before and After Detections
        cat_map = {
            "open_damaged_manhole": IssueCategory.OPEN_DAMAGED_MANHOLE,
            "damaged_missing_road_sign": IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
            "road_waterlogging": IssueCategory.ROAD_WATERLOGGING,
        }

        before_dets = request.before_detection_result.detections or []
        after_dets = request.after_detection_result.detections or []

        # Find confident before detections
        confident_before = [d for d in before_dets if d.confidence >= threshold]
        if not confident_before:
            return VisualResolutionAuditResult(
                outcome=ResolutionAuditOutcome.INSUFFICIENT_EVIDENCE,
                issue_category=request.issue_category or IssueCategory.UNKNOWN,
                evidence_quality=EvidenceQuality.INSUFFICIENT,
                temporal_consistency=temporal_state,
                spatial_consistency=spatial_state,
                explanation="No confident civic defect detections observed in before evidence to baseline resolution audit.",
                limitations=limitations,
                epistemic_state=EpistemicState.SYSTEM_DERIVED,
                model_metadata={"threshold": threshold, "before_detections_count": len(before_dets)},
            )

        # Determine target category
        if request.issue_category:
            target_cat = request.issue_category
        else:
            top_before = sorted(confident_before, key=lambda d: d.confidence, reverse=True)[0]
            target_cat = cat_map.get(top_before.class_name, IssueCategory.OTHER_CIVIC_ISSUE)

        # Filter after detections matching target category
        target_class_name = target_cat.value
        after_target_confident = [
            d for d in after_dets
            if cat_map.get(d.class_name, IssueCategory.OTHER_CIVIC_ISSUE) == target_cat and d.confidence >= threshold
        ]
        after_target_marginal = [
            d for d in after_dets
            if cat_map.get(d.class_name, IssueCategory.OTHER_CIVIC_ISSUE) == target_cat and d.confidence < threshold
        ]
        after_other_confident = [
            d for d in after_dets
            if cat_map.get(d.class_name, IssueCategory.OTHER_CIVIC_ISSUE) != target_cat and d.confidence >= threshold
        ]

        before_obs_summary = f"{target_cat.value} detected with confidence {confident_before[0].confidence:.2f}"

        # Scenario A: Defect Persists (same target category observed in after image above threshold)
        if after_target_confident:
            top_after = sorted(after_target_confident, key=lambda d: d.confidence, reverse=True)[0]
            after_obs_summary = f"{target_cat.value} detected with confidence {top_after.confidence:.2f}"
            return VisualResolutionAuditResult(
                outcome=ResolutionAuditOutcome.DEFECT_PERSISTS,
                issue_category=target_cat,
                before_observation=before_obs_summary,
                after_observation=after_obs_summary,
                evidence_quality=EvidenceQuality.SUFFICIENT,
                temporal_consistency=temporal_state,
                spatial_consistency=spatial_state,
                explanation=(
                    f"Visual defect persists: {target_cat.value} was observed in both before "
                    f"and after visual evidence with confidence >= {threshold:.2f}."
                ),
                limitations=limitations,
                epistemic_state=EpistemicState.SYSTEM_DERIVED,
                model_metadata={
                    "threshold": threshold,
                    "before_confidence": confident_before[0].confidence,
                    "after_confidence": top_after.confidence,
                },
            )

        # Scenario B: Marginal or Inconclusive Detection in After Evidence
        if after_target_marginal:
            top_marginal = sorted(after_target_marginal, key=lambda d: d.confidence, reverse=True)[0]
            after_obs_summary = f"{target_cat.value} observed marginally (confidence {top_marginal.confidence:.2f} < {threshold:.2f})"
            return VisualResolutionAuditResult(
                outcome=ResolutionAuditOutcome.INCONCLUSIVE,
                issue_category=target_cat,
                before_observation=before_obs_summary,
                after_observation=after_obs_summary,
                evidence_quality=EvidenceQuality.DEGRADED,
                temporal_consistency=temporal_state,
                spatial_consistency=spatial_state,
                explanation=(
                    f"Inconclusive visual evidence: after-image contains weak observation of {target_cat.value} "
                    f"(confidence {top_marginal.confidence:.2f}) below evidence threshold {threshold:.2f}."
                ),
                limitations=limitations,
                epistemic_state=EpistemicState.SYSTEM_DERIVED,
                model_metadata={
                    "threshold": threshold,
                    "marginal_confidence": top_marginal.confidence,
                },
            )

        # Scenario C: Confident Different Defect in After Evidence
        if after_other_confident:
            other_cat = cat_map.get(after_other_confident[0].class_name, IssueCategory.OTHER_CIVIC_ISSUE)
            after_obs_summary = f"Different defect observed: {other_cat.value} (confidence {after_other_confident[0].confidence:.2f})"
            return VisualResolutionAuditResult(
                outcome=ResolutionAuditOutcome.INCONCLUSIVE,
                issue_category=target_cat,
                before_observation=before_obs_summary,
                after_observation=after_obs_summary,
                evidence_quality=EvidenceQuality.SUFFICIENT,
                temporal_consistency=temporal_state,
                spatial_consistency=spatial_state,
                explanation=(
                    f"After evidence shows a different issue category ({other_cat.value}); "
                    f"the original {target_cat.value} defect cannot be treated as visually verified as resolved."
                ),
                limitations=limitations,
                epistemic_state=EpistemicState.SYSTEM_DERIVED,
                model_metadata={
                    "threshold": threshold,
                    "observed_other_category": other_cat.value,
                },
            )

        # Scenario D: Defect Not Observed (no detection of target defect in after evidence)
        after_obs_summary = f"No detections of {target_cat.value} observed in after-image"
        return VisualResolutionAuditResult(
            outcome=ResolutionAuditOutcome.DEFECT_NOT_OBSERVED,
            issue_category=target_cat,
            before_observation=before_obs_summary,
            after_observation=after_obs_summary,
            evidence_quality=EvidenceQuality.SUFFICIENT,
            temporal_consistency=temporal_state,
            spatial_consistency=spatial_state,
            explanation=(
                f"Visual evidence indicates {target_cat.value} was not observed in the available after-image. "
                f"Epistemic note: defect non-observation does not constitute physical proof of structural repair."
            ),
            limitations=limitations,
            epistemic_state=EpistemicState.SYSTEM_DERIVED,
            model_metadata={
                "threshold": threshold,
                "after_detections_count": 0,
            },
        )


# Shared singleton instance
visual_resolution_auditor = VisualResolutionAuditor()
