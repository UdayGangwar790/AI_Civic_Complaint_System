from fastapi import APIRouter, status

from app.schemas.priority import PriorityScoreRequest, PriorityScoreResponse
from app.services.priority import calculate_priority_score

router = APIRouter()


@router.post(
    "/score",
    response_model=PriorityScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute transparent civic priority and risk intelligence score",
)
def compute_priority_score(request: PriorityScoreRequest) -> PriorityScoreResponse:
    """
    Computes an explainable civic priority score (0-100) and risk level (P1-P4)
    combining issue hazard type, NLP textual risk indicators, duplicate reports,
    location context, and detection confidence.
    """
    return calculate_priority_score(request)
