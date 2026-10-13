import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.authority import AuthorityResult
from app.schemas.complaint import ComplaintLocation
from app.schemas.duplicate import DuplicateCheckResponse
from app.schemas.civic_intelligence import RecurrenceAnalysis
from app.schemas.nlp import NLPAnalysisResponse
from app.schemas.priority import PriorityScoreRequest
from app.services.priority import calculate_priority_score


class TestPriorityM38(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    # 1. Low-risk complaint
    def test_01_low_risk_complaint(self):
        payload = {
            "issue_category": "damaged_missing_road_sign",
            "cv_confidence": 0.35,
            "nlp_analysis": {
                "detected_language": "en",
                "issue_category": "damaged_missing_road_sign",
                "issue_confidence": 0.5,
                "issue_keywords": ["road sign"],
                "severity_signals": [],
                "risk_signals": [],
                "extracted_entities": [],
                "normalized_summary": "Road sign slightly tilted",
                "confidence": 0.5,
                "explanation": "Standard road sign maintenance",
            },
            "duplicate_analysis": {
                "classification": "unique",
                "similarity_score": 0.0,
                "issue_match": False,
                "reason": "No duplicates",
            },
            "location_context": {
                "road": None,
                "area": None,
            },
        }
        res = self.client.post("/api/v1/priority/score", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertLess(data["priority_score"], 40)
        self.assertEqual(data["priority_level"], "P4")
        self.assertEqual(data["risk_level"], "Low")

    # 2. High-risk manhole
    def test_02_high_risk_manhole(self):
        payload = {
            "issue_category": "open_damaged_manhole",
            "cv_confidence": 0.95,
            "nlp_analysis": {
                "detected_language": "en",
                "issue_category": "open_damaged_manhole",
                "issue_confidence": 0.95,
                "issue_keywords": ["manhole", "open"],
                "severity_signals": ["dangerous", "accident", "injury"],
                "risk_signals": ["fall hazard"],
                "extracted_entities": [],
                "normalized_summary": "Extremely dangerous open manhole",
                "confidence": 0.95,
                "explanation": "Critical danger",
            },
            "duplicate_analysis": {
                "classification": "duplicate",
                "similarity_score": 0.88,
                "matched_reference_id": "CVKI-20261011-MAN001",
                "issue_match": True,
                "reason": "Recurring nearby complaints",
            },
            "location_context": {
                "road": "Outer Ring Road Highway",
                "area": "Main Junction",
            },
            "authority_context": {
                "authority_status": "verified",
            },
        }
        res = self.client.post("/api/v1/priority/score", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["priority_score"], 80)
        self.assertEqual(data["priority_level"], "P1")
        self.assertEqual(data["risk_level"], "Critical")
        self.assertTrue(any("fall hazard" in r.lower() for r in data["reasons"]))

    # 3. Waterlogging with risk signals
    def test_03_waterlogging_with_risk_signals(self):
        payload = {
            "issue_category": "road_waterlogging",
            "cv_confidence": 0.88,
            "nlp_analysis": {
                "detected_language": "en",
                "issue_category": "road_waterlogging",
                "issue_confidence": 0.90,
                "issue_keywords": ["waterlogging", "flooding"],
                "severity_signals": ["severe flooding", "blocked road"],
                "risk_signals": ["vehicle damage risk"],
                "extracted_entities": [],
                "normalized_summary": "Severe waterlogging blocking traffic",
                "confidence": 0.9,
                "explanation": "Severe flooding",
            },
            "location_context": {
                "road": "Main Marg Highway Bypass",
            },
        }
        res = self.client.post("/api/v1/priority/score", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["priority_score"], 60)
        self.assertIn(data["priority_level"], ["P1", "P2"])

    # 4. Road sign issue
    def test_04_road_sign_issue(self):
        req = PriorityScoreRequest(
            issue_category="damaged_missing_road_sign",
            cv_confidence=0.75,
            nlp_analysis=None,
            duplicate_analysis=None,
            location_context=None,
            authority_context=None,
        )
        resp = calculate_priority_score(req)
        self.assertIn(resp.priority_level, ["P3", "P4"])
        self.assertTrue(any("damaged or missing road sign" in r.lower() for r in resp.reasons))

    # 5. Repeated complaint signal
    def test_05_repeated_complaint_signal(self):
        dup_yes = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                duplicate_analysis=DuplicateCheckResponse(
                    classification="duplicate",
                    similarity_score=0.9,
                    matched_reference_id="CVKI-20261011-DUP1",
                    issue_match=True,
                    reason="Duplicate nearby",
                ),
            )
        )
        dup_no = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                duplicate_analysis=DuplicateCheckResponse(
                    classification="unique",
                    similarity_score=0.0,
                    issue_match=False,
                    reason="Unique",
                ),
            )
        )
        self.assertGreater(dup_yes.priority_score, dup_no.priority_score)
        self.assertTrue(any("multiple" in r.lower() or "duplicate" in r.lower() for r in dup_yes.reasons))

    # 6. No duplicate information
    def test_06_no_duplicate_information(self):
        resp = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="road_waterlogging",
                duplicate_analysis=None,
            )
        )
        self.assertGreaterEqual(resp.priority_score, 0)
        self.assertLessEqual(resp.priority_score, 100)

    # 7. Low CV confidence
    def test_07_low_cv_confidence(self):
        resp = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                cv_confidence=0.30,
            )
        )
        self.assertIn("Low computer vision detection confidence", "".join(resp.evidence))

    # 8. High CV confidence
    def test_08_high_cv_confidence(self):
        resp_high = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                cv_confidence=0.95,
            )
        )
        resp_low = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                cv_confidence=0.30,
            )
        )
        self.assertGreater(resp_high.priority_score, resp_low.priority_score)
        self.assertTrue(any("high detection confidence" in r.lower() for r in resp_high.reasons))

    # 9. Missing location
    def test_09_missing_location(self):
        resp = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                location_context=None,
            )
        )
        self.assertGreaterEqual(resp.priority_score, 0)
        self.assertIn("Location context not supplied", "".join(resp.evidence))

    # 10. Missing authority
    def test_10_missing_authority(self):
        resp = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                authority_context=None,
            )
        )
        self.assertIn("Authority context not supplied", "".join(resp.evidence))

    # 11. Priority score 0–100
    def test_11_priority_score_range(self):
        for cat in ("open_damaged_manhole", "damaged_missing_road_sign", "road_waterlogging", "other_civic_issue"):
            resp = calculate_priority_score(
                PriorityScoreRequest(
                    issue_category=cat,
                    cv_confidence=0.8,
                )
            )
            self.assertGreaterEqual(resp.priority_score, 0)
            self.assertLessEqual(resp.priority_score, 100)

    # 12. Correct priority levels
    def test_12_correct_priority_levels(self):
        # P1: Critical (>= 80)
        p1_resp = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                cv_confidence=0.95,
                nlp_analysis=NLPAnalysisResponse(
                    detected_language="en",
                    issue_category="open_damaged_manhole",
                    issue_confidence=0.9,
                    issue_keywords=["manhole"],
                    severity_signals=["dangerous", "accident"],
                    risk_signals=["fall hazard"],
                    extracted_entities=[],
                    normalized_summary="Dangerous manhole",
                    confidence=0.9,
                    explanation="High risk",
                ),
                duplicate_analysis=DuplicateCheckResponse(
                    classification="duplicate",
                    similarity_score=0.9,
                    matched_reference_id="CVKI-1",
                    issue_match=True,
                    reason="Duplicate",
                ),
                location_context=ComplaintLocation(road="Expressway Flyover"),
            )
        )
        self.assertEqual(p1_resp.priority_level, "P1")
        self.assertEqual(p1_resp.risk_level, "Critical")

        # P4: Low (< 40)
        p4_resp = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="other_civic_issue",
                cv_confidence=0.2,
            )
        )
        self.assertEqual(p4_resp.priority_level, "P4")
        self.assertEqual(p4_resp.risk_level, "Low")

    # 13. Reasons correspond to actual evidence
    def test_13_reasons_correspond_to_actual_evidence(self):
        resp = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="road_waterlogging",
                nlp_analysis=NLPAnalysisResponse(
                    detected_language="en",
                    issue_category="road_waterlogging",
                    issue_confidence=0.8,
                    issue_keywords=["waterlogging"],
                    severity_signals=["blocked road"],
                    risk_signals=[],
                    extracted_entities=[],
                    normalized_summary="Waterlogged road",
                    confidence=0.8,
                    explanation="Road blocked",
                ),
            )
        )
        self.assertTrue(len(resp.reasons) > 0)
        self.assertTrue(any("waterlogging" in r.lower() for r in resp.reasons))
        self.assertTrue(any("blocked road" in r.lower() for r in resp.reasons))

    # 14. No protected attribute usage
    def test_14_no_protected_attribute_usage(self):
        # Verify schema and calculation contain zero fields for citizen identity, gender, religion, income
        fields = PriorityScoreRequest.model_fields.keys()
        for forbidden in ("user_id", "email", "name", "gender", "age", "religion", "caste", "income"):
            self.assertNotIn(forbidden, fields)

    # 15. Malformed request
    def test_15_malformed_request(self):
        # Missing required issue_category
        res = self.client.post("/api/v1/priority/score", json={})
        self.assertEqual(res.status_code, 422)

        # Invalid CV confidence > 1.0
        res2 = self.client.post("/api/v1/priority/score", json={"issue_category": "open_damaged_manhole", "cv_confidence": 1.5})
        self.assertEqual(res2.status_code, 422)

    def test_16_recurrence_adds_a_bounded_explainable_priority_signal(self):
        recurrence = RecurrenceAnalysis(
            recurrence_detected=True,
            recurrence_count=20,
            recurrence_explanation="Twenty prior cases in the configured window.",
        )
        response = calculate_priority_score(
            PriorityScoreRequest(issue_category="road_waterlogging"),
            recurrence_analysis=recurrence,
        )
        self.assertEqual(response.recurrence_score, 5)
        self.assertTrue(any("prior same-category" in reason for reason in response.reasons))
        self.assertTrue(any("recurrence signal (+5 pts" in item for item in response.evidence))

    def test_17_possible_duplicate_does_not_claim_recurrence_without_history_signal(self):
        response = calculate_priority_score(
            PriorityScoreRequest(
                issue_category="open_damaged_manhole",
                duplicate_analysis=DuplicateCheckResponse(
                    classification="possible_duplicate",
                    similarity_score=0.7,
                    matched_reference_id="CVKI-PRIOR",
                    issue_match=True,
                    reason="Similar report nearby.",
                ),
            )
        )
        self.assertEqual(response.recurrence_score, 0)
        self.assertTrue(any("recurrence is evaluated separately" in reason for reason in response.reasons))

    def test_18_public_priority_request_cannot_supply_recurrence_history(self):
        response = self.client.post(
            "/api/v1/priority/score",
            json={
                "issue_category": "road_waterlogging",
                "recurrence_analysis": {
                    "recurrence_detected": True,
                    "recurrence_count": 50,
                    "recurrence_window_days": 180,
                    "recurrence_explanation": "Client-provided claim.",
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recurrence_score"], 0)
        self.assertIn("Recurrence analysis not supplied", " ".join(response.json()["evidence"]))


if __name__ == "__main__":
    unittest.main()
