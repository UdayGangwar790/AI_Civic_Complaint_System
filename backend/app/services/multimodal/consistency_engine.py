"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.2: Cross-Modal Evidence Consistency & Grounding Engine

Evaluates whether citizen-reported civic issue information is consistent with available
computer vision evidence. Operates as a deterministic, bounded, explainable rule engine.

CRITICAL EPISTEMIC PRINCIPLE:
Evaluates consistency among available evidence signals. Does NOT establish physical ground truth.
Never infers causality (e.g. does not infer "manhole caused waterlogging").
"""

from datetime import datetime, timezone
import logging
import re
import time
from typing import Any, Optional

from app.services.cv.base_provider import StandardDetectionResult
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

logger = logging.getLogger("cvki.services.multimodal.consistency")

# =============================================================================
# Deterministic Evidence Thresholds
# =============================================================================
# Chosen in alignment with M1.13 and M8 default confidence configuration
DEFAULT_EVIDENCE_THRESHOLD = 0.25
HIGH_EVIDENCE_THRESHOLD = 0.50

# =============================================================================
# Lexicon for Deterministic Issue Category Mapping
# =============================================================================
_MANHOLE_TERMS = {
    "manhole", "drain cover", "open lid", "gutter", "sewer", "sewage", "pit",
    "chamber", "inspection chamber", "drainage lid", "storm drain",
    "गटर", "मैनहोल", "नाली का ढक्कन", "खुला ढक्कन", "सीवर", "चैंबर", "गड्ढा",
    "naali", "nali", "khula manhole", "dhakkan", "open manhole",
}

_ROADSIGN_TERMS = {
    "road sign", "traffic sign", "signboard", "sign board", "direction board",
    "broken sign", "missing sign", "speed limit sign", "street sign", "symbol board",
    "रोड साइन", "साइनबोर्ड", "यातायात संकेत", "दिशा बोर्ड", "टूटा साइन",
    "toota sign", "board gayab", "board gir gaya",
}

_WATERLOGGING_TERMS = {
    "waterlogging", "water logging", "water stagnation", "flooding", "waterlogged",
    "stagnant water", "puddle", "drainage blockage", "water accumulated", "rainwater",
    "जलभराव", "पानी भरा", "बाढ़", "सड़क पर पानी", "नाली जाम", "कीचड़", "पानी जमा",
    "paani bhara", "pani bhara", "pani jama", "water jam", "road pe pani",
}

# Negation words: English, Hindi, Hinglish (excludes 'without'/'bina' which describe missing components like 'without lid')
_NEGATION_WORDS = {
    "no", "not", "neither", "nor", "never",
    "nahi", "nahin", "nhi", "na",
}


def _extract_words(text: str) -> list[str]:
    """Tokenizes text into lowercase alphanumeric words."""
    return re.findall(r"\b\w+\b", text.lower())


def _check_negation_proximity(text: str, target_phrase: str, window_words: int = 3) -> bool:
    """
    Checks if a target category term is directly preceded by a negation particle
    within a bounded window of words.
    """
    words = _extract_words(text)
    phrase_tokens = _extract_words(target_phrase)
    if not phrase_tokens:
        return False

    phrase_len = len(phrase_tokens)
    for i in range(len(words) - phrase_len + 1):
        if words[i:i + phrase_len] == phrase_tokens:
            start_window = max(0, i - window_words)
            preceding_words = words[start_window:i]
            if any(w in _NEGATION_WORDS for w in preceding_words):
                return True
    return False


class CrossModalConsistencyEngine:
    """
    Deterministic cross-modal evidence consistency and grounding engine.
    Compares citizen text claims against M8 computer vision detections.
    """

    def __init__(
        self,
        evidence_threshold: float = DEFAULT_EVIDENCE_THRESHOLD,
    ):
        self._evidence_threshold = evidence_threshold

    @property
    def evidence_threshold(self) -> float:
        return self._evidence_threshold

    def extract_reported_categories(
        self,
        text: Optional[str],
        issue_context_class: Optional[str] = None,
    ) -> tuple[set[IssueCategory], set[IssueCategory]]:
        """
        Extracts positive and negated issue categories from citizen text and context.
        Returns (positive_categories, negated_categories).
        """
        positive: set[IssueCategory] = set()
        negated: set[IssueCategory] = set()

        if text:
            text_lower = text.lower()

            # 1. Check manhole
            for term in _MANHOLE_TERMS:
                if term in text_lower:
                    if _check_negation_proximity(text_lower, term):
                        negated.add(IssueCategory.OPEN_DAMAGED_MANHOLE)
                    else:
                        positive.add(IssueCategory.OPEN_DAMAGED_MANHOLE)

            # 2. Check road sign
            for term in _ROADSIGN_TERMS:
                if term in text_lower:
                    if _check_negation_proximity(text_lower, term):
                        negated.add(IssueCategory.DAMAGED_MISSING_ROAD_SIGN)
                    else:
                        positive.add(IssueCategory.DAMAGED_MISSING_ROAD_SIGN)

            # 3. Check waterlogging
            for term in _WATERLOGGING_TERMS:
                if term in text_lower:
                    if _check_negation_proximity(text_lower, term):
                        negated.add(IssueCategory.ROAD_WATERLOGGING)
                    else:
                        positive.add(IssueCategory.ROAD_WATERLOGGING)

        # 4. Integrate structured civic context if text was empty or didn't match
        if issue_context_class:
            class_clean = issue_context_class.strip().lower()
            context_mapping = {
                "open_damaged_manhole": IssueCategory.OPEN_DAMAGED_MANHOLE,
                "damaged_missing_road_sign": IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
                "road_waterlogging": IssueCategory.ROAD_WATERLOGGING,
            }
            if class_clean in context_mapping:
                cat = context_mapping[class_clean]
                if cat not in negated:
                    positive.add(cat)

        # If an issue is both negated and positive, negation takes precedence
        for n in negated:
            positive.discard(n)

        return positive, negated

    def extract_cv_evidence(
        self,
        cv_result: Optional[StandardDetectionResult],
    ) -> dict[IssueCategory, float]:
        """
        Extracts verified defect categories from StandardDetectionResult meeting the threshold.
        Returns a mapping of IssueCategory -> maximum confidence score.
        """
        if cv_result is None or not cv_result.success or not cv_result.detections:
            return {}

        cat_mapping = {
            "open_damaged_manhole": IssueCategory.OPEN_DAMAGED_MANHOLE,
            "damaged_missing_road_sign": IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
            "road_waterlogging": IssueCategory.ROAD_WATERLOGGING,
        }

        evidence: dict[IssueCategory, float] = {}
        for det in cv_result.detections:
            if det.confidence >= self._evidence_threshold:
                cat = cat_mapping.get(det.class_name, IssueCategory.OTHER_CIVIC_ISSUE)
                if cat not in evidence or det.confidence > evidence[cat]:
                    evidence[cat] = det.confidence

        return evidence

    def evaluate_consistency(
        self,
        input_data: MultimodalInput,
    ) -> EvidenceAlignmentAssessment:
        """
        Evaluates cross-modal evidence alignment between citizen input and CV evidence.
        Produces a strictly bounded EvidenceAlignmentAssessment.
        """
        # Step 1: Extract citizen reported categories and negations
        context_class = (
            input_data.civic_issue_context.reported_class
            if input_data.civic_issue_context
            else None
        )
        reported_cats, negated_cats = self.extract_reported_categories(
            input_data.text,
            issue_context_class=context_class,
        )

        # Step 2: Extract computer vision evidence
        cv_evidence = self.extract_cv_evidence(input_data.cv_result)

        # Check if CV had detections that were filtered out by threshold
        raw_detections_exist = (
            input_data.cv_result is not None
            and bool(input_data.cv_result.detections)
        )

        # Scenario 1: Negation conflict
        # Citizen explicitly negated an issue category, but CV detected it
        negated_conflicts = [cat for cat in negated_cats if cat in cv_evidence]
        if negated_conflicts:
            conflicted_cat = negated_conflicts[0]
            conf_val = cv_evidence[conflicted_cat]
            return EvidenceAlignmentAssessment(
                state=AlignmentState.CONFLICTING,
                matched_issue_category=None,
                conflicting_fields=["negated_issue_category"],
                supporting_evidence=[],
                missing_evidence=[],
                explanation=(
                    f"Citizen text contains a negative statement regarding {conflicted_cat.value} "
                    f"while available CV evidence indicates the presence of this issue category "
                    f"(confidence: {conf_val:.2f})."
                ),
            )

        # Scenario 2: Insufficient evidence
        # Case 2a: No reported categories recognized from text or context
        if not reported_cats:
            return EvidenceAlignmentAssessment(
                state=AlignmentState.INSUFFICIENT_EVIDENCE,
                matched_issue_category=None,
                conflicting_fields=[],
                supporting_evidence=[],
                missing_evidence=[],
                explanation=(
                    "Available evidence is insufficient to evaluate consistency: citizen text "
                    "does not identify a recognized civic issue category (no recognized civic issue category was found)."
                ),
            )

        # Case 2b: Reported categories exist, but no CV evidence exists
        if not cv_evidence:
            if raw_detections_exist:
                exp = (
                    f"Available CV detection evidence is below the required evidence strength "
                    f"threshold ({self._evidence_threshold:.2f}) to evaluate alignment with citizen report."
                )
            else:
                exp = (
                    "Available evidence is insufficient to compare with citizen claims: "
                    "no computer vision detection evidence was provided."
                )
            return EvidenceAlignmentAssessment(
                state=AlignmentState.INSUFFICIENT_EVIDENCE,
                matched_issue_category=None,
                conflicting_fields=[],
                supporting_evidence=[],
                missing_evidence=[f"cv_detection:{cat.value}" for cat in sorted(reported_cats, key=lambda c: c.value)],
                explanation=exp,
            )

        # Step 3: Compare positive reported categories with CV evidence
        detected_cats = set(cv_evidence.keys())
        supported_cats = reported_cats.intersection(detected_cats)
        unsupported_cats = reported_cats.difference(detected_cats)

        # Case 3a: Exact full match of all reported categories
        if supported_cats and not unsupported_cats:
            primary_cat = sorted(supported_cats, key=lambda c: cv_evidence[c], reverse=True)[0]
            supporting_list = [
                f"cv_detection:{cat.value} (confidence: {cv_evidence[cat]:.2f})"
                for cat in sorted(supported_cats, key=lambda c: c.value)
            ]
            return EvidenceAlignmentAssessment(
                state=AlignmentState.ALIGNED,
                matched_issue_category=primary_cat,
                conflicting_fields=[],
                supporting_evidence=supporting_list,
                missing_evidence=[],
                explanation="Citizen-reported issue category matches the available CV detection evidence.",
            )

        # Case 3b: Partial match (some reported categories detected, some missing)
        if supported_cats and unsupported_cats:
            primary_cat = sorted(supported_cats, key=lambda c: cv_evidence[c], reverse=True)[0]
            supporting_list = [
                f"cv_detection:{cat.value} (confidence: {cv_evidence[cat]:.2f})"
                for cat in sorted(supported_cats, key=lambda c: c.value)
            ]
            missing_list = [
                f"cv_detection:{cat.value}"
                for cat in sorted(unsupported_cats, key=lambda c: c.value)
            ]
            sup_names = ", ".join(cat.value for cat in sorted(supported_cats, key=lambda c: c.value))
            unsup_names = ", ".join(cat.value for cat in sorted(unsupported_cats, key=lambda c: c.value))
            return EvidenceAlignmentAssessment(
                state=AlignmentState.PARTIALLY_ALIGNED,
                matched_issue_category=primary_cat,
                conflicting_fields=["missing_issue_category"],
                supporting_evidence=supporting_list,
                missing_evidence=missing_list,
                explanation=(
                    f"CV evidence supports {sup_names}, but the additional reported {unsup_names} "
                    f"issue was not observed."
                ),
            )

        # Case 3c: Complete conflict (none of the reported categories were detected, but other categories were)
        if not supported_cats and detected_cats:
            rep_names = ", ".join(cat.value for cat in sorted(reported_cats, key=lambda c: c.value))
            obs_names = ", ".join(cat.value for cat in sorted(detected_cats, key=lambda c: c.value))
            return EvidenceAlignmentAssessment(
                state=AlignmentState.CONFLICTING,
                matched_issue_category=None,
                conflicting_fields=["issue_category"],
                supporting_evidence=[],
                missing_evidence=[f"cv_detection:{cat.value}" for cat in sorted(reported_cats, key=lambda c: c.value)],
                explanation=(
                    f"Citizen text reports {rep_names}, while the available CV evidence "
                    f"indicates {obs_names} instead."
                ),
            )

        # Fallback conservative state
        return EvidenceAlignmentAssessment(
            state=AlignmentState.INSUFFICIENT_EVIDENCE,
            matched_issue_category=None,
            conflicting_fields=[],
            supporting_evidence=[],
            missing_evidence=[],
            explanation="Evidence signals were inconclusive to determine cross-modal alignment.",
        )

    def evaluate_ambiguity(
        self,
        input_data: MultimodalInput,
        alignment: EvidenceAlignmentAssessment,
    ) -> AmbiguityAssessment:
        """
        Derives an AmbiguityAssessment strictly from the cross-modal alignment state.
        Does NOT implement interactive citizen interrogation (which belongs to M9.3).
        """
        if alignment.state == AlignmentState.CONFLICTING:
            return AmbiguityAssessment(
                state=AmbiguityState.CONFLICTING_EVIDENCE,
                reasons=[
                    "Cross-modal evidence conflict between citizen statement and computer vision observations."
                ],
                missing_information=["reconciled_issue_category"],
                requires_clarification=True,
            )
        elif alignment.state == AlignmentState.PARTIALLY_ALIGNED:
            return AmbiguityAssessment(
                state=AmbiguityState.AMBIGUOUS,
                reasons=[
                    "Some citizen-reported issue components lack corresponding computer vision evidence."
                ],
                missing_information=alignment.missing_evidence,
                requires_clarification=True,
            )
        elif alignment.state == AlignmentState.INSUFFICIENT_EVIDENCE:
            return AmbiguityAssessment(
                state=AmbiguityState.INSUFFICIENT_EVIDENCE,
                reasons=[
                    "Available evidence is insufficient to verify consistency across modalities."
                ],
                missing_information=["corroborating_visual_or_textual_evidence"],
                requires_clarification=False,
            )
        elif alignment.state == AlignmentState.ALIGNED:
            return AmbiguityAssessment(
                state=AmbiguityState.CLEAR,
                reasons=[],
                missing_information=[],
                requires_clarification=False,
            )
        else:
            return AmbiguityAssessment(
                state=AmbiguityState.NOT_EVALUATED,
                reasons=[],
                missing_information=[],
                requires_clarification=False,
            )

    def analyze(self, input_data: MultimodalInput) -> StandardMultimodalResult:
        """
        Executes complete M9.2 cross-modal evaluation and returns a populated StandardMultimodalResult.
        """
        started_at = time.perf_counter()

        # Sanitize text
        clean_text = sanitize_text_pii(input_data.text) if input_data.text else ""

        # Step 1: Evaluate evidence alignment
        alignment = self.evaluate_consistency(input_data)

        # Step 2: Evaluate ambiguity
        ambiguity = self.evaluate_ambiguity(input_data, alignment)

        # Step 3: Determine primary issue category
        issue_cat = alignment.matched_issue_category or IssueCategory.UNKNOWN
        if issue_cat == IssueCategory.UNKNOWN:
            reported_cats, _ = self.extract_reported_categories(
                input_data.text,
                issue_context_class=input_data.civic_issue_context.reported_class if input_data.civic_issue_context else None,
            )
            if reported_cats:
                issue_cat = sorted(reported_cats, key=lambda c: c.value)[0]

        # Extract entities from location context
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

        return StandardMultimodalResult(
            success=True,
            provider_id="consistency_engine",
            model_id="m9.2-rule-grounding-engine",
            model_version="0.2.0-deterministic",
            model_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            task=MultimodalTaskType.CROSS_MODAL_VERIFICATION,
            processing_time_ms=round(duration_ms, 2),
            timestamp=datetime.now(timezone.utc),
            language=input_data.language or "en",
            normalized_intent=CivicIntent.REPORT_ISSUE,
            issue_category=issue_cat,
            extracted_entities=entities,
            ambiguity_assessment=ambiguity,
            evidence_alignment=alignment,
            suggested_clarifications=[],
            explanation=alignment.explanation,
            epistemic_state=EpistemicState.MODEL_OBSERVATION,
            metadata={
                "engine": "cross_modal_consistency_engine",
                "evidence_threshold": self._evidence_threshold,
                "text_length": len(clean_text),
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
            },
        )


# Shared singleton instance
cross_modal_consistency_engine = CrossModalConsistencyEngine()
