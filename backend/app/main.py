import logging
import hmac
import re
import time
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.v1.admin import router as admin_router
from app.api.v1.detection import router as detection_router
from app.api.v1.authority import router as authority_router
from app.api.v1.auth import router as auth_router
from app.api.v1.complaint import router as complaint_router
from app.api.v1.location import router as location_router
from app.api.v1.model import router as model_router
from app.api.v1.nlp import router as nlp_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.priority import router as priority_router
from app.core.config import settings
from app.core.csrf import verify_csrf_token
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.request_limits import RequestBodySizeLimitMiddleware
from app.core.request_context import RequestContext, current_request_context
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
    Loads the YOLO model once at application startup into shared service memory,
    and initializes the shared MongoDB connection pool.
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

    db_success = await connect_to_mongo()
    if db_success:
        logger.info("MongoDB persistence layer initialized and ready.")
    else:
        logger.warning(
            "MongoDB persistence layer failed to connect during startup. "
            "Complaint case endpoints will report 503 Service Unavailable."
        )

    yield

    logger.info("Shutting down CVKI backend services...")
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Civic Vision & Knowledge Intelligence platform",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(RequestBodySizeLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = [
        {
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "Invalid request."),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    started_at = getattr(request.state, "request_started_at", time.perf_counter())
    duration_ms = (time.perf_counter() - started_at) * 1000
    logger.error(
        "Unhandled request failure (request_id=%s, method=%s, path=%s, error_type=%s, duration_ms=%.2f).",
        request_id,
        request.method,
        request.url.path,
        type(exc).__name__,
        duration_ms,
    )
    response = JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred."},
    )
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_cookie_authenticated_requests(request, call_next):
    candidate_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        candidate_request_id
        if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate_request_id)
        else uuid4().hex
    )
    started_at = time.perf_counter()
    request.state.request_id = request_id
    request.state.request_started_at = started_at
    client_ip = request.client.host if request.client else None
    request_context_token = current_request_context.set(
        RequestContext(
            request_id=request_id,
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent"),
        )
    )

    is_auth_bootstrap = request.url.path in {
        f"{settings.API_V1_STR}/auth/register",
        f"{settings.API_V1_STR}/auth/login",
    }
    try:
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not is_auth_bootstrap:
            auth_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
            if auth_token and not request.headers.get("Authorization"):
                csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME, "")
                csrf_header = request.headers.get("X-CSRF-Token", "")
                if (
                    not csrf_cookie
                    or not csrf_header
                    or not hmac.compare_digest(csrf_cookie, csrf_header)
                    or not verify_csrf_token(auth_token, csrf_cookie)
                ):
                    response = JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF validation failed."},
                    )
                else:
                    response = await call_next(request)
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request completed (request_id=%s, method=%s, path=%s, status=%s, duration_ms=%.2f).",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started_at) * 1000,
        )
        return response
    finally:
        current_request_context.reset(request_context_token)


# Include routers
# Health check: GET /api/health
app.include_router(health_router, prefix="/api", tags=["health"])

# Model management: GET /api/v1/model/status and GET /api/model/status
app.include_router(model_router, prefix=f"{settings.API_V1_STR}/model", tags=["model"])
app.include_router(model_router, prefix="/api/model", tags=["model"])
app.include_router(detection_router, prefix=f"{settings.API_V1_STR}/detection", tags=["detection"])
app.include_router(location_router, prefix=f"{settings.API_V1_STR}/location", tags=["location"])
app.include_router(authority_router, prefix=f"{settings.API_V1_STR}/authority", tags=["authority"])
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(admin_router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(complaint_router, prefix=f"{settings.API_V1_STR}/complaint", tags=["complaint"])
app.include_router(nlp_router, prefix=f"{settings.API_V1_STR}/nlp", tags=["nlp"])
app.include_router(priority_router, prefix=f"{settings.API_V1_STR}/priority", tags=["priority"])
app.include_router(notifications_router, prefix=f"{settings.API_V1_STR}/notifications", tags=["notifications"])


@app.get("/")
def read_root():
    return {
        "message": "Welcome to CVKI Backend API. Visit /docs for documentation.",
        "service": "CVKI backend",
        "version": "0.2.0",
    }