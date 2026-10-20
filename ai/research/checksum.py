"""
CVKI Research v2.x - R0 Checksum & Integrity Utilities
Calculates file SHA-256, directory inventory manifests, and dataset integrity verification.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def compute_file_sha256(file_path: Path | str, chunk_size: int = 65536) -> str:
    """Computes hexadecimal SHA-256 hash for a single file."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_dataset_manifest(dataset_dir: Path | str) -> dict[str, Any]:
    """
    Traverses dataset_dir and builds a deterministic inventory manifest.
    Each file entry captures relative_path, file_size (bytes), and sha256 checksum.
    Also computes a composite inventory checksum across all entries sorted by relative path.
    """
    root = Path(dataset_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"Directory not found: {root}")

    file_entries = []
    composite_hasher = hashlib.sha256()

    for dirpath, _, filenames in os.walk(root):
        for fname in sorted(filenames):
            full_path = Path(dirpath) / fname
            rel_path = full_path.relative_to(root).as_posix()
            size_bytes = full_path.stat().st_size
            sha = compute_file_sha256(full_path)

            file_entries.append({
                "relative_path": rel_path,
                "file_size": size_bytes,
                "sha256": sha,
            })
            # Feed composite hash with deterministic format
            composite_hasher.update(f"{rel_path}:{size_bytes}:{sha}\n".encode("utf-8"))

    # Sort deterministically by relative path
    file_entries.sort(key=lambda x: x["relative_path"])
    composite_inventory_sha = composite_hasher.hexdigest()

    return {
        "dataset_path": str(root.as_posix()),
        "file_count": len(file_entries),
        "inventory_sha256": composite_inventory_sha,
        "files": file_entries,
    }


def verify_dataset_manifest(
    dataset_dir: Path | str,
    manifest: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Verifies that the files currently on disk in dataset_dir match the manifest.
    Returns (is_valid, list_of_discrepancies).
    """
    root = Path(dataset_dir)
    current_manifest = generate_dataset_manifest(root)

    discrepancies = []
    if current_manifest["file_count"] != manifest.get("file_count"):
        discrepancies.append(
            f"File count mismatch: expected {manifest.get('file_count')}, got {current_manifest['file_count']}"
        )

    if current_manifest["inventory_sha256"] != manifest.get("inventory_sha256"):
        discrepancies.append(
            f"Inventory composite SHA mismatch: expected {manifest.get('inventory_sha256')}, "
            f"got {current_manifest['inventory_sha256']}"
        )

    # Detailed per-file check if composite fails
    if discrepancies:
        expected_files = {f["relative_path"]: f for f in manifest.get("files", [])}
        actual_files = {f["relative_path"]: f for f in current_manifest["files"]}

        added = set(actual_files.keys()) - set(expected_files.keys())
        removed = set(expected_files.keys()) - set(actual_files.keys())
        modified = []

        for p in set(expected_files.keys()) & set(actual_files.keys()):
            if (
                expected_files[p]["sha256"] != actual_files[p]["sha256"]
                or expected_files[p]["file_size"] != actual_files[p]["file_size"]
            ):
                modified.append(p)

        if added:
            discrepancies.append(f"Unexpected files added ({len(added)}): {sorted(list(added))[:5]}")
        if removed:
            discrepancies.append(f"Expected files missing ({len(removed)}): {sorted(list(removed))[:5]}")
        if modified:
            discrepancies.append(f"Files modified ({len(modified)}): {sorted(modified)[:5]}")

    return (len(discrepancies) == 0, discrepancies)
