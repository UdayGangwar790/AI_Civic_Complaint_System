import asyncio
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.main import app
from app.models.roles import UserRole
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseAssignment,
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    FollowUp,
)
from app.schemas.provenance import (
    ClaimType,
    EvidenceRecord,
    SourceType,
    VerificationState,
    calculate_evidence_hash,
)
from app.services.authority import resolve_authority_for_location
import app.services.complaint_case as complaint_case_module
from app.services.external_civic_data import external_civic_service
from app.services.geospatial_intelligence import get_geospatial_intelligence_context
from app.services.authority import AuthorityLookup, resolve_authority
from app.services.civic_intelligence import get_case_intelligence
from app.services.provenance_engine import (
    EvidenceProvenanceEngine,
    InMemoryProvenanceRepository,
    get_provenance_engine,
    set_provenance_engine,
)


def _build_test_case(
    ref_id: str,
    user_id: str = "usr_citizen_123",
    lat: float = 12.9716,
    lon: float = 77.5946,
    issue_class: str = "pothole",
    road: str = "MG Road",
    assigned_to: str | None = None,
    created_at: datetime | None = None,
    builder: str | None = None,
) -> ComplaintCase:
    now = created_at or datetime.now(timezone.utc)
    complaint_loc = ComplaintLocation(
        road=road,
        area="Central Area",
        city="Bengaluru",
        district="Bengaluru Urban",
        state="Karnataka",
        latitude=lat,
        longitude=lon,
    )
    auth = resolve_authority_for_location(complaint_loc)
    if auth:
        from app.schemas.authority import AuthorityParty
        if not auth.maintenance_authority:
            auth.maintenance_authority = AuthorityParty(
                name="Bruhat Bengaluru Mahanagara Palike (BBMP)",
                type="municipal_corporation",
                source="BBMP Official Road Register",
                official_portal_url="https://bbmp.gov.in/roads",
            )
        if not auth.road_owner:
            auth.road_owner = AuthorityParty(
                name="Government of Karnataka",
                type="state_government",
                source="Karnataka State Gazette",
                official_portal_url="https://karnataka.gov.in",
            )
        auth.authority_status = "verified"
    if builder and auth:
        auth.builder_or_contractor = builder
    assignment = None
    if assigned_to:
        assignment = CaseAssignment(
            assigned_to_user_id=assigned_to,
            assigned_at=now,
            assigned_by_user_id="usr_admin",
            assignment_status="assigned",
        )
    return ComplaintCase(
        reference_id=ref_id,
        user_id=user_id,
        status="submitted_to_cvki",
        created_at=now,
        issue=CaseIssue(
            class_name=issue_class,
            label=issue_class.replace("_", " ").title(),
            severity="medium",
            confidence=0.88,
        ),
        location=complaint_loc,
        authority=auth,
        assignment=assignment,
        complaint=CaseComplaint(
            language="en",
            title=f"Civic Issue {ref_id}",
            description="Detected road defect needing repair.",
        ),
        follow_up=FollowUp(guidance="Saved in CVKI."),
    )


class TestEvidenceProvenanceEngineM64(unittest.TestCase):
    def setUp(self):
        self.original_overrides = dict(app.dependency_overrides)
        self.client = TestClient(app)
        self.in_memory_prov_repo = InMemoryProvenanceRepository()
        self.engine = EvidenceProvenanceEngine(repository=self.in_memory_prov_repo)
        
        # Set up engine and in-memory case repository
        set_provenance_engine(self.engine)
        self.original_case_repo = complaint_case_module.case_repository
        self.case_repo = complaint_case_module.InMemoryComplaintCaseRepository()
        complaint_case_module.set_case_repository(self.case_repo)

    def tearDown(self):
        complaint_case_module.set_case_repository(self.original_case_repo)
        app.dependency_overrides = self.original_overrides

    # -------------------------------------------------------------------------
    # A. Provenance Schema
    # -------------------------------------------------------------------------
    def test_a_provenance_schema(self):
        rec = EvidenceRecord(
            evidence_id="ev_test_123",
            claim_type=ClaimType.DETECTION,
            matched_attribute="pothole",
            source="CV YOLOv8n",
            source_type=SourceType.CV_MODEL,
            retrieved_at=datetime.now(timezone.utc),
            verification_state=VerificationState.VERIFIED,
            explanation="Computer vision model detected pothole with 88% confidence.",
            evidence_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        )
        self.assertEqual(rec.evidence_id, "ev_test_123")
        self.assertEqual(rec.claim_type, ClaimType.DETECTION)
        self.assertEqual(rec.freshness, "fresh")
        self.assertEqual(rec.status, "active")
        self.assertEqual(rec.version, 1)
        self.assertIsNone(rec.source_url)

    # -------------------------------------------------------------------------
    # B. Evidence Creation
    # -------------------------------------------------------------------------
    def test_b_evidence_creation(self):
        rec = self.engine.build_evidence_record(
            claim_type=ClaimType.ROAD_IDENTITY,
            matched_attribute="road_name",
            source="Bengaluru Open Data Road Registry",
            source_type=SourceType.ROAD_REGISTRY,
            explanation="Identified road corridor as MG Road.",
            verification_state=VerificationState.VERIFIED,
            source_url="https://bbmp.gov.in/roads",
        )
        self.assertTrue(rec.evidence_id.startswith("ev_"))
        self.assertEqual(rec.claim_type, ClaimType.ROAD_IDENTITY)
        self.assertEqual(rec.source_type, SourceType.ROAD_REGISTRY)
        self.assertEqual(rec.verification_state, VerificationState.VERIFIED)
        self.assertTrue(len(rec.evidence_hash) == 64)

    # -------------------------------------------------------------------------
    # C. Evidence Fingerprint (Deterministic Hashing)
    # -------------------------------------------------------------------------
    def test_c_evidence_fingerprint(self):
        h1 = calculate_evidence_hash(
            claim_type="detection",
            matched_attribute="pothole",
            source="CV YOLOv8n",
            source_type="cv_model",
            explanation="Detection match",
        )
        h2 = calculate_evidence_hash(
            claim_type="detection",
            matched_attribute="pothole",
            source="CV YOLOv8n",
            source_type="cv_model",
            explanation="Detection match",
        )
        h3 = calculate_evidence_hash(
            claim_type="detection",
            matched_attribute="pothole",
            source="CV YOLOv8n",
            source_type="cv_model",
            explanation="Different explanation",
        )
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertEqual(len(h1), 64)

    # -------------------------------------------------------------------------
    # D. Source Type Validation
    # -------------------------------------------------------------------------
    def test_d_source_type_validation(self):
        expected_sources = [
            "cv_model", "gps", "geocoder", "road_registry", "government_registry",
            "tender_registry", "concession_registry", "weather_provider",
            "traffic_provider", "open_data", "cvki_case_history", "citizen_report",
            "authority_update", "admin_update", "system_derived"
        ]
        for s in expected_sources:
            st = SourceType(s)
            self.assertEqual(st.value, s)

        with self.assertRaises(ValueError):
            SourceType("arbitrary_unvalidated_source")

    # -------------------------------------------------------------------------
    # E. Claim Type Validation
    # -------------------------------------------------------------------------
    def test_e_claim_type_validation(self):
        expected_claims = [
            "detection", "location", "road_identity", "jurisdiction",
            "road_owner", "maintenance_authority", "builder_or_contractor",
            "weather_context", "rainfall_context", "traffic_context",
            "recurrence", "hotspot_context", "priority",
            "complaint_submission_readiness", "resolution_evidence"
        ]
        for c in expected_claims:
            ct = ClaimType(c)
            self.assertEqual(ct.value, c)

        with self.assertRaises(ValueError):
            ClaimType("unsupported_claim_type")

    # -------------------------------------------------------------------------
    # F. Verification State Validation
    # -------------------------------------------------------------------------
    def test_f_verification_state_validation(self):
        expected_states = [
            "verified", "partially_verified", "not_verified",
            "stale", "unavailable", "system_derived"
        ]
        for s in expected_states:
            vs = VerificationState(s)
            self.assertEqual(vs.value, s)

        with self.assertRaises(ValueError):
            VerificationState("fully_trusted")

    # -------------------------------------------------------------------------
    # G. Client Verification Override Rejection
    # -------------------------------------------------------------------------
    def test_g_client_verification_override_rejection(self):
        case = _build_test_case("CVKI-20261014-GOV")
        self.case_repo.save(case)

        # Build chain: server resolves states, ignoring any client claims
        resp = self.engine.generate_case_provenance_chain(case)
        for claim in resp.claims:
            self.assertIn(claim.verification_state, list(VerificationState))
            # Cannot be overridden by client
            self.assertNotEqual(claim.verification_state, "client_verified")

    # -------------------------------------------------------------------------
    # H. Authority Evidence Provenance
    # -------------------------------------------------------------------------
    def test_h_authority_evidence_provenance(self):
        case = _build_test_case("CVKI-20261014-AUTH")
        resp = self.engine.generate_case_provenance_chain(case)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.MAINTENANCE_AUTHORITY, claims)
        auth_claim = claims[ClaimType.MAINTENANCE_AUTHORITY]
        self.assertEqual(auth_claim.source_type, SourceType.GOVERNMENT_REGISTRY)
        self.assertIn(auth_claim.verification_state, [VerificationState.VERIFIED, VerificationState.PARTIALLY_VERIFIED])

    # -------------------------------------------------------------------------
    # I. Builder Evidence Safety (Strict Rule)
    # -------------------------------------------------------------------------
    def test_i_builder_evidence_safety(self):
        # Case with builder but NO explicit tender/concession registry source
        rec_inferred = self.engine.build_evidence_record(
            claim_type=ClaimType.BUILDER_OR_CONTRACTOR,
            matched_attribute="builder_or_contractor",
            source="Local Municipal Directory",
            source_type=SourceType.GOVERNMENT_REGISTRY,
            explanation="Contractor XYZ Corp inferred from road authority.",
            verification_state=VerificationState.VERIFIED,  # Should be downgraded
        )
        self.assertEqual(rec_inferred.verification_state, VerificationState.NOT_VERIFIED)
        self.assertIn("Safety Rule", rec_inferred.explanation)

        # Case with explicit tender registry source
        rec_explicit = self.engine.build_evidence_record(
            claim_type=ClaimType.BUILDER_OR_CONTRACTOR,
            matched_attribute="builder_or_contractor",
            source="State Highway Tender Portal",
            source_type=SourceType.TENDER_REGISTRY,
            explanation="Contractor awarded per Contract #9981.",
            verification_state=VerificationState.VERIFIED,
        )
        self.assertEqual(rec_explicit.verification_state, VerificationState.VERIFIED)

    # -------------------------------------------------------------------------
    # J. Geospatial Provenance
    # -------------------------------------------------------------------------
    def test_j_geospatial_provenance(self):
        case = _build_test_case("CVKI-20261014-GEO")
        resp = self.engine.generate_case_provenance_chain(case)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.LOCATION, claims)
        loc_claim = claims[ClaimType.LOCATION]
        self.assertEqual(loc_claim.source_type, SourceType.GPS)
        self.assertIn("12.9716", loc_claim.explanation)

    # -------------------------------------------------------------------------
    # K. Match Quality Provenance
    # -------------------------------------------------------------------------
    def test_k_match_quality_provenance(self):
        case = _build_test_case("CVKI-20261014-MQ")
        resp = self.engine.generate_case_provenance_chain(case)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.ROAD_IDENTITY, claims)
        road_claim = claims[ClaimType.ROAD_IDENTITY]
        self.assertIn("match_quality", road_claim.metadata)
        self.assertIn(road_claim.metadata["match_quality"], ["EXACT", "STRONG", "APPROXIMATE", "UNAVAILABLE"])

    # -------------------------------------------------------------------------
    # L. Weather Provenance
    # -------------------------------------------------------------------------
    def test_l_weather_provenance(self):
        ext_ctx = {
            "weather": {
                "temperature_c": 26.5,
                "condition": "Partly Cloudy",
                "source": "Open-Meteo API",
                "status": "live",
            }
        }
        case = _build_test_case("CVKI-20261014-WEA")
        resp = self.engine.generate_case_provenance_chain(case, external_context=ext_ctx)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.WEATHER_CONTEXT, claims)
        wea_claim = claims[ClaimType.WEATHER_CONTEXT]
        self.assertEqual(wea_claim.source_type, SourceType.WEATHER_PROVIDER)
        self.assertEqual(wea_claim.freshness, "live")
        self.assertIn("26.5", wea_claim.explanation)

    # -------------------------------------------------------------------------
    # M. Rainfall Provenance
    # -------------------------------------------------------------------------
    def test_m_rainfall_provenance(self):
        ext_ctx = {
            "rainfall": {
                "window_rainfall_mm": 18.2,
                "rainfall_intensity": "moderate",
                "source": "Open-Meteo Historical",
                "status": "cached_fresh",
            }
        }
        case = _build_test_case("CVKI-20261014-RAIN")
        resp = self.engine.generate_case_provenance_chain(case, external_context=ext_ctx)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.RAINFALL_CONTEXT, claims)
        rain_claim = claims[ClaimType.RAINFALL_CONTEXT]
        self.assertEqual(rain_claim.source_type, SourceType.WEATHER_PROVIDER)
        self.assertEqual(rain_claim.freshness, "cached_fresh")
        self.assertIn("18.2 mm", rain_claim.explanation)

    # -------------------------------------------------------------------------
    # N. Non-Causal Wording Invariant
    # -------------------------------------------------------------------------
    def test_n_non_causal_wording(self):
        # Attempt to create rainfall record with causal language
        rec = self.engine.build_evidence_record(
            claim_type=ClaimType.RAINFALL_CONTEXT,
            matched_attribute="rainfall_context",
            source="Open-Meteo",
            source_type=SourceType.WEATHER_PROVIDER,
            explanation="Rainfall caused severe waterlogging and is responsible for pothole expansion.",
            verification_state=VerificationState.VERIFIED,
        )
        explanation_lower = rec.explanation.lower()
        self.assertNotIn("caused", explanation_lower)
        self.assertNotIn("responsible for", explanation_lower)
        self.assertIn("consistent with recent rainfall", explanation_lower)

    # -------------------------------------------------------------------------
    # O. Recurrence Provenance
    # -------------------------------------------------------------------------
    def test_o_recurrence_provenance(self):
        case = _build_test_case("CVKI-20261014-REC")
        intel_mock = MagicMock()
        intel_mock.recurrence.recurrence_detected = True
        intel_mock.recurrence.recurrence_count = 3
        intel_mock.recurrence.recurrence_window_days = 180
        intel_mock.recurrence.spatial_threshold_meters = 250.0
        intel_mock.recurrence.related_historical_case_ids = ["CVKI-001", "CVKI-002"]
        intel_mock.hotspot_detected = False
        intel_mock.priority_score = 65
        intel_mock.resolution_evidence_state = None

        resp = self.engine.generate_case_provenance_chain(case, intelligence=intel_mock)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.RECURRENCE, claims)
        rec_claim = claims[ClaimType.RECURRENCE]
        self.assertEqual(rec_claim.source_type, SourceType.CVKI_CASE_HISTORY)
        self.assertEqual(rec_claim.verification_state, VerificationState.SYSTEM_DERIVED)
        self.assertEqual(rec_claim.metadata["related_case_count"], 3)
        self.assertIn("CVKI-derived intelligence", rec_claim.explanation)

    # -------------------------------------------------------------------------
    # P. Hotspot Provenance
    # -------------------------------------------------------------------------
    def test_p_hotspot_provenance(self):
        case = _build_test_case("CVKI-20261014-HOT")
        intel_mock = MagicMock()
        intel_mock.recurrence.recurrence_detected = False
        intel_mock.hotspot_detected = True
        intel_mock.hotspot_window_days = 90
        intel_mock.recent_location_case_count = 7
        intel_mock.recent_location_unresolved_count = 5
        intel_mock.priority_score = 70
        intel_mock.resolution_evidence_state = None

        resp = self.engine.generate_case_provenance_chain(case, intelligence=intel_mock)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.HOTSPOT_CONTEXT, claims)
        hot_claim = claims[ClaimType.HOTSPOT_CONTEXT]
        self.assertEqual(hot_claim.source_type, SourceType.CVKI_CASE_HISTORY)
        self.assertEqual(hot_claim.verification_state, VerificationState.SYSTEM_DERIVED)
        self.assertEqual(hot_claim.metadata["unresolved_count"], 5)

    # -------------------------------------------------------------------------
    # Q. Priority Provenance
    # -------------------------------------------------------------------------
    def test_q_priority_provenance(self):
        case = _build_test_case("CVKI-20261014-PRIO")
        case.priority_analysis = MagicMock()
        case.priority_analysis.priority_score = 78
        case.priority_analysis.priority_level = "High"
        case.priority_analysis.risk_level = "Elevated"
        case.priority_analysis.reasons = ["Heavy traffic corridor", "Pothole depth > 5cm"]

        resp = self.engine.generate_case_provenance_chain(case)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.PRIORITY, claims)
        prio_claim = claims[ClaimType.PRIORITY]
        self.assertEqual(prio_claim.verification_state, VerificationState.SYSTEM_DERIVED)
        self.assertEqual(prio_claim.metadata["priority_score"], 78)
        self.assertIn("Heavy traffic corridor", prio_claim.explanation)

    # -------------------------------------------------------------------------
    # R. Resolution Evidence Provenance
    # -------------------------------------------------------------------------
    def test_r_resolution_evidence_provenance(self):
        case = _build_test_case("CVKI-20261014-RES")
        intel_mock = MagicMock()
        intel_mock.recurrence.recurrence_detected = False
        intel_mock.hotspot_detected = False
        intel_mock.resolution_evidence_state = "evidence_supported"
        intel_mock.resolution_evidence_explanation = "Repair verified with contractor work receipt."

        resp = self.engine.generate_case_provenance_chain(case, intelligence=intel_mock)
        claims = {c.claim_type: c for c in resp.claims}
        
        self.assertIn(ClaimType.RESOLUTION_EVIDENCE, claims)
        res_claim = claims[ClaimType.RESOLUTION_EVIDENCE]
        self.assertEqual(res_claim.verification_state, VerificationState.VERIFIED)
        self.assertIn("Repair verified", res_claim.explanation)

    # -------------------------------------------------------------------------
    # S. Evidence Staleness
    # -------------------------------------------------------------------------
    def test_s_evidence_staleness(self):
        now = datetime.now(timezone.utc)
        past_time = now - timedelta(hours=48)
        rec = self.engine.build_evidence_record(
            claim_type=ClaimType.WEATHER_CONTEXT,
            matched_attribute="weather",
            source="Open-Meteo",
            source_type=SourceType.WEATHER_PROVIDER,
            explanation="Old weather reading",
            verification_state=VerificationState.STALE,
            freshness="cached_stale",
            observed_at=past_time,
            retrieved_at=now,
        )
        self.assertEqual(rec.verification_state, VerificationState.STALE)
        self.assertEqual(rec.freshness, "cached_stale")
        self.assertEqual(rec.observed_at, past_time)
        self.assertEqual(rec.retrieved_at, now)

    # -------------------------------------------------------------------------
    # T. Evidence Invalidation
    # -------------------------------------------------------------------------
    def test_t_evidence_invalidation(self):
        rec = self.engine.build_evidence_record(
            claim_type=ClaimType.JURISDICTION,
            matched_attribute="ward_boundary",
            source="City GIS Portal",
            source_type=SourceType.GOVERNMENT_REGISTRY,
            explanation="Ward 112 assigned.",
            verification_state=VerificationState.VERIFIED,
            case_reference="CVKI-20261014-INV",
        )
        self.in_memory_prov_repo.save_record(rec)

        with patch("app.services.audit.AuditService.record_event", new_callable=AsyncMock) as mock_audit:
            invalidated = self.engine.invalidate_evidence(
                evidence_id=rec.evidence_id,
                reason="Boundary redrawn under new municipal notification.",
                actor_user_id="usr_admin",
            )
            self.assertIsNotNone(invalidated)
            self.assertEqual(invalidated.status, "invalidated")
            self.assertEqual(invalidated.verification_state, VerificationState.NOT_VERIFIED)
            self.assertEqual(invalidated.metadata["invalidation_reason"], "Boundary redrawn under new municipal notification.")
            self.assertEqual(mock_audit.call_count, 1)

    # -------------------------------------------------------------------------
    # U. Evidence Versioning / History
    # -------------------------------------------------------------------------
    def test_u_evidence_versioning_history(self):
        rec_v1 = self.engine.build_evidence_record(
            claim_type=ClaimType.MAINTENANCE_AUTHORITY,
            matched_attribute="maintenance_authority",
            source="BBMP Portal v1",
            source_type=SourceType.GOVERNMENT_REGISTRY,
            explanation="Assigned to BBMP Major Roads.",
            verification_state=VerificationState.VERIFIED,
            case_reference="CVKI-20261014-VER",
            version=1,
        )
        self.in_memory_prov_repo.save_record(rec_v1)

        rec_v2 = self.engine.build_evidence_record(
            claim_type=ClaimType.MAINTENANCE_AUTHORITY,
            matched_attribute="maintenance_authority",
            source="BBMP Portal v2",
            source_type=SourceType.GOVERNMENT_REGISTRY,
            explanation="Re-assigned to NHAI Corridor Authority.",
            verification_state=VerificationState.VERIFIED,
            case_reference="CVKI-20261014-VER",
            version=2,
        )
        self.in_memory_prov_repo.save_record(rec_v2)

        history = self.in_memory_prov_repo.get_history_for_claim(
            case_reference="CVKI-20261014-VER",
            claim_type=ClaimType.MAINTENANCE_AUTHORITY,
        )
        self.assertEqual(len(history), 2)
        versions = [h.version for h in history]
        self.assertIn(1, versions)
        self.assertIn(2, versions)

    # -------------------------------------------------------------------------
    # V. Citizen Access (Own Case Allowed, Sensitive Fields Masked)
    # -------------------------------------------------------------------------
    def test_v_citizen_access(self):
        case = _build_test_case("CVKI-20261014-CIT", user_id="usr_citizen_42")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_citizen_42",
            email="citizen42@example.com",
            role=UserRole.CITIZEN.value,
        )

        res = self.client.get(f"/api/v1/provenance/cases/{case.reference_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["case_reference"], "CVKI-20261014-CIT")
        self.assertIn("claims", data)
        self.assertTrue(len(data["claims"]) > 0)
        # Ensure sensitive user IDs/audit data are not leaked
        self.assertNotIn("usr_citizen_42", str(data["claims"]))

    # -------------------------------------------------------------------------
    # W. Authority Access (Assigned Case Allowed)
    # -------------------------------------------------------------------------
    def test_w_authority_access(self):
        case = _build_test_case("CVKI-20261014-AUTH-OK", assigned_to="usr_assigned_auth")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_assigned_auth",
            email="auth@gov.in",
            role=UserRole.AUTHORITY.value,
        )

        res = self.client.get(f"/api/v1/provenance/cases/{case.reference_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["case_reference"], "CVKI-20261014-AUTH-OK")

    # -------------------------------------------------------------------------
    # X. Admin Access (Full Provenance Access)
    # -------------------------------------------------------------------------
    def test_x_admin_access(self):
        case = _build_test_case("CVKI-20261014-ADM", user_id="usr_other")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_superadmin",
            email="admin@cvki.gov",
            role=UserRole.ADMIN.value,
        )

        res = self.client.get(f"/api/v1/provenance/cases/{case.reference_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["case_reference"], "CVKI-20261014-ADM")

    # -------------------------------------------------------------------------
    # Y. Cross-User / Cross-Authority Denial (Strict 403 & 401)
    # -------------------------------------------------------------------------
    def test_y_cross_user_denial(self):
        case = _build_test_case("CVKI-20261014-CROSS", user_id="usr_citizen_owner", assigned_to="usr_auth_assigned")
        self.case_repo.save(case)

        # 1. Unauthenticated -> 401
        res = self.client.get(f"/api/v1/provenance/cases/{case.reference_id}")
        self.assertEqual(res.status_code, 401)

        # 2. Other Citizen -> 403
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_stranger_citizen",
            email="stranger@example.com",
            role=UserRole.CITIZEN.value,
        )
        res2 = self.client.get(f"/api/v1/provenance/cases/{case.reference_id}")
        self.assertEqual(res2.status_code, 403)

        # 3. Unassigned Authority -> 403
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_unassigned_auth",
            email="unassigned@gov.in",
            role=UserRole.AUTHORITY.value,
        )
        res3 = self.client.get(f"/api/v1/provenance/cases/{case.reference_id}")
        self.assertEqual(res3.status_code, 403)

    # -------------------------------------------------------------------------
    # Z. Audit Integration
    # -------------------------------------------------------------------------
    def test_z_audit_integration(self):
        rec = self.engine.build_evidence_record(
            claim_type=ClaimType.DETECTION,
            matched_attribute="pothole",
            source="CV YOLOv8n",
            source_type=SourceType.CV_MODEL,
            explanation="Pothole detected.",
            verification_state=VerificationState.VERIFIED,
            case_reference="CVKI-20261014-AUD",
        )
        self.in_memory_prov_repo.save_record(rec)

        with patch("app.services.audit.AuditService.record_event", new_callable=AsyncMock) as mock_audit:
            self.engine.invalidate_evidence(
                evidence_id=rec.evidence_id,
                reason="Re-inspection showed surface shadow.",
                actor_user_id="usr_inspector",
            )
            mock_audit.assert_called_once()
            args, kwargs = mock_audit.call_args
            self.assertEqual(kwargs.get("action") or args[0], "evidence_invalidated")

    # -------------------------------------------------------------------------
    # AA. Source URL Security (SSRF and Safe Source Allowlist)
    # -------------------------------------------------------------------------
    def test_aa_source_url_security(self):
        # Disallow loopback / private IP
        rec_loopback = self.engine.build_evidence_record(
            claim_type=ClaimType.MAINTENANCE_AUTHORITY,
            matched_attribute="maintenance_authority",
            source="Private Registry",
            source_type=SourceType.GOVERNMENT_REGISTRY,
            explanation="Authority data.",
            verification_state=VerificationState.VERIFIED,
            source_url="http://127.0.0.1:8000/internal-secrets",
        )
        self.assertIsNone(rec_loopback.source_url)
        self.assertIn("source_url_rejection_reason", rec_loopback.metadata)

        # Disallow cloud metadata endpoint
        rec_metadata = self.engine.build_evidence_record(
            claim_type=ClaimType.MAINTENANCE_AUTHORITY,
            matched_attribute="maintenance_authority",
            source="Cloud Metadata",
            source_type=SourceType.GOVERNMENT_REGISTRY,
            explanation="Metadata service.",
            verification_state=VerificationState.VERIFIED,
            source_url="http://169.254.169.254/latest/meta-data",
        )
        self.assertIsNone(rec_metadata.source_url)

        # Allow valid official source
        rec_valid = self.engine.build_evidence_record(
            claim_type=ClaimType.MAINTENANCE_AUTHORITY,
            matched_attribute="maintenance_authority",
            source="Official Road Portal",
            source_type=SourceType.GOVERNMENT_REGISTRY,
            explanation="Official gazette.",
            verification_state=VerificationState.VERIFIED,
            source_url="https://bbmp.gov.in/road-maintenance",
        )
        self.assertEqual(rec_valid.source_url, "https://bbmp.gov.in/road-maintenance")

    # -------------------------------------------------------------------------
    # AB. No Secret Leakage
    # -------------------------------------------------------------------------
    def test_ab_no_secret_leakage(self):
        case = _build_test_case("CVKI-20261014-SEC")
        self.case_repo.save(case)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="usr_admin",
            email="admin@example.com",
            role=UserRole.ADMIN.value,
        )

        res = self.client.get(f"/api/v1/provenance/cases/{case.reference_id}")
        self.assertEqual(res.status_code, 200)
        body = res.text.lower()
        self.assertNotIn("api_key", body)
        self.assertNotIn("secret_key", body)
        self.assertNotIn("password", body)
        self.assertNotIn("authorization", body)

    # -------------------------------------------------------------------------
    # AC. M6.1 Regression (Live Authority Provider remains functional)
    # -------------------------------------------------------------------------
    def test_ac_m61_regression(self):
        res = resolve_authority(
            latitude=12.91,
            longitude=77.63,
            context={"road": "NH-44 Hosur Road", "city": "Bengaluru", "state": "Karnataka"},
        )
        self.assertIsNotNone(res)
        self.assertIsNotNone(res.authority_status)

    # -------------------------------------------------------------------------
    # AD. M6.2 Regression (Geospatial Intelligence remains functional)
    # -------------------------------------------------------------------------
    def test_ad_m62_regression(self):
        ctx = asyncio.run(
            get_geospatial_intelligence_context(
                latitude=12.9716,
                longitude=77.5946,
                issue_category="pothole",
            )
        )
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.location.latitude, 12.9716)
        self.assertEqual(ctx.location.longitude, 77.5946)

    # -------------------------------------------------------------------------
    # AE. M6.3 Regression (External Civic Data remains functional)
    # -------------------------------------------------------------------------
    def test_ae_m63_regression(self):
        ctx = external_civic_service.get_external_civic_context(
            latitude=12.9716,
            longitude=77.5946,
            issue_category="pothole",
        )
        self.assertIsNotNone(ctx)
        self.assertIsNotNone(ctx.weather)
        self.assertIsNotNone(ctx.rainfall)

    # -------------------------------------------------------------------------
    # AF. M5.2 Regression (Recurrence Intelligence remains functional)
    # -------------------------------------------------------------------------
    def test_af_m52_regression(self):
        now = datetime.now(timezone.utc)
        c1 = _build_test_case("CVKI-20261014-R1", created_at=now - timedelta(days=10))
        c2 = _build_test_case("CVKI-20261014-R2", created_at=now)
        self.case_repo.save(c1)
        self.case_repo.save(c2)
        
        intel = asyncio.run(get_case_intelligence(c2.reference_id, actor_user_id="usr_admin", actor_role="admin"))
        self.assertIsNotNone(intel)
        self.assertTrue(intel.recurrence.recurrence_detected)
        self.assertEqual(intel.recurrence.recurrence_count, 1)


if __name__ == "__main__":
    unittest.main()
