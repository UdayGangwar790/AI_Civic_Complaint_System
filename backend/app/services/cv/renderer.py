"""
CVKI - Civic Vision & Knowledge Intelligence
Module 8.6: Computer Vision Annotation Renderer

Renders standardized bounding boxes and classification labels onto visual artifacts.
Completely decoupled from model execution engines or deep learning frameworks.
Produces Base64 PNG Data URLs for presentation layers and audit dashboards.
"""

import base64
from io import BytesIO
from typing import Any, Union
from PIL import Image, ImageDraw

from app.services.cv.base_provider import StandardBoundingBox, StandardDetection

# Visual styling tokens for civic hazard overlays
DEFAULT_OUTLINE_COLOR = (255, 64, 64)       # High-visibility crimson
DEFAULT_FILL_COLOR = (255, 64, 64)
DEFAULT_TEXT_COLOR = (255, 255, 255)
DEFAULT_BOX_WIDTH = 3


def render_detections(
    image: Image.Image,
    detections: list[Union[StandardDetection, dict[str, Any]]],
    outline_color: tuple[int, int, int] = DEFAULT_OUTLINE_COLOR,
    box_width: int = DEFAULT_BOX_WIDTH,
) -> Image.Image:
    """
    Renders standardized detections onto an in-memory RGB copy of the provided image.
    Accepts both StandardDetection pydantic objects and legacy detection dictionaries.
    """
    annotated = image.copy().convert("RGB")
    draw = ImageDraw.Draw(annotated)
    img_width, img_height = annotated.size

    for det in detections:
        # Extract coordinates and label safely from StandardDetection or dict
        if isinstance(det, StandardDetection):
            x1, y1 = det.bbox.x1, det.bbox.y1
            x2, y2 = det.bbox.x2, det.bbox.y2
            class_name = det.class_name
            confidence = det.confidence
        elif isinstance(det, dict):
            bbox = det.get("bbox", {})
            x1 = int(bbox.get("x1", 0))
            y1 = int(bbox.get("y1", 0))
            x2 = int(bbox.get("x2", 0))
            y2 = int(bbox.get("y2", 0))
            class_name = str(det.get("class_name", "unknown"))
            confidence = float(det.get("confidence", 0.0))
        else:
            continue

        # Constrain to image canvas
        clamped_x1 = max(0, min(x1, img_width))
        clamped_y1 = max(0, min(y1, img_height))
        clamped_x2 = max(0, min(x2, img_width))
        clamped_y2 = max(0, min(y2, img_height))

        if clamped_x1 >= clamped_x2 or clamped_y1 >= clamped_y2:
            continue

        label_text = f"{class_name} {confidence:.2f}"

        # Draw bounding rectangle
        draw.rectangle(
            (clamped_x1, clamped_y1, clamped_x2, clamped_y2),
            outline=outline_color,
            width=box_width,
        )

        # Measure label typography
        text_bbox = draw.textbbox((0, 0), label_text)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        # Position label tag
        tag_y = clamped_y1 - text_h - 4 if clamped_y1 >= text_h + 4 else clamped_y1
        draw.rectangle(
            (clamped_x1, tag_y, clamped_x1 + text_w + 6, tag_y + text_h + 4),
            fill=DEFAULT_FILL_COLOR,
        )
        draw.text((clamped_x1 + 3, tag_y + 2), label_text, fill=DEFAULT_TEXT_COLOR)

    return annotated


def render_annotated_png_data_url(
    image: Image.Image,
    detections: list[Union[StandardDetection, dict[str, Any]]],
) -> str:
    """
    Renders detections and returns a standard data URL (data:image/png;base64,...)
    compatible with frontend web clients and audit storage.
    """
    annotated = render_detections(image, detections)
    buf = BytesIO()
    annotated.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64_str}"
