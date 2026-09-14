from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.services.computer_vision import cv_model_service

router = APIRouter()


@router.get("/status", summary="Get Computer Vision Model Status")
def get_model_status():
    """
    Returns the current operational and readiness status of the loaded YOLO model.
    Exposes safe model metadata (version, class mapping, readiness) without
    revealing internal server filesystem paths.
    """
    model_status = cv_model_service.get_model_status()
    
    if not model_status.get("loaded", False):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=model_status
        )
        
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=model_status
    )
