"""
CVKI M7.3 Government Reference-ID Mapping Service.
Maintains strict separation between internal CVKI case references and external government portal tracking IDs.
Provides idempotent mapping, conflict detection, UNKNOWN_OUTCOME integration, provenance, knowledge graph, and RBAC.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
from threading import Lock
from typing import Any, Optional
import uuid

from app.core.database import (
    GOVERNMENT_REFERENCE_MAPPINGS_COLLECTION,
    get_database,
)
from app.schemas.complaint_case import ComplaintCase
from app.schemas.government_reference import (
    GovernmentReferenceListResponse,
    GovernmentReferenceMapping,
    GovernmentReferenceMappingResponse,
    ManualReferenceCreateRequest,
    ReferenceMappingState,
)
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
)
from app.services.audit import AuditService
from app.services.government_registry import government_registry

logger = logging.getLogger("cvki.government_reference")


class GovernmentReferenceRepository(ABC):
    @abstractmethod
    def save(self, mapping: GovernmentReferenceMapping) -> GovernmentReferenceMapping:
        pass

    @abstractmethod
    def get_by_id(self, mapping_id: str) -> Optional[GovernmentReferenceMapping]:
        pass

    @abstractmethod
    def find_by_case(self, cvki_reference_id: str) -> list[GovernmentReferenceMapping]:
        pass

    @abstractmethod
    def find_by_integration_and_reference(
        self, integration_id: str, government_reference_id: str
    ) -> list[GovernmentReferenceMapping]:
        pass

    @abstractmethod
    def find_by_case_and_integration(
        self, cvki_reference_id: str, integration_id: str
    ) -> Optional[GovernmentReferenceMapping]:
        pass

    @abstractmethod
    def find_by_submission(self, submission_id: str) -> Optional[GovernmentReferenceMapping]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass

    @abstractmethod
    def list_all(self, limit: int = 1000) -> list[GovernmentReferenceMapping]:
        pass


class InMemoryGovernmentReferenceRepository(GovernmentReferenceRepository):
    def __init__(self):
        self._mappings: dict[str, GovernmentReferenceMapping] = {}
        self._lock = Lock()

    def save(self, mapping: GovernmentReferenceMapping) -> GovernmentReferenceMapping:
        with self._lock:
            self._mappings[mapping.mapping_id] = mapping.model_copy(deep=True)
        return mapping

    def get_by_id(self, mapping_id: str) -> Optional[GovernmentReferenceMapping]:
        with self._lock:
            m = self._mappings.get(mapping_id)
            return m.model_copy(deep=True) if m else None

    def find_by_case(self, cvki_reference_id: str) -> list[GovernmentReferenceMapping]:
        with self._lock:
            return [
                m.model_copy(deep=True)
                for m in self._mappings.values()
                if m.cvki_reference_id == cvki_reference_id
            ]

    def find_by_integration_and_reference(
        self, integration_id: str, government_reference_id: str
    ) -> list[GovernmentReferenceMapping]:
        with self._lock:
            return [
                m.model_copy(deep=True)
                for m in self._mappings.values()
                if m.integration_id == integration_id
                and m.government_reference_id
                and m.government_reference_id.strip().lower() == government_reference_id.strip().lower()
            ]

    def find_by_case_and_integration(
        self, cvki_reference_id: str, integration_id: str
    ) -> Optional[GovernmentReferenceMapping]:
        with self._lock:
            for m in self._mappings.values():
                if m.cvki_reference_id == cvki_reference_id and m.integration_id == integration_id:
                    return m.model_copy(deep=True)
            return None

    def find_by_submission(self, submission_id: str) -> Optional[GovernmentReferenceMapping]:
        with self._lock:
            for m in self._mappings.values():
                if m.submission_id == submission_id:
                    return m.model_copy(deep=True)
            return None

    def clear(self) -> None:
        with self._lock:
            self._mappings.clear()

    def list_all(self, limit: int = 1000) -> list[GovernmentReferenceMapping]:
        with self._lock:
            return [m.model_copy(deep=True) for m in list(self._mappings.values())[:limit]]


class MongoGovernmentReferenceRepository(GovernmentReferenceRepository):
    def __init__(self):
        self._db = None

    def _get_collection(self):
        db = get_database()
        if db is None:
            raise RuntimeError("MongoDB persistence is unavailable.")
        return db[GOVERNMENT_REFERENCE_MAPPINGS_COLLECTION]

    def save(self, mapping: GovernmentReferenceMapping) -> GovernmentReferenceMapping:
        try:
            col = self._get_collection()
            doc = mapping.model_dump()
            col.replace_one({"mapping_id": mapping.mapping_id}, doc, upsert=True)
            return mapping
        except Exception as exc:
            logger.warning("MongoDB reference mapping save fallback: %s", exc)
            return mapping

    def get_by_id(self, mapping_id: str) -> Optional[GovernmentReferenceMapping]:
        try:
            col = self._get_collection()
            doc = col.find_one({"mapping_id": mapping_id})
            return GovernmentReferenceMapping(**doc) if doc else None
        except Exception:
            return None

    def find_by_case(self, cvki_reference_id: str) -> list[GovernmentReferenceMapping]:
        try:
            col = self._get_collection()
            cursor = col.find({"cvki_reference_id": cvki_reference_id})
            return [GovernmentReferenceMapping(**doc) for doc in cursor]
        except Exception:
            return []

    def find_by_integration_and_reference(
        self, integration_id: str, government_reference_id: str
    ) -> list[GovernmentReferenceMapping]:
        try:
            col = self._get_collection()
            cursor = col.find({
                "integration_id": integration_id,
                "government_reference_id": government_reference_id,
            })
            return [GovernmentReferenceMapping(**doc) for doc in cursor]
        except Exception:
            return []

    def find_by_case_and_integration(
        self, cvki_reference_id: str, integration_id: str
    ) -> Optional[GovernmentReferenceMapping]:
        try:
            col = self._get_collection()
            doc = col.find_one({"cvki_reference_id": cvki_reference_id, "integration_id": integration_id})
            return GovernmentReferenceMapping(**doc) if doc else None
        except Exception:
            return None

    def find_by_submission(self, submission_id: str) -> Optional[GovernmentReferenceMapping]:
        try:
            col = self._get_collection()
            doc = col.find_one({"submission_id": submission_id})
            return GovernmentReferenceMapping(**doc) if doc else None
        except Exception:
            return None

    def clear(self) -> None:
        try:
            col = self._get_collection()
            col.delete_many({})
        except Exception:
            pass

    def list_all(self, limit: int = 1000) -> list[GovernmentReferenceMapping]:
        try:
            col = self._get_collection()
            cursor = col.find().limit(limit)
            return [GovernmentReferenceMapping(**doc) for doc in cursor]
        except Exception:
            return []


class GovernmentReferenceService:
    """
    Core identity mapping coordinator between CVKI cases and external government portals.
    Guarantees:
    - Permanent CVKI reference immutability (never overwritten by government ID)
    - Integration-specific namespaces (no cross-portal collision)
    - Idempotent repeated observations
    - Robust conflict detection (cross-case theft, unexpected reference mutation)
    - Epistemic honesty: REFERENCE_RECEIVED != REFERENCE_CONFIRMED
    - UNKNOWN_OUTCOME integration
    """

    def __init__(self, repository: Optional[GovernmentReferenceRepository] = None):
        self.repository = repository or InMemoryGovernmentReferenceRepository()

    async def record_mapping(
        self,
        cvki_reference_id: str,
        submission_id: str,
        integration_id: str,
        government_reference_id: Optional[str] = None,
        government_reference_type: Optional[str] = None,
        government_reference_status: Optional[str] = None,
        mapping_state: ReferenceMappingState = ReferenceMappingState.UNMAPPED,
        source: str = "adapter",
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        external_case_url: Optional[str] = None,
        raw_metadata: Optional[dict[str, Any]] = None,
        case: Optional[ComplaintCase] = None,
        authority_name: Optional[str] = None,
        provenance_evidence_id: Optional[str] = None,
        skip_kg_update: bool = False,
    ) -> GovernmentReferenceMapping:
        """
        Idempotently records or updates an identity mapping between a CVKI case and a government reference.
        Validates cross-case uniqueness and detects reference conflicts.
        """
        now = datetime.now(timezone.utc)
        clean_ref = government_reference_id.strip() if government_reference_id else None

        # 1. Lookup existing mapping for this case and integration
        existing = self.repository.find_by_case_and_integration(cvki_reference_id, integration_id)

        # 2. Conflict Detection: Cross-Case Duplicate Reference
        if clean_ref:
            matches = self.repository.find_by_integration_and_reference(integration_id, clean_ref)
            for m in matches:
                if m.cvki_reference_id != cvki_reference_id:
                    # Same government reference claimed by two different CVKI cases on the same integration!
                    conflict_reason = (
                        f"Cross-case conflict: Reference '{clean_ref}' on '{integration_id}' is already "
                        f"associated with CVKI Case '{m.cvki_reference_id}' (State: {m.mapping_state})."
                    )
                    logger.error(conflict_reason)

                    # Preserve the existing mapping or create a conflicted record for the current case
                    conflicted_mapping = GovernmentReferenceMapping(
                        mapping_id=existing.mapping_id if existing else f"grm_{uuid.uuid4().hex[:12]}",
                        cvki_reference_id=cvki_reference_id,
                        submission_id=submission_id,
                        integration_id=integration_id,
                        government_reference_id=clean_ref,
                        government_reference_type=government_reference_type or "conflicted_reference",
                        government_reference_status=government_reference_status,
                        mapping_state=ReferenceMappingState.REFERENCE_CONFLICT,
                        created_at=existing.created_at if existing else now,
                        updated_at=now,
                        first_observed_at=existing.first_observed_at if (existing and existing.first_observed_at) else now,
                        last_confirmed_at=None,
                        source=source,
                        verification_state="conflicted",
                        explanation=conflict_reason,
                        external_case_url=external_case_url,
                        metadata={
                            **(raw_metadata or {}),
                            "conflict_detected": True,
                            "conflicting_case_id": m.cvki_reference_id,
                            "conflicting_mapping_id": m.mapping_id,
                        },
                        version=(existing.version + 1) if existing else 1,
                    )
                    self.repository.save(conflicted_mapping)

                    # Audit the conflict
                    await AuditService.record_event(
                        action="government_reference_conflict",
                        result="conflict_detected",
                        actor_user_id=actor_user_id,
                        actor_role=actor_role,
                        resource_type="case",
                        resource_reference_id=cvki_reference_id,
                        metadata={
                            "integration_id": integration_id,
                            "government_reference_id": clean_ref,
                            "conflicting_case_id": m.cvki_reference_id,
                            "conflict_reason": conflict_reason,
                        },
                    )

                    # Update knowledge graph with conflicted state
                    try:
                        from app.services.knowledge_graph import get_knowledge_graph_service
                        kg_svc = get_knowledge_graph_service()
                        kg_svc.record_government_reference_mapping_graph(
                            case_reference_id=cvki_reference_id,
                            submission_id=submission_id,
                            integration_id=integration_id,
                            government_reference_id=clean_ref,
                            mapping_state=ReferenceMappingState.REFERENCE_CONFLICT.value,
                            verification_state="conflicted",
                            explanation=conflict_reason,
                        )
                    except Exception as exc:
                        logger.warning("Failed to record conflicted mapping in knowledge graph: %s", exc)

                    # Trigger notification if case is provided
                    if case:
                        try:
                            from app.services.notification import trigger_gov_reference_conflict_notification
                            await trigger_gov_reference_conflict_notification(
                                case,
                                integration_id=integration_id,
                                government_reference_id=clean_ref,
                                conflict_reason=conflict_reason,
                            )
                        except Exception as exc:
                            logger.warning("Failed to fire conflict notification: %s", exc)

                    return conflicted_mapping

        # 3. Conflict Detection: Unexpected In-Place Reference Replacement
        if existing and existing.government_reference_id and clean_ref:
            if existing.government_reference_id.strip().lower() != clean_ref.lower():
                # The reference ID changed without an administrative migration reason
                replacement_conflict = (
                    f"Reference mutation conflict: Case '{cvki_reference_id}' on '{integration_id}' "
                    f"already possessed confirmed reference '{existing.government_reference_id}'. "
                    f"Unexpected replacement with '{clean_ref}' rejected."
                )
                logger.error(replacement_conflict)

                existing.mapping_state = ReferenceMappingState.REFERENCE_CONFLICT
                existing.verification_state = "conflicted"
                existing.explanation = replacement_conflict
                existing.updated_at = now
                existing.version += 1
                existing.metadata["rejected_replacement_reference"] = clean_ref
                self.repository.save(existing)

                await AuditService.record_event(
                    action="government_reference_conflict",
                    result="replacement_conflict",
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    resource_type="case",
                    resource_reference_id=cvki_reference_id,
                    metadata={
                        "integration_id": integration_id,
                        "existing_reference": existing.government_reference_id,
                        "rejected_reference": clean_ref,
                    },
                )
                return existing

        # 4. Determine Verification State & Provenance Linkage
        is_confirmed = (mapping_state == ReferenceMappingState.REFERENCE_CONFIRMED)
        v_state = "verified" if is_confirmed else (
            "unverified" if mapping_state in [
                ReferenceMappingState.REFERENCE_RECEIVED,
                ReferenceMappingState.UNVERIFIED_MANUAL_REFERENCE,
                ReferenceMappingState.SUBMISSION_PENDING,
                ReferenceMappingState.UNMAPPED,
            ] else "unavailable"
        )

        first_obs = existing.first_observed_at if existing and existing.first_observed_at else (now if clean_ref else None)
        last_conf = now if is_confirmed else (existing.last_confirmed_at if existing else None)

        defn = government_registry.get_definition(integration_id)
        display_name = defn.display_name if defn else integration_id

        explanation = (
            f"Government tracking ID '{clean_ref}' authoritatively confirmed by {display_name}."
            if is_confirmed and clean_ref
            else (
                f"Government tracking ID '{clean_ref}' received from {display_name}; awaiting authoritative confirmation."
                if mapping_state == ReferenceMappingState.REFERENCE_RECEIVED and clean_ref
                else (
                    f"Submission outcome is unknown; reconciliation required."
                    if mapping_state == ReferenceMappingState.UNKNOWN_OUTCOME
                    else f"Reference status: {mapping_state.value}"
                )
            )
        )

        mapping_id = existing.mapping_id if existing else f"grm_{uuid.uuid4().hex[:12]}"

        # 5. Build M6.4 Provenance Record if reference is confirmed and not provided
        ev_id = provenance_evidence_id or (existing.provenance_evidence_id if existing else None)
        if not ev_id and is_confirmed and clean_ref:
            try:
                from app.services.provenance_engine import get_provenance_engine
                prov_svc = get_provenance_engine()
                ev_rec = prov_svc.build_evidence_record(
                    claim_type=ClaimType.GOVERNMENT_SUBMISSION,
                    case_reference=cvki_reference_id,
                    matched_attribute="external_reference_id",
                    source=f"Government Reference Mapping ({display_name})",
                    source_type=SourceType.GOVERNMENT_ADAPTER,
                    source_url=defn.official_source_url if defn else None,
                    observed_at=now,
                    retrieved_at=now,
                    freshness="fresh",
                    verification_state=VerificationState.VERIFIED,
                    explanation=explanation,
                    claim_value=clean_ref,
                    metadata={
                        "integration_id": integration_id,
                        "submission_id": submission_id,
                        "government_reference_id": clean_ref,
                        "mapping_id": mapping_id,
                    },
                )
                ev_id = ev_rec.evidence_id if ev_rec else None
            except Exception as exc:
                logger.warning("Failed to record reference mapping provenance: %s", exc)

        # 6. Build and Save Mapping Record
        mapping = GovernmentReferenceMapping(
            mapping_id=mapping_id,
            cvki_reference_id=cvki_reference_id,
            submission_id=submission_id,
            integration_id=integration_id,
            government_reference_id=clean_ref,
            government_reference_type=government_reference_type or ("official_tracking_id" if clean_ref else None),
            government_reference_status=government_reference_status,
            mapping_state=mapping_state,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            first_observed_at=first_obs,
            last_confirmed_at=last_conf,
            source=source,
            provenance_evidence_id=ev_id,
            verification_state=v_state,
            explanation=explanation,
            external_case_url=external_case_url or (existing.external_case_url if existing else None),
            metadata={
                **(raw_metadata or {}),
                "integration_display_name": display_name,
            },
            version=(existing.version + 1) if existing else 1,
        )
        self.repository.save(mapping)

        # 7. Knowledge Graph Update (M6.5)
        if not skip_kg_update and (clean_ref or mapping_state == ReferenceMappingState.UNKNOWN_OUTCOME):
            try:
                from app.services.knowledge_graph import get_knowledge_graph_service
                kg_svc = get_knowledge_graph_service()
                kg_svc.record_government_reference_mapping_graph(
                    case_reference_id=cvki_reference_id,
                    submission_id=submission_id,
                    integration_id=integration_id,
                    government_reference_id=clean_ref,
                    mapping_state=mapping_state.value,
                    verification_state=v_state,
                    evidence_id=ev_id,
                    explanation=explanation,
                )
            except Exception as exc:
                logger.warning("Failed to record reference mapping in knowledge graph: %s", exc)

        # 8. Audit Logging
        action_name = (
            "government_reference_confirmed"
            if is_confirmed
            else (
                "government_reference_received"
                if mapping_state == ReferenceMappingState.REFERENCE_RECEIVED
                else (
                    "government_reference_unknown_outcome"
                    if mapping_state == ReferenceMappingState.UNKNOWN_OUTCOME
                    else "government_reference_mapping_updated"
                )
            )
        )
        await AuditService.record_event(
            action=action_name,
            result="success",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="case",
            resource_reference_id=cvki_reference_id,
            metadata={
                "mapping_id": mapping.mapping_id,
                "submission_id": submission_id,
                "integration_id": integration_id,
                "government_reference_id": clean_ref,
                "mapping_state": mapping_state.value,
            },
        )

        # 9. Trigger Notification if newly confirmed
        if is_confirmed and clean_ref and case:
            try:
                from app.services.notification import trigger_gov_reference_confirmed_notification
                await trigger_gov_reference_confirmed_notification(
                    case,
                    integration_id=integration_id,
                    government_reference_id=clean_ref,
                    authority_name=authority_name or display_name,
                )
            except Exception as exc:
                logger.warning("Failed to fire reference confirmed notification: %s", exc)

        return mapping

    async def record_manual_reference(
        self,
        cvki_reference_id: str,
        integration_id: str,
        req: ManualReferenceCreateRequest,
        actor_user_id: str,
        actor_role: str,
        case: Optional[ComplaintCase] = None,
    ) -> GovernmentReferenceMapping:
        """
        Records an administrative manual government reference entry.
        Strictly enters UNVERIFIED_MANUAL_REFERENCE with verification_state="unverified".
        Never marked as confirmed until verified upstream.
        """
        clean_ref = req.government_reference_id.strip()
        now = datetime.now(timezone.utc)

        # Cross-case conflict check
        matches = self.repository.find_by_integration_and_reference(integration_id, clean_ref)
        for m in matches:
            if m.cvki_reference_id != cvki_reference_id:
                conflict_reason = (
                    f"Cannot manually link reference '{clean_ref}': already mapped to "
                    f"CVKI Case '{m.cvki_reference_id}' on '{integration_id}'."
                )
                logger.error(conflict_reason)
                raise ValueError(conflict_reason)

        existing = self.repository.find_by_case_and_integration(cvki_reference_id, integration_id)
        mapping_id = existing.mapping_id if existing else f"grm_{uuid.uuid4().hex[:12]}"
        submission_id = existing.submission_id if existing else f"manual_sub_{uuid.uuid4().hex[:8]}"

        defn = government_registry.get_definition(integration_id)
        display_name = defn.display_name if defn else integration_id

        explanation = (
            f"Manual reference '{clean_ref}' recorded by {actor_role} ({actor_user_id}). "
            f"Reason: {req.reason}. Note: Unverified until authoritative government confirmation."
        )

        mapping = GovernmentReferenceMapping(
            mapping_id=mapping_id,
            cvki_reference_id=cvki_reference_id,
            submission_id=submission_id,
            integration_id=integration_id,
            government_reference_id=clean_ref,
            government_reference_type=req.government_reference_type,
            government_reference_status="manual_unverified",
            mapping_state=ReferenceMappingState.UNVERIFIED_MANUAL_REFERENCE,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            first_observed_at=now,
            last_confirmed_at=None,
            source=f"manual:{actor_user_id}",
            verification_state="unverified",
            explanation=explanation,
            metadata={
                "entered_by": actor_user_id,
                "entered_by_role": actor_role,
                "reason": req.reason,
                "notes": req.notes,
                "integration_display_name": display_name,
            },
            version=(existing.version + 1) if existing else 1,
        )
        self.repository.save(mapping)

        await AuditService.record_event(
            action="government_reference_manual_entry",
            result="success",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="case",
            resource_reference_id=cvki_reference_id,
            metadata={
                "mapping_id": mapping.mapping_id,
                "integration_id": integration_id,
                "government_reference_id": clean_ref,
                "reason": req.reason,
            },
        )
        return mapping

    def get_case_mappings(self, cvki_reference_id: str) -> GovernmentReferenceListResponse:
        """Retrieves safe normalized list of reference mappings for a CVKI case."""
        raw_list = self.repository.find_by_case(cvki_reference_id)
        responses = [self._to_response(m) for m in raw_list]
        return GovernmentReferenceListResponse(
            cvki_reference_id=cvki_reference_id,
            mappings=responses,
            total=len(responses),
        )

    def get_mapping(
        self, cvki_reference_id: str, integration_id: str
    ) -> Optional[GovernmentReferenceMappingResponse]:
        """Retrieves safe normalized reference mapping for a specific integration."""
        raw = self.repository.find_by_case_and_integration(cvki_reference_id, integration_id)
        return self._to_response(raw) if raw else None

    def _to_response(self, m: GovernmentReferenceMapping) -> GovernmentReferenceMappingResponse:
        defn = government_registry.get_definition(m.integration_id)
        display_name = defn.display_name if defn else m.integration_id
        is_auth = (m.mapping_state == ReferenceMappingState.REFERENCE_CONFIRMED)
        is_conflict = (m.mapping_state == ReferenceMappingState.REFERENCE_CONFLICT)

        return GovernmentReferenceMappingResponse(
            mapping_id=m.mapping_id,
            cvki_reference_id=m.cvki_reference_id,
            submission_id=m.submission_id,
            integration_id=m.integration_id,
            integration_display_name=display_name,
            government_reference_id=m.government_reference_id,
            government_reference_type=m.government_reference_type,
            government_reference_status=m.government_reference_status,
            mapping_state=m.mapping_state,
            verification_state=m.verification_state,
            first_observed_at=m.first_observed_at,
            last_confirmed_at=m.last_confirmed_at,
            source=m.source,
            explanation=m.explanation,
            external_case_url=m.external_case_url,
            provenance_evidence_id=m.provenance_evidence_id,
            is_authoritative=is_auth,
            conflict_detected=is_conflict,
            conflict_details=m.explanation if is_conflict else None,
            version=m.version,
        )


# Global singleton instance
government_reference_service = GovernmentReferenceService()


def get_government_reference_service() -> GovernmentReferenceService:
    return government_reference_service


def set_government_reference_service(service: GovernmentReferenceService) -> None:
    global government_reference_service
    government_reference_service = service
