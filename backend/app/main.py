import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.model import router as model_router
from app.core.config import settings
from app.services.computer_vision import cv_model_service

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cvki.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Loads the YOLO model once at application startup into shared service memory.
    """
    logger.info("Initializing CVKI backend services...")
    load_success = cv_model_service.load_model()
    if load_success:
        logger.info("YOLO model initialized and ready for requests.")
    else:
        logger.warning(
            "YOLO model failed to load during startup. "
            "Model status endpoint will report 503 Service Unavailable."
        )
    yield
    logger.info("Shutting down CVKI backend services...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Civic Vision & Knowledge Intelligence platform",
    version="0.2.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# Health check: GET /api/health
app.include_router(health_router, prefix="/api", tags=["health"])

# Model management: GET /api/v1/model/status and GET /api/model/status
app.include_router(model_router, prefix=f"{settings.API_V1_STR}/model", tags=["model"])
app.include_router(model_router, prefix="/api/model", tags=["model"])


@app.get("/")
def read_root():
    return {
        "message": "Welcome to CVKI Backend API. Visit /docs for documentation.",
        "service": "CVKI backend",
        "version": "0.2.0",
    }