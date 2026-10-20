"""
CVKI Research v2.x - R0 Environment Capture
Captures truthful system, library, hardware, and git state without fabricating missing metadata.
"""

import importlib.metadata
import os
import platform
import subprocess
import sys
from typing import Any


def get_git_revision() -> str:
    """Returns current git commit hash if available, or 'unknown'. Never creates a commit."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        commit = res.stdout.strip()
        return commit if commit else "unknown"
    except Exception:
        return "unknown"


def get_package_version(package_name: str) -> str:
    """Returns installed package version or 'unknown' if not installed."""
    try:
        return importlib.metadata.version(package_name)
    except Exception:
        return "unknown"


def capture_environment() -> dict[str, Any]:
    """
    Captures complete execution environment metadata without guessing.
    Unknown or unavailable fields are recorded as 'unknown'.
    """
    # Hardware & OS
    os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
    cpu_info = platform.processor() or "unknown"
    python_ver = sys.version.split()[0]

    # CUDA / GPU inspection via torch if available
    cuda_available = "unknown"
    cuda_version = "unknown"
    gpu_devices = []
    try:
        import torch
        cuda_available = str(torch.cuda.is_available())
        if torch.cuda.is_available():
            cuda_version = str(torch.version.cuda) or "unknown"
            gpu_devices = [
                torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())
            ]
        else:
            cuda_version = "N/A (CPU only)"
            gpu_devices = ["None"]
    except Exception:
        pass

    # Library versions
    libraries = {
        "torch": get_package_version("torch"),
        "torchvision": get_package_version("torchvision"),
        "ultralytics": get_package_version("ultralytics"),
        "numpy": get_package_version("numpy"),
        "opencv-python": get_package_version("opencv-python"),
        "scikit-learn": get_package_version("scikit-learn"),
        "transformers": get_package_version("transformers"),
        "pydantic": get_package_version("pydantic"),
        "fastapi": get_package_version("fastapi"),
        "pyyaml": get_package_version("pyyaml"),
    }

    git_commit = get_git_revision()

    return {
        "python_version": python_ver,
        "os": os_info,
        "architecture": platform.machine(),
        "cpu": cpu_info,
        "cuda_available": cuda_available,
        "cuda_version": cuda_version,
        "gpu_devices": gpu_devices,
        "git_commit": git_commit,
        "libraries": libraries,
    }
