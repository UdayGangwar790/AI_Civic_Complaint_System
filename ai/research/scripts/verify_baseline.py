#!/usr/bin/env python3
"""
CVKI Research v2.x - Baseline Verification Script
Verifies that the frozen M1.13 weights and D0 dataset (dataset_m1_13) have not been altered.
"""

from pathlib import Path
import sys

# Ensure repository root is on sys.path
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

from ai.research.checksum import compute_file_sha256, verify_dataset_manifest
import json

EXPECTED_M113_SHA = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
EXPECTED_DATASET_COUNT = 605


def verify_baseline() -> bool:
    print("=" * 70)
    print("CVKI Research v2.x - Production Baseline Integrity Check")
    print("=" * 70)

    # 1. Verify Weights Checksum
    weights_path = root_dir / "ai" / "computer_vision" / "training" / "runs" / "yolov8n_m1_13" / "weights" / "best.pt"
    if not weights_path.exists():
        print(f"[FAIL] M1.13 weights file not found: {weights_path}")
        return False

    actual_sha = compute_file_sha256(weights_path)
    print(f"M1.13 Checkpoint: {weights_path}")
    print(f"Expected SHA-256: {EXPECTED_M113_SHA}")
    print(f"Actual SHA-256:   {actual_sha}")

    if actual_sha != EXPECTED_M113_SHA:
        print("[FAIL] M1.13 weights SHA-256 mismatch! Production baseline has been modified.")
        return False
    print("[PASS] M1.13 weights checksum is exact.")

    # 2. Verify Dataset Inventory
    dataset_dir = root_dir / "ai" / "computer_vision" / "dataset_m1_13"
    if not dataset_dir.is_dir():
        print(f"[FAIL] Production dataset directory not found: {dataset_dir}")
        return False

    manifest_file = root_dir / "ai" / "research" / "registry" / "d0_manifest.json"
    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        is_valid, errors = verify_dataset_manifest(dataset_dir, manifest)
        if not is_valid:
            print("[FAIL] Dataset D0 inventory verification failed:")
            for err in errors:
                print(f"  - {err}")
            return False
        print(f"[PASS] Dataset D0 manifest verified. Exactly {manifest['file_count']} files match composite SHA.")
    else:
        # Fallback file count check
        files = list(dataset_dir.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        print(f"Dataset File Count: {file_count} (Expected: {EXPECTED_DATASET_COUNT})")
        if file_count != EXPECTED_DATASET_COUNT:
            print(f"[FAIL] Dataset file count mismatch: {file_count} vs {EXPECTED_DATASET_COUNT}")
            return False
        print("[PASS] Dataset file count exact.")

    print("=" * 70)
    print("ALL BASELINE INTEGRITY CHECKS PASSED: FROZEN BASELINE INTACT.")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = verify_baseline()
    sys.exit(0 if success else 1)
