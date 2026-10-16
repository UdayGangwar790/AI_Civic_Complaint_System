"""
CVKI M7.5 Evidence-Based Escalation Engine Service.
Provides a deterministic, policy-driven escalation decision engine linking confirmed government references,
synchronized external statuses, status freshness, and verified evidence.
Strictly separates observed external government facts from system-derived escalation decisions.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import logging
from threading import Lock
from typing import Any, Optional
import uuid

from app.core.database import (
    ESCALATION_DECISIONS_COLLECTION,
    ESCALATION_POLICIES_COLLECTION,
    get_database,
)
from app.schemas.complaint_case import ComplaintCase
from app.schemas.escalation import (
    EscalationAction,
    EscalationDecisionRecord,
    EscalationHistoryResponse,
    EscalationLevel,
    EscalationPolicy,
    EscalationPolicyListResponse,
    EscalationReasonCode,
    EscalationResponse,
    EscalationState,
)
from app.schemas.government_integration import (
    IntegrationState,
    NormalizedGovernmentStatus,
)
from app.schemas.government_reference import ReferenceMappingState
from app.schemas.government_status import FreshnessState, SynchronizationState
from app.schemas.provenance import (
    ClaimType,
    SourceType,
    VerificationState,
)
from app.services.audit import AuditService
from app.services.government_reference_service import get_government_reference_service
from app.services.government_registry import government_registry
from app.services.government_status_service import get_government_status_service
from app.services.notification import trigger_escalation_recommended_notification

logger = logging.getLogger("cvki.escalation")


def _get_default_policies() -> list[EscalationPolicy]:
    """
    Returns standard engineering default escalation policies.
    Epistemological rule: Clearly labeled as ENGINEERING DEFAULT / CONFIGURABLE POLICY,
    NOT official government SLAs unless verified from official gazette.
    """
    now = datetime.now(timezone.utc)
    return [
        EscalationPolicy(
            policy_id="default_no_status_72h",
            integration_id="*",
            condition_normalized_status=None,
            minimum_age_hours=72.0,
            escalation_action=EscalationAction.FOLLOW_UP,
            escalation_level=EscalationLevel.FOLLOW_UP,
            cooldown_hours=24.0,
            max_escalation_count=3,
            priority=50,
            description="Engineering default: Follow-up recommended when no external status observation is received within 72h of confirmed reference.",
            is_official_sla=False,
            created_at=now,
            updated_at=now,
        ),
        EscalationPolicy(
            policy_id="default_registered_72h",
            integration_id="*",
            condition_normalized_status=NormalizedGovernmentStatus.REGISTERED,
            minimum_age_hours=72.0,
            escalation_action=EscalationAction.FOLLOW_UP,
            escalation_level=EscalationLevel.FOLLOW_UP,
            cooldown_hours=24.0,
            max_escalation_count=3,
            priority=100,
            description="Engineering default: Follow-up recommended when case remains in REGISTERED status beyond 72 hours without progression.",
            is_official_sla=False,
            created_at=now,
            updated_at=now,
        ),
        EscalationPolicy(
            policy_id="default_under_review_120h",
            integration_id="*",
            condition_normalized_status=NormalizedGovernmentStatus.UNDER_REVIEW,
            minimum_age_hours=120.0,
            escalation_action=EscalationAction.FOLLOW_UP,
            escalation_level=EscalationLevel.FOLLOW_UP,
            cooldown_hours=48.0,
            max_escalation_count=3,
            priority=110,
            description="Engineering default: Follow-up recommended when case remains UNDER_REVIEW beyond 120 hours (5 days).",
            is_official_sla=False,
            created_at=now,
            updated_at=now,
        ),
        EscalationPolicy(
            policy_id="default_assigned_96h",
            integration_id="*",
            condition_normalized_status=NormalizedGovernmentStatus.ASSIGNED,
            minimum_age_hours=96.0,
            escalation_action=EscalationAction.FOLLOW_UP,
            escalation_level=EscalationLevel.FOLLOW_UP,
            cooldown_hours=24.0,
            max_escalation_count=3,
            priority=120,
            description="Engineering default: Follow-up recommended when case remains ASSIGNED without commencement beyond 96 hours (4 days).",
            is_official_sla=False,
            created_at=now,
            updated_at=now,
        ),
        EscalationPolicy(
            policy_id="default_in_progress_168h",
            integration_id="*",
            condition_normalized_status=NormalizedGovernmentStatus.IN_PROGRESS,
            minimum_age_hours=168.0,
            escalation_action=EscalationAction.ESCALATE,
            escalation_level=EscalationLevel.ESCALATE,
            cooldown_hours=48.0,
            max_escalation_count=3,
            priority=130,
            description="Engineering default: Formal escalation recommended when physical work remains IN_PROGRESS beyond 168 hours (7 days).",
            is_official_sla=False,
            created_at=now,
            updated_at=now,
        ),
        EscalationPolicy(
            policy_id="default_needs_information",
            integration_id="*",
            condition_normalized_status=NormalizedGovernmentStatus.NEEDS_INFORMATION,
            minimum_age_hours=0.0,
            escalation_action=EscalationAction.CITIZEN_ACTION_REQUIRED,
            escalation_level=EscalationLevel.FOLLOW_UP,
            cooldown_hours=12.0,
            max_escalation_count=5,
            priority=20,
            description="Engineering default: Prompts citizen action when authority seeks clarification or additional evidence.",
            is_official_sla=False,
            created_at=now,
            updated_at=now,
        ),
    ]


class EscalationRepository(ABC):
    @abstractmethod
    def save_decision(self, decision: EscalationDecisionRecord) -> EscalationDecisionRecord:
        pass

    @abstractmethod
    def get_decision(self, decision_id: str) -> Optional[EscalationDecisionRecord]:
        pass

    @abstractmethod
    def get_latest_decision(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[EscalationDecisionRecord]:
        pass

    @abstractmethod
    def get_decision_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[EscalationDecisionRecord]:
        pass

    @abstractmethod
    def save_policy(self, policy: EscalationPolicy) -> EscalationPolicy:
        pass

    @abstractmethod
    def get_policy(self, policy_id: str) -> Optional[EscalationPolicy]:
        pass

    @abstractmethod
    def list_policies(self, enabled_only: bool = False) -> list[EscalationPolicy]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryEscalationRepository(EscalationRepository):
    def __init__(self):
        self._decisions: dict[str, EscalationDecisionRecord] = {}
        self._policies: dict[str, EscalationPolicy] = {}
        self._lock = Lock()
        for p in _get_default_policies():
            self._policies[p.policy_id] = p

    def save_decision(self, decision: EscalationDecisionRecord) -> EscalationDecisionRecord:
        with self._lock:
            self._decisions[decision.decision_id] = decision.model_copy(deep=True)
        return decision

    def get_decision(self, decision_id: str) -> Optional[EscalationDecisionRecord]:
        with self._lock:
            d = self._decisions.get(decision_id)
            return d.model_copy(deep=True) if d else None

    def get_latest_decision(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[EscalationDecisionRecord]:
        with self._lock:
            matches = [
                d for d in self._decisions.values()
                if d.cvki_reference_id == cvki_reference_id
                and (integration_id is None or d.integration_id == integration_id)
            ]
            if not matches:
                return None
            matches.sort(key=lambda x: x.evaluated_at, reverse=True)
            return matches[0].model_copy(deep=True)

    def get_decision_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[EscalationDecisionRecord]:
        with self._lock:
            matches = [
                d for d in self._decisions.values()
                if d.cvki_reference_id == cvki_reference_id
                and (integration_id is None or d.integration_id == integration_id)
            ]
            matches.sort(key=lambda x: x.evaluated_at, reverse=True)
            return [m.model_copy(deep=True) for m in matches[:limit]]

    def save_policy(self, policy: EscalationPolicy) -> EscalationPolicy:
        with self._lock:
            self._policies[policy.policy_id] = policy.model_copy(deep=True)
        return policy

    def get_policy(self, policy_id: str) -> Optional[EscalationPolicy]:
        with self._lock:
            p = self._policies.get(policy_id)
            return p.model_copy(deep=True) if p else None

    def list_policies(self, enabled_only: bool = False) -> list[EscalationPolicy]:
        with self._lock:
            pols = list(self._policies.values())
            if enabled_only:
                pols = [p for p in pols if p.enabled]
            pols.sort(key=lambda x: x.priority)
            return [p.model_copy(deep=True) for p in pols]

    def clear(self) -> None:
        with self._lock:
            self._decisions.clear()
            self._policies.clear()
            for p in _get_default_policies():
                self._policies[p.policy_id] = p


class MongoEscalationRepository(EscalationRepository):
    def __init__(self):
        self._fallback = InMemoryEscalationRepository()

    def save_decision(self, decision: EscalationDecisionRecord) -> EscalationDecisionRecord:
        self._fallback.save_decision(decision)
        db = get_database()
        if db is not None:
            try:
                db.sync_command(
                    lambda: db.delegate[ESCALATION_DECISIONS_COLLECTION].replace_one(
                        {"decision_id": decision.decision_id},
                        decision.model_dump(),
                        upsert=True,
                    )
                )
            except Exception as exc:
                logger.warning("MongoDB escalation decision save failed, fallback active: %s", exc)
        return decision

    def get_decision(self, decision_id: str) -> Optional[EscalationDecisionRecord]:
        db = get_database()
        if db is not None:
            try:
                doc = db.sync_command(
                    lambda: db.delegate[ESCALATION_DECISIONS_COLLECTION].find_one(
                        {"decision_id": decision_id}
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return EscalationDecisionRecord(**doc)
            except Exception as exc:
                logger.warning("MongoDB get decision failed: %s", exc)
        return self._fallback.get_decision(decision_id)

    def get_latest_decision(
        self, cvki_reference_id: str, integration_id: Optional[str] = None
    ) -> Optional[EscalationDecisionRecord]:
        db = get_database()
        if db is not None:
            try:
                query: dict[str, Any] = {"cvki_reference_id": cvki_reference_id}
                if integration_id:
                    query["integration_id"] = integration_id
                doc = db.sync_command(
                    lambda: db.delegate[ESCALATION_DECISIONS_COLLECTION].find_one(
                        query, sort=[("evaluated_at", -1)]
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return EscalationDecisionRecord(**doc)
            except Exception as exc:
                logger.warning("MongoDB get latest decision failed: %s", exc)
        return self._fallback.get_latest_decision(cvki_reference_id, integration_id)

    def get_decision_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> list[EscalationDecisionRecord]:
        db = get_database()
        if db is not None:
            try:
                query: dict[str, Any] = {"cvki_reference_id": cvki_reference_id}
                if integration_id:
                    query["integration_id"] = integration_id
                cursor = db.sync_command(
                    lambda: list(
                        db.delegate[ESCALATION_DECISIONS_COLLECTION].find(
                            query, sort=[("evaluated_at", -1)]
                        ).limit(limit)
                    )
                )
                recs = []
                for doc in cursor:
                    doc.pop("_id", None)
                    recs.append(EscalationDecisionRecord(**doc))
                if recs:
                    return recs
            except Exception as exc:
                logger.warning("MongoDB get decision history failed: %s", exc)
        return self._fallback.get_decision_history(cvki_reference_id, integration_id, limit)

    def save_policy(self, policy: EscalationPolicy) -> EscalationPolicy:
        self._fallback.save_policy(policy)
        db = get_database()
        if db is not None:
            try:
                db.sync_command(
                    lambda: db.delegate[ESCALATION_POLICIES_COLLECTION].replace_one(
                        {"policy_id": policy.policy_id},
                        policy.model_dump(),
                        upsert=True,
                    )
                )
            except Exception as exc:
                logger.warning("MongoDB save policy failed: %s", exc)
        return policy

    def get_policy(self, policy_id: str) -> Optional[EscalationPolicy]:
        db = get_database()
        if db is not None:
            try:
                doc = db.sync_command(
                    lambda: db.delegate[ESCALATION_POLICIES_COLLECTION].find_one(
                        {"policy_id": policy_id}
                    )
                )
                if doc:
                    doc.pop("_id", None)
                    return EscalationPolicy(**doc)
            except Exception as exc:
                logger.warning("MongoDB get policy failed: %s", exc)
        return self._fallback.get_policy(policy_id)

    def list_policies(self, enabled_only: bool = False) -> list[EscalationPolicy]:
        db = get_database()
        if db is not None:
            try:
                query: dict[str, Any] = {"enabled": True} if enabled_only else {}
                cursor = db.sync_command(
                    lambda: list(
                        db.delegate[ESCALATION_POLICIES_COLLECTION].find(
                            query, sort=[("priority", 1)]
                        )
                    )
                )
                pols = []
                for doc in cursor:
                    doc.pop("_id", None)
                    pols.append(EscalationPolicy(**doc))
                if pols:
                    return pols
            except Exception as exc:
                logger.warning("MongoDB list policies failed: %s", exc)
        return self._fallback.list_policies(enabled_only)

    def clear(self) -> None:
        self._fallback.clear()
        db = get_database()
        if db is not None:
            try:
                db.sync_command(lambda: db.delegate[ESCALATION_DECISIONS_COLLECTION].delete_many({}))
                db.sync_command(lambda: db.delegate[ESCALATION_POLICIES_COLLECTION].delete_many({}))
            except Exception as exc:
                logger.warning("MongoDB clear escalation failed: %s", exc)


class EscalationService:
    """
    Evidence-Based Escalation Engine (M7.5).
    Evaluates complaints deterministically against configurable policies and verified government facts.
    """

    def __init__(self, repository: Optional[EscalationRepository] = None):
        self.repository = repository or MongoEscalationRepository()

    def _find_matching_policy(
        self,
        integration_id: str,
        issue_category: Optional[str],
        normalized_status: Optional[NormalizedGovernmentStatus],
    ) -> Optional[EscalationPolicy]:
        """
        Finds the highest priority enabled policy matching integration, category, and status.
        """
        policies = self.repository.list_policies(enabled_only=True)
        # Sort by priority ascending (lower value = higher priority)
        policies.sort(key=lambda x: x.priority)

        # First pass: try exact status match if normalized_status is provided
        if normalized_status is not None:
            for p in policies:
                if p.integration_id != "*" and p.integration_id != integration_id:
                    continue
                if p.target_issue_category and issue_category and p.target_issue_category != issue_category:
                    continue
                if p.condition_normalized_status is not None:
                    if p.condition_normalized_status in (
                        NormalizedGovernmentStatus.NEEDS_INFORMATION,
                        NormalizedGovernmentStatus.AWAITING_INFORMATION,
                    ):
                        if normalized_status in (
                            NormalizedGovernmentStatus.NEEDS_INFORMATION,
                            NormalizedGovernmentStatus.AWAITING_INFORMATION,
                        ):
                            return p
                    elif p.condition_normalized_status == normalized_status:
                        return p

        # Second pass: fallback / catch-all policy when condition_normalized_status is None
        for p in policies:
            if p.integration_id != "*" and p.integration_id != integration_id:
                continue
            if p.target_issue_category and issue_category and p.target_issue_category != issue_category:
                continue
            if p.condition_normalized_status is None:
                if normalized_status in (
                    NormalizedGovernmentStatus.RESOLVED,
                    NormalizedGovernmentStatus.CLOSED,
                    NormalizedGovernmentStatus.REJECTED,
                ):
                    continue
                return p
        return None

    async def evaluate_escalation(
        self,
        case: ComplaintCase,
        integration_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> EscalationResponse:
        """
        Deterministically evaluates whether a case is a candidate for follow-up or escalation.
        Operates exclusively on verified reference, synchronized status, status age, and policies.
        """
        now = datetime.now(timezone.utc)
        cvki_ref = case.reference_id
        issue_cat = case.issue.class_name if case.issue else None

        # Step 1: Check Government Reference Mapping
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

        # Condition Gate 1: No mapping
        if not target_mapping or target_mapping.mapping_state == ReferenceMappingState.UNMAPPED:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=None,
                state=EscalationState.NOT_ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.NOT_ELIGIBLE_NO_REFERENCE,
                explanation="Case has not been mapped or dispatched to an external government integration. Internal policy requires a confirmed external tracking reference before escalation can be evaluated.",
                recommended_action="Prepare complaint package and complete verified government submission first.",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 2: Reference Conflict
        if target_mapping.conflict_detected or target_mapping.mapping_state == ReferenceMappingState.REFERENCE_CONFLICT:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.NOT_ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.NOT_ELIGIBLE_REFERENCE_CONFLICT,
                explanation="Identity collision detected for government reference ID. Automated escalation is paused pending conflict resolution.",
                recommended_action="Case manager review required to resolve external reference collision.",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 3: Reference Received but not confirmed
        if target_mapping.mapping_state == ReferenceMappingState.REFERENCE_RECEIVED:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.NOT_ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.NOT_ELIGIBLE_UNCONFIRMED_REFERENCE,
                explanation="External tracking reference has been received but is not yet authoritatively confirmed upstream.",
                recommended_action="Wait for upstream status confirmation or webhook verification before escalating.",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 4: UNKNOWN_OUTCOME
        if target_mapping.mapping_state == ReferenceMappingState.UNKNOWN_OUTCOME:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=None,
                state=EscalationState.NOT_ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.NOT_ELIGIBLE_NO_REFERENCE,
                explanation="Previous dispatch outcome is unknown. Reconciliation required before escalation can be evaluated.",
                recommended_action="Perform reconciliation to confirm whether the government portal accepted the complaint.",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Step 2: Check Integration Operational State
        defn = government_registry.get_definition(int_id)
        if not defn or defn.configuration_status in (IntegrationState.NOT_CONFIGURED, IntegrationState.DISABLED):
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.NOT_ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.NOT_ELIGIBLE_INTEGRATION_UNCONFIGURED,
                explanation="Target government integration is not configured. Official automated escalation is not supported.",
                recommended_action="Refer to manual offline submission guidelines or official citizen portal.",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        if defn.configuration_status in (IntegrationState.UNAVAILABLE, IntegrationState.DEGRADED):
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.NOT_ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.INTEGRATION_UNAVAILABLE_DEGRADED,
                explanation="Integration adapter is currently experiencing gateway unavailability or elevated error rates. This is an integration impediment, not evidence of government delay.",
                recommended_action="Retry synchronization once the upstream government gateway stabilizes.",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Step 3: Retrieve Latest Synchronized Government Status (M7.4)
        status_service = get_government_status_service()
        latest_status = status_service.repository.find_latest(cvki_ref, int_id)
        freshness = status_service.compute_freshness(latest_status) if latest_status else FreshnessState.UNKNOWN

        if latest_status and latest_status.synchronization_state in (SynchronizationState.UNAVAILABLE, SynchronizationState.FAILED):
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.NOT_ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.INTEGRATION_UNAVAILABLE_DEGRADED,
                explanation="Upstream government status check is currently unavailable or experiencing gateway failure. This is an integration impediment, not evidence of government delay.",
                recommended_action="Retry status synchronization once the government gateway stabilizes.",
                status_freshness=freshness,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 5: No status observed after confirmed reference
        if not latest_status:
            # Check elapsed time since reference confirmation
            ref_confirmed_at = target_mapping.last_confirmed_at or target_mapping.first_observed_at or target_mapping.created_at
            elapsed_hours = (now - ref_confirmed_at).total_seconds() / 3600.0 if ref_confirmed_at else 0.0

            policy = self._find_matching_policy(int_id, issue_cat, None)
            threshold = policy.minimum_age_hours if policy else 72.0

            if elapsed_hours >= threshold:
                return await self._evaluate_and_record_escalation(
                    case=case,
                    int_id=int_id,
                    gov_ref=gov_ref,
                    policy=policy,
                    state=EscalationState.FOLLOW_UP_RECOMMENDED,
                    level=EscalationLevel.FOLLOW_UP,
                    action=EscalationAction.FOLLOW_UP,
                    decision_str="FOLLOW_UP",
                    reason_code=EscalationReasonCode.NO_STATUS_AFTER_CONFIRMATION,
                    explanation=f"Government reference '{gov_ref}' was confirmed {elapsed_hours:.1f} hours ago, but no external status pulse has been returned by portal.",
                    recommended_action="Initiate operational inquiry with public authority regarding acknowledgment receipt.",
                    observed_raw=None,
                    observed_norm=None,
                    status_age_hours=elapsed_hours,
                    status_freshness=freshness,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                )
            else:
                return self._record_and_return_decision(
                    cvki_ref=cvki_ref,
                    int_id=int_id,
                    gov_ref=gov_ref,
                    state=EscalationState.ELIGIBLE,
                    level=EscalationLevel.NONE,
                    action=EscalationAction.NONE,
                    reason_code=EscalationReasonCode.WITHIN_ACCEPTABLE_AGE,
                    explanation=f"Government reference confirmed {elapsed_hours:.1f}h ago. Within normal acknowledgment window ({threshold:.0f}h).",
                    recommended_action="No escalation required at this time. Awaiting first status synchronization.",
                    status_age_hours=elapsed_hours,
                    status_freshness=freshness,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                )

        observed_norm = latest_status.normalized_external_status
        observed_raw = latest_status.raw_external_status

        # Condition Gate 6: Status is UNKNOWN -> Do not falsely escalate
        if observed_norm == NormalizedGovernmentStatus.UNKNOWN:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.SYNC_UNCERTAINTY_UNKNOWN_STATUS,
                explanation=f"External status is UNKNOWN (raw: '{observed_raw}'). Epistemic rule: Cannot infer government inaction or delay from status uncertainty.",
                recommended_action="Perform diagnostic sync check or manual inquiry before inferring operational delay.",
                observed_raw=observed_raw,
                observed_norm=observed_norm,
                status_freshness=freshness,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 7: Status is RESOLVED
        if observed_norm == NormalizedGovernmentStatus.RESOLVED:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.CLOSED,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.RESOLVED_NO_ESCALATION,
                explanation=f"External portal reports grievance as RESOLVED (raw: '{observed_raw}'). Escalation suppressed pending citizen physical resolution verification (M7.6).",
                recommended_action="Inspect citizen resolution verification prompt. Do not escalate a resolved public sector docket.",
                observed_raw=observed_raw,
                observed_norm=observed_norm,
                status_freshness=freshness,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 8: Status is CLOSED or CANCELLED
        if observed_norm in (NormalizedGovernmentStatus.CLOSED, NormalizedGovernmentStatus.CANCELLED):
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.CLOSED,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.CLOSED_NO_ESCALATION,
                explanation=f"External portal docket is {observed_norm.value.upper()} (raw: '{observed_raw}').",
                recommended_action="Case is closed upstream. Review authority closing remarks.",
                observed_raw=observed_raw,
                observed_norm=observed_norm,
                status_freshness=freshness,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 9: Status is REJECTED
        if observed_norm == NormalizedGovernmentStatus.REJECTED:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                state=EscalationState.ACTION_REQUIRED,
                level=EscalationLevel.NONE,
                action=EscalationAction.CITIZEN_ACTION_REQUIRED,
                reason_code=EscalationReasonCode.SUBMISSION_REJECTED_BY_PORTAL,
                explanation=f"External authority portal rejected the submission (raw: '{observed_raw}'). Epistemic rule: Resubmission without addressing rejection grounds is prohibited.",
                recommended_action="Review portal rejection reason (e.g. invalid jurisdiction or duplicate) and advise citizen on administrative appeal.",
                observed_raw=observed_raw,
                observed_norm=observed_norm,
                status_freshness=freshness,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 10: Status is NEEDS_INFORMATION / AWAITING_INFORMATION
        if observed_norm in (NormalizedGovernmentStatus.NEEDS_INFORMATION, NormalizedGovernmentStatus.AWAITING_INFORMATION):
            policy = self._find_matching_policy(int_id, issue_cat, observed_norm)
            return await self._evaluate_and_record_escalation(
                case=case,
                int_id=int_id,
                gov_ref=gov_ref,
                policy=policy,
                state=EscalationState.ACTION_REQUIRED,
                level=EscalationLevel.FOLLOW_UP,
                action=EscalationAction.CITIZEN_ACTION_REQUIRED,
                decision_str="ACTION_REQUIRED",
                reason_code=EscalationReasonCode.NEEDS_INFORMATION_FROM_CITIZEN,
                explanation=f"Public authority requested additional clarification or supporting documentation (raw: '{observed_raw}').",
                recommended_action="Notify citizen to provide requested clarifications on the civic complaint.",
                observed_raw=observed_raw,
                observed_norm=observed_norm,
                status_freshness=freshness,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Condition Gate 11: Active Status (REGISTERED, UNDER_REVIEW, ASSIGNED, IN_PROGRESS, ON_HOLD)
        # Calculate status age from first_seen_at of this continuous observation
        status_age_hours = (now - latest_status.first_seen_at).total_seconds() / 3600.0

        # Match applicable policy
        policy = self._find_matching_policy(int_id, issue_cat, observed_norm)
        threshold_hours = policy.minimum_age_hours if policy else 72.0

        if status_age_hours < threshold_hours:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                policy=policy,
                state=EscalationState.ELIGIBLE,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.WITHIN_ACCEPTABLE_AGE,
                explanation=f"Status '{observed_norm.value}' has been active for {status_age_hours:.1f} hours, which is within the configured policy window ({threshold_hours:.0f} hours).",
                recommended_action="No escalation required at this time. Status is progressing within configured engineering policy bounds.",
                observed_raw=observed_raw,
                observed_norm=observed_norm,
                status_age_hours=status_age_hours,
                status_freshness=freshness,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Status age exceeds policy threshold -> Evaluate Cooldown & Max Escalation Count
        decision_level = policy.escalation_level if policy else EscalationLevel.FOLLOW_UP
        rec_state = (
            EscalationState.ESCALATION_RECOMMENDED
            if decision_level in (EscalationLevel.ESCALATE, EscalationLevel.HIGH_PRIORITY_FOLLOW_UP)
            else EscalationState.FOLLOW_UP_RECOMMENDED
        )
        rec_decision = "ESCALATE" if decision_level == EscalationLevel.ESCALATE else "FOLLOW_UP"

        explanation_msg = (
            f"Government status has remained unchanged as '{observed_norm.value}' (raw: '{observed_raw}') "
            f"for {status_age_hours:.1f} hours, exceeding the configured policy threshold of {threshold_hours:.0f} hours."
        )

        return await self._evaluate_and_record_escalation(
            case=case,
            int_id=int_id,
            gov_ref=gov_ref,
            policy=policy,
            state=rec_state,
            level=decision_level,
            action=policy.escalation_action if policy else EscalationAction.FOLLOW_UP,
            decision_str=rec_decision,
            reason_code=EscalationReasonCode.STATUS_UNCHANGED_BEYOND_POLICY,
            explanation=explanation_msg,
            recommended_action=f"Dispatch follow-up package to {defn.display_name} regarding unmoving case {gov_ref}.",
            observed_raw=observed_raw,
            observed_norm=observed_norm,
            status_age_hours=status_age_hours,
            status_freshness=freshness,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )

    async def _evaluate_and_record_escalation(
        self,
        case: ComplaintCase,
        int_id: str,
        gov_ref: Optional[str],
        policy: Optional[EscalationPolicy],
        state: EscalationState,
        level: EscalationLevel,
        action: EscalationAction,
        decision_str: str,
        reason_code: EscalationReasonCode,
        explanation: str,
        recommended_action: str,
        observed_raw: Optional[str],
        observed_norm: Optional[NormalizedGovernmentStatus],
        status_age_hours: Optional[float] = None,
        status_freshness: Optional[FreshnessState] = None,
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> EscalationResponse:
        """
        Applies cooldown and duplicate suppression before persisting an escalation decision.
        """
        now = datetime.now(timezone.utc)
        cvki_ref = case.reference_id
        policy_id = policy.policy_id if policy else "default"
        max_count = policy.max_escalation_count if policy else 3
        cooldown_hours = policy.cooldown_hours if policy else 24.0

        # Check existing decision history
        history = self.repository.get_decision_history(cvki_ref, int_id, limit=20)
        meaningful_prior = [
            d for d in history
            if d.escalation_state in (
                EscalationState.FOLLOW_UP_RECOMMENDED,
                EscalationState.ESCALATION_RECOMMENDED,
                EscalationState.ACTION_REQUIRED,
            )
        ]
        escalation_count = len(meaningful_prior)

        # Gate A: Max Escalation Count Reached
        if escalation_count >= max_count:
            return self._record_and_return_decision(
                cvki_ref=cvki_ref,
                int_id=int_id,
                gov_ref=gov_ref,
                policy=policy,
                state=EscalationState.COOLDOWN,
                level=EscalationLevel.NONE,
                action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.MAX_ESCALATION_REACHED,
                explanation=f"Maximum configured escalation notifications ({max_count}) reached for this case. Further automated alerts suppressed to prevent notification fatigue.",
                recommended_action="Case manager direct administrative intervention required.",
                observed_raw=observed_raw,
                observed_norm=observed_norm,
                status_age_hours=status_age_hours,
                status_freshness=status_freshness,
                escalation_count=escalation_count,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            )

        # Gate B: Active Cooldown
        if meaningful_prior:
            last_meaningful = meaningful_prior[0]
            cooldown_expiry = last_meaningful.evaluated_at + timedelta(hours=cooldown_hours)
            if now < cooldown_expiry:
                remaining_hours = (cooldown_expiry - now).total_seconds() / 3600.0
                return self._record_and_return_decision(
                    cvki_ref=cvki_ref,
                    int_id=int_id,
                    gov_ref=gov_ref,
                    policy=policy,
                    state=EscalationState.COOLDOWN,
                    level=EscalationLevel.NONE,
                    action=EscalationAction.NONE,
                    reason_code=EscalationReasonCode.IN_COOLDOWN,
                    explanation=f"Case is in active notification cooldown ({remaining_hours:.1f} hours remaining) following prior recommendation.",
                    recommended_action=f"Cooldown active until {cooldown_expiry.isoformat()}. Automated alerts suppressed.",
                    observed_raw=observed_raw,
                    observed_norm=observed_norm,
                    status_age_hours=status_age_hours,
                    status_freshness=status_freshness,
                    escalation_count=escalation_count,
                    cooldown_until=cooldown_expiry,
                    is_in_cooldown=True,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                )

        # Cooldown & Count checks passed: emit active escalation decision
        new_count = escalation_count + 1
        cooldown_until = now + timedelta(hours=cooldown_hours)

        resp = self._record_and_return_decision(
            cvki_ref=cvki_ref,
            int_id=int_id,
            gov_ref=gov_ref,
            policy=policy,
            state=state,
            level=level,
            action=action,
            reason_code=reason_code,
            explanation=explanation,
            recommended_action=recommended_action,
            observed_raw=observed_raw,
            observed_norm=observed_norm,
            status_age_hours=status_age_hours,
            status_freshness=status_freshness,
            escalation_count=new_count,
            cooldown_until=cooldown_until,
            is_in_cooldown=False,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            decision_override=decision_str,
        )

        # Trigger In-App Notification (M7.5)
        try:
            await trigger_escalation_recommended_notification(
                case=case,
                integration_id=int_id,
                escalation_level=level.value,
                reason=explanation,
                recommended_action=recommended_action,
            )
        except Exception as notif_err:
            logger.warning("Failed to fire escalation notification: %s", notif_err)

        return resp

    def _record_and_return_decision(
        self,
        cvki_ref: str,
        int_id: str,
        gov_ref: Optional[str],
        policy: Optional[EscalationPolicy] = None,
        state: EscalationState = EscalationState.NOT_ELIGIBLE,
        level: EscalationLevel = EscalationLevel.NONE,
        action: EscalationAction = EscalationAction.NONE,
        reason_code: EscalationReasonCode = EscalationReasonCode.NOT_ELIGIBLE_NO_REFERENCE,
        explanation: str = "",
        recommended_action: str = "",
        observed_raw: Optional[str] = None,
        observed_norm: Optional[NormalizedGovernmentStatus] = None,
        status_age_hours: Optional[float] = None,
        status_freshness: Optional[FreshnessState] = None,
        escalation_count: int = 0,
        cooldown_until: Optional[datetime] = None,
        is_in_cooldown: bool = False,
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        decision_override: Optional[str] = None,
    ) -> EscalationResponse:
        """
        Builds, persists, logs, links provenance and knowledge graph for an escalation decision.
        """
        now = datetime.now(timezone.utc)
        decision_id = f"esc_{uuid.uuid4().hex[:14]}"
        policy_id = policy.policy_id if policy else None
        policy_desc = policy.description if policy else None
        decision_token = decision_override or ("NONE" if level == EscalationLevel.NONE else "FOLLOW_UP")

        # Provenance Linkage (M6.4)
        ev_id = None
        try:
            from app.services.provenance_engine import get_provenance_engine
            ev_rec = get_provenance_engine().build_evidence_record(
                claim_type=ClaimType.ESCALATION_DECISION,
                case_reference=cvki_ref,
                matched_attribute="escalation_state",
                source="CVKI Escalation Engine",
                source_type=SourceType.SYSTEM_DERIVED,
                observed_at=now,
                retrieved_at=now,
                freshness="fresh",
                verification_state=VerificationState.SYSTEM_DERIVED,
                explanation=explanation,
                claim_value=decision_token,
                metadata={
                    "decision_id": decision_id,
                    "reason_code": reason_code.value,
                    "escalation_level": level.value,
                    "policy_id": policy_id,
                    "is_system_derived": True,
                },
            )
            ev_id = ev_rec.evidence_id if ev_rec else None
        except Exception as prov_err:
            logger.warning("Failed to record escalation provenance: %s", prov_err)

        # Knowledge Graph Linkage (M6.5)
        try:
            from app.services.knowledge_graph import get_knowledge_graph_service
            get_knowledge_graph_service().record_escalation_decision_graph(
                case_reference_id=cvki_ref,
                decision_id=decision_id,
                escalation_level=level.value,
                reason_code=reason_code.value,
                decision=decision_token,
                policy_id=policy_id,
                evidence_id=ev_id,
                explanation=explanation,
            )
        except Exception as kg_err:
            logger.warning("Failed to record escalation in knowledge graph: %s", kg_err)

        decision_record = EscalationDecisionRecord(
            decision_id=decision_id,
            cvki_reference_id=cvki_ref,
            integration_id=int_id,
            government_reference_id=gov_ref,
            policy_id=policy_id,
            escalation_state=state,
            escalation_level=level,
            escalation_action=action,
            decision=decision_token,
            reason_code=reason_code,
            explanation=explanation,
            recommended_action=recommended_action,
            observed_raw_status=observed_raw,
            observed_normalized_status=observed_norm,
            status_age_hours=status_age_hours,
            status_freshness=status_freshness,
            escalation_count=escalation_count,
            cooldown_until=cooldown_until,
            is_in_cooldown=is_in_cooldown,
            is_system_derived=True,
            provenance_evidence_id=ev_id,
            evaluated_at=now,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            metadata={"policy_id": policy_id},
        )
        self.repository.save_decision(decision_record)

        # Audit Trail
        try:
            import asyncio
            coro = AuditService.record_event(
                action="escalation_evaluated",
                result=decision_token.lower(),
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                resource_type="case",
                resource_reference_id=cvki_ref,
                metadata={
                    "decision_id": decision_id,
                    "decision": decision_token,
                    "reason_code": reason_code.value,
                    "escalation_level": level.value,
                    "policy_id": policy_id,
                },
            )
            # Safe execution whether inside or outside running loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(coro)
            except RuntimeError:
                asyncio.run(coro)
        except Exception as audit_err:
            logger.warning("Failed to record escalation audit: %s", audit_err)

        return EscalationResponse(
            cvki_reference_id=cvki_ref,
            integration_id=int_id,
            government_reference_id=gov_ref,
            decision=decision_token,
            escalation_state=state,
            escalation_level=level,
            escalation_action=action,
            reason_code=reason_code,
            explanation=explanation,
            recommended_action=recommended_action,
            policy_id=policy_id,
            policy_description=policy_desc,
            status_age_hours=status_age_hours,
            status_freshness=status_freshness,
            escalation_count=escalation_count,
            max_escalation_count=policy.max_escalation_count if policy else 3,
            is_in_cooldown=is_in_cooldown,
            cooldown_until=cooldown_until,
            is_official_sla=policy.is_official_sla if policy else False,
            is_system_derived=True,
            evaluated_at=now,
            provenance_evidence_id=ev_id,
        )

    def get_current_escalation(
        self, case: ComplaintCase, integration_id: Optional[str] = None
    ) -> EscalationResponse:
        """
        Retrieves the latest evaluated escalation decision without re-evaluating.
        If no decision has been evaluated yet, returns an un-evaluated default response.
        """
        cvki_ref = case.reference_id
        ref_service = get_government_reference_service()
        mappings = ref_service.get_case_mappings(cvki_ref).mappings
        target_mapping = mappings[0] if mappings else None
        int_id = integration_id or (target_mapping.integration_id if target_mapping else "unassigned")
        gov_ref = target_mapping.government_reference_id if target_mapping else None

        latest = self.repository.get_latest_decision(cvki_ref, int_id)
        if not latest:
            return EscalationResponse(
                cvki_reference_id=cvki_ref,
                integration_id=int_id,
                government_reference_id=gov_ref,
                decision="NONE",
                escalation_state=EscalationState.NOT_ELIGIBLE if not gov_ref else EscalationState.ELIGIBLE,
                escalation_level=EscalationLevel.NONE,
                escalation_action=EscalationAction.NONE,
                reason_code=EscalationReasonCode.NOT_ELIGIBLE_NO_REFERENCE if not gov_ref else EscalationReasonCode.WITHIN_ACCEPTABLE_AGE,
                explanation="No escalation evaluation has been conducted yet for this case.",
                recommended_action="Trigger escalation evaluation to check status against policy thresholds.",
                is_official_sla=False,
                is_system_derived=True,
            )

        policy = self.repository.get_policy(latest.policy_id) if latest.policy_id else None
        return EscalationResponse(
            cvki_reference_id=cvki_ref,
            integration_id=latest.integration_id,
            government_reference_id=latest.government_reference_id,
            decision=latest.decision,
            escalation_state=latest.escalation_state,
            escalation_level=latest.escalation_level,
            escalation_action=latest.escalation_action,
            reason_code=latest.reason_code,
            explanation=latest.explanation,
            recommended_action=latest.recommended_action,
            policy_id=latest.policy_id,
            policy_description=policy.description if policy else None,
            status_age_hours=latest.status_age_hours,
            status_freshness=latest.status_freshness,
            escalation_count=latest.escalation_count,
            max_escalation_count=policy.max_escalation_count if policy else 3,
            is_in_cooldown=latest.is_in_cooldown,
            cooldown_until=latest.cooldown_until,
            is_official_sla=policy.is_official_sla if policy else False,
            is_system_derived=True,
            evaluated_at=latest.evaluated_at,
            provenance_evidence_id=latest.provenance_evidence_id,
        )

    def get_escalation_history(
        self, cvki_reference_id: str, integration_id: Optional[str] = None, limit: int = 50
    ) -> EscalationHistoryResponse:
        """
        Retrieves full evaluation history for a case.
        """
        records = self.repository.get_decision_history(cvki_reference_id, integration_id, limit=limit)
        return EscalationHistoryResponse(
            cvki_reference_id=cvki_reference_id,
            decisions=records,
            total=len(records),
        )

    def list_policies(self, enabled_only: bool = False) -> EscalationPolicyListResponse:
        """Lists available escalation policies."""
        pols = self.repository.list_policies(enabled_only=enabled_only)
        return EscalationPolicyListResponse(policies=pols, total=len(pols))

    def create_or_update_policy(
        self, policy: EscalationPolicy, actor_user_id: Optional[str] = None, actor_role: Optional[str] = None
    ) -> EscalationPolicy:
        """Admin endpoint to create or update an escalation policy."""
        saved = self.repository.save_policy(policy)
        try:
            import asyncio
            coro = AuditService.record_event(
                action="escalation_policy_updated",
                result="saved",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                resource_type="policy",
                resource_reference_id=policy.policy_id,
                metadata={"policy_id": policy.policy_id, "priority": policy.priority},
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(coro)
            except RuntimeError:
                asyncio.run(coro)
        except Exception as exc:
            logger.warning("Audit for policy update failed: %s", exc)
        return saved


escalation_service = EscalationService()


def get_escalation_service() -> EscalationService:
    return escalation_service


def set_escalation_service(service: EscalationService) -> None:
    global escalation_service
    escalation_service = service
