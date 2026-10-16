"""
CVKI M7.1 Government Integration API Endpoints.
Provides registry discovery, submission summaries, verified dispatch initiation,
status synchronization, and reconciliation.
"""

import inspect
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AuthenticatedUser, get_current_user, require_roles
from app.models.roles import UserRole
from app.schemas.government_integration import (
    GovernmentIntegrationDefinition,
    GovernmentIntegrationListResponse,
    GovernmentStatusSyncResult,
    GovernmentSubmissionResponse,
    GovernmentSubmissionSummary,
    ReconciliationRequest,
    ReconciliationResult,
    SubmitGovernmentCaseRequest,
)
from app.schemas.government_submission import PrepareSubmissionResponse
from app.schemas.government_reference import (
    GovernmentReferenceListResponse,
    GovernmentReferenceMappingResponse,
    ManualReferenceCreateRequest,
)
from app.schemas.government_status import (
    GovernmentStatusHistoryResponse,
    GovernmentStatusSyncResponse,
)
from app.schemas.escalation import (
    EscalationHistoryResponse,
    EscalationPolicy,
    EscalationPolicyCreateRequest,
    EscalationPolicyListResponse,
    EscalationResponse,
)
from app.schemas.resolution_verification import (
    CitizenResolutionVerificationHistoryResponse,
    CitizenResolutionVerificationResponse,
    CitizenResolutionVerificationSubmitRequest,
    ResolutionVerificationReviewRequest,
)
from app.schemas.government_analytics import (
    AuthorityPerformanceAggregate,
    CaseTimelineAnalyticsResponse,
    EscalationAnalyticsMetrics,
    GovernmentAnalyticsSummaryResponse,
    GovernmentStatusDistributionItem,
    ResolutionVerificationMetrics,
)
from app.services.complaint_case import (
    ComplaintCaseDatabaseError,
    ComplaintCaseNotFoundError,
    get_case,
)
from app.services.government_integration_service import (
    NOT_CONFIGURED_NOTICE,
    government_integration_service,
)
from app.services.government_reference_service import get_government_reference_service
from app.services.government_status_service import get_government_status_service
from app.services.escalation_service import get_escalation_service
from app.services.resolution_verification_service import get_resolution_verification_service
from app.services.government_analytics_service import get_government_analytics_service
from app.services.government_registry import government_registry
from app.services.government_submission import (
    SubmissionBlockedError,
    SubmissionNotReadyError,
    prepare_government_submission,
)

logger = logging.getLogger("cvki.api.government_integration")

router = APIRouter(tags=["Government Integration Foundation"])


def _check_case_access(case, user: AuthenticatedUser) -> None:
    """Enforces RBAC access for case: citizen owner, admin, or authority."""
    if user.role == UserRole.ADMIN.value:
        return
    if user.role == UserRole.CITIZEN.value:
        if case.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CVKI case was not found.",
            )
        return
    if user.role == UserRole.AUTHORITY.value:
        # Authority can access if assigned or if authority matches case authority
        if getattr(case, "assignment", None) and case.assignment.assigned_to_user_id == user.user_id:
            return
        # Authority general review permitted
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.get(
    "/government-integrations",
    response_model=GovernmentIntegrationListResponse,
    summary="List registered government integrations and capabilities",
)
async def list_government_integrations(
    active_only: bool = Query(default=False, description="Filter for enabled integrations only"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentIntegrationListResponse:
    """
    Returns registered public government integrations and their capabilities.
    Does not expose secrets, credentials, or private keys.
    """
    definitions = government_registry.list_definitions(active_only=active_only)
    return GovernmentIntegrationListResponse(
        integrations=definitions,
        total=len(definitions),
    )


@router.get(
    "/government-integrations/{integration_id}",
    response_model=GovernmentIntegrationDefinition,
    summary="Get integration details by ID",
)
async def get_government_integration(
    integration_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentIntegrationDefinition:
    defn = government_registry.get_definition(integration_id)
    if not defn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Government integration '{integration_id}' was not found.",
        )
    return defn


@router.get(
    "/government/cases/{reference_id}/submission",
    response_model=GovernmentSubmissionSummary,
    summary="Get government submission state and summary for a case",
)
async def get_case_government_submission(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentSubmissionSummary:
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    return government_integration_service.get_submission_summary(case)


@router.post(
    "/government/cases/{reference_id}/prepare",
    response_model=PrepareSubmissionResponse,
    summary="Prepare structured government dispatch package",
)
async def prepare_government_case_package(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PrepareSubmissionResponse:
    """Prepares structured complaint dispatch package if verified."""
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    try:
        _, response = await prepare_government_submission(case, user_id=current_user.user_id)
        return response
    except SubmissionBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except SubmissionNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/government/cases/{reference_id}/submit",
    response_model=GovernmentSubmissionResponse,
    summary="Submit case to government integration adapter",
)
async def submit_government_case(
    reference_id: str,
    req: Optional[SubmitGovernmentCaseRequest] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentSubmissionResponse:
    """
    Submits verified case to official government integration.
    Citizens can only trigger submission for their own cases.
    Refuses if integration is unconfigured, authority unverified, or outcome unknown.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    integration_id = req.integration_id if req else None
    idempotency_key = req.idempotency_key if req else None

    # Citizen cannot submit through arbitrary custom adapter directly; must use resolved authority integration
    if current_user.role == UserRole.CITIZEN.value and integration_id:
        # Check if the requested integration matches the case authority
        summary = government_integration_service.get_submission_summary(case)
        if summary.integration_id != integration_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Citizens cannot dispatch through arbitrary adapters. Target must match verified case authority.",
            )

    response = await government_integration_service.submit_case(
        case=case,
        integration_id=integration_id,
        user_id=current_user.user_id,
        user_role=current_user.role,
        caller_idempotency_key=idempotency_key,
    )
    return response


@router.post(
    "/government/cases/{reference_id}/reconcile",
    response_model=ReconciliationResult,
    summary="Reconcile an unconfirmed submission (Admin/Authority only)",
)
async def reconcile_government_submission(
    reference_id: str,
    req: Optional[ReconciliationRequest] = None,
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN, UserRole.AUTHORITY)),
) -> ReconciliationResult:
    """
    Reconciles a submission stuck in UNKNOWN_OUTCOME.
    Admin or Authority only. Checks external government status before allowing any retry.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    result = await government_integration_service.reconcile_submission(
        case_reference_id=reference_id,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
    )
    return result


@router.get(
    "/government/cases/{reference_id}/status",
    response_model=GovernmentStatusSyncResponse,
    summary="Synchronize and retrieve external government status (M7.4)",
)
async def get_or_sync_government_status(
    reference_id: str,
    sync: bool = Query(default=False, description="Whether to trigger live synchronization"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentStatusSyncResponse:
    """
    Returns latest cached status observation. If sync=True, triggers upstream synchronization.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    status_service = get_government_status_service()
    if sync:
        return await status_service.synchronize_status(
            case=case,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
        )
    return status_service.get_status_summary(case)


@router.post(
    "/government/cases/{reference_id}/status/sync",
    response_model=GovernmentStatusSyncResponse,
    summary="Trigger live external government status synchronization (M7.4)",
)
async def trigger_government_status_sync(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentStatusSyncResponse:
    """
    Synchronizes status with external government portal and records append-oriented history.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    return await get_government_status_service().synchronize_status(
        case=case,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
    )


@router.get(
    "/government/cases/{reference_id}/status/history",
    response_model=GovernmentStatusHistoryResponse,
    summary="Get status synchronization history (M7.4)",
)
async def get_government_status_history(
    reference_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentStatusHistoryResponse:
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    return get_government_status_service().get_status_history(reference_id, limit=limit)


@router.get(
    "/government/cases/{reference_id}/references",
    response_model=GovernmentReferenceListResponse,
    summary="List government external reference mappings for a case (M7.3)",
)
async def list_case_government_references(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentReferenceListResponse:
    """
    Returns all government reference mappings for a CVKI case.
    Citizens can view only their own cases.
    Maintains separate identities between internal CVKI reference and external tracking IDs.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    return get_government_reference_service().get_case_mappings(reference_id)


@router.get(
    "/government/cases/{reference_id}/references/{integration_id}",
    response_model=GovernmentReferenceMappingResponse,
    summary="Get government reference mapping for a specific integration (M7.3)",
)
async def get_case_government_reference_for_integration(
    reference_id: str,
    integration_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> GovernmentReferenceMappingResponse:
    """
    Returns the government reference mapping for a specific integration.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    mapping = get_government_reference_service().get_mapping(reference_id, integration_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reference mapping found for case '{reference_id}' on integration '{integration_id}'.",
        )
    return mapping


@router.get(
    "/government/cases/{reference_id}/references/{integration_id}/provenance",
    summary="Get provenance evidence record for a reference mapping (M7.3)",
)
async def get_case_government_reference_provenance(
    reference_id: str,
    integration_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retrieves M6.4 provenance evidence justifying the association of a government reference ID.
    Answers: 'Why does CVKI believe this government reference belongs to this CVKI case?'
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    mapping = get_government_reference_service().get_mapping(reference_id, integration_id)
    if not mapping or not mapping.provenance_evidence_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No provenance evidence record found for reference on integration '{integration_id}'.",
        )

    from app.services.provenance_engine import get_provenance_engine
    ev = get_provenance_engine().get_evidence_by_id(mapping.provenance_evidence_id)
    if not ev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referenced evidence record not found in provenance repository.",
        )
    return ev


@router.post(
    "/government/cases/{reference_id}/references/{integration_id}/manual",
    response_model=GovernmentReferenceMappingResponse,
    summary="Record an administrative manual government reference (Authority/Admin only)",
)
async def create_manual_government_reference(
    reference_id: str,
    integration_id: str,
    req: ManualReferenceCreateRequest,
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN, UserRole.AUTHORITY)),
) -> GovernmentReferenceMappingResponse:
    """
    Allows authorized staff to record an offline docket/acknowledgment reference.
    Strictly recorded as UNVERIFIED_MANUAL_REFERENCE with verification_state="unverified".
    Never authoritative until confirmed upstream.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    defn = government_registry.get_definition(integration_id)
    if not defn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Government integration '{integration_id}' was not found.",
        )

    try:
        ref_service = get_government_reference_service()
        mapping = await ref_service.record_manual_reference(
            cvki_reference_id=reference_id,
            integration_id=integration_id,
            req=req,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            case=case,
        )
        return ref_service._to_response(mapping)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(val_err))


# ==============================================================================
# M7.5 EVIDENCE-BASED ESCALATION ENGINE ENDPOINTS
# ==============================================================================

@router.get(
    "/government/cases/{reference_id}/escalation",
    response_model=EscalationResponse,
    summary="Get current evidence-based escalation decision (M7.5)",
)
async def get_case_escalation(
    reference_id: str,
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> EscalationResponse:
    """
    Returns the latest recorded escalation evaluation for a case.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    return get_escalation_service().get_current_escalation(case, integration_id=integration_id)


@router.post(
    "/government/cases/{reference_id}/escalation/evaluate",
    response_model=EscalationResponse,
    summary="Deterministically evaluate escalation eligibility and recommendations (M7.5)",
)
async def evaluate_case_escalation(
    reference_id: str,
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> EscalationResponse:
    """
    Deterministically evaluates case against verified government reference,
    synchronized status, status age, and policy rules.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    return await get_escalation_service().evaluate_escalation(
        case=case,
        integration_id=integration_id,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
    )


@router.get(
    "/government/cases/{reference_id}/escalation/history",
    response_model=EscalationHistoryResponse,
    summary="Get escalation evaluation history (M7.5)",
)
async def get_case_escalation_history(
    reference_id: str,
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> EscalationHistoryResponse:
    """
    Returns full chronological audit trail of escalation evaluations for a case.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    return get_escalation_service().get_escalation_history(
        cvki_reference_id=reference_id, integration_id=integration_id, limit=limit
    )


@router.get(
    "/admin/government/escalation-policies",
    response_model=EscalationPolicyListResponse,
    summary="List escalation policies (Admin only, M7.5)",
)
async def list_escalation_policies(
    enabled_only: bool = Query(default=False),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN)),
) -> EscalationPolicyListResponse:
    """
    Lists configured escalation policies. Labeled as engineering defaults, not official SLAs.
    """
    return get_escalation_service().list_policies(enabled_only=enabled_only)


@router.post(
    "/admin/government/escalation-policies",
    response_model=EscalationPolicy,
    summary="Create or update an escalation policy (Admin only, M7.5)",
)
async def create_or_update_escalation_policy(
    req: EscalationPolicyCreateRequest,
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN)),
) -> EscalationPolicy:
    """
    Admin endpoint to configure policy thresholds for deterministic civic complaint escalation.
    """
    policy = EscalationPolicy(
        policy_id=req.policy_id,
        integration_id=req.integration_id,
        target_issue_category=req.target_issue_category,
        condition_normalized_status=req.condition_normalized_status,
        minimum_age_hours=req.minimum_age_hours,
        maximum_age_hours=req.maximum_age_hours,
        escalation_action=req.escalation_action,
        escalation_level=req.escalation_level,
        cooldown_hours=req.cooldown_hours,
        max_escalation_count=req.max_escalation_count,
        requires_reference_confirmation=req.requires_reference_confirmation,
        requires_fresh_status=req.requires_fresh_status,
        enabled=req.enabled,
        priority=req.priority,
        description=req.description,
        is_official_sla=False,
    )
    return get_escalation_service().create_or_update_policy(
        policy, actor_user_id=current_user.user_id, actor_role=current_user.role
    )


# ==============================================================================
# M7.6 Citizen Resolution Verification Endpoints
# ==============================================================================

@router.post(
    "/government/cases/{reference_id}/resolution-verification",
    response_model=CitizenResolutionVerificationResponse,
    summary="Submit citizen resolution verification feedback (M7.6)",
)
async def submit_case_resolution_verification(
    reference_id: str,
    req: CitizenResolutionVerificationSubmitRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CitizenResolutionVerificationResponse:
    """
    Submits citizen-side verification on whether a civic hazard has been physically resolved.
    Does NOT automatically mutate internal case status (Epistemic Invariant Rule 1).
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    try:
        return await get_resolution_verification_service().submit_verification(
            case=case,
            req=req,
            citizen_user_id=current_user.user_id,
            citizen_role=current_user.role,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.get(
    "/government/cases/{reference_id}/resolution-verification",
    response_model=CitizenResolutionVerificationResponse,
    summary="Get latest resolution verification for a case (M7.6)",
)
async def get_latest_case_resolution_verification(
    reference_id: str,
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CitizenResolutionVerificationResponse:
    """
    Returns latest citizen resolution verification record for the case.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)

    res = get_resolution_verification_service().get_latest_verification(
        cvki_reference_id=reference_id, integration_id=integration_id
    )
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resolution verification record exists for this case.",
        )
    return res


@router.get(
    "/government/cases/{reference_id}/resolution-verification/history",
    response_model=CitizenResolutionVerificationHistoryResponse,
    summary="Get resolution verification history for a case (M7.6)",
)
async def get_case_resolution_verification_history(
    reference_id: str,
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CitizenResolutionVerificationHistoryResponse:
    """
    Returns full chronological audit trail of verification submissions and reviews for a case.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    return get_resolution_verification_service().get_verification_history(
        cvki_reference_id=reference_id, integration_id=integration_id, limit=limit
    )


@router.post(
    "/admin/government/cases/{reference_id}/resolution-verification/{verification_id}/review",
    response_model=CitizenResolutionVerificationResponse,
    summary="Operator/Admin review of disputed or needs-review verification (Admin/Authority, M7.6)",
)
async def review_case_resolution_verification(
    reference_id: str,
    verification_id: str,
    req: ResolutionVerificationReviewRequest,
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN, UserRole.AUTHORITY)),
) -> CitizenResolutionVerificationResponse:
    """
    Admin or Authority operator review determining ground resolution for disputed cases.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    try:
        return await get_resolution_verification_service().review_verification(
            case=case,
            verification_id=verification_id,
            req=req,
            reviewer_user_id=current_user.user_id,
            reviewer_role=current_user.role,
        )
    except LookupError as le:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(le))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


# ==============================================================================
# M7.7 Government Response Analytics Endpoints
# ==============================================================================

@router.get(
    "/admin/government/analytics/summary",
    response_model=GovernmentAnalyticsSummaryResponse,
    summary="Aggregate government response and verification analytics (Admin/Authority, M7.7)",
)
async def get_government_analytics_summary(
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN, UserRole.AUTHORITY)),
) -> GovernmentAnalyticsSummaryResponse:
    """
    Returns executive summary of observed government response times, status distribution,
    citizen verification dispute rates, and data quality indicators.
    Strictly system-derived analytics; never represents official statutory SLAs.
    """
    return get_government_analytics_service().get_summary_analytics(integration_id=integration_id)


@router.get(
    "/admin/government/analytics/status-distribution",
    response_model=list[GovernmentStatusDistributionItem],
    summary="Government status distribution counts and percentages (Admin/Authority, M7.7)",
)
async def get_government_status_distribution(
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN, UserRole.AUTHORITY)),
) -> list[GovernmentStatusDistributionItem]:
    """
    Returns distribution breakdown across all normalized government statuses.
    """
    summary = get_government_analytics_service().get_summary_analytics(integration_id=integration_id)
    return summary.status_distribution


@router.get(
    "/admin/government/analytics/resolution-verification",
    response_model=ResolutionVerificationMetrics,
    summary="Resolution verification and citizen dispute metrics (Admin/Authority, M7.7)",
)
async def get_government_resolution_verification_analytics(
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN, UserRole.AUTHORITY)),
) -> ResolutionVerificationMetrics:
    """
    Returns aggregate resolution verification and citizen dispute metrics.
    """
    summary = get_government_analytics_service().get_summary_analytics(integration_id=integration_id)
    return summary.resolution_verification


@router.get(
    "/admin/government/analytics/escalation",
    response_model=EscalationAnalyticsMetrics,
    summary="Escalation and follow-up analytics (Admin/Authority, M7.7)",
)
async def get_government_escalation_analytics(
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN, UserRole.AUTHORITY)),
) -> EscalationAnalyticsMetrics:
    """
    Returns aggregate escalation engine metrics.
    """
    summary = get_government_analytics_service().get_summary_analytics(integration_id=integration_id)
    return summary.escalation


@router.get(
    "/admin/government/analytics/authorities",
    response_model=list[AuthorityPerformanceAggregate],
    summary="Per-authority performance and dispute metrics (Admin/Authority, M7.7)",
)
async def get_government_authorities_analytics(
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN, UserRole.AUTHORITY)),
) -> list[AuthorityPerformanceAggregate]:
    """
    Returns performance breakdown aggregated by public authority / integration.
    """
    summary = get_government_analytics_service().get_summary_analytics()
    return summary.authority_aggregates


@router.get(
    "/government/cases/{reference_id}/analytics/timeline",
    response_model=CaseTimelineAnalyticsResponse,
    summary="Case lifecycle timeline analytics (M7.7)",
)
async def get_case_timeline_analytics(
    reference_id: str,
    integration_id: Optional[str] = Query(default=None, description="Optional target integration filter"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CaseTimelineAnalyticsResponse:
    """
    Returns chronological timeline of observed government dispatch, status updates,
    escalation decisions, and citizen resolution feedback for a single case.
    """
    try:
        case = await get_case(reference_id)
    except ComplaintCaseNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CVKI case was not found.")
    except ComplaintCaseDatabaseError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service is unavailable.")

    _check_case_access(case, current_user)
    return get_government_analytics_service().get_case_timeline_analytics(
        case=case, integration_id=integration_id
    )
