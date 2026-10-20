#!/usr/bin/env python3
"""
CVKI Research v2.x - R1 Automated Dataset Audit Tool
Path: ai/research/scripts/audit_dataset.py

Performs comprehensive automated scientific quality auditing on a CVKI research dataset:
- File integrity and dimension validation
- Exact duplicate detection (SHA-256)
- Near-duplicate detection (dHash perceptual hashing)
- Annotation bounding box and class ID validation
- Visual annotation QA (tiny boxes, giant boxes, edge-touching, aspect ratios)
- Image quality metrics (resolution, blur, brightness, contrast)
- Privacy review (identifiable artifact flags)
- Hard negative verification
- Class balance, environmental, and source distribution
- Cross-split data leakage audit (Train/Val/Test)
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.research.dataset_qa import (
    validate_image_file,
    ExactDuplicateDetector,
    NearDuplicateDetector,
    compute_dhash,
    validate_yolo_annotation_file,
    perform_visual_annotation_qa,
    analyze_image_quality,
    audit_split_leakage,
)


def audit_dataset(dataset_name: str = "D1", output_json: Path = None) -> Dict[str, Any]:
    dataset_dir = REPO_ROOT / "ai" / "research" / "datasets" / dataset_name
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"
    splits_dir = dataset_dir / "splits"
    metadata_dir = dataset_dir / "metadata"
    qa_dir = dataset_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect all images
    image_paths = sorted(list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")))
    total_images = len(image_paths)

    # 2. File and Image Quality Validation
    file_records = []
    quality_records = []
    exact_detector = ExactDuplicateDetector()
    near_detector = NearDuplicateDetector(distance_threshold=4)
    sha_map = {}
    dhash_map = {}

    for img_path in image_paths:
        f_val = validate_image_file(img_path)
        file_records.append(f_val)
        exact_detector.register(str(img_path), f_val.sha256)
        sha_map[img_path.name] = f_val.sha256

        q_val = analyze_image_quality(img_path)
        quality_records.append(q_val)

        dh = compute_dhash(img_path)
        dhash_map[img_path.name] = dh
        near_detector.register(str(img_path), dh)

    # 3. Exact and Near Duplicates
    exact_duplicates = exact_detector.get_duplicate_groups()
    near_duplicates = near_detector.find_near_duplicate_pairs()

    # 4. Annotations and Visual QA
    label_records = []
    visual_qa_flags = []
    class_counts = {0: 0, 1: 0, 2: 0}
    total_boxes = 0

    for img_path in image_paths:
        lbl_path = labels_dir / f"{img_path.stem}.txt"
        lbl_val = validate_yolo_annotation_file(lbl_path)
        label_records.append(lbl_val)

        if lbl_val.is_valid and lbl_val.boxes:
            flags = perform_visual_annotation_qa(lbl_val.boxes)
            visual_qa_flags.extend(flags)
            for box in lbl_val.boxes:
                if box.class_id in class_counts:
                    class_counts[box.class_id] += 1
                total_boxes += 1

    # Class balance assessment
    max_c = max(class_counts.values()) if any(class_counts.values()) else 1
    min_c = min(class_counts.values()) if any(class_counts.values()) else 0
    ratio = max_c / max(min_c, 1)
    if ratio < 1.5:
        balance_rating = "BALANCED"
    elif ratio < 3.0:
        balance_rating = "MODERATELY IMBALANCED"
    else:
        balance_rating = "HIGHLY IMBALANCED"

    # 5. Metadata analysis
    sources_file = metadata_dir / "sources.json"
    sources_data = []
    if sources_file.exists():
        with open(sources_file, "r", encoding="utf-8") as f:
            sources_data = json.load(f)

    hard_negatives_file = metadata_dir / "hard_negatives.json"
    hard_negatives_count = 0
    if hard_negatives_file.exists():
        with open(hard_negatives_file, "r", encoding="utf-8") as f:
            hn_content = json.load(f)
            if isinstance(hn_content, dict):
                hard_negatives_count = len(hn_content.get("hard_negatives", []))
            elif isinstance(hn_content, list):
                hard_negatives_count = len(hn_content)

    # Privacy review analysis from images_manifest.json
    manifest_file = dataset_dir / "manifests" / "images_manifest.json"
    privacy_records = []
    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
            privacy_records = manifest_data.get("images", [])

    # 6. Split and Leakage Audit
    split_records = {"train": [], "val": [], "test": []}
    for split_name in ["train", "val", "test"]:
        split_txt = splits_dir / f"{split_name}.txt"
        if split_txt.exists():
            with open(split_txt, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                for line in lines:
                    fname = Path(line).name
                    split_records[split_name].append({
                        "image_path": line,
                        "sha256": sha_map.get(fname, ""),
                        "dhash": dhash_map.get(fname, 0),
                    })

    leakage_report = audit_split_leakage(split_records, near_dup_threshold=4)

    # 7. Overall Summary
    audit_summary = {
        "dataset_name": dataset_name,
        "dataset_path": str(dataset_dir),
        "total_images": total_images,
        "total_annotations": total_boxes,
        "class_distribution": {
            "0_open_damaged_manhole": class_counts.get(0, 0),
            "1_damaged_missing_road_sign": class_counts.get(1, 0),
            "2_road_waterlogging": class_counts.get(2, 0),
        },
        "class_balance_status": balance_rating,
        "hard_negatives_count": hard_negatives_count,
        "source_registry_count": len(sources_data),
        "file_validation": {
            "total_files": len(file_records),
            "valid_files": sum(1 for r in file_records if r.status == "VALID"),
            "corrupted_or_invalid": sum(1 for r in file_records if r.status != "VALID"),
        },
        "duplicates": {
            "exact_duplicate_groups": len(exact_duplicates),
            "near_duplicate_pairs": len(near_duplicates),
        },
        "leakage_audit": {
            "total_images": leakage_report.total_images,
            "train_count": leakage_report.train_count,
            "val_count": leakage_report.val_count,
            "test_count": leakage_report.test_count,
            "exact_duplicates_across_splits": leakage_report.exact_duplicates_across_splits,
            "near_duplicates_across_splits": leakage_report.near_duplicates_across_splits,
            "verdict": leakage_report.verdict,
        },
        "quality_overview": {
            "acceptable": sum(1 for q in quality_records if q.quality_verdict == "ACCEPT"),
            "review": sum(1 for q in quality_records if q.quality_verdict == "REVIEW"),
            "rejected": sum(1 for q in quality_records if q.quality_verdict == "REJECT"),
        },
        "privacy_overview": {
            "total_reviewed": len(privacy_records),
            "clear": sum(1 for p in privacy_records if p.get("privacy_status") == "CLEAR"),
            "review_required": sum(1 for p in privacy_records if p.get("privacy_status") == "REVIEW_REQUIRED"),
            "redaction_required": sum(1 for p in privacy_records if p.get("privacy_status") == "REDACTION_REQUIRED"),
        },
        "splits_breakdown": {
            "train": len(split_records.get("train", [])),
            "val": len(split_records.get("val", [])),
            "test": len(split_records.get("test", [])),
        },
        "composite_verdict": (
            "PASSED"
            if leakage_report.verdict == "NO KNOWN LEAKAGE"
            and sum(1 for r in file_records if r.status != "VALID") == 0
            else "FAILED"
        ),
    }

    # Save JSON output
    target_json = output_json or (qa_dir / "dataset_audit_report.json")
    with open(target_json, "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2)

    return audit_summary


def print_audit_report(summary: Dict[str, Any]) -> None:
    print("\n" + "=" * 70)
    print(f"CVKI RESEARCH DATASET AUDIT REPORT: {summary['dataset_name']}")
    print("=" * 70)
    print(f"Path: {summary['dataset_path']}")
    print(f"Total Usable Images:      {summary['total_images']}")
    print(f"Total YOLO Annotations:   {summary['total_annotations']}")
    print(f"Hard Negatives:           {summary['hard_negatives_count']}")
    print(f"Class Balance Status:     {summary['class_balance_status']}")
    print("\nClass Distribution:")
    for cls_name, count in summary["class_distribution"].items():
        print(f"  - {cls_name}: {count}")

    print("\nSplit Distribution:")
    for s_name, count in summary["splits_breakdown"].items():
        print(f"  - {s_name}: {count}")

    print("\nData Integrity & QA:")
    print(f"  - File Validation:        {summary['file_validation']['valid_files']} accepted / {summary['file_validation']['corrupted_or_invalid']} rejected")
    print(f"  - Exact Duplicate Groups: {summary['duplicates']['exact_duplicate_groups']}")
    print(f"  - Near-Duplicate Pairs:   {summary['duplicates']['near_duplicate_pairs']}")
    print(f"  - Cross-Split Leakage:    {summary['leakage_audit']['verdict']}")
    print(f"  - Quality Clear/Review:   {summary['quality_overview']['acceptable']} / {summary['quality_overview']['review']}")
    print(f"  - Privacy Clear/Review:   {summary['privacy_overview']['clear']} / {summary['privacy_overview']['review_required']}")

    print("\nLeakage Audit Details:")
    print(f"  - Cross-split exact:      {len(summary['leakage_audit']['exact_duplicates_across_splits'])}")
    print(f"  - Cross-split near:       {len(summary['leakage_audit']['near_duplicates_across_splits'])}")
    print(f"  - Final Verdict:          {summary['leakage_audit']['verdict']}")
    print("-" * 70)
    print(f"OVERALL COMPOSITE VERDICT: {summary['composite_verdict']}")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Audit a CVKI Research Dataset")
    parser.add_argument("--dataset", default="D1", help="Name of dataset directory (default: D1)")
    parser.add_argument("--output", default=None, help="Path to write output JSON")
    args = parser.parse_args()

    out_path = Path(args.output) if args.output else None
    summary = audit_dataset(dataset_name=args.dataset, output_json=out_path)
    print_audit_report(summary)

    if summary["composite_verdict"] != "PASSED":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
