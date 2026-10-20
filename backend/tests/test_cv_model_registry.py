"""
CVKI - Civic Vision & Knowledge Intelligence
Module 8.3: Computer Vision Model Registry Unit Tests
"""

from datetime import datetime, timezone
import unittest

from app.services.cv.base_provider import (
    ModelDescriptor,
    ModelFramework,
    ModelLifecycleStatus,
    ModelTaskType,
)
from app.services.cv.model_registry import (
    DuplicateModelError,
    InvalidLifecycleTransitionError,
    InvalidModelHashError,
    InvalidModelReferenceError,
    InvalidModelVersionError,
    ModelEvaluationMetadata,
    ModelNotFoundError,
    ModelRegistry,
    SplitEvaluationMetrics,
    model_registry,
    resolve_safe_model_reference,
    validate_sha256_format,
)
from app.services.computer_vision import cv_model_service


class TestCVModelRegistry(unittest.TestCase):
    """
    Tests for Module 8.3 CV Model Registry & Lifecycle Management.
    Verifies model identity, state transitions, cryptographic integrity, and security boundaries.
    """

    def setUp(self):
        # Reset the shared registry to baseline state before each test
        model_registry.reset()

    def test_01_valid_model_registration(self):
        """Verify registering a valid model descriptor succeeds and stores it in REGISTERED state."""
        desc = ModelDescriptor(
            model_id="test-model-yolo",
            model_name="Experimental Road Hazard Detector",
            model_version="2.0.0-rc1",
            provider_id="yolov8_provider",
            framework=ModelFramework.ULTRALYTICS_YOLO,
            task_type=ModelTaskType.OBJECT_DETECTION,
            sha256_hash="a" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
            supported_classes={0: "pothole", 1: "open_manhole"},
            default_confidence_threshold=0.35,
        )
        registered = model_registry.register_model(desc)
        self.assertEqual(registered.model_id, "test-model-yolo")
        self.assertEqual(registered.model_version, "2.0.0-rc1")
        self.assertEqual(registered.lifecycle_status, ModelLifecycleStatus.REGISTERED)
        self.assertIsNone(registered.activated_at)
        self.assertIsNotNone(registered.created_at)

    def test_02_duplicate_model_identity_rejected(self):
        """Verify registering an existing model_id raises DuplicateModelError."""
        desc = ModelDescriptor(
            model_id="duplicate-model",
            model_name="Duplicate Model",
            model_version="1.0.0",
            sha256_hash="b" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
        )
        model_registry.register_model(desc)
        with self.assertRaises(DuplicateModelError):
            model_registry.register_model(desc)

    def test_03_invalid_model_version_rejected(self):
        """Verify invalid or malformed model versions raise InvalidModelVersionError."""
        for bad_ver in ["", "   ", "version two", "v1..0", "alpha!@#"]:
            desc = ModelDescriptor(
                model_id=f"test-bad-ver-{hash(bad_ver)}",
                model_name="Bad Version Model",
                model_version=bad_ver,
                sha256_hash="c" * 64,
                model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
            )
            with self.assertRaises(InvalidModelVersionError):
                model_registry.register_model(desc)

    def test_04_invalid_sha256_rejected(self):
        """Verify malformed SHA-256 hashes raise InvalidModelHashError."""
        for bad_hash in ["short", "z" * 64, "12345", "a" * 63, "a" * 65]:
            desc = ModelDescriptor(
                model_id=f"test-bad-hash-{hash(bad_hash)}",
                model_name="Bad Hash Model",
                model_version="1.0.0",
                sha256_hash=bad_hash,
                model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
            )
            with self.assertRaises(InvalidModelHashError):
                model_registry.register_model(desc)

    def test_05_model_retrieval(self):
        """Verify retrieving an existing model returns its descriptor and unknown ID raises ModelNotFoundError."""
        model = model_registry.get_model("m1.13-yolov8n")
        self.assertEqual(model.model_id, "m1.13-yolov8n")
        self.assertEqual(model.model_version, "1.13")

        with self.assertRaises(ModelNotFoundError):
            model_registry.get_model("non-existent-model-xyz")

    def test_06_model_listing(self):
        """Verify list_models returns all models and supports status filtering."""
        all_models = model_registry.list_models()
        self.assertGreaterEqual(len(all_models), 1)
        self.assertEqual(all_models[0].model_id, "m1.13-yolov8n")

        # Filter by active
        active_models = model_registry.list_models(status=ModelLifecycleStatus.ACTIVE)
        self.assertEqual(len(active_models), 1)
        self.assertEqual(active_models[0].model_id, "m1.13-yolov8n")

        # Filter by registered
        registered_models = model_registry.list_models(status=ModelLifecycleStatus.REGISTERED)
        self.assertEqual(len(registered_models), 0)

    def test_07_lifecycle_transition_registered_to_validating(self):
        """Verify valid transition from REGISTERED to VALIDATING."""
        desc = ModelDescriptor(
            model_id="trans-model-1",
            model_name="Transition Model 1",
            model_version="1.0.0",
            sha256_hash="d" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
        )
        model_registry.register_model(desc)
        updated = model_registry.transition_model_status("trans-model-1", ModelLifecycleStatus.VALIDATING)
        self.assertEqual(updated.lifecycle_status, ModelLifecycleStatus.VALIDATING)

    def test_08_lifecycle_transition_validating_to_evaluated(self):
        """Verify valid transition sequence: REGISTERED -> VALIDATING -> EVALUATED."""
        desc = ModelDescriptor(
            model_id="trans-model-2",
            model_name="Transition Model 2",
            model_version="1.0.0",
            sha256_hash="e" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
        )
        model_registry.register_model(desc)
        model_registry.transition_model_status("trans-model-2", ModelLifecycleStatus.VALIDATING)
        evaluated = model_registry.transition_model_status("trans-model-2", ModelLifecycleStatus.EVALUATED)
        self.assertEqual(evaluated.lifecycle_status, ModelLifecycleStatus.EVALUATED)

    def test_09_lifecycle_transition_evaluated_to_active(self):
        """Verify valid transition sequence: REGISTERED -> VALIDATING -> EVALUATED -> ACTIVE."""
        desc = ModelDescriptor(
            model_id="trans-model-3",
            model_name="Transition Model 3",
            model_version="1.0.0",
            sha256_hash="f" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
        )
        model_registry.register_model(desc)
        model_registry.transition_model_status("trans-model-3", ModelLifecycleStatus.VALIDATING)
        model_registry.transition_model_status("trans-model-3", ModelLifecycleStatus.EVALUATED)
        active = model_registry.activate_model("trans-model-3")
        self.assertEqual(active.lifecycle_status, ModelLifecycleStatus.ACTIVE)
        self.assertIsNotNone(active.activated_at)
        self.assertEqual(model_registry.get_active_model().model_id, "trans-model-3")

    def test_10_lifecycle_transition_active_to_retired(self):
        """Verify retiring an active model transitions it to RETIRED and sets retired_at."""
        retired = model_registry.retire_model("m1.13-yolov8n")
        self.assertEqual(retired.lifecycle_status, ModelLifecycleStatus.RETIRED)
        self.assertIsNotNone(retired.retired_at)
        self.assertIsNone(model_registry.get_active_model())

    def test_11_invalid_lifecycle_transitions_rejected(self):
        """Verify arbitrary state jumps raise InvalidLifecycleTransitionError."""
        desc = ModelDescriptor(
            model_id="illegal-trans-model",
            model_name="Illegal Transition Model",
            model_version="1.0.0",
            sha256_hash="0" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
        )
        model_registry.register_model(desc)
        # Attempt direct jump REGISTERED -> ACTIVE (must be EVALUATED first)
        with self.assertRaises(InvalidLifecycleTransitionError):
            model_registry.transition_model_status("illegal-trans-model", ModelLifecycleStatus.ACTIVE)

        # Attempt direct jump REGISTERED -> RETIRED
        with self.assertRaises(InvalidLifecycleTransitionError):
            model_registry.transition_model_status("illegal-trans-model", ModelLifecycleStatus.RETIRED)

    def test_12_registering_model_does_not_automatically_activate(self):
        """Verify registering a model always places it in REGISTERED status regardless of input descriptor."""
        desc = ModelDescriptor(
            model_id="eager-model",
            model_name="Eager Model",
            model_version="1.0.0",
            sha256_hash="1" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
            lifecycle_status=ModelLifecycleStatus.ACTIVE,  # Attempting pre-mature active request
        )
        registered = model_registry.register_model(desc)
        self.assertEqual(registered.lifecycle_status, ModelLifecycleStatus.REGISTERED)
        self.assertNotEqual(model_registry.get_active_model().model_id, "eager-model")
        self.assertEqual(model_registry.get_active_model().model_id, "m1.13-yolov8n")

    def test_13_only_explicit_activation_can_produce_active_state(self):
        """Verify active state requires explicit progression through the lifecycle state machine."""
        desc = ModelDescriptor(
            model_id="promoted-model",
            model_name="Promoted Model",
            model_version="1.0.0",
            sha256_hash="2" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
        )
        model_registry.register_model(desc)
        model_registry.transition_model_status("promoted-model", ModelLifecycleStatus.VALIDATING)
        model_registry.transition_model_status("promoted-model", ModelLifecycleStatus.EVALUATED)
        active = model_registry.activate_model("promoted-model")
        self.assertEqual(active.lifecycle_status, ModelLifecycleStatus.ACTIVE)

    def test_14_m1_13_metadata_has_exact_sha(self):
        """Verify M1.13 baseline registration contains exact frozen SHA-256 hash."""
        m1_13 = model_registry.get_model("m1.13-yolov8n")
        expected_sha = "602160d4851e0d79c34cb23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3"
        self.assertEqual(m1_13.sha256_hash, expected_sha)
        self.assertEqual(m1_13.model_version, "1.13")
        self.assertEqual(m1_13.lifecycle_status, ModelLifecycleStatus.ACTIVE)

        # Cryptographically verify the physical best.pt weights file against registered hash
        valid, msg = model_registry.verify_model_integrity("m1.13-yolov8n")
        self.assertTrue(valid, msg)
        self.assertIn("verified", msg.lower())

    def test_15_m1_13_registration_does_not_alter_production_runtime(self):
        """Verify registry operation does not modify or re-bind production YOLOModelService."""
        # 1. Verify YOLOModelService remains the production service class
        self.assertEqual(cv_model_service.__class__.__name__, "YOLOModelService")
        self.assertEqual(cv_model_service._model_name, "yolov8n")
        self.assertEqual(cv_model_service._model_version, "M1.13-yolov8n")

        # 2. Verify cv_model_service is independent of model_registry
        self.assertNotIn("model_registry", cv_model_service.__dict__)

        # 3. Verify load_model operates independently on the production weights path
        loaded = cv_model_service.load_model()
        self.assertTrue(loaded)
        self.assertTrue(cv_model_service.is_loaded)
        status = cv_model_service.get_model_status()
        self.assertTrue(status["loaded"])
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["model_version"], "M1.13-yolov8n")

    def test_16_model_reference_path_traversal_rejected(self):
        """Verify model references cannot break outside project root boundaries."""
        for bad_ref in [
            "../secret.pt",
            "../../etc/passwd",
            "C:\\Windows\\System32\\calc.exe",
            "ai/../../outside.pt",
            "null\x00byte.pt",
        ]:
            with self.assertRaises(InvalidModelReferenceError):
                resolve_safe_model_reference(bad_ref)

    def test_17_evaluation_metrics_remain_optional(self):
        """Verify ModelDescriptor instantiates cleanly with evaluation_metadata omitted."""
        desc = ModelDescriptor(
            model_id="no-eval-model",
            model_name="Un-evaluated Model",
            model_version="1.0.0",
            sha256_hash="3" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
            evaluation_metadata=None,
        )
        registered = model_registry.register_model(desc)
        self.assertIsNone(registered.evaluation_metadata)

    def test_18_missing_evaluation_data_does_not_become_zero(self):
        """Verify missing metrics remain None rather than fabricating 0.0 values."""
        split_metrics = SplitEvaluationMetrics(split_name="test_split", precision=0.85)
        self.assertEqual(split_metrics.precision, 0.85)
        self.assertIsNone(split_metrics.recall)
        self.assertIsNone(split_metrics.map50)
        self.assertIsNone(split_metrics.map50_95)

    def test_19_duplicate_activation_behavior_is_controlled(self):
        """Verify activating Model B automatically retires the previously active Model A."""
        # Baseline M1.13 is active initially
        self.assertEqual(model_registry.get_active_model().model_id, "m1.13-yolov8n")

        desc = ModelDescriptor(
            model_id="next-gen-model",
            model_name="Next Gen Detector",
            model_version="2.0.0",
            sha256_hash="4" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
        )
        model_registry.register_model(desc)
        model_registry.transition_model_status("next-gen-model", ModelLifecycleStatus.VALIDATING)
        model_registry.transition_model_status("next-gen-model", ModelLifecycleStatus.EVALUATED)
        model_registry.activate_model("next-gen-model")

        # Now next-gen-model is active
        self.assertEqual(model_registry.get_active_model().model_id, "next-gen-model")

        # M1.13 has been automatically transitioned to RETIRED
        old_m1_13 = model_registry.get_model("m1.13-yolov8n")
        self.assertEqual(old_m1_13.lifecycle_status, ModelLifecycleStatus.RETIRED)
        self.assertIsNotNone(old_m1_13.retired_at)

        # Rollback: activating M1.13 from RETIRED should succeed and retire next-gen-model
        model_registry.activate_model("m1.13-yolov8n")
        self.assertEqual(model_registry.get_active_model().model_id, "m1.13-yolov8n")
        self.assertEqual(
            model_registry.get_model("next-gen-model").lifecycle_status,
            ModelLifecycleStatus.RETIRED,
        )

    def test_20_disabled_model_cannot_transition(self):
        """Verify DISABLED is a terminal state that cannot transition to ACTIVE or any other state."""
        desc = ModelDescriptor(
            model_id="faulty-model",
            model_name="Faulty Model",
            model_version="1.0.0",
            sha256_hash="5" * 64,
            model_reference="ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt",
        )
        model_registry.register_model(desc)
        model_registry.disable_model("faulty-model")
        self.assertEqual(
            model_registry.get_model("faulty-model").lifecycle_status,
            ModelLifecycleStatus.DISABLED,
        )

        with self.assertRaises(InvalidLifecycleTransitionError):
            model_registry.transition_model_status("faulty-model", ModelLifecycleStatus.ACTIVE)

        with self.assertRaises(InvalidLifecycleTransitionError):
            model_registry.transition_model_status("faulty-model", ModelLifecycleStatus.VALIDATING)


if __name__ == "__main__":
    unittest.main()
