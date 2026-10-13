from fastapi import APIRouter, status

from app.schemas.nlp import NLPAnalysisRequest, NLPAnalysisResponse
from app.services.nlp import analyze_complaint_text

router = APIRouter()


@router.post(
    "/analyze",
    response_model=NLPAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze citizen complaint text for civic intelligence",
)
def analyze_nlp_complaint(request: NLPAnalysisRequest) -> NLPAnalysisResponse:
    """
    Analyzes citizen complaint text across English, Hindi, and Hinglish.
    Extracts issue classification, keywords, severity signals, risk signals,
    and location entities with explainable provenance.
    """
    return analyze_complaint_text(request)
