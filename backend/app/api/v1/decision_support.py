"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.4: Decision Support REST API Endpoints
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.models.roles import UserRole
from app.schemas.decision_support import (
    CitizenClarifyRequest,
    CitizenViewResponse,
    DecisionContext,
    DecisionSupportResult,
    RecommendationReviewRequest,
)
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
)
from uuid import uuid4

from app.services.decision_support import get_decision_support_engine
from app.services.decision_projection import get_decision_projector
from app.services.provenance_engine import get_provenance_engine
from app.services.multimodal.clarification_resolver import active_clarification_resolver
from app.services.multimodal.consistency_engine import cross_modal_consistency_engine
from app.services.multimodal.contracts import (
    ClarificationAnswer,
    ClarificationAnswerType,
    ClarificationQuestion,
    ClarificationQuestionType,
    EpistemicState,
    IssueCategory,
    MultimodalInput,
)
from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
import app.services.complaint_case as complaint_case_module

logger = logging.getLogger("cvki.api.decision_support")

router = APIRouter()


def _map_case_to_decision_context(case) -> DecisionContext:
    """Constructs a trusted DecisionContext from a persisted ComplaintCase document."""
    # 1. Map issue category
    issue_category = IssueCategory.UNKNOWN
    if case.issue and case.issue.class_name:
        name_upper = case.issue.class_name.upper()
        if "MANHOLE" in name_upper:
            issue_category = IssueCategory.OPEN_DAMAGED_MANHOLE
        elif "SIGN" in name_upper:
            issue_category = IssueCategory.DAMAGED_MISSING_ROAD_SIGN
        elif "WATER" in name_upper or "FLOOD" in name_upper:
            issue_category = IssueCategory.ROAD_WATERLOGGING
        else:
            issue_category = IssueCategory.OTHER_CIVIC_ISSUE

    # 2. Reconstruct StandardDetectionResult if detection exists on case
    detection_res = None
    if case.issue and case.issue.class_name:
        bbox_obj = getattr(case.issue, "bbox", None)
        if bbox_obj:
            bbox = StandardBoundingBox(
                x1=bbox_obj.x1,
                y1=bbox_obj.y1,
                x2=bbox_obj.x2,
                y2=bbox_obj.y2,
            )
        else:
            bbox = StandardBoundingBox(x1=0, y1=0, x2=1, y2=1)
        det = StandardDetection(
            class_id=getattr(case.issue, "class_id", 0),
            class_name=case.issue.class_name,
            confidence=case.issue.confidence,
            bbox=bbox,
        )
        detection_res = StandardDetectionResult(
            success=True,
            detections=[det],
            total_detections=1,
            model_id="m1_13",
            model_version="1.13.0",
            provider_id="yolov8_m1_13",
        )

    # 3. Priority and Recurrence (server-derived only)
    priority_level = None
    if case.priority_analysis and case.priority_analysis.priority_level:
        val = case.priority_analysis.priority_level
        priority_level = val.value if hasattr(val, "value") else str(val)

    is_recurrent = False
    recurrence_count = 0
    if case.recurrence_analysis:
        is_recurrent = getattr(case.recurrence_analysis, "recurrence_detected", getattr(case.recurrence_analysis, "is_recurrent", False))
        recurrence_count = getattr(case.recurrence_analysis, "recurrence_count", 0)

    # 4. Authority
    authority_name = None
    is_auth_verified = False
    if case.authority:
        m_auth = getattr(case.authority, "maintenance_authority", None)
        r_owner = getattr(case.authority, "road_owner", None)
        if m_auth and getattr(m_auth, "name", None):
            authority_name = m_auth.name
        elif r_owner and getattr(r_owner, "name", None):
            authority_name = r_owner.name
        elif hasattr(case.authority, "authority_name"):
            authority_name = getattr(case.authority, "authority_name")
        is_auth_verified = getattr(case.authority, "authority_status", "") == "verified" or getattr(case.authority, "verified", False)

    # 5. Citizen text
    citizen_text = None
    if case.complaint:
        citizen_text = f"{case.complaint.title}. {case.complaint.description}".strip()

    return DecisionContext(
        case_reference=case.reference_id,
        issue_category=issue_category,
        detection_result=detection_res,
        citizen_text=citizen_text,
        normalized_text=None,
        alignment_score=None,
        ambiguity_score=None,
        clarification_needed=False,
        priority_level=priority_level,
        is_recurrent=is_recurrent,
        recurrence_count=recurrence_count,
        is_hotspot=False,
        location_context=case.location.model_dump() if case.location else None,
        authority_name=authority_name,
        is_authority_verified=is_auth_verified,
        weather_condition=None,
        government_status=case.status,
    )


def _check_case_access(case, current_user: AuthenticatedUser) -> None:
    """Enforces strict RBAC access on case decision support."""
    if current_user.role == UserRole.CITIZEN.value:
        if case.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Citizens can only access decision support for their own cases.",
            )
    elif current_user.role == UserRole.AUTHORITY.value:
        assigned_user_id = case.assignment.assigned_to_user_id if case.assignment else None
        if assigned_user_id and assigned_user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authorities can only access decision support for cases assigned to them.",
            )


@router.get(
    "/cases/{reference_id}",
    response_model=DecisionSupportResult,
    summary="Get evidence-aware decision support recommendations for a complaint case",
)
async def get_case_decision_support(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DecisionSupportResult:
    """
    Retrieves decision support recommendations for a complaint case.
    RBAC:
    - Citizen: only accessible for their own cases.
    - Authority: only accessible for assigned cases.
    - Admin: unrestricted access.
    """
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _check_case_access(case, current_user)

    ctx = _map_case_to_decision_context(case)
    engine = get_decision_support_engine()
    result = engine.evaluate_case(ctx)

    try:
        projector = get_decision_projector()
        projector.project_decision_recommendation(reference_id, result)
    except Exception as exc:
        logger.warning("Decision projection failed for case %s: %s", reference_id, exc)

    # For citizens, omit internal supervisor escalation notes
    if current_user.role == UserRole.CITIZEN.value:
        result.mitigation_actions = [
            action for action in result.mitigation_actions
            if action.target_role != "authority_officer"
        ]

    return result


@router.post(
    "/cases/{reference_id}/evaluate",
    response_model=DecisionSupportResult,
    summary="Evaluate decision support with custom or updated operational context",
    dependencies=[
        Depends(
            rate_limit_dependency(
                scope="decision_support_evaluate",
                limit=settings.INFERENCE_RATE_LIMIT_REQUESTS,
                window_seconds=settings.INFERENCE_RATE_LIMIT_WINDOW_SECONDS,
            )
        )
    ],
)
async def evaluate_case_decision_support(
    reference_id: str,
    custom_context: Optional[DecisionContext] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DecisionSupportResult:
    """
    Re-evaluates operational decision support for a case.
    Authorities and admins can pass updated environmental or alignment context.
    Client-provided priority and recurrence overrides are strictly stripped and replaced with server truth.
    """
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _check_case_access(case, current_user)

    server_ctx = _map_case_to_decision_context(case)

    if custom_context:
        # Merge allowed custom fields (weather, traffic, alignment), but preserve server-derived priority & recurrence
        ctx = DecisionContext(
            case_reference=reference_id,
            issue_category=server_ctx.issue_category,
            detection_result=custom_context.detection_result or server_ctx.detection_result,
            citizen_text=custom_context.citizen_text or server_ctx.citizen_text,
            normalized_text=custom_context.normalized_text or server_ctx.normalized_text,
            alignment_score=custom_context.alignment_score,
            ambiguity_score=custom_context.ambiguity_score,
            clarification_needed=custom_context.clarification_needed,
            priority_level=server_ctx.priority_level,  # Strictly server-derived
            is_recurrent=server_ctx.is_recurrent,      # Strictly server-derived
            recurrence_count=server_ctx.recurrence_count,
            is_hotspot=server_ctx.is_hotspot,
            location_context=server_ctx.location_context,
            authority_name=server_ctx.authority_name,
            is_authority_verified=server_ctx.is_authority_verified,
            weather_condition=custom_context.weather_condition,
            traffic_level=custom_context.traffic_level,
            government_status=server_ctx.government_status,
            visual_audit_outcome=custom_context.visual_audit_outcome,
        )
    else:
        ctx = server_ctx

    engine = get_decision_support_engine()
    result = engine.evaluate_case(ctx)

    # Project decision recommendation into M6.4 Provenance & M6.5 Knowledge Graph
    try:
        projector = get_decision_projector()
        projector.project_decision_recommendation(reference_id, result)
    except Exception as exc:
        logger.warning("Decision projection failed for case %s: %s", reference_id, exc)

    if current_user.role == UserRole.CITIZEN.value:
        result.mitigation_actions = [
            action for action in result.mitigation_actions
            if action.target_role != "authority_officer"
        ]

    return result


@router.get(
    "/cases/{reference_id}/provenance",
    summary="Get provenance trail of decision support recommendations and field inspections",
)
async def get_case_decision_provenance(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _check_case_access(case, current_user)
    if current_user.role == UserRole.CITIZEN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizens are strictly prohibited from accessing internal decision provenance records.",
        )
    projector = get_decision_projector()
    records = projector.get_case_decision_provenance(reference_id)
    return {
        "case_reference": reference_id,
        "provenance_records": [r.model_dump(mode="json") for r in records],
    }


@router.get(
    "/cases/{reference_id}/graph",
    summary="Get decision support and field inspection knowledge graph subgraph",
)
async def get_case_decision_graph(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _check_case_access(case, current_user)
    if current_user.role == UserRole.CITIZEN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizens are strictly prohibited from accessing internal decision knowledge graphs.",
        )
    projector = get_decision_projector()
    subgraph = projector.get_case_decision_subgraph(reference_id)
    return subgraph


@router.get(
    "/cases/{reference_id}/citizen-view",
    response_model=CitizenViewResponse,
    summary="Get privacy-safe citizen view of decision support and case status",
)
async def get_citizen_view(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CitizenViewResponse:
    """
    Returns a citizen-facing view of the case:
    - Safe simplified explanation.
    - Public location representation (fuzzed coordinates + road/area, protecting exact residential privacy).
    - Status and available evidence list.
    - Clarification questions if the citizen's report was ambiguous.
    - Explicitly omits internal authority-only recommendations, supervisor notes, and sensitive audit details.
    """
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _check_case_access(case, current_user)

    issue_cat_str = "Civic Issue"
    if case.issue and case.issue.class_name:
        issue_cat_str = case.issue.class_name.replace("_", " ").title()

    simple_expl = (
        f"We have registered your report regarding '{issue_cat_str}'. "
        f"Initial observations have been evaluated and forwarded for municipal response."
    )

    # Public location privacy: approximate coordinates to 3 decimals (~100m)
    loc_dict: dict[str, Any] = {}
    if case.location:
        loc_dict["road"] = case.location.road or ""
        loc_dict["area"] = case.location.area or ""
        loc_dict["city"] = case.location.city or ""
        if case.location.latitude is not None and case.location.longitude is not None:
            loc_dict["latitude_approx"] = round(float(case.location.latitude), 3)
            loc_dict["longitude_approx"] = round(float(case.location.longitude), 3)
            loc_dict["privacy_note"] = "Coordinates approximated to protect residential location privacy."

    clarification_questions = []
    clarification_required = False
    try:
        citizen_text = ""
        if case.complaint:
            citizen_text = f"{case.complaint.title}. {case.complaint.description}".strip()

        mm_input = MultimodalInput(
            request_id=f"req_{uuid4().hex[:12]}",
            text=citizen_text or None,
        )
        alignment = cross_modal_consistency_engine.evaluate_consistency(mm_input)
        ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(mm_input, alignment)
        clar_res = active_clarification_resolver.resolve(mm_input, alignment, ambiguity)
        if clar_res.requires_clarification:
            clarification_required = True
            clarification_questions = [q.model_dump(mode="json") for q in clar_res.questions]
    except Exception as exc:
        logger.debug("Clarification resolution skipped in citizen view: %s", exc)

    avail_ev = ["Citizen report submitted"]
    if case.issue and case.issue.class_name:
        avail_ev.append(f"Visual observation: {case.issue.class_name}")
    if case.location and case.location.latitude is not None:
        avail_ev.append("Location captured")

    additional_needed = []
    if clarification_required:
        additional_needed.append("Clarification regarding issue category or scope")
    if not case.location or case.location.latitude is None:
        additional_needed.append("Nearby landmark or cross street")

    follow_up = [
        "Your report has been logged with the local authority.",
        "A municipal team will evaluate field priority and dispatch an inspector.",
    ]
    if clarification_required:
        follow_up.append("Please respond to the clarification prompt to assist the responding team.")

    return CitizenViewResponse(
        case_reference=reference_id,
        issue_category=issue_cat_str,
        status=case.status,
        simplified_explanation=simple_expl,
        clarification_required=clarification_required,
        clarification_questions=clarification_questions,
        available_evidence=avail_ev,
        additional_information_needed=additional_needed,
        follow_up_guidance=follow_up,
        public_location=loc_dict,
    )


@router.get(
    "/cases/{reference_id}/clarification",
    summary="Get active clarification questions for a complaint case",
)
async def get_case_clarification(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retrieves active clarification questions generated by M9.3 for this case.
    """
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _check_case_access(case, current_user)

    citizen_text = ""
    if case.complaint:
        citizen_text = f"{case.complaint.title}. {case.complaint.description}".strip()

    mm_input = MultimodalInput(
        request_id=f"req_{uuid4().hex[:12]}",
        text=citizen_text or None,
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(mm_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(mm_input, alignment)
    clar_res = active_clarification_resolver.resolve(mm_input, alignment, ambiguity)

    return {
        "case_reference": reference_id,
        "requires_clarification": clar_res.requires_clarification,
        "status": clar_res.status.value,
        "questions": [q.model_dump(mode="json") for q in clar_res.questions],
        "reason": clar_res.reason,
        "guidance": "Your answer will be treated as a reported observation.",
        "epistemic_state": EpistemicState.USER_REPORTED.value,
    }


@router.post(
    "/cases/{reference_id}/clarify",
    summary="Citizen submits clarification response to an active question",
    dependencies=[
        Depends(
            rate_limit_dependency(
                scope="decision_support_clarify",
                limit=settings.INFERENCE_RATE_LIMIT_REQUESTS,
                window_seconds=settings.INFERENCE_RATE_LIMIT_WINDOW_SECONDS,
            )
        )
    ],
)
async def submit_citizen_clarification(
    reference_id: str,
    request: CitizenClarifyRequest,
    http_request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Allows a citizen (or authorized admin) to submit an answer to an active clarification question.
    CRITICAL EPISTEMIC INVARIANTS:
    - Citizen response is strictly USER_REPORTED.
    - Never automatically promotes to VERIFIED_EVIDENCE.
    - Clarification resolved != Issue resolved.
    - Case lifecycle state is NEVER mutated.
    """
    from app.core.idempotency import compute_payload_fingerprint, get_idempotency_store
    fingerprint = compute_payload_fingerprint(request.model_dump())
    idem_key = http_request.headers.get("Idempotency-Key") or f"clarify_{reference_id}_{current_user.user_id}_{fingerprint}"
    idem_store = get_idempotency_store()
    acquired, existing_record = idem_store.acquire(
        key=idem_key,
        scope="citizen_clarification",
        fingerprint=fingerprint,
    )
    if not acquired and existing_record:
        if existing_record.status == "IN_PROGRESS":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A clarification submission with this key is currently in progress.",
            )
        return JSONResponse(
            status_code=existing_record.response_status_code or 200,
            content=existing_record.response_body,
            headers={"Idempotent-Replay": "true"},
        )

    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        idem_store.release_on_failure(idem_key)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    # Strict RBAC: only owner citizen or admin
    if current_user.role == UserRole.CITIZEN.value and case.user_id != current_user.user_id:
        idem_store.release_on_failure(idem_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizens can only answer clarification questions on their own cases.",
        )
    if current_user.role == UserRole.AUTHORITY.value:
        idem_store.release_on_failure(idem_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clarification answers must come from the reporting citizen.",
        )

    # 1. Re-derive questions to validate against active question
    citizen_text = ""
    if case.complaint:
        citizen_text = f"{case.complaint.title}. {case.complaint.description}".strip()

    mm_input = MultimodalInput(
        request_id=f"req_{uuid4().hex[:12]}",
        text=citizen_text or None,
        language=request.language,
    )
    alignment = cross_modal_consistency_engine.evaluate_consistency(mm_input)
    ambiguity = cross_modal_consistency_engine.evaluate_ambiguity(mm_input, alignment)
    clar_res = active_clarification_resolver.resolve(mm_input, alignment, ambiguity)

    # Find the target question
    matched_q = next((q for q in clar_res.questions if q.question_id == request.question_id), None)
    if not matched_q:
        # Also allow general response if question ID prefix matches
        matched_q = ClarificationQuestion(
            question_id=request.question_id,
            question_text="Citizen clarification question",
            target_field="general_clarification",
            question_type=ClarificationQuestionType.ISSUE_TYPE,
            answer_type=ClarificationAnswerType.SINGLE_CHOICE if request.selected_option else ClarificationAnswerType.FREE_TEXT,
            options=[request.selected_option] if request.selected_option else [],
            required=False,
            reason="Citizen response to active clarification",
        )

    # Build answer model
    answer_model = ClarificationAnswer(
        question_id=request.question_id,
        answer_type=matched_q.answer_type,
        selected_option=request.selected_option,
        selected_options=request.selected_options or [],
        free_text=request.free_text,
        epistemic_state=EpistemicState.USER_REPORTED,
        valid=True,
    )

    is_valid, rej_reason = active_clarification_resolver.validate_answer(answer_model, matched_q)
    if not is_valid:
        idem_store.release_on_failure(idem_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Clarification answer validation failed: {rej_reason}",
        )

    # 2. Record in M6.4 Provenance strictly as USER_REPORTED
    prov_engine = get_provenance_engine()
    val_summary = {
        "question_id": request.question_id,
        "selected_option": request.selected_option,
        "selected_options": request.selected_options,
        "free_text": request.free_text,
    }
    prov_engine.build_evidence_record(
        case_reference=reference_id,
        claim_type=ClaimType.OPERATIONAL_DECISION_RECOMMENDATION,
        source=f"Citizen {current_user.user_id}",
        source_type=SourceType.CITIZEN_REPORT,
        explanation=f"Citizen clarification response for {request.question_id}",
        verification_state=VerificationState.NOT_VERIFIED,
        claim_value=val_summary,
        metadata={
            "user_id": current_user.user_id,
            "epistemic_state": EpistemicState.USER_REPORTED.value,
            "claim_value": val_summary,
        },
    )

    # 3. Re-evaluate case decision support with the clarification answer included
    ctx = _map_case_to_decision_context(case)
    if request.selected_option:
        ctx.citizen_text = f"{ctx.citizen_text or ''} (Clarification: {request.selected_option})".strip()
    elif request.free_text:
        ctx.citizen_text = f"{ctx.citizen_text or ''} (Clarification: {request.free_text})".strip()

    engine = get_decision_support_engine()
    updated_decision = engine.evaluate_case(ctx)

    # Project new decision version into KG
    projector = get_decision_projector()
    projector.project_decision_recommendation(reference_id, updated_decision)

    res_body = {
        "status": "SUCCESS",
        "case_reference": reference_id,
        "clarification_status": "RESOLVED",
        "message": "Your clarification has been recorded as user-reported observation.",
        "epistemic_state": EpistemicState.USER_REPORTED.value,
        "updated_decision_id": updated_decision.recommendation_id,
        "updated_decision_version": updated_decision.decision_version,
    }
    idem_store.complete(key=idem_key, response_status_code=200, response_body=res_body)
    return res_body


@router.post(
    "/cases/{reference_id}/review",
    summary="Authority or Admin records that decision recommendation was reviewed",
)
async def review_recommendation(
    reference_id: str,
    review: RecommendationReviewRequest,
    http_request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Authority marks that the operational decision recommendation was reviewed.
    CRITICAL INVARIANT:
    - Does NOT automatically mutate case lifecycle status to 'resolved' or 'closed'.
    - Audits human reviewer identity and review notes into Provenance.
    """
    if current_user.role not in (UserRole.AUTHORITY.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only authorities and administrators can review decision recommendations.",
        )

    from app.core.idempotency import compute_payload_fingerprint, get_idempotency_store
    fingerprint = compute_payload_fingerprint(review.model_dump())
    idem_key = http_request.headers.get("Idempotency-Key") or f"review_{reference_id}_{current_user.user_id}_{fingerprint}"
    idem_store = get_idempotency_store()
    acquired, existing_record = idem_store.acquire(
        key=idem_key,
        scope="authority_review",
        fingerprint=fingerprint,
    )
    if not acquired and existing_record:
        if existing_record.status == "IN_PROGRESS":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A review with this key is currently in progress.",
            )
        return JSONResponse(
            status_code=existing_record.response_status_code or 200,
            content=existing_record.response_body,
            headers={"Idempotent-Replay": "true"},
        )

    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        idem_store.release_on_failure(idem_key)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    _check_case_access(case, current_user)

    prov_engine = get_provenance_engine()
    review_record = prov_engine.build_evidence_record(
        case_reference=reference_id,
        claim_type=ClaimType.OPERATIONAL_DECISION_RECOMMENDATION,
        source=f"Reviewer {current_user.user_id}",
        source_type=SourceType.AUTHORITY_UPDATE,
        explanation=f"Authority review: {review.review_status}. Notes: {review.review_notes or 'None'}",
        verification_state=VerificationState.VERIFIED,
        claim_value={
            "review_status": review.review_status,
            "review_notes": review.review_notes,
            "reviewer_id": current_user.user_id,
            "decision_action_taken": review.decision_action_taken,
        },
        metadata={
            "reviewer_id": current_user.user_id,
            "reviewer_role": current_user.role,
            "review_status": review.review_status,
        },
    )

    review_res = {
        "status": "SUCCESS",
        "case_reference": reference_id,
        "review_status": review.review_status,
        "reviewer_id": current_user.user_id,
        "evidence_id": review_record.evidence_id,
        "epistemic_state": "AUTHORITY_VERIFIED",
        "case_status_unchanged": case.status,
    }
    idem_store.complete(key=idem_key, response_status_code=200, response_body=review_res)
    return review_res


