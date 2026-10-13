from datetime import datetime, timezone
import unittest
import uuid

from fastapi.testclient import TestClient
import pymongo

from app.core.config import settings
from app.core.database import COMPLAINT_CASES_COLLECTION, USERS_COLLECTION
from app.core.security import create_access_token, hash_password
from app.main import app

TEST_DB_NAME = "cvki_test_analytics_m4_7"


def _build_analytics_case(
    ref_id: str,
    issue_class: str = "open_damaged_manhole",
    priority: str = "P1",
    priority_score: int = 90,
    status: str = "submitted_to_cvki",
    city: str = "Bengaluru",
    road: str = "Brigade Road",
    dup_class: str = "unique",
    auth_status: str = "verified",
    assigned: bool = False,
    created_at: datetime = None,
):
    now = created_at or datetime.now(timezone.utc)
    assignment = {
        "assigned_to_user_id": "usr_auth_1" if assigned else None,
        "assigned_to_role": "authority" if assigned else None,
        "assigned_to_email": "officer@bbmp.gov.in" if assigned else None,
        "assigned_by_user_id": "usr_admin_123" if assigned else None,
        "assigned_at": now if assigned else None,
        "assignment_status": "assigned" if assigned else "unassigned",
    }

    return {
        "reference_id": ref_id,
        "user_id": "usr_citizen_100",
        "created_at": now,
        "updated_at": now,
        "status": status,
        "issue": {
            "class_name": issue_class,
            "label": issue_class.replace("_", " ").title(),
            "severity": "high",
            "confidence": 0.95,
        },
        "location": {
            "road": road,
            "city": city,
            "pincode": "560025",
            "latitude": 12.9716,
            "longitude": 77.5946,
        },
        "complaint": {
            "language": "en",
            "title": f"Analytics Case {ref_id}",
            "description": "Reported issue for metrics testing.",
        },
        "evidence": ["frame_analytics.jpg"],
        "authority": {
            "name": "Bruhat Bengaluru Mahanagara Palike",
            "department": "Infrastructure",
            "portal_url": "https://bbmp.gov.in",
            "authority_status": auth_status,
        },
        "follow_up": {
            "guidance": "Processed.",
            "external_submission_status": "not_submitted",
        },
        "priority_analysis": {
            "priority_level": priority,
            "priority_score": priority_score,
            "risk_level": "Critical" if priority == "P1" else "Medium",
            "risk_factors": ["High volume area"],
        },
        "duplicate_analysis": {
            "status": dup_class,
            "classification": dup_class,
            "issue_match": False,
            "reason": "Evaluated classification",
            "similarity_score": 0.85 if dup_class == "duplicate" else 0.05,
        },
        "assignment": assignment,
    }


class TestAnalyticsM47(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = settings.MONGODB_DB_NAME
        settings.MONGODB_DB_NAME = TEST_DB_NAME

        try:
            cls.sync_client = pymongo.MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            cls.sync_client.admin.command("ping")
        except Exception:
            raise unittest.SkipTest("MongoDB is unavailable for Analytics test suite.")

        cls.sync_db = cls.sync_client[TEST_DB_NAME]
        cls.users_col = cls.sync_db[USERS_COLLECTION]
        cls.cases_col = cls.sync_db[COMPLAINT_CASES_COLLECTION]

        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "sync_client") and cls.sync_client is not None:
            try:
                cls.sync_client.drop_database(TEST_DB_NAME)
            except Exception:
                pass
            cls.sync_client.close()

        if hasattr(cls, "client_cm"):
            cls.client_cm.__exit__(None, None, None)

        settings.MONGODB_DB_NAME = cls._orig_db

    def setUp(self):
        self.users_col.delete_many({})
        self.cases_col.delete_many({})

        self.admin_id = self._insert_user("admin@cvki.gov.in", role="admin")
        self.citizen_id = self._insert_user("citizen@cvki.gov.in", role="citizen")
        self.authority_id = self._insert_user("officer@bbmp.gov.in", role="authority")

        self.admin_token = create_access_token(self.admin_id, role="admin", email="admin@cvki.gov.in")
        self.citizen_token = create_access_token(self.citizen_id, role="citizen", email="citizen@cvki.gov.in")
        self.authority_token = create_access_token(self.authority_id, role="authority", email="officer@bbmp.gov.in")

    def _insert_user(self, email: str, role: str = "citizen") -> str:
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        self.users_col.insert_one({
            "user_id": user_id,
            "email": email.strip().lower(),
            "password_hash": hash_password("SecurePassword2026!"),
            "role": role,
            "is_active": True,
            "created_at": now,
        })
        return user_id

    # --- Test 1: Admin can access analytics endpoint ---
    def test_01_admin_access_allowed(self):
        self.cases_col.insert_one(_build_analytics_case("CVKI-AN-1"))
        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["summary"]["total_cases"], 1)
        self.assertIn("engineering prioritization baseline", data["disclaimer"])

    # --- Test 2: Unauthenticated request rejected (401) ---
    def test_02_unauthenticated_rejected(self):
        resp = self.client.get("/api/v1/admin/analytics")
        self.assertEqual(resp.status_code, 401)

    # --- Test 3: Citizen access forbidden (403) ---
    def test_03_citizen_forbidden(self):
        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    # --- Test 4: Authority access forbidden (admin-only endpoint) (403) ---
    def test_04_authority_forbidden(self):
        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.authority_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    # --- Test 5: Empty database returns zero metrics safely ---
    def test_05_empty_database_returns_zero_metrics(self):
        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["summary"]["total_cases"], 0)
        self.assertEqual(data["summary"]["open_cases"], 0)
        self.assertEqual(data["summary"]["resolved_cases"], 0)
        self.assertEqual(data["issue_distribution"], [])
        self.assertEqual(len(data["priority_distribution"]), 4)
        for prio in data["priority_distribution"]:
            self.assertEqual(prio["count"], 0)

    # --- Test 6: Issue distribution aggregation correctness ---
    def test_06_issue_distribution_aggregation(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", issue_class="open_damaged_manhole"))
        self.cases_col.insert_one(_build_analytics_case("C-2", issue_class="open_damaged_manhole"))
        self.cases_col.insert_one(_build_analytics_case("C-3", issue_class="road_waterlogging"))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        issues = {item["key"]: item["count"] for item in data["issue_distribution"]}
        self.assertEqual(issues.get("open_damaged_manhole"), 2)
        self.assertEqual(issues.get("road_waterlogging"), 1)

    # --- Test 7: Priority distribution aggregation (P1, P2, P3, P4) ---
    def test_07_priority_distribution_aggregation(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", priority="P1", priority_score=95))
        self.cases_col.insert_one(_build_analytics_case("C-2", priority="P2", priority_score=75))
        self.cases_col.insert_one(_build_analytics_case("C-3", priority="P2", priority_score=80))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        prios = {item["key"]: item["count"] for item in data["priority_distribution"]}
        self.assertEqual(prios.get("P1"), 1)
        self.assertEqual(prios.get("P2"), 2)
        # Average priority score should be computed: (95 + 75 + 80) / 3 = 83.33
        self.assertAlmostEqual(data["summary"]["average_priority_score"], 83.33, places=1)

    # --- Test 8: Status distribution aggregation ---
    def test_08_status_distribution_aggregation(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", status="submitted_to_cvki"))
        self.cases_col.insert_one(_build_analytics_case("C-2", status="in_progress"))
        self.cases_col.insert_one(_build_analytics_case("C-3", status="resolved"))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        statuses = {item["key"]: item["count"] for item in data["status_distribution"]}
        self.assertEqual(statuses.get("submitted_to_cvki"), 1)
        self.assertEqual(statuses.get("in_progress"), 1)
        self.assertEqual(statuses.get("resolved"), 1)

    # --- Test 9: Duplicate classification distribution ---
    def test_09_duplicate_distribution_aggregation(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", dup_class="unique"))
        self.cases_col.insert_one(_build_analytics_case("C-2", dup_class="possible_duplicate"))
        self.cases_col.insert_one(_build_analytics_case("C-3", dup_class="duplicate"))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        dups = {item["key"]: item["count"] for item in data["duplicate_distribution"]}
        self.assertEqual(dups.get("unique"), 1)
        self.assertEqual(dups.get("possible_duplicate"), 1)
        self.assertEqual(dups.get("duplicate"), 1)

    # --- Test 10: City distribution aggregation ---
    def test_10_city_distribution_aggregation(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", city="Bengaluru"))
        self.cases_col.insert_one(_build_analytics_case("C-2", city="Bengaluru"))
        self.cases_col.insert_one(_build_analytics_case("C-3", city="Mysuru"))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        cities = {item["key"]: item["count"] for item in data["city_distribution"]}
        self.assertEqual(cities.get("Bengaluru"), 2)
        self.assertEqual(cities.get("Mysuru"), 1)

    # --- Test 11: Authority verification status distribution ---
    def test_11_authority_status_distribution(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", auth_status="verified"))
        self.cases_col.insert_one(_build_analytics_case("C-2", auth_status="partially_verified"))
        self.cases_col.insert_one(_build_analytics_case("C-3", auth_status="not_verified"))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        auths = {item["key"]: item["count"] for item in data["authority_distribution"]}
        self.assertEqual(auths.get("verified"), 1)
        self.assertEqual(auths.get("partially_verified"), 1)
        self.assertEqual(auths.get("not_verified"), 1)

    # --- Test 12: Geographic concentration top hotspots ---
    def test_12_geographic_concentration(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", road="Indiranagar 100ft Rd", city="Bengaluru"))
        self.cases_col.insert_one(_build_analytics_case("C-2", road="Indiranagar 100ft Rd", city="Bengaluru"))
        self.cases_col.insert_one(_build_analytics_case("C-3", road="Koramangala 80ft Rd", city="Bengaluru"))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        conc = data["geographic_concentration"]
        self.assertGreaterEqual(len(conc), 2)
        self.assertEqual(conc[0]["road"], "Indiranagar 100ft Rd")
        self.assertEqual(conc[0]["count"], 2)

    # --- Test 13: Time series aggregation (daily, weekly, monthly) ---
    def test_13_time_series_grouping(self):
        d1 = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
        d2 = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
        self.cases_col.insert_one(_build_analytics_case("C-1", created_at=d1))
        self.cases_col.insert_one(_build_analytics_case("C-2", created_at=d2))

        # Daily
        resp_daily = self.client.get(
            "/api/v1/admin/analytics?group_by=daily",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp_daily.status_code, 200)
        daily_series = resp_daily.json()["time_series"]
        self.assertGreaterEqual(len(daily_series), 2)

        # Monthly
        resp_monthly = self.client.get(
            "/api/v1/admin/analytics?group_by=monthly",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp_monthly.status_code, 200)
        monthly_series = resp_monthly.json()["time_series"]
        self.assertEqual(len(monthly_series), 1)
        self.assertEqual(monthly_series[0]["date"], "2026-10")
        self.assertEqual(monthly_series[0]["count"], 2)

    # --- Test 14: Resolution metrics ---
    def test_14_resolution_metrics_calculation(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", status="resolved"))
        self.cases_col.insert_one(_build_analytics_case("C-2", status="closed"))
        self.cases_col.insert_one(_build_analytics_case("C-3", status="in_progress"))
        self.cases_col.insert_one(_build_analytics_case("C-4", status="submitted_to_cvki"))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        metrics = data["resolution_metrics"]
        self.assertEqual(metrics["resolved_count"], 1)
        self.assertEqual(metrics["closed_count"], 1)
        self.assertEqual(metrics["open_count"], 2)
        # 2 out of 4 resolved/closed = 50.0%
        self.assertEqual(metrics["resolution_rate_pct"], 50.0)

    # --- Test 15: Multi-criteria filtering updates analytics ---
    def test_15_filter_by_issue_and_priority(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", issue_class="open_damaged_manhole", priority="P1"))
        self.cases_col.insert_one(_build_analytics_case("C-2", issue_class="open_damaged_manhole", priority="P2"))
        self.cases_col.insert_one(_build_analytics_case("C-3", issue_class="road_waterlogging", priority="P1"))

        resp = self.client.get(
            "/api/v1/admin/analytics?issue=open_damaged_manhole&priority=P1",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["summary"]["total_cases"], 1)
        self.assertEqual(data["summary"]["open_cases"], 1)

    # --- Test 16: Assigned vs unassigned breakdown ---
    def test_16_assigned_vs_unassigned_summary(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", assigned=True))
        self.cases_col.insert_one(_build_analytics_case("C-2", assigned=False))

        resp = self.client.get(
            "/api/v1/admin/analytics",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        summary = resp.json()["summary"]
        self.assertEqual(summary["assigned_cases"], 1)
        self.assertEqual(summary["unassigned_cases"], 1)

    # --- Test 17: CSV export returns valid CSV content and attachment header ---
    def test_17_csv_export_endpoint(self):
        self.cases_col.insert_one(_build_analytics_case("C-1", issue_class="open_damaged_manhole", priority="P1"))

        resp = self.client.get(
            "/api/v1/admin/analytics/export",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers["content-type"])
        self.assertIn("cvki_operational_analytics.csv", resp.headers.get("content-disposition", ""))
        self.assertIn("CVKI OPERATIONAL ANALYTICS SUMMARY", resp.text)
        self.assertIn("open_damaged_manhole", resp.text)

    def test_csv_export_neutralizes_spreadsheet_formulas(self):
        case = _build_analytics_case("C-CSV-FORMULA")
        case["location"]["road"] = '=HYPERLINK("https://example.invalid")'
        self.cases_col.insert_one(case)

        response = self.client.get(
            "/api/v1/admin/analytics/export",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.text)

    # --- Test 18: CSV export forbidden to non-admin users ---
    def test_18_csv_export_forbidden_to_citizen(self):
        resp = self.client.get(
            "/api/v1/admin/analytics/export",
            headers={"Authorization": f"Bearer {self.citizen_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    # --- Test 19: Date range filter bounded results ---
    def test_19_date_range_filter(self):
        d_old = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        d_recent = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
        self.cases_col.insert_one(_build_analytics_case("C-OLD", created_at=d_old))
        self.cases_col.insert_one(_build_analytics_case("C-RECENT", created_at=d_recent))

        resp = self.client.get(
            "/api/v1/admin/analytics?created_from=2026-10-01T00:00:00Z",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["summary"]["total_cases"], 1)
