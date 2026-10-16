from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AuthenticatedUser, get_current_user
from app.models.roles import UserRole
from app.schemas.provenance import CaseProvenanceResponse
import app.services.complaint_case as complaint_case_module
from app.services.provenance_engine import get_provenance_engine

router = APIRouter()


@router.get(
    "/cases/{reference_id}",
    response_model=CaseProvenanceResponse,
    summary="Get comprehensive evidence provenance chain for a civic complaint case",
)
async def get_case_provenance(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CaseProvenanceResponse:
    """
    Retrieves the complete evidence provenance chain for an existing complaint case.
    Strictly enforces RBAC:
    - Citizen: only accessible by the case owner (403 for other citizens).
    - Authority: only accessible if the case is assigned to that authority (403 for unassigned).
    - Admin: city-wide provenance access.
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
        if assigned_user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authorities can only view provenance for cases assigned to them.",
            )

    # 2. Citizen Access Control
    elif current_user.role == UserRole.CITIZEN.value:
        if case.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Citizens can only view provenance for their own cases.",
            )

    # 3. Admin has unrestricted access

    engine = get_provenance_engine()
    provenance_response = engine.generate_case_provenance_chain(case)

    # For citizen role, mask internal reporter IDs or internal audit notes if present in metadata
    if current_user.role == UserRole.CITIZEN.value:
        sanitized_claims = []
        for claim in provenance_response.claims:
            c_copy = claim.model_copy(deep=True)
            # Remove any internal user IDs or emails from metadata
            c_copy.metadata.pop("user_id", None)
            c_copy.metadata.pop("email", None)
            c_copy.metadata.pop("assigned_to_user_id", None)
            sanitized_claims.append(c_copy)
        provenance_response.claims = sanitized_claims

    return provenance_response
