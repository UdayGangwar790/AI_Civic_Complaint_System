import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.nlp import NLPAnalysisRequest
from app.services.nlp import analyze_complaint_text


class TestNLPM36(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    # 1. English complaint
    def test_01_english_complaint(self):
        payload = {
            "title": "Open manhole on MG Road",
            "description": "There is a dangerous open manhole on MG Road near Metro station that could cause severe injury.",
            "language": "en",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["detected_language"], "en")
        self.assertEqual(data["issue_category"], "open_damaged_manhole")
        self.assertIn("dangerous", data["severity_signals"])
        self.assertIn("injury", data["severity_signals"])

    # 2. Hindi complaint
    def test_02_hindi_complaint(self):
        payload = {
            "title": "सड़क पर भारी जलभराव",
            "description": "रिंग रोड पर बहुत गंभीर जलभराव है, पानी भरा हुआ है और रास्ता बंद हो गया है।",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["detected_language"], "hi")
        self.assertEqual(data["issue_category"], "road_waterlogging")
        self.assertIn("blocked road", data["severity_signals"])

    # 3. Hinglish complaint
    def test_03_hinglish_complaint(self):
        payload = {
            "title": "Khula manhole dangerous hai",
            "description": "Sector 14 main road pe manhole ka dhakkan toota hai, bahut khatarnak accident ho sakta hai.",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["detected_language"], "hinglish")
        self.assertEqual(data["issue_category"], "open_damaged_manhole")
        self.assertIn("dangerous", data["severity_signals"])
        self.assertIn("accident", data["severity_signals"])

    # 4. Empty description
    def test_04_empty_description(self):
        payload = {
            "title": "",
            "description": "",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["confidence"], 0.0)
        self.assertEqual(data["issue_category"], "other_civic_issue")
        self.assertEqual(len(data["issue_keywords"]), 0)
        self.assertEqual(len(data["extracted_entities"]), 0)

    # 5. Unknown civic issue
    def test_05_unknown_civic_issue(self):
        payload = {
            "title": "Street light flickering",
            "description": "The street light in our neighborhood is flickering intermittently and needs repair.",
            "language": "en",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["issue_category"], "other_civic_issue")
        self.assertEqual(len(data["issue_keywords"]), 0)

    # 6. Manhole complaint
    def test_06_manhole_complaint(self):
        payload = {
            "title": "Uncovered drain pit",
            "description": "The sewer inspection chamber lid is cracked and open on Link Road.",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["issue_category"], "open_damaged_manhole")
        self.assertTrue(any(kw in ["sewer", "chamber", "open"] for kw in data["issue_keywords"]))

    # 7. Road-sign complaint
    def test_07_road_sign_complaint(self):
        payload = {
            "title": "Broken direction signboard",
            "description": "Traffic sign board indicating speed limit has fallen down near Metro station.",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["issue_category"], "damaged_missing_road_sign")
        self.assertTrue(len(data["issue_keywords"]) > 0)

    # 8. Waterlogging complaint
    def test_08_waterlogging_complaint(self):
        payload = {
            "title": "Massive puddle water stagnation",
            "description": "Rainwater stagnation and waterlogging near Koramangala junction.",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["issue_category"], "road_waterlogging")
        self.assertTrue(any(kw in ["waterlogging", "rainwater", "puddle", "water stagnation"] for kw in data["issue_keywords"]))

    # 9. Keyword extraction
    def test_09_keyword_extraction(self):
        req = NLPAnalysisRequest(
            title="Gutter cover broken",
            description="Inspection chamber and sewer drain cover completely broken.",
            language="en",
        )
        resp = analyze_complaint_text(req)
        self.assertIn("open_damaged_manhole", resp.issue_category)
        self.assertTrue(len(resp.issue_keywords) >= 2)

    # 10. Risk signal extraction
    def test_10_risk_signal_extraction(self):
        req = NLPAnalysisRequest(
            title="Accident hazard",
            description="Unlit area at night, deep open pit, someone may fall down and get injured.",
            language="en",
        )
        resp = analyze_complaint_text(req)
        self.assertIn("fall hazard", resp.risk_signals)
        self.assertIn("injury", resp.severity_signals)
        self.assertIn("deep/open", resp.severity_signals)
        self.assertIn("night visibility issue", resp.severity_signals)

    # 11. Entity extraction
    def test_11_entity_extraction(self):
        req = NLPAnalysisRequest(
            title="Hazard on Brigade Road",
            description="Near Metro station, Brigade Road in Bengaluru Karnataka, Ward 45.",
            language="en",
        )
        resp = analyze_complaint_text(req)
        entity_types = [e.type for e in resp.extracted_entities]
        entity_names = [e.name for e in resp.extracted_entities]
        self.assertIn("road", entity_types)
        self.assertIn("landmark", entity_types)
        self.assertIn("ward", entity_types)
        self.assertIn("city", entity_types)
        self.assertTrue(all(e.source == "text" for e in resp.extracted_entities))

    # 12. No fabricated entities
    def test_12_no_fabricated_entities(self):
        req = NLPAnalysisRequest(
            title="Issue with infrastructure",
            description="The problem is really bad and needs immediate attention from authorities.",
            language="en",
        )
        resp = analyze_complaint_text(req)
        self.assertEqual(len(resp.extracted_entities), 0)

    # 13. Explicit language selection
    def test_13_explicit_language_selection(self):
        payload = {
            "title": "Open drain",
            "description": "Very dangerous condition.",
            "language": "hi",  # Citizen explicitly prefers Hindi channel
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["detected_language"], "hi")

    # 14. Confidence range
    def test_14_confidence_range(self):
        payload = {
            "title": "Pothole problem",
            "description": "Road has damage.",
        }
        res = self.client.post("/api/v1/nlp/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        conf = res.json()["confidence"]
        issue_conf = res.json()["issue_confidence"]
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)
        self.assertGreaterEqual(issue_conf, 0.0)
        self.assertLessEqual(issue_conf, 1.0)

    # 15. Malformed request
    def test_15_malformed_request(self):
        # Invalid language value
        res = self.client.post("/api/v1/nlp/analyze", json={"language": "invalid_lang_code"})
        self.assertEqual(res.status_code, 422)

    # 16. Existing complaint API regression
    def test_16_existing_complaint_api_regression(self):
        draft_payload = {
            "detection": {
                "class_name": "open_damaged_manhole",
                "confidence": 0.89,
            },
            "location": {
                "road": "MG Road",
                "city": "Bengaluru",
                "latitude": 12.9716,
                "longitude": 77.5946,
            },
            "language": "en",
        }
        res = self.client.post("/api/v1/complaint/draft", json=draft_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["issue_category"], "open_damaged_manhole")
        self.assertIn("MG Road", data["description"])


if __name__ == "__main__":
    unittest.main()
