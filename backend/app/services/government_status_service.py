"""
CVKI M7.4 Government Status Synchronization Service.
Maintains strict separation between internal CVKI case lifecycle and external government portal statuses.
Provides idempotent observation recording, stale response protection, freshness tracking,
provenance engine linkage (M6.4), knowledge graph integration (M6.5), and RBAC safeguards.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from threading import Lock
from typing import Any, Optional
import uuid

from app.core.config import settings
from app.core.database import (
    GOVERNMENT_STATUS_RECORDS_COLLECTION,
    get_database,
)
from app.schemas.complaint_case import ComplaintCase
from app.schemas.government_integration import (
    IntegrationState,
    NormalizedGovernmentStatus,
)
from app.schemas.government_reference import ReferenceMappingState
from app.schemas.government_status import (
    FreshnessState,
    GovernmentStatusHistoryResponse,
    GovernmentStatusSynchronizationRecord,
    GovernmentStatusSyncResponse,
    SynchronizationState,
)
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
)
from app.services.audit import AuditService
from app.services.government_reference_service import get_government_reference_service
from app.services.government_registry import government_registry
from app.services.notification import (
    trigger_gov_needs_information_notification,
    trigger_gov_status_changed_notification,
    trigger_gov_status_unavailable_notification,
)

logger = logging.getLogger("cvki.government_status")


class GovernmentStatusRepository(ABC):
    @abstractmethod
    def save(self, record: GovernmentStatusSynchronizationRecord) -> GovernmentStatusSynchronizationRecord:
        pass

    @abstractmethod
    def get_by_id(self, sync_id: str) -> Optional[GovernmentStatusSynchronizationRecord]:
        pass

    @abstractmethod
    def find_latest(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[GovernmentStatusSynchronizationRecord]:
        pass

    @abstractmethod
    def find_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[GovernmentStatusSynchronizationRecord]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryGovernmentStatusRepository(GovernmentStatusRepository):
    def __init__(self):
        self._records: dict[str, GovernmentStatusSynchronizationRecord] = {}
        self._lock = Lock()

    def save(self, record: GovernmentStatusSynchronizationRecord) -> GovernmentStatusSynchronizationRecord:
        with self._lock:
            self._records[record.sync_id] = record.model_copy(deep=True)
        return record

    def get_by_id(self, sync_id: str) -> Optional[GovernmentStatusSynchronizationRecord]:
        with self._lock:
            r = self._records.get(sync_id)
            return r.model_copy(deep=True) if r else None

    def find_latest(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[GovernmentStatusSynchronizationRecord]:
        with self._lock:
            matches = [
                r for r in self._records.values()
                if r.cvki_reference_id == cvki_reference_id
                and (integration_id is None or r.integration_id == integration_id)
            ]
            if not matches:
                return None
            matches.sort(key=lambda x: x.last_seen_at, reverse=True)
            return matches[0].model_copy(deep=True)

    def find_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[GovernmentStatusSynchronizationRecord]:
        with self._lock:
            matches = [
                r for r in self._records.values()
                if r.cvki_reference_id == cvki_reference_id
                and (integration_id is None or r.integration_id == integration_id)
            ]
            matches.sort(key=lambda x: x.last_seen_at, reverse=True)
            return [m.model_copy(deep=True) for m in matches[:limit]]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


class MongoGovernmentStatusRepository(GovernmentStatusRepository):
    def __init__(self):
        self._fallback = InMemoryGovernmentStatusRepository()

    def save(self, record: GovernmentStatusSynchronizationRecord) -> GovernmentStatusSynchronizationRecord:
        self._fallback.save(record)
        db = get_database()
        if db is not None:
            try:
                db.sync_command(
                    lambda: db.delegate[GOVERNMENT_STATUS_RECORDS_COLLECTION].replace_one(
                        {"sync_id": record.sync_id},
                        record.model_dump(),
                        upsert=True,
                    )
                )
            except Exception as exc:
                logger.warning("MongoDB government status save failed, fallback active: %s", exc)
        return record

    def get_by_id(self, sync_id: str) -> Optional[GovernmentStatusSynchronizationRecord]:
        db = get_database()
        if db is not None:
            try:
                doc = db.sync_command(
                    lambda: db.delegate[GOVERNMENT_STATUS_RECORDS_COLLECTION].find_one(
                        {"sync_id": sync_id}
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return GovernmentStatusSynchronizationRecord(**doc)
            except Exception as exc:
                logger.warning("MongoDB get status by id failed: %s", exc)
        return self._fallback.get_by_id(sync_id)

    def find_latest(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[GovernmentStatusSynchronizationRecord]:
        db = get_database()
        if db is not None:
            try:
                query: dict[str, Any] = {"cvki_reference_id": cvki_reference_id}
                if integration_id:
                    query["integration_id"] = integration_id
                doc = db.sync_command(
                    lambda: db.delegate[GOVERNMENT_STATUS_RECORDS_COLLECTION].find_one(
                        query, sort=[("last_seen_at", -1)]
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return GovernmentStatusSynchronizationRecord(**doc)
            except Exception as exc:
                logger.warning("MongoDB find latest status failed: %s", exc)
        return self._fallback.find_latest(cvki_reference_id, integration_id)

    def find_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[GovernmentStatusSynchronizationRecord]:
        db = get_database()
        if db is not None:
            try:
                query: dict[str, Any] = {"cvki_reference_id": cvki_reference_id}
                if integration_id:
                    query["integration_id"] = integration_id
                cursor = db.sync_command(
                    lambda: list(
                        db.delegate[GOVERNMENT_STATUS_RECORDS_COLLECTION].find(
                            query, sort=[("last_seen_at", -1)]
                        ).limit(limit)
                    )
                )
                recs = []
                for doc in cursor:
                    doc.pop("_id", None)
                    recs.append(GovernmentStatusSynchronizationRecord(**doc))
                if recs:
                    return recs
            except Exception as exc:
                logger.warning("MongoDB find status history failed: %s", exc)
        return self._fallback.find_history(cvki_reference_id, integration_id, limit)

    def clear(self) -> None:
        self._fallback.clear()
        db = get_database()
        if db is not None:
            try:
                db.sync_command(lambda: db.delegate[GOVERNMENT_STATUS_RECORDS_COLLECTION].delete_many({}))
            except Exception as exc:
                logger.warning("MongoDB clear status records failed: %s", exc)


class GovernmentStatusService:
    """
    Core orchestrator for M7.4 Government Status Synchronization.
    """

    FRESHNESS_WINDOW_HOURS = 24.0

    def __init__(self, repository: Optional[GovernmentStatusRepository] = None):
        self.repository = repository or MongoGovernmentStatusRepository()

    def compute_freshness(
        self, record: Optional[GovernmentStatusSynchronizationRecord]
    ) -> FreshnessState:
        """
        Calculates engineering freshness state based on retrieval and check recency.
        """
        if not record or not record.last_checked_at:
            return FreshnessState.UNKNOWN
        if record.synchronization_state in (SynchronizationState.UNAVAILABLE, SynchronizationState.FAILED):
            return FreshnessState.UNAVAILABLE

        now = datetime.now(timezone.utc)
        age = now - record.last_checked_at
        if age <= timedelta(hours=self.FRESHNESS_WINDOW_HOURS):
            return FreshnessState.FRESH
        return FreshnessState.STALE

    async def synchronize_status(
        self,
        case: ComplaintCase,
        integration_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        force_refresh: bool = False,
    ) -> GovernmentStatusSyncResponse:
        """
        Executes external government status synchronization for a CVKI complaint case.
        Strictly observes reference-ID dependencies, stale response protection, and idempotency.
        """
        now = datetime.now(timezone.utc)
        cvki_ref = case.reference_id

        # 1. Identity Mapping Inspection (M7.3 dependency)
        ref_service = get_government_reference_service()
        mappings = ref_service.get_case_mappings(cvki_ref).mappings

        target_mapping = None
        if integration_id:
            for m in mappings:
                if m.integration_id == integration_id:
                    target_mapping = m
                    break
        elif mappings:
            # Prefer confirmed mapping, otherwise first active
            for m in mappings:
                if m.mapping_state == ReferenceMappingState.REFERENCE_CONFIRMED:
                    target_mapping = m
                    break
            if not target_mapping:
                target_mapping = mappings[0]

        # Gate A: No reference mapping exists
        if not target_mapping or target_mapping.mapping_state == ReferenceMappingState.UNMAPPED:
            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=integration_id or "unassigned",
                integration_display_name="No Integration Assigned",
                government_reference_id=None,
                synchronization_state=SynchronizationState.NOT_READY,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNKNOWN,
                notice="Case has not been mapped or dispatched to any external government system.",
                error_code="CASE_NOT_MAPPED",
                error_message_safe="No government reference tracking ID is associated with this case.",
            )

        int_id = target_mapping.integration_id
        gov_ref = target_mapping.government_reference_id
        defn = government_registry.get_definition(int_id)
        display_name = defn.display_name if defn else int_id

        # Gate B: Reference Conflict
        if target_mapping.conflict_detected or target_mapping.mapping_state == ReferenceMappingState.REFERENCE_CONFLICT:
            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                integration_display_name=display_name,
                government_reference_id=gov_ref,
                synchronization_state=SynchronizationState.CONFLICT_BLOCKED,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNKNOWN,
                notice="Status synchronization blocked: An external reference identity conflict is active for this case.",
                error_code="REFERENCE_CONFLICT_BLOCKED",
                error_message_safe="Automatic status synchronization is paused due to an identity collision on this reference.",
            )

        # Gate C: UNKNOWN_OUTCOME -> Try reconciliation where supported
        if target_mapping.mapping_state == ReferenceMappingState.UNKNOWN_OUTCOME:
            from app.services.government_integration_service import government_integration_service
            rec_result = await government_integration_service.reconcile_submission(
                cvki_ref, actor_user_id=actor_user_id, actor_role=actor_role
            )
            if rec_result.resolved and rec_result.reconciled_state.value == "SUBMITTED":
                # Upstream confirmed submission! Re-read target mapping
                target_mapping = ref_service.get_mapping(cvki_ref, int_id)
                gov_ref = target_mapping.government_reference_id if target_mapping else None
            else:
                return GovernmentStatusSyncResponse(
                    cvki_reference_id=cvki_ref,
                    integration_id=int_id,
                    integration_display_name=display_name,
                    government_reference_id=None,
                    synchronization_state=SynchronizationState.UNKNOWN_OUTCOME,
                    normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                    freshness=FreshnessState.UNKNOWN,
                    reconciliation_required=True,
                    notice="Submission outcome is unknown. Reconciliation required before status synchronization.",
                    error_code="UNKNOWN_OUTCOME",
                    error_message_safe="Government portal receipt unconfirmed. System cannot query status without confirmed tracking ID.",
                )

        # Gate D: REFERENCE_RECEIVED but not confirmed
        if target_mapping.mapping_state == ReferenceMappingState.REFERENCE_RECEIVED:
            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                integration_display_name=display_name,
                government_reference_id=gov_ref,
                synchronization_state=SynchronizationState.REFERENCE_NOT_CONFIRMED,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNKNOWN,
                notice="External tracking reference has been received but is not yet authoritatively confirmed upstream.",
                error_code="REFERENCE_NOT_CONFIRMED",
                error_message_safe="Tracking reference provisional; awaiting upstream authoritative confirmation.",
            )

        if not gov_ref:
            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                integration_display_name=display_name,
                government_reference_id=None,
                synchronization_state=SynchronizationState.NOT_READY,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNKNOWN,
                notice="Government tracking reference is missing.",
                error_code="MISSING_GOVERNMENT_REFERENCE",
                error_message_safe="Cannot query status without an external tracking identifier.",
            )

        # Gate E: Check integration configuration & Adapter lookup
        if not defn or defn.configuration_status in (IntegrationState.NOT_CONFIGURED, IntegrationState.UNAVAILABLE, IntegrationState.DISABLED):
            diagnostic = defn.diagnostic_message if defn else "Integration is not configured."
            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                integration_display_name=display_name,
                government_reference_id=gov_ref,
                synchronization_state=SynchronizationState.UNAVAILABLE,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNAVAILABLE,
                notice=diagnostic,
                diagnostic_message=diagnostic,
                error_code="INTEGRATION_NOT_CONFIGURED",
                error_message_safe=diagnostic,
            )

        adapter = government_registry.get_adapter(int_id)
        if not adapter:
            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                integration_display_name=display_name,
                government_reference_id=gov_ref,
                synchronization_state=SynchronizationState.UNAVAILABLE,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNAVAILABLE,
                notice=f"Adapter '{int_id}' is not loaded.",
                error_code="ADAPTER_NOT_FOUND",
                error_message_safe="Adapter executable not found in registry.",
            )

        # Query Adapter for Upstream Status
        try:
            status_res = await adapter.get_status(gov_ref)
        except Exception as exc:
            logger.error("Adapter get_status raised unexpected exception: %s", exc)
            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                integration_display_name=display_name,
                government_reference_id=gov_ref,
                synchronization_state=SynchronizationState.FAILED,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNAVAILABLE,
                notice=f"Failed to query status from {display_name}: {exc}",
                error_code="STATUS_QUERY_EXCEPTION",
                error_message_safe="Communication error querying government portal status.",
            )

        latest_prev = self.repository.find_latest(cvki_ref, int_id)

        # Upstream status check failed
        if not status_res.success:
            if latest_prev:
                # Retain previous observation, mark as checked with failure state
                latest_prev.last_checked_at = now
                latest_prev.freshness_state = FreshnessState.UNAVAILABLE
                latest_prev.updated_at = now
                self.repository.save(latest_prev)

            await AuditService.record_event(
                action="government_status_sync_failed",
                result="failed",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                resource_type="case",
                resource_reference_id=cvki_ref,
                metadata={"integration_id": int_id, "error": status_res.error_message_safe},
            )
            try:
                await trigger_gov_status_unavailable_notification(case, int_id, status_res.error_message_safe)
            except Exception as notif_err:
                logger.warning("Failed to fire status unavailable notification: %s", notif_err)

            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                integration_display_name=display_name,
                government_reference_id=gov_ref,
                synchronization_state=SynchronizationState.FAILED,
                latest_raw_status=latest_prev.raw_external_status if latest_prev else None,
                normalized_status=latest_prev.normalized_external_status if latest_prev else NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNAVAILABLE,
                last_checked_at=now,
                last_successful_sync_at=latest_prev.retrieved_at if latest_prev else None,
                notice=f"Status check failed: {status_res.error_message_safe}",
                error_code=status_res.error_code or "STATUS_CHECK_FAILED",
                error_message_safe=status_res.error_message_safe,
            )

        # 4. Stale Response Protection
        # If upstream payload provides an explicit timestamp, verify chronology
        ext_timestamp = getattr(status_res, "observed_at", None)
        if ext_timestamp and latest_prev and latest_prev.external_status_timestamp:
            if ext_timestamp < latest_prev.external_status_timestamp:
                logger.warning(
                    "Stale government response detected for %s on %s: received %s older than %s",
                    cvki_ref, int_id, ext_timestamp, latest_prev.external_status_timestamp
                )
                return GovernmentStatusSyncResponse(
                    cvki_reference_id=cvki_ref,
                    integration_id=int_id,
                    integration_display_name=display_name,
                    government_reference_id=gov_ref,
                    synchronization_state=SynchronizationState.STALE_RESPONSE,
                    latest_raw_status=latest_prev.raw_external_status,
                    normalized_status=latest_prev.normalized_external_status,
                    freshness=FreshnessState.STALE,
                    last_checked_at=now,
                    last_successful_sync_at=latest_prev.retrieved_at,
                    external_updated_at=latest_prev.external_updated_at,
                    notice="External response timestamp is older than current known observation. Retaining latest verified state.",
                    error_code="STALE_RESPONSE_IGNORED",
                    error_message_safe="Upstream government server returned an older cached status payload.",
                )

        raw_status = status_res.raw_status
        normalized_st = status_res.normalized_status
        status_code = normalized_st.value.upper()

        # 5. Idempotent Repeated Observation vs Transition
        is_identical = (
            latest_prev is not None
            and latest_prev.raw_external_status == raw_status
            and latest_prev.normalized_external_status == normalized_st
        )

        if is_identical and latest_prev is not None:
            # Idempotent bump: update observation freshness without creating redundant history record
            latest_prev.last_seen_at = now
            latest_prev.last_checked_at = now
            latest_prev.freshness_state = FreshnessState.FRESH
            latest_prev.updated_at = now
            if getattr(status_res, "external_case_url", None):
                latest_prev.external_case_url = status_res.external_case_url
            saved_record = self.repository.save(latest_prev)
            sync_state = SynchronizationState.UNCHANGED
        else:
            # New Status Transition: create append-oriented history record
            prev_raw = latest_prev.raw_external_status if latest_prev else None
            prev_norm = latest_prev.normalized_external_status if latest_prev else None
            sync_id = f"gss_{uuid.uuid4().hex[:14]}"

            new_record = GovernmentStatusSynchronizationRecord(
                sync_id=sync_id,
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                government_reference_id=gov_ref,
                synchronization_state=SynchronizationState.SYNCED,
                raw_external_status=raw_status,
                normalized_external_status=normalized_st,
                normalized_status_code=status_code,
                external_status_timestamp=ext_timestamp,
                retrieved_at=now,
                previous_external_status=prev_raw,
                previous_normalized_status=prev_norm,
                first_seen_at=now,
                last_seen_at=now,
                last_checked_at=now,
                source=f"adapter:{int_id}",
                adapter_version="1.0",
                freshness_state=FreshnessState.FRESH,
                external_case_url=getattr(status_res, "external_case_url", None),
                details=getattr(status_res, "details", {}),
                created_at=now,
                updated_at=now,
            )

            # M6.4 Provenance Engine Integration
            ev_id = None
            try:
                from app.services.provenance_engine import get_provenance_engine
                ev_rec = get_provenance_engine().build_evidence_record(
                    claim_type=ClaimType.GOVERNMENT_STATUS,
                    case_reference=cvki_ref,
                    matched_attribute="normalized_status",
                    source=f"Government Adapter ({display_name})",
                    source_type=SourceType.GOVERNMENT_ADAPTER,
                    source_url=defn.official_source_url,
                    observed_at=now,
                    retrieved_at=now,
                    freshness="fresh",
                    verification_state=VerificationState.VERIFIED,
                    explanation=f"Government portal '{display_name}' reports status '{normalized_st.value}' (raw: '{raw_status}') for reference '{gov_ref}'.",
                    claim_value=normalized_st.value,
                    metadata={
                        "integration_id": int_id,
                        "government_reference_id": gov_ref,
                        "raw_status": raw_status,
                        "normalized_status": normalized_st.value,
                        "sync_id": sync_id,
                    },
                )
                ev_id = ev_rec.evidence_id if ev_rec else None
                new_record.provenance_evidence_id = ev_id
            except Exception as prov_err:
                logger.warning("Failed to record status provenance: %s", prov_err)

            # M6.5 Knowledge Graph Integration
            try:
                from app.services.knowledge_graph import get_knowledge_graph_service
                get_knowledge_graph_service().record_government_status_graph(
                    case_reference_id=cvki_ref,
                    integration_id=int_id,
                    government_reference_id=gov_ref,
                    normalized_status=normalized_st.value,
                    raw_status=raw_status,
                    freshness=FreshnessState.FRESH.value,
                    evidence_id=ev_id,
                    observed_at=now,
                )
            except Exception as kg_err:
                logger.warning("Failed to record status in knowledge graph: %s", kg_err)

            saved_record = self.repository.save(new_record)
            sync_state = SynchronizationState.SYNCED

            # Notifications on Meaningful Transition
            try:
                await trigger_gov_status_changed_notification(
                    case=case,
                    integration_id=int_id,
                    government_reference_id=gov_ref,
                    previous_status=prev_raw,
                    new_status=normalized_st.value,
                    raw_status=raw_status,
                )
                if normalized_st in (NormalizedGovernmentStatus.AWAITING_INFORMATION, NormalizedGovernmentStatus.NEEDS_INFORMATION):
                    await trigger_gov_needs_information_notification(
                        case=case,
                        integration_id=int_id,
                        government_reference_id=gov_ref,
                        details=f"Status: {raw_status}",
                    )
            except Exception as notif_err:
                logger.warning("Failed to fire status change notification: %s", notif_err)

            # Audit Trail
            await AuditService.record_event(
                action="government_status_transitioned",
                result="transitioned",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                resource_type="case",
                resource_reference_id=cvki_ref,
                metadata={
                    "sync_id": sync_id,
                    "integration_id": int_id,
                    "government_reference_id": gov_ref,
                    "previous_status": prev_raw,
                    "new_status": raw_status,
                    "normalized_status": normalized_st.value,
                },
            )

        history_recs = self.repository.find_history(cvki_ref, int_id, limit=5)
        history_summary = [
            {
                "sync_id": h.sync_id,
                "raw_status": h.raw_external_status,
                "normalized_status": h.normalized_external_status.value,
                "first_seen_at": h.first_seen_at.isoformat(),
                "last_seen_at": h.last_seen_at.isoformat(),
                "freshness": h.freshness_state.value,
            }
            for h in history_recs
        ]

        next_rec = now + timedelta(hours=self.FRESHNESS_WINDOW_HOURS)

        return GovernmentStatusSyncResponse(
            cvki_reference_id=cvki_ref,
            integration_id=int_id,
            integration_display_name=display_name,
            government_reference_id=gov_ref,
            synchronization_state=sync_state,
            latest_raw_status=saved_record.raw_external_status,
            normalized_status=saved_record.normalized_external_status,
            freshness=saved_record.freshness_state,
            last_checked_at=saved_record.last_checked_at,
            last_successful_sync_at=saved_record.retrieved_at,
            external_updated_at=saved_record.external_updated_at,
            next_recommended_sync_at=next_rec,
            notice=f"External status synchronized: '{saved_record.normalized_external_status.value}' (Official raw status: '{saved_record.raw_external_status}').",
            provenance_evidence_id=saved_record.provenance_evidence_id,
            external_case_url=saved_record.external_case_url,
            history_summary=history_summary,
        )

    def get_status_summary(
        self, case: ComplaintCase, integration_id: Optional[str] = None
    ) -> GovernmentStatusSyncResponse:
        """
        Retrieves the latest cached status observation without invoking an external network call.
        """
        cvki_ref = case.reference_id
        ref_service = get_government_reference_service()
        mappings = ref_service.get_case_mappings(cvki_ref).mappings
        
        target_mapping = None
        if integration_id:
            for m in mappings:
                if m.integration_id == integration_id:
                    target_mapping = m
                    break
        elif mappings:
            for m in mappings:
                if m.mapping_state == ReferenceMappingState.REFERENCE_CONFIRMED:
                    target_mapping = m
                    break
            if not target_mapping:
                target_mapping = mappings[0]

        int_id = target_mapping.integration_id if target_mapping else (integration_id or "unassigned")
        gov_ref = target_mapping.government_reference_id if target_mapping else None
        defn = government_registry.get_definition(int_id)
        display_name = defn.display_name if defn else int_id

        latest = self.repository.find_latest(cvki_ref, int_id)
        if not latest:
            return GovernmentStatusSyncResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                integration_display_name=display_name,
                government_reference_id=gov_ref,
                synchronization_state=SynchronizationState.NOT_READY if not gov_ref else SynchronizationState.UNKNOWN,
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                freshness=FreshnessState.UNKNOWN,
                notice="No status synchronization records exist yet for this case.",
            )

        freshness = self.compute_freshness(latest)
        history_recs = self.repository.find_history(cvki_ref, int_id, limit=5)
        history_summary = [
            {
                "sync_id": h.sync_id,
                "raw_status": h.raw_external_status,
                "normalized_status": h.normalized_external_status.value,
                "first_seen_at": h.first_seen_at.isoformat(),
                "last_seen_at": h.last_seen_at.isoformat(),
                "freshness": h.freshness_state.value,
            }
            for h in history_recs
        ]

        return GovernmentStatusSyncResponse(
            cvki_reference_id=cvki_ref,
            integration_id=int_id,
            integration_display_name=display_name,
            government_reference_id=gov_ref,
            synchronization_state=latest.synchronization_state,
            latest_raw_status=latest.raw_external_status,
            normalized_status=latest.normalized_external_status,
            freshness=freshness,
            last_checked_at=latest.last_checked_at,
            last_successful_sync_at=latest.retrieved_at,
            external_updated_at=latest.external_updated_at,
            notice=f"Latest recorded status: '{latest.normalized_external_status.value}' (Official raw: '{latest.raw_external_status}').",
            provenance_evidence_id=latest.provenance_evidence_id,
            external_case_url=latest.external_case_url,
            history_summary=history_summary,
        )

    def get_status_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> GovernmentStatusHistoryResponse:
        """
        Retrieves complete append-oriented synchronization history for a case.
        """
        records = self.repository.find_history(cvki_reference_id, integration_id, limit=limit)
        gov_ref = records[0].government_reference_id if records else None
        int_id = integration_id or (records[0].integration_id if records else "unknown")

        return GovernmentStatusHistoryResponse(
            cvki_reference_id=cvki_reference_id,
            integration_id=int_id,
            government_reference_id=gov_ref,
            records=records,
            total=len(records),
        )


government_status_service = GovernmentStatusService()


def get_government_status_service() -> GovernmentStatusService:
    return government_status_service


def set_government_status_service(service: GovernmentStatusService) -> None:
    global government_status_service
    government_status_service = service
