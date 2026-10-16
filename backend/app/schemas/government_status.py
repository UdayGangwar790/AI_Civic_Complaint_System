"""
CVKI M7.4 Government Status Synchronization Schemas.
Maintains strict separation between internal CVKI case lifecycle and external government portal statuses.
Tracks append-oriented synchronization history, stale response protection, idempotency, and freshness.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator

from app.schemas.government_integration import NormalizedGovernmentStatus


class FreshnessState(str, Enum):
    """Engineering freshness status for external government observations."""
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class SynchronizationState(str, Enum):
    """
    State of the synchronization cycle.
    Ensures safe handling of conflicts, unconfirmed references, and stale upstream payloads.
    """
    SYNCED = "SYNCED"
    UNCHANGED = "UNCHANGED"
    STALE_RESPONSE = "STALE_RESPONSE"
    NOT_READY = "NOT_READY"
    REFERENCE_NOT_CONFIRMED = "REFERENCE_NOT_CONFIRMED"
    CONFLICT_BLOCKED = "CONFLICT_BLOCKED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class GovernmentStatusSynchronizationRecord(BaseModel):
    """
    Canonical persistent record representing a verified external government status observation.
    Maintains append-oriented history for state transitions and idempotent timestamp bumps.
    """
    sync_id: str = Field(..., description="Unique deterministic synchronization record ID (e.g. gss_<hex>)")
    cvki_reference_id: str = Field(..., description="Permanent, immutable CVKI Case Reference ID")
    integration_id: str = Field(..., description="Target government integration slug (e.g. gov_cpgrams)")
    government_reference_id: Optional[str] = Field(None, description="External government tracking or docket ID")
    synchronization_state: SynchronizationState = Field(default=SynchronizationState.SYNCED)
    raw_external_status: Optional[str] = Field(None, description="Exact un-parsed raw status string received from portal")
    normalized_external_status: NormalizedGovernmentStatus = Field(default=NormalizedGovernmentStatus.UNKNOWN)
    normalized_status_code: Optional[str] = Field(None, description="Canonical uppercase code representation")
    external_status_timestamp: Optional[datetime] = Field(None, description="Official upstream timestamp from government portal if provided")
    external_updated_at: Optional[datetime] = Field(None, description="Upstream last-updated timestamp from portal if provided")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Local time when status was fetched")
    previous_external_status: Optional[str] = Field(None, description="Prior raw status before this transition")
    previous_normalized_status: Optional[NormalizedGovernmentStatus] = Field(None, description="Prior normalized status before this transition")
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when this specific status was first observed")
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of latest observation confirming this status")
    last_checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when system queried adapter")
    source: str = Field(default="system", description="Source of observation (e.g. adapter:gov_cpgrams, manual_sync, background_poller)")
    adapter_version: str = Field(default="1.0", description="Version of adapter used for lookup")
    freshness_state: FreshnessState = Field(default=FreshnessState.FRESH)
    error_code: Optional[str] = Field(None, description="Safe error code if sync failed")
    error_message_safe: Optional[str] = Field(None, description="Sanitized error description safe for citizen display")
    reconciliation_required: bool = Field(default=False, description="Whether UNKNOWN_OUTCOME requires administrative reconciliation")
    provenance_evidence_id: Optional[str] = Field(None, description="M6.4 Evidence Record ID justifying this status observation")
    external_case_url: Optional[str] = Field(None, description="Official portal link to citizen tracking view")
    details: dict[str, Any] = Field(default_factory=dict, description="Sanitized upstream metadata and diagnostic payload")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def _map_compat_status_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "normalized_status" in data and "normalized_external_status" not in data:
                data["normalized_external_status"] = data["normalized_status"]
            if "raw_status" in data and "raw_external_status" not in data:
                data["raw_external_status"] = data["raw_status"]
        return data

    @property
    def normalized_status(self) -> NormalizedGovernmentStatus:
        return self.normalized_external_status

    @property
    def raw_status(self) -> Optional[str]:
        return self.raw_external_status


class GovernmentStatusSyncResponse(BaseModel):
    """
    API response model returning the latest synchronized government status,
    freshness indicators, and safe summary history.
    """
    cvki_reference_id: str
    case_reference_id: Optional[str] = None
    submission_id: Optional[str] = ""
    integration_id: str
    integration_display_name: str
    government_reference_id: Optional[str] = None
    synchronization_state: SynchronizationState
    latest_raw_status: Optional[str] = None
    normalized_status: NormalizedGovernmentStatus
    freshness: FreshnessState
    last_checked_at: Optional[datetime] = None
    last_successful_sync_at: Optional[datetime] = None
    external_updated_at: Optional[datetime] = None
    next_recommended_sync_at: Optional[datetime] = None
    notice: str
    diagnostic_message: Optional[str] = None
    reconciliation_required: bool = False
    error_code: Optional[str] = None
    error_message_safe: Optional[str] = None
    provenance_evidence_id: Optional[str] = None
    external_case_url: Optional[str] = None
    history_summary: list[dict[str, Any]] = Field(default_factory=list)
    raw_status: Optional[str] = None
    observed_at: Optional[datetime] = None
    success: bool = True
    error: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if self.case_reference_id is None:
            self.case_reference_id = self.cvki_reference_id
        if self.raw_status is None and self.latest_raw_status is not None:
            self.raw_status = self.latest_raw_status
        if self.observed_at is None:
            self.observed_at = self.last_successful_sync_at or self.last_checked_at or datetime.now(timezone.utc)
        if self.error is None and self.error_code is not None:
            self.error = self.error_code
        if self.synchronization_state in (SynchronizationState.FAILED, SynchronizationState.UNAVAILABLE):
            self.success = False


class GovernmentStatusHistoryResponse(BaseModel):
    """
    Full append-oriented history of status observations and transitions for a case.
    """
    cvki_reference_id: str
    integration_id: str
    government_reference_id: Optional[str] = None
    records: list[GovernmentStatusSynchronizationRecord]
    total: int
