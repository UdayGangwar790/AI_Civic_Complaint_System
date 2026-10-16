from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
from threading import Lock
from typing import Any, Optional
import uuid

from app.core.database import EVIDENCE_RECORDS_COLLECTION, get_database
from app.schemas.complaint_case import ComplaintCase
from app.schemas.provenance import (
    CaseProvenanceResponse,
    ClaimType,
    EvidenceRecord,
    SourceType,
    VerificationState,
    calculate_evidence_hash,
)
from app.services.authority_registry import is_safe_official_url

logger = logging.getLogger("cvki.services.provenance_engine")


class ProvenanceRepository(ABC):
    @abstractmethod
    def save(self, record: EvidenceRecord) -> EvidenceRecord:
        pass

    @abstractmethod
    def find_by_case(self, reference_id: str) -> list[EvidenceRecord]:
        pass

    @abstractmethod
    def find_by_id(self, evidence_id: str) -> Optional[EvidenceRecord]:
        pass

    @abstractmethod
    def find_history(self, reference_id: str, claim_type: ClaimType) -> list[EvidenceRecord]:
        pass

    @abstractmethod
    def invalidate(self, evidence_id: str, reason: str) -> Optional[EvidenceRecord]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryProvenanceRepository(ProvenanceRepository):
    """Thread-safe in-memory repository for unit tests and offline operation."""

    def __init__(self):
        self._records: dict[str, EvidenceRecord] = {}
        self._lock = Lock()

    def save(self, record: EvidenceRecord) -> EvidenceRecord:
        with self._lock:
            self._records[record.evidence_id] = record.model_copy(deep=True)
        return record

    def save_record(self, record: EvidenceRecord) -> EvidenceRecord:
        return self.save(record)

    def find_by_case(self, reference_id: str) -> list[EvidenceRecord]:
        with self._lock:
            return [
                r.model_copy(deep=True)
                for r in self._records.values()
                if r.case_reference == reference_id and r.status == "active"
            ]

    def find_by_id(self, evidence_id: str) -> Optional[EvidenceRecord]:
        with self._lock:
            record = self._records.get(evidence_id)
            return record.model_copy(deep=True) if record else None

    def find_history(self, reference_id: str, claim_type: ClaimType) -> list[EvidenceRecord]:
        with self._lock:
            matching = [
                r.model_copy(deep=True)
                for r in self._records.values()
                if r.case_reference == reference_id and r.claim_type == claim_type
            ]
            return sorted(matching, key=lambda x: x.version, reverse=True)

    def get_history_for_claim(self, case_reference: str, claim_type: ClaimType) -> list[EvidenceRecord]:
        return self.find_history(case_reference, claim_type)

    def invalidate(self, evidence_id: str, reason: str) -> Optional[EvidenceRecord]:
        with self._lock:
            record = self._records.get(evidence_id)
            if not record:
                return None
            updated_meta = dict(record.metadata or {})
            updated_meta["invalidation_reason"] = reason
            updated = record.model_copy(
                update={
                    "status": "invalidated",
                    "verification_state": VerificationState.NOT_VERIFIED,
                    "invalidation_reason": reason,
                    "metadata": updated_meta,
                }
            )
            self._records[evidence_id] = updated
            return updated.model_copy(deep=True)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


class MongoProvenanceRepository(ProvenanceRepository):
    """MongoDB persistence repository for production evidence records."""

    def __init__(self, fallback: Optional[InMemoryProvenanceRepository] = None):
        self._fallback = fallback or InMemoryProvenanceRepository()

    def save(self, record: EvidenceRecord) -> EvidenceRecord:
        self._fallback.save(record)
        db = get_database()
        if db is not None:
            try:
                doc = record.model_dump(mode="python")
                db.sync_command(
                    lambda: db.delegate[EVIDENCE_RECORDS_COLLECTION].replace_one(
                        {"evidence_id": record.evidence_id}, doc, upsert=True
                    )
                )
            except Exception as exc:
                logger.warning("Failed to persist evidence record to MongoDB (%s).", exc)
        return record

    def find_by_case(self, reference_id: str) -> list[EvidenceRecord]:
        db = get_database()
        if db is None:
            return self._fallback.find_by_case(reference_id)
        try:
            cursor = db.sync_command(
                lambda: list(
                    db.delegate[EVIDENCE_RECORDS_COLLECTION].find(
                        {"case_reference": reference_id, "status": "active"}
                    )
                )
            )
            if not cursor:
                return self._fallback.find_by_case(reference_id)
            return [EvidenceRecord(**doc) for doc in cursor]
        except Exception as exc:
            logger.warning("Mongo evidence lookup failed (%s); using fallback.", exc)
            return self._fallback.find_by_case(reference_id)

    def find_by_id(self, evidence_id: str) -> Optional[EvidenceRecord]:
        db = get_database()
        if db is None:
            return self._fallback.find_by_id(evidence_id)
        try:
            doc = db.sync_command(
                lambda: db.delegate[EVIDENCE_RECORDS_COLLECTION].find_one({"evidence_id": evidence_id})
            )
            if not doc:
                return self._fallback.find_by_id(evidence_id)
            return EvidenceRecord(**doc)
        except Exception as exc:
            logger.warning("Mongo evidence lookup failed (%s); using fallback.", exc)
            return self._fallback.find_by_id(evidence_id)

    def find_history(self, reference_id: str, claim_type: ClaimType) -> list[EvidenceRecord]:
        db = get_database()
        if db is None:
            return self._fallback.find_history(reference_id, claim_type)
        try:
            cursor = db.sync_command(
                lambda: list(
                    db.delegate[EVIDENCE_RECORDS_COLLECTION].find(
                        {"case_reference": reference_id, "claim_type": claim_type.value}
                    ).sort("version", -1)
                )
            )
            if not cursor:
                return self._fallback.find_history(reference_id, claim_type)
            return [EvidenceRecord(**doc) for doc in cursor]
        except Exception as exc:
            logger.warning("Mongo evidence history lookup failed (%s); using fallback.", exc)
            return self._fallback.find_history(reference_id, claim_type)

    def invalidate(self, evidence_id: str, reason: str) -> Optional[EvidenceRecord]:
        self._fallback.invalidate(evidence_id, reason)
        db = get_database()
        if db is not None:
            try:
                db.sync_command(
                    lambda: db.delegate[EVIDENCE_RECORDS_COLLECTION].update_one(
                        {"evidence_id": evidence_id},
                        {
                            "$set": {
                                "status": "invalidated",
                                "verification_state": VerificationState.NOT_VERIFIED.value,
                                "invalidation_reason": reason,
                            }
                        },
                    )
                )
            except Exception as exc:
                logger.warning("Failed to update evidence invalidation in MongoDB (%s).", exc)
        return self.find_by_id(evidence_id)

    def clear(self) -> None:
        self._fallback.clear()
        db = get_database()
        if db is not None:
            try:
                db.sync_command(lambda: db.delegate[EVIDENCE_RECORDS_COLLECTION].delete_many({}))
            except Exception as exc:
                logger.warning("Failed to clear MongoDB evidence records (%s).", exc)


class EvidenceProvenanceEngine:
    """
    Evidence Provenance Engine.
    Ensures all civic intelligence claims are traceable to verified sources,
    enforces builder verification safety, sanitizes URLs against SSRF,
    and supports append-oriented evidence versioning.
    """

    def __init__(self, repository: Optional[ProvenanceRepository] = None):
        self.repository = repository or MongoProvenanceRepository()

    def build_evidence_record(
        self,
        claim_type: ClaimType,
        source: str,
        source_type: SourceType,
        explanation: str,
        matched_attribute: Optional[str] = None,
        case_reference: Optional[str] = None,
        source_url: Optional[str] = None,
        provider: Optional[str] = None,
        observed_at: Optional[datetime] = None,
        retrieved_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        freshness: str = "unknown",
        verification_state: VerificationState = VerificationState.NOT_VERIFIED,
        status: str = "active",
        version: int = 1,
        claim_value: Any = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> EvidenceRecord:
        """
        Creates and stores a validated EvidenceRecord.
        Applies SSRF security on source URLs and enforces builder/causal safety rules.
        """
        meta = dict(metadata or {})
        explanation = str(explanation or "")

        # URL SSRF Validation
        sanitized_url = None
        if source_url:
            is_safe, reason = is_safe_official_url(source_url)
            if is_safe:
                sanitized_url = source_url
            else:
                meta["source_url_rejection_reason"] = reason
                logger.warning("Evidence source URL '%s' rejected by SSRF guard: %s", source_url, reason)

        # Enforce Builder Evidence Safety (Section 12)
        # Builder claims are ONLY accepted with explicit tender, concession, or contract registers
        if claim_type == ClaimType.BUILDER_OR_CONTRACTOR:
            if source_type not in {SourceType.TENDER_REGISTRY, SourceType.CONCESSION_REGISTRY}:
                verification_state = VerificationState.NOT_VERIFIED
                explanation = (
                    "Safety Rule: Builder or contractor attribution cannot be inferred from maintenance authority or road owner; "
                    "requires explicit tender or concession registry verification."
                )

        # Enforce Non-Causal Explanation Policy for Environmental Data
        if claim_type in {ClaimType.WEATHER_CONTEXT, ClaimType.RAINFALL_CONTEXT}:
            explanation_lower = explanation.lower()
            if any(w in explanation_lower for w in ("cause", "caused", "causing", "responsible for", "due to")):
                explanation = "Weather conditions are consistent with recent rainfall (contextual observations only; does not establish causation)."

        # Compute deterministic fingerprint
        evidence_hash = calculate_evidence_hash(
            claim_type=claim_type.value,
            matched_attribute=matched_attribute,
            source=source,
            source_type=source_type.value,
            value=claim_value if claim_value is not None else explanation,
        )

        record = EvidenceRecord(
            evidence_id=f"ev_{uuid.uuid4().hex[:16]}",
            case_reference=case_reference,
            claim_type=claim_type,
            matched_attribute=matched_attribute,
            source=source,
            source_type=source_type,
            source_url=sanitized_url,
            provider=provider,
            observed_at=observed_at,
            retrieved_at=retrieved_at or datetime.now(timezone.utc),
            expires_at=expires_at,
            freshness=freshness,
            status=status,
            verification_state=verification_state,
            explanation=explanation,
            evidence_hash=evidence_hash,
            version=version,
            metadata=meta,
        )

        return self.repository.save(record)

    def generate_case_provenance_chain(
        self,
        case: ComplaintCase,
        external_context: Optional[dict[str, Any]] = None,
        intelligence: Optional[Any] = None,
    ) -> CaseProvenanceResponse:
        """
        Builds the complete end-to-end provenance chain for a given persisted case.
        """
        records: list[EvidenceRecord] = []
        now = datetime.now(timezone.utc)
        ref = case.reference_id

        # 1. Detection Evidence
        detection_rec = self.build_evidence_record(
            claim_type=ClaimType.DETECTION,
            case_reference=ref,
            matched_attribute="issue_category",
            source="YOLOv8 M1.13 Detection Model",
            source_type=SourceType.CV_MODEL,
            provider="CVKI Computer Vision Subsystem",
            observed_at=case.created_at,
            retrieved_at=case.created_at,
            freshness="fresh",
            verification_state=VerificationState.VERIFIED,
            explanation=f"Computer vision model detected '{case.issue.class_name}' with {round(case.issue.confidence * 100)}% confidence.",
            claim_value=case.issue.class_name,
            metadata={"confidence": case.issue.confidence, "model_version": "M1.13-yolov8n"},
        )
        records.append(detection_rec)

        # 2. Location & Road Evidence
        loc = case.location
        if loc.latitude is not None and loc.longitude is not None:
            loc_rec = self.build_evidence_record(
                claim_type=ClaimType.LOCATION,
                case_reference=ref,
                matched_attribute="coordinates",
                source="GPS / Geolocation",
                source_type=SourceType.GPS,
                observed_at=case.created_at,
                retrieved_at=case.created_at,
                freshness="fresh",
                verification_state=VerificationState.VERIFIED if loc.accuracy_m and loc.accuracy_m <= 25 else VerificationState.PARTIALLY_VERIFIED,
                explanation=f"Reported coordinates: ({loc.latitude:.4f}, {loc.longitude:.4f})"
                + (f" with ±{round(loc.accuracy_m)}m GPS accuracy" if loc.accuracy_m else "")
                + ".",
                claim_value=[loc.latitude, loc.longitude],
                metadata={"accuracy_m": loc.accuracy_m, "city": loc.city, "state": loc.state},
            )
            records.append(loc_rec)

        if loc.road:
            road_rec = self.build_evidence_record(
                claim_type=ClaimType.ROAD_IDENTITY,
                case_reference=ref,
                matched_attribute="road_name",
                source="OpenStreetMap Nominatim Reverse Geocoding",
                source_type=SourceType.GEOCODER,
                retrieved_at=case.created_at,
                freshness="fresh",
                verification_state=VerificationState.PARTIALLY_VERIFIED,
                explanation=f"Identified road corridor: '{loc.road}' based on coordinate reverse geocoding.",
                claim_value=loc.road,
                metadata={"road": loc.road, "area": loc.area, "match_quality": "EXACT" if loc.road else "APPROXIMATE"},
            )
            records.append(road_rec)

        # 3. Authority Intelligence Evidence
        auth = case.authority
        if auth:
            if auth.road_owner and auth.road_owner.name:
                owner_rec = self.build_evidence_record(
                    claim_type=ClaimType.ROAD_OWNER,
                    case_reference=ref,
                    matched_attribute="road_owner",
                    source=auth.road_owner.source or "Official Register",
                    source_type=SourceType.GOVERNMENT_REGISTRY,
                    source_url=auth.road_owner.official_portal_url,
                    retrieved_at=auth.resolved_at or now,
                    freshness=auth.freshness,
                    verification_state=VerificationState.VERIFIED if auth.authority_status == "verified" else VerificationState.PARTIALLY_VERIFIED,
                    explanation=f"Road owner verified as '{auth.road_owner.name}' ({auth.road_owner.type}).",
                    claim_value=auth.road_owner.name,
                )
                records.append(owner_rec)

            if auth.maintenance_authority and auth.maintenance_authority.name:
                maint_rec = self.build_evidence_record(
                    claim_type=ClaimType.MAINTENANCE_AUTHORITY,
                    case_reference=ref,
                    matched_attribute="maintenance_authority",
                    source=auth.maintenance_authority.source or "Official Register",
                    source_type=SourceType.GOVERNMENT_REGISTRY,
                    source_url=auth.maintenance_authority.official_portal_url,
                    retrieved_at=auth.resolved_at or now,
                    freshness=auth.freshness,
                    verification_state=VerificationState.VERIFIED if auth.authority_status == "verified" else VerificationState.PARTIALLY_VERIFIED,
                    explanation=f"Maintenance authority verified as '{auth.maintenance_authority.name}' ({auth.maintenance_authority.type}).",
                    claim_value=auth.maintenance_authority.name,
                )
                records.append(maint_rec)
            else:
                maint_rec = self.build_evidence_record(
                    claim_type=ClaimType.MAINTENANCE_AUTHORITY,
                    case_reference=ref,
                    matched_attribute="maintenance_authority",
                    source="Official Register",
                    source_type=SourceType.GOVERNMENT_REGISTRY,
                    retrieved_at=now,
                    freshness="unknown",
                    verification_state=VerificationState.NOT_VERIFIED,
                    explanation="Maintenance authority is not verified by official road registries.",
                    claim_value="Unassigned / Unverified",
                )
                records.append(maint_rec)

            if auth.builder_or_contractor:
                builder_name = auth.builder_or_contractor.name if hasattr(auth.builder_or_contractor, "name") else str(auth.builder_or_contractor)
                src = getattr(auth.builder_or_contractor, "source", None) or ""
                is_tender = "tender" in src.lower() or "concession" in src.lower()
                builder_rec = self.build_evidence_record(
                    claim_type=ClaimType.BUILDER_OR_CONTRACTOR,
                    case_reference=ref,
                    matched_attribute="builder_or_contractor",
                    source=src or "Contract Registry",
                    source_type=SourceType.TENDER_REGISTRY if is_tender else SourceType.GOVERNMENT_REGISTRY,
                    retrieved_at=auth.resolved_at or now,
                    freshness=auth.freshness,
                    verification_state=VerificationState.VERIFIED if is_tender else VerificationState.NOT_VERIFIED,
                    explanation=f"Builder or contractor designated as '{builder_name}'.",
                    claim_value=builder_name,
                )
                records.append(builder_rec)

        # External Civic Context (M6.3)
        if external_context:
            weather = external_context.get("weather")
            if weather:
                w_status = weather.get("status", "live")
                w_temp = weather.get("temperature_c", 25.0)
                w_cond = weather.get("condition", "Observed")
                w_src = weather.get("source", "Weather Provider")
                records.append(
                    self.build_evidence_record(
                        claim_type=ClaimType.WEATHER_CONTEXT,
                        case_reference=ref,
                        matched_attribute="weather",
                        source=w_src,
                        source_type=SourceType.WEATHER_PROVIDER,
                        retrieved_at=now,
                        freshness=w_status,
                        verification_state=VerificationState.VERIFIED if "live" in w_status else VerificationState.PARTIALLY_VERIFIED,
                        explanation=f"Observed temperature {w_temp}°C with {w_cond} conditions.",
                        claim_value=weather,
                        metadata=weather,
                    )
                )

            rainfall = external_context.get("rainfall")
            if rainfall:
                r_status = rainfall.get("status", "live")
                r_mm = rainfall.get("window_rainfall_mm", 0.0)
                r_intensity = rainfall.get("rainfall_intensity", "none")
                r_src = rainfall.get("source", "Weather Provider")
                records.append(
                    self.build_evidence_record(
                        claim_type=ClaimType.RAINFALL_CONTEXT,
                        case_reference=ref,
                        matched_attribute="rainfall_context",
                        source=r_src,
                        source_type=SourceType.WEATHER_PROVIDER,
                        retrieved_at=now,
                        freshness=r_status,
                        verification_state=VerificationState.VERIFIED if "live" in r_status else VerificationState.PARTIALLY_VERIFIED,
                        explanation=f"Recorded {r_mm} mm rainfall ({r_intensity}) within observation window. Weather conditions are consistent with recent rainfall.",
                        claim_value=rainfall,
                        metadata=rainfall,
                    )
                )

        # 4. System-Derived Intelligence (M5.2 Recurrence / Hotspot)
        rec_data = intelligence.recurrence if intelligence and hasattr(intelligence, "recurrence") else getattr(case, "recurrence_analysis", None)
        if rec_data and getattr(rec_data, "recurrence_detected", False):
            rec_count = getattr(rec_data, "recurrence_count", 0)
            rec_window = getattr(rec_data, "recurrence_window_days", 180)
            rel_ids = getattr(rec_data, "related_historical_case_ids", [])
            rec_evidence = self.build_evidence_record(
                claim_type=ClaimType.RECURRENCE,
                case_reference=ref,
                matched_attribute="recurrence",
                source="CVKI Historical Case Repository",
                source_type=SourceType.CVKI_CASE_HISTORY,
                retrieved_at=now,
                freshness="fresh",
                verification_state=VerificationState.SYSTEM_DERIVED,
                explanation=f"CVKI-derived intelligence: detected {rec_count} recurring reports along this corridor within {rec_window} days (spatial window: 250m).",
                claim_value=rec_count,
                metadata={"related_case_count": rec_count, "related_case_ids": rel_ids, "window_days": rec_window},
            )
            records.append(rec_evidence)

        if intelligence and getattr(intelligence, "hotspot_detected", False):
            hot_count = getattr(intelligence, "recent_location_case_count", 0)
            unres_count = getattr(intelligence, "recent_location_unresolved_count", 0)
            hot_win = getattr(intelligence, "hotspot_window_days", 90)
            hot_evidence = self.build_evidence_record(
                claim_type=ClaimType.HOTSPOT_CONTEXT,
                case_reference=ref,
                matched_attribute="hotspot_context",
                source="CVKI Historical Case Repository",
                source_type=SourceType.CVKI_CASE_HISTORY,
                retrieved_at=now,
                freshness="fresh",
                verification_state=VerificationState.SYSTEM_DERIVED,
                explanation=f"System identified localized concentration: {hot_count} reports in {hot_win} days ({unres_count} unresolved).",
                claim_value=hot_count,
                metadata={"recent_case_count": hot_count, "unresolved_count": unres_count, "window_days": hot_win},
            )
            records.append(hot_evidence)

        # 5. Priority Evidence
        prio = getattr(case, "priority_analysis", None)
        if prio:
            p_score = getattr(prio, "priority_score", 0)
            p_level = getattr(prio, "priority_level", "Standard")
            p_reasons = getattr(prio, "reasons", [])
            prio_rec = self.build_evidence_record(
                claim_type=ClaimType.PRIORITY,
                case_reference=ref,
                matched_attribute="priority_score",
                source="CVKI Priority & Risk Engine",
                source_type=SourceType.SYSTEM_DERIVED,
                retrieved_at=now,
                freshness="fresh",
                verification_state=VerificationState.SYSTEM_DERIVED,
                explanation=f"Calculated priority {p_level} (score: {p_score}) based on civic factors: {', '.join(p_reasons)}.",
                claim_value=p_score,
                metadata={"level": p_level, "score": p_score, "priority_score": p_score, "reasons": p_reasons},
            )
            records.append(prio_rec)

        # 6. Resolution Evidence
        res_state = getattr(intelligence, "resolution_evidence_state", None) if intelligence else None
        if res_state and isinstance(res_state, str):
            res_expl = str(getattr(intelligence, "resolution_evidence_explanation", "Resolution evidence analyzed."))
            res_ver = VerificationState.VERIFIED if res_state == "evidence_supported" else VerificationState.PARTIALLY_VERIFIED
            records.append(
                self.build_evidence_record(
                    claim_type=ClaimType.RESOLUTION_EVIDENCE,
                    case_reference=ref,
                    matched_attribute="resolution_evidence",
                    source="CVKI Case Resolution Records",
                    source_type=SourceType.SYSTEM_DERIVED,
                    retrieved_at=now,
                    freshness="fresh",
                    verification_state=res_ver,
                    explanation=res_expl,
                    claim_value=res_state,
                    metadata={"resolution_evidence_state": res_state},
                )
            )
        elif getattr(case, "resolution_evidence", None):
            for rev in case.resolution_evidence:
                res_rec = self.build_evidence_record(
                    claim_type=ClaimType.RESOLUTION_EVIDENCE,
                    case_reference=ref,
                    matched_attribute="resolution_note",
                    source=f"Civic Staff ({rev.recorded_by_role})",
                    source_type=SourceType.AUTHORITY_UPDATE if rev.recorded_by_role == "authority" else SourceType.ADMIN_UPDATE,
                    observed_at=rev.recorded_at,
                    retrieved_at=rev.recorded_at,
                    freshness="fresh",
                    verification_state=VerificationState.VERIFIED,
                    explanation=f"Resolution recorded by {rev.recorded_by_role}: '{rev.note}'.",
                    claim_value=rev.note,
                )
                records.append(res_rec)

        # Group by category
        claim_groups: dict[str, list[EvidenceRecord]] = {}
        for r in records:
            claim_groups.setdefault(r.claim_type.value, []).append(r)

        # Determine overall summary state
        has_verified_auth = any(
            r.claim_type == ClaimType.MAINTENANCE_AUTHORITY and r.verification_state == VerificationState.VERIFIED
            for r in records
        )
        has_verified_det = any(
            r.claim_type == ClaimType.DETECTION and r.verification_state == VerificationState.VERIFIED
            for r in records
        )
        if has_verified_auth and has_verified_det:
            summary_state = VerificationState.VERIFIED
        elif has_verified_det:
            summary_state = VerificationState.PARTIALLY_VERIFIED
        else:
            summary_state = VerificationState.NOT_VERIFIED

        limitations = [
            "Provenance establishes traceability of system claims to underlying data sources; it does not replace statutory ground verification.",
            "Builder attribution requires explicit concession/tender documentation and cannot be assumed from road ownership.",
            "Environmental data provides contextual background and does not establish causation.",
        ]

        return CaseProvenanceResponse(
            reference_id=case.reference_id,
            generated_at=now,
            summary_verification_state=summary_state,
            claims=records,
            claim_groups=claim_groups,
            limitations=limitations,
        )

    def get_evidence_by_id(self, evidence_id: str) -> Optional[EvidenceRecord]:
        """Lookup an evidence record by its unique ID."""
        return self.repository.find_by_id(evidence_id)

    def invalidate_evidence(
        self,
        evidence_id: str,
        reason: str,
        actor_user_id: str = "system",
        actor_role: str = "admin",
    ) -> Optional[EvidenceRecord]:
        """
        Invalidates a specific evidence record and records an audit log event.
        """
        updated = self.repository.invalidate(evidence_id, reason)
        if updated:
            try:
                from app.services.audit import AuditService
                import asyncio
                # Attempt to schedule audit event
                coro = AuditService.record_event(
                    action="evidence_invalidated",
                    result="success",
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    resource_type="evidence_record",
                    resource_reference_id=evidence_id,
                    metadata={"reason": reason, "case_reference": updated.case_reference},
                )
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(coro)
                except RuntimeError:
                    asyncio.run(coro)
            except Exception as audit_err:
                logger.debug("Non-fatal audit logging notice: %s", audit_err)
        return updated


provenance_engine = EvidenceProvenanceEngine()


def get_provenance_engine() -> EvidenceProvenanceEngine:
    """Returns the singleton EvidenceProvenanceEngine instance."""
    return provenance_engine


def set_provenance_engine(engine: EvidenceProvenanceEngine) -> None:
    """Overrides the global EvidenceProvenanceEngine instance (useful for testing)."""
    global provenance_engine
    provenance_engine = engine
