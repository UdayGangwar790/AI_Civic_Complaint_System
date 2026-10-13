from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.database import is_mongo_healthy
from app.services.computer_vision import cv_model_service

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "CVKI backend",
    }


@router.get("/ready")
async def readiness_check():
    database_ready = await is_mongo_healthy()
    model_ready = cv_model_service.is_loaded
    ready = database_ready and model_ready
    response = {
        "status": "ready" if ready else "not_ready",
        "service": "CVKI backend",
        "dependencies": {
            "database": "available" if database_ready else "unavailable",
            "model": "available" if model_ready else "unavailable",
        },
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response,
    )