"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.5: Field Inspection Protocol & Audit Engine Tests
"""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.field_inspection import (
    AuditOutcome,
    ExpectedObservationType,
    FieldInspectionSubmissionRequest,
    GeofenceResult,
    InspectionCompleteness,
    InspectionObservationItem,
)
from app.services.complaint_case import (
    ComplaintCase,
    InMemoryComplaintCaseRepository,
    set_case_repository,
)
import app.services.complaint_case as complaint_case_module
from app.services.field_inspection import (
    InMemoryFieldInspectionRepository,
    get_audit_engine,
    get_field_inspection_repository,
    get_protocol_generator,
)
from app.services.multimodal.contracts import EpistemicState, IssueCategory


CITIZEN_1 = AuthenticatedUser(user_id="user_cit_1", email="cit1@cvki.gov.in", role=UserRole.CITIZEN.value)
CITIZEN_2 = AuthenticatedUser(user_id="user_cit_2", email="cit2@cvki.gov.in", role=UserRole.CITIZEN.value)
AUTHORITY_1 = AuthenticatedUser(user_id="user_auth_1", email="auth1@cvki.gov.in", role=UserRole.AUTHORITY.value)
AUTHORITY_2 = AuthenticatedUser(user_id="user_auth_2", email="auth2@cvki.gov.in", role=UserRole.AUTHORITY.value)
ADMIN_1 = AuthenticatedUser(user_id="user_admin_1", email="admin@cvki.gov.in", role=UserRole.ADMIN.value)


@pytest.fixture(autouse=True)
def setup_inspection_env():
    orig_repo = complaint_case_module.case_repository
    mem_repo = InMemoryComplaintCaseRepository()
    set_case_repository(mem_repo)

    insp_repo = get_field_inspection_repository()
    insp_repo.clear()

    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    yield mem_repo
    app.dependency_overrides.clear()
    set_case_repository(orig_repo)


def _make_case(reference_id="CASE-INSP-001", user_id="user_cit_1", assigned_to="user_auth_1", class_name="open_damaged_manhole"):
    return ComplaintCase(
        reference_id=reference_id,
        user_id=user_id,
        status="submitted_to_cvki",
        created_at=datetime.now(timezone.utc),
        issue={
            "class_id": 0,
            "class_name": class_name,
            "label": "Open Manhole",
            "severity": "high",
            "confidence": 0.88,
        },
        location={"latitude": 12.9716, "longitude": 77.5946, "city": "Bengaluru"},
        authority={
            "authority_status": "verified",
            "maintenance_authority": {"name": "BBMP Road Maintenance", "type": "Municipal"},
        },
        complaint={"title": "Hazardous road issue", "description": "Large dangerous opening", "language": "en"},
        follow_up={"guidance": "Saved in CVKI."},
        assignment={"assigned_to_user_id": assigned_to} if assigned_to else None,
    )


# --- 20 Required Tests ---

def test_01_protocol_generation():
    """Verify inspection protocol generates deterministically for a complaint case."""
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(
        case_reference="CASE-001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        case_location={"latitude": 12.9716, "longitude": 77.5946},
    )
    assert protocol.protocol_id == "PROTOCOL-MANHOLE-V1"
    assert protocol.case_reference == "CASE-001"
    assert len(protocol.inspection_steps) > 0
    assert len(protocol.prohibited_inferences) > 0


def test_02_manhole_protocol():
    """Verify open damaged manhole protocol contents and safety overrides."""
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(
        case_reference="CASE-MH-01",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
    )
    step_ids = [s.step_id for s in protocol.inspection_steps]
    assert "STEP-MANHOLE-01" in step_ids
    assert "STEP-MANHOLE-02" in step_ids
    assert "STEP-MANHOLE-04" in step_ids

    # Safety override check
    dim_step = next(s for s in protocol.inspection_steps if s.step_id == "STEP-MANHOLE-03")
    assert dim_step.mandatory is False
    assert "SAFETY OVERRIDE" in dim_step.safety_guidance
    assert any("confined space" in s.lower() for s in protocol.safety_notes)


def test_03_road_sign_protocol():
    """Verify road sign protocol includes approaching sightline and stability checks."""
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(
        case_reference="CASE-RS-01",
        issue_category=IssueCategory.DAMAGED_MISSING_ROAD_SIGN,
    )
    assert protocol.protocol_id == "PROTOCOL-ROAD-SIGN-V1"
    assert any("sightline" in s.instruction.lower() or "50m" in s.instruction for s in protocol.inspection_steps)
    assert any("pole vertical deflection" in s.instruction.lower() for s in protocol.inspection_steps)


def test_04_waterlogging_protocol():
    """Verify waterlogging protocol includes catch basin inflow check and contextual weather caveat."""
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(
        case_reference="CASE-WL-01",
        issue_category=IssueCategory.ROAD_WATERLOGGING,
    )
    assert protocol.protocol_id == "PROTOCOL-WATERLOGGING-V1"
    assert any("50m" in s.instruction.lower() for s in protocol.inspection_steps)
    assert any("contextual" in inf.lower() for inf in protocol.prohibited_inferences)


def test_05_generic_protocol():
    """Verify generic protocol fallback includes baseline walkthrough verification."""
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(
        case_reference="CASE-GEN-01",
        issue_category=IssueCategory.OTHER_CIVIC_ISSUE,
    )
    assert protocol.protocol_id == "PROTOCOL-GENERIC-CIVIC-V1"
    assert len(protocol.inspection_steps) == 3


def test_06_authenticated_submission(setup_inspection_env):
    """Verify authorized inspector can submit inspection and receive 201 Created."""
    case = _make_case(reference_id="CASE-SUBMIT-001", user_id="user_cit_1", assigned_to="user_auth_1")
    setup_inspection_env.save(case)

    client = TestClient(app)
    req_body = {
        "protocol_id": "PROTOCOL-MANHOLE-V1",
        "protocol_version": "1.0.0",
        "observations": [
            {
                "step_id": "STEP-MANHOLE-01",
                "observation_text": "Captured wide-angle photos from north and south approach lanes.",
                "defect_confirmed": True,
            },
            {
                "step_id": "STEP-MANHOLE-02",
                "observation_text": "Rim casting fractured on west edge, lid missing completely.",
                "defect_confirmed": True,
            },
            {
                "step_id": "STEP-MANHOLE-04",
                "observation_text": "Reflective traffic cone placed over open aperture.",
                "defect_confirmed": True,
                "safety_measures_taken": "Deployed temporary cone",
            },
        ],
        "evidence_items": ["ev_photo_01.jpg", "ev_photo_02.jpg"],
        "location": {"latitude": 12.9716, "longitude": 77.5946},
        "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        "notes": "Verified hazard on site",
    }
    resp = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-SUBMIT-001/submit",
        json=req_body,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["inspection_id"].startswith("INSP-")
    assert data["case_reference"] == "CASE-SUBMIT-001"
    assert data["inspector_id"] == "user_auth_1"
    assert data["audit_result"]["outcome"] == AuditOutcome.SUPPORTED.value


def test_07_rbac_citizen_forbidden(setup_inspection_env):
    """Verify citizen role cannot submit an official field inspection."""
    case = _make_case(reference_id="CASE-CIT-FORBIDDEN", user_id="user_cit_1", assigned_to="user_auth_1")
    setup_inspection_env.save(case)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-CIT-FORBIDDEN/submit",
        json={
            "protocol_id": "PROTOCOL-MANHOLE-V1",
            "protocol_version": "1.0.0",
            "observations": [{"step_id": "STEP-MANHOLE-01", "observation_text": "Citizen trying to submit"}],
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_08_authority_assignment(setup_inspection_env):
    """Verify authority cannot submit inspection for a case assigned to someone else."""
    case = _make_case(reference_id="CASE-AUTH-WRONG", user_id="user_cit_1", assigned_to="user_auth_2")
    setup_inspection_env.save(case)

    # user_auth_1 attempts to inspect case assigned to user_auth_2
    app.dependency_overrides[get_current_user] = lambda: AUTHORITY_1
    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-AUTH-WRONG/submit",
        json={
            "protocol_id": "PROTOCOL-MANHOLE-V1",
            "protocol_version": "1.0.0",
            "observations": [{"step_id": "STEP-MANHOLE-01", "observation_text": "Unauthorized authority"}],
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_09_citizen_read_sanitized_protocol(setup_inspection_env):
    """Verify citizen can view protocol for their own case, but not someone else's case."""
    case1 = _make_case(reference_id="CASE-CIT-OWN", user_id="user_cit_1")
    case2 = _make_case(reference_id="CASE-CIT-OTHER", user_id="user_cit_2")
    setup_inspection_env.save(case1)
    setup_inspection_env.save(case2)

    app.dependency_overrides[get_current_user] = lambda: CITIZEN_1
    client = TestClient(app)

    # Own case: allowed
    resp1 = client.get(f"{settings.API_V1_STR}/inspection/cases/CASE-CIT-OWN/protocol")
    assert resp1.status_code == status.HTTP_200_OK

    # Other's case: forbidden
    resp2 = client.get(f"{settings.API_V1_STR}/inspection/cases/CASE-CIT-OTHER/protocol")
    assert resp2.status_code == status.HTTP_403_FORBIDDEN


def test_10_location_validation_within_area():
    """Verify inspection coordinates within 150m return WITHIN_EXPECTED_AREA."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(
        case_reference="CASE-LOC-01",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        case_location={"latitude": 12.9716, "longitude": 77.5946},
    )
    # 20 meters away
    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[
            InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Photos taken", defect_confirmed=True)
        ],
        location={"latitude": 12.9717, "longitude": 77.5947},
        inspection_timestamp=datetime.now(timezone.utc),
    )
    rec = engine.audit_submission(protocol, sub, inspector_id="user_auth_1")
    assert rec.geofence_result == GeofenceResult.WITHIN_EXPECTED_AREA
    assert rec.audit_result.distance_from_case_meters is not None
    assert rec.audit_result.distance_from_case_meters < 50.0


def test_11_geofence_outside_area():
    """Verify inspection coordinates > 150m return OUTSIDE_EXPECTED_AREA."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(
        case_reference="CASE-LOC-02",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        case_location={"latitude": 12.9716, "longitude": 77.5946},
    )
    # ~500 meters away
    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[
            InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Observed from afar", defect_confirmed=True)
        ],
        location={"latitude": 12.9760, "longitude": 77.5946},
        inspection_timestamp=datetime.now(timezone.utc),
    )
    rec = engine.audit_submission(protocol, sub, inspector_id="user_auth_1")
    assert rec.geofence_result == GeofenceResult.OUTSIDE_EXPECTED_AREA
    assert rec.audit_result.distance_from_case_meters > 150.0


def test_12_future_timestamp_rejection():
    """Verify submission with timestamp in the future is rejected with ValueError."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(case_reference="CASE-TIME-01", issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)

    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Future inspection")],
        inspection_timestamp=future_time,
    )
    with pytest.raises(ValueError) as excinfo:
        engine.audit_submission(protocol, sub, inspector_id="user_auth_1")
    assert "future" in str(excinfo.value).lower()


def test_13_incomplete_inspection():
    """Verify missing mandatory steps return InspectionCompleteness.PARTIAL."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(case_reference="CASE-INC-01", issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)

    # Submit only 1 out of 3 mandatory steps
    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[
            InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Only step 1 done", defect_confirmed=True)
        ],
        inspection_timestamp=datetime.now(timezone.utc),
    )
    rec = engine.audit_submission(protocol, sub, inspector_id="user_auth_1")
    assert rec.completeness == InspectionCompleteness.PARTIAL
    assert len(rec.audit_result.missing_mandatory_steps) == 2


def test_14_conflicting_evidence():
    """Verify internal observation contradiction flags CONFLICTING audit outcome."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(case_reference="CASE-CONF-01", issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)

    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[
            InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Aperture wide open", defect_confirmed=True),
            InspectionObservationItem(step_id="STEP-MANHOLE-02", observation_text="No defect seen at all", defect_confirmed=False),
        ],
        inspection_timestamp=datetime.now(timezone.utc),
    )
    rec = engine.audit_submission(protocol, sub, inspector_id="user_auth_1")
    assert rec.audit_result.outcome == AuditOutcome.CONFLICTING
    assert any("contradiction" in c.lower() for c in rec.conflicts)


def test_15_complete_supported_inspection():
    """Verify complete inspection with confirmed defect returns AuditOutcome.SUPPORTED."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(
        case_reference="CASE-SUPP-01",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        case_location={"latitude": 12.9716, "longitude": 77.5946},
    )
    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[
            InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Overview taken", defect_confirmed=True),
            InspectionObservationItem(step_id="STEP-MANHOLE-02", observation_text="Frame broken", defect_confirmed=True),
            InspectionObservationItem(step_id="STEP-MANHOLE-04", observation_text="Barricade verified", defect_confirmed=True),
        ],
        location={"latitude": 12.9716, "longitude": 77.5946},
        inspection_timestamp=datetime.now(timezone.utc),
    )
    rec = engine.audit_submission(protocol, sub, inspector_id="user_auth_1")
    assert rec.completeness == InspectionCompleteness.COMPLETE
    assert rec.audit_result.outcome == AuditOutcome.SUPPORTED


def test_16_audit_result_structure():
    """Verify audit result contains all required fields and SYSTEM_DERIVED epistemic state."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(case_reference="CASE-STRUCT-01", issue_category=IssueCategory.ROAD_WATERLOGGING)

    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[
            InspectionObservationItem(step_id="STEP-WATER-01", observation_text="Ponding verified", defect_confirmed=True)
        ],
        inspection_timestamp=datetime.now(timezone.utc),
    )
    rec = engine.audit_submission(protocol, sub, inspector_id="user_auth_1")
    audit = rec.audit_result
    assert audit.audit_id is not None
    assert audit.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert "Field inspection audit completed" in audit.audit_explanation


def test_17_inspector_identity_from_auth_context(setup_inspection_env):
    """Verify inspector identity is taken strictly from auth user and cannot be spoofed."""
    case = _make_case(reference_id="CASE-SPOOF-01", assigned_to="user_auth_1")
    setup_inspection_env.save(case)

    client = TestClient(app)
    resp = client.post(
        f"{settings.API_V1_STR}/inspection/cases/CASE-SPOOF-01/submit",
        json={
            "protocol_id": "PROTOCOL-MANHOLE-V1",
            "protocol_version": "1.0.0",
            "inspector_id": "spoofed_super_admin",  # Ignored
            "observations": [
                {"step_id": "STEP-MANHOLE-01", "observation_text": "Overview recorded", "defect_confirmed": True}
            ],
            "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["inspector_id"] == "user_auth_1"


def test_18_epistemic_state_preservation():
    """Verify inspection record epistemic state is USER_REPORTED."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(case_reference="CASE-EPI-01", issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)

    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Notes")],
        inspection_timestamp=datetime.now(timezone.utc),
    )
    rec = engine.audit_submission(protocol, sub, inspector_id="user_auth_1")
    assert rec.epistemic_state == EpistemicState.USER_REPORTED
    assert rec.audit_result.epistemic_state == EpistemicState.SYSTEM_DERIVED


def test_19_before_after_integration():
    """Verify M9.5 visual audit outcome integration corroborates or flags conflicts."""
    engine = get_audit_engine()
    gen = get_protocol_generator()
    protocol = gen.generate_protocol(case_reference="CASE-M95-01", issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)

    # Inspector denies defect while M9.5 observed DEFECT_PERSISTS -> Conflict
    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        observations=[
            InspectionObservationItem(step_id="STEP-MANHOLE-01", observation_text="Nothing here", defect_confirmed=False)
        ],
        inspection_timestamp=datetime.now(timezone.utc),
    )
    rec = engine.audit_submission(protocol, sub, inspector_id="user_auth_1", visual_audit_outcome="DEFECT_PERSISTS")
    assert any("cross-evidence conflict" in c.lower() for c in rec.conflicts)


def test_20_duplicate_submission_and_retrieval(setup_inspection_env):
    """Verify multiple inspections for same case are stored distinctly and retrievable by ID."""
    case = _make_case(reference_id="CASE-DUP-001", assigned_to="user_auth_1")
    setup_inspection_env.save(case)

    client = TestClient(app)
    req_body = {
        "protocol_id": "PROTOCOL-MANHOLE-V1",
        "protocol_version": "1.0.0",
        "observations": [
            {"step_id": "STEP-MANHOLE-01", "observation_text": "First inspection", "defect_confirmed": True}
        ],
        "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    resp1 = client.post(f"{settings.API_V1_STR}/inspection/cases/CASE-DUP-001/submit", json=req_body)
    assert resp1.status_code == status.HTTP_201_CREATED
    id1 = resp1.json()["inspection_id"]

    req_body["observations"][0]["observation_text"] = "Second inspection follow-up"
    resp2 = client.post(f"{settings.API_V1_STR}/inspection/cases/CASE-DUP-001/submit", json=req_body)
    assert resp2.status_code == status.HTTP_201_CREATED
    id2 = resp2.json()["inspection_id"]

    assert id1 != id2

    # Fetch both individually
    fetch1 = client.get(f"{settings.API_V1_STR}/inspection/{id1}")
    assert fetch1.status_code == status.HTTP_200_OK
    assert fetch1.json()["observations"][0]["observation_text"] == "First inspection"

    fetch2 = client.get(f"{settings.API_V1_STR}/inspection/{id2}")
    assert fetch2.status_code == status.HTTP_200_OK
    assert fetch2.json()["observations"][0]["observation_text"] == "Second inspection follow-up"
