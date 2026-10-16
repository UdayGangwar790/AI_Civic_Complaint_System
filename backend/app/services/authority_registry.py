"""
CVKI M6.1 Official Source Registry & SSRF Security Protection.
Manages registered official authority sources, metadata, freshness policies, and domain verification.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("cvki.authority.registry")

OFFICIAL_SOURCE_TYPES_M61 = {
    # M6.1 types
    "official_government_page",
    "official_open_data",
    "official_api",
    "official_project_registry",
    "official_tender",
    "official_contract",
    "official_concession_document",
    # M3/M5 legacy compatibility types
    "government_portal",
    "official_gazette",
    "municipal_registry",
    "public_works_record",
    "official_tender_record",
    "official_contract_record",
    "official_database",
    "official_government",
    "official_portal",
    "official_project_document",
    "concession_agreement",
}

DISALLOWED_SOURCE_TYPES_M61 = {
    "blog",
    "social_media",
    "wikipedia",
    "unverified_directory",
    "user_forum",
    "third_party_directory",
    "private_directory",
}

BUILDER_EVIDENCE_TYPES_M61 = {
    "official_tender",
    "official_contract",
    "official_concession_document",
    "official_project_registry",
    "official_tender_record",
    "official_contract_record",
    "official_project_document",
    "concession_agreement",
}

OFFICIAL_TRUSTED_DOMAINS_M61 = {
    "gov.in",
    "nic.in",
    "gov",
    "nhai.gov.in",
    "morth.nic.in",
    "pgportal.gov.in",
    "bbmp.gov.in",
    "karnataka.gov.in",
    "mcdonline.nic.in",
    "delhi.gov.in",
    "mcgm.gov.in",
    "maharashtra.gov.in",
    "pmc.gov.in",
    "chennaicorporation.gov.in",
    "tn.gov.in",
    "ghmc.gov.in",
    "telangana.gov.in",
}


@dataclass(frozen=True)
class OfficialSourceDefinition:
    source_id: str
    organization: str
    source_name: str
    source_type: str
    base_url: str
    allowed_domain: str
    jurisdiction_scope: str
    supported_roles: list[str] = field(default_factory=list)
    supported_road_types: list[str] = field(default_factory=list)
    refresh_policy_days: int = 30
    active: bool = True
    last_verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Built-in seed registry of official public road authority sources
_INITIAL_REGISTRY: dict[str, OfficialSourceDefinition] = {
    "src_morth_gazette": OfficialSourceDefinition(
        source_id="src_morth_gazette",
        organization="Ministry of Road Transport and Highways (MoRTH)",
        source_name="MoRTH Statutory Gazette Notifications",
        source_type="official_gazette",
        base_url="https://morth.nic.in",
        allowed_domain="morth.nic.in",
        jurisdiction_scope="national",
        supported_roles=["road_owner"],
        supported_road_types=["national_highway", "expressway"],
        refresh_policy_days=90,
        active=True,
    ),
    "src_nhai_portal": OfficialSourceDefinition(
        source_id="src_nhai_portal",
        organization="National Highways Authority of India (NHAI)",
        source_name="NHAI Project & Maintenance Portal",
        source_type="government_portal",
        base_url="https://nhai.gov.in",
        allowed_domain="nhai.gov.in",
        jurisdiction_scope="national",
        supported_roles=["maintenance_authority", "builder_or_contractor"],
        supported_road_types=["national_highway", "expressway"],
        refresh_policy_days=30,
        active=True,
    ),
    "src_nhai_contract_registry": OfficialSourceDefinition(
        source_id="src_nhai_contract_registry",
        organization="NHAI Concessions & Tenders Division",
        source_name="NHAI Official Concession & Contract Registry",
        source_type="official_contract_record",
        base_url="https://nhai.gov.in",
        allowed_domain="nhai.gov.in",
        jurisdiction_scope="national",
        supported_roles=["builder_or_contractor"],
        supported_road_types=["national_highway"],
        refresh_policy_days=180,
        active=True,
    ),
    "src_kpwd_gazette": OfficialSourceDefinition(
        source_id="src_kpwd_gazette",
        organization="Karnataka Public Works Department (KPWD)",
        source_name="Karnataka State Gazette PWD Notifications",
        source_type="official_gazette",
        base_url="https://karnataka.gov.in",
        allowed_domain="karnataka.gov.in",
        jurisdiction_scope="state_karnataka",
        supported_roles=["road_owner", "maintenance_authority"],
        supported_road_types=["state_highway", "major_district_road"],
        refresh_policy_days=60,
        active=True,
    ),
    "src_bbmp_registry": OfficialSourceDefinition(
        source_id="src_bbmp_registry",
        organization="Bruhat Bengaluru Mahanagara Palike (BBMP)",
        source_name="BBMP Municipal Road Asset Register",
        source_type="municipal_registry",
        base_url="https://bbmp.gov.in",
        allowed_domain="bbmp.gov.in",
        jurisdiction_scope="municipal_bengaluru",
        supported_roles=["road_owner", "maintenance_authority"],
        supported_road_types=["arterial", "sub_arterial", "ward_road"],
        refresh_policy_days=30,
        active=True,
    ),
}

_source_registry: dict[str, OfficialSourceDefinition] = dict(_INITIAL_REGISTRY)


def register_official_source(definition: OfficialSourceDefinition) -> None:
    """Registers or updates an official source definition."""
    _source_registry[definition.source_id] = definition


def get_official_source(source_id: str) -> OfficialSourceDefinition | None:
    """Retrieves an official source definition by its unique identifier."""
    return _source_registry.get(source_id)


def list_official_sources(active_only: bool = True) -> list[OfficialSourceDefinition]:
    """Lists registered official sources."""
    if active_only:
        return [src for src in _source_registry.values() if src.active]
    return list(_source_registry.values())


def reset_source_registry() -> None:
    """Resets registry to initial seed for test isolation."""
    global _source_registry
    _source_registry = dict(_INITIAL_REGISTRY)


def is_safe_official_url(url_or_domain: str | None) -> tuple[bool, str]:
    """
    Validates URL safety against SSRF and allows only configured official domains.
    Rejects private networks, loopbacks, link-local addresses, and cloud metadata IPs.
    Returns (is_safe, reason).
    """
    if not url_or_domain:
        return False, "URL is empty."

    raw = url_or_domain.strip()
    if "://" in raw:
        try:
            parsed = urlparse(raw)
        except Exception:
            return False, "Malformed URL syntax."

        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            return False, f"URL scheme '{scheme}' is disallowed; only HTTP and HTTPS are permitted."

        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    else:
        hostname = raw.split("/")[0].split(":")[0].lower()
        port = None

    if not hostname:
        return False, "URL missing valid hostname."

    # Prevent non-standard ports for external official resources
    if port and port not in {80, 443}:
        return False, f"Disallowed destination port {port}."

    # Check for direct IP address or loopback / link-local / private subnets (SSRF protection)
    try:
        ip = ipaddress.ip_address(hostname)
        # Explicit cloud metadata check (169.254.169.254)
        if str(ip) == "169.254.169.254":
            return False, "Cloud instance metadata service address is forbidden."
        if ip.is_loopback:
            return False, "Loopback IP addresses are forbidden."
        if ip.is_private:
            return False, "Private network IP addresses are forbidden."
        if ip.is_link_local:
            return False, "Link-local IP addresses are forbidden."
        if ip.is_reserved or ip.is_multicast:
            return False, "Reserved or multicast IP addresses are forbidden."
    except ValueError:
        # Not a raw IP, standard hostname
        pass

    # Reject localhost name
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        return False, "Localhost domain is forbidden."

    # Check against trusted official domains
    domain_trusted = False
    if hostname.endswith(".gov.in") or hostname.endswith(".nic.in") or hostname.endswith(".gov") or hostname == "mock-gov.local":
        domain_trusted = True
    else:
        for trusted in OFFICIAL_TRUSTED_DOMAINS_M61:
            if hostname == trusted or hostname.endswith("." + trusted):
                domain_trusted = True
                break

    # Also check against registered source allowed domains
    if not domain_trusted:
        for reg in _source_registry.values():
            if reg.active and (hostname == reg.allowed_domain.lower() or hostname.endswith("." + reg.allowed_domain.lower())):
                domain_trusted = True
                break

    if not domain_trusted:
        return False, f"Domain '{hostname}' is not on the official trusted government allowlist."

    return True, "URL verified against official domain allowlist."
