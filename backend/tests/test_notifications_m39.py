from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.schemas.authority import AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import (
    CaseComplaint,
    CaseIssue,
    ComplaintCase,
    ComplaintCaseCreateRequest,
    FollowUp,
)
from app.schemas.notification import NotificationCreate
from app.services import complaint_case as cc_mod
from app.services import notification as notif_mod
from app.services.complaint_case import InMemoryComplaintCaseRepository
from app.services.notification import (
    InMemoryNotificationRepository,
    create_notification,
    get_user_unread_count,
    list_user_notifications,
    mark_all_notifications_as_read,
    mark_notification_as_read,
    set_notification_repository,
    trigger_case_created_notification,
    trigger_duplicate_detected_notification,
    trigger_gov_submission_prepared_notification,
    trigger_priority_assigned_notification,
    trigger_status_changed_notification,
)


class TestNotificationsM39(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

        # Register User 1
        reg1 = cls.client.post("/api/v1/auth/register", json={"email": "m39_user1@cvki.internal", "password": "Password123!", "full_name": "User One"})
        if reg1.status_code in (200, 201):
            cls.token1 = reg1.cookies.get(settings.AUTH_COOKIE_NAME)
            cls.user1_id = reg1.json()["user"]["user_id"]
        else:
            login1 = cls.client.post("/api/v1/auth/login", json={"email": "m39_user1@cvki.internal", "password": "Password123!"})
            cls.token1 = login1.cookies.get(settings.AUTH_COOKIE_NAME)
            cls.user1_id = login1.json()["user"]["user_id"]
        cls.auth_headers1 = {"Authorization": f"Bearer {cls.token1}"}

        # Register User 2 (for cross-user ownership tests)
        reg2 = cls.client.post("/api/v1/auth/register", json={"email": "m39_user2@cvki.internal", "password": "Password123!", "full_name": "User Two"})
        if reg2.status_code in (200, 201):
            cls.token2 = reg2.cookies.get(settings.AUTH_COOKIE_NAME)
            cls.user2_id = reg2.json()["user"]["user_id"]
        else:
            login2 = cls.client.post("/api/v1/auth/login", json={"email": "m39_user2@cvki.internal", "password": "Password123!"})
            cls.token2 = login2.cookies.get(settings.AUTH_COOKIE_NAME)
            cls.user2_id = login2.json()["user"]["user_id"]
        cls.auth_headers2 = {"Authorization": f"Bearer {cls.token2}"}

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def setUp(self):
        self.client.cookies.clear()
        self._orig_notif_repo = notif_mod.notification_repository
        self._orig_case_repo = cc_mod.case_repository
        self.notif_repo = InMemoryNotificationRepository()
        self.case_repo = InMemoryComplaintCaseRepository()
        set_notification_repository(self.notif_repo)
        cc_mod.set_case_repository(self.case_repo)

    def tearDown(self):
        set_notification_repository(self._orig_notif_repo)
        cc_mod.set_case_repository(self._orig_case_repo)

    # 1. Notification creation
    def test_01_notification_creation(self):
        import asyncio
        req = NotificationCreate(
            user_id=self.user1_id,
            reference_id="CVKI-20261011-TEST01",
            type="case_created",
            title="Case Created",
            message="Your case has been created successfully.",
            priority="P2",
        )
        notif = asyncio.run(create_notification(req))
        self.assertIsNotNone(notif.notification_id)
        self.assertTrue(notif.notification_id.startswith("notif_"))
        self.assertEqual(notif.user_id, self.user1_id)
        self.assertEqual(notif.reference_id, "CVKI-20261011-TEST01")
        self.assertEqual(notif.type, "case_created")
        self.assertFalse(notif.is_read)
        self.assertEqual(notif.delivery_status, "in_app")

    # 2. Notification listing
    def test_02_notification_listing(self):
        import asyncio
        asyncio.run(create_notification(NotificationCreate(
            user_id=self.user1_id,
            type="case_created",
            title="First Notice",
            message="Welcome to CVKI",
            priority="P3",
        )))
        asyncio.run(create_notification(NotificationCreate(
            user_id=self.user1_id,
            type="priority_assigned",
            title="Second Notice",
            message="Priority assigned",
            priority="P2",
        )))

        res = self.client.get("/api/v1/notifications", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["unread_count"], 2)

    # 3. Pagination
    def test_03_pagination(self):
        import asyncio
        for i in range(15):
            asyncio.run(create_notification(NotificationCreate(
                user_id=self.user1_id,
                type="system_notification",
                title=f"Notice {i}",
                message=f"Message {i}",
                priority="P4",
            )))

        res = self.client.get("/api/v1/notifications?page=1&page_size=10", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 15)
        self.assertEqual(len(data["items"]), 10)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["pages"], 2)

        res_p2 = self.client.get("/api/v1/notifications?page=2&page_size=10", headers=self.auth_headers1)
        self.assertEqual(res_p2.status_code, 200)
        data_p2 = res_p2.json()
        self.assertEqual(len(data_p2["items"]), 5)

    # 4. Unread count
    def test_04_unread_count(self):
        import asyncio
        asyncio.run(create_notification(NotificationCreate(
            user_id=self.user1_id,
            type="case_created",
            title="Test",
            message="Test msg",
        )))
        res = self.client.get("/api/v1/notifications/unread-count", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["unread_count"], 1)

    # 5. Mark one read
    def test_05_mark_one_read(self):
        import asyncio
        notif = asyncio.run(create_notification(NotificationCreate(
            user_id=self.user1_id,
            type="case_created",
            title="Unread Notice",
            message="Content",
        )))
        res = self.client.post(f"/api/v1/notifications/{notif.notification_id}/read", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["notification"]["is_read"])

        # Verify unread count decreases
        res_count = self.client.get("/api/v1/notifications/unread-count", headers=self.auth_headers1)
        self.assertEqual(res_count.json()["unread_count"], 0)

    # 6. Mark all read
    def test_06_mark_all_read(self):
        import asyncio
        for i in range(3):
            asyncio.run(create_notification(NotificationCreate(
                user_id=self.user1_id,
                type="system_notification",
                title=f"Alert {i}",
                message=f"Msg {i}",
            )))
        res = self.client.post("/api/v1/notifications/read-all", headers=self.auth_headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["updated_count"], 3)

        res_count = self.client.get("/api/v1/notifications/unread-count", headers=self.auth_headers1)
        self.assertEqual(res_count.json()["unread_count"], 0)

    # 7. Notification ownership
    def test_07_notification_ownership(self):
        import asyncio
        notif = asyncio.run(create_notification(NotificationCreate(
            user_id=self.user1_id,
            type="case_created",
            title="User 1 Secret",
            message="Secret message",
        )))
        # User 2 tries to mark User 1's notification as read
        res = self.client.post(f"/api/v1/notifications/{notif.notification_id}/read", headers=self.auth_headers2)
        self.assertEqual(res.status_code, 403)

        # User 2 listings do not see User 1's notifications
        res_list = self.client.get("/api/v1/notifications", headers=self.auth_headers2)
        self.assertEqual(res_list.json()["total"], 0)

    # 8. Unauthorized access
    def test_08_unauthorized_access(self):
        res = self.client.get("/api/v1/notifications")
        self.assertEqual(res.status_code, 401)
        res_count = self.client.get("/api/v1/notifications/unread-count")
        self.assertEqual(res_count.status_code, 401)

    # 9. Case-created notification trigger
    def test_09_case_created_notification(self):
        case_payload = {
            "issue": {
                "class_name": "open_damaged_manhole",
                "label": "Open/Damaged Manhole",
                "severity": "high",
                "confidence": 0.85,
            },
            "location": {
                "road": "MG Road",
                "city": "Bengaluru",
                "district": "Bengaluru Urban",
                "state": "Karnataka",
                "latitude": 12.9716,
                "longitude": 77.5946,
            },
            "complaint": {
                "language": "en",
                "title": "Open manhole hazard",
                "description": "Deep open manhole poses urgent risk to pedestrians.",
            },
            "evidence": ["photo.jpg"],
        }
        res = self.client.post("/api/v1/complaint/cases", json=case_payload, headers=self.auth_headers1)
        self.assertIn(res.status_code, (200, 201))
        ref_id = res.json()["reference_id"]

        # Check notifications for user1
        res_notifs = self.client.get("/api/v1/notifications", headers=self.auth_headers1)
        self.assertEqual(res_notifs.status_code, 200)
        items = res_notifs.json()["items"]
        case_created_items = [n for n in items if n["type"] == "case_created"]
        self.assertGreaterEqual(len(case_created_items), 1)
        self.assertEqual(case_created_items[0]["reference_id"], ref_id)
        self.assertIn(ref_id, case_created_items[0]["message"])

    # 10. Priority notification trigger
    def test_10_priority_notification(self):
        import asyncio
        case = ComplaintCase(
            reference_id="CVKI-20261011-PRI001",
            user_id=self.user1_id,
            status="submitted_to_cvki",
            created_at=datetime.now(timezone.utc),
            issue=CaseIssue(class_name="open_damaged_manhole", label="Open Manhole", severity="high", confidence=0.9),
            location=ComplaintLocation(road="MG Road", latitude=12.97, longitude=77.59),
            authority=AuthorityResult(authority_status="not_verified"),
            complaint=CaseComplaint(language="en", title="Manhole", description="Urgent danger"),
            follow_up=FollowUp(guidance="guidance"),
        )
        # Attach M3.8 priority analysis
        from app.schemas.priority import PriorityScoreResponse
        case.priority_analysis = PriorityScoreResponse(
            priority_score=85,
            priority_level="P1",
            risk_level="Critical",
            reasons=["Open manhole"],
            evidence=["High risk"],
            limitations=[],
        )
        notif = asyncio.run(trigger_priority_assigned_notification(case))
        self.assertIsNotNone(notif)
        self.assertEqual(notif.type, "priority_assigned")
        self.assertEqual(notif.priority, "P1")
        self.assertIn("P1", notif.title)

    # 11. Duplicate notification trigger
    def test_11_duplicate_notification(self):
        import asyncio
        case = ComplaintCase(
            reference_id="CVKI-20261011-DUP001",
            user_id=self.user1_id,
            status="submitted_to_cvki",
            created_at=datetime.now(timezone.utc),
            issue=CaseIssue(class_name="open_damaged_manhole", label="Open Manhole", severity="high", confidence=0.9),
            location=ComplaintLocation(road="MG Road", latitude=12.97, longitude=77.59),
            authority=AuthorityResult(authority_status="not_verified"),
            complaint=CaseComplaint(language="en", title="Manhole", description="Urgent danger"),
            follow_up=FollowUp(guidance="guidance"),
        )
        from app.schemas.duplicate import DuplicateCheckResponse
        case.duplicate_analysis = DuplicateCheckResponse(
            classification="duplicate",
            similarity_score=0.92,
            matched_reference_id="CVKI-20261011-PREV01",
            distance_meters=20.0,
            time_difference_hours=2.0,
            issue_match=True,
            reason="High similarity",
        )
        notif = asyncio.run(trigger_duplicate_detected_notification(case))
        self.assertIsNotNone(notif)
        self.assertEqual(notif.type, "duplicate_detected")
        self.assertIn("CVKI-20261011-PREV01", notif.message)

    # 12. Status-change notification trigger
    def test_12_status_change_notification(self):
        import asyncio
        case = ComplaintCase(
            reference_id="CVKI-20261011-STAT01",
            user_id=self.user1_id,
            status="under_review",
            created_at=datetime.now(timezone.utc),
            issue=CaseIssue(class_name="open_damaged_manhole", label="Open Manhole", severity="high", confidence=0.9),
            location=ComplaintLocation(road="MG Road", latitude=12.97, longitude=77.59),
            authority=AuthorityResult(authority_status="not_verified"),
            complaint=CaseComplaint(language="en", title="Manhole", description="Danger"),
            follow_up=FollowUp(guidance="guidance"),
        )
        notif = asyncio.run(trigger_status_changed_notification(case, old_status="submitted_to_cvki", new_status="under_review"))
        self.assertIsNotNone(notif)
        self.assertEqual(notif.type, "case_status_changed")
        self.assertIn("under_review", notif.message)

    # 13. Government-prepared notification trigger
    def test_13_government_prepared_notification(self):
        import asyncio
        case = ComplaintCase(
            reference_id="CVKI-20261011-GOV01",
            user_id=self.user1_id,
            status="submitted_to_cvki",
            created_at=datetime.now(timezone.utc),
            issue=CaseIssue(class_name="open_damaged_manhole", label="Open Manhole", severity="high", confidence=0.9),
            location=ComplaintLocation(road="MG Road", latitude=12.97, longitude=77.59),
            authority=AuthorityResult(authority_status="verified"),
            complaint=CaseComplaint(language="en", title="Manhole", description="Danger"),
            follow_up=FollowUp(guidance="guidance"),
        )
        notif = asyncio.run(trigger_gov_submission_prepared_notification(case))
        self.assertIsNotNone(notif)
        self.assertEqual(notif.type, "government_submission_prepared")
        self.assertIn("prepared and ready for citizen review", notif.message)
        self.assertIn("Not submitted to external portal yet", notif.message)

    # 14. No notification on failed case creation
    def test_14_no_notification_on_failed_case_creation(self):
        initial_count = self.client.get("/api/v1/notifications/unread-count", headers=self.auth_headers1).json()["unread_count"]
        # Post invalid payload
        invalid_payload = {"issue": {"class_name": "unknown_invalid_class"}}
        res = self.client.post("/api/v1/complaint/cases", json=invalid_payload, headers=self.auth_headers1)
        self.assertIn(res.status_code, (422, 400))
        # Verify no notification created
        new_count = self.client.get("/api/v1/notifications/unread-count", headers=self.auth_headers1).json()["unread_count"]
        self.assertEqual(new_count, initial_count)

    # 15. Malformed request
    def test_15_malformed_request(self):
        res = self.client.get("/api/v1/notifications?page=invalid", headers=self.auth_headers1)
        self.assertIn(res.status_code, (400, 422))
        res2 = self.client.get("/api/v1/notifications?page_size=9999", headers=self.auth_headers1)
        self.assertIn(res2.status_code, (400, 422))


if __name__ == "__main__":
    unittest.main()
