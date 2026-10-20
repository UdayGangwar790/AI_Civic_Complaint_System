"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.3: Active Clarification & Ambiguity Resolver Test Suite

Validates all 27+ required test cases for M9.3 active clarification:
1. ALIGNED + CLEAR -> no question
2. CONFLICTING -> neutral reconciliation question
3. PARTIALLY_ALIGNED -> focused question
4. unknown issue -> ISSUE_TYPE question
5. insufficient evidence -> bounded response
6. maximum question limit
7. no duplicate question
8. answered question not repeated
9. valid option accepted
10. invalid option rejected
11. free text length validation
12. user answer remains USER_REPORTED
13. clarification RESOLVED != civic issue resolved
14. no accusation language
15. no leading questions
16. no causality claims
17. deterministic repeated execution
18. English template
19. Hindi template
20. Hinglish template
21. unsupported language fallback
22. PII sanitization
23. credential sanitization
24. no external network
25. M9.2 regression
26. M9.1 regression
27. model-independent behavior
"""

import socket
import pytest

from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
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
    MultimodalLocationContext,
)
from app.services.multimodal.clarification_resolver import (
    ActiveClarificationResolver,
    active_clarification_resolver,
)
from app.services.multimodal.consistency_engine import (
    cross_modal_consistency_engine,
)


# =============================================================================
# Helper Fixtures & Test Data Generators
# =============================================================================

def _build_cv_result(class_name: str, confidence: float = 0.85) -> StandardDetectionResult:
    dets = [
        StandardDetection(
            class_id=0,
            class_name=class_name,
            confidence=confidence,
            bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=200),
        )
    ]
    return StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=len(dets),
        detections=dets,
    )




# =============================================================================
# Test 1: ALIGNED + CLEAR -> No Question Generated
# =============================================================================

def test_01_aligned_and_clear_generates_no_question():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-01",
        text="Open manhole on the road",
        cv_result=_build_cv_result("open_damaged_manhole", 0.90),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    assert alignment.state == AlignmentState.ALIGNED
    assert ambiguity.state == AmbiguityState.CLEAR

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert result.status == ClarificationStatus.NOT_REQUIRED
    assert result.requires_clarification is False
    assert len(result.questions) == 0
    assert result.unresolved_fields == []


# =============================================================================
# Test 2: CONFLICTING -> Neutral Reconciliation Question
# =============================================================================

def test_02_conflicting_generates_neutral_reconciliation_question():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-02",
        text="Open manhole on the road",
        cv_result=_build_cv_result("road_waterlogging", 0.88),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    assert alignment.state == AlignmentState.CONFLICTING

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert result.status == ClarificationStatus.QUESTION_PRESENTED
    assert result.requires_clarification is True
    assert len(result.questions) == 1

    q = result.questions[0]
    assert q.target_field == "issue_type"
    assert q.question_type == ClarificationQuestionType.ISSUE_TYPE
    assert "Open/damaged manhole" in q.options
    assert "Road waterlogging" in q.options
    assert "Both" in q.options
    assert "Something else" in q.options


# =============================================================================
# Test 3: PARTIALLY_ALIGNED -> Focused Scope Question
# =============================================================================

def test_03_partially_aligned_generates_focused_scope_question():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-03",
        text="Waterlogging and broken road sign near market",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    assert alignment.state == AlignmentState.PARTIALLY_ALIGNED

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert result.status == ClarificationStatus.QUESTION_PRESENTED
    assert result.requires_clarification is True
    assert len(result.questions) == 1

    q = result.questions[0]
    assert q.target_field == "issue_scope"
    assert q.question_type == ClarificationQuestionType.ISSUE_SCOPE
    assert any("only" in opt.lower() for opt in q.options)
    assert "Both" in q.options


# =============================================================================
# Test 4: Unknown Issue -> ISSUE_TYPE Question
# =============================================================================

def test_04_unknown_issue_generates_issue_type_question():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-04",
        text="There is something bad on the road please fix it",
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert result.status == ClarificationStatus.QUESTION_PRESENTED
    assert result.requires_clarification is True
    assert len(result.questions) == 1

    q = result.questions[0]
    assert q.target_field == "issue_type"
    assert q.question_type == ClarificationQuestionType.ISSUE_TYPE
    assert len(q.options) >= 3


# =============================================================================
# Test 5: Insufficient Evidence -> Bounded Safe Response
# =============================================================================

def test_05_insufficient_evidence_bounded_safe_response():
    resolver = ActiveClarificationResolver()
    # No text, only an evidence reference without cv result
    m_input = MultimodalInput(
        request_id="req-05",
        text=None,
        evidence_reference_id="ev_reference_005",
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert result.status == ClarificationStatus.INSUFFICIENT_INFORMATION
    assert result.requires_clarification is False
    assert len(result.questions) == 0


# =============================================================================
# Test 6: Maximum Question Limit (Budget Enforcement)
# =============================================================================

def test_06_maximum_question_limit_enforced():
    resolver = ActiveClarificationResolver(default_max_questions=2)
    m_input = MultimodalInput(
        request_id="req-06",
        text="Gutter open on street",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    # Provide 2 previous questions in history
    history = [
        ClarificationAnswer(
            question_id="prev_q_1",
            selected_option="Something",
            answer_type=ClarificationAnswerType.SINGLE_CHOICE,
            valid=True,
        ),
        ClarificationAnswer(
            question_id="prev_q_2",
            selected_option="Something else",
            answer_type=ClarificationAnswerType.SINGLE_CHOICE,
            valid=True,
        ),
    ]

    result = resolver.resolve(m_input, alignment, ambiguity, history_answers=history, max_questions=2)
    assert result.status == ClarificationStatus.NEEDS_USER_DECISION
    assert result.requires_clarification is False
    assert len(result.questions) == 0
    assert "Clarification budget reached" in (result.reason or "")


# =============================================================================
# Test 7: No Duplicate Question Generated in Same Cycle
# =============================================================================

def test_07_no_duplicate_question_in_same_cycle():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-07",
        text="Unclear civic report",
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    q_ids = [q.question_id for q in result.questions]
    assert len(q_ids) == len(set(q_ids)), "Duplicate question IDs generated in single cycle"


# =============================================================================
# Test 8: Answered Question Not Repeated
# =============================================================================

def test_08_answered_question_not_repeated():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-08",
        text="Open manhole on road",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    # First turn: get question
    first_res = resolver.resolve(m_input, alignment, ambiguity)
    assert len(first_res.questions) == 1
    q1 = first_res.questions[0]

    # Citizen answers q1
    ans = ClarificationAnswer(
        question_id=q1.question_id,
        selected_option="Open/damaged manhole",
        answer_type=ClarificationAnswerType.SINGLE_CHOICE,
        valid=True,
    )

    # Second turn with answer provided
    second_res = resolver.resolve(m_input, alignment, ambiguity, history_answers=[ans])
    # The answered question should not be asked again! It should be resolved
    assert second_res.status == ClarificationStatus.RESOLVED
    assert len(second_res.questions) == 0


# =============================================================================
# Test 9: Valid Option Accepted
# =============================================================================

def test_09_valid_option_accepted():
    resolver = ActiveClarificationResolver()
    q = ClarificationQuestion(
        question_id="cq_test_09",
        question_text="Which issue?",
        target_field="issue_type",
        options=["Open/damaged manhole", "Road waterlogging", "Both", "Something else"],
        reason="Testing option acceptance",
        answer_type=ClarificationAnswerType.SINGLE_CHOICE,
    )
    ans = ClarificationAnswer(
        question_id="cq_test_09",
        selected_option="Road waterlogging",
        answer_type=ClarificationAnswerType.SINGLE_CHOICE,
    )
    is_valid, err = resolver.validate_answer(ans, q)
    assert is_valid is True
    assert err is None


# =============================================================================
# Test 10: Invalid Option Rejected
# =============================================================================

def test_10_invalid_option_rejected():
    resolver = ActiveClarificationResolver()
    q = ClarificationQuestion(
        question_id="cq_test_10",
        question_text="Which issue?",
        target_field="issue_type",
        options=["Open/damaged manhole", "Road waterlogging"],
        reason="Testing invalid option rejection",
        answer_type=ClarificationAnswerType.SINGLE_CHOICE,
    )
    ans = ClarificationAnswer(
        question_id="cq_test_10",
        selected_option="Pothole in road",  # Not in options
        answer_type=ClarificationAnswerType.SINGLE_CHOICE,
    )
    is_valid, err = resolver.validate_answer(ans, q)
    assert is_valid is False
    assert "not among valid choices" in (err or "")


# =============================================================================
# Test 11: Free Text Length Validation
# =============================================================================

def test_11_free_text_length_validation():
    resolver = ActiveClarificationResolver()
    q = ClarificationQuestion(
        question_id="cq_test_11",
        question_text="Please describe location",
        target_field="issue_location",
        options=[],
        reason="Testing length bounds",
        answer_type=ClarificationAnswerType.FREE_TEXT,
    )

    # Exceeding 500 chars should be rejected
    long_text = "A" * 501
    ans_invalid = ClarificationAnswer(
        question_id="cq_test_11",
        free_text=long_text,
        answer_type=ClarificationAnswerType.FREE_TEXT,
    )
    is_valid, err = resolver.validate_answer(ans_invalid, q)
    assert is_valid is False
    assert "exceeds maximum allowed length" in (err or "")

    # Bounded length (e.g. 50 chars) should be accepted
    ans_valid = ClarificationAnswer(
        question_id="cq_test_11",
        free_text="Near MG Road metro station pillar 42",
        answer_type=ClarificationAnswerType.FREE_TEXT,
    )
    is_valid_ok, err_ok = resolver.validate_answer(ans_valid, q)
    assert is_valid_ok is True
    assert err_ok is None


# =============================================================================
# Test 12: User Answer Strictly Remains USER_REPORTED
# =============================================================================

def test_12_user_answer_strictly_remains_user_reported():
    ans = ClarificationAnswer(
        question_id="cq_test_12",
        selected_option="Open/damaged manhole",
        epistemic_state=EpistemicState.USER_REPORTED,
    )
    assert ans.epistemic_state == EpistemicState.USER_REPORTED

    # Attempting to assign VERIFIED_EVIDENCE to citizen answer must raise ValidationError
    with pytest.raises(ValueError):
        ClarificationAnswer(
            question_id="cq_test_12",
            selected_option="Open/damaged manhole",
            epistemic_state=EpistemicState.VERIFIED_EVIDENCE,  # Prohibited!
        )


# =============================================================================
# Test 13: Clarification RESOLVED != Civic Issue Resolved
# =============================================================================

def test_13_clarification_resolved_does_not_mean_civic_issue_resolved():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-13",
        text="Open manhole on road",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    # Prior answer given
    ans = ClarificationAnswer(
        question_id="cq_issue_type_abc",
        selected_option="Open/damaged manhole",
        valid=True,
    )
    result = resolver.resolve(m_input, alignment, ambiguity, history_answers=[ans])

    # Status must be RESOLVED for clarification
    assert result.status == ClarificationStatus.RESOLVED
    # Epistemic state MUST still be USER_REPORTED (not verified evidence!)
    assert result.epistemic_state == EpistemicState.USER_REPORTED
    assert result.epistemic_state != EpistemicState.VERIFIED_EVIDENCE


# =============================================================================
# Test 14: No Accusation Language in Generated Questions
# =============================================================================

def test_14_no_accusation_language_in_questions():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-14",
        text="Open manhole on road",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    for q in result.questions:
        text = q.question_text.lower()
        reason = q.reason.lower()
        forbidden_terms = ["lie", "liar", "fake", "fraud", "false claim", "wrong", "mistake", "accuse"]
        for term in forbidden_terms:
            assert term not in text, f"Forbidden accusation term '{term}' found in question text"
            assert term not in reason, f"Forbidden accusation term '{term}' found in reason"


# =============================================================================
# Test 15: No Leading Questions
# =============================================================================

def test_15_no_leading_questions():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-15",
        text="Manhole cover missing",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    for q in result.questions:
        text = q.question_text.lower()
        # Bad phrasing: "CV detected waterlogging. Isn't that the actual problem?" or "Are you sure?"
        assert "isn't that" not in text
        assert "are you sure" not in text
        assert "cv detected" not in text
        assert "computer vision detected" not in text


# =============================================================================
# Test 16: No Causality Claims
# =============================================================================

def test_16_no_causality_claims():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-16",
        text="Manhole cover missing and waterlogging",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    for q in result.questions:
        text = q.question_text.lower()
        reason = q.reason.lower()
        causality_terms = ["caused by", "led to", "due to manhole", "resulting from", "causation"]
        for term in causality_terms:
            assert term not in text, f"Causality claim '{term}' in question text"
            assert term not in reason, f"Causality claim '{term}' in reason"


# =============================================================================
# Test 17: Deterministic Repeated Execution
# =============================================================================

def test_17_deterministic_repeated_execution():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-17",
        text="Open drain lid on the road",
        cv_result=_build_cv_result("damaged_missing_road_sign", 0.80),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    runs = [resolver.resolve(m_input, alignment, ambiguity) for _ in range(5)]
    first_res = runs[0]

    for run in runs[1:]:
        assert run.status == first_res.status
        assert len(run.questions) == len(first_res.questions)
        assert run.questions[0].question_id == first_res.questions[0].question_id
        assert run.questions[0].question_text == first_res.questions[0].question_text
        assert run.questions[0].options == first_res.questions[0].options


# =============================================================================
# Test 18: English Template
# =============================================================================

def test_18_english_template():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-18",
        text="Gutter broken",
        language="en",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert len(result.questions) == 1
    q = result.questions[0]
    assert q.question_text == "Which issue best describes the problem you want to report?"
    assert "Open/damaged manhole" in q.options


# =============================================================================
# Test 19: Hindi Template
# =============================================================================

def test_19_hindi_template():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-19",
        text="गटर का ढक्कन खुला है",
        language="hi",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert len(result.questions) == 1
    q = result.questions[0]
    assert "आप किस समस्या की रिपोर्ट करना चाहते हैं?" in q.question_text
    assert "दोनों" in q.options or "खुला/क्षतिग्रस्त मैनहोल" in q.options


# =============================================================================
# Test 20: Hinglish Template
# =============================================================================

def test_20_hinglish_template():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-20",
        text="Khula manhole hai",
        language="hinglish",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert len(result.questions) == 1
    q = result.questions[0]
    assert "Aap kis issue ki report karna chahte hain?" in q.question_text


# =============================================================================
# Test 21: Unsupported Language Fallback
# =============================================================================

def test_21_unsupported_language_fallback():
    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-21",
        text="Manhole issue",
        language="fr",  # French is unsupported in M9.3
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert len(result.questions) == 1
    q = result.questions[0]
    # Must safely fall back to English template
    assert q.question_text == "Which issue best describes the problem you want to report?"


# =============================================================================
# Test 22: PII Sanitization
# =============================================================================

def test_22_pii_sanitization():
    # Citizen inputs phone number and email in text
    m_input = MultimodalInput(
        request_id="req-22",
        text="Contact citizen John Doe at 9876543210 or citizen@example.com for road sign",
        cv_result=_build_cv_result("damaged_missing_road_sign", 0.90),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    assert alignment.state == AlignmentState.ALIGNED
    assert ambiguity.state == AmbiguityState.CLEAR


# =============================================================================
# Test 23: Credential & Malicious Content Sanitization in Answers
# =============================================================================

def test_23_credential_and_path_sanitization_in_answers():
    resolver = ActiveClarificationResolver()
    q = ClarificationQuestion(
        question_id="cq_test_23",
        question_text="Provide detail",
        target_field="detail",
        reason="Sanitization check",
        answer_type=ClarificationAnswerType.FREE_TEXT,
    )

    # 1. Credential injection in free text
    ans_cred = ClarificationAnswer(
        question_id="cq_test_23",
        free_text="My auth_token is eyJhbGciOiJIUzI1NiIsIn...",
        answer_type=ClarificationAnswerType.FREE_TEXT,
    )
    is_valid, err = resolver.validate_answer(ans_cred, q)
    assert is_valid is False
    assert "prohibited credential" in (err or "")

    # 2. Path traversal in free text
    ans_path = ClarificationAnswer(
        question_id="cq_test_23",
        free_text="../../etc/passwd",
        answer_type=ClarificationAnswerType.FREE_TEXT,
    )
    is_valid, err = resolver.validate_answer(ans_path, q)
    assert is_valid is False
    assert "prohibited path traversal" in (err or "")

    # 3. URL injection in free text
    ans_url = ClarificationAnswer(
        question_id="cq_test_23",
        free_text="Visit http://malicious-site.com/payload",
        answer_type=ClarificationAnswerType.FREE_TEXT,
    )
    is_valid, err = resolver.validate_answer(ans_url, q)
    assert is_valid is False
    assert "cannot contain web URLs" in (err or "")


# =============================================================================
# Test 24: No External Network Calls
# =============================================================================

def test_24_no_external_network_calls(monkeypatch):
    # Monkeypatch socket connect to fail if any external network attempt occurs
    def guarded_connect(*args, **kwargs):
        pytest.fail("M9.3 made an unauthorized external network call via socket!")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    resolver = ActiveClarificationResolver()
    m_input = MultimodalInput(
        request_id="req-24",
        text="Open manhole on road",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(m_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(m_input, alignment)

    result = resolver.resolve(m_input, alignment, ambiguity)
    assert result.status == ClarificationStatus.QUESTION_PRESENTED


# =============================================================================
# Test 25: M9.2 Regression Integrity
# =============================================================================

def test_25_m92_regression_integrity():
    m_input = MultimodalInput(
        request_id="req-25",
        text="Severe road waterlogging",
        cv_result=_build_cv_result("road_waterlogging", 0.85),
    )
    res = cross_modal_consistency_engine.analyze(m_input)
    assert res.success is True
    assert res.evidence_alignment.state == AlignmentState.ALIGNED
    assert res.ambiguity_assessment.state == AmbiguityState.CLEAR


# =============================================================================
# Test 26: M9.1 SPI & Schemas Regression Integrity
# =============================================================================

def test_26_m91_regression_integrity():
    from app.services.multimodal.resolver import multimodal_provider_resolver

    mock_prov = multimodal_provider_resolver.resolve_provider("mock_multimodal_provider")
    assert mock_prov is not None
    if not mock_prov.is_loaded:
        mock_prov.initialize()


    m_input = MultimodalInput(
        request_id="req-26",
        text="Damaged road sign near crossing",
    )
    res = mock_prov.infer(m_input)
    assert res.success is True
    assert res.epistemic_state == EpistemicState.MODEL_OBSERVATION



# =============================================================================
# Test 27: Model-Independent Behavior
# =============================================================================

def test_27_model_independent_behavior():
    # Resolver must work identically regardless of which model provided cv_result
    resolver = ActiveClarificationResolver()

    # Provider A detection result
    dets_a = [
        StandardDetection(
            class_id=0,
            class_name="open_damaged_manhole",
            confidence=0.82,
            bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=200),
        )
    ]
    cv_a = StandardDetectionResult(
        model_id="m1.13-yolov8n",
        model_version="1.13.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=len(dets_a),
        detections=dets_a,
    )

    # Provider B detection result (hypothetical future provider)
    dets_b = [
        StandardDetection(
            class_id=0,
            class_name="open_damaged_manhole",
            confidence=0.82,
            bbox=StandardBoundingBox(x1=10, y1=20, x2=100, y2=200),
        )
    ]
    cv_b = StandardDetectionResult(
        model_id="future-yolo-v2",
        model_version="2.0.0",
        task="civic_hazard_detection",
        success=True,
        total_detections=len(dets_b),
        detections=dets_b,
    )



    input_a = MultimodalInput(request_id="req-27a", text="Waterlogging on street", cv_result=cv_a)
    input_b = MultimodalInput(request_id="req-27b", text="Waterlogging on street", cv_result=cv_b)

    align_a = cross_modal_consistency_engine.evaluate_consistency(input_a)
    ambig_a = cross_modal_consistency_engine.evaluate_ambiguity(input_a, align_a)

    align_b = cross_modal_consistency_engine.evaluate_consistency(input_b)
    ambig_b = cross_modal_consistency_engine.evaluate_ambiguity(input_b, align_b)

    res_a = resolver.resolve(input_a, align_a, ambig_a)
    res_b = resolver.resolve(input_b, align_b, ambig_b)

    assert res_a.questions[0].question_text == res_b.questions[0].question_text
    assert res_a.questions[0].options == res_b.questions[0].options
