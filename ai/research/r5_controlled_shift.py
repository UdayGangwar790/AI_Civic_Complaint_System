"""Generate and evaluate deterministic R5 perturbations of the frozen D1 test split."""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import math
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from ultralytics import YOLO
from ultralytics.utils.metrics import ap_per_class

REPO_ROOT = Path(__file__).resolve().parents[2]
D1_ROOT = REPO_ROOT / "ai" / "research" / "datasets" / "D1"
R5_ROOT = REPO_ROOT / "ai" / "research" / "datasets" / "R5_controlled_shift"
R3_CHECKPOINT = (
    REPO_ROOT
    / "ai"
    / "research"
    / "experiments"
    / "R3"
    / "CVR2-CV-006"
    / "weights"
    / "best.pt"
)
R3_SHA256 = "72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28"
M113_SHA256 = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
MASTER_SEED = 20261019
PRIMARY_THRESHOLD = 0.100
SECONDARY_THRESHOLD = 0.250
EVALUATION_IOU = 0.50
PREDICTION_FLOOR = 0.001
NMS_IOU = 0.70
CLASS_NAMES = {
    0: "open_damaged_manhole",
    1: "damaged_missing_road_sign",
    2: "road_waterlogging",
}
TRANSFORM_PARAMETERS: dict[str, dict[str, dict[str, Any]]] = {
    "brightness": {
        "L1": {"factor": 0.80},
        "L2": {"factor": 0.60},
        "L3": {"factor": 0.40},
    },
    "contrast": {
        "L1": {"factor": 0.80},
        "L2": {"factor": 0.60},
        "L3": {"factor": 0.40},
    },
    "blur": {
        "L1": {"radius": 0.5},
        "L2": {"radius": 1.0},
        "L3": {"radius": 2.0},
    },
    "noise": {
        "L1": {"sigma": 5.0},
        "L2": {"sigma": 12.0},
        "L3": {"sigma": 24.0},
    },
    "jpeg": {
        "L1": {"quality": 75},
        "L2": {"quality": 45},
        "L3": {"quality": 20},
    },
    "shadow": {
        "L1": {"alpha": 0.12, "mask_blur": 24, "polygon_vertices": 6},
        "L2": {"alpha": 0.27, "mask_blur": 18, "polygon_vertices": 6},
        "L3": {"alpha": 0.45, "mask_blur": 12, "polygon_vertices": 6},
    },
    "rain": {
        "L1": {"streaks_per_640px": 35, "length": 12, "alpha": 45, "width": 1},
        "L2": {"streaks_per_640px": 70, "length": 20, "alpha": 70, "width": 1},
        "L3": {"streaks_per_640px": 120, "length": 30, "alpha": 100, "width": 2},
    },
}
EXCLUDED_TRANSFORMATIONS = {
    "crop_viewpoint": {
        "status": "EXCLUDED_INVALID_FOR_MEANINGFUL_LEVELS",
        "reason": (
            "The D1 held-out test box for d1_road_waterlogging_019.jpg has a 0.0078 "
            "minimum normalized border margin. A centered crop must retain at least "
            "0.9844 of each dimension to keep this box whole (at most 1.56% total "
            "dimension crop); this is too small to define three meaningful severity "
            "levels. Stronger crops truncate the annotated target."
        ),
        "source_image": "images/d1_road_waterlogging_019.jpg",
        "minimum_box_border_margin": 0.0078,
        "minimum_retained_fraction": 0.9844,
    }
}
IOU_THRESHOLDS = np.linspace(0.50, 0.95, 10, dtype=np.float32)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_seed(source_sha256: str, transform: str, severity: str) -> int:
    value = f"{MASTER_SEED}:{source_sha256}:{transform}:{severity}".encode("ascii")
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")


def read_yolo_labels(path: Path) -> list[tuple[int, float, float, float, float]]:
    boxes = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"{path}:{line_number}: expected five YOLO fields")
        class_id = int(fields[0])
        values = tuple(float(value) for value in fields[1:])
        if class_id not in CLASS_NAMES or not all(math.isfinite(value) for value in values):
            raise ValueError(f"{path}:{line_number}: invalid class or non-finite coordinate")
        x, y, width, height = values
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
            raise ValueError(f"{path}:{line_number}: normalized coordinates out of bounds")
        if x - width / 2 < 0 or x + width / 2 > 1 or y - height / 2 < 0 or y + height / 2 > 1:
            raise ValueError(f"{path}:{line_number}: bounding box extends outside the image")
        boxes.append((class_id, x, y, width, height))
    return boxes


def crop_yolo_labels(label_text: str, retained_fraction: float) -> str:
    if not 0 < retained_fraction <= 1:
        raise ValueError("retained_fraction must be in (0, 1]")
    margin = (1.0 - retained_fraction) / 2
    transformed = []
    for class_id, x, y, width, height in parse_yolo_label_text(label_text):
        left, top = x - width / 2, y - height / 2
        right, bottom = x + width / 2, y + height / 2
        tolerance = 1e-9
        if (
            left < margin - tolerance
            or top < margin - tolerance
            or right > 1 - margin + tolerance
            or bottom > 1 - margin + tolerance
        ):
            raise ValueError("crop would truncate a ground-truth box")
        new_x = (x - margin) / retained_fraction
        new_y = (y - margin) / retained_fraction
        new_width = width / retained_fraction
        new_height = height / retained_fraction
        transformed.append(
            f"{class_id} {new_x:.8f} {new_y:.8f} {new_width:.8f} {new_height:.8f}"
        )
    return "\n".join(transformed) + ("\n" if transformed else "")


def parse_yolo_label_text(
    label_text: str,
) -> list[tuple[int, float, float, float, float]]:
    parsed = []
    for line_number, line in enumerate(label_text.splitlines(), 1):
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"label line {line_number}: expected five YOLO fields")
        class_id = int(fields[0])
        values = tuple(float(value) for value in fields[1:])
        if class_id not in CLASS_NAMES or not all(math.isfinite(value) for value in values):
            raise ValueError(f"label line {line_number}: invalid class or coordinates")
        x, y, width, height = values
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
            raise ValueError(f"label line {line_number}: normalized coordinates out of bounds")
        if x - width / 2 < 0 or x + width / 2 > 1 or y - height / 2 < 0 or y + height / 2 > 1:
            raise ValueError(f"label line {line_number}: bounding box extends outside image")
        parsed.append((class_id, x, y, width, height))
    return parsed


def apply_transform(
    image: Image.Image,
    transform: str,
    severity: str,
    seed: int,
) -> Image.Image:
    params = TRANSFORM_PARAMETERS[transform][severity]
    rgb = image.convert("RGB")
    width, height = rgb.size
    rng = np.random.default_rng(seed)

    if transform == "brightness":
        return ImageEnhance.Brightness(rgb).enhance(float(params["factor"]))
    if transform == "contrast":
        return ImageEnhance.Contrast(rgb).enhance(float(params["factor"]))
    if transform == "blur":
        return rgb.filter(ImageFilter.GaussianBlur(radius=float(params["radius"])))
    if transform == "noise":
        pixels = np.asarray(rgb, dtype=np.float32)
        noise = rng.normal(0.0, float(params["sigma"]), size=pixels.shape)
        return Image.fromarray(np.clip(pixels + noise, 0, 255).astype(np.uint8), "RGB")
    if transform == "jpeg":
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=int(params["quality"]), optimize=False)
        buffer.seek(0)
        with Image.open(buffer) as compressed:
            return compressed.convert("RGB").copy()
    if transform == "shadow":
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        count = int(params["polygon_vertices"])
        points = [
            (int(rng.uniform(-0.15, 0.95) * width), int(rng.uniform(-0.15, 0.95) * height))
            for _ in range(count)
        ]
        draw.polygon(points, fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(float(params["mask_blur"])))
        alpha = np.asarray(mask, dtype=np.float32) * float(params["alpha"])
        pixels = np.asarray(rgb, dtype=np.float32) * (1.0 - alpha[..., None] / 255.0)
        return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")
    if transform == "rain":
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        scale = min(width, height) / 640
        count = max(1, round(int(params["streaks_per_640px"]) * scale))
        length = max(1, round(int(params["length"]) * scale))
        line_width = max(1, round(int(params["width"]) * scale))
        for _ in range(count):
            x = int(rng.integers(0, width))
            y = int(rng.integers(0, height))
            draw.line(
                (x, y, x - max(1, length // 3), min(height, y + length)),
                fill=(190, 205, 220, int(params["alpha"])),
                width=line_width,
            )
        return Image.alpha_composite(rgb.convert("RGBA"), overlay).convert("RGB")
    if transform == "crop":
        fraction = float(params["retained_fraction"])
        crop_width = round(width * fraction)
        crop_height = round(height * fraction)
        left = (width - crop_width) // 2
        top = (height - crop_height) // 2
        cropped = rgb.crop((left, top, left + crop_width, top + crop_height))
        return cropped.resize((width, height), Image.Resampling.LANCZOS)
    raise ValueError(f"Unknown transformation: {transform}")


def _test_sources() -> list[tuple[Path, Path]]:
    entries = []
    for relative_path in (D1_ROOT / "splits" / "test.txt").read_text(encoding="utf-8").splitlines():
        if not relative_path.strip():
            continue
        image_path = D1_ROOT / relative_path.strip()
        label_path = D1_ROOT / "labels" / f"{image_path.stem}.txt"
        if not image_path.is_file() or not label_path.is_file():
            raise FileNotFoundError(f"Missing D1 test image or label: {image_path}")
        read_yolo_labels(label_path)
        entries.append((image_path, label_path))
    return entries


def generate_dataset(output_root: Path = R5_ROOT) -> tuple[Path, str]:
    if output_root.exists():
        raise FileExistsError(f"Refusing to overwrite existing R5 artifacts: {output_root}")
    sources = _test_sources()
    (output_root / "clean" / "images").mkdir(parents=True)
    (output_root / "clean" / "labels").mkdir()
    generated_at = datetime.now(timezone.utc).isoformat()
    source_records = []

    for image_path, label_path in sources:
        source_records.append(
            {
                "image_path": image_path,
                "label_path": label_path,
                "image_sha256": sha256_file(image_path),
                "label_sha256": sha256_file(label_path),
            }
        )

    records: list[dict[str, Any]] = []
    for source in source_records:
        image_path = source["image_path"]
        label_path = source["label_path"]
        relative_image = image_path.relative_to(D1_ROOT).as_posix()
        source_split = "test"
        source_label = label_path.relative_to(D1_ROOT).as_posix()
        clean_image = output_root / "clean" / "images" / image_path.name
        clean_label = output_root / "clean" / "labels" / label_path.name
        shutil.copyfile(image_path, clean_image)
        shutil.copyfile(label_path, clean_label)
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
            dimensions = list(image.size)
            for transform, severity_map in TRANSFORM_PARAMETERS.items():
                for severity, params in severity_map.items():
                    seed = derive_seed(source["image_sha256"], transform, severity)
                    variant_label_text = label_path.read_text(encoding="utf-8")
                    if transform == "crop":
                        variant_label_text = crop_yolo_labels(
                            variant_label_text, float(params["retained_fraction"])
                        )
                    variant = apply_transform(image, transform, severity, seed)
                    output_image = (
                        output_root / transform / severity / "images" / image_path.name
                    )
                    output_label = (
                        output_root / transform / severity / "labels" / label_path.name
                    )
                    output_image.parent.mkdir(parents=True, exist_ok=True)
                    output_label.parent.mkdir(parents=True, exist_ok=True)
                    variant.save(output_image, format="JPEG", quality=95, optimize=False)
                    output_label.write_text(variant_label_text, encoding="utf-8")
                    records.append(
                        _mapping_record(
                            source,
                            relative_image,
                            source_split,
                            source_label,
                            transform,
                            severity,
                            seed,
                            params,
                            output_image,
                            output_label,
                            output_root,
                            dimensions,
                            generated_at,
                        )
                    )
        records.append(
            _mapping_record(
                source,
                relative_image,
                source_split,
                source_label,
                "clean",
                "clean",
                None,
                {},
                clean_image,
                clean_label,
                output_root,
                dimensions,
                generated_at,
            )
        )

    manifest = {
        "schema_version": "1.0",
        "dataset_id": "R5_controlled_shift",
        "data_type": "synthetic_controlled_perturbations_of_D1_research_test_images",
        "external_real_world_dataset": False,
        "source_dataset_id": "D1",
        "source_dataset_composite_sha256": _d1_composite_sha256(),
        "source_dataset_manifest_file_sha256": _d1_manifest_sha256(),
        "source_split": "test",
        "source_image_count": len(source_records),
        "transformed_image_count": len(records),
        "master_seed": MASTER_SEED,
        "excluded_transformations": EXCLUDED_TRANSFORMATIONS,
        "generation_timestamp": generated_at,
        "class_names": CLASS_NAMES,
        "records": records,
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_sha = sha256_file(manifest_path)
    (output_root / "MANIFEST.SHA256").write_text(f"{manifest_sha}  manifest.json\n", encoding="ascii")
    return manifest_path, manifest_sha


def _mapping_record(
    source: dict[str, Any],
    relative_image: str,
    source_split: str,
    source_label: str,
    transform: str,
    severity: str,
    seed: int | None,
    params: dict[str, Any],
    output_image: Path,
    output_label: Path,
    output_root: Path,
    dimensions: list[int],
    generated_at: str,
) -> dict[str, Any]:
    if transform == "clean":
        params = {"operation": "byte-for-byte copy of source image and label"}
    return {
        "source_image": relative_image,
        "source_split": source_split,
        "source_image_sha256": source["image_sha256"],
        "source_label": source_label,
        "source_label_sha256": source["label_sha256"],
        "transformation": transform,
        "severity": severity,
        "random_seed": seed,
        "parameters": params,
        "generated_image": output_image.relative_to(output_root).as_posix(),
        "generated_image_sha256": sha256_file(output_image),
        "generated_label": output_label.relative_to(output_root).as_posix(),
        "generated_label_sha256": sha256_file(output_label),
        "dimensions": dimensions,
        "generation_timestamp": generated_at,
    }


def _d1_manifest_sha256() -> str:
    manifest_path = D1_ROOT / "manifests" / "dataset_manifest.json"
    return sha256_file(manifest_path)


def _d1_composite_sha256() -> str:
    manifest_path = D1_ROOT / "manifests" / "dataset_manifest.json"
    return str(json.loads(manifest_path.read_text(encoding="utf-8"))["composite_sha256"])


def _box_iou(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)
    top_left = np.maximum(boxes_a[:, None, :2], boxes_b[None, :, :2])
    bottom_right = np.minimum(boxes_a[:, None, 2:], boxes_b[None, :, 2:])
    intersection_wh = np.clip(bottom_right - top_left, 0, None)
    intersection = intersection_wh[..., 0] * intersection_wh[..., 1]
    area_a = np.clip(boxes_a[:, 2] - boxes_a[:, 0], 0, None) * np.clip(
        boxes_a[:, 3] - boxes_a[:, 1], 0, None
    )
    area_b = np.clip(boxes_b[:, 2] - boxes_b[:, 0], 0, None) * np.clip(
        boxes_b[:, 3] - boxes_b[:, 1], 0, None
    )
    return intersection / np.maximum(area_a[:, None] + area_b[None, :] - intersection, 1e-9)


def _labels_to_xyxy(label_path: Path, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    labels = parse_yolo_label_text(label_path.read_text(encoding="utf-8"))
    boxes = []
    classes = []
    for class_id, x, y, box_width, box_height in labels:
        boxes.append(
            [
                (x - box_width / 2) * width,
                (y - box_height / 2) * height,
                (x + box_width / 2) * width,
                (y + box_height / 2) * height,
            ]
        )
        classes.append(class_id)
    return np.asarray(boxes, dtype=np.float32).reshape(-1, 4), np.asarray(classes, dtype=np.int64)


def _match_predictions(
    predictions: list[dict[str, Any]],
    labels: list[tuple[np.ndarray, np.ndarray]],
    strategy: str,
) -> np.ndarray:
    if strategy not in {"confidence", "iou"}:
        raise ValueError(f"Unsupported matching strategy: {strategy}")
    matches = np.zeros((len(predictions), len(IOU_THRESHOLDS)), dtype=bool)
    for image_index, (gt_boxes, gt_classes) in enumerate(labels):
        prediction_indices = [
            index for index, prediction in enumerate(predictions)
            if prediction["image_index"] == image_index
        ]
        for threshold_index, iou_threshold in enumerate(IOU_THRESHOLDS):
            used_gt: set[int] = set()
            if strategy == "confidence":
                ordered_predictions = sorted(
                    prediction_indices,
                    key=lambda index: -predictions[index]["confidence"],
                )
                for prediction_index in ordered_predictions:
                    prediction = predictions[prediction_index]
                    candidate_gt = [
                        gt_index
                        for gt_index, gt_class in enumerate(gt_classes)
                        if prediction["class_id"] == int(gt_class)
                        and gt_index not in used_gt
                    ]
                    if not candidate_gt:
                        continue
                    overlaps = _box_iou(
                        np.asarray([prediction["box"]], dtype=np.float32),
                        gt_boxes[candidate_gt],
                    )[0]
                    best_position = int(np.argmax(overlaps))
                    if float(overlaps[best_position]) >= float(iou_threshold):
                        matches[prediction_index, threshold_index] = True
                        used_gt.add(candidate_gt[best_position])
            elif strategy == "iou":
                prediction_boxes = np.asarray(
                    [predictions[index]["box"] for index in prediction_indices],
                    dtype=np.float32,
                ).reshape(-1, 4)
                overlap_matrix = _box_iou(gt_boxes, prediction_boxes)
                prediction_classes = np.asarray(
                    [predictions[index]["class_id"] for index in prediction_indices],
                    dtype=np.int64,
                )
                class_matches = gt_classes[:, None] == prediction_classes[None, :]
                overlap_matrix *= class_matches
                pairs = np.nonzero(overlap_matrix >= float(iou_threshold))
                candidates = np.column_stack(pairs)
                if candidates.shape[0] > 1:
                    candidates = candidates[
                        overlap_matrix[candidates[:, 0], candidates[:, 1]].argsort()[::-1]
                    ]
                    candidates = candidates[
                        np.unique(candidates[:, 1], return_index=True)[1]
                    ]
                    candidates = candidates[
                        np.unique(candidates[:, 0], return_index=True)[1]
                    ]
                for gt_index, local_prediction_index in candidates:
                    prediction_index = prediction_indices[int(local_prediction_index)]
                    matches[prediction_index, threshold_index] = True
    return matches


def _error_cases(
    predictions: list[dict[str, Any]],
    matches: np.ndarray,
    labels: list[tuple[np.ndarray, np.ndarray]],
    source_records: list[dict[str, Any]],
    threshold: float,
) -> list[dict[str, Any]]:
    selected = [
        index
        for index, prediction in enumerate(predictions)
        if prediction["confidence"] >= threshold
    ]
    matched_gt: dict[int, set[int]] = {}
    cases = []
    for index in selected:
        prediction = predictions[index]
        image_index = prediction["image_index"]
        if matches[index, 0]:
            gt_boxes, gt_classes = labels[image_index]
            candidates = [
                (gt_index, gt_box)
                for gt_index, (gt_box, gt_class) in enumerate(zip(gt_boxes, gt_classes))
                if prediction["class_id"] == int(gt_class)
                and gt_index not in matched_gt.setdefault(image_index, set())
            ]
            if candidates:
                overlaps = _box_iou(
                    np.asarray([prediction["box"]], dtype=np.float32),
                    np.asarray([box for _, box in candidates], dtype=np.float32),
                )[0]
                best_index = int(np.argmax(overlaps))
                if overlaps[best_index] >= EVALUATION_IOU:
                    matched_gt[image_index].add(candidates[best_index][0])
            continue
        record = source_records[image_index]
        cases.append(
            {
                "source_image": record["source_image"],
                "generated_image": record["generated_image"],
                "transformation": record["transformation"],
                "severity": record["severity"],
                "error_type": "FALSE_POSITIVE",
                "affected_class": CLASS_NAMES[prediction["class_id"]],
                "prediction": {
                    "class_id": prediction["class_id"],
                    "confidence": prediction["confidence"],
                    "xyxy": prediction["box"],
                },
                "ground_truth": [],
                "visual_failure_pattern": "Not manually reviewed; unmatched model box recorded.",
            }
        )
    for image_index, (gt_boxes, gt_classes) in enumerate(labels):
        record = source_records[image_index]
        for gt_index, (gt_box, gt_class) in enumerate(zip(gt_boxes, gt_classes)):
            if gt_index not in matched_gt.get(image_index, set()):
                cases.append(
                    {
                        "source_image": record["source_image"],
                        "generated_image": record["generated_image"],
                        "transformation": record["transformation"],
                        "severity": record["severity"],
                        "error_type": "FALSE_NEGATIVE",
                        "affected_class": CLASS_NAMES[int(gt_class)],
                        "prediction": None,
                        "ground_truth": {
                            "class_id": int(gt_class),
                            "xyxy": gt_box.tolist(),
                        },
                        "visual_failure_pattern": "Not manually reviewed; unmatched ground-truth box recorded.",
                    }
                )
    return cases


def _metric_counts(
    predictions: list[dict[str, Any]],
    matches: np.ndarray,
    labels: list[tuple[np.ndarray, np.ndarray]],
    confidence_threshold: float,
    ap_predictions: list[dict[str, Any]] | None = None,
    ap_matches: np.ndarray | None = None,
) -> dict[str, Any]:
    selected_indices = [
        index for index, prediction in enumerate(predictions)
        if prediction["confidence"] >= confidence_threshold
    ]
    gt_classes = np.concatenate([classes for _, classes in labels]) if labels else np.array([], dtype=np.int64)
    selected_matches = matches[selected_indices, 0] if selected_indices else np.array([], dtype=bool)
    selected = [predictions[index] for index in selected_indices]
    tp = int(selected_matches.sum())
    fp = len(selected) - tp
    fn = int(sum(len(classes) for _, classes in labels)) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    per_class: dict[str, Any] = {}
    ap_info: dict[int, dict[str, float]] = {}
    ap_predictions = predictions if ap_predictions is None else ap_predictions
    ap_matches = matches if ap_matches is None else ap_matches
    all_conf = np.asarray([item["confidence"] for item in ap_predictions], dtype=np.float32)
    pred_cls = np.asarray([item["class_id"] for item in ap_predictions], dtype=np.int64)
    ap_values = ap_per_class(
        ap_matches,
        all_conf,
        pred_cls,
        gt_classes,
        names=CLASS_NAMES,
    )
    ap_array = ap_values[5]
    ap_classes = ap_values[6]
    ap_info = {
        int(class_id): {
            "mAP50": float(ap_array[index, 0]),
            "mAP50_95": float(ap_array[index].mean()),
        }
        for index, class_id in enumerate(ap_classes)
    }
    for class_id, class_name in CLASS_NAMES.items():
        class_gt = int(sum(np.count_nonzero(classes == class_id) for _, classes in labels))
        class_candidates = [
            prediction
            for prediction in ap_predictions
            if prediction["class_id"] == class_id
        ]
        class_preds = [
            (index, prediction)
            for index, prediction in enumerate(predictions)
            if prediction["class_id"] == class_id
            and prediction["confidence"] >= confidence_threshold
        ]
        class_confidence = _confidence_statistics(
            [prediction for _, prediction in class_preds]
        )
        class_tp = sum(bool(matches[index, 0]) for index, _ in class_preds)
        class_fp = len(class_preds) - class_tp
        class_fn = class_gt - class_tp
        if class_gt == 0:
            per_class[class_name] = {
                "status": "INSUFFICIENT_SAMPLE",
                "ground_truth": 0,
                "TP": class_tp,
                "FP": class_fp,
                "FN": class_fn,
                "precision": None,
                "recall": None,
                "F1": None,
                "mAP50": None,
                "mAP50_95": None,
                "confidence_statistics": class_confidence,
                "candidate_confidence_statistics": _confidence_statistics(class_candidates),
            }
            continue
        class_precision = class_tp / (class_tp + class_fp) if class_tp + class_fp else 0.0
        class_recall = class_tp / class_gt
        class_f1 = (
            2 * class_precision * class_recall / (class_precision + class_recall)
            if class_precision + class_recall else 0.0
        )
        ap_metrics = ap_info.get(class_id, {"mAP50": 0.0, "mAP50_95": 0.0})
        per_class[class_name] = {
            "status": "VALID_SAMPLE",
            "ground_truth": class_gt,
            "TP": class_tp,
            "FP": class_fp,
            "FN": class_fn,
            "precision": class_precision,
            "recall": class_recall,
            "F1": class_f1,
            **ap_metrics,
            "confidence_statistics": class_confidence,
            "candidate_confidence_statistics": _confidence_statistics(class_candidates),
        }
    valid_classes = [
        metrics for metrics in per_class.values()
        if metrics["status"] == "VALID_SAMPLE"
    ]
    map50 = float(np.mean([item["mAP50"] for item in valid_classes])) if valid_classes else None
    map5095 = float(np.mean([item["mAP50_95"] for item in valid_classes])) if valid_classes else None
    macro_precision = float(np.mean([item["precision"] for item in valid_classes])) if valid_classes else None
    macro_recall = float(np.mean([item["recall"] for item in valid_classes])) if valid_classes else None
    macro_f1 = float(np.mean([item["F1"] for item in valid_classes])) if valid_classes else None
    return {
        "confidence_threshold": confidence_threshold,
        "IoU_threshold": EVALUATION_IOU,
        "image_count": len(labels),
        "ground_truth_box_count": int(len(gt_classes)),
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "F1": f1,
        "mAP50": map50,
        "mAP50_95": map5095,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_F1": macro_f1,
        "micro_precision": precision,
        "micro_recall": recall,
        "per_class": per_class,
        "confidence_statistics": _confidence_statistics(selected),
        "candidate_confidence_statistics": _confidence_statistics(ap_predictions),
    }


def _confidence_statistics(predictions: list[dict[str, Any]]) -> dict[str, float | int | None]:
    values = [float(item["confidence"]) for item in predictions]
    if not values:
        return {
            "prediction_count": 0,
            "mean": None,
            "median": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "prediction_count": len(values),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }


def _discover_conditions(dataset_root: Path) -> list[dict[str, Any]]:
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for record in manifest["records"]:
        rows.append(
            {
                "record": record,
                "image_path": dataset_root / record["generated_image"],
                "label_path": dataset_root / record["generated_label"],
            }
        )
    return rows


def _official_ap_validation(
    model: YOLO,
    condition_root: Path,
    condition_name: str,
) -> dict[str, Any]:
    data_yaml = (
        f'path: "{condition_root.as_posix()}"\n'
        "train: images\n"
        "val: images\n"
        "names:\n"
        "  0: open_damaged_manhole\n"
        "  1: damaged_missing_road_sign\n"
        "  2: road_waterlogging\n"
    )
    with NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        encoding="utf-8",
        delete=False,
    ) as stream:
        stream.write(data_yaml)
        data_yaml_path = Path(stream.name)
    try:
        with TemporaryDirectory(prefix="r5-ultralytics-", dir=condition_root) as output_dir:
            validation = model.val(
                data=str(data_yaml_path),
                split="val",
                imgsz=640,
                conf=PREDICTION_FLOOR,
                iou=NMS_IOU,
                max_det=300,
                batch=16,
                device="cpu",
                plots=False,
                save_json=False,
                project=output_dir,
                name=condition_name,
                exist_ok=True,
                verbose=False,
            )
    finally:
        data_yaml_path.unlink(missing_ok=True)

    class_indices = [int(value) for value in validation.box.ap_class_index]
    all_ap = np.asarray(validation.box.all_ap)
    per_class = {}
    for class_id, class_name in CLASS_NAMES.items():
        if class_id not in class_indices:
            per_class[class_name] = {
                "status": "INSUFFICIENT_SAMPLE",
                "mAP50": None,
                "mAP50_95": None,
            }
            continue
        ap_index = class_indices.index(class_id)
        per_class[class_name] = {
            "status": "VALID_SAMPLE",
            "mAP50": float(all_ap[ap_index, 0]),
            "mAP50_95": float(all_ap[ap_index].mean()),
        }
    return {
        "evaluator": "Ultralytics DetectionValidator",
        "ultralytics_version": importlib.metadata.version("ultralytics"),
        "confidence_floor": PREDICTION_FLOOR,
        "NMS_IoU_threshold": NMS_IOU,
        "mAP50": float(validation.box.map50),
        "mAP50_95": float(validation.box.map),
        "per_class": per_class,
    }


def evaluate_dataset(dataset_root: Path = R5_ROOT) -> dict[str, Any]:
    manifest_path = dataset_root / "manifest.json"
    manifest_sha = sha256_file(manifest_path)
    model = YOLO(str(R3_CHECKPOINT))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _discover_conditions(dataset_root):
        record = row["record"]
        condition = (record["transformation"], record["severity"])
        grouped.setdefault(condition, []).append(row)

    results_by_condition: dict[str, Any] = {}
    all_error_cases: list[dict[str, Any]] = []
    for (transform, severity), rows in grouped.items():
        image_paths = [row["image_path"] for row in rows]
        start = time.perf_counter()
        predictions_by_image = model.predict(
            source=[str(path) for path in image_paths],
            imgsz=640,
            conf=PREDICTION_FLOOR,
            iou=NMS_IOU,
            max_det=300,
            device="cpu",
            verbose=False,
        )
        wall_ms_per_image = (time.perf_counter() - start) * 1000 / max(len(rows), 1)
        predictions: list[dict[str, Any]] = []
        labels: list[tuple[np.ndarray, np.ndarray]] = []
        image_inference_ms = []
        for image_index, (row, result) in enumerate(zip(rows, predictions_by_image)):
            with Image.open(row["image_path"]) as opened:
                width, height = opened.size
            gt_boxes, gt_classes = _labels_to_xyxy(row["label_path"], width, height)
            labels.append((gt_boxes, gt_classes))
            image_inference_ms.append(float(result.speed.get("inference", 0.0)))
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            xyxy = boxes.xyxy.detach().cpu().numpy()
            confidences = boxes.conf.detach().cpu().numpy()
            classes = boxes.cls.detach().cpu().numpy().astype(int)
            for box, confidence, class_id in zip(xyxy, confidences, classes):
                predictions.append(
                    {
                        "image_index": image_index,
                        "source_image": row["record"]["source_image"],
                        "generated_image": row["record"]["generated_image"],
                        "box": [float(value) for value in box],
                        "confidence": float(confidence),
                        "class_id": int(class_id),
                    }
                )
        source_records = [row["record"] for row in rows]
        ap_matches = _match_predictions(predictions, labels, "iou")
        primary_predictions = [
            prediction for prediction in predictions
            if prediction["confidence"] >= PRIMARY_THRESHOLD
        ]
        secondary_predictions = [
            prediction for prediction in predictions
            if prediction["confidence"] >= SECONDARY_THRESHOLD
        ]
        primary_matches = _match_predictions(primary_predictions, labels, "confidence")
        secondary_matches = _match_predictions(secondary_predictions, labels, "confidence")
        primary = _metric_counts(
            primary_predictions,
            primary_matches,
            labels,
            PRIMARY_THRESHOLD,
            ap_predictions=predictions,
            ap_matches=ap_matches,
        )
        secondary = _metric_counts(
            secondary_predictions,
            secondary_matches,
            labels,
            SECONDARY_THRESHOLD,
            ap_predictions=predictions,
            ap_matches=ap_matches,
        )
        condition_root = (
            dataset_root / "clean"
            if transform == "clean"
            else dataset_root / transform / severity
        )
        official_ap = _official_ap_validation(
            model,
            condition_root,
            f"{transform}_{severity}",
        )
        primary["mAP50"] = official_ap["mAP50"]
        primary["mAP50_95"] = official_ap["mAP50_95"]
        secondary["mAP50"] = official_ap["mAP50"]
        secondary["mAP50_95"] = official_ap["mAP50_95"]
        for class_name, class_ap in official_ap["per_class"].items():
            primary["per_class"][class_name]["mAP50"] = class_ap["mAP50"]
            primary["per_class"][class_name]["mAP50_95"] = class_ap["mAP50_95"]
            secondary["per_class"][class_name]["mAP50"] = class_ap["mAP50"]
            secondary["per_class"][class_name]["mAP50_95"] = class_ap["mAP50_95"]
        errors = _error_cases(
            primary_predictions,
            primary_matches,
            labels,
            source_records,
            PRIMARY_THRESHOLD,
        )
        results_by_condition[f"{transform}:{severity}"] = {
            "transformation": transform,
            "severity": severity,
            "source_image_count": len(rows),
            "source_dataset": "D1",
            "source_split": "test",
            "generated_manifest_sha256": manifest_sha,
            "average_precision_evaluation": official_ap,
            "primary": primary,
            "secondary": secondary,
            "latency_ms_per_image": {
                "mean_model_inference": float(np.mean(image_inference_ms)) if image_inference_ms else None,
                "median_model_inference": float(np.median(image_inference_ms)) if image_inference_ms else None,
                "batch_wall_time_divided_by_images": wall_ms_per_image,
            },
            "error_counts_at_primary_threshold": {
                "false_positives": primary["FP"],
                "false_negatives": primary["FN"],
            },
            "error_cases": errors[:50],
        }
        all_error_cases.extend(errors)

    clean_primary = results_by_condition["clean:clean"]["primary"]
    clean_secondary = results_by_condition["clean:clean"]["secondary"]
    for condition in results_by_condition.values():
        for key, baseline in (("primary", clean_primary), ("secondary", clean_secondary)):
            current = condition[key]
            condition.setdefault("degradation", {})[key] = {
                name: (
                    current[name] - baseline[name]
                    if current[name] is not None and baseline[name] is not None
                    else None
                )
                for name in ("F1", "recall", "precision", "mAP50", "mAP50_95")
            }
            condition.setdefault("degradation", {})[key].update(
                {
                    f"delta_{name}": condition[key][name] - baseline[name]
                    if condition[key][name] is not None and baseline[name] is not None
                    else None
                    for name in ("TP", "FP", "FN")
                }
            )
            condition[key]["confidence_shift_mean"] = (
                condition[key]["confidence_statistics"]["mean"]
                - baseline["confidence_statistics"]["mean"]
                if condition[key]["confidence_statistics"]["mean"] is not None
                and baseline["confidence_statistics"]["mean"] is not None
                else None
            )
            condition[key]["candidate_confidence_shift_mean"] = (
                condition[key]["candidate_confidence_statistics"]["mean"]
                - baseline["candidate_confidence_statistics"]["mean"]
                if condition[key]["candidate_confidence_statistics"]["mean"] is not None
                and baseline["candidate_confidence_statistics"]["mean"] is not None
                else None
            )
            condition[key]["per_class_delta"] = {}
            for class_name, class_metrics in condition[key]["per_class"].items():
                baseline_class = baseline["per_class"][class_name]
                if (
                    class_metrics["status"] != "VALID_SAMPLE"
                    or baseline_class["status"] != "VALID_SAMPLE"
                ):
                    condition[key]["per_class_delta"][class_name] = {
                        "status": "INSUFFICIENT_SAMPLE",
                        "delta_FP": None,
                        "delta_FN": None,
                        "confidence_shift_mean": None,
                        "candidate_confidence_shift_mean": None,
                    }
                    continue
                condition[key]["per_class_delta"][class_name] = {
                    "status": "VALID_SAMPLE",
                    "delta_FP": class_metrics["FP"] - baseline_class["FP"],
                    "delta_FN": class_metrics["FN"] - baseline_class["FN"],
                    "confidence_shift_mean": (
                        class_metrics["confidence_statistics"]["mean"]
                        - baseline_class["confidence_statistics"]["mean"]
                        if class_metrics["confidence_statistics"]["mean"] is not None
                        and baseline_class["confidence_statistics"]["mean"] is not None
                        else None
                    ),
                    "candidate_confidence_shift_mean": (
                        class_metrics["candidate_confidence_statistics"]["mean"]
                        - baseline_class["candidate_confidence_statistics"]["mean"]
                        if class_metrics["candidate_confidence_statistics"]["mean"] is not None
                        and baseline_class["candidate_confidence_statistics"]["mean"] is not None
                        else None
                    ),
                }
        condition["threshold_sensitivity"] = {
            "F1_primary_minus_secondary": condition["primary"]["F1"]
            - condition["secondary"]["F1"]
        }

    perturbation_scores: dict[str, list[tuple[str, float]]] = {}
    for name, condition in results_by_condition.items():
        if name == "clean:clean":
            continue
        perturbation_scores.setdefault(condition["transformation"], []).append(
            (
                condition["severity"],
                condition["degradation"]["primary"]["F1"],
            )
        )
    mean_degradation = {
        transform: float(np.mean([delta for _, delta in values]))
        for transform, values in perturbation_scores.items()
    }
    class_support = {
        name: metrics["ground_truth"]
        for name, metrics in clean_primary["per_class"].items()
    }
    valid_classes = [
        name for name, support in class_support.items() if support > 0
    ]
    error_analysis = {
        "representative_errors": all_error_cases[:100],
        "visual_review_performed": False,
        "interpretation": "Automated unmatched boxes only; no visual failure cause was inferred.",
    }
    summary = {
        "experiment_id": "CVR2-CV-016",
        "dataset_id": "R5_controlled_shift",
        "research_only": True,
        "production_integration": False,
        "status": "PARTIALLY_VALIDATED",
        "source_dataset": "D1",
        "source_image_count": len(_test_sources()),
        "source_split": "test",
        "external_real_world_dataset": False,
        "data_type": "controlled synthetic perturbations",
        "model_id": "R3-YOLO-ROBUST-BASE",
        "model_sha256": R3_SHA256,
        "m1_13_sha256": M113_SHA256,
        "d0_file_count_reference": 605,
        "checkpoint_sha256": sha256_file(R3_CHECKPOINT),
        "evaluation_code_sha256": sha256_file(Path(__file__)),
        "confidence_threshold": PRIMARY_THRESHOLD,
        "secondary_confidence_threshold": SECONDARY_THRESHOLD,
        "IoU_threshold": EVALUATION_IOU,
        "nms_iou_threshold": NMS_IOU,
        "prediction_floor_for_ap": PREDICTION_FLOOR,
        "dataset_manifest_sha256": manifest_sha,
        "source_dataset_composite_sha256": _d1_composite_sha256(),
        "source_dataset_manifest_file_sha256": _d1_manifest_sha256(),
        "conditions": results_by_condition,
        "summary": {
            "condition_count_including_clean": len(results_by_condition),
            "source_image_count": len(_test_sources()),
            "ground_truth_boxes": clean_primary["ground_truth_box_count"],
            "class_support": class_support,
            "classes_with_valid_support": valid_classes,
            "insufficient_sample_classes": [
                name for name, support in class_support.items() if support == 0
            ],
            "mean_delta_f1_by_transform": mean_degradation,
            "threshold_sensitivity": {
                key: item["threshold_sensitivity"]["F1_primary_minus_secondary"]
                for key, item in results_by_condition.items()
            },
            "strongest_affected_class": "INSUFFICIENT_SAMPLE: only one class has test support",
            "weakest_affected_class": "INSUFFICIENT_SAMPLE: only one class has test support",
            "most_robust_perturbation": (
                max(mean_degradation, key=mean_degradation.get) if mean_degradation else None
            ),
            "most_damaging_perturbation": (
                min(mean_degradation, key=mean_degradation.get) if mean_degradation else None
            ),
        },
        "error_analysis": error_analysis,
        "environment": _capture_environment(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return summary


def _capture_environment() -> dict[str, Any]:
    from ai.research.environment import capture_environment

    return capture_environment()


def run_experiment() -> None:
    manifest_path, manifest_sha = generate_dataset()
    result = evaluate_dataset()
    experiment_dir = REPO_ROOT / "ai" / "research" / "experiments" / "R5"
    experiment_dir.mkdir(parents=True, exist_ok=False)
    result["generation_manifest_path"] = str(manifest_path.relative_to(REPO_ROOT))
    result["generation_manifest_sha256"] = manifest_sha
    output_path = experiment_dir / "metrics.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    config = {
        "experiment_id": "CVR2-CV-016",
        "title": "Controlled Domain-Shift & Robustness Study",
        "research_only": True,
        "production_integration": False,
        "hypothesis": "Performance and confidence may degrade with increasing controlled perturbation severity; this is an association within the fixed D1 test images.",
        "source_dataset": "D1",
        "source_split": "test",
        "model_id": "R3-YOLO-ROBUST-BASE",
        "m1_13_sha256": M113_SHA256,
        "d0_file_count_reference": 605,
        "checkpoint_sha256": R3_SHA256,
        "evaluation_code_sha256": sha256_file(Path(__file__)),
        "thresholds": {
            "primary_confidence": PRIMARY_THRESHOLD,
            "secondary_confidence": SECONDARY_THRESHOLD,
            "IoU": EVALUATION_IOU,
            "no_per_condition_tuning": True,
        },
        "transformations": TRANSFORM_PARAMETERS,
        "excluded_transformations": EXCLUDED_TRANSFORMATIONS,
        "master_seed": MASTER_SEED,
        "generation_manifest_sha256": manifest_sha,
        "source_dataset_composite_sha256": result["source_dataset_composite_sha256"],
        "source_dataset_manifest_file_sha256": result["source_dataset_manifest_file_sha256"],
        "output_manifest_sha256": manifest_sha,
        "metrics_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "status": result["status"],
        "timestamp": result["timestamp"],
        "environment": result["environment"],
    }
    (experiment_dir / "experiment.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (experiment_dir / "README.md").write_text(
        "# CVR2-CV-016 — Controlled Domain-Shift & Robustness Study\n\n"
        "Status: `PARTIALLY_VALIDATED`. See `metrics.json` and "
        "`ai/research/datasets/R5_controlled_shift/manifest.json` for measured results "
        "and source-to-output provenance. This is a controlled perturbation study on "
        "D1 test images, not an external real-world dataset.\n",
        encoding="utf-8",
    )
    print(f"Generated manifest: {manifest_path}")
    print(f"Manifest SHA-256: {manifest_sha}")
    print(f"Metrics: {output_path}")
    print(f"Status: {result['status']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Run R5 generation and evaluation; existing output paths are never overwritten.")
    else:
        run_experiment()
