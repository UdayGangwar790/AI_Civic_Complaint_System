from datetime import datetime, timedelta, timezone
import asyncio
import unittest

from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.main import app
from app.schemas.authority import AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseAssignment,
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    ComplaintCaseCreateRequest,
    FollowUp,
)
from app.schemas.civic_intelligence import ResolutionEvidenceRecord
from app.schemas.duplicate import DuplicateCheckResponse
from app.schemas.priority import PriorityScoreResponse
from app.services.civic_intelligence import (
    _resolution_evidence_state,
    analyze_recurrence_for_new_case,
    get_case_intelligence,
)
import app.services.complaint_case as complaint_case_module
from app.services.complaint_case import InMemoryComplaintCaseRepository, set_case_repository
from app.services.complaint_case import create_case


NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def make_case(
    reference_id,
    *,
    issue="open_damaged_manhole",
    days_ago=0,
    status="submitted_to_cvki",
    latitude=12.9716,
    longitude=77.5946,
    road="Brigade Road",
    city="Bengaluru",
    assigned_to=None,
    resolution_evidence=None,
    resolution_evidence_recorded_at=None,
):
    created_at = NOW - timedelta(days=days_ago)
    assignment = CaseAssignment(
        assigned_to_user_id=assigned_to,
        assigned_to_role="authority" if assigned_to else None,
        assignment_status="assigned" if assigned_to else "unassigned",
    )
    return ComplaintCase(
        reference_id=reference_id,
        user_id=f"citizen-{reference_id}",
        status=status,
        created_at=created_at,
        updated_at=created_at,
        issue=CaseIssue(
            class_name=issue,
            label=issue.replace("_", " ").title(),
            severity="high",
            confidence=0.8,
        ),
        location=ComplaintLocation(
            road=road,
            city=city,
            latitude=latitude,
            longitude=longitude,
        ),
        authority=AuthorityResult(authority_status="not_verified"),
        complaint=CaseComplaint(language="en", title="Reported issue", description="A civic issue was reported."),
        follow_up=FollowUp(guidance="Saved in CVKI."),
        assignment=assignment,
        resolution_evidence=resolution_evidence or [],
        resolution_evidence_recorded_at=resolution_evidence_recorded_at,
    )


class TestCivicIntelligenceM52(unittest.TestCase):
    def setUp(self):
        self.original_repository = complaint_case_module.case_repository
        self.repository = InMemoryComplaintCaseRepository()
        set_case_repository(self.repository)
        self.client = TestClient(app)
        self.original_overrides = dict(app.dependency_overrides)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides = self.original_overrides
        set_case_repository(self.original_repository)

    def test_no_history_is_not_recurrence(self):
        recurrence = asyncio.run(
            analyze_recurrence_for_new_case(
                "open_damaged_manhole",
                ComplaintLocation(road="Brigade Road", city="Bengaluru", latitude=12.9716, longitude=77.5946),
                NOW,
            )
        )
        self.assertFalse(recurrence.recurrence_detected)
        self.assertEqual(recurrence.recurrence_count, 0)
        self.assertIn("insufficient historical evidence", recurrence.recurrence_explanation)

    def test_recurrence_requires_same_issue_location_and_more_than_duplicate_window(self):
        self.repository.save(make_case("OLD-SAME-1", days_ago=12, status="resolved"))
        self.repository.save(make_case("OLD-SAME-2", days_ago=5, status="closed"))
        self.repository.save(make_case("RECENT-DUP", days_ago=1))
        self.repository.save(make_case("OTHER-ISSUE", issue="road_waterlogging", days_ago=8))
        self.repository.save(make_case("OTHER-LOCATION", days_ago=8, latitude=12.98, longitude=77.60))

        recurrence = asyncio.run(
            analyze_recurrence_for_new_case(
                "open_damaged_manhole",
                ComplaintLocation(road="Brigade Road", city="Bengaluru", latitude=12.9716, longitude=77.5946),
                NOW,
            )
        )
        self.assertTrue(recurrence.recurrence_detected)
        self.assertEqual(recurrence.recurrence_count, 2)
        self.assertNotIn("RECENT-DUP", recurrence.related_historical_case_ids)
        self.assertNotIn("OTHER-ISSUE", recurrence.related_historical_case_ids)
        self.assertNotIn("OTHER-LOCATION", recurrence.related_historical_case_ids)

    def test_nearby_different_issue_is_not_recurrence(self):
        self.repository.save(make_case("NEARBY-WATER", issue="road_waterlogging", days_ago=5))
        recurrence = asyncio.run(
            analyze_recurrence_for_new_case(
                "open_damaged_manhole",
                ComplaintLocation(road="Brigade Road", city="Bengaluru", latitude=12.9716, longitude=77.5946),
                NOW,
            )
        )
        self.assertFalse(recurrence.recurrence_detected)
        self.assertEqual(recurrence.recurrence_count, 0)

    def test_same_issue_within_72_hours_remains_duplicate_window_not_recurrence(self):
        self.repository.save(make_case("DUPLICATE-WINDOW", days_ago=1))
        current = make_case("CURRENT", days_ago=0)
        current.duplicate_analysis = DuplicateCheckResponse(
            classification="possible_duplicate",
            similarity_score=0.7,
            matched_reference_id="DUPLICATE-WINDOW",
            issue_match=True,
            reason="Possible same incident.",
        )
        self.repository.save(current)
        response = asyncio.run(
            get_case_intelligence("CURRENT", "admin-1", "admin")
        )
        self.assertEqual(response.recurrence.recurrence_count, 0)
        self.assertFalse(response.recurrence.recurrence_detected)

    def test_recurrence_count_is_exact_for_history_within_scan_limit(self):
        self.repository.save(make_case("REC-ONE", days_ago=30))
        self.repository.save(make_case("REC-TWO", days_ago=20))
        self.repository.save(make_case("REC-THREE", days_ago=10))
        current = make_case("REC-CURRENT")
        self.repository.save(current)
        response = asyncio.run(get_case_intelligence("REC-CURRENT", "admin-1", "admin"))
        self.assertEqual(response.recurrence.recurrence_count, 3)
        self.assertTrue(response.recurrence.history_scan_complete)
        self.assertEqual(len(response.recurrence.related_historical_case_ids), 3)

    def test_new_case_persists_recurrence_and_priority_signal(self):
        self.repository.save(make_case("HISTORICAL", days_ago=10, status="resolved"))
        request = ComplaintCaseCreateRequest(
            issue=CaseIssue(
                class_name="open_damaged_manhole",
                label="Open/Damaged Manhole",
                severity="high",
                confidence=0.8,
            ),
            location=ComplaintLocation(
                road="Brigade Road",
                city="Bengaluru",
                latitude=12.9716,
                longitude=77.5946,
            ),
            complaint=CaseComplaint(
                language="en",
                title="Open manhole",
                description="An open manhole is reported on Brigade Road.",
            ),
            priority_analysis=PriorityScoreResponse(
                priority_score=0,
                priority_level="P4",
                risk_level="Low",
                reasons=["Client-provided priority must not be trusted."],
            ),
        )
        saved_case = asyncio.run(create_case(request, user_id="citizen-new"))
        self.assertTrue(saved_case.recurrence_analysis.recurrence_detected)
        self.assertEqual(saved_case.recurrence_analysis.recurrence_count, 1)
        self.assertEqual(saved_case.priority_analysis.recurrence_score, 2)
        self.assertTrue(any("Separate issue recurrence signal" in item for item in saved_case.priority_analysis.evidence))

    def test_resolution_states_distinguish_status_note_and_reopened_case(self):
        unresolved = make_case("OPEN")
        self.assertEqual(_resolution_evidence_state(unresolved)[0], "status_only")

        resolved_without_note = make_case("RESOLVED-NO-NOTE", status="resolved")
        self.assertEqual(_resolution_evidence_state(resolved_without_note)[0], "evidence_missing")

        note = ResolutionEvidenceRecord(
            note="Inspection note recorded by assigned authority.",
            recorded_at=NOW,
            recorded_by_role="authority",
        )
        resolved_with_note = make_case(
            "RESOLVED-WITH-NOTE",
            status="resolved",
            resolution_evidence=[note],
            resolution_evidence_recorded_at=NOW,
        )
        state, explanation = _resolution_evidence_state(resolved_with_note)
        self.assertEqual(state, "evidence_supported")
        self.assertIn("not independently verified", explanation)

        reopened = make_case("REOPENED", status="in_progress", resolution_evidence=[note], resolution_evidence_recorded_at=NOW)
        self.assertEqual(_resolution_evidence_state(reopened)[0], "status_only")

        closed_after_reopen = make_case(
            "CLOSED-OLD-NOTE",
            status="closed",
            resolution_evidence=[note],
            resolution_evidence_recorded_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(_resolution_evidence_state(closed_after_reopen)[0], "evidence_missing")

    def test_recommendations_are_based_on_saved_history_and_do_not_claim_repair(self):
        self.repository.save(make_case("PAST-1", days_ago=50, status="resolved"))
        self.repository.save(make_case("PAST-2", days_ago=49, status="in_progress"))
        current = make_case("CURRENT-OPEN", days_ago=45)
        self.repository.save(current)
        response = __import__("asyncio").run(get_case_intelligence("CURRENT-OPEN", "admin-1", "admin"))
        kinds = {item.kind for item in response.recommendations}
        self.assertIn("recurrence", kinds)
        self.assertIn("hotspot", kinds)
        self.assertIn("unresolved_duration", kinds)
        all_text = " ".join(item.message + " " + item.basis for item in response.recommendations).lower()
        self.assertNotIn("repair verified", all_text)
        self.assertNotIn("authority must", all_text)
        self.assertEqual(response.recent_location_unresolved_count, 2)

    def test_admin_and_assigned_authority_scoping_and_citizen_denial(self):
        self.repository.save(make_case("SCOPED-HISTORY", days_ago=8))
        current = make_case("SCOPED", assigned_to="authority-1")
        self.repository.save(current)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="citizen-1", email="citizen@example.invalid", role="citizen"
        )
        citizen_response = self.client.get("/api/v1/admin/cases/SCOPED/intelligence")
        self.assertEqual(citizen_response.status_code, 403)

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="admin-1", email="admin@example.invalid", role="admin"
        )
        admin_response = self.client.get("/api/v1/admin/cases/SCOPED/intelligence")
        self.assertEqual(admin_response.status_code, 200)
        self.assertIn("SCOPED-HISTORY", admin_response.json()["recurrence"]["related_historical_case_ids"])

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="authority-1", email="authority@example.invalid", role="authority"
        )
        authority_response = self.client.get("/api/v1/authority/cases/SCOPED/intelligence")
        self.assertEqual(authority_response.status_code, 200)
        self.assertEqual(authority_response.json()["recurrence"]["related_historical_case_ids"], [])

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id="authority-2", email="other@example.invalid", role="authority"
        )
        other_authority_response = self.client.get("/api/v1/authority/cases/SCOPED/intelligence")
        self.assertEqual(other_authority_response.status_code, 403)

    def test_unauthenticated_intelligence_request_is_rejected(self):
        response = self.client.get("/api/v1/admin/cases/NO-AUTH/intelligence")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
