"""R8 source admission, privacy, independence, and freeze tests."""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
R8_ROOT = REPO_ROOT / "ai" / "research" / "experiments" / "R8"

M113_SHA256 = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
R3_SHA256 = "72c57f6f052321abfe798edbef862848a2441a3b17fa16997376db93711bbc28"
D0_FILE_COUNT = 605
D0_TREE_SHA256 = "e609ad2e701b1e668d5d1f9474be6b1e2a8240bc61a4adbe1fee096db4ec2658"
R5_MANIFEST_SHA256 = "d36bd0f653c5650f628ad26d9397b5e843154931f23177918235b94b2f899f0e"
R5_METRICS_SHA256 = "a07f0ac9271b5af85689346632e181201fb453918408539505ed23059c39b13e"
R6_MANIFEST_SHA256 = "2c793e05dbc068d0ea1907e466a352a06b0728330fef580cd20485464408b348"
R6_METRICS_SHA256 = "907fc80c19372d344f67b7eb9990169fd47d1315c812b98cdf743513feca7831"
R7_FROZEN_HASHES = {
    "ai/research/experiments/R7/experiment.json": "db075478277425a249dd48366406db95142018569eb58f91df4dca9d1d5b0ce0",
    "ai/research/experiments/R7/case_set.json": "cf38f78740d6bd0f724eb8f45e7321514572c8fa55a68f65c01da8df16e866e4",
    "ai/research/experiments/R7/provenance.json": "ddaf0f692f812eeeeffcd38122b2bebd052a3df252c0a42243e34de4bacf72ee",
    "ai/research/experiments/R7/metrics.json": "40c17c692b58c364b462431f53a4b0d3e9aaac3ed2e0c0b687fc937756f96447",
    "ai/research/experiments/R7/config.yaml": "cc9227a6a4e824863e054d42d2dcabed518a4ccb49f01b35cd407fe3ea8d36d0",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _d0_tree_hash(root: Path) -> str:
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        relative_path = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative_path + b"\0" + _sha256(path).encode("ascii") + b"\n")
    return digest.hexdigest()


def test_frozen_m113_r3_and_d0_integrity():
    m113 = (
        REPO_ROOT
        / "ai"
        / "computer_vision"
        / "training"
        / "runs"
        / "yolov8n_m1_13"
        / "weights"
        / "best.pt"
    )
    r3 = REPO_ROOT / "ai/research/experiments/R3/CVR2-CV-006/weights/best.pt"
    d0 = REPO_ROOT / "ai/computer_vision/dataset_m1_13"
    assert _sha256(m113) == M113_SHA256
    assert _sha256(r3) == R3_SHA256
    assert sum(path.is_file() for path in d0.rglob("*")) == D0_FILE_COUNT
    assert _d0_tree_hash(d0) == D0_TREE_SHA256


def test_frozen_r5_r6_integrity():
    sources = {
        "ai/research/datasets/R5_controlled_shift/manifest.json": R5_MANIFEST_SHA256,
        "ai/research/experiments/R5/metrics.json": R5_METRICS_SHA256,
        "ai/research/datasets/R6_controlled_sequences/manifest.json": R6_MANIFEST_SHA256,
        "ai/research/experiments/R6/metrics.json": R6_METRICS_SHA256,
    }
    for relative_path, expected_hash in sources.items():
        assert _sha256(REPO_ROOT / relative_path) == expected_hash


def test_r7_frozen_research_records_unchanged():
    for relative_path, expected_hash in R7_FROZEN_HASHES.items():
        assert _sha256(REPO_ROOT / relative_path) == expected_hash


def test_source_records_have_audit_fields_and_no_unverified_source_is_admitted():
    inventory = _load(R8_ROOT / "source_inventory.json")
    assert len(inventory["sources"]) == 8
    required = {
        "source_id",
        "source_name_claimed",
        "source_reference",
        "license_claimed",
        "license_reference",
        "provenance",
        "modality",
        "geographic_scope_claimed",
        "temporal_scope_claimed",
        "limitations",
        "audit_status",
    }
    assert all(required <= source.keys() for source in inventory["sources"])
    assert inventory["admitted_case_sources"] == []
    assert inventory["admitted_case_count"] == 0
    assert all(
        source["audit_status"] != "ADMITTED"
        for source in inventory["sources"]
    )
    assert any(
        source["audit_status"] == "QUARANTINED_NOT_ADMITTED"
        for source in inventory["sources"]
    )


def test_no_fabricated_case_records_and_schema_keeps_missing_fields_optional():
    experiment = _load(R8_ROOT / "experiment.json")
    manifest = _load(R8_ROOT / "dataset_manifest.json")
    schema = _load(R8_ROOT / "case_schema.json")
    assert experiment["case_count"] == 0
    assert experiment["status"] == "CASE_DATASET_NOT_AVAILABLE"
    assert manifest["case_count"] == 0
    assert manifest["records"] == []
    assert "case_id" in schema["required"]
    assert "provenance" in schema["required"]
    assert "citizen_description" not in schema["required"]
    assert "approximate_location" not in schema["required"]
    assert schema["additionalProperties"] is False


def test_privacy_controls_cover_identifiers_and_no_case_data_was_admitted():
    audit = _load(R8_ROOT / "privacy_audit.json")
    policy = audit["policy"]
    assert audit["case_records_reviewed"] == 0
    assert audit["case_records_admitted"] == 0
    for field in (
        "location",
        "faces",
        "license_plates",
        "personal_names",
        "phone_numbers",
        "email_addresses",
        "exact_home_addresses",
        "other_identifiers",
    ):
        assert policy[field]
    assert audit["prior_artifact_claims"]["independently_re_reviewed_in_r8"] is False


def test_independence_audit_preserves_reported_and_recomputed_distinctions():
    audit = _load(R8_ROOT / "independence_audit.json")
    checks = audit["checks"]
    assert checks["d1_internal_exact_duplicates"]["count"] == 0
    assert checks["d1_internal_near_duplicate_pairs"]["count"] == 5
    assert checks["d1_cross_split_exact_duplicates"]["count"] == 0
    assert checks["d1_cross_split_near_duplicates"]["count"] == 0
    assert checks["d1_sequence_group_cross_split"]["sequence_groups"] == 41
    assert checks["d1_sequence_group_cross_split"]["groups_spanning_splits"] == 0
    assert checks["d1_to_d0_exact_image_overlap"]["matching_sha256"] == 0
    assert checks["d1_to_d0_near_image_overlap"]["matching_pairs"] == 0
    assert checks["d1_source_independence"]["status"] == "INCONCLUSIVE"
    assert checks["r5_source_overlap"]["status"] == "KNOWN_DERIVATIVE"
    assert checks["r6_source_overlap"]["status"] == "KNOWN_DERIVATIVE"
    assert audit["overall_independence"] == "NOT_ESTABLISHED_FOR_CIVIC_CASES"


def test_synthetic_r5_r6_are_not_counted_as_real_world_cases():
    manifest = _load(R8_ROOT / "dataset_manifest.json")
    metrics = _load(R8_ROOT / "metrics.json")
    assert manifest["case_count"] == 0
    assert metrics["data_integrity"]["r5_r6_are_independent_real_world_cases"] is False


def test_provenance_source_checksums_and_r8_freeze_manifest():
    provenance = _load(R8_ROOT / "provenance.json")
    for source in provenance["sources"]:
        path = REPO_ROOT / source["path"]
        if path.is_file():
            assert _sha256(path) == source["sha256"]
        elif path.is_dir():
            assert sum(item.is_file() for item in path.rglob("*")) == source["file_count"]
            assert _d0_tree_hash(path) == source["tree_sha256"]
        else:
            raise AssertionError(f"Missing provenance source {source['path']}")

    manifest = _load(R8_ROOT / "freeze_manifest.json")
    assert manifest["freeze_status"] == "FROZEN_RESEARCH_RECORD"
    for relative_path, expected_hash in manifest["files"].items():
        assert _sha256(R8_ROOT / relative_path) == expected_hash
    dataset_manifest = _load(R8_ROOT / "dataset_manifest.json")
    assert _sha256(R8_ROOT / dataset_manifest["source_inventory"]) == dataset_manifest[
        "source_manifest_sha256"
    ]


def test_no_production_integration_or_model_training():
    experiment = _load(R8_ROOT / "experiment.json")
    assert experiment["research_only"] is True
    assert experiment["production_integration"] is False
    assert experiment["model_training"] is False
    assert experiment["final_state"]["NO GIT COMMIT"] is True
    assert experiment["final_state"]["NO GIT PUSH"] is True
