"""
CVKI M7.6 Citizen Resolution Verification Service.
Enforces strict epistemic separation between external government status observations ("RESOLVED")
and citizen-verified physical resolution ground truth.
Collects, evaluates, audits, and tracks citizen resolution feedback without mutating internal case status.
"""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone
import logging
from threading import Lock
from typing import Any, Optional
import uuid

from app.core.database import RESOLUTION_VERIFICATIONS_COLLECTION, get_database
from app.models.roles import UserRole
from app.schemas.complaint_case import ComplaintCase
from app.schemas.government_reference import ReferenceMappingState
from app.schemas.provenance import ClaimType, SourceType, VerificationState
from app.schemas.resolution_verification import (
    CitizenResolutionResponse,
    CitizenResolutionVerificationHistoryResponse,
    CitizenResolutionVerificationRecord,
    CitizenResolutionVerificationResponse,
    CitizenResolutionVerificationSubmitRequest,
    ResolutionVerificationReviewRequest,
    ResolutionVerificationStatus,
    ResolutionVerificationTransitionRecord,
)
from app.services.audit import AuditService
from app.services.government_reference_service import get_government_reference_service
from app.services.government_status_service import get_government_status_service
from app.services.knowledge_graph import get_knowledge_graph_service
from app.services.notification import (
    trigger_resolution_verification_disputed_notification,
    trigger_resolution_verification_reviewed_notification,
    trigger_resolution_verification_submitted_notification,
)
from app.services.provenance_engine import get_provenance_engine

logger = logging.getLogger("cvki.resolution_verification")

UNCERTAINTY_PHRASES = (
    "not sure",
    "doubt",
    "maybe",
    "unclear",
    "partially",
    "cannot tell",
    "not certain",
    "conflicting",
)


class ResolutionVerificationRepository(ABC):
    """Abstract interface for storing and querying citizen resolution verification records."""

    @abstractmethod
    def save_verification(
        self, record: CitizenResolutionVerificationRecord
    ) -> CitizenResolutionVerificationRecord:
        pass

    @abstractmethod
    def get_verification(self, verification_id: str) -> Optional[CitizenResolutionVerificationRecord]:
        pass

    @abstractmethod
    def get_latest_verification(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[CitizenResolutionVerificationRecord]:
        pass

    @abstractmethod
    def get_verification_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[CitizenResolutionVerificationRecord]:
        pass

    @abstractmethod
    def list_all(self, limit: int = 500) -> list[CitizenResolutionVerificationRecord]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryResolutionVerificationRepository(ResolutionVerificationRepository):
    """Thread-safe in-memory repository for unit testing and local development."""

    def __init__(self):
        self._records: dict[str, CitizenResolutionVerificationRecord] = {}
        self._lock = Lock()

    def save_verification(
        self, record: CitizenResolutionVerificationRecord
    ) -> CitizenResolutionVerificationRecord:
        with self._lock:
            self._records[record.verification_id] = record.model_copy(deep=True)
        return record

    def get_verification(self, verification_id: str) -> Optional[CitizenResolutionVerificationRecord]:
        with self._lock:
            rec = self._records.get(verification_id)
            return rec.model_copy(deep=True) if rec else None

    def get_latest_verification(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[CitizenResolutionVerificationRecord]:
        with self._lock:
            matches = [
                r for r in self._records.values()
                if r.cvki_reference_id == cvki_reference_id
                and (integration_id is None or r.integration_id == integration_id)
            ]
            if not matches:
                return None
            matches.sort(key=lambda x: x.submitted_at, reverse=True)
            return matches[0].model_copy(deep=True)

    def get_verification_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[CitizenResolutionVerificationRecord]:
        with self._lock:
            matches = [
                r for r in self._records.values()
                if r.cvki_reference_id == cvki_reference_id
                and (integration_id is None or r.integration_id == integration_id)
            ]
            matches.sort(key=lambda x: x.submitted_at, reverse=True)
            return [m.model_copy(deep=True) for m in matches[:limit]]

    def list_all(self, limit: int = 500) -> list[CitizenResolutionVerificationRecord]:
        with self._lock:
            recs = list(self._records.values())
            recs.sort(key=lambda x: x.submitted_at, reverse=True)
            return [r.model_copy(deep=True) for r in recs[:limit]]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


class MongoResolutionVerificationRepository(ResolutionVerificationRepository):
    """MongoDB persistent repository with graceful fallback to in-memory storage."""

    def __init__(self):
        self._fallback = InMemoryResolutionVerificationRepository()

    def save_verification(
        self, record: CitizenResolutionVerificationRecord
    ) -> CitizenResolutionVerificationRecord:
        self._fallback.save_verification(record)
        db = get_database()
        if db is not None:
            try:
                db.sync_command(
                    lambda: db.delegate[RESOLUTION_VERIFICATIONS_COLLECTION].replace_one(
                        {"verification_id": record.verification_id},
                        record.model_dump(),
                        upsert=True,
                    )
                )
            except Exception as exc:
                logger.warning("MongoDB verification save failed, fallback active: %s", exc)
        return record

    def get_verification(self, verification_id: str) -> Optional[CitizenResolutionVerificationRecord]:
        db = get_database()
        if db is not None:
            try:
                doc = db.sync_command(
                    lambda: db.delegate[RESOLUTION_VERIFICATIONS_COLLECTION].find_one(
                        {"verification_id": verification_id}
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return CitizenResolutionVerificationRecord(**doc)
            except Exception as exc:
                logger.warning("MongoDB get verification failed: %s", exc)
        return self._fallback.get_verification(verification_id)

    def get_latest_verification(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[CitizenResolutionVerificationRecord]:
        db = get_database()
        if db is not None:
            try:
                query: dict[str, Any] = {"cvki_reference_id": cvki_reference_id}
                if integration_id:
                    query["integration_id"] = integration_id
                doc = db.sync_command(
                    lambda: db.delegate[RESOLUTION_VERIFICATIONS_COLLECTION].find_one(
                        query, sort=[("submitted_at", -1)]
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return CitizenResolutionVerificationRecord(**doc)
            except Exception as exc:
                logger.warning("MongoDB get latest verification failed: %s", exc)
        return self._fallback.get_latest_verification(cvki_reference_id, integration_id)

    def get_verification_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[CitizenResolutionVerificationRecord]:
        db = get_database()
        if db is not None:
            try:
                query: dict[str, Any] = {"cvki_reference_id": cvki_reference_id}
                if integration_id:
                    query["integration_id"] = integration_id
                cursor = db.sync_command(
                    lambda: list(
                        db.delegate[RESOLUTION_VERIFICATIONS_COLLECTION].find(
                            query, sort=[("submitted_at", -1)]
                        ).limit(limit)
                    )
                )
                recs = []
                for doc in cursor:
                    doc.pop("_id", None)
                    recs.append(CitizenResolutionVerificationRecord(**doc))
                if recs:
                    return recs
            except Exception as exc:
                logger.warning("MongoDB get verification history failed: %s", exc)
        return self._fallback.get_verification_history(cvki_reference_id, integration_id, limit)

    def list_all(self, limit: int = 500) -> list[CitizenResolutionVerificationRecord]:
        db = get_database()
        if db is not None:
            try:
                cursor = db.sync_command(
                    lambda: list(
                        db.delegate[RESOLUTION_VERIFICATIONS_COLLECTION].find(
                            {}, sort=[("submitted_at", -1)]
                        ).limit(limit)
                    )
                )
                recs = []
                for doc in cursor:
                    doc.pop("_id", None)
                    recs.append(CitizenResolutionVerificationRecord(**doc))
                if recs:
                    return recs
            except Exception as exc:
                logger.warning("MongoDB list all verifications failed: %s", exc)
        return self._fallback.list_all(limit)

    def clear(self) -> None:
        self._fallback.clear()
        db = get_database()
        if db is not None:
            try:
                db.sync_command(lambda: db.delegate[RESOLUTION_VERIFICATIONS_COLLECTION].delete_many({}))
            except Exception as exc:
                logger.warning("MongoDB clear verifications failed: %s", exc)


class ResolutionVerificationService:
    """
    Citizen Resolution Verification Service (M7.6).
    Enforces deterministic evaluation of citizen-side resolution feedback.
    """

    def __init__(self, repository: Optional[ResolutionVerificationRepository] = None):
        self.repository = repository or MongoResolutionVerificationRepository()

    async def submit_verification(
        self,
        case: ComplaintCase,
        req: CitizenResolutionVerificationSubmitRequest,
        citizen_user_id: str,
        citizen_role: str,
    ) -> CitizenResolutionVerificationResponse:
        """
        Processes and records a citizen's resolution feedback for a case.
        Strictly enforces that external government status != internal physical resolution.
        """
        now = datetime.now(timezone.utc)
        cvki_ref = case.reference_id

        # Step 1: Verify Government Reference Mapping (M7.3)
        ref_service = get_government_reference_service()
        mappings = ref_service.get_case_mappings(cvki_ref).mappings

        target_mapping = None
        if req.integration_id:
            for m in mappings:
                if m.integration_id == req.integration_id:
                    target_mapping = m
                    break
        elif mappings:
            for m in mappings:
                if m.mapping_state == ReferenceMappingState.REFERENCE_CONFIRMED:
                    target_mapping = m
                    break
            if not target_mapping:
                target_mapping = mappings[0]

        int_id = target_mapping.integration_id if target_mapping else (req.integration_id or "unassigned")
        gov_ref = target_mapping.government_reference_id if target_mapping else None

        # Step 2: Retrieve latest synchronized government status (M7.4)
        status_service = get_government_status_service()
        latest_status = status_service.repository.find_latest(cvki_ref, int_id)
        obs_status = latest_status.normalized_external_status.value if latest_status else None
        sync_id = latest_status.sync_id if latest_status else None

        # Step 3: Determine Verification Status based on deterministic rules
        notes_lower = (req.citizen_notes or "").lower()
        has_uncertainty = any(phrase in notes_lower for phrase in UNCERTAINTY_PHRASES)

        is_physical_verified = False
        if req.requires_review or has_uncertainty:
            verif_status = ResolutionVerificationStatus.NEEDS_REVIEW
            is_physical_verified = False
        elif req.citizen_response == CitizenResolutionResponse.CONFIRMED_RESOLVED:
            # Rule 1: Confirmed by citizen
            verif_status = ResolutionVerificationStatus.VERIFIED_RESOLVED
            is_physical_verified = True
        elif req.citizen_response == CitizenResolutionResponse.STILL_UNRESOLVED:
            # Rule 2: Disputed by citizen
            verif_status = ResolutionVerificationStatus.CITIZEN_DISPUTED
            is_physical_verified = False
        elif req.citizen_response == CitizenResolutionResponse.PARTIALLY_RESOLVED:
            # Rule 3: Partial resolution
            verif_status = ResolutionVerificationStatus.PARTIALLY_RESOLVED
            is_physical_verified = False
        elif req.citizen_response == CitizenResolutionResponse.CANNOT_VERIFY:
            # Rule 4 & 5: Cannot verify -> insufficient evidence
            verif_status = ResolutionVerificationStatus.INSUFFICIENT_EVIDENCE
            is_physical_verified = False
        else:
            verif_status = ResolutionVerificationStatus.NEEDS_REVIEW
            is_physical_verified = False

        # Build initial transition record
        transition_id = f"trans_{uuid.uuid4().hex[:12]}"
        init_trans = ResolutionVerificationTransitionRecord(
            transition_id=transition_id,
            from_status=ResolutionVerificationStatus.PENDING,
            to_status=verif_status,
            actor_user_id=citizen_user_id,
            actor_role=citizen_role,
            transition_reason=f"Citizen verification submitted as {req.citizen_response.value}.",
            transitioned_at=now,
        )

        verification_id = f"verif_{uuid.uuid4().hex[:14]}"

        # Step 4: Register Provenance Claim (M6.4)
        ev_id = None
        try:
            prov_engine = get_provenance_engine()
            ev_rec = prov_engine.build_evidence_record(
                claim_type=ClaimType.RESOLUTION_VERIFICATION,
                case_reference=cvki_ref,
                matched_attribute="resolution_verification_status",
                source=f"Citizen Verification: {citizen_user_id}",
                source_type=SourceType.CITIZEN_REPORT,
                observed_at=now,
                retrieved_at=now,
                freshness="fresh",
                verification_state=VerificationState.VERIFIED if is_physical_verified else VerificationState.PARTIALLY_VERIFIED,
                explanation=f"Citizen reported: {req.citizen_response.value}. Verification outcome: {verif_status.value}.",
                claim_value=verif_status.value,
                metadata={
                    "verification_id": verification_id,
                    "citizen_response": req.citizen_response.value,
                    "is_physical_resolution_verified": is_physical_verified,
                    "observed_government_status": obs_status,
                    "has_photo_evidence": bool(req.evidence_photo_url),
                },
            )
            ev_id = ev_rec.evidence_id if ev_rec else None
        except Exception as prov_err:
            logger.warning("Failed to record resolution verification provenance: %s", prov_err)

        # Step 5: Update Knowledge Graph (M6.5)
        try:
            get_knowledge_graph_service().record_resolution_verification_graph(
                case_reference_id=cvki_ref,
                verification_id=verification_id,
                citizen_response=req.citizen_response.value,
                verification_status=verif_status.value,
                is_physical_resolution_verified=is_physical_verified,
                evidence_id=ev_id,
                explanation=req.citizen_notes,
                reviewer_user_id=None,
            )
        except Exception as kg_err:
            logger.warning("Failed to record resolution verification in knowledge graph: %s", kg_err)

        # Location packaging
        loc_dict = None
        if req.latitude is not None and req.longitude is not None:
            loc_dict = {"latitude": req.latitude, "longitude": req.longitude}

        # Build persistent record
        record = CitizenResolutionVerificationRecord(
            verification_id=verification_id,
            cvki_reference_id=cvki_ref,
            integration_id=int_id,
            government_reference_id=gov_ref,
            government_status_sync_id=sync_id,
            observed_government_status=obs_status,
            citizen_user_id=citizen_user_id,
            citizen_response=req.citizen_response,
            verification_status=verif_status,
            citizen_notes=req.citizen_notes,
            evidence_photo_url=req.evidence_photo_url,
            evidence_photo_metadata=req.evidence_photo_metadata,
            location=loc_dict,
            is_physical_resolution_verified=is_physical_verified,
            provenance_evidence_id=ev_id,
            submitted_at=now,
            created_at=now,
            updated_at=now,
            history=[init_trans],
            metadata={"source": "citizen_app"},
        )
        self.repository.save_verification(record)

        # Step 6: Dispatch Notifications (M3.9)
        try:
            if req.citizen_response == CitizenResolutionResponse.STILL_UNRESOLVED:
                await trigger_resolution_verification_disputed_notification(
                    case=case,
                    citizen_response=req.citizen_response.value,
                    citizen_notes=req.citizen_notes,
                )
            else:
                await trigger_resolution_verification_submitted_notification(
                    case=case,
                    citizen_response=req.citizen_response.value,
                    verification_status=verif_status.value,
                )
        except Exception as notif_err:
            logger.warning("Failed to dispatch resolution verification notification: %s", notif_err)

        # Step 7: Structured Audit Trail (M4.8)
        try:
            coro = AuditService.record_event(
                action="resolution_verification_submitted",
                result=verif_status.value.lower(),
                actor_user_id=citizen_user_id,
                actor_role=citizen_role,
                resource_type="case",
                resource_reference_id=cvki_ref,
                metadata={
                    "verification_id": verification_id,
                    "citizen_response": req.citizen_response.value,
                    "verification_status": verif_status.value,
                    "is_physical_resolution_verified": is_physical_verified,
                    "integration_id": int_id,
                },
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(coro)
            except RuntimeError:
                asyncio.run(coro)
        except Exception as audit_err:
            logger.warning("Failed to record verification audit: %s", audit_err)

        return CitizenResolutionVerificationResponse(
            verification_id=record.verification_id,
            cvki_reference_id=record.cvki_reference_id,
            integration_id=record.integration_id,
            government_reference_id=record.government_reference_id,
            observed_government_status=record.observed_government_status,
            citizen_user_id=record.citizen_user_id,
            citizen_response=record.citizen_response,
            verification_status=record.verification_status,
            is_physical_resolution_verified=record.is_physical_resolution_verified,
            citizen_notes=record.citizen_notes,
            evidence_photo_url=record.evidence_photo_url,
            reviewer_user_id=record.reviewer_user_id,
            reviewer_notes=record.reviewer_notes,
            reviewed_at=record.reviewed_at,
            provenance_evidence_id=record.provenance_evidence_id,
            submitted_at=record.submitted_at,
            updated_at=record.updated_at,
        )

    async def review_verification(
        self,
        case: ComplaintCase,
        verification_id: str,
        req: ResolutionVerificationReviewRequest,
        reviewer_user_id: str,
        reviewer_role: str,
    ) -> CitizenResolutionVerificationResponse:
        """
        Operator or Admin review of a disputed, partially resolved, or needs-review verification record.
        """
        now = datetime.now(timezone.utc)
        record = self.repository.get_verification(verification_id)
        if not record or record.cvki_reference_id != case.reference_id:
            raise LookupError(f"Verification record '{verification_id}' for case '{case.reference_id}' was not found.")

        # State transition validation
        if req.verification_status == ResolutionVerificationStatus.PENDING:
            raise ValueError("Cannot transition a reviewed verification back to PENDING.")

        if record.verification_status == ResolutionVerificationStatus.CLOSED_UNVERIFIED and reviewer_role != UserRole.ADMIN.value:
            raise ValueError("Only an administrator can reopen a closed unverified record.")

        from_status = record.verification_status
        to_status = req.verification_status

        # Determine physical resolution verification flag
        if req.override_physical_resolution is not None:
            is_physical_verified = req.override_physical_resolution
        elif to_status == ResolutionVerificationStatus.VERIFIED_RESOLVED:
            is_physical_verified = True
        else:
            is_physical_verified = False

        # Transition record
        trans_id = f"trans_{uuid.uuid4().hex[:12]}"
        trans = ResolutionVerificationTransitionRecord(
            transition_id=trans_id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=reviewer_user_id,
            actor_role=reviewer_role,
            transition_reason=req.reviewer_notes,
            transitioned_at=now,
        )

        record.verification_status = to_status
        record.is_physical_resolution_verified = is_physical_verified
        record.reviewer_user_id = reviewer_user_id
        record.reviewer_role = reviewer_role
        record.reviewer_notes = req.reviewer_notes
        record.reviewed_at = now
        record.updated_at = now
        record.history.append(trans)

        # Update Provenance Claim (M6.4)
        try:
            prov_engine = get_provenance_engine()
            ev_rec = prov_engine.build_evidence_record(
                claim_type=ClaimType.RESOLUTION_VERIFICATION,
                case_reference=case.reference_id,
                matched_attribute="resolution_verification_status",
                source=f"Casework Reviewer: {reviewer_user_id} ({reviewer_role})",
                source_type=SourceType.ADMIN_UPDATE if reviewer_role == UserRole.ADMIN.value else SourceType.AUTHORITY_UPDATE,
                observed_at=now,
                retrieved_at=now,
                freshness="fresh",
                verification_state=VerificationState.VERIFIED if is_physical_verified else VerificationState.PARTIALLY_VERIFIED,
                explanation=f"Reviewer determination: {to_status.value}. Notes: {req.reviewer_notes}",
                claim_value=to_status.value,
                metadata={
                    "verification_id": verification_id,
                    "reviewer_user_id": reviewer_user_id,
                    "is_physical_resolution_verified": is_physical_verified,
                },
            )
            record.provenance_evidence_id = ev_rec.evidence_id if ev_rec else record.provenance_evidence_id
        except Exception as prov_err:
            logger.warning("Failed to record review provenance: %s", prov_err)

        # Update Knowledge Graph (M6.5)
        try:
            get_knowledge_graph_service().record_resolution_verification_graph(
                case_reference_id=case.reference_id,
                verification_id=verification_id,
                citizen_response=record.citizen_response.value,
                verification_status=to_status.value,
                is_physical_resolution_verified=is_physical_verified,
                evidence_id=record.provenance_evidence_id,
                explanation=req.reviewer_notes,
                reviewer_user_id=reviewer_user_id,
            )
        except Exception as kg_err:
            logger.warning("Failed to update resolution verification in knowledge graph: %s", kg_err)

        # Save record
        self.repository.save_verification(record)

        # Dispatch Notification to citizen
        try:
            await trigger_resolution_verification_reviewed_notification(
                case=case,
                verification_status=to_status.value,
                reviewer_notes=req.reviewer_notes,
            )
        except Exception as notif_err:
            logger.warning("Failed to send review notification: %s", notif_err)

        # Audit event
        try:
            coro = AuditService.record_event(
                action="resolution_verification_reviewed",
                result=to_status.value.lower(),
                actor_user_id=reviewer_user_id,
                actor_role=reviewer_role,
                resource_type="case",
                resource_reference_id=case.reference_id,
                metadata={
                    "verification_id": verification_id,
                    "from_status": from_status.value,
                    "to_status": to_status.value,
                    "is_physical_resolution_verified": is_physical_verified,
                },
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(coro)
            except RuntimeError:
                asyncio.run(coro)
        except Exception as audit_err:
            logger.warning("Failed to record review audit: %s", audit_err)

        return CitizenResolutionVerificationResponse(
            verification_id=record.verification_id,
            cvki_reference_id=record.cvki_reference_id,
            integration_id=record.integration_id,
            government_reference_id=record.government_reference_id,
            observed_government_status=record.observed_government_status,
            citizen_user_id=record.citizen_user_id,
            citizen_response=record.citizen_response,
            verification_status=record.verification_status,
            is_physical_resolution_verified=record.is_physical_resolution_verified,
            citizen_notes=record.citizen_notes,
            evidence_photo_url=record.evidence_photo_url,
            reviewer_user_id=record.reviewer_user_id,
            reviewer_notes=record.reviewer_notes,
            reviewed_at=record.reviewed_at,
            provenance_evidence_id=record.provenance_evidence_id,
            submitted_at=record.submitted_at,
            updated_at=record.updated_at,
        )

    def get_latest_verification(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[CitizenResolutionVerificationResponse]:
        """Returns the most recent verification record for a case."""
        rec = self.repository.get_latest_verification(cvki_reference_id, integration_id)
        if not rec:
            return None
        return CitizenResolutionVerificationResponse(
            verification_id=rec.verification_id,
            cvki_reference_id=rec.cvki_reference_id,
            integration_id=rec.integration_id,
            government_reference_id=rec.government_reference_id,
            observed_government_status=rec.observed_government_status,
            citizen_user_id=rec.citizen_user_id,
            citizen_response=rec.citizen_response,
            verification_status=rec.verification_status,
            is_physical_resolution_verified=rec.is_physical_resolution_verified,
            citizen_notes=rec.citizen_notes,
            evidence_photo_url=rec.evidence_photo_url,
            reviewer_user_id=rec.reviewer_user_id,
            reviewer_notes=rec.reviewer_notes,
            reviewed_at=rec.reviewed_at,
            provenance_evidence_id=rec.provenance_evidence_id,
            submitted_at=rec.submitted_at,
            updated_at=rec.updated_at,
        )

    def get_verification_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> CitizenResolutionVerificationHistoryResponse:
        """Returns chronological history of verification submissions and transitions for a case."""
        recs = self.repository.get_verification_history(cvki_reference_id, integration_id, limit)
        return CitizenResolutionVerificationHistoryResponse(
            cvki_reference_id=cvki_reference_id,
            verifications=recs,
            total=len(recs),
        )


resolution_verification_service = ResolutionVerificationService()


def get_resolution_verification_service() -> ResolutionVerificationService:
    return resolution_verification_service


def set_resolution_verification_service(service: ResolutionVerificationService) -> None:
    global resolution_verification_service
    resolution_verification_service = service
