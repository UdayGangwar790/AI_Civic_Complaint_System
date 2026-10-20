"""
CVKI Research v2.x - R1 Dataset QA & Data Quality Engine
Provides comprehensive file validation, exact duplicate detection, near-duplicate hashing,
annotation validation, visual QA, hard negative tracking, leakage auditing, and privacy review.
"""

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Optional
import numpy as np
from PIL import Image, ImageStat

# Canonical 3 target classes for CVKI baseline / D1
ALLOWED_CLASS_IDS = {0, 1, 2}
TARGET_CLASS_NAMES = {
    0: "open_damaged_manhole",
    1: "damaged_missing_road_sign",
    2: "road_waterlogging",
}

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


# ==============================================================================
# R1.1 Sourcing & Licensing Validation
# ==============================================================================

@dataclass
class SourceLicenseRecord:
    source_id: str
    source_name: str
    source_url: str
    provider: str
    license: str
    license_url: str
    collection_date: str
    geographic_scope: str
    image_count: int
    class_scope: list[str]
    usage_permission: str  # PERMITTED_RESEARCH, PERMITTED_COMMERCIAL, QUARANTINED, UNKNOWN
    attribution_requirement: bool
    notes: str = ""

    def is_admissible(self) -> bool:
        """Only explicitly permitted research/open licenses are admitted to D1."""
        return self.usage_permission in ("PERMITTED_RESEARCH", "PERMITTED_COMMERCIAL")


# ==============================================================================
# R1.6 File Validation
# ==============================================================================

@dataclass
class FileValidationResult:
    image_path: str
    file_size_bytes: int
    width: int
    height: int
    format: str
    sha256: str
    status: str  # VALID, REJECTED, QUARANTINED
    reason: str = ""


def validate_image_file(file_path: Path | str, min_dimension: int = 64) -> FileValidationResult:
    """Validates file integrity, dimensions, format, and readable headers."""
    p = Path(file_path)
    if not p.is_file():
        return FileValidationResult(
            image_path=str(p), file_size_bytes=0, width=0, height=0, format="UNKNOWN",
            sha256="", status="REJECTED", reason="File does not exist or is not a file."
        )

    file_size = p.stat().st_size
    if file_size == 0:
        return FileValidationResult(
            image_path=str(p), file_size_bytes=0, width=0, height=0, format="UNKNOWN",
            sha256="", status="REJECTED", reason="Zero-byte empty file."
        )

    # Compute SHA-256
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    file_sha = hasher.hexdigest()

    # Extension check
    ext = p.suffix.lower()
    if ext not in VALID_IMAGE_EXTENSIONS:
        return FileValidationResult(
            image_path=str(p), file_size_bytes=file_size, width=0, height=0, format=ext,
            sha256=file_sha, status="REJECTED", reason=f"Unsupported format extension '{ext}'."
        )

    # Image open & header check
    try:
        with Image.open(p) as img:
            img.verify()  # Verifies file integrity
        # Re-open for size (verify closes or invalidates image state)
        with Image.open(p) as img:
            w, h = img.size
            fmt = img.format or ext.replace(".", "").upper()

            if w < min_dimension or h < min_dimension:
                return FileValidationResult(
                    image_path=str(p), file_size_bytes=file_size, width=w, height=h, format=fmt,
                    sha256=file_sha, status="REJECTED",
                    reason=f"Extremely small dimensions ({w}x{h} < {min_dimension}px minimum)."
                )

            return FileValidationResult(
                image_path=str(p), file_size_bytes=file_size, width=w, height=h, format=fmt,
                sha256=file_sha, status="VALID", reason="Image file is valid."
            )
    except Exception as e:
        return FileValidationResult(
            image_path=str(p), file_size_bytes=file_size, width=0, height=0, format="CORRUPTED",
            sha256=file_sha, status="REJECTED", reason=f"Corrupted image header or unreadable data: {str(e)}"
        )


# ==============================================================================
# R1.7 Exact Duplicate Detection (SHA-256)
# ==============================================================================

class ExactDuplicateDetector:
    """Detects and groups bitwise identical files using SHA-256."""

    def __init__(self):
        self._sha_to_paths: dict[str, list[str]] = {}

    def register(self, file_path: str, sha256: str) -> None:
        if sha256 not in self._sha_to_paths:
            self._sha_to_paths[sha256] = []
        self._sha_to_paths[sha256].append(file_path)

    def get_duplicate_groups(self) -> dict[str, list[str]]:
        """Returns map of sha256 -> list of identical duplicate paths (groups > 1)."""
        return {sha: paths for sha, paths in self._sha_to_paths.items() if len(paths) > 1}


# ==============================================================================
# R1.8 Near-Duplicate Detection (dHash / Perceptual Hash)
# ==============================================================================

def compute_dhash(image_path: Path | str, hash_size: int = 8) -> int:
    """
    Computes a 64-bit difference hash (dHash) for an image.
    Resizes to (hash_size + 1, hash_size), converts to grayscale, compares adjacent pixels.
    """
    with Image.open(image_path) as img:
        img_gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        if hasattr(img_gray, "get_flattened_data"):
            pixels = list(img_gray.get_flattened_data())
        else:
            pixels = list(np.array(img_gray).flatten())

    diff = []
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            diff.append(left > right)

    decimal_value = 0
    for idx, bit in enumerate(diff):
        if bit:
            decimal_value |= 1 << idx
    return decimal_value


def hamming_distance(hash1: int, hash2: int) -> int:
    """Returns Hamming distance between two 64-bit integer hashes."""
    x = hash1 ^ hash2
    return bin(x).count("1")


class NearDuplicateDetector:
    """
    Groups images with Hamming distance <= threshold.
    Flagged images are assigned status NEAR_DUPLICATE_REVIEW.
    """

    def __init__(self, distance_threshold: int = 4):
        self.distance_threshold = distance_threshold
        self._items: list[tuple[str, int]] = []  # (path, dhash)

    def register(self, file_path: str, dhash: int) -> None:
        self._items.append((file_path, dhash))

    def find_near_duplicate_pairs(self) -> list[dict[str, Any]]:
        pairs = []
        n = len(self._items)
        for i in range(n):
            path_a, hash_a = self._items[i]
            for j in range(i + 1, n):
                path_b, hash_b = self._items[j]
                dist = hamming_distance(hash_a, hash_b)
                if dist <= self.distance_threshold:
                    pairs.append({
                        "image_a": path_a,
                        "image_b": path_b,
                        "hamming_distance": dist,
                        "status": "NEAR_DUPLICATE_REVIEW",
                    })
        return pairs


# ==============================================================================
# R1.10 Annotation Validation
# ==============================================================================

@dataclass
class BoundingBox:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float


@dataclass
class AnnotationValidationResult:
    label_path: str
    is_valid: bool
    box_count: int
    boxes: list[BoundingBox] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_yolo_annotation_line(line: str) -> tuple[Optional[BoundingBox], Optional[str]]:
    """Validates a single YOLO bounding box line: <class_id> <x> <y> <w> <h>."""
    parts = line.strip().split()
    if not parts:
        return None, None
    if len(parts) != 5:
        return None, f"Expected 5 tokens per line, got {len(parts)}: '{line.strip()}'"

    try:
        class_id = int(parts[0])
        x = float(parts[1])
        y = float(parts[2])
        w = float(parts[3])
        h = float(parts[4])
    except ValueError as e:
        return None, f"Non-numeric value in line '{line.strip()}': {str(e)}"

    if math.isnan(x) or math.isnan(y) or math.isnan(w) or math.isnan(h):
        return None, "NaN detected in coordinates."
    if math.isinf(x) or math.isinf(y) or math.isinf(w) or math.isinf(h):
        return None, "Infinite value detected in coordinates."

    if class_id not in ALLOWED_CLASS_IDS:
        return None, f"Invalid class_id {class_id}. Target classes are strictly {ALLOWED_CLASS_IDS}."

    if not (0.0 <= x <= 1.0):
        return None, f"x_center {x} out of bounds [0, 1]."
    if not (0.0 <= y <= 1.0):
        return None, f"y_center {y} out of bounds [0, 1]."
    if not (0.0 < w <= 1.0):
        return None, f"width {w} out of bounds (0, 1]."
    if not (0.0 < h <= 1.0):
        return None, f"height {h} out of bounds (0, 1]."

    return BoundingBox(class_id, x, y, w, h), None


def validate_yolo_annotation_file(label_path: Path | str) -> AnnotationValidationResult:
    """Validates an entire YOLO .txt label file."""
    p = Path(label_path)
    if not p.is_file():
        return AnnotationValidationResult(label_path=str(p), is_valid=False, box_count=0, errors=["File not found."])

    boxes = []
    errors = []
    warnings = []

    with open(p, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for idx, line in enumerate(lines, start=1):
        line_clean = line.strip()
        if not line_clean:
            continue
        box, err = validate_yolo_annotation_line(line_clean)
        if err:
            errors.append(f"Line {idx}: {err}")
        elif box:
            boxes.append(box)

    return AnnotationValidationResult(
        label_path=str(p),
        is_valid=len(errors) == 0,
        box_count=len(boxes),
        boxes=boxes,
        errors=errors,
        warnings=warnings,
    )


# ==============================================================================
# R1.11 Visual Annotation QA
# ==============================================================================

@dataclass
class VisualQAFlag:
    box_index: int
    flag_type: str  # VERY_SMALL, VERY_LARGE, EDGE_TOUCHING, UNUSUAL_ASPECT
    description: str
    status: str = "REVIEW_REQUIRED"


def perform_visual_annotation_qa(
    boxes: list[BoundingBox],
    small_box_threshold: float = 0.002,   # Area < 0.2% of image
    large_box_threshold: float = 0.90,    # Area > 90% of image
    edge_tolerance: float = 0.001,
) -> list[VisualQAFlag]:
    """Inspects bounding box geometry for suspicious annotations."""
    flags = []
    for idx, box in enumerate(boxes):
        area = box.width * box.height
        if area < small_box_threshold:
            flags.append(VisualQAFlag(
                box_index=idx, flag_type="VERY_SMALL",
                description=f"Box area {area:.5f} is very small (< {small_box_threshold})."
            ))
        elif area > large_box_threshold:
            flags.append(VisualQAFlag(
                box_index=idx, flag_type="VERY_LARGE",
                description=f"Box area {area:.4f} covers > {large_box_threshold*100}% of image."
            ))

        # Edge touching check: [x - w/2, y - h/2, x + w/2, y + h/2]
        x1 = box.x_center - box.width / 2.0
        y1 = box.y_center - box.height / 2.0
        x2 = box.x_center + box.width / 2.0
        y2 = box.y_center + box.height / 2.0
        if x1 <= edge_tolerance or y1 <= edge_tolerance or x2 >= (1.0 - edge_tolerance) or y2 >= (1.0 - edge_tolerance):
            flags.append(VisualQAFlag(
                box_index=idx, flag_type="EDGE_TOUCHING",
                description=f"Box touches image edge: bounds=({x1:.3f}, {y1:.3f}, {x2:.3f}, {y2:.3f})."
            ))

        # Unusual aspect ratio check (e.g. extremely thin needle boxes)
        aspect = box.width / max(box.height, 1e-6)
        if aspect < 0.1 or aspect > 10.0:
            flags.append(VisualQAFlag(
                box_index=idx, flag_type="UNUSUAL_ASPECT",
                description=f"Unusual box aspect ratio w/h = {aspect:.2f}."
            ))

    return flags


# ==============================================================================
# R1.15 Image Quality Metrics
# ==============================================================================

@dataclass
class ImageQualityMetrics:
    image_path: str
    width: int
    height: int
    aspect_ratio: float
    file_size_bytes: int
    brightness_mean: float
    contrast_std: float
    blur_score: float  # Laplacian variance estimate
    quality_verdict: str  # ACCEPT, REVIEW, REJECT
    reason: str = ""


def estimate_blur_score(img_gray_arr: np.ndarray) -> float:
    """Estimates blur using discrete Laplacian kernel variance via numpy."""
    # Laplacian kernel 3x3
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    # Simple convolution via slicing
    h, w = img_gray_arr.shape
    if h < 3 or w < 3:
        return 0.0
    pad = np.pad(img_gray_arr, 1, mode="edge")
    lap = (
        pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:]
        - 4 * pad[1:-1, 1:-1]
    )
    return float(lap.var())


def analyze_image_quality(file_path: Path | str) -> ImageQualityMetrics:
    """Measures resolution, aspect ratio, brightness, contrast, and blur."""
    p = Path(file_path)
    file_size = p.stat().st_size
    with Image.open(p) as img:
        w, h = img.size
        aspect = round(w / max(h, 1), 3)

        # Grayscale stats
        gray = img.convert("L")
        stat = ImageStat.Stat(gray)
        mean_bright = round(stat.mean[0], 2)
        std_contrast = round(stat.stddev[0], 2)

        arr = np.array(gray, dtype=np.float32)
        blur_val = round(estimate_blur_score(arr), 2)

    verdict = "ACCEPT"
    reasons = []

    if mean_bright < 20.0:
        verdict = "REVIEW"
        reasons.append("Extremely dark scene (<20.0 mean brightness)")
    elif mean_bright > 240.0:
        verdict = "REVIEW"
        reasons.append("Extremely overexposed scene (>240.0 mean brightness)")

    if std_contrast < 15.0:
        verdict = "REVIEW"
        reasons.append("Low contrast scene (<15.0 stddev)")

    if blur_val < 30.0:
        verdict = "REVIEW"
        reasons.append("Potential motion or sensor blur (<30.0 Laplacian var)")

    return ImageQualityMetrics(
        image_path=str(p),
        width=w,
        height=h,
        aspect_ratio=aspect,
        file_size_bytes=file_size,
        brightness_mean=mean_bright,
        contrast_std=std_contrast,
        blur_score=blur_val,
        quality_verdict=verdict,
        reason="; ".join(reasons) if reasons else "Quality acceptable",
    )


# ==============================================================================
# R1.12 Hard Negatives Strategy
# ==============================================================================

@dataclass
class HardNegativeRecord:
    image_name: str
    target_class_confusion: str  # MANHOLE, ROAD_SIGN, WATERLOGGING
    negative_type: str            # CLOSED_MANHOLE, HEALTHY_SIGN, WET_ROAD_PUDDLE, SHADOW, REFLECTION
    source: str
    reason: str
    review_status: str            # VERIFIED_NEGATIVE, REVIEW_PENDING


# ==============================================================================
# R1.18 Privacy Review
# ==============================================================================

@dataclass
class PrivacyReviewResult:
    image_name: str
    privacy_status: str  # CLEAR, REVIEW_REQUIRED, REDACTION_REQUIRED, REJECT
    flags: list[str] = field(default_factory=list)
    notes: str = ""


# ==============================================================================
# R1.9 Data Leakage Prevention
# ==============================================================================

@dataclass
class LeakageAuditReport:
    total_images: int
    train_count: int
    val_count: int
    test_count: int
    exact_duplicates_across_splits: list[dict[str, Any]]
    near_duplicates_across_splits: list[dict[str, Any]]
    verdict: str  # NO KNOWN LEAKAGE or LEAKAGE_DETECTED


def audit_split_leakage(
    splits: dict[str, list[dict[str, Any]]],  # split_name -> list of records with path, sha256, dhash
    near_dup_threshold: int = 4,
) -> LeakageAuditReport:
    """
    Audits split assignments for exact duplicate or near-duplicate leakage.
    Guarantees no correlated samples cross train/val/test boundaries.
    """
    exact_cross_leakage = []
    near_cross_leakage = []

    # Map sha -> list of (split, path)
    sha_map: dict[str, list[tuple[str, str]]] = {}
    dhash_list: list[tuple[str, str, int]] = []  # (split, path, dhash)

    total_imgs = 0
    counts = {"train": 0, "val": 0, "test": 0}

    for split_name, items in splits.items():
        counts[split_name] = len(items)
        total_imgs += len(items)
        for item in items:
            sha = item["sha256"]
            path = item["image_path"]
            if sha not in sha_map:
                sha_map[sha] = []
            sha_map[sha].append((split_name, path))

            if "dhash" in item:
                dhash_list.append((split_name, path, item["dhash"]))

    # Check exact SHA across different splits
    for sha, occurrences in sha_map.items():
        splits_present = {occ[0] for occ in occurrences}
        if len(splits_present) > 1:
            exact_cross_leakage.append({
                "sha256": sha,
                "splits_involved": list(splits_present),
                "occurrences": [{"split": s, "path": p} for s, p in occurrences],
            })

    # Check near duplicates across different splits
    m = len(dhash_list)
    for i in range(m):
        split_a, path_a, hash_a = dhash_list[i]
        for j in range(i + 1, m):
            split_b, path_b, hash_b = dhash_list[j]
            if split_a != split_b:
                dist = hamming_distance(hash_a, hash_b)
                if dist <= near_dup_threshold:
                    near_cross_leakage.append({
                        "split_a": split_a,
                        "path_a": path_a,
                        "split_b": split_b,
                        "path_b": path_b,
                        "hamming_distance": dist,
                    })

    verdict = "NO KNOWN LEAKAGE" if (not exact_cross_leakage and not near_cross_leakage) else "LEAKAGE_DETECTED"

    return LeakageAuditReport(
        total_images=total_imgs,
        train_count=counts.get("train", 0),
        val_count=counts.get("val", 0),
        test_count=counts.get("test", 0),
        exact_duplicates_across_splits=exact_cross_leakage,
        near_duplicates_across_splits=near_cross_leakage,
        verdict=verdict,
    )
