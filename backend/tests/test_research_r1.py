"""
CVKI Research v2.x - R1 Dataset QA & Data Quality Test Suite
Tests D1 dataset registration, D0 immutability, licensing, file validation,
duplicate detection, near-duplicate hashing, YOLO annotation validation,
visual QA, split leakage audit, hard negatives, privacy, and manifest checksums.
"""

import json
from pathlib import Path
import tempfile
import numpy as np
from PIL import Image
import pytest

from ai.research.dataset_registry import DatasetRegistry, DatasetEntry, SplitDefinition
from ai.research.dataset_qa import (
    SourceLicenseRecord,
    FileValidationResult,
    validate_image_file,
    ExactDuplicateDetector,
    NearDuplicateDetector,
    compute_dhash,
    hamming_distance,
    BoundingBox,
    validate_yolo_annotation_line,
    validate_yolo_annotation_file,
    perform_visual_annotation_qa,
    analyze_image_quality,
    audit_split_leakage,
    ALLOWED_CLASS_IDS,
)
from ai.research.scripts.audit_dataset import audit_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_01_d1_dataset_registration_and_status():
    """Verify D1 is properly registered with RESEARCH_CANDIDATE status and parent D0."""
    registry = DatasetRegistry()
    d1 = registry.get("D1")
    assert d1 is not None, "D1 must be registered in DatasetRegistry"
    assert d1["dataset_id"] == "D1"
    assert d1["dataset_version"] == "1.0"
    assert d1["status"] == "RESEARCH_CANDIDATE"
    assert d1["parent_dataset"] == "D0"
    assert d1["image_count"] == 122
    assert d1["label_count"] == 122
    assert d1["split_definition"]["train_count"] == 86
    assert d1["split_definition"]["val_count"] == 18
    assert d1["split_definition"]["test_count"] == 18
    assert "composite_sha256" in d1["checksum_inventory"]
    assert len(d1["checksum_inventory"]["composite_sha256"]) == 64


def test_02_d0_immutability_protection():
    """Ensure D0 baseline cannot be overwritten or re-registered."""
    registry = DatasetRegistry()
    d0 = registry.get("D0")
    assert d0 is not None
    assert d0["status"] == "FROZEN_PRODUCTION_BASELINE"
    assert d0["image_count"] == 605

    # Attempting to register D0 must raise ValueError
    with pytest.raises(ValueError, match="D0 is the FROZEN_PRODUCTION_BASELINE"):
        registry.register(
            DatasetEntry(
                dataset_id="D0",
                dataset_version="2.0",
                description="Illegal overwrite",
                source="test",
                class_schema=["pothole"],
                image_count=100,
            )
        )


def test_03_license_and_provenance_validation():
    """Verify license admission logic and quarantine behavior."""
    permitted_rec = SourceLicenseRecord(
        source_id="SRC-TEST-01",
        source_name="Open Municipal Portal",
        source_url="https://civic.org/data",
        provider="Dept of Transport",
        license="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        collection_date="2026-10-19",
        geographic_scope="Urban",
        image_count=50,
        class_scope=["open_damaged_manhole"],
        usage_permission="PERMITTED_RESEARCH",
        attribution_requirement=True,
    )
    assert permitted_rec.is_admissible() is True

    quarantined_rec = SourceLicenseRecord(
        source_id="SRC-TEST-02",
        source_name="Scraped Web Blog",
        source_url="https://randomblog.com/photo",
        provider="Unknown Blogger",
        license="UNKNOWN",
        license_url="UNKNOWN",
        collection_date="2026-10-19",
        geographic_scope="UNKNOWN",
        image_count=10,
        class_scope=["road_waterlogging"],
        usage_permission="QUARANTINED",
        attribution_requirement=False,
    )
    assert quarantined_rec.is_admissible() is False


def test_04_file_validation_and_corruption_rejection():
    """Verify file validation rejects non-existent, empty, and corrupted files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Non-existent file
        res_nonexistent = validate_image_file(tmp_path / "missing.jpg")
        assert res_nonexistent.status == "REJECTED"
        assert "not a file" in res_nonexistent.reason

        # 2. Zero-byte file
        zero_file = tmp_path / "zero.jpg"
        zero_file.touch()
        res_zero = validate_image_file(zero_file)
        assert res_zero.status == "REJECTED"
        assert "Zero-byte" in res_zero.reason

        # 3. Corrupted header
        corrupt_file = tmp_path / "corrupt.jpg"
        corrupt_file.write_bytes(b"INVALID_HEADER_NOT_A_JPEG_DATA_STREAM")
        res_corrupt = validate_image_file(corrupt_file)
        assert res_corrupt.status == "REJECTED"
        assert "Corrupted" in res_corrupt.reason

        # 4. Valid image
        valid_file = tmp_path / "valid.jpg"
        img = Image.fromarray(np.zeros((100, 100, 3), dtype=np.uint8))
        img.save(valid_file, "JPEG")
        res_valid = validate_image_file(valid_file)
        assert res_valid.status == "VALID"
        assert res_valid.width == 100
        assert res_valid.height == 100
        assert len(res_valid.sha256) == 64


def test_05_exact_duplicate_detection():
    """Verify ExactDuplicateDetector detects bitwise identical files without deleting."""
    detector = ExactDuplicateDetector()
    detector.register("image_a.jpg", "abcdef1234567890")
    detector.register("image_b.jpg", "abcdef1234567890")
    detector.register("image_c.jpg", "unique9876543210")

    duplicates = detector.get_duplicate_groups()
    assert len(duplicates) == 1
    assert "abcdef1234567890" in duplicates
    assert set(duplicates["abcdef1234567890"]) == {"image_a.jpg", "image_b.jpg"}


def test_06_near_duplicate_detection_dhash():
    """Verify dHash perceptual hashing and near-duplicate detection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create base image
        img1_path = tmp_path / "img1.png"
        arr1 = np.zeros((128, 128, 3), dtype=np.uint8)
        arr1[30:70, 30:70] = 200
        Image.fromarray(arr1).save(img1_path)

        # Create slightly modified image (near duplicate)
        img2_path = tmp_path / "img2.png"
        arr2 = arr1.copy()
        arr2[32:68, 32:68] = 195
        Image.fromarray(arr2).save(img2_path)

        # Create completely different image
        img3_path = tmp_path / "img3.png"
        arr3 = np.zeros((128, 128, 3), dtype=np.uint8)
        arr3[90:120, 10:40] = 255
        Image.fromarray(arr3).save(img3_path)

        h1 = compute_dhash(img1_path)
        h2 = compute_dhash(img2_path)
        h3 = compute_dhash(img3_path)

        dist_1_2 = hamming_distance(h1, h2)
        dist_1_3 = hamming_distance(h1, h3)

        assert dist_1_2 <= 4, f"Near duplicates should have small distance, got {dist_1_2}"
        assert dist_1_3 > dist_1_2, "Different images should have higher distance"

        detector = NearDuplicateDetector(distance_threshold=4)
        detector.register(str(img1_path), h1)
        detector.register(str(img2_path), h2)
        detector.register(str(img3_path), h3)

        pairs = detector.find_near_duplicate_pairs()
        assert len(pairs) >= 1
        assert pairs[0]["status"] == "NEAR_DUPLICATE_REVIEW"


def test_07_annotation_validation_yolo_bounds():
    """Verify YOLO bounding box parsing, coordinate bounds, and class verification."""
    # Valid line: class 0, x=0.5, y=0.5, w=0.2, h=0.3
    box, err = validate_yolo_annotation_line("0 0.500000 0.500000 0.200000 0.300000")
    assert err is None
    assert box is not None
    assert box.class_id == 0
    assert box.x_center == 0.5

    # Invalid class ID (e.g. 5)
    box, err = validate_yolo_annotation_line("5 0.5 0.5 0.2 0.2")
    assert err is not None
    assert "Invalid class_id 5" in err

    # Out of bounds coordinate (> 1.0)
    box, err = validate_yolo_annotation_line("1 1.25 0.5 0.2 0.2")
    assert err is not None
    assert "x_center 1.25 out of bounds" in err

    # Negative coordinate
    box, err = validate_yolo_annotation_line("2 0.5 -0.1 0.2 0.2")
    assert err is not None
    assert "y_center -0.1 out of bounds" in err

    # NaN / Inf coordinates
    box, err = validate_yolo_annotation_line("0 nan 0.5 0.2 0.2")
    assert err is not None
    assert "NaN detected" in err


def test_08_visual_annotation_qa():
    """Verify visual QA detection for tiny boxes, giant boxes, and unusual aspect ratios."""
    # 1. Normal box
    normal_box = BoundingBox(class_id=0, x_center=0.5, y_center=0.5, width=0.2, height=0.2)
    flags = perform_visual_annotation_qa([normal_box])
    assert len(flags) == 0

    # 2. Very small box (area < 0.002)
    tiny_box = BoundingBox(class_id=1, x_center=0.5, y_center=0.5, width=0.01, height=0.01)
    flags = perform_visual_annotation_qa([tiny_box])
    assert any(f.flag_type == "VERY_SMALL" for f in flags)

    # 3. Very large box (area > 0.90)
    giant_box = BoundingBox(class_id=2, x_center=0.5, y_center=0.5, width=0.98, height=0.98)
    flags = perform_visual_annotation_qa([giant_box])
    assert any(f.flag_type == "VERY_LARGE" for f in flags)

    # 4. Unusual aspect ratio (width/height > 10)
    needle_box = BoundingBox(class_id=0, x_center=0.5, y_center=0.5, width=0.8, height=0.05)
    flags = perform_visual_annotation_qa([needle_box])
    assert any(f.flag_type == "UNUSUAL_ASPECT" for f in flags)


def test_09_image_quality_analysis():
    """Verify image quality analysis computes brightness, contrast, and blur score."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_img = Path(tmp_dir) / "test_pattern.png"
        # Generate checkerboard pattern
        arr = np.indices((100, 100)).sum(axis=0) % 2 * 255
        arr = np.stack([arr]*3, axis=-1).astype(np.uint8)
        Image.fromarray(arr).save(tmp_img)

        metrics = analyze_image_quality(tmp_img)
        assert metrics.width == 100
        assert metrics.height == 100
        assert metrics.aspect_ratio == 1.0
        assert metrics.blur_score > 0
        assert metrics.quality_verdict in ("ACCEPT", "REVIEW")


def test_10_hard_negative_tracking():
    """Verify D1 hard negatives are recorded in metadata and have empty label files."""
    d1_dir = REPO_ROOT / "ai" / "research" / "datasets" / "D1"
    hn_file = d1_dir / "metadata" / "hard_negatives.json"
    assert hn_file.exists(), "hard_negatives.json metadata must exist"

    with open(hn_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "hard_negatives" in data
    assert len(data["hard_negatives"]) >= 4

    # Check that hard negative images have corresponding empty 0-byte labels
    images_manifest = d1_dir / "manifests" / "images_manifest.json"
    with open(images_manifest, "r", encoding="utf-8") as f:
        img_records = json.load(f)["images"]

    hn_images = [r for r in img_records if r.get("is_hard_negative")]
    assert len(hn_images) == 32

    labels_dir = d1_dir / "labels"
    for hn in hn_images:
        lbl_file = labels_dir / f"{Path(hn['relative_path']).stem}.txt"
        assert lbl_file.exists(), f"Label file {lbl_file} must exist for hard negative"
        assert lbl_file.stat().st_size == 0, f"Hard negative label {lbl_file} must be 0 bytes"


def test_11_split_leakage_prevention():
    """Verify audit_split_leakage detects cross-split leakage and confirms D1 has NO KNOWN LEAKAGE."""
    # Test 1: Clean splits with distant 64-bit hashes
    clean_splits = {
        "train": [{"image_path": "img1.jpg", "sha256": "sha1", "dhash": 0x0000000000000000}],
        "val": [{"image_path": "img2.jpg", "sha256": "sha2", "dhash": 0x0F0F0F0F0F0F0F0F}],
        "test": [{"image_path": "img3.jpg", "sha256": "sha3", "dhash": 0xF0F0F0F0F0F0F0F0}],
    }
    report_clean = audit_split_leakage(clean_splits)
    assert report_clean.verdict == "NO KNOWN LEAKAGE"
    assert len(report_clean.exact_duplicates_across_splits) == 0
    assert len(report_clean.near_duplicates_across_splits) == 0

    # Test 2: Injected exact duplicate across train and test
    leaky_splits = {
        "train": [{"image_path": "img1.jpg", "sha256": "sha_shared", "dhash": 0x123456789ABCDEF0}],
        "val": [{"image_path": "img2.jpg", "sha256": "sha2", "dhash": 0x0F0F0F0F0F0F0F0F}],
        "test": [{"image_path": "img1_dup.jpg", "sha256": "sha_shared", "dhash": 0x123456789ABCDEF0}],
    }
    report_leaky = audit_split_leakage(leaky_splits)
    assert report_leaky.verdict == "LEAKAGE_DETECTED"
    assert len(report_leaky.exact_duplicates_across_splits) == 1

    # Test 3: Actual D1 dataset audit
    d1_dir = REPO_ROOT / "ai" / "research" / "datasets" / "D1"
    audit_file = d1_dir / "qa" / "dataset_audit_report.json"
    with open(audit_file, "r", encoding="utf-8") as f:
        d1_audit = json.load(f)
    assert d1_audit["leakage_audit"]["verdict"] == "NO KNOWN LEAKAGE"
    assert len(d1_audit["leakage_audit"]["exact_duplicates_across_splits"]) == 0
    assert len(d1_audit["leakage_audit"]["near_duplicates_across_splits"]) == 0


def test_12_privacy_review_verification():
    """Verify privacy review results in images_manifest.json are all CLEAR."""
    manifest_path = REPO_ROOT / "ai" / "research" / "datasets" / "D1" / "manifests" / "images_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for img in data["images"]:
        assert img["privacy_status"] == "CLEAR", f"Image {img['relative_path']} must have privacy status CLEAR"


def test_13_dataset_manifests_and_checksum_integrity():
    """Verify D1 dataset, images, and labels manifests exist and have consistent counts."""
    d1_dir = REPO_ROOT / "ai" / "research" / "datasets" / "D1"
    m_dir = d1_dir / "manifests"

    dataset_m = m_dir / "dataset_manifest.json"
    images_m = m_dir / "images_manifest.json"
    labels_m = m_dir / "labels_manifest.json"

    assert dataset_m.exists()
    assert images_m.exists()
    assert labels_m.exists()

    with open(dataset_m, "r", encoding="utf-8") as f:
        ds_data = json.load(f)
    with open(images_m, "r", encoding="utf-8") as f:
        im_data = json.load(f)
    with open(labels_m, "r", encoding="utf-8") as f:
        lb_data = json.load(f)

    assert ds_data["total_images"] == 122
    assert ds_data["total_labels"] == 122
    assert len(im_data["images"]) == 122
    assert len(lb_data["labels"]) == 122
    assert ds_data["classes"] == ["open_damaged_manhole", "damaged_missing_road_sign", "road_waterlogging"]


def test_14_automated_audit_script_execution():
    """Verify audit_dataset function runs programmatically and passes."""
    report = audit_dataset(dataset_name="D1")
    assert report["composite_verdict"] == "PASSED"
    assert report["total_images"] == 122
    assert report["total_annotations"] == 90
    assert report["class_balance_status"] == "BALANCED"
    assert report["leakage_audit"]["verdict"] == "NO KNOWN LEAKAGE"
