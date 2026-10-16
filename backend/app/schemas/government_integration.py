from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class IntegrationState(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED = "CONFIGURED"
    CONFIGURED_STAGING = "CONFIGURED_STAGING"
    CONFIGURED_PRODUCTION = "CONFIGURED_PRODUCTION"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    SUBMISSION_ACCEPTED = "SUBMISSION_ACCEPTED"
    SUBMISSION_REJECTED = "SUBMISSION_REJECTED"
    STATUS_UNAVAILABLE = "STATUS_UNAVAILABLE"


class SubmissionLifecycleState(str, Enum):
    READY = "READY"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    QUEUED = "QUEUED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    STATUS_SYNCING = "STATUS_SYNCING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class NormalizedGovernmentStatus(str, Enum):
    RECEIVED = "received"
    REGISTERED = "registered"
    UNDER_REVIEW = "under_review"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    AWAITING_INFORMATION = "awaiting_information"
    NEEDS_INFORMATION = "needs_information"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class AdapterType(str, Enum):
    NONE = "none"
    MOCK = "mock"
    REST_API = "rest_api"
    PORTAL = "portal"
    WEBHOOK = "webhook"


class AdapterCapabilities(BaseModel):
    submission_supported: bool = Field(default=False, description="Supports dispatching complaints to government endpoint")
    status_supported: bool = Field(default=False, description="Supports querying external status")
    reference_id_supported: bool = Field(default=False, description="Returns official tracking or acknowledgment identifier")
    attachment_supported: bool = Field(default=False, description="Supports photo/evidence binary attachments")
    citizen_identity_supported: bool = Field(default=False, description="Supports citizen credential or verified identity mapping")
    webhook_supported: bool = Field(default=False, description="Supports inbound asynchronous status webhooks")
    polling_supported: bool = Field(default=False, description="Supports periodic status polling")


class GovernmentIntegrationDefinition(BaseModel):
    integration_id: str = Field(..., description="Unique slug for government integration")
    display_name: str = Field(..., description="Human-readable name of integration")
    authority: str = Field(..., description="Name of public authority this integration targets")
    service_type: str = Field(..., description="Type of municipal or government service, e.g. grievance_portal")
    official_domain: str = Field(..., description="Verified official government domain, e.g. bbmp.gov.in")
    official_source_url: Optional[str] = Field(None, description="Official portal or API endpoint documentation URL")
    adapter_type: AdapterType = Field(default=AdapterType.NONE, description="Technology adapter type")
    capabilities: AdapterCapabilities = Field(default_factory=AdapterCapabilities)
    enabled: bool = Field(default=False, description="Whether integration is active for case submission")
    configuration_status: IntegrationState = Field(default=IntegrationState.NOT_CONFIGURED)
    verification_state: str = Field(default="unverified", description="Domain and API verification status")
    diagnostic_message: Optional[str] = Field(None, description="Truthful technical diagnostic explaining current configuration status or missing credentials")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GovernmentSubmissionRecord(BaseModel):
    submission_id: str = Field(..., description="Unique submission attempt ID")
    case_reference_id: str = Field(..., description="CVKI Case Reference ID")
    integration_id: str = Field(..., description="Target integration ID")
    authority_id: Optional[str] = Field(None, description="Target authority identifier")
    submission_state: SubmissionLifecycleState = Field(default=SubmissionLifecycleState.READY)
    external_reference_id: Optional[str] = Field(None, description="Official government tracking or acknowledgment ID")
    external_status: Optional[str] = Field(None, description="Raw external status string received from portal")
    normalized_status: Optional[NormalizedGovernmentStatus] = Field(None, description="CVKI normalized status")
    external_case_url: Optional[str] = Field(None, description="Official portal link to citizen tracking view")
    submitted_at: Optional[datetime] = Field(None, description="Timestamp when submission was accepted")
    last_status_sync_at: Optional[datetime] = Field(None, description="Timestamp of most recent status check")
    next_status_sync_at: Optional[datetime] = Field(None, description="Scheduled next sync timestamp")
    adapter_version: str = Field(default="1.0")
    request_fingerprint: Optional[str] = Field(None, description="SHA-256 fingerprint of payload")
    response_fingerprint: Optional[str] = Field(None, description="SHA-256 fingerprint of server response")
    error_code: Optional[str] = Field(None, description="Normalized error code if failed")
    error_message_safe: Optional[str] = Field(None, description="Sanitized error description safe for citizen display")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GovernmentSubmissionSummary(BaseModel):
    case_reference_id: str
    integration_id: str
    integration_name: str
    authority: str
    integration_state: IntegrationState
    submission_state: SubmissionLifecycleState
    external_reference_id: Optional[str] = None
    external_status: Optional[str] = None
    normalized_status: Optional[NormalizedGovernmentStatus] = None
    external_case_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    last_status_sync_at: Optional[datetime] = None
    next_status_sync_at: Optional[datetime] = None
    reconciliation_required: bool = False
    notice: str
    diagnostic_message: Optional[str] = None


class GovernmentIntegrationListResponse(BaseModel):
    integrations: list[GovernmentIntegrationDefinition]
    total: int


class SubmitGovernmentCaseRequest(BaseModel):
    integration_id: Optional[str] = Field(None, description="Optional override integration ID; otherwise resolved from case authority")
    idempotency_key: Optional[str] = Field(None, description="Optional caller idempotency key")


class GovernmentSubmissionResponse(BaseModel):
    success: bool
    submission_id: str
    case_reference_id: str
    integration_id: str
    submission_state: SubmissionLifecycleState
    external_reference_id: Optional[str] = None
    normalized_status: Optional[NormalizedGovernmentStatus] = None
    notice: str
    reconciliation_required: bool = False
    error_code: Optional[str] = None
    error_message_safe: Optional[str] = None


class GovernmentStatusSyncResult(BaseModel):
    submission_id: str
    case_reference_id: str
    raw_status: Optional[str] = None
    normalized_status: NormalizedGovernmentStatus
    observed_at: datetime
    success: bool
    notice: str
    error: Optional[str] = None


class ReconciliationRequest(BaseModel):
    reason: Optional[str] = Field(default="Admin manual reconciliation check")


class ReconciliationResult(BaseModel):
    submission_id: str
    case_reference_id: str
    prior_state: SubmissionLifecycleState
    reconciled_state: SubmissionLifecycleState
    external_reference_id: Optional[str] = None
    resolved: bool
    explanation: str
