"""Generate and evaluate deterministic synthetic temporal sequences for R6."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
from ultralytics import YOLO

from ai.research.r5_controlled_shift import (
    CLASS_NAMES,
    D1_ROOT,
    EVALUATION_IOU,
    M113_SHA256,
    PRIMARY_THRESHOLD,
    R3_CHECKPOINT,
    R3_SHA256,
    SECONDARY_THRESHOLD,
    parse_yolo_label_text,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
R6_ROOT = REPO_ROOT / "ai" / "research" / "datasets" / "R6_controlled_sequences"
EXPERIMENT_ROOT = REPO_ROOT / "ai" / "research" / "experiments" / "R6"
MASTER_SEED = 20261020
FRAME_COUNT = 10
SEQUENCE_TYPES = (
    "STATIC_SEQUENCE",
    "SMALL_PERTURBATION_SEQUENCE",
    "CAMERA_MOTION_SEQUENCE",
    "OCCLUSION_SEQUENCE",
    "QUALITY_DEGRADATION_SEQUENCE",
)
SAMPLING_STRIDES = (1, 2, 3)
TEMPORAL_RULES = (
    "NO_TEMPORAL_FILTER",
    "2_FRAME_PERSISTENCE",
    "3_FRAME_PERSISTENCE",
    "1_FRAME_GAP_TOLERANCE",
)
PREDICTION_FLOOR = 0.001
NMS_IOU = 0.70
MAX_DETECTIONS = 300
IMAGE_SIZE = 640


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _test_sources() -> list[tuple[Path, Path]]:
    source_list = D1_ROOT / "splits" / "test.txt"
    if not source_list.is_file():
        raise FileNotFoundError(f"Missing D1 test split: {source_list}")
    entries = []
    for image_line in source_list.read_text(encoding="utf-8").splitlines():
        if not image_line.strip():
            continue
        image = D1_ROOT / image_line.strip()
        label = D1_ROOT / "labels" / f"{image.stem}.txt"
        if not image.is_file() or not label.is_file():
            raise FileNotFoundError(f"Missing D1 source image or label: {image}, {label}")
        entries.append((image, label))
    if not entries:
        raise ValueError("D1 test split is empty")
    return entries


def _seed(source_hash: str, sequence_type: str, frame_id: int) -> int:
    value = f"{MASTER_SEED}:{source_hash}:{sequence_type}:{frame_id}".encode("ascii")
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")


def _source_object_records(label_text: str) -> list[dict[str, Any]]:
    parsed = parse_yolo_label_text(label_text)
    return [
        {
            "object_id": index,
            "class_id": class_id,
            "xywh_normalized": [x, y, width, height],
        }
        for index, (class_id, x, y, width, height) in enumerate(parsed)
    ]


def _translate_frame(
    image: Image.Image,
    objects: list[dict[str, Any]],
    dx: int,
    dy: int,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    width, height = image.size
    moved_image = image.transform(
        (width, height),
        Image.Transform.AFFINE,
        (1, 0, -dx, 0, 1, -dy),
        resample=Image.Resampling.BILINEAR,
        fillcolor=(96, 96, 96),
    )
    translated = []
    for obj in objects:
        class_id = int(obj["class_id"])
        center_x, center_y, box_width, box_height = obj["xywh_normalized"]
        left = max(0.0, center_x * width - box_width * width / 2 + dx)
        top = max(0.0, center_y * height - box_height * height / 2 + dy)
        right = min(float(width), center_x * width + box_width * width / 2 + dx)
        bottom = min(float(height), center_y * height + box_height * height / 2 + dy)
        if right <= left or bottom <= top:
            continue
        translated.append(
            {
                "object_id": int(obj["object_id"]),
                "class_id": class_id,
                "xywh_normalized": [
                    (left + right) / (2 * width),
                    (top + bottom) / (2 * height),
                    (right - left) / width,
                    (bottom - top) / height,
                ],
            }
        )
    return moved_image, translated


def _make_frame(
    source_image: Image.Image,
    objects: list[dict[str, Any]],
    sequence_type: str,
    frame_id: int,
    seed: int,
) -> tuple[Image.Image, list[dict[str, Any]], dict[str, Any]]:
    rng = np.random.default_rng(seed)
    image = source_image.copy().convert("RGB")
    output_objects = [dict(obj) for obj in objects]
    params: dict[str, Any] = {"operation": sequence_type}

    if sequence_type == "STATIC_SEQUENCE":
        params = {"operation": "repeat_source_image_without_pixel_changes"}
    elif sequence_type == "SMALL_PERTURBATION_SEQUENCE":
        brightness_factors = (0.98, 1.00, 1.02, 0.99, 1.01)
        factor = brightness_factors[frame_id % len(brightness_factors)]
        noise_sigma = (0.0, 1.0, 2.0, 1.0, 0.5)[frame_id % 5]
        image = ImageEnhance.Brightness(image).enhance(factor)
        pixels = np.asarray(image, dtype=np.float32)
        if noise_sigma:
            pixels = np.clip(
                pixels + rng.normal(0.0, noise_sigma, size=pixels.shape), 0, 255
            )
        image = Image.fromarray(pixels.astype(np.uint8), "RGB")
        params = {
            "brightness_factor": factor,
            "additive_gaussian_noise_sigma": noise_sigma,
            "noise_distribution": "zero-mean Gaussian in RGB pixel values",
        }
    elif sequence_type == "CAMERA_MOTION_SEQUENCE":
        dx = (-8, -6, -4, -2, 0, 2, 4, 6, 8, 10)[frame_id]
        dy = (-4, -3, -2, -1, 0, 1, 2, 3, 4, 5)[frame_id]
        image, output_objects = _translate_frame(image, output_objects, dx, dy)
        params = {
            "translation_pixels": {"dx": dx, "dy": dy},
            "resampling": "bilinear",
            "fill_rgb": [96, 96, 96],
            "annotation_policy": "translate boxes and clip to visible image bounds",
        }
    elif sequence_type == "OCCLUSION_SEQUENCE":
        active = frame_id in (4, 5)
        if active:
            width, height = image.size
            x1, y1 = int(width * 0.38), int(height * 0.34)
            x2, y2 = int(width * 0.62), int(height * 0.66)
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle((x1, y1, x2, y2), fill=(32, 32, 32, 209))
            image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        params = {
            "active": active,
            "active_frame_ids": [4, 5],
            "rectangle_fraction_xyxy": [0.38, 0.34, 0.62, 0.66],
            "opacity": 0.82,
            "annotation_policy": "retain full source object boxes under synthetic occluder",
        }
    elif sequence_type == "QUALITY_DEGRADATION_SEQUENCE":
        level = (0.0, 0.4, 0.8, 1.2, 1.6, 1.6, 1.2, 0.8, 0.4, 0.0)[frame_id]
        sigma = (0.0, 1.0, 2.0, 3.0, 4.0, 4.0, 3.0, 2.0, 1.0, 0.0)[frame_id]
        quality = (95, 85, 75, 65, 55, 55, 65, 75, 85, 95)[frame_id]
        if level:
            image = image.filter(ImageFilter.GaussianBlur(radius=level))
        if sigma:
            pixels = np.asarray(image, dtype=np.float32)
            pixels = np.clip(
                pixels + rng.normal(0.0, sigma, size=pixels.shape), 0, 255
            )
            image = Image.fromarray(pixels.astype(np.uint8), "RGB")
        params = {
            "gaussian_blur_radius_pixels": level,
            "additive_gaussian_noise_sigma": sigma,
            "jpeg_quality": quality,
            "noise_distribution": "zero-mean Gaussian in RGB pixel values",
        }
        import io

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=False)
        buffer.seek(0)
        with Image.open(buffer) as compressed:
            image = compressed.convert("RGB")
    else:
        raise ValueError(f"Unknown R6 sequence type: {sequence_type}")

    return image, output_objects, params


def _label_text(objects: list[dict[str, Any]]) -> str:
    lines = []
    for obj in objects:
        class_id = int(obj["class_id"])
        x, y, width, height = obj["xywh_normalized"]
        if not (
            0 <= x <= 1
            and 0 <= y <= 1
            and 0 < width <= 1
            and 0 < height <= 1
            and x - width / 2 >= -1e-8
            and y - height / 2 >= -1e-8
            and x + width / 2 <= 1 + 1e-8
            and y + height / 2 <= 1 + 1e-8
        ):
            raise ValueError(f"Generated out-of-bounds annotation: {obj}")
        lines.append(
            f"{class_id} {x:.8f} {y:.8f} {width:.8f} {height:.8f}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def generate_sequences(output_root: Path = R6_ROOT) -> tuple[Path, str]:
    if output_root.exists():
        raise FileExistsError(f"Refusing to overwrite existing R6 dataset: {output_root}")
    source_entries = _test_sources()
    generated_at = _now()
    records: list[dict[str, Any]] = []
    for image_path, label_path in source_entries:
        source_image_hash = sha256_file(image_path)
        source_label_hash = sha256_file(label_path)
        source_image_id = image_path.stem
        source_image_path = image_path.relative_to(D1_ROOT).as_posix()
        source_label_path = label_path.relative_to(D1_ROOT).as_posix()
        source_objects = _source_object_records(label_path.read_text(encoding="utf-8"))
        with Image.open(image_path) as opened:
            source_image = opened.convert("RGB")
        for sequence_type in SEQUENCE_TYPES:
            sequence_id = f"{sequence_type.lower()}__{source_image_id}"
            for frame_id in range(FRAME_COUNT):
                seed = _seed(source_image_hash, sequence_type, frame_id)
                image, objects, params = _make_frame(
                    source_image, source_objects, sequence_type, frame_id, seed
                )
                frame_root = (
                    output_root
                    / sequence_type
                    / sequence_id
                    / f"frame_{frame_id:03d}"
                )
                image_path_out = frame_root / "image.jpg"
                label_path_out = frame_root / "labels.txt"
                image_path_out.parent.mkdir(parents=True, exist_ok=True)
                image.save(image_path_out, format="JPEG", quality=95, optimize=False)
                label_path_out.write_text(
                    _label_text(objects), encoding="utf-8", newline="\n"
                )
                parsed = parse_yolo_label_text(
                    label_path_out.read_text(encoding="utf-8")
                )
                if len(parsed) != len(objects):
                    raise ValueError(f"Generated labels failed round-trip: {label_path_out}")
                records.append(
                    {
                        "sequence_type": sequence_type,
                        "sequence_id": sequence_id,
                        "source_image_id": source_image_id,
                        "source_image": source_image_path,
                        "source_image_sha256": source_image_hash,
                        "source_label": source_label_path,
                        "source_label_sha256": source_label_hash,
                        "source_split": "test",
                        "frame_id": frame_id,
                        "temporal_order": frame_id,
                        "frame_count": FRAME_COUNT,
                        "generated_image": image_path_out.relative_to(output_root).as_posix(),
                        "generated_image_sha256": sha256_file(image_path_out),
                        "generated_label": label_path_out.relative_to(output_root).as_posix(),
                        "generated_label_sha256": sha256_file(label_path_out),
                        "object_ids": [obj["object_id"] for obj in objects],
                        "ground_truth_objects": objects,
                        "transformation_parameters": params,
                        "seed": seed,
                        "generation_timestamp": generated_at,
                        "manifest_reference": "manifest.json",
                        "dimensions": list(image.size),
                    }
                )

    source_manifest = D1_ROOT / "manifests" / "dataset_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "dataset_id": "R6_controlled_sequences",
        "data_type": "CONTROLLED_SYNTHETIC_TEMPORAL_EVALUATION",
        "real_world_video_evaluation": "REAL_WORLD_VIDEO_EVALUATION_NOT_AVAILABLE",
        "external_real_world_dataset": False,
        "source_dataset": "D1",
        "source_split": "test",
        "source_dataset_composite_sha256": json.loads(
            source_manifest.read_text(encoding="utf-8")
        )["composite_sha256"],
        "source_dataset_manifest_sha256": sha256_file(source_manifest),
        "source_image_count": len(source_entries),
        "source_class_support": {
            class_name: sum(
                1
                for _, label_path in source_entries
                for class_id, *_ in parse_yolo_label_text(
                    label_path.read_text(encoding="utf-8")
                )
                if class_id == class_index
            )
            for class_index, class_name in CLASS_NAMES.items()
        },
        "sequence_count": len(source_entries) * len(SEQUENCE_TYPES),
        "sequence_types": list(SEQUENCE_TYPES),
        "frames_per_sequence": FRAME_COUNT,
        "frame_count": len(records),
        "master_seed": MASTER_SEED,
        "generation_timestamp": generated_at,
        "class_names": CLASS_NAMES,
        "sequence_design": {
            "STATIC_SEQUENCE": "same source pixels represented in ten frames",
            "SMALL_PERTURBATION_SEQUENCE": "predefined small brightness and seeded noise changes",
            "CAMERA_MOTION_SEQUENCE": "small bounded translation with propagated and clipped boxes",
            "OCCLUSION_SEQUENCE": "fixed opaque synthetic rectangle on frames 4 and 5",
            "QUALITY_DEGRADATION_SEQUENCE": "predefined blur, noise, and JPEG levels over time",
        },
        "records": records,
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksum = sha256_file(manifest_path)
    (output_root / "MANIFEST.SHA256").write_text(
        f"{checksum}  manifest.json\n", encoding="ascii"
    )
    return manifest_path, checksum


def _iou(box_a: list[float], box_b: list[float]) -> float:
    left = max(box_a[0], box_b[0])
    top = max(box_a[1], box_b[1])
    right = min(box_a[2], box_b[2])
    bottom = min(box_a[3], box_b[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    return intersection / max(area_a + area_b - intersection, 1e-9)


def _xywh_to_xyxy(objects: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
    boxes = []
    for obj in objects:
        x, y, box_width, box_height = obj["xywh_normalized"]
        boxes.append(
            {
                "object_id": int(obj["object_id"]),
                "class_id": int(obj["class_id"]),
                "box": [
                    (x - box_width / 2) * width,
                    (y - box_height / 2) * height,
                    (x + box_width / 2) * width,
                    (y + box_height / 2) * height,
                ],
            }
        )
    return boxes


def _frame_match(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = [p for p in predictions if p["confidence"] >= threshold]
    selected.sort(key=lambda p: (-p["confidence"], p["class_id"], p["box"]))
    unmatched_gt = set(range(len(ground_truth)))
    true_predictions = []
    false_predictions = []
    for prediction in selected:
        candidates = [
            (index, _iou(prediction["box"], gt["box"]))
            for index, gt in enumerate(ground_truth)
            if index in unmatched_gt and gt["class_id"] == prediction["class_id"]
        ]
        candidates = [item for item in candidates if item[1] >= EVALUATION_IOU]
        if candidates:
            gt_index, overlap = max(candidates, key=lambda item: (item[1], -item[0]))
            unmatched_gt.remove(gt_index)
            true_predictions.append(
                {
                    **prediction,
                    "matched_object_id": ground_truth[gt_index]["object_id"],
                    "matched_iou": overlap,
                }
            )
        else:
            false_predictions.append(prediction)
    false_negatives = [ground_truth[index] for index in sorted(unmatched_gt)]
    return true_predictions + [{"_fn": gt} for gt in false_negatives], false_predictions


def _match_frame_detailed(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    selected = [p for p in predictions if p["confidence"] >= threshold]
    selected.sort(key=lambda p: (-p["confidence"], p["class_id"], p["box"]))
    unmatched_gt = set(range(len(ground_truth)))
    true_predictions = []
    false_predictions = []
    for prediction in selected:
        candidates = [
            (index, _iou(prediction["box"], gt["box"]))
            for index, gt in enumerate(ground_truth)
            if index in unmatched_gt and gt["class_id"] == prediction["class_id"]
        ]
        candidates = [item for item in candidates if item[1] >= EVALUATION_IOU]
        if candidates:
            gt_index, overlap = max(candidates, key=lambda item: (item[1], -item[0]))
            unmatched_gt.remove(gt_index)
            true_predictions.append(
                {
                    **prediction,
                    "matched_object_id": ground_truth[gt_index]["object_id"],
                    "matched_iou": overlap,
                }
            )
        else:
            false_predictions.append(prediction)
    false_negatives = [ground_truth[index] for index in sorted(unmatched_gt)]
    return true_predictions, false_predictions, false_negatives


def _frame_metrics(
    frames: list[dict[str, Any]], threshold: float
) -> dict[str, Any]:
    tp = fp = fn = 0
    per_class = {
        name: {"TP": 0, "FP": 0, "FN": 0, "ground_truth": 0}
        for name in CLASS_NAMES.values()
    }
    for frame in frames:
        matched, false_predictions, false_negatives = _match_frame_detailed(
            frame["predictions"], frame["ground_truth"], threshold
        )
        tp += len(matched)
        fp += len(false_predictions)
        fn += len(false_negatives)
        for item in frame["ground_truth"]:
            per_class[CLASS_NAMES[item["class_id"]]]["ground_truth"] += 1
        for item in matched:
            per_class[CLASS_NAMES[item["class_id"]]]["TP"] += 1
        for item in false_predictions:
            per_class[CLASS_NAMES[item["class_id"]]]["FP"] += 1
        for item in false_negatives:
            per_class[CLASS_NAMES[item["class_id"]]]["FN"] += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    for name, values in per_class.items():
        ctp, cfp, cfn = values["TP"], values["FP"], values["FN"]
        values["precision"] = ctp / (ctp + cfp) if ctp + cfp else 0.0
        values["recall"] = ctp / (ctp + cfn) if ctp + cfn else 0.0
        cprecision, crecall = values["precision"], values["recall"]
        values["F1"] = (
            2 * cprecision * crecall / (cprecision + crecall)
            if cprecision + crecall
            else 0.0
        )
        if values["ground_truth"] == 0:
            values["status"] = "INSUFFICIENT_SAMPLE"
    return {
        "confidence_threshold": threshold,
        "IoU_threshold": EVALUATION_IOU,
        "frame_count": len(frames),
        "ground_truth_box_count": tp + fn,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "F1": f1,
        "per_class": per_class,
    }


def _frame_level_record(frame: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "sequence_id": frame["sequence_id"],
        "sequence_type": frame["sequence_type"],
        "source_image_id": frame["source_image_id"],
        "frame_id": frame["frame_id"],
        "generated_image": frame["generated_image"],
        "inference_ms": frame["inference_ms"],
        "ground_truth": frame["ground_truth"],
        "operating_points": {},
    }
    for name, threshold in (
        ("primary", PRIMARY_THRESHOLD),
        ("secondary", SECONDARY_THRESHOLD),
    ):
        matched, false_positives, false_negatives = _match_frame_detailed(
            frame["predictions"], frame["ground_truth"], threshold
        )
        tp, fp, fn = len(matched), len(false_positives), len(false_negatives)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        record["operating_points"][name] = {
            "confidence_threshold": threshold,
            "IoU_threshold": EVALUATION_IOU,
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "precision": precision,
            "recall": recall,
            "F1": f1,
            "detections": [
                {
                    "class_id": item["class_id"],
                    "class_name": item["class_name"],
                    "confidence": item["confidence"],
                    "xyxy": item["box"],
                    "is_true_positive": True,
                    "matched_object_id": item["matched_object_id"],
                    "matched_iou": item["matched_iou"],
                }
                for item in matched
            ]
            + [
                {
                    "class_id": item["class_id"],
                    "class_name": item["class_name"],
                    "confidence": item["confidence"],
                    "xyxy": item["box"],
                    "is_true_positive": False,
                    "matched_object_id": None,
                    "matched_iou": None,
                }
                for item in false_positives
            ],
            "false_negative_object_ids": [
                item["object_id"] for item in false_negatives
            ],
        }
    return record


def _filter_event(detections: list[bool], rule: str) -> tuple[bool, int | None]:
    positives = [index for index, value in enumerate(detections) if value]
    if rule == "NO_TEMPORAL_FILTER":
        return (bool(positives), positives[0] if positives else None)
    if rule == "2_FRAME_PERSISTENCE":
        for index in range(len(detections) - 1):
            if detections[index] and detections[index + 1]:
                return True, index + 1
        return False, None
    if rule == "3_FRAME_PERSISTENCE":
        for index in range(len(detections) - 2):
            if all(detections[index : index + 3]):
                return True, index + 2
        return False, None
    if rule == "1_FRAME_GAP_TOLERANCE":
        for first_index, second_index in zip(positives, positives[1:]):
            if second_index - first_index <= 2:
                return True, second_index
        return False, None
    raise ValueError(f"Unknown temporal filter: {rule}")


def _associate_false_positive_tracks(
    frame_false_positives: list[list[dict[str, Any]]],
) -> list[list[dict[str, Any]]]:
    tracks: list[list[dict[str, Any]]] = []
    active: list[dict[str, Any]] = []
    next_id = 0
    for frame_index, current in enumerate(frame_false_positives):
        candidates = []
        for track in active:
            previous = track["observations"][-1]
            if not 0 < frame_index - previous["frame_index"] <= 2:
                continue
            for prediction_index, prediction in enumerate(current):
                if prediction["class_id"] != previous["class_id"]:
                    continue
                overlap = _iou(previous["box"], prediction["box"])
                if overlap >= EVALUATION_IOU:
                    candidates.append((overlap, track["track_id"], prediction_index))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        used_tracks: set[int] = set()
        used_predictions: set[int] = set()
        for _, track_id, prediction_index in candidates:
            if track_id in used_tracks or prediction_index in used_predictions:
                continue
            track = next(item for item in active if item["track_id"] == track_id)
            track["observations"].append(
                {"frame_index": frame_index, **current[prediction_index]}
            )
            used_tracks.add(track_id)
            used_predictions.add(prediction_index)
        for prediction_index, prediction in enumerate(current):
            if prediction_index in used_predictions:
                continue
            track = {
                "track_id": next_id,
                "class_id": prediction["class_id"],
                "observations": [{"frame_index": frame_index, **prediction}],
            }
            next_id += 1
            active.append(track)
            tracks.append(track)
    return tracks


def _temporal_metrics(
    sequence_frames: list[dict[str, Any]],
    threshold: float,
    sampling_stride: int,
) -> dict[str, Any]:
    sampled_indices = list(range(0, len(sequence_frames), sampling_stride))
    if not sampled_indices:
        return {}
    sampled = [sequence_frames[index] for index in sampled_indices]
    object_presence: dict[int, list[bool]] = {}
    object_class: dict[int, int] = {}
    matched_tp_by_frame: list[set[int]] = []
    false_positives_by_frame: list[list[dict[str, Any]]] = []
    frame_level_tp = frame_level_fp = frame_level_fn = 0

    for sample_index, frame in enumerate(sampled):
        matched, false_positives, false_negatives = _match_frame_detailed(
            frame["predictions"], frame["ground_truth"], threshold
        )
        frame_level_tp += len(matched)
        frame_level_fp += len(false_positives)
        frame_level_fn += len(false_negatives)
        matched_ids = {item["matched_object_id"] for item in matched}
        present_ids = {item["object_id"] for item in frame["ground_truth"]}
        for object_id in present_ids | set(object_presence):
            object_presence.setdefault(object_id, [False] * sample_index)
        for object_id, values in object_presence.items():
            values.append(object_id in matched_ids)
        for gt in frame["ground_truth"]:
            object_class[gt["object_id"]] = gt["class_id"]
        matched_tp_by_frame.append(matched_ids)
        false_positives_by_frame.append(false_positives)

    # Extend tracks first observed after frame zero with explicit missing values.
    for object_id, values in object_presence.items():
        if len(values) < len(sampled):
            values.extend([False] * (len(sampled) - len(values)))

    gt_event_count = len(object_presence)
    event_tp_by_rule: dict[str, int] = {rule: 0 for rule in TEMPORAL_RULES}
    event_fn_by_rule: dict[str, int] = {rule: 0 for rule in TEMPORAL_RULES}
    detection_delay: dict[str, list[int]] = {rule: [] for rule in TEMPORAL_RULES}
    class_event_counts = {
        name: {"ground_truth_events": 0, **{rule: 0 for rule in TEMPORAL_RULES}}
        for name in CLASS_NAMES.values()
    }
    gap_lengths: list[int] = []
    recovered_gaps = 0
    all_gaps = 0
    continuity_numerator = 0
    continuity_denominator = 0
    for object_id, outcomes in object_presence.items():
        object_name = CLASS_NAMES[object_class[object_id]]
        class_event_counts[object_name]["ground_truth_events"] += 1
        # Include frames where the camera-motion annotation clips the object away.
        source_object_frames = [
            object_id in {gt["object_id"] for gt in frame["ground_truth"]}
            for frame in sampled
        ]
        outcomes = [
            outcome if source_object_frames[index] else False
            for index, outcome in enumerate(outcomes)
        ]
        expected_transitions = sum(
            1
            for index in range(len(source_object_frames) - 1)
            if source_object_frames[index] and source_object_frames[index + 1]
        )
        continuity_denominator += expected_transitions
        continuity_numerator += sum(
            1
            for index in range(len(outcomes) - 1)
            if source_object_frames[index]
            and source_object_frames[index + 1]
            and outcomes[index]
            and outcomes[index + 1]
        )
        index = 0
        while index < len(outcomes):
            if outcomes[index]:
                index += 1
                continue
            start = index
            while index < len(outcomes) and not outcomes[index]:
                index += 1
            if any(source_object_frames[start:index]) and any(outcomes[:start]):
                all_gaps += 1
                gap_lengths.append((index - start) * sampling_stride)
                if index < len(outcomes) and outcomes[index]:
                    recovered_gaps += 1
        for rule in TEMPORAL_RULES:
            filtered, detected_at = _filter_event(outcomes, rule)
            event_tp_by_rule[rule] = event_tp_by_rule.get(rule, 0) + int(filtered)
            class_event_counts[object_name][rule] += int(filtered)
            if filtered and detected_at is not None:
                detection_delay[rule].append(detected_at * sampling_stride)
    event_fn_by_rule = {
        rule: gt_event_count - event_tp_by_rule[rule] for rule in TEMPORAL_RULES
    }

    fp_tracks = _associate_false_positive_tracks(false_positives_by_frame)
    fp_events_by_rule = {rule: 0 for rule in TEMPORAL_RULES}
    class_fp_events_by_rule = {
        name: {rule: 0 for rule in TEMPORAL_RULES}
        for name in CLASS_NAMES.values()
    }
    fp_persistence_lengths = []
    for track in fp_tracks:
        positions = [int(item["frame_index"]) for item in track["observations"]]
        presence = [index in positions for index in range(len(sampled))]
        fp_persistence_lengths.append(len(positions))
        for rule in TEMPORAL_RULES:
            accepted, _ = _filter_event(presence, rule)
            fp_events_by_rule[rule] += int(accepted)
            if accepted:
                class_fp_events_by_rule[CLASS_NAMES[track["class_id"]]][rule] += 1

    event_results = {}
    for rule in TEMPORAL_RULES:
        event_tp = event_tp_by_rule[rule]
        event_fp = fp_events_by_rule[rule]
        event_fn = event_fn_by_rule[rule]
        event_precision = event_tp / (event_tp + event_fp) if event_tp + event_fp else 0.0
        event_recall = event_tp / (event_tp + event_fn) if event_tp + event_fn else 0.0
        event_results[rule] = {
            "ground_truth_events": gt_event_count,
            "detected_ground_truth_events": event_tp,
            "missed_ground_truth_events": event_fn,
            "persistent_false_positive_events": event_fp,
            "event_precision": event_precision,
            "event_recall": event_recall,
            "mean_detection_delay_frames": (
                float(np.mean(detection_delay[rule])) if detection_delay[rule] else None
            ),
        }

    frame_precision = (
        frame_level_tp / (frame_level_tp + frame_level_fp)
        if frame_level_tp + frame_level_fp
        else 0.0
    )
    frame_recall = (
        frame_level_tp / (frame_level_tp + frame_level_fn)
        if frame_level_tp + frame_level_fn
        else 0.0
    )
    return {
        "sampling_stride": sampling_stride,
        "sampled_frame_count_per_sequence": len(sampled),
        "frame_precision": frame_precision,
        "frame_recall": frame_recall,
        "frame_TP": frame_level_tp,
        "frame_FP": frame_level_fp,
        "frame_FN": frame_level_fn,
        "detection_persistence_fraction": (
            frame_level_tp / (frame_level_tp + frame_level_fn)
            if frame_level_tp + frame_level_fn
            else None
        ),
        "track_continuity_fraction": (
            continuity_numerator / continuity_denominator
            if continuity_denominator
            else None
        ),
        "track_continuity_transitions": continuity_numerator,
        "expected_adjacent_transitions": continuity_denominator,
        "detection_gap_count": all_gaps,
        "mean_detection_gap_frames": (
            float(np.mean(gap_lengths)) if gap_lengths else None
        ),
        "recovery_rate": recovered_gaps / all_gaps if all_gaps else None,
        "false_positive_track_count": len(fp_tracks),
        "mean_false_positive_track_persistence_frames": (
            float(np.mean(fp_persistence_lengths)) if fp_persistence_lengths else 0.0
        ),
        "event_results_by_rule": event_results,
        "event_results_by_class": {
            class_name: {
                rule: {
                    "ground_truth_events": values["ground_truth_events"],
                    "detected_ground_truth_events": values[rule],
                    "missed_ground_truth_events": (
                        values["ground_truth_events"] - values[rule]
                    ),
                    "persistent_false_positive_events": class_fp_events_by_rule[
                        class_name
                    ][rule],
                    "event_precision": (
                        values[rule]
                        / (
                            values[rule]
                            + class_fp_events_by_rule[class_name][rule]
                        )
                        if values[rule] + class_fp_events_by_rule[class_name][rule]
                        else 0.0
                    ),
                    "event_recall": (
                        values[rule] / values["ground_truth_events"]
                        if values["ground_truth_events"]
                        else None
                    ),
                    "status": (
                        "VALID_SAMPLE"
                        if values["ground_truth_events"]
                        else "INSUFFICIENT_SAMPLE"
                    ),
                }
                for rule in TEMPORAL_RULES
            }
            for class_name, values in class_event_counts.items()
        },
        "selected_model_inference_ms_per_sequence": sum(
            float(sequence_frames[index]["inference_ms"])
            for index in sampled_indices
        ),
        "frame_processing_fraction": len(sampled_indices) / len(sequence_frames),
        "sampling_cost_is_projection_not_measured_reinference": True,
    }


def _predict_sequences(
    manifest: dict[str, Any],
    dataset_root: Path,
    model: YOLO,
) -> dict[str, list[dict[str, Any]]]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in manifest["records"]:
        by_type.setdefault(row["sequence_type"], []).append(row)
    result: dict[str, list[dict[str, Any]]] = {}
    for sequence_type, rows in by_type.items():
        rows.sort(key=lambda row: (row["sequence_id"], row["frame_id"]))
        wall_start = time.perf_counter()
        predictions_by_frame = model.predict(
            source=[str(dataset_root / row["generated_image"]) for row in rows],
            imgsz=IMAGE_SIZE,
            conf=PREDICTION_FLOOR,
            iou=NMS_IOU,
            max_det=MAX_DETECTIONS,
            device="cpu",
            verbose=False,
        )
        wall_elapsed = time.perf_counter() - wall_start
        frames = []
        for row, prediction in zip(rows, predictions_by_frame):
            image_path = dataset_root / row["generated_image"]
            with Image.open(image_path) as opened:
                width, height = opened.size
            ground_truth = _xywh_to_xyxy(
                row["ground_truth_objects"], width, height
            )
            predictions = []
            boxes = prediction.boxes
            if boxes is not None and len(boxes):
                coords = boxes.xyxy.detach().cpu().numpy()
                confidences = boxes.conf.detach().cpu().numpy()
                classes = boxes.cls.detach().cpu().numpy().astype(int)
                for box, confidence, class_id in zip(coords, confidences, classes):
                    predictions.append(
                        {
                            "class_id": int(class_id),
                            "class_name": CLASS_NAMES[int(class_id)],
                            "confidence": float(confidence),
                            "box": [float(value) for value in box],
                        }
                    )
            frames.append(
                {
                    "sequence_type": sequence_type,
                    "sequence_id": row["sequence_id"],
                    "source_image_id": row["source_image_id"],
                    "frame_id": row["frame_id"],
                    "generated_image": row["generated_image"],
                    "ground_truth": ground_truth,
                    "predictions": predictions,
                    "inference_ms": float(prediction.speed.get("inference", 0.0)),
                }
            )
        total_frames = len(rows)
        for frame in frames:
            frame["sequence_type_wall_ms_per_frame"] = wall_elapsed * 1000 / max(
                total_frames, 1
            )
        result[sequence_type] = frames
    return result


def evaluate_sequences(
    dataset_root: Path = R6_ROOT,
    experiment_root: Path = EXPERIMENT_ROOT,
) -> dict[str, Any]:
    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_sha = sha256_file(manifest_path)
    model = YOLO(str(R3_CHECKPOINT))
    predictions = _predict_sequences(manifest, dataset_root, model)
    sequence_results: dict[str, Any] = {}
    all_frames_by_type: dict[str, list[dict[str, Any]]] = {}
    error_analysis = []

    for sequence_type, frames in predictions.items():
        all_frames_by_type[sequence_type] = frames
        primary = _frame_metrics(frames, PRIMARY_THRESHOLD)
        secondary = _frame_metrics(frames, SECONDARY_THRESHOLD)
        sequence_groups: dict[str, list[dict[str, Any]]] = {}
        for frame in frames:
            sequence_groups.setdefault(frame["sequence_id"], []).append(frame)
        temporal_by_stride: dict[str, Any] = {}
        for stride in SAMPLING_STRIDES:
            per_sequence = [
                _temporal_metrics(group, PRIMARY_THRESHOLD, stride)
                for group in sequence_groups.values()
            ]
            temporal_by_stride[str(stride)] = _aggregate_temporal(per_sequence)
        mean_latency = float(np.mean([f["inference_ms"] for f in frames])) if frames else 0.0
        wall_latency = float(
            np.mean([f["sequence_type_wall_ms_per_frame"] for f in frames])
        ) if frames else 0.0
        sequence_results[sequence_type] = {
            "sequence_count": len(sequence_groups),
            "frame_count": len(frames),
            "ground_truth_box_count": primary["ground_truth_box_count"],
            "primary_frame_metrics": primary,
            "secondary_frame_metrics": secondary,
            "frame_level_records": [_frame_level_record(frame) for frame in frames],
            "temporal_by_sampling_stride": temporal_by_stride,
            "latency": {
                "mean_model_inference_ms_per_frame": mean_latency,
                "wall_clock_ms_per_frame_for_generation_ordered_batch": wall_latency,
                "real_time_claim": False,
            },
            "class_support": {
                name: values["ground_truth"]
                for name, values in primary["per_class"].items()
            },
        }
        error_analysis.extend(
            _temporal_error_examples(sequence_groups, PRIMARY_THRESHOLD)
        )

    return {
        "experiment_id": "CVR2-CV-024",
        "study_id": "R6_TEMPORAL_VIDEO_ROBUSTNESS",
        "status": "PARTIALLY_VALIDATED",
        "research_only": True,
        "production_integration": False,
        "real_world_video_evaluation": "REAL_WORLD_VIDEO_EVALUATION_NOT_AVAILABLE",
        "evaluation_type": "CONTROLLED_SYNTHETIC_TEMPORAL_EVALUATION",
        "source_dataset": "D1",
        "source_split": "test",
        "source_image_count": manifest["source_image_count"],
        "source_dataset_composite_sha256": manifest["source_dataset_composite_sha256"],
        "source_dataset_manifest_sha256": manifest["source_dataset_manifest_sha256"],
        "dataset_id": manifest["dataset_id"],
        "dataset_manifest_sha256": manifest_sha,
        "model_id": "R3-YOLO-ROBUST-BASE",
        "model_sha256": R3_SHA256,
        "checkpoint_sha256": sha256_file(R3_CHECKPOINT),
        "m1_13_sha256": M113_SHA256,
        "d0_file_count_reference": 605,
        "confidence_threshold": PRIMARY_THRESHOLD,
        "secondary_confidence_threshold": SECONDARY_THRESHOLD,
        "IoU_threshold": EVALUATION_IOU,
        "prediction_floor": PREDICTION_FLOOR,
        "NMS_IoU_threshold": NMS_IOU,
        "temporal_association": {
            "rule": "class-consistent greedy highest IoU at or above 0.50; candidate may re-associate within two sampled steps to permit one missing sampled frame",
            "threshold": EVALUATION_IOU,
            "filter_rules": list(TEMPORAL_RULES),
            "matching": "confidence-ranked greedy one-to-one matching to frame annotations",
        },
        "frame_count_per_sequence": FRAME_COUNT,
        "sampling_strides": list(SAMPLING_STRIDES),
        "sequence_results": sequence_results,
        "class_names": CLASS_NAMES,
        "class_support_status": {
            name: (
                "VALID_SAMPLE"
                if sum(item["class_support"][name] for item in sequence_results.values()) > 0
                else "INSUFFICIENT_SAMPLE"
            )
            for name in CLASS_NAMES.values()
        },
        "error_analysis": error_analysis[:100],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "ultralytics": importlib.metadata.version("ultralytics"),
            "numpy": np.__version__,
            "pillow": importlib.metadata.version("pillow"),
            "device": "CPU",
        },
        "evaluation_code_sha256": sha256_file(Path(__file__)),
        "timestamp": _now(),
    }


def _aggregate_temporal(per_sequence: list[dict[str, Any]]) -> dict[str, Any]:
    if not per_sequence:
        return {}
    aggregate: dict[str, Any] = {
        "sequence_count": len(per_sequence),
        "sampled_frame_count_per_sequence": per_sequence[0][
            "sampled_frame_count_per_sequence"
        ],
    }
    sum_keys = (
        "frame_TP",
        "frame_FP",
        "frame_FN",
        "track_continuity_transitions",
        "expected_adjacent_transitions",
        "detection_gap_count",
        "false_positive_track_count",
    )
    for key in sum_keys:
        aggregate[key] = sum(int(item[key]) for item in per_sequence)
    tp, fp, fn = aggregate["frame_TP"], aggregate["frame_FP"], aggregate["frame_FN"]
    aggregate["frame_precision"] = tp / (tp + fp) if tp + fp else 0.0
    aggregate["frame_recall"] = tp / (tp + fn) if tp + fn else 0.0
    aggregate["detection_persistence_fraction"] = (
        aggregate["frame_recall"] if tp + fn else None
    )
    transitions = aggregate["expected_adjacent_transitions"]
    aggregate["track_continuity_fraction"] = (
        aggregate["track_continuity_transitions"] / transitions if transitions else None
    )
    gap_values = [
        item["mean_detection_gap_frames"]
        for item in per_sequence
        if item["mean_detection_gap_frames"] is not None
    ]
    aggregate["mean_detection_gap_frames"] = (
        float(np.mean(gap_values)) if gap_values else None
    )
    gap_rates = [item["recovery_rate"] for item in per_sequence if item["recovery_rate"] is not None]
    aggregate["recovery_rate_mean_over_sequences_with_gaps"] = (
        float(np.mean(gap_rates)) if gap_rates else None
    )
    fp_means = [
        item["mean_false_positive_track_persistence_frames"]
        for item in per_sequence
    ]
    aggregate["mean_false_positive_track_persistence_frames"] = (
        float(np.mean(fp_means)) if fp_means else 0.0
    )
    aggregate["frame_processing_fraction"] = float(
        np.mean([item["frame_processing_fraction"] for item in per_sequence])
    )
    aggregate["mean_selected_model_inference_ms_per_sequence"] = float(
        np.mean(
            [
                item["selected_model_inference_ms_per_sequence"]
                for item in per_sequence
            ]
        )
    )
    aggregate["event_results_by_rule"] = {}
    for rule in TEMPORAL_RULES:
        fields = (
            "ground_truth_events",
            "detected_ground_truth_events",
            "missed_ground_truth_events",
            "persistent_false_positive_events",
        )
        totals = {
            field: sum(
                item["event_results_by_rule"][rule][field] for item in per_sequence
            )
            for field in fields
        }
        tp_events = totals["detected_ground_truth_events"]
        fp_events = totals["persistent_false_positive_events"]
        fn_events = totals["missed_ground_truth_events"]
        totals["event_precision"] = (
            tp_events / (tp_events + fp_events) if tp_events + fp_events else 0.0
        )
        totals["event_recall"] = (
            tp_events / (tp_events + fn_events) if tp_events + fn_events else 0.0
        )
        delays = [
            item["event_results_by_rule"][rule]["mean_detection_delay_frames"]
            for item in per_sequence
            if item["event_results_by_rule"][rule]["mean_detection_delay_frames"]
            is not None
        ]
        totals["mean_detection_delay_frames"] = (
            float(np.mean(delays)) if delays else None
        )
        aggregate["event_results_by_rule"][rule] = totals
    aggregate["event_results_by_class"] = {}
    for class_name in CLASS_NAMES.values():
        aggregate["event_results_by_class"][class_name] = {}
        for rule in TEMPORAL_RULES:
            records = [
                item["event_results_by_class"][class_name][rule]
                for item in per_sequence
            ]
            gt_events = sum(record["ground_truth_events"] for record in records)
            detected_events = sum(
                record["detected_ground_truth_events"] for record in records
            )
            false_events = sum(
                record["persistent_false_positive_events"] for record in records
            )
            aggregate["event_results_by_class"][class_name][rule] = {
                "ground_truth_events": gt_events,
                "detected_ground_truth_events": detected_events,
                "missed_ground_truth_events": gt_events - detected_events,
                "persistent_false_positive_events": false_events,
                "event_precision": (
                    detected_events / (detected_events + false_events)
                    if detected_events + false_events
                    else 0.0
                ),
                "event_recall": (
                    detected_events / gt_events if gt_events else None
                ),
                "status": "VALID_SAMPLE" if gt_events else "INSUFFICIENT_SAMPLE",
            }
    return aggregate


def _temporal_error_examples(
    sequence_groups: dict[str, list[dict[str, Any]]], threshold: float
) -> list[dict[str, Any]]:
    errors = []
    for sequence_id, frames in sequence_groups.items():
        matched_per_frame = []
        fp_per_frame = []
        for frame in frames:
            matched, false_predictions, false_negatives = _match_frame_detailed(
                frame["predictions"], frame["ground_truth"], threshold
            )
            matched_per_frame.append(
                {item["matched_object_id"]: item for item in matched}
            )
            fp_per_frame.append(false_predictions)
        object_ids = sorted(
            {
                gt["object_id"]
                for frame in frames
                for gt in frame["ground_truth"]
            }
        )
        for object_id in object_ids:
            visible = [
                object_id in {gt["object_id"] for gt in frame["ground_truth"]}
                for frame in frames
            ]
            detections = [
                object_id in matched_per_frame[index] for index in range(len(frames))
            ]
            if not any(detections) and any(visible):
                error_type = "PERSISTENT_FALSE_NEGATIVE"
            elif any(visible[index] and not detections[index] for index in range(len(frames))):
                error_type = "TEMPORARY_FALSE_NEGATIVE"
            else:
                continue
            missed_frame_ids = [
                index
                for index, (present, detected) in enumerate(zip(visible, detections))
                if present and not detected
            ]
            class_id = next(
                gt["class_id"]
                for frame in frames
                for gt in frame["ground_truth"]
                if gt["object_id"] == object_id
            )
            missed_ground_truth = [
                {
                    "frame_id": frame_id,
                    "object_id": object_id,
                    "class_id": class_id,
                    "xyxy": next(
                        gt["box"]
                        for gt in frames[frame_id]["ground_truth"]
                        if gt["object_id"] == object_id
                    ),
                }
                for frame_id in missed_frame_ids
            ]
            errors.append(
                {
                    "sequence_id": sequence_id,
                    "sequence_type": frames[0]["sequence_type"],
                    "frame_ids": missed_frame_ids,
                    "class": class_id,
                    "object_id": object_id,
                    "prediction": None,
                    "ground_truth": missed_ground_truth,
                    "temporal_rule": "NO_TEMPORAL_FILTER",
                    "error_type": error_type,
                }
            )
            detected_indices = [
                index for index, detected in enumerate(detections) if detected
            ]
            if detected_indices and detected_indices[0] > 0:
                first_detected = detected_indices[0]
                errors.append(
                    {
                        "sequence_id": sequence_id,
                        "sequence_type": frames[0]["sequence_type"],
                        "frame_ids": list(range(first_detected)),
                        "class": class_id,
                        "object_id": object_id,
                        "prediction": matched_per_frame[first_detected][object_id],
                        "ground_truth": [
                            item
                            for item in missed_ground_truth
                            if item["frame_id"] < first_detected
                        ],
                        "temporal_rule": "NO_TEMPORAL_FILTER",
                        "error_type": "DELAYED_DETECTION",
                    }
                )
            for miss_index in missed_frame_ids:
                if any(detections[:miss_index]) and not any(detections[miss_index + 1 :]):
                    errors.append(
                        {
                            "sequence_id": sequence_id,
                            "sequence_type": frames[0]["sequence_type"],
                            "frame_ids": [miss_index],
                            "class": class_id,
                            "object_id": object_id,
                            "prediction": None,
                            "ground_truth": [
                                item
                                for item in missed_ground_truth
                                if item["frame_id"] == miss_index
                            ],
                            "temporal_rule": "NO_TEMPORAL_FILTER",
                            "error_type": "MISSED_RECOVERY",
                        }
                    )
        fp_by_frame = []
        for index, false_predictions in enumerate(fp_per_frame):
            fp_by_frame.append(
                [
                    {"frame_index": index, **prediction}
                    for prediction in false_predictions
                ]
            )
        tracks = _associate_false_positive_tracks(fp_by_frame)
        for track in tracks:
            if len(track["observations"]) >= 2:
                errors.append(
                    {
                        "sequence_id": sequence_id,
                        "sequence_type": frames[0]["sequence_type"],
                        "frame_ids": [
                            item["frame_index"] for item in track["observations"]
                        ],
                        "class": track["class_id"],
                        "prediction": track["observations"][0],
                        "ground_truth": None,
                        "temporal_rule": "CLASS_AND_IOU_0.50_TRACK_ALLOWING_ONE_MISSING_FRAME",
                        "error_type": "PERSISTENT_FALSE_POSITIVE",
                    }
                )
            elif track["observations"]:
                item = track["observations"][0]
                errors.append(
                    {
                        "sequence_id": sequence_id,
                        "sequence_type": frames[0]["sequence_type"],
                        "frame_ids": [item["frame_index"]],
                        "class": track["class_id"],
                        "prediction": item,
                        "ground_truth": None,
                        "temporal_rule": "CLASS_AND_IOU_0.50_TRACK_ALLOWING_ONE_MISSING_FRAME",
                        "error_type": "TRANSIENT_FALSE_POSITIVE",
                    }
                )
    return errors


def _write_records(metrics: dict[str, Any], manifest_sha: str) -> None:
    expected_files = {
        "metrics.json",
        "experiment.json",
        *(f"CVR2-CV-{number:03d}.json" for number in range(17, 25)),
    }
    if EXPERIMENT_ROOT.exists():
        unexpected = {
            path.name for path in EXPERIMENT_ROOT.iterdir() if path.name not in expected_files
        }
        if unexpected:
            raise FileExistsError(
                f"Refusing to overwrite unexpected R6 experiment artifacts: {sorted(unexpected)}"
            )
    else:
        EXPERIMENT_ROOT.mkdir(parents=True)
    provenance = {
        "source_dataset": "D1",
        "source_split": "test",
        "source_hash": metrics["source_dataset_composite_sha256"],
        "dataset_manifest_sha256": manifest_sha,
        "sequence_generation_method": "Deterministic controlled synthetic temporal frames derived from D1 test still images; not recorded video",
        "seed": MASTER_SEED,
        "frame_count": FRAME_COUNT,
        "transformation_parameters": "Per-frame records in the checksummed sequence manifest",
        "model_id": metrics["model_id"],
        "model_hash": metrics["model_sha256"],
        "checkpoint_hash": metrics["checkpoint_sha256"],
        "confidence_threshold": PRIMARY_THRESHOLD,
        "secondary_confidence_threshold": SECONDARY_THRESHOLD,
        "IoU_threshold": EVALUATION_IOU,
        "temporal_association_rule": metrics["temporal_association"],
        "temporal_filter": list(TEMPORAL_RULES),
        "environment": metrics["environment"],
        "timestamp": metrics["timestamp"],
        "research_code_sha256": metrics["evaluation_code_sha256"],
        "production_integration": False,
        "research_only": True,
    }
    designs = {
        "CVR2-CV-017": {
            "title": "Temporal sequence construction",
            "sequence_generation_method": "Deterministic synthetic sequences from D1 test images",
            "seed": MASTER_SEED,
            "frame_count": FRAME_COUNT,
            "transformation_parameters": "See dataset manifest frame records",
        },
        "CVR2-CV-018": {"title": "Frame-level baseline", "temporal_filter": "NONE"},
        "CVR2-CV-019": {
            "title": "Temporal persistence analysis",
            "temporal_association_rule": metrics["temporal_association"],
        },
        "CVR2-CV-020": {
            "title": "Frame sampling-rate study",
            "sampling_strides": SAMPLING_STRIDES,
        },
        "CVR2-CV-021": {
            "title": "Controlled camera-motion study",
            "transformation_parameters": "Bounded integer translation, labels propagated and clipped",
        },
        "CVR2-CV-022": {
            "title": "Temporal filtering ablation",
            "temporal_filters": list(TEMPORAL_RULES),
        },
        "CVR2-CV-023": {
            "title": "Temporal error analysis",
            "temporal_association_rule": metrics["temporal_association"],
        },
        "CVR2-CV-024": {
            "title": "Final R6 evaluation and conclusions",
            "status": metrics["status"],
        },
    }
    for experiment_id, design in designs.items():
        record = {
            "experiment_id": experiment_id,
            **design,
            **provenance,
            "output_manifest_sha256": manifest_sha,
            "metrics_file": "metrics.json",
        }
        (EXPERIMENT_ROOT / f"{experiment_id}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    metrics_path = EXPERIMENT_ROOT / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    experiment = {
        "experiment_id": "CVR2-CV-024",
        "title": "Final R6 evaluation and conclusions",
        **provenance,
        "evaluation_code_sha256": metrics["evaluation_code_sha256"],
        "sequence_manifest_sha256": manifest_sha,
        "metrics_sha256": sha256_file(metrics_path),
        "status": metrics["status"],
        "real_world_video_evaluation": "REAL_WORLD_VIDEO_EVALUATION_NOT_AVAILABLE",
    }
    (EXPERIMENT_ROOT / "experiment.json").write_text(
        json.dumps(experiment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_experiment() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--evaluate-existing":
        manifest_path = R6_ROOT / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"R6 sequence manifest does not exist: {manifest_path}")
        manifest_sha = sha256_file(manifest_path)
    else:
        manifest_path, manifest_sha = generate_sequences()
    result = evaluate_sequences()
    result["sequence_manifest_path"] = manifest_path.relative_to(REPO_ROOT).as_posix()
    result["sequence_manifest_sha256"] = manifest_sha
    _write_records(result, manifest_sha)
    print(f"Generated {R6_ROOT}")
    print(f"Sequence manifest SHA-256: {manifest_sha}")
    print(f"Experiment records: {EXPERIMENT_ROOT}")
    print(f"Status: {result['status']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Generate and evaluate R6 synthetic temporal sequences; existing output is never overwritten.")
    else:
        run_experiment()
