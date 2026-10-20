"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.1: Multimodal SPI & Standard Contracts Unit Tests

Validates framework-agnostic multimodal data contracts, epistemic boundaries,
mock provider lifecycle, provider resolution, security constraints, and PII sanitization.
"""

from datetime import datetime, timezone
import unittest

from pydantic import ValidationError

from app.services.cv.base_provider import (
    StandardBoundingBox,
    StandardDetection,
    StandardDetectionResult,
)
from app.services.multimodal import (
    AlignmentState,
    AmbiguityAssessment,
    AmbiguityState,
    CivicIntent,
    CivicIssueContext,
    EpistemicState,
    EvidenceAlignmentAssessment,
    ExtractedCivicEntity,
    InformationOrigin,
    IssueCategory,
    MockMultimodalProvider,
    MultimodalInferenceProvider,
    MultimodalInput,
    MultimodalLocationContext,
    MultimodalMessage,
    MultimodalProviderDescriptor,
    MultimodalProviderNotFoundError,
    MultimodalProviderResolver,
    MultimodalTaskType,
    StandardMultimodalResult,
    multimodal_provider_resolver,
    sanitize_multimodal_metadata,
    sanitize_text_pii,
)


class TestMultimodalContractsM91(unittest.TestCase):
    """Unit tests for M9.1 Standard Contracts, Security Constraints, and Epistemic Bounds."""

    def setUp(self):
        self.sample_cv_result = StandardDetectionResult(
            success=True,
            model_id="m1.13-yolov8n",
            model_version="1.13.0",
            total_detections=1,
            detections=[
                StandardDetection(
                    class_id=0,
                    class_name="open_damaged_manhole",
                    confidence=0.89,
                    bbox=StandardBoundingBox(x1=50, y1=50, x2=200, y2=200),
                )
            ],
            inference_duration_ms=88.5,
        )

    # 1. Valid input contract
    def test_valid_multimodal_input(self):
        input_data = MultimodalInput(
            request_id="REQ-2026-001",
            text="Open manhole cover on 100 Feet Road causing hazard.",
            language="en",
            evidence_reference_id="EV-102938",
            cv_result=self.sample_cv_result,
            civic_issue_context=CivicIssueContext(
                reported_class="open_damaged_manhole",
                severity="critical",
            ),
            location_context=MultimodalLocationContext(
                road_name="100 Feet Road",
                locality="Indiranagar",
                city="Bengaluru",
                latitude=12.9716,
                longitude=77.5946,
            ),
            origin=InformationOrigin.USER_PROVIDED,
            metadata={"source": "mobile_app"},
        )
        self.assertEqual(input_data.request_id, "REQ-2026-001")
        self.assertEqual(input_data.language, "en")
        self.assertEqual(input_data.origin, InformationOrigin.USER_PROVIDED)
        self.assertIsNotNone(input_data.cv_result)
        self.assertEqual(input_data.cv_result.total_detections, 1)

    # 2. Invalid input rejected (empty input without text, cv, or evidence)
    def test_empty_input_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            MultimodalInput(request_id="REQ-EMPTY")
        self.assertIn("MultimodalInput must contain at least one of", str(ctx.exception))

    # 3. Oversized text rejected (>5000 chars)
    def test_oversized_text_rejected(self):
        oversized = "A" * 5001
        with self.assertRaises(ValidationError) as ctx:
            MultimodalInput(
                request_id="REQ-OVERSIZE",
                text=oversized,
            )
        self.assertIn("String should have at most 5000 characters", str(ctx.exception))

    # 4. Malformed CV result rejected
    def test_malformed_cv_result_rejected(self):
        with self.assertRaises(ValidationError):
            MultimodalInput(
                request_id="REQ-MALFORMED-CV",
                cv_result={"invalid": "not_a_standard_cv_result"},  # type: ignore
            )

    # 5. Valid standard output
    def test_valid_standard_multimodal_result(self):
        result = StandardMultimodalResult(
            success=True,
            provider_id="mock_multimodal_provider",
            model_id="mock_civic_multimodal",
            model_version="0.1.0-mock",
            task=MultimodalTaskType.COMPLAINT_ANALYSIS,
            processing_time_ms=12.5,
            timestamp=datetime.now(timezone.utc),
            language="en",
            normalized_intent=CivicIntent.REPORT_ISSUE,
            issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            extracted_entities=[
                ExtractedCivicEntity(entity_name="Indiranagar", entity_type="locality")
            ],
            ambiguity_assessment=AmbiguityAssessment(
                state=AmbiguityState.CLEAR,
                requires_clarification=False,
            ),
            evidence_alignment=EvidenceAlignmentAssessment(
                state=AlignmentState.ALIGNED,
                matched_issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
            ),
            suggested_clarifications=[],
            explanation="Validated complaint report.",
            epistemic_state=EpistemicState.MODEL_OBSERVATION,
            metadata={"engine": "mock"},
        )
        self.assertTrue(result.success)
        self.assertEqual(result.epistemic_state, EpistemicState.MODEL_OBSERVATION)
        self.assertEqual(result.normalized_intent, CivicIntent.REPORT_ISSUE)
        self.assertEqual(result.issue_category, IssueCategory.OPEN_DAMAGED_MANHOLE)

    # 6. Invalid epistemic state rejected (cannot claim VERIFIED_EVIDENCE directly)
    def test_verified_evidence_state_rejected_from_model_output(self):
        with self.assertRaises(ValidationError) as ctx:
            StandardMultimodalResult(
                success=True,
                provider_id="mock_provider",
                model_id="mock_model",
                model_version="1.0.0",
                epistemic_state=EpistemicState.VERIFIED_EVIDENCE,
            )
        self.assertIn("StandardMultimodalResult cannot claim VERIFIED_EVIDENCE directly", str(ctx.exception))

    # 7. Ambiguity contract
    def test_ambiguity_contract(self):
        amb = AmbiguityAssessment(
            state=AmbiguityState.AMBIGUOUS,
            reasons=["Image shows dark scene without road markings", "Pit depth unclear"],
            missing_information=["exact_lane_location", "water_depth"],
            requires_clarification=True,
        )
        self.assertEqual(amb.state, AmbiguityState.AMBIGUOUS)
        self.assertTrue(amb.requires_clarification)
        self.assertEqual(len(amb.reasons), 2)
        self.assertEqual(len(amb.missing_information), 2)

    # 8. Evidence alignment contract
    def test_evidence_alignment_contract(self):
        alignment = EvidenceAlignmentAssessment(
            state=AlignmentState.CONFLICTING,
            matched_issue_category=None,
            conflicting_fields=["issue_class"],
            supporting_evidence=["GPS within municipal road corridor"],
            missing_evidence=["Visual waterlogging detection"],
            explanation="Citizen describes waterlogging but visual model detected open manhole.",
        )
        self.assertEqual(alignment.state, AlignmentState.CONFLICTING)
        self.assertEqual(alignment.conflicting_fields, ["issue_class"])
        self.assertIn("open manhole", alignment.explanation)

    # 9. Provider lifecycle
    def test_provider_lifecycle(self):
        provider = MockMultimodalProvider()
        desc = provider.descriptor
        self.assertEqual(desc.provider_id, "mock_multimodal_provider")
        self.assertFalse(provider.is_loaded)

        # Infer before initialize must raise
        with self.assertRaises(RuntimeError) as ctx:
            provider.infer(MultimodalInput(request_id="R-1", text="Test issue"))
        self.assertIn("not initialized", str(ctx.exception))

        # Initialize
        init_ok = provider.initialize()
        self.assertTrue(init_ok)
        self.assertTrue(provider.is_loaded)

        # Infer
        res = provider.infer(MultimodalInput(request_id="R-1", text="Test issue"))
        self.assertTrue(res.success)
        self.assertEqual(res.epistemic_state, EpistemicState.MODEL_OBSERVATION)

        # Shutdown
        provider.shutdown()
        self.assertFalse(provider.is_loaded)

    # 10. Mock provider deterministic behavior
    def test_mock_provider_deterministic_behavior(self):
        provider = MockMultimodalProvider()
        provider.initialize()

        inp = MultimodalInput(
            request_id="REQ-DETERMINISTIC",
            text="Dangerous open manhole near MG Road Metro",
            language="en",
            cv_result=self.sample_cv_result,
            location_context=MultimodalLocationContext(
                road_name="MG Road",
                city="Bengaluru",
            ),
        )

        res1 = provider.infer(inp)
        res2 = provider.infer(inp)

        self.assertEqual(res1.issue_category, IssueCategory.OPEN_DAMAGED_MANHOLE)
        self.assertEqual(res2.issue_category, IssueCategory.OPEN_DAMAGED_MANHOLE)
        self.assertEqual(res1.normalized_intent, res2.normalized_intent)
        self.assertEqual(len(res1.extracted_entities), len(res2.extracted_entities))
        self.assertEqual(res1.extracted_entities[0].entity_name, "MG Road")

    # 11. Unknown provider rejected by resolver
    def test_unknown_provider_rejected(self):
        resolver = MultimodalProviderResolver()
        with self.assertRaises(MultimodalProviderNotFoundError) as ctx:
            resolver.resolve_provider("non_existent_arbitrary_provider")
        self.assertIn("not an approved server-side provider", str(ctx.exception))

    # 12. Arbitrary filesystem path rejected in evidence reference
    def test_arbitrary_filesystem_path_rejected(self):
        forbidden_references = [
            "../../etc/passwd",
            "..\\windows\\system32",
            "/var/data/image.jpg",
            "C:\\Users\\secret.png",
            "null\x00byte",
        ]
        for ref in forbidden_references:
            with self.assertRaises(ValidationError) as ctx:
                MultimodalInput(
                    request_id="REQ-SEC-PATH",
                    text="Some text",
                    evidence_reference_id=ref,
                )
            self.assertIn("path traversal", str(ctx.exception))

    # 13. Arbitrary URL rejected in evidence reference
    def test_arbitrary_url_rejected(self):
        forbidden_urls = [
            "http://malicious.com/exploit.jpg",
            "https://evil.site/payload",
            "file:///etc/hosts",
            "ftp://anonymous@server/data",
        ]
        for url in forbidden_urls:
            with self.assertRaises(ValidationError) as ctx:
                MultimodalInput(
                    request_id="REQ-SEC-URL",
                    text="Some text",
                    evidence_reference_id=url,
                )
            self.assertIn("cannot be an external network URL", str(ctx.exception))

    # 14. PII sanitization (emails and phone numbers redacted)
    def test_pii_sanitization(self):
        dirty_text = (
            "Contact me at rahul.verma@example.com or call +91-9876543210 about the open manhole. "
            "Alternate phone: 9123456789 or 555-123-4567."
        )
        clean = sanitize_text_pii(dirty_text)
        self.assertNotIn("rahul.verma@example.com", clean)
        self.assertNotIn("9876543210", clean)
        self.assertNotIn("9123456789", clean)
        self.assertNotIn("555-123-4567", clean)
        self.assertIn("[EMAIL_REDACTED]", clean)
        self.assertIn("[PHONE_REDACTED]", clean)
        self.assertIn("about the open manhole", clean)

        # Metadata credential scrubbing
        dirty_meta = {
            "api_key": "super_secret_key",
            "auth_token": "bearer xyz",
            "user_password": "plain_password",
            "device": "android",
            "nested": {"session_cookie": "sess_123", "zoom": 15},
        }
        clean_meta = sanitize_multimodal_metadata(dirty_meta)
        self.assertEqual(clean_meta["api_key"], "[REDACTED]")
        self.assertEqual(clean_meta["auth_token"], "[REDACTED]")
        self.assertEqual(clean_meta["user_password"], "[REDACTED]")
        self.assertEqual(clean_meta["device"], "android")
        self.assertEqual(clean_meta["nested"]["session_cookie"], "[REDACTED]")
        self.assertEqual(clean_meta["nested"]["zoom"], 15)

    # 15. Provider metadata validation & sensitive key rejection in MultimodalInput
    def test_sensitive_metadata_keys_rejected_in_multimodal_input(self):
        with self.assertRaises(ValidationError) as ctx:
            MultimodalInput(
                request_id="REQ-METADATA-SEC",
                text="Civic hazard description",
                metadata={"jwt_token": "eyJhbGciOi..."},
            )
        self.assertIn("prohibited sensitive credential pattern", str(ctx.exception))

    # 16. Message role validation in conversational context
    def test_conversational_message_role_validation(self):
        msg = MultimodalMessage(role="citizen", content="Yes, the water is knee-deep.")
        self.assertEqual(msg.role, "citizen")

        with self.assertRaises(ValidationError):
            MultimodalMessage(role="hacker_admin", content="Invalid role")


if __name__ == "__main__":
    unittest.main()
