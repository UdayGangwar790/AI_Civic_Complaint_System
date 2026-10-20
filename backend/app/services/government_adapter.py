"""
CVKI M7.1 Abstract Government Integration Adapter Interface and Mock Adapter.
Provides the contract for external municipal/state/national government integrations.
"""

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.schemas.complaint_case import ComplaintCase
from app.schemas.government_integration import (
    AdapterCapabilities,
    IntegrationState,
    NormalizedGovernmentStatus,
)
from app.schemas.government_submission import GovernmentSubmissionPackage
from app.services.authority_registry import is_safe_official_url

logger = logging.getLogger("cvki.government_adapter")


@dataclass
class AdapterSubmissionResult:
    state: IntegrationState
    external_reference_id: Optional[str] = None
    raw_status: Optional[str] = None
    normalized_status: Optional[NormalizedGovernmentStatus] = None
    response_fingerprint: Optional[str] = None
    error_code: Optional[str] = None
    error_message_safe: Optional[str] = None
    is_unknown_outcome: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterStatusResult:
    external_reference_id: str
    raw_status: str
    normalized_status: NormalizedGovernmentStatus
    external_case_url: Optional[str] = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_code: Optional[str] = None
    error_message_safe: Optional[str] = None


class GovernmentIntegrationAdapter(ABC):
    """
    Abstract adapter for official government portal or API communication.
    Implementations must be asynchronous-safe.
    """

    @abstractmethod
    def get_capabilities(self) -> AdapterCapabilities:
        """Returns the declared capabilities of this government adapter."""
        pass

    @abstractmethod
    async def validate_submission(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
    ) -> tuple[bool, list[str]]:
        """
        Validates whether the case and submission package fulfill all external API requirements.
        Returns (is_valid, validation_errors).
        """
        pass

    @abstractmethod
    async def prepare_submission(
        self,
        case: ComplaintCase,
    ) -> dict[str, Any]:
        """Formats the internal CVKI case into the adapter's external request payload."""
        pass

    @abstractmethod
    async def submit(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
        idempotency_key: str,
    ) -> AdapterSubmissionResult:
        """
        Executes external dispatch.
        Must respect idempotency_key to prevent duplicate submissions on retries.
        """
        pass

    @abstractmethod
    async def get_status(
        self,
        external_reference_id: str,
    ) -> AdapterStatusResult:
        """Queries the external government portal for updated case status."""
        pass

    @abstractmethod
    def normalize_status(
        self,
        external_status: str,
    ) -> NormalizedGovernmentStatus:
        """Maps an external vendor/authority status string into CVKI normalized status."""
        pass


class MockGovernmentAdapter(GovernmentIntegrationAdapter):
    """
    Deterministic Sandbox/Mock Adapter for M7.1 architectural testing only.
    Clearly marked ENVIRONMENT = "TEST". Never to be used in production or shown
    as a real official government connection.
    """
    ENVIRONMENT = "TEST"

    def __init__(
        self,
        integration_id: str = "mock_gov_adapter",
        display_name: str = "Test Mock Government Adapter",
        should_fail: bool = False,
        should_timeout: bool = False,
        should_reject: bool = False,
    ):
        self.integration_id = integration_id
        self.display_name = display_name
        self.should_fail = should_fail
        self.should_timeout = should_timeout
        self.should_reject = should_reject
        # Simulated external database
        self._submitted_store: dict[str, dict[str, Any]] = {}
        self._idempotency_keys: dict[str, str] = {}  # idempotency_key -> external_ref_id

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            submission_supported=True,
            status_supported=True,
            reference_id_supported=True,
            attachment_supported=True,
            citizen_identity_supported=True,
            webhook_supported=False,
            polling_supported=True,
        )

    async def validate_submission(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not package.complaint_title:
            errors.append("Complaint title is required.")
        if not package.detected_location:
            errors.append("Location information is required.")
        if not package.road_owner and not package.maintenance_authority:
            errors.append("At least one responsible authority must be identified.")
        return len(errors) == 0, errors

    async def prepare_submission(
        self,
        case: ComplaintCase,
    ) -> dict[str, Any]:
        return {
            "source_system": "CVKI_SANDBOX",
            "environment": self.ENVIRONMENT,
            "case_reference": case.reference_id,
            "issue": case.issue.class_name,
            "title": case.complaint.title if case.complaint else "Civic Issue",
            "description": case.complaint.description if case.complaint else "",
            "coordinates": [case.location.latitude, case.location.longitude] if case.location else None,
        }

    async def submit(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
        idempotency_key: str,
    ) -> AdapterSubmissionResult:
        # Check idempotency first
        if idempotency_key in self._idempotency_keys:
            existing_ref = self._idempotency_keys[idempotency_key]
            rec = self._submitted_store[existing_ref]
            return AdapterSubmissionResult(
                state=IntegrationState.SUBMISSION_ACCEPTED,
                external_reference_id=existing_ref,
                raw_status=rec["raw_status"],
                normalized_status=self.normalize_status(rec["raw_status"]),
                response_fingerprint=rec["fingerprint"],
                metadata={"idempotent_replay": True},
            )

        if self.should_timeout:
            # Simulate a request reaching network but response failing / dropping
            # We record to internal store to simulate server-side receipt without client ACK
            simulated_ref = f"MOCK-GOV-{case.reference_id[:8].upper()}"
            self._submitted_store[simulated_ref] = {
                "raw_status": "registered",
                "fingerprint": hashlib.sha256(b"timeout-payload").hexdigest(),
                "created_at": datetime.now(timezone.utc),
            }
            self._idempotency_keys[idempotency_key] = simulated_ref
            return AdapterSubmissionResult(
                state=IntegrationState.TEMPORARY_FAILURE,
                external_reference_id=None,
                error_code="TIMEOUT_RESPONSE_LOST",
                error_message_safe="Connection timed out while waiting for government portal acknowledgment.",
                is_unknown_outcome=True,
            )

        if self.should_reject:
            return AdapterSubmissionResult(
                state=IntegrationState.SUBMISSION_REJECTED,
                error_code="MOCK_SUBMISSION_REJECTED",
                error_message_safe="Government portal rejected submission: Invalid jurisdiction for road category.",
            )

        if self.should_fail:
            return AdapterSubmissionResult(
                state=IntegrationState.TEMPORARY_FAILURE,
                error_code="MOCK_EXTERNAL_ERROR",
                error_message_safe="Simulated 500 error from external endpoint.",
            )

        # Successful submission simulation
        external_ref = f"MOCK-GOV-{case.reference_id[:8].upper()}"
        resp_payload = {
            "ack_id": external_ref,
            "status": "registered",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        fingerprint = hashlib.sha256(json.dumps(resp_payload, sort_keys=True).encode()).hexdigest()
        
        self._submitted_store[external_ref] = {
            "raw_status": "registered",
            "fingerprint": fingerprint,
            "created_at": datetime.now(timezone.utc),
        }
        self._idempotency_keys[idempotency_key] = external_ref

        return AdapterSubmissionResult(
            state=IntegrationState.SUBMISSION_ACCEPTED,
            external_reference_id=external_ref,
            raw_status="registered",
            normalized_status=NormalizedGovernmentStatus.REGISTERED,
            response_fingerprint=fingerprint,
            metadata={"sandbox": True, "environment": self.ENVIRONMENT},
        )

    async def get_status(
        self,
        external_reference_id: str,
    ) -> AdapterStatusResult:
        if external_reference_id not in self._submitted_store:
            return AdapterStatusResult(
                external_reference_id=external_reference_id,
                raw_status="unknown",
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                success=False,
                error_code="EXTERNAL_REF_NOT_FOUND",
                error_message_safe=f"External reference '{external_reference_id}' was not found in mock store.",
            )

        rec = self._submitted_store[external_reference_id]
        raw_st = rec.get("raw_status", "registered")
        return AdapterStatusResult(
            external_reference_id=external_reference_id,
            raw_status=raw_st,
            normalized_status=self.normalize_status(raw_st),
            external_case_url=f"https://mock-gov.local/cases/{external_reference_id}",
            observed_at=datetime.now(timezone.utc),
            success=True,
        )

    def set_external_status(self, external_reference_id: str, new_raw_status: str) -> None:
        """Helper for unit tests to simulate progression in government portal."""
        if external_reference_id in self._submitted_store:
            self._submitted_store[external_reference_id]["raw_status"] = new_raw_status

    def normalize_status(self, external_status: str) -> NormalizedGovernmentStatus:
        s = (external_status or "").strip().lower()
        mapping = {
            "received": NormalizedGovernmentStatus.RECEIVED,
            "registered": NormalizedGovernmentStatus.REGISTERED,
            "ack": NormalizedGovernmentStatus.REGISTERED,
            "under_review": NormalizedGovernmentStatus.UNDER_REVIEW,
            "pending_inspection": NormalizedGovernmentStatus.UNDER_REVIEW,
            "assigned": NormalizedGovernmentStatus.ASSIGNED,
            "in_progress": NormalizedGovernmentStatus.IN_PROGRESS,
            "work_commenced": NormalizedGovernmentStatus.IN_PROGRESS,
            "awaiting_info": NormalizedGovernmentStatus.AWAITING_INFORMATION,
            "needs_information": NormalizedGovernmentStatus.NEEDS_INFORMATION,
            "on_hold": NormalizedGovernmentStatus.ON_HOLD,
            "cancelled": NormalizedGovernmentStatus.CANCELLED,
            "resolved": NormalizedGovernmentStatus.RESOLVED,
            "closed": NormalizedGovernmentStatus.CLOSED,
            "rejected": NormalizedGovernmentStatus.REJECTED,
        }
        return mapping.get(s, NormalizedGovernmentStatus.UNKNOWN)


class CPGRAMSIntegrationAdapter(GovernmentIntegrationAdapter):
    """
    Official G2G Web API Adapter for CPGRAMS (DARPG/NIC).
    Mandated by the Government of India for departmental and state/central grievance
    interoperability ("One Nation – One Portal").
    Targets: Ministry of Road Transport and Highways (MoRTH), National Highways,
    and Central Government civic infrastructure grievances.
    """

    def __init__(
        self,
        integration_id: str = "gov_cpgrams",
        display_name: str = "Centralized Public Grievance Redress and Monitoring System (CPGRAMS)",
        authority: str = "Department of Administrative Reforms and Public Grievances (DARPG)",
        official_domain: str = "pgportal.gov.in",
        official_source_url: str = "https://pgportal.gov.in",
        env_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        client_id_override: Optional[str] = None,
        agency_code_override: Optional[str] = None,
    ):
        self.integration_id = integration_id
        self.display_name = display_name
        self.authority = authority
        self.official_domain = official_domain
        self.official_source_url = official_source_url
        self._env_override = env_override
        self._base_url_override = base_url_override
        self._api_key_override = api_key_override
        self._client_id_override = client_id_override
        self._agency_code_override = agency_code_override
        self._idempotency_store: dict[str, AdapterSubmissionResult] = {}

    @property
    def environment(self) -> str:
        return (self._env_override or settings.CPGRAMS_ENV or "unconfigured").strip().lower()

    @property
    def base_url(self) -> str:
        return (self._base_url_override or settings.CPGRAMS_BASE_URL or "https://pgportal.gov.in/api/v1").strip()

    @property
    def api_key(self) -> str:
        return (self._api_key_override or settings.CPGRAMS_API_KEY or "").strip()

    @property
    def client_id(self) -> str:
        return (self._client_id_override or settings.CPGRAMS_CLIENT_ID or "").strip()

    @property
    def agency_code(self) -> str:
        return (self._agency_code_override or settings.CPGRAMS_AGENCY_CODE or "MORTH").strip()

    def get_configuration_state(self) -> IntegrationState:
        # Check if enabled in settings or explicitly overridden
        if not getattr(settings, "CPGRAMS_ENABLED", False) and not self._env_override:
            return IntegrationState.NOT_CONFIGURED
        env = self.environment
        if env == "production":
            if not self.api_key:
                return IntegrationState.NOT_CONFIGURED
            return IntegrationState.CONFIGURED_PRODUCTION
        elif env == "staging":
            if not self.api_key:
                return IntegrationState.NOT_CONFIGURED
            return IntegrationState.CONFIGURED_STAGING
        elif env == "degraded":
            return IntegrationState.DEGRADED
        elif env == "disabled":
            return IntegrationState.DISABLED
        return IntegrationState.NOT_CONFIGURED

    def is_configured(self) -> bool:
        st = self.get_configuration_state()
        return st in (
            IntegrationState.CONFIGURED_STAGING,
            IntegrationState.CONFIGURED_PRODUCTION,
            IntegrationState.AVAILABLE,
        )

    def get_diagnostic_message(self) -> str:
        st = self.get_configuration_state()
        if st == IntegrationState.CONFIGURED_PRODUCTION:
            return "CPGRAMS G2G Web API configured for production dispatch (pgportal.gov.in). Official DARPG/NIC credentials active."
        if st == IntegrationState.CONFIGURED_STAGING:
            return "CPGRAMS G2G Web API configured for staging sandbox (pgportal.gov.in). DARPG/NIC test credentials active."
        if st == IntegrationState.DISABLED:
            return "CPGRAMS integration is disabled by system configuration."
        if st == IntegrationState.DEGRADED:
            return "CPGRAMS integration is currently experiencing degraded availability or network connectivity issues."
        return (
            "CPGRAMS (DARPG/NIC) G2G Web API integration is not configured. Missing required server-side credentials "
            "(CPGRAMS_API_KEY, CPGRAMS_CLIENT_ID) or DARPG NIC administrative onboarding. In accordance with CVKI integrity policy, "
            "no mock or simulated submission is dispatched in place of official integration."
        )

    def get_capabilities(self) -> AdapterCapabilities:
        configured = self.is_configured()
        return AdapterCapabilities(
            submission_supported=configured,
            status_supported=configured,
            reference_id_supported=True,
            attachment_supported=True,
            citizen_identity_supported=True,
            webhook_supported=False,
            polling_supported=True,
        )

    async def validate_submission(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not self.is_configured():
            errors.append("CPGRAMS integration is not configured. Missing required server-side credentials.")
            return False, errors
        if not package.complaint_title:
            errors.append("Complaint title is required for CPGRAMS submission.")
        if not package.detected_location:
            errors.append("Location information is required for CPGRAMS grievance routing.")
        if not package.complaint_description:
            errors.append("Complaint description is required for CPGRAMS grievance text.")
        return len(errors) == 0, errors

    async def prepare_submission(
        self,
        case: ComplaintCase,
    ) -> dict[str, Any]:
        return {
            "source_system": "CVKI_CIVIC_PORTAL",
            "agency_code": self.agency_code,
            "sub_agency": "NHAI" if (case.authority and "nhai" in (case.authority.road_owner.name if case.authority.road_owner else "").lower()) else "MORTH",
            "complaint_reference": case.reference_id,
            "subject": case.complaint.title if case.complaint else "Civic Complaint",
            "grievance_text": case.complaint.description if case.complaint else "",
            "category": case.issue.label if case.issue else "Road Defect",
            "severity": case.issue.severity if case.issue else "medium",
            "coordinates": {
                "latitude": case.location.latitude if case.location else None,
                "longitude": case.location.longitude if case.location else None,
            },
            "location_details": {
                "road": case.location.road if case.location else None,
                "area": case.location.area if case.location else None,
                "city": case.location.city if case.location else None,
                "state": case.location.state if case.location else None,
            },
            "evidence": {
                "vision_model": (case.metadata.get("model_version") if hasattr(case, "metadata") and case.metadata and case.metadata.get("model_version") else "M1.13-yolov8n"),
                "confidence": case.issue.confidence if case.issue else None,
                "detected_class": case.issue.class_name if case.issue else None,
            },
        }

    async def submit(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
        idempotency_key: str,
    ) -> AdapterSubmissionResult:
        if not self.is_configured():
            return AdapterSubmissionResult(
                state=IntegrationState.NOT_CONFIGURED,
                error_code="CPGRAMS_NOT_CONFIGURED",
                error_message_safe=self.get_diagnostic_message(),
            )

        # Idempotency cache check
        if idempotency_key in self._idempotency_store:
            cached = self._idempotency_store[idempotency_key]
            return AdapterSubmissionResult(
                state=cached.state,
                external_reference_id=cached.external_reference_id,
                raw_status=cached.raw_status,
                normalized_status=cached.normalized_status,
                response_fingerprint=cached.response_fingerprint,
                metadata={**cached.metadata, "idempotent_replay": True},
            )

        # SSRF Pre-flight security check
        is_safe, sec_reason = is_safe_official_url(self.base_url)
        if not is_safe:
            return AdapterSubmissionResult(
                state=IntegrationState.TEMPORARY_FAILURE,
                error_code="SSRF_SECURITY_REJECTION",
                error_message_safe=f"Target URL security validation failed: {sec_reason}",
            )

        endpoint = f"{self.base_url.rstrip('/')}/grievance/submit"
        payload = await self.prepare_submission(case)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Client-ID": self.client_id,
            "X-Agency-Code": self.agency_code,
            "X-Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
            "User-Agent": "CVKI/1.0 (Government Integration Client)",
        }

        timeout_sec = getattr(settings, "GOVERNMENT_REQUEST_TIMEOUT_SECONDS", 5.0)

        # Network transmission
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
        except httpx.TimeoutException:
            # CRITICAL: A timeout after dispatch means request may have reached upstream government server!
            # Never blindly resubmit. Must use UNKNOWN_OUTCOME.
            return AdapterSubmissionResult(
                state=IntegrationState.TEMPORARY_FAILURE,
                is_unknown_outcome=True,
                error_code="TIMEOUT_RESPONSE_LOST",
                error_message_safe="Connection timed out while waiting for CPGRAMS portal acknowledgment. Outcome unconfirmed.",
            )
        except (httpx.ConnectError, httpx.NetworkError) as net_err:
            return AdapterSubmissionResult(
                state=IntegrationState.TEMPORARY_FAILURE,
                is_unknown_outcome=True,
                error_code="NETWORK_ERROR_UNKNOWN_OUTCOME",
                error_message_safe=f"Network communication failure: {type(net_err).__name__}",
            )
        except Exception:
            return AdapterSubmissionResult(
                state=IntegrationState.TEMPORARY_FAILURE,
                is_unknown_outcome=True,
                error_code="UNEXPECTED_TRANSMISSION_ERROR",
                error_message_safe="Unexpected transmission failure communicating with CPGRAMS portal.",
            )

        # Response evaluation
        if resp.status_code in (200, 201):
            try:
                data = resp.json()
            except Exception:
                return AdapterSubmissionResult(
                    state=IntegrationState.TEMPORARY_FAILURE,
                    error_code="MALFORMED_RESPONSE",
                    error_message_safe="CPGRAMS portal returned non-JSON response.",
                )

            ext_ref = data.get("registration_number") or data.get("reference_id") or data.get("grievance_id")
            if not ext_ref:
                return AdapterSubmissionResult(
                    state=IntegrationState.TEMPORARY_FAILURE,
                    error_code="MALFORMED_RESPONSE",
                    error_message_safe="CPGRAMS portal response missing external registration reference ID.",
                )

            raw_status = data.get("status", "registered")
            norm_status = self.normalize_status(raw_status)
            fingerprint = hashlib.sha256(resp.content).hexdigest()

            result = AdapterSubmissionResult(
                state=IntegrationState.SUBMISSION_ACCEPTED,
                external_reference_id=str(ext_ref),
                raw_status=raw_status,
                normalized_status=norm_status,
                response_fingerprint=fingerprint,
                metadata={
                    "environment": self.environment,
                    "agency_code": self.agency_code,
                    "portal_received_at": data.get("received_at"),
                },
            )
            self._idempotency_store[idempotency_key] = result
            return result

        elif resp.status_code in (400, 422):
            try:
                err_data = resp.json()
                detail = err_data.get("detail") or err_data.get("message") or "Schema or jurisdiction validation failed."
            except Exception:
                detail = "Schema or jurisdiction validation failed."
            return AdapterSubmissionResult(
                state=IntegrationState.SUBMISSION_REJECTED,
                error_code="CPGRAMS_SUBMISSION_REJECTED",
                error_message_safe=f"CPGRAMS portal rejected submission: {detail}",
            )
        elif resp.status_code in (401, 403):
            return AdapterSubmissionResult(
                state=IntegrationState.AUTH_REQUIRED,
                error_code="CPGRAMS_AUTHENTICATION_FAILED",
                error_message_safe="CPGRAMS portal authentication failed. Check API credentials.",
            )
        elif resp.status_code == 429:
            return AdapterSubmissionResult(
                state=IntegrationState.RATE_LIMITED,
                error_code="CPGRAMS_RATE_LIMITED",
                error_message_safe="CPGRAMS portal rate limit reached. Back off before re-attempting.",
            )
        elif resp.status_code >= 500:
            return AdapterSubmissionResult(
                state=IntegrationState.TEMPORARY_FAILURE,
                error_code="UPSTREAM_GOVERNMENT_ERROR",
                error_message_safe=f"CPGRAMS portal returned upstream error (HTTP {resp.status_code}).",
            )
        else:
            return AdapterSubmissionResult(
                state=IntegrationState.TEMPORARY_FAILURE,
                error_code=f"UPSTREAM_HTTP_{resp.status_code}",
                error_message_safe=f"Unexpected status code HTTP {resp.status_code} from CPGRAMS portal.",
            )

    async def get_status(
        self,
        external_reference_id: str,
    ) -> AdapterStatusResult:
        if not self.is_configured():
            return AdapterStatusResult(
                external_reference_id=external_reference_id,
                raw_status="unknown",
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                success=False,
                error_code="CPGRAMS_NOT_CONFIGURED",
                error_message_safe=self.get_diagnostic_message(),
            )

        is_safe, sec_reason = is_safe_official_url(self.base_url)
        if not is_safe:
            return AdapterStatusResult(
                external_reference_id=external_reference_id,
                raw_status="unknown",
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                success=False,
                error_code="SSRF_SECURITY_REJECTION",
                error_message_safe=f"Target URL security validation failed: {sec_reason}",
            )

        endpoint = f"{self.base_url.rstrip('/')}/grievance/status/{external_reference_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Client-ID": self.client_id,
            "User-Agent": "CVKI/1.0 (Government Integration Client)",
        }

        timeout_sec = getattr(settings, "GOVERNMENT_REQUEST_TIMEOUT_SECONDS", 5.0)

        # GET is idempotent, safe to retry with bounded backoff
        max_attempts = 2
        last_error = ""
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    resp = await client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        return AdapterStatusResult(
                            external_reference_id=external_reference_id,
                            raw_status="unknown",
                            normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                            success=False,
                            error_code="MALFORMED_STATUS_RESPONSE",
                            error_message_safe="CPGRAMS portal returned non-JSON status response.",
                        )
                    raw_st = data.get("status", "unknown")
                    return AdapterStatusResult(
                        external_reference_id=external_reference_id,
                        raw_status=raw_st,
                        normalized_status=self.normalize_status(raw_st),
                        external_case_url=f"https://pgportal.gov.in/StatusTrack?regNo={external_reference_id}",
                        observed_at=datetime.now(timezone.utc),
                        details=data,
                        success=True,
                    )
                elif resp.status_code == 404:
                    return AdapterStatusResult(
                        external_reference_id=external_reference_id,
                        raw_status="not_found",
                        normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                        success=False,
                        error_code="EXTERNAL_REF_NOT_FOUND",
                        error_message_safe=f"Grievance reference '{external_reference_id}' was not found on CPGRAMS.",
                    )
                elif resp.status_code in (401, 403):
                    return AdapterStatusResult(
                        external_reference_id=external_reference_id,
                        raw_status="unknown",
                        normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                        success=False,
                        error_code="CPGRAMS_AUTHENTICATION_FAILED",
                        error_message_safe="Authentication failed querying CPGRAMS status.",
                    )
                else:
                    last_error = f"HTTP {resp.status_code}"
            except Exception as exc:
                last_error = str(exc)
            if attempt < max_attempts - 1:
                await asyncio.sleep(0.2 * (2 ** attempt))

        return AdapterStatusResult(
            external_reference_id=external_reference_id,
            raw_status="unknown",
            normalized_status=NormalizedGovernmentStatus.UNKNOWN,
            success=False,
            error_code="STATUS_QUERY_FAILED",
            error_message_safe=f"Failed to query CPGRAMS status: {last_error}",
        )

    async def reconcile(
        self,
        case_reference_id: str,
        target_sub: Any = None,
    ) -> AdapterStatusResult:
        """
        Reconciles a submission in UNKNOWN_OUTCOME with CPGRAMS portal.
        Queries the portal using the CVKI case reference ID to determine if it was accepted.
        """
        if not self.is_configured():
            return AdapterStatusResult(
                external_reference_id="",
                raw_status="unknown",
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                success=False,
                error_code="CPGRAMS_NOT_CONFIGURED",
                error_message_safe="Cannot reconcile with CPGRAMS because integration is not configured.",
            )

        # If sub already has external reference ID, query status directly
        if getattr(target_sub, "external_reference_id", None):
            return await self.get_status(target_sub.external_reference_id)

        # Otherwise query reconciliation endpoint by case reference
        endpoint = f"{self.base_url.rstrip('/')}/grievance/reconcile"
        params = {"case_reference": case_reference_id}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Client-ID": self.client_id,
            "User-Agent": "CVKI/1.0 (Government Integration Client)",
        }
        timeout_sec = getattr(settings, "GOVERNMENT_REQUEST_TIMEOUT_SECONDS", 5.0)

        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.get(endpoint, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                ext_ref = data.get("registration_number") or data.get("reference_id")
                if ext_ref:
                    raw_st = data.get("status", "registered")
                    return AdapterStatusResult(
                        external_reference_id=str(ext_ref),
                        raw_status=raw_st,
                        normalized_status=self.normalize_status(raw_st),
                        external_case_url=f"https://pgportal.gov.in/StatusTrack?regNo={ext_ref}",
                        observed_at=datetime.now(timezone.utc),
                        details=data,
                        success=True,
                    )
            # Not found or 404 indicates no record was accepted by upstream
            return AdapterStatusResult(
                external_reference_id="",
                raw_status="unconfirmed",
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                success=False,
                error_code="NO_RECORD_FOUND_ON_GOVERNMENT_PORTAL",
                error_message_safe="CPGRAMS portal confirmed that no grievance was received for this case reference.",
            )
        except Exception as exc:
            return AdapterStatusResult(
                external_reference_id="",
                raw_status="unknown",
                normalized_status=NormalizedGovernmentStatus.UNKNOWN,
                success=False,
                error_code="RECONCILIATION_QUERY_ERROR",
                error_message_safe=f"Reconciliation query to CPGRAMS failed: {exc}",
            )

    def normalize_status(self, external_status: str) -> NormalizedGovernmentStatus:
        s = (external_status or "").strip().lower()
        mapping = {
            "received": NormalizedGovernmentStatus.RECEIVED,
            "registered": NormalizedGovernmentStatus.REGISTERED,
            "lodged": NormalizedGovernmentStatus.REGISTERED,
            "acknowledged": NormalizedGovernmentStatus.REGISTERED,
            "under_examination": NormalizedGovernmentStatus.UNDER_REVIEW,
            "pending": NormalizedGovernmentStatus.UNDER_REVIEW,
            "under_scrutiny": NormalizedGovernmentStatus.UNDER_REVIEW,
            "scrutiny": NormalizedGovernmentStatus.UNDER_REVIEW,
            "forwarded": NormalizedGovernmentStatus.ASSIGNED,
            "assigned": NormalizedGovernmentStatus.ASSIGNED,
            "sent_to_subordinate": NormalizedGovernmentStatus.ASSIGNED,
            "in_process": NormalizedGovernmentStatus.IN_PROGRESS,
            "in_progress": NormalizedGovernmentStatus.IN_PROGRESS,
            "in-progress": NormalizedGovernmentStatus.IN_PROGRESS,
            "investigation_underway": NormalizedGovernmentStatus.IN_PROGRESS,
            "action_initiated": NormalizedGovernmentStatus.IN_PROGRESS,
            "clarification_sought": NormalizedGovernmentStatus.AWAITING_INFORMATION,
            "awaiting_documents": NormalizedGovernmentStatus.AWAITING_INFORMATION,
            "interim_reply": NormalizedGovernmentStatus.AWAITING_INFORMATION,
            "disposed": NormalizedGovernmentStatus.RESOLVED,
            "resolved": NormalizedGovernmentStatus.RESOLVED,
            "redressed": NormalizedGovernmentStatus.RESOLVED,
            "settled": NormalizedGovernmentStatus.RESOLVED,
            "closed": NormalizedGovernmentStatus.CLOSED,
            "rejected": NormalizedGovernmentStatus.REJECTED,
            "denied": NormalizedGovernmentStatus.REJECTED,
            "ineligible": NormalizedGovernmentStatus.REJECTED,
            "not_entertained": NormalizedGovernmentStatus.REJECTED,
        }
        return mapping.get(s, NormalizedGovernmentStatus.UNKNOWN)


class NHAIIntegrationAdapter(GovernmentIntegrationAdapter):
    """
    Adapter Shell for NHAI (National Highways Authority of India).
    Epistemic Status: UNVERIFIED / NOT_CONFIGURED.
    No verified public third-party REST developer API is published by NHAI for automated
    civic complaint submission. Reports must be made via Rajmarg Yatra app or nhai.gov.in.
    """

    def __init__(
        self,
        integration_id: str = "gov_nhai",
        display_name: str = "NHAI National Highway Grievance Service",
        authority: str = "National Highways Authority of India (NHAI)",
        official_domain: str = "nhai.gov.in",
        official_source_url: str = "https://nhai.gov.in",
    ):
        self.integration_id = integration_id
        self.display_name = display_name
        self.authority = authority
        self.official_domain = official_domain
        self.official_source_url = official_source_url

    def get_configuration_state(self) -> IntegrationState:
        return IntegrationState.NOT_CONFIGURED

    def get_diagnostic_message(self) -> str:
        return (
            "NHAI (National Highways Authority of India) does not currently publish a verified public third-party "
            "REST API for external civic complaint ingestion. NHAI accepts citizen reports directly via the official "
            "Rajmarg Yatra mobile app or web portal (nhai.gov.in). CVKI maintains this adapter in NOT_CONFIGURED state "
            "in accordance with epistemic honesty rules until official API access is granted by NHAI/MoRTH."
        )

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            submission_supported=False,
            status_supported=False,
            reference_id_supported=False,
            attachment_supported=False,
            citizen_identity_supported=False,
            webhook_supported=False,
            polling_supported=False,
        )

    async def validate_submission(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
    ) -> tuple[bool, list[str]]:
        return False, [
            "Official NHAI third-party API is not available or configured. "
            "Complaints must be reported via official portal nhai.gov.in or Rajmarg Yatra app."
        ]

    async def prepare_submission(
        self,
        case: ComplaintCase,
    ) -> dict[str, Any]:
        return {
            "source_system": "CVKI_CIVIC_PORTAL",
            "authority": self.authority,
            "case_reference": case.reference_id,
            "status": "NOT_CONFIGURED",
        }

    async def submit(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
        idempotency_key: str,
    ) -> AdapterSubmissionResult:
        return AdapterSubmissionResult(
            state=IntegrationState.UNAVAILABLE,
            error_code="NHAI_API_NOT_AVAILABLE",
            error_message_safe=self.get_diagnostic_message(),
        )

    async def get_status(
        self,
        external_reference_id: str,
    ) -> AdapterStatusResult:
        return AdapterStatusResult(
            external_reference_id=external_reference_id,
            raw_status="unavailable",
            normalized_status=NormalizedGovernmentStatus.UNKNOWN,
            success=False,
            error_code="NHAI_API_NOT_AVAILABLE",
            error_message_safe=self.get_diagnostic_message(),
        )

    def normalize_status(self, external_status: str) -> NormalizedGovernmentStatus:
        return NormalizedGovernmentStatus.UNKNOWN


class BBMPSahaayaIntegrationAdapter(GovernmentIntegrationAdapter):
    """
    Adapter Shell for BBMP Sahaaya 2.0 (Bruhat Bengaluru Mahanagara Palike).
    Epistemic Status: UNVERIFIED / NOT_CONFIGURED.
    No documented public developer API is published by BBMP for third-party automated
    civic complaint dispatch. Citizens use Namma Bengaluru / Sahaaya 2.0 mobile app or bbmp.gov.in.
    """

    def __init__(
        self,
        integration_id: str = "gov_bbmp",
        display_name: str = "BBMP Bruhat Bengaluru Mahanagara Palike Sahaya",
        authority: str = "Bruhat Bengaluru Mahanagara Palike (BBMP)",
        official_domain: str = "bbmp.gov.in",
        official_source_url: str = "https://bbmp.gov.in",
    ):
        self.integration_id = integration_id
        self.display_name = display_name
        self.authority = authority
        self.official_domain = official_domain
        self.official_source_url = official_source_url

    def get_configuration_state(self) -> IntegrationState:
        return IntegrationState.NOT_CONFIGURED

    def get_diagnostic_message(self) -> str:
        return (
            "BBMP Sahaaya (Bruhat Bengaluru Mahanagara Palike) does not provide a documented public developer API "
            "for automated civic complaint dispatch. Official citizen grievance registration is conducted through "
            "Namma Bengaluru / Sahaaya 2.0 app and bbmp.gov.in. CVKI maintains this adapter in NOT_CONFIGURED state "
            "without simulated success."
        )

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            submission_supported=False,
            status_supported=False,
            reference_id_supported=False,
            attachment_supported=False,
            citizen_identity_supported=False,
            webhook_supported=False,
            polling_supported=False,
        )

    async def validate_submission(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
    ) -> tuple[bool, list[str]]:
        return False, [
            "Official BBMP Sahaaya API is not configured. Programmatic dispatch is unavailable "
            "without BBMP-IT administrative onboarding."
        ]

    async def prepare_submission(
        self,
        case: ComplaintCase,
    ) -> dict[str, Any]:
        return {
            "source_system": "CVKI_CIVIC_PORTAL",
            "authority": self.authority,
            "case_reference": case.reference_id,
            "status": "NOT_CONFIGURED",
        }

    async def submit(
        self,
        case: ComplaintCase,
        package: GovernmentSubmissionPackage,
        idempotency_key: str,
    ) -> AdapterSubmissionResult:
        return AdapterSubmissionResult(
            state=IntegrationState.UNAVAILABLE,
            error_code="BBMP_API_NOT_AVAILABLE",
            error_message_safe=self.get_diagnostic_message(),
        )

    async def get_status(
        self,
        external_reference_id: str,
    ) -> AdapterStatusResult:
        return AdapterStatusResult(
            external_reference_id=external_reference_id,
            raw_status="unavailable",
            normalized_status=NormalizedGovernmentStatus.UNKNOWN,
            success=False,
            error_code="BBMP_API_NOT_AVAILABLE",
            error_message_safe=self.get_diagnostic_message(),
        )

    def normalize_status(self, external_status: str) -> NormalizedGovernmentStatus:
        return NormalizedGovernmentStatus.UNKNOWN
