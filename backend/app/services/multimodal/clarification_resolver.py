"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.3: Active Clarification & Ambiguity Resolver

Implements a deterministic, explainable, non-leading clarification policy engine.
When citizen-provided information and available computer vision evidence are ambiguous,
incomplete, or conflicting, generates bounded clarification questions to resolve the
citizen's report ambiguity.

CRITICAL EPISTEMIC PRINCIPLE:
Resolves ambiguity in the citizen's report; does NOT establish or verify physical ground truth.
A status of 'RESOLVED' denotes clarification ambiguity is resolved, NOT that the civic defect
is physically verified or fixed. Citizen responses strictly retain epistemic state USER_REPORTED.
"""

from datetime import datetime, timezone
import hashlib
import logging
import re
import time
from typing import Any, Optional

from app.services.multimodal.contracts import (
    AlignmentState,
    AmbiguityAssessment,
    AmbiguityState,
    ClarificationAnswer,
    ClarificationAnswerType,
    ClarificationQuestion,
    ClarificationQuestionType,
    ClarificationResult,
    ClarificationStatus,
    EpistemicState,
    EvidenceAlignmentAssessment,
    IssueCategory,
    MultimodalInput,
)
from app.services.multimodal.consistency_engine import (
    cross_modal_consistency_engine,
)
from app.services.multimodal.security import sanitize_text_pii

logger = logging.getLogger("cvki.services.multimodal.clarification")

# =============================================================================
# Constants & Operational Limits
# =============================================================================
DEFAULT_MAX_QUESTIONS = 2
HARD_CAP_MAX_QUESTIONS = 3
MAX_FREE_TEXT_LENGTH = 500
MAX_OPTIONS_COUNT = 10

# Banned patterns for answer validation
_PATH_TRAVERSAL_PATTERN = re.compile(r"(\.\.|[a-zA-Z]:[\\/]|/etc/|/var/|/usr/|/bin/|\x00)")
_URL_SCHEME_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://")
_SENSITIVE_CREDENTIAL_TERMS = {
    "password", "secret", "bearer", "token", "jwt",
    "credential", "sessionid", "auth_token", "api_key",
}


# =============================================================================
# Localized Issue Category Labels (en, hi, hinglish)
# =============================================================================
_CATEGORY_LABELS: dict[str, dict[IssueCategory, str]] = {
    "en": {
        IssueCategory.OPEN_DAMAGED_MANHOLE: "Open/damaged manhole",
        IssueCategory.DAMAGED_MISSING_ROAD_SIGN: "Damaged/missing road sign",
        IssueCategory.ROAD_WATERLOGGING: "Road waterlogging",
        IssueCategory.OTHER_CIVIC_ISSUE: "Other civic issue",
        IssueCategory.UNKNOWN: "Unknown civic issue",
    },
    "hi": {
        IssueCategory.OPEN_DAMAGED_MANHOLE: "खुला/क्षतिग्रस्त मैनहोल",
        IssueCategory.DAMAGED_MISSING_ROAD_SIGN: "टूटा/गायब रोड साइन",
        IssueCategory.ROAD_WATERLOGGING: "सड़क पर जलभराव",
        IssueCategory.OTHER_CIVIC_ISSUE: "अन्य नागरिक समस्या",
        IssueCategory.UNKNOWN: "अज्ञात नागरिक समस्या",
    },
    "hinglish": {
        IssueCategory.OPEN_DAMAGED_MANHOLE: "Open/damaged manhole",
        IssueCategory.DAMAGED_MISSING_ROAD_SIGN: "Damaged/missing road sign",
        IssueCategory.ROAD_WATERLOGGING: "Road waterlogging",
        IssueCategory.OTHER_CIVIC_ISSUE: "Other civic issue",
        IssueCategory.UNKNOWN: "Unknown civic issue",
    },
}

_COMMON_OPTIONS: dict[str, dict[str, str]] = {
    "en": {
        "both": "Both",
        "something_else": "Something else",
        "only": "only",
    },
    "hi": {
        "both": "दोनों",
        "something_else": "कुछ और",
        "only": "केवल",
    },
    "hinglish": {
        "both": "Dono",
        "something_else": "Kuch aur",
        "only": "only",
    },
}


def _normalize_lang(language: Optional[str]) -> str:
    """Normalizes language code with safe fallback to English."""
    if not language:
        return "en"
    clean = language.strip().lower()
    if clean in {"hi", "hindi"}:
        return "hi"
    if clean in {"hinglish", "hi-en", "en-hi"}:
        return "hinglish"
    if clean in {"en", "english"}:
        return "en"
    # Safe fallback for unsupported language
    return "en"


def _category_display(cat: IssueCategory, lang: str) -> str:
    norm_lang = _normalize_lang(lang)
    labels = _CATEGORY_LABELS.get(norm_lang, _CATEGORY_LABELS["en"])
    return labels.get(cat, _CATEGORY_LABELS["en"].get(cat, cat.value))


# =============================================================================
# Active Clarification Policy Engine (M9.3)
# =============================================================================

class ActiveClarificationResolver:
    """
    Bounded, deterministic clarification policy engine.
    Consumes M9.2 cross-modal alignment and ambiguity assessments to generate
    targeted, neutral, non-leading clarification questions.
    """

    def __init__(
        self,
        default_max_questions: int = DEFAULT_MAX_QUESTIONS,
    ):
        self._default_max_questions = min(default_max_questions, HARD_CAP_MAX_QUESTIONS)

    # -------------------------------------------------------------------------
    # Answer Validation
    # -------------------------------------------------------------------------
    def validate_answer(
        self,
        answer: ClarificationAnswer,
        question: ClarificationQuestion,
    ) -> tuple[bool, Optional[str]]:
        """
        Validates citizen clarification response against the active question.
        Ensures options belong to the question, lengths are bounded,
        and no malicious or sensitive data (paths, URLs, credentials) is injected.

        Returns (is_valid, rejection_reason).
        """
        # 1. Question ID matching
        if answer.question_id != question.question_id:
            return False, f"Question ID mismatch: answer refers to '{answer.question_id}', expected '{question.question_id}'."

        # 2. Epistemic check (must be USER_REPORTED)
        if answer.epistemic_state != EpistemicState.USER_REPORTED:
            return False, "Invalid epistemic state: citizen responses cannot claim verified truth."

        # 3. Single choice validation
        if question.answer_type == ClarificationAnswerType.SINGLE_CHOICE:
            if not answer.selected_option:
                return False, "Single-choice answer requires a selected_option."
            if question.options and answer.selected_option not in question.options:
                return False, f"Selected option '{answer.selected_option}' is not among valid choices."

        # 4. Multi choice validation
        elif question.answer_type == ClarificationAnswerType.MULTI_CHOICE:
            if not answer.selected_options:
                return False, "Multi-choice answer requires at least one selected option in selected_options."
            if question.options:
                invalid_options = [opt for opt in answer.selected_options if opt not in question.options]
                if invalid_options:
                    return False, f"Selected options contain invalid choices: {invalid_options}."

        # 5. Free text validation
        text_to_check = answer.free_text or ""
        if question.answer_type == ClarificationAnswerType.FREE_TEXT:
            if question.required and not text_to_check.strip():
                return False, "Free-text response cannot be empty for required question."

        if text_to_check:
            if len(text_to_check) > MAX_FREE_TEXT_LENGTH:
                return False, f"Free text exceeds maximum allowed length of {MAX_FREE_TEXT_LENGTH} characters."

            # URL rejection
            if _URL_SCHEME_PATTERN.search(text_to_check):
                return False, "Free text cannot contain web URLs or network protocol links."

            # Credential / token keywords rejection
            lower_text = text_to_check.lower()
            for cred_term in _SENSITIVE_CREDENTIAL_TERMS:
                if cred_term in lower_text:
                    return False, f"Free text contains prohibited credential or sensitive keyword '{cred_term}'."

            # Path traversal rejection
            if _PATH_TRAVERSAL_PATTERN.search(text_to_check):
                return False, "Free text contains prohibited path traversal sequences."

        # Option text checks as well
        option_val = answer.selected_option or ""
        if option_val:
            if _URL_SCHEME_PATTERN.search(option_val):
                return False, "Selected option cannot contain web URLs."
            if _PATH_TRAVERSAL_PATTERN.search(option_val):
                return False, "Selected option contains prohibited path traversal sequences."

        return True, None


    # -------------------------------------------------------------------------
    # Deterministic Question ID Generation
    # -------------------------------------------------------------------------
    def _generate_question_id(self, target_field: str, q_type: ClarificationQuestionType, key_suffix: str = "") -> str:
        raw_key = f"clarify_{target_field}_{q_type.value}_{key_suffix}"
        short_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:8]
        return f"cq_{target_field}_{short_hash}"

    # -------------------------------------------------------------------------
    # Policy: Conflict Reconciliation Question
    # -------------------------------------------------------------------------
    def _create_conflict_question(
        self,
        reported_cats: set[IssueCategory],
        detected_cats: set[IssueCategory],
        lang: str,
    ) -> ClarificationQuestion:
        norm_lang = _normalize_lang(lang)
        opt_common = _COMMON_OPTIONS.get(norm_lang, _COMMON_OPTIONS["en"])

        # Determine primary citizen category and CV category
        rep_list = sorted(reported_cats, key=lambda c: c.value)
        det_list = sorted(detected_cats, key=lambda c: c.value)

        rep_name = _category_display(rep_list[0], norm_lang) if rep_list else _category_display(IssueCategory.OTHER_CIVIC_ISSUE, norm_lang)
        det_name = _category_display(det_list[0], norm_lang) if det_list else _category_display(IssueCategory.OTHER_CIVIC_ISSUE, norm_lang)

        # Options: Option A, Option B, Both, Something else
        options = [rep_name, det_name, opt_common["both"], opt_common["something_else"]]
        # Deduplicate while preserving order
        unique_options: list[str] = []
        for opt in options:
            if opt not in unique_options:
                unique_options.append(opt)

        if norm_lang == "hi":
            q_text = "आप किस समस्या की रिपोर्ट करना चाहते हैं?"
        elif norm_lang == "hinglish":
            q_text = "Aap kis issue ki report karna chahte hain?"
        else:
            q_text = "Which issue best describes the problem you want to report?"

        q_id = self._generate_question_id("issue_type", ClarificationQuestionType.ISSUE_TYPE, f"{rep_name}_{det_name}")

        return ClarificationQuestion(
            question_id=q_id,
            question_text=q_text,
            target_field="issue_type",
            question_type=ClarificationQuestionType.ISSUE_TYPE,
            options=unique_options,
            required=True,
            priority=1,
            reason="Resolve cross-modal discrepancy between citizen report and computer vision observation.",
            answer_type=ClarificationAnswerType.SINGLE_CHOICE,
            metadata={
                "citizen_reported": [c.value for c in rep_list],
                "cv_detected": [c.value for c in det_list],
            },
        )

    # -------------------------------------------------------------------------
    # Policy: Partial Alignment Scope Question
    # -------------------------------------------------------------------------
    def _create_partial_alignment_question(
        self,
        supported_cats: set[IssueCategory],
        unsupported_cats: set[IssueCategory],
        lang: str,
    ) -> ClarificationQuestion:
        norm_lang = _normalize_lang(lang)
        opt_common = _COMMON_OPTIONS.get(norm_lang, _COMMON_OPTIONS["en"])

        sup_list = sorted(supported_cats, key=lambda c: c.value)
        unsup_list = sorted(unsupported_cats, key=lambda c: c.value)

        sup_name = _category_display(sup_list[0], norm_lang)
        unsup_name = _category_display(unsup_list[0], norm_lang)

        if norm_lang == "hi":
            q_text = f"आपने {sup_name} और {unsup_name} दोनों का उल्लेख किया है। रिपोर्ट में कौन सी समस्या शामिल की जानी चाहिए?"
            opt_sup = f"{sup_name} {opt_common['only']}"
            opt_unsup = f"{unsup_name} {opt_common['only']}"
        elif norm_lang == "hinglish":
            q_text = f"Aapne {sup_name} aur {unsup_name} dono mention kiye hain. Report mein kaun si issue include karni chahiye?"
            opt_sup = f"{sup_name} {opt_common['only']}"
            opt_unsup = f"{unsup_name} {opt_common['only']}"
        else:
            q_text = f"You mentioned both {sup_name.lower()} and {unsup_name.lower()}. Which issue should be included in the report?"
            opt_sup = f"{sup_name} only"
            opt_unsup = f"{unsup_name} only"

        options = [opt_sup, opt_unsup, opt_common["both"], opt_common["something_else"]]
        q_id = self._generate_question_id("issue_scope", ClarificationQuestionType.ISSUE_SCOPE, f"{sup_name}_{unsup_name}")

        return ClarificationQuestion(
            question_id=q_id,
            question_text=q_text,
            target_field="issue_scope",
            question_type=ClarificationQuestionType.ISSUE_SCOPE,
            options=options,
            required=True,
            priority=2,
            reason="Citizen reported multiple defects, but computer vision corroborated only a subset.",
            answer_type=ClarificationAnswerType.SINGLE_CHOICE,
            metadata={
                "supported": [c.value for c in sup_list],
                "unsupported": [c.value for c in unsup_list],
            },
        )

    # -------------------------------------------------------------------------
    # Policy: Unknown Issue Type Question
    # -------------------------------------------------------------------------
    def _create_unknown_issue_question(self, lang: str) -> ClarificationQuestion:
        norm_lang = _normalize_lang(lang)
        options = [
            _category_display(IssueCategory.OPEN_DAMAGED_MANHOLE, norm_lang),
            _category_display(IssueCategory.DAMAGED_MISSING_ROAD_SIGN, norm_lang),
            _category_display(IssueCategory.ROAD_WATERLOGGING, norm_lang),
            _category_display(IssueCategory.OTHER_CIVIC_ISSUE, norm_lang),
        ]

        if norm_lang == "hi":
            q_text = "आप किस समस्या की रिपोर्ट करना चाहते हैं?"
        elif norm_lang == "hinglish":
            q_text = "Aap kaun si civic problem report karna chahte hain?"
        else:
            q_text = "What problem would you like to report?"

        q_id = self._generate_question_id("issue_type", ClarificationQuestionType.ISSUE_TYPE, "unknown_issue")

        return ClarificationQuestion(
            question_id=q_id,
            question_text=q_text,
            target_field="issue_type",
            question_type=ClarificationQuestionType.ISSUE_TYPE,
            options=options,
            required=True,
            priority=1,
            reason="Citizen report does not identify a recognized civic defect category.",
            answer_type=ClarificationAnswerType.SINGLE_CHOICE,
            metadata={"rule": "unknown_issue_category"},
        )

    # -------------------------------------------------------------------------
    # Policy: Missing Location Question
    # -------------------------------------------------------------------------
    def _create_location_question(self, lang: str) -> ClarificationQuestion:
        norm_lang = _normalize_lang(lang)
        if norm_lang == "hi":
            q_text = "यह समस्या कहाँ स्थित है? कृपया सड़क, लैंडमार्क या क्षेत्र का नाम बताएं।"
        elif norm_lang == "hinglish":
            q_text = "Yeh issue kahan par located hai? Please road, landmark ya area batayein."
        else:
            q_text = "Where is this issue located? Please specify the road, landmark, or area."

        q_id = self._generate_question_id("issue_location", ClarificationQuestionType.ISSUE_LOCATION, "missing_location")

        return ClarificationQuestion(
            question_id=q_id,
            question_text=q_text,
            target_field="issue_location",
            question_type=ClarificationQuestionType.ISSUE_LOCATION,
            options=[],
            required=True,
            priority=3,
            reason="Report lacks geospatial and landmark attributes necessary to dispatch inspection.",
            answer_type=ClarificationAnswerType.FREE_TEXT,
            metadata={"rule": "missing_location"},
        )

    # -------------------------------------------------------------------------
    # Main Clarification Generation & Resolution Pipeline
    # -------------------------------------------------------------------------
    def resolve(
        self,
        input_data: MultimodalInput,
        alignment: EvidenceAlignmentAssessment,
        ambiguity: AmbiguityAssessment,
        history_answers: Optional[list[ClarificationAnswer]] = None,
        max_questions: Optional[int] = None,
    ) -> ClarificationResult:
        """
        Executes active clarification resolution given M9.2 assessments.
        Deterministic, bounded, explainable, and non-leading.
        """
        started_at = time.perf_counter()
        budget = min(max_questions or self._default_max_questions, HARD_CAP_MAX_QUESTIONS)
        history = history_answers or []
        lang = _normalize_lang(input_data.language)

        # Step 0: Filter already-answered question IDs and target fields
        answered_q_ids = {a.question_id for a in history if a.valid}
        answered_target_fields = set()
        for a in history:
            if a.valid and a.question_id.startswith("cq_"):
                # Extract target_field from question_id: cq_<target_field>_<hash>
                parts = a.question_id.split("_")
                if len(parts) >= 3:
                    answered_target_fields.add(parts[1])

        # Step 1: Check Aligned + Clear case
        if alignment.state == AlignmentState.ALIGNED and ambiguity.state == AmbiguityState.CLEAR:
            return ClarificationResult(
                status=ClarificationStatus.NOT_REQUIRED,
                requires_clarification=False,
                questions=[],
                unresolved_fields=[],
                reason="Report and evidence are aligned and clear; no clarification required.",
                max_questions=budget,
                epistemic_state=EpistemicState.USER_REPORTED,
                metadata={"duration_ms": round((time.perf_counter() - started_at) * 1000.0, 2)},
            )

        # Step 2: Check if previous answers have already resolved clarification
        # If all prior clarification questions were answered satisfactorily
        if history and all(a.valid for a in history):
            # Check if any outstanding ambiguous fields remain unaddressed by history
            # If issue_type was answered
            if "issue_type" in answered_target_fields or any("issue_type" in a.question_id for a in history):
                return ClarificationResult(
                    status=ClarificationStatus.RESOLVED,
                    requires_clarification=False,
                    questions=[],
                    unresolved_fields=[],
                    reason="Citizen provided valid clarification; report ambiguity resolved.",
                    max_questions=budget,
                    epistemic_state=EpistemicState.USER_REPORTED,
                    metadata={"resolved_by_answers_count": len(history)},
                )
            if "issue_scope" in answered_target_fields or any("issue_scope" in a.question_id for a in history):
                return ClarificationResult(
                    status=ClarificationStatus.RESOLVED,
                    requires_clarification=False,
                    questions=[],
                    unresolved_fields=[],
                    reason="Citizen clarified report scope; ambiguity resolved.",
                    max_questions=budget,
                    epistemic_state=EpistemicState.USER_REPORTED,
                    metadata={"resolved_by_answers_count": len(history)},
                )

        # Step 3: Check Question Budget
        if len(history) >= budget:
            return ClarificationResult(
                status=ClarificationStatus.NEEDS_USER_DECISION,
                requires_clarification=False,
                questions=[],
                unresolved_fields=ambiguity.missing_information or ["ambiguous_report"],
                reason=f"Clarification budget reached ({budget} questions). Further automated questioning suspended.",
                max_questions=budget,
                epistemic_state=EpistemicState.USER_REPORTED,
                metadata={
                    "questions_asked_count": len(history),
                    "budget_limit": budget,
                },
            )

        # Step 4: Extract evidence categories for targeted question generation
        reported_cats, _ = cross_modal_consistency_engine.extract_reported_categories(
            input_data.text,
            issue_context_class=input_data.civic_issue_context.reported_class if input_data.civic_issue_context else None,
        )
        cv_evidence = cross_modal_consistency_engine.extract_cv_evidence(input_data.cv_result)
        detected_cats = set(cv_evidence.keys())

        candidate_questions: list[ClarificationQuestion] = []

        # Policy Priority 1: Conflicting evidence
        if alignment.state == AlignmentState.CONFLICTING:
            q = self._create_conflict_question(reported_cats, detected_cats, lang)
            if q.question_id not in answered_q_ids and q.target_field not in answered_target_fields:
                candidate_questions.append(q)

        # Policy Priority 2: Partially aligned (multiple issues, only some observed)
        elif alignment.state == AlignmentState.PARTIALLY_ALIGNED:
            supported = reported_cats.intersection(detected_cats)
            unsupported = reported_cats.difference(detected_cats)
            q = self._create_partial_alignment_question(supported, unsupported, lang)
            if q.question_id not in answered_q_ids and q.target_field not in answered_target_fields:
                candidate_questions.append(q)

        # Policy Priority 3: Insufficient evidence / Unknown issue category
        elif not reported_cats:
            # Check if input text exists or is empty
            if not input_data.text or not input_data.text.strip():
                # Genuinely no text and no issue recognized
                if not detected_cats:
                    return ClarificationResult(
                        status=ClarificationStatus.INSUFFICIENT_INFORMATION,
                        requires_clarification=False,
                        questions=[],
                        unresolved_fields=["issue_category", "text_description"],
                        reason="Insufficient information available to generate targeted clarification questions.",
                        max_questions=budget,
                        epistemic_state=EpistemicState.USER_REPORTED,
                    )
            q = self._create_unknown_issue_question(lang)
            if q.question_id not in answered_q_ids and q.target_field not in answered_target_fields:
                candidate_questions.append(q)

        # Policy Priority 4: Known issue but missing location information
        elif input_data.location_context is None or (
            not input_data.location_context.road_name
            and not input_data.location_context.locality
            and not input_data.location_context.latitude
        ):
            # Only ask if location was marked as missing
            if "location" in ambiguity.missing_information or "location_context" in ambiguity.missing_information:
                q = self._create_location_question(lang)
                if q.question_id not in answered_q_ids and q.target_field not in answered_target_fields:
                    candidate_questions.append(q)

        # Step 5: Check candidate questions against budget
        remaining_budget = budget - len(history)
        selected_questions = candidate_questions[:remaining_budget]

        duration_ms = (time.perf_counter() - started_at) * 1000.0

        if not selected_questions:
            # If no question could be selected but ambiguity exists and budget wasn't reached
            if ambiguity.requires_clarification or alignment.state != AlignmentState.ALIGNED:
                return ClarificationResult(
                    status=ClarificationStatus.INSUFFICIENT_INFORMATION,
                    requires_clarification=False,
                    questions=[],
                    unresolved_fields=ambiguity.missing_information or ["unresolved_ambiguity"],
                    reason="No further targeted clarification questions can be formulated with available evidence.",
                    max_questions=budget,
                    epistemic_state=EpistemicState.USER_REPORTED,
                    metadata={"duration_ms": round(duration_ms, 2)},
                )
            else:
                return ClarificationResult(
                    status=ClarificationStatus.NOT_REQUIRED,
                    requires_clarification=False,
                    questions=[],
                    unresolved_fields=[],
                    reason="No clarification required.",
                    max_questions=budget,
                    epistemic_state=EpistemicState.USER_REPORTED,
                    metadata={"duration_ms": round(duration_ms, 2)},
                )

        return ClarificationResult(
            status=ClarificationStatus.QUESTION_PRESENTED,
            requires_clarification=True,
            questions=selected_questions,
            unresolved_fields=[q.target_field for q in selected_questions],
            reason=selected_questions[0].reason,
            max_questions=budget,
            epistemic_state=EpistemicState.USER_REPORTED,
            metadata={
                "duration_ms": round(duration_ms, 2),
                "questions_count": len(selected_questions),
                "language": lang,
            },
        )


# Shared singleton instance
active_clarification_resolver = ActiveClarificationResolver()
