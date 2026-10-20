import base64
from io import BytesIO
import logging
import warnings

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.schemas.detection import DetectionResponse
from app.services.computer_vision import ModelUnavailableError, cv_model_service
from app.services.cv.runtime import cv_runtime_service

router = APIRouter()
logger = logging.getLogger("cvki.api.detection")
_SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


@router.post(
    "/predict",
    response_model=DetectionResponse,
    summary="Detect civic problems in an uploaded image",
    dependencies=[
        Depends(rate_limit_dependency(
            scope="inference",
            limit=settings.INFERENCE_RATE_LIMIT_REQUESTS,
            window_seconds=settings.INFERENCE_RATE_LIMIT_WINDOW_SECONDS,
        ))
    ],
)
async def predict_image(file: UploadFile = File(...)) -> DetectionResponse:
    """Validate one image upload and run inference using the model-agnostic CV runtime."""
    if not cv_runtime_service.is_loaded and not cv_model_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Detection model is unavailable.",
        )

    content = await file.read(settings.MAX_IMAGE_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )
    if len(content) > settings.MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The uploaded image exceeds the maximum allowed size.",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as verified_image:
                if verified_image.format not in _SUPPORTED_IMAGE_FORMATS:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="Unsupported image format. Use JPG, PNG, or WEBP.",
                    )
                if verified_image.width * verified_image.height > settings.MAX_IMAGE_PIXELS:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="The uploaded image dimensions exceed the maximum allowed size.",
                    )
                verified_image.verify()
            with Image.open(BytesIO(content)) as image:
                image = image.convert("RGB")
                detections = cv_model_service.predict(image)
                annotated_image = cv_model_service.annotate_image(image, detections)
                output = BytesIO()
                annotated_image.save(output, format="PNG")
                annotated_data_url = (
                    "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
                )
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a readable image.",
        )
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The uploaded image dimensions exceed the maximum allowed size.",
        )
    except ModelUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Detection model is unavailable.",
        )
    except Exception as exc:
        logger.error("Image inference failed (error_type=%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image inference failed.",
        )

    return DetectionResponse(
        success=True,
        model_version=settings.YOLO_MODEL_VERSION,
        total_detections=len(detections),
        detections=detections,
        annotated_image=annotated_data_url,
    )