"""
CVKI M7.1 Government Integration Service.
Orchestrates government adapters, lifecycle state machine, idempotency,
reconciliation, provenance, knowledge graph, and audit logging.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import inspect
import json
import logging
from threading import Lock
from typing import Any, Optional
import uuid

from app.core.config import settings
from app.core.database import (
    GOVERNMENT_SUBMISSIONS_COLLECTION,
    get_database,
)
from app.schemas.complaint_case import ComplaintCase
from app.schemas.government_integration import (
    GovernmentIntegrationDefinition,
    GovernmentStatusSyncResult,
    GovernmentSubmissionRecord,
    GovernmentSubmissionResponse,
    GovernmentSubmissionSummary,
    IntegrationState,
    NormalizedGovernmentStatus,
    ReconciliationResult,
    SubmissionLifecycleState,
)
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
)
from app.services.audit import AuditService
from app.services.government_adapter import (
    GovernmentIntegrationAdapter,
    MockGovernmentAdapter,
)
from app.services.government_registry import government_registry
from app.services.government_state_machine import SubmissionStateMachine

logger = logging.getLogger("cvki.government_integration")

NOT_CONFIGURED_NOTICE = (
    "Government portal integration is not configured. CVKI has prepared the structured "
    "complaint package but has not submitted it to a government system."
)


class GovernmentSubmissionRepository(ABC):
    @abstractmethod
    def save(self, record: GovernmentSubmissionRecord) -> GovernmentSubmissionRecord:
        pass

    @abstractmethod
    def get_by_id(self, submission_id: str) -> Optional[GovernmentSubmissionRecord]:
        pass

    @abstractmethod
    def find_by_case(self, case_reference_id: str) -> list[GovernmentSubmissionRecord]:
        pass

    @abstractmethod
    def find_active_submission(self, case_reference_id: str, integration_id: str) -> Optional[GovernmentSubmissionRecord]:
        pass

    @abstractmethod
    def list_submissions(self, limit: int = 50) -> list[GovernmentSubmissionRecord]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryGovernmentSubmissionRepository(GovernmentSubmissionRepository):
    def __init__(self):
        self._records: dict[str, GovernmentSubmissionRecord] = {}
        self._lock = Lock()

    def save(self, record: GovernmentSubmissionRecord) -> GovernmentSubmissionRecord:
        with self._lock:
            self._records[record.submission_id] = record.model_copy(deep=True)
        return record

    def get_by_id(self, submission_id: str) -> Optional[GovernmentSubmissionRecord]:
        with self._lock:
            rec = self._records.get(submission_id)
            return rec.model_copy(deep=True) if rec else None

    def find_by_case(self, case_reference_id: str) -> list[GovernmentSubmissionRecord]:
        with self._lock:
            return [
                r.model_copy(deep=True)
                for r in self._records.values()
                if r.case_reference_id == case_reference_id
            ]

    def find_active_submission(self, case_reference_id: str, integration_id: str) -> Optional[GovernmentSubmissionRecord]:
        with self._lock:
            for r in self._records.values():
                if r.case_reference_id == case_reference_id and r.integration_id == integration_id:
                    if r.submission_state in {
                        SubmissionLifecycleState.SUBMITTING,
                        SubmissionLifecycleState.SUBMITTED,
                        SubmissionLifecycleState.UNKNOWN_OUTCOME,
                        SubmissionLifecycleState.STATUS_SYNCING,
                    }:
                        return r.model_copy(deep=True)
        return None

    def list_submissions(self, limit: int = 50) -> list[GovernmentSubmissionRecord]:
        with self._lock:
            sorted_recs = sorted(
                self._records.values(),
                key=lambda x: x.created_at,
                reverse=True,
            )
            return [r.model_copy(deep=True) for r in sorted_recs[:limit]]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


class MongoGovernmentSubmissionRepository(GovernmentSubmissionRepository):
    def __init__(self):
        self._fallback = InMemoryGovernmentSubmissionRepository()

    def save(self, record: GovernmentSubmissionRecord) -> GovernmentSubmissionRecord:
        self._fallback.save(record)
        db = get_database()
        if db is not None:
            try:
                db.sync_command(
                    lambda: db.delegate[GOVERNMENT_SUBMISSIONS_COLLECTION].replace_one(
                        {"submission_id": record.submission_id},
                        record.model_dump(),
                        upsert=True,
                    )
                )
            except Exception as exc:
                logger.warning("MongoDB government submission save failed, fallback active: %s", exc)
        return record

    def get_by_id(self, submission_id: str) -> Optional[GovernmentSubmissionRecord]:
        db = get_database()
        if db is not None:
            try:
                doc = db.sync_command(
                    lambda: db.delegate[GOVERNMENT_SUBMISSIONS_COLLECTION].find_one(
                        {"submission_id": submission_id}
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return GovernmentSubmissionRecord(**doc)
            except Exception as exc:
                logger.warning("MongoDB get submission failed: %s", exc)
        return self._fallback.get_by_id(submission_id)

    def find_by_case(self, case_reference_id: str) -> list[GovernmentSubmissionRecord]:
        db = get_database()
        if db is not None:
            try:
                cursor = db.sync_command(
                    lambda: list(
                        db.delegate[GOVERNMENT_SUBMISSIONS_COLLECTION].find(
                            {"case_reference_id": case_reference_id}
                        ).sort("created_at", -1)
                    )
                )
                recs = []
                for doc in cursor:
                    doc.pop("_id", None)
                    recs.append(GovernmentSubmissionRecord(**doc))
                if recs:
                    return recs
            except Exception as exc:
                logger.warning("MongoDB find submissions by case failed: %s", exc)
        return self._fallback.find_by_case(case_reference_id)

    def find_active_submission(self, case_reference_id: str, integration_id: str) -> Optional[GovernmentSubmissionRecord]:
        active_states = [
            SubmissionLifecycleState.SUBMITTING.value,
            SubmissionLifecycleState.SUBMITTED.value,
            SubmissionLifecycleState.UNKNOWN_OUTCOME.value,
            SubmissionLifecycleState.STATUS_SYNCING.value,
        ]
        db = get_database()
        if db is not None:
            try:
                doc = db.sync_command(
                    lambda: db.delegate[GOVERNMENT_SUBMISSIONS_COLLECTION].find_one(
                        {
                            "case_reference_id": case_reference_id,
                            "integration_id": integration_id,
                            "submission_state": {"$in": active_states},
                        }
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return GovernmentSubmissionRecord(**doc)
            except Exception as exc:
                logger.warning("MongoDB find active submission failed: %s", exc)
        return self._fallback.find_active_submission(case_reference_id, integration_id)

    def list_submissions(self, limit: int = 50) -> list[GovernmentSubmissionRecord]:
        db = get_database()
        if db is not None:
            try:
                cursor = db.sync_command(
                    lambda: list(
                        db.delegate[GOVERNMENT_SUBMISSIONS_COLLECTION].find()
                        .sort("created_at", -1)
                        .limit(limit)
                    )
                )
                recs = []
                for doc in cursor:
                    doc.pop("_id", None)
                    recs.append(GovernmentSubmissionRecord(**doc))
                if recs:
                    return recs
            except Exception as exc:
                logger.warning("MongoDB list submissions failed: %s", exc)
        return self._fallback.list_submissions(limit)

    def clear(self) -> None:
        self._fallback.clear()
        db = get_database()
        if db is not None:
            try:
                db.sync_command(lambda: db.delegate[GOVERNMENT_SUBMISSIONS_COLLECTION].delete_many({}))
            except Exception as exc:
                logger.warning("MongoDB clear submissions failed: %s", exc)


class GovernmentIntegrationService:
    def __init__(self, repository: Optional[GovernmentSubmissionRepository] = None):
        self.repository = repository or MongoGovernmentSubmissionRepository()

    def get_submission_summary(self, case: ComplaintCase) -> GovernmentSubmissionSummary:
        """
        Builds safe summary of government submission state for citizen or authority display.
        Enforces explicit NOT_CONFIGURED wording when no active integration exists.
        """
        # 1. Resolve identified authority from case
        auth_name = None
        if case.authority:
            if case.authority.maintenance_authority:
                auth_name = case.authority.maintenance_authority.name
            elif case.authority.road_owner:
                auth_name = case.authority.road_owner.name

        # 2. Find any active or historical submission records for this case
        subs = self.repository.find_by_case(case.reference_id)
        latest_sub = subs[0] if subs else None

        # 3. Lookup registered integration
        integration: Optional[GovernmentIntegrationDefinition] = None
        if latest_sub:
            integration = government_registry.get_definition(latest_sub.integration_id)
        if not integration and auth_name:
            integration = government_registry.find_integration_for_authority(auth_name)

        if not integration:
            # Default unconfigured placeholder
            return GovernmentSubmissionSummary(
                case_reference_id=case.reference_id,
                integration_id="not_configured",
                integration_name="Unconfigured Authority Portal",
                authority=auth_name or "Unassigned Public Authority",
                integration_state=IntegrationState.NOT_CONFIGURED,
                submission_state=latest_sub.submission_state if latest_sub else SubmissionLifecycleState.READY,
                external_reference_id=latest_sub.external_reference_id if latest_sub else None,
                external_status=latest_sub.external_status if latest_sub else None,
                normalized_status=latest_sub.normalized_status if latest_sub else None,
                external_case_url=latest_sub.external_case_url if latest_sub else None,
                submitted_at=latest_sub.submitted_at if latest_sub else None,
                last_status_sync_at=latest_sub.last_status_sync_at if latest_sub else None,
                next_status_sync_at=latest_sub.next_status_sync_at if latest_sub else None,
                reconciliation_required=(latest_sub.submission_state == SubmissionLifecycleState.UNKNOWN_OUTCOME) if latest_sub else False,
                notice=NOT_CONFIGURED_NOTICE,
                diagnostic_message=NOT_CONFIGURED_NOTICE,
            )

        # Build notice text
        if latest_sub and latest_sub.submission_state == SubmissionLifecycleState.SUBMITTED:
            notice = f"Case successfully submitted to {integration.display_name}. External tracking ID: {latest_sub.external_reference_id}."
        elif latest_sub and latest_sub.submission_state == SubmissionLifecycleState.UNKNOWN_OUTCOME:
            notice = "External outcome is unconfirmed. Reconciliation is required before retry."
        elif integration.configuration_status == IntegrationState.NOT_CONFIGURED or not integration.enabled:
            notice = NOT_CONFIGURED_NOTICE
        elif integration.configuration_status == IntegrationState.UNAVAILABLE:
            notice = NOT_CONFIGURED_NOTICE
        elif integration.configuration_status == IntegrationState.CONFIGURED_STAGING:
            notice = f"Integration '{integration.display_name}' configured in STAGING sandbox. Ready for test dispatch."
        elif integration.configuration_status == IntegrationState.CONFIGURED_PRODUCTION:
            notice = f"Integration '{integration.display_name}' configured in PRODUCTION. Ready for official dispatch."
        else:
            notice = f"Integration '{integration.display_name}' is {integration.configuration_status.value}. Ready for dispatch."

        return GovernmentSubmissionSummary(
            case_reference_id=case.reference_id,
            integration_id=integration.integration_id,
            integration_name=integration.display_name,
            authority=integration.authority,
            integration_state=integration.configuration_status,
            submission_state=latest_sub.submission_state if latest_sub else SubmissionLifecycleState.READY,
            external_reference_id=latest_sub.external_reference_id if latest_sub else None,
            external_status=latest_sub.external_status if latest_sub else None,
            normalized_status=latest_sub.normalized_status if latest_sub else None,
            external_case_url=latest_sub.external_case_url if latest_sub else None,
            submitted_at=latest_sub.submitted_at if latest_sub else None,
            last_status_sync_at=latest_sub.last_status_sync_at if latest_sub else None,
            next_status_sync_at=latest_sub.next_status_sync_at if latest_sub else None,
            reconciliation_required=(latest_sub.submission_state == SubmissionLifecycleState.UNKNOWN_OUTCOME) if latest_sub else False,
            notice=notice,
            diagnostic_message=integration.diagnostic_message,
        )

    async def submit_case(
        self,
        case: ComplaintCase,
        integration_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        caller_idempotency_key: Optional[str] = None,
    ) -> GovernmentSubmissionResponse:
        """
        Executes safe, verified government submission attempt.
        Refuses if unverified, unconfigured, or in duplicate/unknown state.
        """
        now = datetime.now(timezone.utc)

        # 1. Authority verification policy check
        if not case.authority or case.authority.authority_status == "not_verified":
            await AuditService.record_event(
                action="government_submission_rejected",
                result="rejected",
                actor_user_id=user_id,
                actor_role=user_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={"reason": "Authority unverified; government submission refused."},
            )
            return GovernmentSubmissionResponse(
                success=False,
                submission_id="",
                case_reference_id=case.reference_id,
                integration_id=integration_id or "unknown",
                submission_state=SubmissionLifecycleState.FAILED,
                notice="Submission blocked: Responsible authority has not been verified from official government sources.",
                error_code="AUTHORITY_NOT_VERIFIED",
                error_message_safe="Responsible authority could not be verified from official government records.",
            )

        # 2. Submission package check
        from app.services.government_submission import check_submission_readiness
        readiness = check_submission_readiness(case)
        if readiness.readiness_status in ("blocked", "not_ready"):
            return GovernmentSubmissionResponse(
                success=False,
                submission_id="",
                case_reference_id=case.reference_id,
                integration_id=integration_id or "unknown",
                submission_state=SubmissionLifecycleState.FAILED,
                notice=f"Submission blocked: Case is not submission-ready ({'; '.join(readiness.reasons)}).",
                error_code="SUBMISSION_NOT_READY",
                error_message_safe=f"Case missing required criteria: {', '.join(readiness.missing_fields)}.",
            )

        # 3. Resolve target integration
        target_int_id = integration_id
        if not target_int_id:
            auth_name = (
                case.authority.maintenance_authority.name
                if case.authority.maintenance_authority
                else case.authority.road_owner.name
                if case.authority.road_owner
                else None
            )
            resolved_defn = government_registry.find_integration_for_authority(auth_name)
            target_int_id = resolved_defn.integration_id if resolved_defn else "gov_unassigned"

        # Production protection: Never use mock adapter in production environment
        if getattr(settings, "ENVIRONMENT", "").strip().lower() == "production" and target_int_id == "mock_sandbox_integration":
            await AuditService.record_event(
                action="government_submission_rejected",
                result="refused",
                actor_user_id=user_id,
                actor_role=user_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={"reason": "Mock adapter forbidden in production", "integration_id": target_int_id},
            )
            return GovernmentSubmissionResponse(
                success=False,
                submission_id="",
                case_reference_id=case.reference_id,
                integration_id=target_int_id,
                submission_state=SubmissionLifecycleState.READY,
                notice="Mock adapter cannot be used in production environment.",
                error_code="MOCK_ADAPTER_FORBIDDEN_IN_PRODUCTION",
                error_message_safe="Mock adapter is forbidden in production environment.",
            )

        defn = government_registry.get_definition(target_int_id)
        if not defn or defn.configuration_status in (IntegrationState.NOT_CONFIGURED, IntegrationState.UNAVAILABLE, IntegrationState.DISABLED) or not defn.enabled:
            notice_msg = defn.diagnostic_message if (defn and defn.diagnostic_message) else NOT_CONFIGURED_NOTICE
            err_code = "INTEGRATION_UNAVAILABLE" if (defn and defn.configuration_status == IntegrationState.UNAVAILABLE) else "INTEGRATION_NOT_CONFIGURED"
            await AuditService.record_event(
                action="government_submission_rejected",
                result="refused",
                actor_user_id=user_id,
                actor_role=user_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={"reason": "Integration not configured or unavailable", "integration_id": target_int_id},
            )
            return GovernmentSubmissionResponse(
                success=False,
                submission_id="",
                case_reference_id=case.reference_id,
                integration_id=target_int_id,
                submission_state=SubmissionLifecycleState.READY,
                notice=notice_msg,
                error_code=err_code,
                error_message_safe=notice_msg,
            )

        # 4. Check active submission & Idempotency
        existing_active = self.repository.find_active_submission(case.reference_id, target_int_id)
        if existing_active:
            if existing_active.submission_state == SubmissionLifecycleState.UNKNOWN_OUTCOME:
                return GovernmentSubmissionResponse(
                    success=False,
                    submission_id=existing_active.submission_id,
                    case_reference_id=case.reference_id,
                    integration_id=target_int_id,
                    submission_state=existing_active.submission_state,
                    reconciliation_required=True,
                    notice="Previous submission attempt outcome is unknown. Reconciliation is required before retry.",
                    error_code="RECONCILIATION_REQUIRED",
                    error_message_safe="Reconciliation is required before re-attempting submission.",
                )
            if existing_active.submission_state == SubmissionLifecycleState.SUBMITTING:
                return GovernmentSubmissionResponse(
                    success=False,
                    submission_id=existing_active.submission_id,
                    case_reference_id=case.reference_id,
                    integration_id=target_int_id,
                    submission_state=existing_active.submission_state,
                    notice="A submission attempt is already in progress for this case.",
                    error_code="DUPLICATE_ACTIVE_SUBMISSION",
                    error_message_safe="Submission is actively processing.",
                )
            if existing_active.submission_state == SubmissionLifecycleState.SUBMITTED:
                # Idempotent replay: return existing confirmed submission
                return GovernmentSubmissionResponse(
                    success=True,
                    submission_id=existing_active.submission_id,
                    case_reference_id=case.reference_id,
                    integration_id=target_int_id,
                    submission_state=existing_active.submission_state,
                    external_reference_id=existing_active.external_reference_id,
                    normalized_status=existing_active.normalized_status,
                    notice=f"Idempotent response: Case was already submitted to {defn.display_name}.",
                )

        # 5. Look up runtime adapter
        adapter = government_registry.get_adapter(target_int_id)
        if not adapter:
            return GovernmentSubmissionResponse(
                success=False,
                submission_id="",
                case_reference_id=case.reference_id,
                integration_id=target_int_id,
                submission_state=SubmissionLifecycleState.READY,
                notice=NOT_CONFIGURED_NOTICE,
                error_code="ADAPTER_NOT_FOUND",
                error_message_safe=NOT_CONFIGURED_NOTICE,
            )

        # 6. Prepare package and initialize submission record
        idempotency_key = caller_idempotency_key or f"cvki:{case.reference_id}:{target_int_id}"
        submission_id = f"sub_{uuid.uuid4().hex[:12]}"
        package = case.government_submission.package if (case.government_submission and case.government_submission.package) else None
        if not package:
            # Auto-prepare structured package
            from app.services.government_submission import prepare_government_submission
            _, prep_resp = await prepare_government_submission(case, user_id or "system")
            package = prep_resp.package

        # Validate with adapter
        is_valid, validation_errors = await adapter.validate_submission(case, package)
        if not is_valid:
            await AuditService.record_event(
                action="government_submission_rejected",
                result="validation_failed",
                actor_user_id=user_id,
                actor_role=user_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={"validation_errors": validation_errors},
            )
            return GovernmentSubmissionResponse(
                success=False,
                submission_id=submission_id,
                case_reference_id=case.reference_id,
                integration_id=target_int_id,
                submission_state=SubmissionLifecycleState.VALIDATION_FAILED,
                notice=f"Submission failed adapter validation: {'; '.join(validation_errors)}",
                error_code="VALIDATION_FAILED",
                error_message_safe="Submission package failed adapter validation requirements.",
            )

        # Calculate request fingerprint
        req_payload = await adapter.prepare_submission(case)
        req_fp = hashlib.sha256(json.dumps(req_payload, sort_keys=True, default=str).encode()).hexdigest()

        # Create record in SUBMITTING state
        record = GovernmentSubmissionRecord(
            submission_id=submission_id,
            case_reference_id=case.reference_id,
            integration_id=target_int_id,
            authority_id=case.authority.maintenance_authority.name if (case.authority and case.authority.maintenance_authority) else None,
            submission_state=SubmissionLifecycleState.SUBMITTING,
            adapter_version="1.0",
            request_fingerprint=req_fp,
            created_at=now,
            updated_at=now,
        )
        self.repository.save(record)

        # M7.3 Reference Mapping: Record SUBMISSION_PENDING
        try:
            from app.schemas.government_reference import ReferenceMappingState
            from app.services.government_reference_service import get_government_reference_service
            gov_ref_svc = get_government_reference_service()
            await gov_ref_svc.record_mapping(
                cvki_reference_id=case.reference_id,
                submission_id=submission_id,
                integration_id=target_int_id,
                mapping_state=ReferenceMappingState.SUBMISSION_PENDING,
                source=f"adapter:{target_int_id}",
                actor_user_id=user_id,
                actor_role=user_role,
                case=case,
            )
        except Exception as exc:
            logger.warning("Failed to record pending reference mapping: %s", exc)

        await AuditService.record_event(
            action="government_submission_attempted",
            result="submitting",
            actor_user_id=user_id,
            actor_role=user_role,
            resource_type="case",
            resource_reference_id=case.reference_id,
            metadata={"submission_id": submission_id, "integration_id": target_int_id},
        )

        # 7. Execute adapter submission
        try:
            adapter_res = await adapter.submit(case, package, idempotency_key)
        except Exception as exc:
            logger.error("Adapter submission raised unhandled error: %s", exc)
            record.submission_state = SubmissionLifecycleState.UNKNOWN_OUTCOME
            record.error_code = "ADAPTER_EXECUTION_ERROR"
            record.error_message_safe = "Connection error during government portal submission."
            record.updated_at = datetime.now(timezone.utc)
            self.repository.save(record)

            # M7.3 Reference Mapping: Record UNKNOWN_OUTCOME
            try:
                from app.schemas.government_reference import ReferenceMappingState
                from app.services.government_reference_service import get_government_reference_service
                await get_government_reference_service().record_mapping(
                    cvki_reference_id=case.reference_id,
                    submission_id=submission_id,
                    integration_id=target_int_id,
                    government_reference_id=None,
                    mapping_state=ReferenceMappingState.UNKNOWN_OUTCOME,
                    source=f"adapter:{target_int_id}",
                    actor_user_id=user_id,
                    actor_role=user_role,
                    case=case,
                )
            except Exception as exc_map:
                logger.warning("Failed to record unknown outcome mapping: %s", exc_map)

            await AuditService.record_event(
                action="government_submission_unknown_outcome",
                result="unknown",
                actor_user_id=user_id,
                actor_role=user_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={"submission_id": submission_id, "error": str(exc)},
            )
            try:
                from app.services.notification import trigger_gov_reconciliation_required_notification
                await trigger_gov_reconciliation_required_notification(case)
            except Exception as exc:
                logger.warning("Failed to trigger reconciliation notification: %s", exc)

            return GovernmentSubmissionResponse(
                success=False,
                submission_id=submission_id,
                case_reference_id=case.reference_id,
                integration_id=target_int_id,
                submission_state=SubmissionLifecycleState.UNKNOWN_OUTCOME,
                reconciliation_required=True,
                notice="Submission outcome is unknown due to a network interruption. Reconciliation required before retry.",
                error_code="UNKNOWN_OUTCOME",
                error_message_safe="Submission request sent but acknowledgment was not confirmed. System will reconcile safely.",
            )

        # 8. Evaluate adapter result
        if adapter_res.is_unknown_outcome:
            record.submission_state = SubmissionLifecycleState.UNKNOWN_OUTCOME
            record.error_code = adapter_res.error_code or "TIMEOUT_UNKNOWN"
            record.error_message_safe = adapter_res.error_message_safe or "Response lost during communication."
            record.updated_at = datetime.now(timezone.utc)
            self.repository.save(record)

            # M7.3 Reference Mapping: Record UNKNOWN_OUTCOME
            try:
                from app.schemas.government_reference import ReferenceMappingState
                from app.services.government_reference_service import government_reference_service
                await government_reference_service.record_mapping(
                    cvki_reference_id=case.reference_id,
                    submission_id=submission_id,
                    integration_id=target_int_id,
                    government_reference_id=None,
                    mapping_state=ReferenceMappingState.UNKNOWN_OUTCOME,
                    source=f"adapter:{target_int_id}",
                    actor_user_id=user_id,
                    actor_role=user_role,
                    case=case,
                )
            except Exception as exc_map:
                logger.warning("Failed to record unknown outcome mapping: %s", exc_map)

            await AuditService.record_event(
                action="government_submission_unknown_outcome",
                result="unknown",
                actor_user_id=user_id,
                actor_role=user_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={"submission_id": submission_id, "error_code": record.error_code},
            )
            try:
                from app.services.notification import trigger_gov_reconciliation_required_notification
                await trigger_gov_reconciliation_required_notification(case)
            except Exception as exc:
                logger.warning("Failed to trigger reconciliation notification: %s", exc)

            return GovernmentSubmissionResponse(
                success=False,
                submission_id=submission_id,
                case_reference_id=case.reference_id,
                integration_id=target_int_id,
                submission_state=SubmissionLifecycleState.UNKNOWN_OUTCOME,
                reconciliation_required=True,
                notice="Submission outcome is unconfirmed. Reconciliation required before retry.",
                error_code="UNKNOWN_OUTCOME",
                error_message_safe=record.error_message_safe,
            )

        if adapter_res.state == IntegrationState.SUBMISSION_ACCEPTED:
            record.submission_state = SubmissionLifecycleState.SUBMITTED
            record.external_reference_id = adapter_res.external_reference_id
            record.external_status = adapter_res.raw_status
            record.normalized_status = adapter_res.normalized_status
            record.response_fingerprint = adapter_res.response_fingerprint
            record.submitted_at = datetime.now(timezone.utc)
            record.last_status_sync_at = datetime.now(timezone.utc)
            record.updated_at = datetime.now(timezone.utc)
            self.repository.save(record)

            # Integrate Provenance Claim (M6.4)
            ev_id = None
            try:
                from app.services.provenance_engine import get_provenance_engine
                ev_rec = get_provenance_engine().build_evidence_record(
                    claim_type=ClaimType.GOVERNMENT_SUBMISSION,
                    case_reference=case.reference_id,
                    matched_attribute="external_reference_id",
                    source=f"Government Adapter ({defn.display_name})",
                    source_type=SourceType.GOVERNMENT_ADAPTER,
                    source_url=defn.official_source_url,
                    observed_at=record.submitted_at,
                    retrieved_at=record.submitted_at,
                    freshness="fresh",
                    verification_state=VerificationState.VERIFIED,
                    explanation=f"Complaint acknowledged by government portal '{defn.display_name}'. Tracking ID: {record.external_reference_id}.",
                    claim_value=record.external_reference_id,
                    metadata={
                        "integration_id": target_int_id,
                        "submission_id": submission_id,
                        "raw_status": adapter_res.raw_status,
                        "response_fingerprint": adapter_res.response_fingerprint,
                    },
                )
                ev_id = ev_rec.evidence_id if ev_rec else None
            except Exception as exc:
                logger.warning("Failed to record government submission provenance: %s", exc)

            # Integrate Knowledge Graph (M6.5)
            try:
                from app.services.knowledge_graph import get_knowledge_graph_service
                get_knowledge_graph_service().record_government_submission_graph(
                    case_reference_id=case.reference_id,
                    submission_id=submission_id,
                    integration_id=target_int_id,
                    external_reference_id=record.external_reference_id,
                    evidence_id=ev_id,
                )
            except Exception as exc:
                logger.warning("Failed to record government submission in knowledge graph: %s", exc)

            # M7.3 Reference Mapping: Record REFERENCE_CONFIRMED
            try:
                from app.schemas.government_reference import ReferenceMappingState
                from app.services.government_reference_service import get_government_reference_service
                gov_ref_svc = get_government_reference_service()
                await gov_ref_svc.record_mapping(
                    cvki_reference_id=case.reference_id,
                    submission_id=submission_id,
                    integration_id=target_int_id,
                    government_reference_id=record.external_reference_id,
                    government_reference_status=record.external_status,
                    mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                    source=f"adapter:{target_int_id}",
                    actor_user_id=user_id,
                    actor_role=user_role,
                    external_case_url=getattr(adapter_res, "external_case_url", None),
                    raw_metadata={"response_fingerprint": adapter_res.response_fingerprint},
                    case=case,
                    authority_name=defn.authority,
                    provenance_evidence_id=ev_id,
                    skip_kg_update=True,
                )
            except Exception as exc_map:
                logger.warning("Failed to record confirmed reference mapping: %s", exc_map)

            # Trigger in-app notification (M7.1)
            try:
                from app.services.notification import trigger_gov_submission_accepted_notification
                await trigger_gov_submission_accepted_notification(
                    case,
                    external_reference_id=record.external_reference_id,
                    authority_name=defn.authority,
                )
            except Exception as exc:
                logger.warning("Failed to trigger submission accepted notification: %s", exc)

            # Audit log
            await AuditService.record_event(
                action="government_submission_accepted",
                result="accepted",
                actor_user_id=user_id,
                actor_role=user_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={
                    "submission_id": submission_id,
                    "integration_id": target_int_id,
                    "external_reference_id": record.external_reference_id,
                    "response_fingerprint": adapter_res.response_fingerprint,
                },
            )

            return GovernmentSubmissionResponse(
                success=True,
                submission_id=submission_id,
                case_reference_id=case.reference_id,
                integration_id=target_int_id,
                submission_state=SubmissionLifecycleState.SUBMITTED,
                external_reference_id=record.external_reference_id,
                normalized_status=record.normalized_status,
                notice=f"Submission accepted by {defn.display_name}. External tracking ID: {record.external_reference_id}.",
            )

        if adapter_res.state == IntegrationState.SUBMISSION_REJECTED:
            record.submission_state = SubmissionLifecycleState.REJECTED
            record.error_code = adapter_res.error_code or "SUBMISSION_REJECTED"
            record.error_message_safe = adapter_res.error_message_safe or "Submission rejected by government portal."
            record.updated_at = datetime.now(timezone.utc)
            self.repository.save(record)

            await AuditService.record_event(
                action="government_submission_rejected",
                result="rejected",
                actor_user_id=user_id,
                actor_role=user_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={"submission_id": submission_id, "reason": record.error_message_safe},
            )
            try:
                from app.services.notification import trigger_gov_submission_rejected_notification
                await trigger_gov_submission_rejected_notification(case, reason=record.error_message_safe)
            except Exception as exc:
                logger.warning("Failed to trigger submission rejected notification: %s", exc)

            return GovernmentSubmissionResponse(
                success=False,
                submission_id=submission_id,
                case_reference_id=case.reference_id,
                integration_id=target_int_id,
                submission_state=SubmissionLifecycleState.REJECTED,
                notice=f"Submission rejected: {record.error_message_safe}",
                error_code=record.error_code,
                error_message_safe=record.error_message_safe,
            )

        # Other failures (TEMPORARY_FAILURE, etc.)
        record.submission_state = SubmissionLifecycleState.FAILED
        record.error_code = adapter_res.error_code or "SUBMISSION_FAILED"
        record.error_message_safe = adapter_res.error_message_safe or "External transmission failed."
        record.updated_at = datetime.now(timezone.utc)
        self.repository.save(record)

        await AuditService.record_event(
            action="government_submission_failed",
            result="failed",
            actor_user_id=user_id,
            actor_role=user_role,
            resource_type="case",
            resource_reference_id=case.reference_id,
            metadata={"submission_id": submission_id, "error": record.error_message_safe},
        )

        return GovernmentSubmissionResponse(
            success=False,
            submission_id=submission_id,
            case_reference_id=case.reference_id,
            integration_id=target_int_id,
            submission_state=SubmissionLifecycleState.FAILED,
            notice=f"Submission failed: {record.error_message_safe}",
            error_code=record.error_code,
            error_message_safe=record.error_message_safe,
        )

    async def reconcile_submission(
        self,
        case_reference_id: str,
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> ReconciliationResult:
        """
        Reconciles a submission stuck in UNKNOWN_OUTCOME.
        Determines whether the external government received the complaint or not.
        """
        subs = self.repository.find_by_case(case_reference_id)
        target_sub = None
        for s in subs:
            if s.submission_state == SubmissionLifecycleState.UNKNOWN_OUTCOME:
                target_sub = s
                break

        if not target_sub:
            return ReconciliationResult(
                submission_id="",
                case_reference_id=case_reference_id,
                prior_state=SubmissionLifecycleState.READY,
                reconciled_state=SubmissionLifecycleState.READY,
                resolved=False,
                explanation="No active submission in UNKNOWN_OUTCOME was found for this case.",
            )

        adapter = government_registry.get_adapter(target_sub.integration_id)
        if not adapter:
            return ReconciliationResult(
                submission_id=target_sub.submission_id,
                case_reference_id=case_reference_id,
                prior_state=target_sub.submission_state,
                reconciled_state=target_sub.submission_state,
                resolved=False,
                explanation=f"Adapter '{target_sub.integration_id}' is not loaded for reconciliation.",
            )

        # Test reconciliation query on adapter:
        if hasattr(adapter, "reconcile"):
            status_res = await adapter.reconcile(case_reference_id, target_sub)
        elif target_sub.external_reference_id:
            status_res = await adapter.get_status(target_sub.external_reference_id)
        else:
            # Deterministic sandbox simulation for mock adapter only
            simulated_ref = f"MOCK-GOV-{case_reference_id[:8].upper()}"
            status_res = await adapter.get_status(simulated_ref)

        if status_res.success:
            reconciled_ref = status_res.external_reference_id or target_sub.external_reference_id
            # External government confirmed receipt! Transition to SUBMITTED
            target_sub.submission_state = SubmissionLifecycleState.SUBMITTED
            target_sub.external_reference_id = reconciled_ref
            target_sub.external_status = status_res.raw_status
            target_sub.normalized_status = status_res.normalized_status
            target_sub.submitted_at = datetime.now(timezone.utc)
            target_sub.last_status_sync_at = datetime.now(timezone.utc)
            target_sub.updated_at = datetime.now(timezone.utc)
            self.repository.save(target_sub)

            # M7.3 Reference Mapping: Reconciled and confirmed
            try:
                from app.schemas.government_reference import ReferenceMappingState
                from app.services.government_reference_service import get_government_reference_service
                gov_ref_svc = get_government_reference_service()
                await gov_ref_svc.record_mapping(
                    cvki_reference_id=case_reference_id,
                    submission_id=target_sub.submission_id,
                    integration_id=target_sub.integration_id,
                    government_reference_id=reconciled_ref,
                    government_reference_status=status_res.raw_status,
                    mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                    source=f"reconciliation:{target_sub.integration_id}",
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    external_case_url=getattr(status_res, "external_case_url", None),
                )
            except Exception as exc_map:
                logger.warning("Failed to record reconciled reference mapping: %s", exc_map)

            await AuditService.record_event(
                action="government_submission_reconciled",
                result="reconciled_submitted",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                resource_type="case",
                resource_reference_id=case_reference_id,
                metadata={
                    "submission_id": target_sub.submission_id,
                    "external_reference_id": reconciled_ref,
                },
            )

            # Link graph & provenance
            try:
                from app.services.knowledge_graph import knowledge_graph_service
                knowledge_graph_service.record_government_submission_graph(
                    case_reference_id=case_reference_id,
                    submission_id=target_sub.submission_id,
                    integration_id=target_sub.integration_id,
                    external_reference_id=reconciled_ref,
                )
            except Exception as exc:
                logger.warning("Graph update during reconciliation failed: %s", exc)

            return ReconciliationResult(
                submission_id=target_sub.submission_id,
                case_reference_id=case_reference_id,
                prior_state=SubmissionLifecycleState.UNKNOWN_OUTCOME,
                reconciled_state=SubmissionLifecycleState.SUBMITTED,
                external_reference_id=reconciled_ref,
                resolved=True,
                explanation="Government portal confirmed acceptance upon reconciliation.",
            )
        else:
            # External government has no record; safe to reset to READY for retry
            target_sub.submission_state = SubmissionLifecycleState.READY
            target_sub.updated_at = datetime.now(timezone.utc)
            self.repository.save(target_sub)

            # M7.3 Reference Mapping: Reconciled unavailable
            try:
                from app.schemas.government_reference import ReferenceMappingState
                from app.services.government_reference_service import get_government_reference_service
                gov_ref_svc = get_government_reference_service()
                await gov_ref_svc.record_mapping(
                    cvki_reference_id=case_reference_id,
                    submission_id=target_sub.submission_id,
                    integration_id=target_sub.integration_id,
                    government_reference_id=None,
                    mapping_state=ReferenceMappingState.REFERENCE_UNAVAILABLE,
                    source=f"reconciliation:{target_sub.integration_id}",
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                )
            except Exception as exc_map:
                logger.warning("Failed to record unavailable reference mapping on reconciliation: %s", exc_map)

            await AuditService.record_event(
                action="government_submission_reconciled",
                result="reconciled_reset_ready",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                resource_type="case",
                resource_reference_id=case_reference_id,
                metadata={"submission_id": target_sub.submission_id},
            )

            return ReconciliationResult(
                submission_id=target_sub.submission_id,
                case_reference_id=case_reference_id,
                prior_state=SubmissionLifecycleState.UNKNOWN_OUTCOME,
                reconciled_state=SubmissionLifecycleState.READY,
                external_reference_id=None,
                resolved=True,
                explanation="Confirmed that external system received no submission. State reset to READY for clean retry.",
            )

    async def sync_case_status(
        self,
        case_reference_id: str,
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> GovernmentStatusSyncResult:
        """
        Synchronizes status from external government portal.
        """
        now = datetime.now(timezone.utc)
        subs = self.repository.find_by_case(case_reference_id)
        active_sub = None
        for s in subs:
            if s.submission_state in (SubmissionLifecycleState.SUBMITTED, SubmissionLifecycleState.STATUS_SYNCING):
                active_sub = s
                break

        if not active_sub or not active_sub.external_reference_id:
            return GovernmentStatusSyncResult(
                submission_id="",
                case_reference_id=case_reference_id,
                raw_status=None,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                observed_at=now,
                success=False,
                notice="No submitted external government reference found for this case.",
                error="CASE_NOT_SUBMITTED",
            )

        adapter = government_registry.get_adapter(active_sub.integration_id)
        if not adapter:
            return GovernmentStatusSyncResult(
                submission_id=active_sub.submission_id,
                case_reference_id=case_reference_id,
                raw_status=active_sub.external_status,
                normalized_status=active_sub.normalized_status or NormalizedGovernmentStatus.UNKNOWN,
                observed_at=now,
                success=False,
                notice="Adapter is not loaded.",
                error="ADAPTER_NOT_FOUND",
            )

        status_res = await adapter.get_status(active_sub.external_reference_id)
        if not status_res.success:
            await AuditService.record_event(
                action="government_status_sync_failed",
                result="failed",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                resource_type="case",
                resource_reference_id=case_reference_id,
                metadata={"error": status_res.error_message_safe},
            )
            return GovernmentStatusSyncResult(
                submission_id=active_sub.submission_id,
                case_reference_id=case_reference_id,
                raw_status=active_sub.external_status,
                normalized_status=active_sub.normalized_status or NormalizedGovernmentStatus.UNKNOWN,
                observed_at=now,
                success=False,
                notice=f"Failed to query external government portal: {status_res.error_message_safe}",
                error=status_res.error_code,
            )

        # Update record
        old_norm = active_sub.normalized_status
        active_sub.external_status = status_res.raw_status
        active_sub.normalized_status = status_res.normalized_status
        active_sub.last_status_sync_at = now
        active_sub.updated_at = now

        if status_res.normalized_status in (NormalizedGovernmentStatus.RESOLVED, NormalizedGovernmentStatus.CLOSED):
            active_sub.submission_state = SubmissionLifecycleState.COMPLETED

        self.repository.save(active_sub)

        # M7.3 Reference Mapping: Update confirmed reference on status sync
        try:
            from app.schemas.government_reference import ReferenceMappingState
            from app.services.government_reference_service import get_government_reference_service
            gov_ref_svc = get_government_reference_service()
            await gov_ref_svc.record_mapping(
                cvki_reference_id=case_reference_id,
                submission_id=active_sub.submission_id,
                integration_id=active_sub.integration_id,
                government_reference_id=active_sub.external_reference_id,
                government_reference_status=status_res.raw_status,
                mapping_state=ReferenceMappingState.REFERENCE_CONFIRMED,
                source=f"status_sync:{active_sub.integration_id}",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                external_case_url=getattr(status_res, "external_case_url", None),
            )
        except Exception as exc_map:
            logger.warning("Failed to update reference mapping during status sync: %s", exc_map)

        # Audit log
        await AuditService.record_event(
            action="government_status_synced",
            result="synced",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="case",
            resource_reference_id=case_reference_id,
            metadata={
                "submission_id": active_sub.submission_id,
                "raw_status": status_res.raw_status,
                "normalized_status": status_res.normalized_status.value,
            },
        )

        return GovernmentStatusSyncResult(
            submission_id=active_sub.submission_id,
            case_reference_id=case_reference_id,
            raw_status=status_res.raw_status,
            normalized_status=status_res.normalized_status,
            observed_at=now,
            success=True,
            notice=f"External status synchronized: '{status_res.normalized_status.value}' (Official raw status: '{status_res.raw_status}').",
        )


# Singleton instance
government_integration_service = GovernmentIntegrationService()


def set_government_integration_service(service: GovernmentIntegrationService) -> None:
    global government_integration_service
    government_integration_service = service
