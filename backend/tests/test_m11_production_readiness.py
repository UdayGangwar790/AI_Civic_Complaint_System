"""
CVKI - Civic Vision & Knowledge Intelligence
Module 11.9: Full-System Production Readiness & Failure Injection Suite
"""

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.core.database import is_mongo_healthy, mongo_manager
from app.core.idempotency import compute_payload_fingerprint, get_idempotency_store
from app.core.security import create_access_token
from app.main import app
from app.models.roles import UserRole
from app.schemas.complaint_case import ComplaintCase
from app.schemas.decision_support import DecisionContext
from app.schemas.external_civic import ExternalDataStatus
from app.schemas.field_inspection import (
    FieldInspectionSubmissionRequest,
    InspectionCompleteness,
    InspectionObservationItem,
)
from app.schemas.multimodal_gateway import MultimodalGatewayRequest
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
    calculate_evidence_hash,
)
from app.services.action_playbook import get_action_playbook_registry
from app.services.cv.providers.m113_yolo_provider import M113YOLOProvider
from app.services.decision_projection import get_decision_projector
from app.services.decision_support import get_decision_support_engine
from app.services.external_civic_provider import (
    OpenMeteoWeatherProvider,
    is_ssrf_safe_external_url,
)
from app.services.field_inspection import get_audit_engine, get_protocol_generator
from app.services.government_adapter import AdapterSubmissionResult, IntegrationState
from app.services.knowledge_graph import get_knowledge_graph_service
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.provenance_engine import get_provenance_engine


EXPECTED_M113_SHA = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================================
# 1. AUTH & RBAC READINESS
# ============================================================================

def test_auth_readiness_invalid_credentials_and_expired_tokens(client):
    # Invalid login
    res_bad_login = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "nonexistent@civic.gov.in", "password": "wrongpassword123"},
    )
    assert res_bad_login.status_code in (401, 404, 422, 503)

    # Expired token rejected
    expired_token = create_access_token(
        user_id="usr_expired",
        email="expired@civic.gov.in",
        expires_delta=timedelta(minutes=-60),
        role=UserRole.CITIZEN.value,
    )
    res_expired = client.get(
        f"{settings.API_V1_STR}/admin/metrics",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res_expired.status_code in (401, 403, 503)


def test_auth_readiness_citizen_forbidden_from_admin_endpoints(client):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user_id="usr_citizen",
        email="citizen@civic.gov.in",
        role=UserRole.CITIZEN.value,
    )
    try:
        res = client.get(f"{settings.API_V1_STR}/admin/metrics")
        assert res.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ============================================================================
# 2. CV M1.13 INVARIANT & SAFETY
# ============================================================================

def test_cv_m113_exact_sha_and_provider_contract():
    model_path = settings.get_resolved_model_path()
    assert model_path.exists(), f"Model file not found at {model_path}"
    with open(model_path, "rb") as f:
        file_sha = hashlib.sha256(f.read()).hexdigest()
    assert file_sha.lower() == EXPECTED_M113_SHA.lower(), f"Model SHA changed! Expected {EXPECTED_M113_SHA}, got {file_sha}"

    provider = M113YOLOProvider(verify_sha_on_load=True)
    assert provider.descriptor.model_id == "m1.13-yolov8n"
    assert provider.descriptor.provider_id == "m113_yolo_provider"


def test_cv_upload_size_limit_rejection(client):
    oversized_data = b"X" * (settings.MAX_IMAGE_UPLOAD_BYTES + 1024)
    res = client.post(
        f"{settings.API_V1_STR}/detection/predict",
        files={"file": ("huge.jpg", oversized_data, "image/jpeg")},
    )
    assert res.status_code in (400, 413, 422)


# ============================================================================
# 3. MULTIMODAL READINESS
# ============================================================================

def test_multimodal_gateway_readiness():
    from app.services.multimodal_gateway import get_multimodal_gateway_service
    gateway = get_multimodal_gateway_service()
    req = MultimodalGatewayRequest(
        text="Raste par khula gaddha hai kripya theek karein",
        language_hint="hi",
    )
    res = gateway.process(req)
    assert res.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert res.vernacular_result is not None
    assert res.vernacular_result.detected_language in ("hi", "hinglish")


# ============================================================================
# 4. DECISION SUPPORT & PLAYBOOK READINESS
# ============================================================================

def test_decision_support_evidence_synthesis_and_human_review_required():
    engine = get_decision_support_engine()
    ctx = DecisionContext(
        case_reference="CVKI-M11-TEST-001",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        priority_level="P1",
        citizen_text="Dangerous open manhole on Main Road",
        latitude=12.9716,
        longitude=77.5946,
    )
    res = engine.evaluate_case(ctx)
    assert res.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert res.human_review_required is True
    assert len(res.matched_playbooks) > 0
    assert len(res.recommended_actions) > 0


# ============================================================================
# 5. FIELD INSPECTION READINESS
# ============================================================================

def test_field_inspection_protocol_and_audit():
    generator = get_protocol_generator()
    protocol = generator.generate_protocol(
        case_reference="CVKI-M11-TEST-002",
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        case_location={"latitude": 12.9716, "longitude": 77.5946},
    )
    assert protocol.case_reference == "CVKI-M11-TEST-002"
    assert len(protocol.inspection_steps) > 0

    audit_engine = get_audit_engine()
    sub = FieldInspectionSubmissionRequest(
        protocol_id=protocol.protocol_id,
        inspection_timestamp=datetime.now(timezone.utc),
        observations=[
            InspectionObservationItem(
                step_id="STEP-MANHOLE-01",
                observation_text="Visual boundary inspection completed.",
                defect_confirmed=True,
            )
        ],
        location={"latitude": 12.9716, "longitude": 77.5946},
    )
    record = audit_engine.audit_submission(
        protocol=protocol,
        submission=sub,
        inspector_id="insp_m11_01",
    )
    assert record.epistemic_state == EpistemicState.USER_REPORTED
    assert record.audit_result.epistemic_state == EpistemicState.SYSTEM_DERIVED
    assert record.completeness in (InspectionCompleteness.PARTIAL, InspectionCompleteness.COMPLETE)


# ============================================================================
# 6. PROVENANCE INTEGRITY & TAMPER DETECTION
# ============================================================================

def test_provenance_hash_chain_integrity():
    engine = get_provenance_engine()
    case_ref = f"CVKI-M11-PROV-{uuid4().hex[:6]}"
    r1 = engine.build_evidence_record(
        case_reference=case_ref,
        claim_type=ClaimType.DETECTION,
        source="M1.13 CV",
        source_type=SourceType.CV_MODEL,
        explanation="Initial defect detection",
        verification_state=VerificationState.NOT_VERIFIED,
        claim_value={"class_name": "open_damaged_manhole", "confidence": 0.91},
    )
    assert r1.evidence_hash is not None

    # Cryptographic tamper divergence
    calc_tampered = calculate_evidence_hash(
        claim_type=r1.claim_type.value,
        matched_attribute=r1.matched_attribute,
        source=r1.source,
        source_type=r1.source_type.value,
        value={"class_name": "tampered_defect", "confidence": 0.99},
        explanation=r1.explanation,
    )
    assert r1.evidence_hash != calc_tampered, "Tampered payload must diverge hash digest!"


# ============================================================================
# 7. KNOWLEDGE GRAPH PROJECTION & TRAVERSAL LIMITS
# ============================================================================

def test_knowledge_graph_traversal_limits():
    kg = get_knowledge_graph_service()
    case_ref = f"CVKI-M11-KG-{uuid4().hex[:6]}"
    subgraph = kg.get_case_graph(case_ref, max_depth=2, max_nodes=10, max_edges=10)
    assert len(subgraph.nodes) <= 10
    assert len(subgraph.edges) <= 10


# ============================================================================
# 8. GOVERNMENT INTEGRATION & UNKNOWN OUTCOMES
# ============================================================================

def test_government_submission_failure_cannot_produce_fake_success():
    res = AdapterSubmissionResult(
        state=IntegrationState.TEMPORARY_FAILURE,
        is_unknown_outcome=True,
        error_code="TIMEOUT",
        error_message_safe="Upstream government server timeout",
    )
    assert res.is_unknown_outcome is True
    assert res.state != IntegrationState.SUBMISSION_ACCEPTED
    assert res.external_reference_id is None


# ============================================================================
# 9. FAILURE INJECTION TESTS
# ============================================================================

def test_failure_injection_ssrf_rejections():
    unsafe_targets = [
        "http://localhost/admin",
        "http://127.0.0.1:8000/secret",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "ftp://example.com/file",
        "file:///etc/passwd",
    ]
    for target in unsafe_targets:
        safe, reason = is_ssrf_safe_external_url(target)
        assert safe is False, f"Expected SSRF rejection for {target}, but passed ({reason})"


def test_failure_injection_mongo_failure_readiness_probe():
    import asyncio
    with patch.object(mongo_manager, "client", None):
        with patch.object(mongo_manager, "db", None):
            res = asyncio.run(is_mongo_healthy())
            assert res is False


def test_failure_injection_idempotency_duplicate_request():
    store = get_idempotency_store()
    key = f"idem_fail_test_{uuid4().hex[:8]}"
    fp = compute_payload_fingerprint({"reference_id": "CVKI-001"})

    acquired, _ = store.acquire(key=key, scope="test", fingerprint=fp)
    assert acquired is True

    # Immediate second request while first is in-progress
    acquired2, rec2 = store.acquire(key=key, scope="test", fingerprint=fp)
    assert acquired2 is False
    assert rec2.status == "IN_PROGRESS"
