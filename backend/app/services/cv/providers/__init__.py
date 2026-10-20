"""
CVKI Computer Vision Providers Package.
Hosts concrete model engine implementations conforming to CVInferenceProvider.
"""

from app.services.cv.providers.m113_yolo_provider import M113YOLOProvider

__all__ = ["M113YOLOProvider"]
