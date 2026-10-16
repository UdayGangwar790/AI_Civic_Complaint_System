"""
CVKI M7.1 Government Service Registry.
Maintains definitions of public municipal/state/national integrations, adapter bindings,
and domain/SSRF verification.
"""

from datetime import datetime, timezone
import logging
from threading import Lock
from typing import Optional

from app.schemas.government_integration import (
    AdapterCapabilities,
    AdapterType,
    GovernmentIntegrationDefinition,
    IntegrationState,
)
from app.services.authority_registry import is_safe_official_url
from app.services.government_adapter import (
    BBMPSahaayaIntegrationAdapter,
    CPGRAMSIntegrationAdapter,
    GovernmentIntegrationAdapter,
    MockGovernmentAdapter,
    NHAIIntegrationAdapter,
)

logger = logging.getLogger("cvki.government_registry")


# Initial official seed catalog of civic government portals.
# All real integrations default strictly to NOT_CONFIGURED and enabled=False.
_INITIAL_DEFINITIONS: dict[str, GovernmentIntegrationDefinition] = {
    "gov_cpgrams": GovernmentIntegrationDefinition(
        integration_id="gov_cpgrams",
        display_name="Centralized Public Grievance Redress and Monitoring System (CPGRAMS)",
        authority="Department of Administrative Reforms and Public Grievances (DARPG)",
        service_type="national_grievance_portal",
        official_domain="pgportal.gov.in",
        official_source_url="https://pgportal.gov.in",
        adapter_type=AdapterType.REST_API,
        capabilities=AdapterCapabilities(
            submission_supported=False,
            status_supported=False,
            reference_id_supported=True,
            attachment_supported=True,
            citizen_identity_supported=True,
            webhook_supported=False,
            polling_supported=True,
        ),
        enabled=False,
        configuration_status=IntegrationState.NOT_CONFIGURED,
        verification_state="api_specification_verified",
        diagnostic_message=(
            "CPGRAMS (DARPG/NIC) G2G Web API integration is not configured. Missing required server-side credentials "
            "(CPGRAMS_API_KEY, CPGRAMS_CLIENT_ID) or DARPG NIC administrative onboarding."
        ),
    ),
    "gov_nhai": GovernmentIntegrationDefinition(
        integration_id="gov_nhai",
        display_name="NHAI National Highway Grievance Service",
        authority="National Highways Authority of India (NHAI)",
        service_type="highway_grievance_portal",
        official_domain="nhai.gov.in",
        official_source_url="https://nhai.gov.in",
        adapter_type=AdapterType.PORTAL,
        capabilities=AdapterCapabilities(
            submission_supported=False,
            status_supported=False,
            reference_id_supported=False,
            attachment_supported=False,
            citizen_identity_supported=False,
            webhook_supported=False,
            polling_supported=False,
        ),
        enabled=False,
        configuration_status=IntegrationState.NOT_CONFIGURED,
        verification_state="domain_verified_api_unverified",
        diagnostic_message=(
            "NHAI (National Highways Authority of India) does not currently publish a verified public third-party "
            "REST API for external civic complaint ingestion. NHAI accepts citizen reports directly via the official "
            "Rajmarg Yatra mobile app or web portal (nhai.gov.in). CVKI maintains this adapter in NOT_CONFIGURED state "
            "in accordance with epistemic honesty rules until official API access is granted by NHAI/MoRTH."
        ),
    ),
    "gov_bbmp": GovernmentIntegrationDefinition(
        integration_id="gov_bbmp",
        display_name="BBMP Bruhat Bengaluru Mahanagara Palike Sahaya",
        authority="Bruhat Bengaluru Mahanagara Palike (BBMP)",
        service_type="municipal_grievance_portal",
        official_domain="bbmp.gov.in",
        official_source_url="https://bbmp.gov.in",
        adapter_type=AdapterType.PORTAL,
        capabilities=AdapterCapabilities(
            submission_supported=False,
            status_supported=False,
            reference_id_supported=False,
            attachment_supported=False,
            citizen_identity_supported=False,
            webhook_supported=False,
            polling_supported=False,
        ),
        enabled=False,
        configuration_status=IntegrationState.NOT_CONFIGURED,
        verification_state="domain_verified_api_unverified",
        diagnostic_message=(
            "BBMP Sahaaya (Bruhat Bengaluru Mahanagara Palike) does not provide a documented public developer API "
            "for automated civic complaint dispatch. Official citizen grievance registration is conducted through "
            "Namma Bengaluru / Sahaaya 2.0 app and bbmp.gov.in. CVKI maintains this adapter in NOT_CONFIGURED state "
            "without simulated success."
        ),
    ),
    "gov_mcd": GovernmentIntegrationDefinition(
        integration_id="gov_mcd",
        display_name="MCD Municipal Corporation of Delhi 311 Service",
        authority="Municipal Corporation of Delhi (MCD)",
        service_type="municipal_grievance_portal",
        official_domain="mcdonline.nic.in",
        official_source_url="https://mcdonline.nic.in",
        adapter_type=AdapterType.NONE,
        capabilities=AdapterCapabilities(
            submission_supported=False,
            status_supported=False,
            reference_id_supported=False,
            attachment_supported=False,
            citizen_identity_supported=False,
            webhook_supported=False,
            polling_supported=False,
        ),
        enabled=False,
        configuration_status=IntegrationState.NOT_CONFIGURED,
        verification_state="domain_verified",
        diagnostic_message="MCD 311 programmatic API is unconfigured.",
    ),
    "gov_pwd_delhi": GovernmentIntegrationDefinition(
        integration_id="gov_pwd_delhi",
        display_name="PWD Delhi Public Works Portal",
        authority="Public Works Department (PWD) Delhi",
        service_type="public_works_portal",
        official_domain="delhi.gov.in",
        official_source_url="https://delhi.gov.in",
        adapter_type=AdapterType.NONE,
        capabilities=AdapterCapabilities(
            submission_supported=False,
            status_supported=False,
            reference_id_supported=False,
            attachment_supported=False,
            citizen_identity_supported=False,
            webhook_supported=False,
            polling_supported=False,
        ),
        enabled=False,
        configuration_status=IntegrationState.NOT_CONFIGURED,
        verification_state="domain_verified",
        diagnostic_message="PWD Delhi portal integration is unconfigured.",
    ),
    "mock_sandbox_integration": GovernmentIntegrationDefinition(
        integration_id="mock_sandbox_integration",
        display_name="CVKI Test Sandbox Mock Government Gateway",
        authority="Sandbox Test Authority",
        service_type="test_mock_gateway",
        official_domain="mock-gov.local",
        official_source_url="https://mock-gov.local",
        adapter_type=AdapterType.MOCK,
        capabilities=AdapterCapabilities(
            submission_supported=True,
            status_supported=True,
            reference_id_supported=True,
            attachment_supported=True,
            citizen_identity_supported=True,
            webhook_supported=False,
            polling_supported=True,
        ),
        enabled=True,
        configuration_status=IntegrationState.AVAILABLE,
        verification_state="sandbox_verified",
        diagnostic_message="Deterministic Mock/Sandbox Adapter for testing only. Not connected to a real government portal.",
    ),
}


class GovernmentServiceRegistry:
    """
    Thread-safe registry managing government integrations and attached runtime adapters.
    """

    def __init__(self):
        self._definitions: dict[str, GovernmentIntegrationDefinition] = dict(_INITIAL_DEFINITIONS)
        self._adapters: dict[str, GovernmentIntegrationAdapter] = {
            "gov_cpgrams": CPGRAMSIntegrationAdapter(),
            "gov_nhai": NHAIIntegrationAdapter(),
            "gov_bbmp": BBMPSahaayaIntegrationAdapter(),
            "mock_sandbox_integration": MockGovernmentAdapter(),
        }
        self._lock = Lock()

    def _sync_definition_with_adapter(
        self,
        defn: GovernmentIntegrationDefinition,
        adapter: Optional[GovernmentIntegrationAdapter],
    ) -> GovernmentIntegrationDefinition:
        copy_d = defn.model_copy()
        if adapter is not None:
            if hasattr(adapter, "get_capabilities"):
                copy_d.capabilities = adapter.get_capabilities()
            if hasattr(adapter, "get_configuration_state"):
                copy_d.configuration_status = adapter.get_configuration_state()
            if hasattr(adapter, "is_configured"):
                copy_d.enabled = adapter.is_configured()
            if hasattr(adapter, "get_diagnostic_message"):
                copy_d.diagnostic_message = adapter.get_diagnostic_message()
        return copy_d

    def list_definitions(self, active_only: bool = False) -> list[GovernmentIntegrationDefinition]:
        with self._lock:
            synced = []
            for int_id, d in self._definitions.items():
                adapter = self._adapters.get(int_id)
                synced_d = self._sync_definition_with_adapter(d, adapter)
                if not active_only or synced_d.enabled:
                    synced.append(synced_d)
            return synced

    def get_definition(self, integration_id: str) -> Optional[GovernmentIntegrationDefinition]:
        with self._lock:
            defn = self._definitions.get(integration_id)
            if not defn:
                return None
            adapter = self._adapters.get(integration_id)
            return self._sync_definition_with_adapter(defn, adapter)

    def get_adapter(self, integration_id: str) -> Optional[GovernmentIntegrationAdapter]:
        with self._lock:
            return self._adapters.get(integration_id)

    def register_adapter(
        self,
        integration_id: str,
        adapter: GovernmentIntegrationAdapter,
        definition: Optional[GovernmentIntegrationDefinition] = None,
    ) -> None:
        with self._lock:
            if definition is not None:
                self._definitions[integration_id] = definition
            self._adapters[integration_id] = adapter

    def find_integration_for_authority(self, authority_name: Optional[str]) -> Optional[GovernmentIntegrationDefinition]:
        """
        Attempts to resolve a registered integration definition for an identified authority.
        Prioritizes verified authority bindings and domain-specific matching.
        """
        if not authority_name:
            return None
        auth_norm = authority_name.strip().lower()

        with self._lock:
            # 1. Exact / strong authority mapping
            target_id = None
            if any(term in auth_norm for term in ("darpg", "cpgrams", "administrative reforms")):
                target_id = "gov_cpgrams"
            elif any(term in auth_norm for term in ("nhai", "national highways authority of india")):
                target_id = "gov_nhai"
            elif any(term in auth_norm for term in ("bbmp", "bruhat bengaluru", "bengaluru mahanagara")):
                target_id = "gov_bbmp"
            elif any(term in auth_norm for term in ("mcd", "municipal corporation of delhi")):
                target_id = "gov_mcd"
            elif any(term in auth_norm for term in ("pwd delhi", "public works department (pwd) delhi")):
                target_id = "gov_pwd_delhi"
            elif any(term in auth_norm for term in ("morth", "ministry of road transport")):
                # MoRTH national grievance routing maps to national CPGRAMS portal
                target_id = "gov_cpgrams"

            if target_id and target_id in self._definitions:
                defn = self._definitions[target_id]
                adapter = self._adapters.get(target_id)
                return self._sync_definition_with_adapter(defn, adapter)

            # 2. General substring match across registered authority names
            for int_id, defn in self._definitions.items():
                if defn.authority.lower() in auth_norm or auth_norm in defn.authority.lower():
                    adapter = self._adapters.get(int_id)
                    return self._sync_definition_with_adapter(defn, adapter)

            # 3. Secondary heuristic match on acronym
            for int_id, defn in self._definitions.items():
                acronym = defn.integration_id.replace("gov_", "").lower()
                if acronym in auth_norm:
                    adapter = self._adapters.get(int_id)
                    return self._sync_definition_with_adapter(defn, adapter)

        return None

    def validate_integration_security(
        self,
        official_domain: str,
        official_source_url: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Validates official domain and URL security against SSRF, disallowing localhost,
        private IPs, loopbacks, and non-government domains.
        """
        if not official_domain or not official_domain.strip():
            return False, "Official domain cannot be empty."

        clean_domain = official_domain.strip().lower()
        if clean_domain == "mock-gov.local":
            return True, "Sandbox mock domain allowed in test environment."

        is_safe, reason = is_safe_official_url(clean_domain)
        if not is_safe:
            return False, f"Domain validation failed: {reason}"

        if official_source_url:
            url_safe, url_reason = is_safe_official_url(official_source_url)
            if not url_safe:
                return False, f"Official source URL validation failed: {url_reason}"

        return True, "Domain and source URL verified."

    def reset_to_initial(self) -> None:
        """Resets registry to initial state for test isolation."""
        with self._lock:
            self._definitions = dict(_INITIAL_DEFINITIONS)
            self._adapters = {
                "gov_cpgrams": CPGRAMSIntegrationAdapter(),
                "gov_nhai": NHAIIntegrationAdapter(),
                "gov_bbmp": BBMPSahaayaIntegrationAdapter(),
                "mock_sandbox_integration": MockGovernmentAdapter(),
            }


# Singleton registry instance
government_registry = GovernmentServiceRegistry()
