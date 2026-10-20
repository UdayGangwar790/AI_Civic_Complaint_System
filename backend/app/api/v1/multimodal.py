"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.2: Multimodal Gateway REST API Endpoints
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.models.roles import UserRole
from app.schemas.multimodal_gateway import (
    MultimodalGatewayRequest,
    MultimodalGatewayResponse,
)
from app.services.multimodal_gateway import get_multimodal_gateway_service
import app.services.complaint_case as complaint_case_module

logger = logging.getLogger("cvki.api.multimodal")

router = APIRouter()


@router.post(
    "/analyze",
    response_model=MultimodalGatewayResponse,
    summary="Execute multimodal consistency, clarification, and visual audit pipeline",
    dependencies=[
        Depends(
            rate_limit_dependency(
                scope="multimodal_analyze",
                limit=settings.INFERENCE_RATE_LIMIT_REQUESTS,
                window_seconds=settings.INFERENCE_RATE_LIMIT_WINDOW_SECONDS,
            )
        )
    ],
)
async def analyze_multimodal(
    request: MultimodalGatewayRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MultimodalGatewayResponse:
    """
    Executes the multimodal intelligence pipeline for arbitrary or preliminary inputs:
    - Normalizes vernacular Indic text (M9.4)
    - Cross-modal evidence consistency evaluation (M9.2)
    - Active clarification questions for ambiguous reports (M9.3)
    - Visual resolution auditing if before/after pairs are provided (M9.5)
    - Epistemic status is strictly SYSTEM_DERIVED.
    """
    if request.case_reference:
        try:
            case = await complaint_case_module.get_case(request.case_reference)
            # Enforce RBAC if case_reference is supplied
            if current_user.role == UserRole.CITIZEN.value and case.user_id != current_user.user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Citizens can only analyze their own cases.",
                )
            if current_user.role == UserRole.AUTHORITY.value:
                assigned_user_id = case.assignment.assigned_to_user_id if case.assignment else None
                if assigned_user_id and assigned_user_id != current_user.user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Authorities can only analyze cases assigned to them.",
                    )
        except complaint_case_module.ComplaintCaseNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case '{request.case_reference}' was not found.",
            )

    gateway_service = get_multimodal_gateway_service()
    try:
        return gateway_service.process(request)
    except Exception as exc:
        logger.error("Multimodal analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Multimodal pipeline processing failed: {str(exc)}",
        )


@router.post(
    "/cases/{reference_id}/analyze",
    response_model=MultimodalGatewayResponse,
    summary="Execute multimodal pipeline bound to an existing complaint case",
    dependencies=[
        Depends(
            rate_limit_dependency(
                scope="multimodal_case_analyze",
                limit=settings.INFERENCE_RATE_LIMIT_REQUESTS,
                window_seconds=settings.INFERENCE_RATE_LIMIT_WINDOW_SECONDS,
            )
        )
    ],
)
async def analyze_case_multimodal(
    reference_id: str,
    request: MultimodalGatewayRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MultimodalGatewayResponse:
    """
    Executes multimodal pipeline for an existing case in CVKI persistence.
    Strictly verifies ownership or authority assignment before execution.
    """
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    # 1. Authority Access Control
    if current_user.role == UserRole.AUTHORITY.value:
        assigned_user_id = case.assignment.assigned_to_user_id if case.assignment else None
        if assigned_user_id and assigned_user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authorities can only analyze cases assigned to them.",
            )

    # 2. Citizen Access Control
    elif current_user.role == UserRole.CITIZEN.value:
        if case.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Citizens can only analyze their own cases.",
            )

    # Override case_reference from URL
    request_copy = request.model_copy(update={"case_reference": reference_id})
    gateway_service = get_multimodal_gateway_service()
    try:
        return gateway_service.process(request_copy)
    except Exception as exc:
        logger.error("Case multimodal analysis failed for %s: %s", reference_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Case multimodal analysis failed: {str(exc)}",
        )
