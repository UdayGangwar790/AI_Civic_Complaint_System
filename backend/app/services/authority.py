from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any
from urllib.parse import urlparse

from app.schemas.authority import (
    AuthorityEvidence,
    AuthorityParty,
    AuthorityResult,
    OfficialSourceRecord,
)

logger = logging.getLogger("cvki.authority")

OFFICIAL_TRUSTED_DOMAINS = {
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

DISALLOWED_SOURCE_TYPES = {
    "blog",
    "social_media",
    "wikipedia",
    "unverified_directory",
    "user_forum",
    "third_party_directory",
}

OFFICIAL_SOURCE_TYPES = {
    "government_portal",
    "official_gazette",
    "municipal_registry",
    "public_works_record",
    "official_tender_record",
    "official_contract_record",
    "official_database",
    "official_government",
}


def is_trusted_official_domain(url_or_domain: str | None) -> bool:
    """
    Validates whether a URL or domain belongs to an official government / public sector allowlist.
    """
    if not url_or_domain:
        return False
    target = url_or_domain.strip().lower()
    if "://" in target:
        try:
            parsed = urlparse(target)
            domain = (parsed.netloc or "").split(":")[0].lower()
        except Exception:
            return False
    else:
        domain = target.split("/")[0].split(":")[0].lower()

    if not domain:
        return False

    # Check official government TLDs
    if domain.endswith(".gov.in") or domain.endswith(".nic.in") or domain.endswith(".gov"):
        return True

    for trusted in OFFICIAL_TRUSTED_DOMAINS:
        if domain == trusted or domain.endswith("." + trusted):
            return True

    return False


class AuthorityProviderError(Exception):
    """Base error for authoritative-source lookup failures."""


class AuthorityProviderTimeout(AuthorityProviderError):
    """An authoritative provider did not respond in time."""


@dataclass(frozen=True)
class AuthorityLookup:
    road_owner: AuthorityParty | None = None
    maintenance_authority: AuthorityParty | None = None
    builder_or_contractor: AuthorityParty | None = None
    evidence: tuple[AuthorityEvidence, ...] = ()
    sources: tuple[OfficialSourceRecord, ...] = ()
    resolved_at: datetime | None = None
    resolution_message: str | None = None


class AuthoritySourceProvider(ABC):
    """Interface for official authority data sources."""

    @abstractmethod
    def supports_location(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        """Determines whether this provider supports the requested location and road context."""
        pass

    @abstractmethod
    def lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        """Retrieves official authority lookup data for the specified coordinates and road context."""
        pass


class NoConfiguredAuthorityProvider(AuthoritySourceProvider):
    """Safe fallback when no authoritative source provider is configured."""

    def supports_location(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        return False

    def lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> None:
        return None


class OfficialRegistryAuthorityProvider(AuthoritySourceProvider):
    """
    Legacy static sample registry. It is not used by the application because
    its embedded references are not independently verified by a live provider.
    """

    def __init__(self) -> None:
        # Verified registry of official road records backed by official gazettes/portals
        self._registry: dict[str, dict] = {
            # National Highway 44 (NH-44 / Hosur Road corridor)
            "nh_44": {
                "keywords": ["nh 44", "nh-44", "nh44", "national highway 44", "hosur road"],
                "road_owner": AuthorityParty(
                    name="Ministry of Road Transport and Highways (MoRTH)",
                    type="central_government_owner",
                    source="National Highways Act Gazette Notification",
                    official_portal_url="https://morth.nic.in",
                ),
                "maintenance_authority": AuthorityParty(
                    name="National Highways Authority of India (NHAI)",
                    type="public_road_authority",
                    source="NHAI Project Implementation Division",
                    official_portal_url="https://nhai.gov.in",
                ),
                "builder_or_contractor": AuthorityParty(
                    name="Bangalore Elevated Tollway Pvt Ltd",
                    type="concessionaire_contractor",
                    source="NHAI Official Concession Agreement Record CA-2006/NH44",
                ),
                "evidence": (
                    AuthorityEvidence(
                        source_name="Ministry of Road Transport and Highways (MoRTH)",
                        source_type="official_gazette",
                        reference="S.O. 1096(E) National Highways Declaration",
                        claim="Road ownership vested in Central Government under National Highways Act.",
                        source_url="https://morth.nic.in",
                    ),
                    AuthorityEvidence(
                        source_name="National Highways Authority of India (NHAI)",
                        source_type="government_portal",
                        reference="NHAI-PIU-BLR-2024",
                        claim="Maintenance and operational jurisdiction assigned to NHAI Bangalore Project Unit.",
                        source_url="https://nhai.gov.in",
                    ),
                    AuthorityEvidence(
                        source_name="NHAI Contract Registry",
                        source_type="official_contract_record",
                        reference="CA-2006/NH44-BOT",
                        claim="Concessionaire contract awarded for elevated expressway maintenance.",
                        source_url="https://nhai.gov.in",
                    ),
                ),
                "sources": (
                    OfficialSourceRecord(
                        source_id="src_nhai_gov",
                        source_name="NHAI Project Portal",
                        source_type="government_portal",
                        source_url="https://nhai.gov.in",
                        source_domain="nhai.gov.in",
                        retrieved_at=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
                        evidence_summary="Official National Highway maintenance registry and concession tracking.",
                        supported_fields=["road_owner", "maintenance_authority", "builder_or_contractor"],
                    ),
                    OfficialSourceRecord(
                        source_id="src_morth_nic",
                        source_name="MoRTH Gazette Notifications",
                        source_type="official_gazette",
                        source_url="https://morth.nic.in",
                        source_domain="morth.nic.in",
                        retrieved_at=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
                        evidence_summary="Statutory road declaration under Section 2 of National Highways Act.",
                        supported_fields=["road_owner"],
                    ),
                ),
                "resolution_message": "Authority verified against official MoRTH and NHAI registry records.",
            },
            # Verified Municipal Arterial Road in Bengaluru (MG Road)
            "blr_mg_road": {
                "keywords": ["mahatma gandhi road", "m.g. road", "mg road"],
                "road_owner": AuthorityParty(
                    name="Bruhat Bengaluru Mahanagara Palike (BBMP)",
                    type="municipal_corporation",
                    source="BBMP Ward 111 Municipal Road Register",
                    official_portal_url="https://bbmp.gov.in",
                ),
                "maintenance_authority": AuthorityParty(
                    name="BBMP Road Infrastructure Division (East Zone)",
                    type="municipal_road_division",
                    source="BBMP Annual Maintenance Schedule",
                    official_portal_url="https://bbmp.gov.in",
                ),
                "builder_or_contractor": None,  # No contractor record in municipal register
                "evidence": (
                    AuthorityEvidence(
                        source_name="BBMP Municipal Road Register",
                        source_type="municipal_registry",
                        reference="BBMP/RI/EZ/2025/111",
                        claim="Arterial road owned and maintained by BBMP East Zone Road Infrastructure.",
                        source_url="https://bbmp.gov.in",
                    ),
                ),
                "sources": (
                    OfficialSourceRecord(
                        source_id="src_bbmp_gov",
                        source_name="BBMP Municipal Portal",
                        source_type="government_portal",
                        source_url="https://bbmp.gov.in",
                        source_domain="bbmp.gov.in",
                        retrieved_at=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
                        evidence_summary="Official BBMP road infrastructure asset inventory.",
                        supported_fields=["road_owner", "maintenance_authority"],
                    ),
                ),
                "resolution_message": "Authority verified from official BBMP Municipal Road Register.",
            },
            # State Highway with road owner verified but maintenance authority unverified (Partially Verified)
            "state_highway_partial": {
                "keywords": ["karnataka state highway 39", "sh-39", "sh 39"],
                "road_owner": AuthorityParty(
                    name="Karnataka Public Works Department (PWD)",
                    type="state_government_owner",
                    source="Karnataka State Gazette Notification PWD/2021",
                    official_portal_url="https://karnataka.gov.in",
                ),
                "maintenance_authority": None,  # Unresolved division / tender
                "builder_or_contractor": None,
                "evidence": (
                    AuthorityEvidence(
                        source_name="Karnataka State Gazette",
                        source_type="official_gazette",
                        reference="KA-GAZ-2021-PWD-SH39",
                        claim="State Highway road ownership vested in Karnataka Public Works Department.",
                        source_url="https://karnataka.gov.in",
                    ),
                ),
                "sources": (
                    OfficialSourceRecord(
                        source_id="src_karnataka_gov",
                        source_name="Karnataka State Gazette",
                        source_type="official_gazette",
                        source_url="https://karnataka.gov.in",
                        source_domain="karnataka.gov.in",
                        retrieved_at=datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc),
                        evidence_summary="State Gazette road notification.",
                        supported_fields=["road_owner"],
                    ),
                ),
                "resolution_message": "Road ownership verified; maintenance authority division remains unverified.",
            },
        }

    def _match_record(self, context: dict[str, str | None]) -> dict | None:
        road = (context.get("road") or "").strip().lower()
        if not road:
            return None
        for record in self._registry.values():
            for kw in record["keywords"]:
                if kw in road:
                    return record
        return None

    def supports_location(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        return self._match_record(context) is not None

    def lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        matched = self._match_record(context)
        if not matched:
            return None

        return AuthorityLookup(
            road_owner=matched.get("road_owner"),
            maintenance_authority=matched.get("maintenance_authority"),
            builder_or_contractor=matched.get("builder_or_contractor"),
            evidence=matched.get("evidence", ()),
            sources=matched.get("sources", ()),
            resolved_at=datetime.now(timezone.utc),
            resolution_message=matched.get("resolution_message"),
        )


# A live official-source provider must be explicitly configured before authority
# claims can be returned as verified.
authority_provider: AuthoritySourceProvider = NoConfiguredAuthorityProvider()


def set_authority_provider(provider: AuthoritySourceProvider) -> None:
    """Allows setting or mocking the authority source provider."""
    global authority_provider
    authority_provider = provider


def _validate_evidence_and_sources(
    evidence: list[AuthorityEvidence],
    sources: list[OfficialSourceRecord],
) -> tuple[list[AuthorityEvidence], list[OfficialSourceRecord], list[str]]:
    """
    Applies the official source allowlist policy.
    Rejects disallowed source types (blogs, wikipedia, etc.) and untrusted domains.
    """
    valid_evidence: list[AuthorityEvidence] = []
    valid_sources: list[OfficialSourceRecord] = []
    rejections: list[str] = []

    for item in evidence:
        stype = (item.source_type or "").strip().lower()
        if stype in DISALLOWED_SOURCE_TYPES:
            rejections.append(f"Evidence from source type '{item.source_type}' is disallowed by official source policy.")
            continue
        if item.source_url and not is_trusted_official_domain(item.source_url):
            rejections.append(f"Evidence URL '{item.source_url}' is not on the trusted official government domain allowlist.")
            continue
        valid_evidence.append(item)

    for src in sources:
        stype = (src.source_type or "").strip().lower()
        if stype in DISALLOWED_SOURCE_TYPES:
            rejections.append(f"Source type '{src.source_type}' is disallowed by official source policy.")
            continue
        if src.source_url and not is_trusted_official_domain(src.source_url):
            rejections.append(f"Source URL '{src.source_url}' does not meet official government domain trust criteria.")
            continue
        valid_sources.append(src)

    return valid_evidence, valid_sources, rejections


def resolve_authority(
    *,
    latitude: float,
    longitude: float,
    context: dict[str, str | None],
) -> AuthorityResult:
    """
    Resolves evidence-based authority intelligence from configured official sources.
    Strictly differentiates between road_owner, maintenance_authority, and builder_or_contractor.
    Never guesses authority from geographic location alone.
    """
    now = datetime.now(timezone.utc)
    base_limitation = (
        "Administrative jurisdiction does not by itself establish responsible road authority. "
        "No authoritative road ownership or maintenance source verified this location."
    )

    lookup = authority_provider.lookup(
        latitude=latitude,
        longitude=longitude,
        context=context,
    )

    if lookup is None:
        return AuthorityResult(
            authority_status="not_verified",
            road_owner=None,
            maintenance_authority=None,
            builder_or_contractor=None,
            evidence=[],
            limitations=[base_limitation],
            sources=[],
            resolved_at=now,
            resolution_message="No official road record found for this location.",
        )

    raw_evidence = list(lookup.evidence)
    raw_sources = list(lookup.sources)
    valid_evidence, valid_sources, rejections = _validate_evidence_and_sources(raw_evidence, raw_sources)

    has_authority_claim = any((lookup.road_owner, lookup.maintenance_authority, lookup.builder_or_contractor))

    if not has_authority_claim or not valid_evidence:
        limitations = [base_limitation]
        if rejections:
            limitations.extend(rejections)
        return AuthorityResult(
            authority_status="not_verified",
            road_owner=None,
            maintenance_authority=None,
            builder_or_contractor=None,
            evidence=valid_evidence,
            limitations=limitations,
            sources=valid_sources,
            resolved_at=now,
            resolution_message="Authoritative evidence is missing or rejected by official source policy.",
        )

    # Builder/contractor verification: only return when supported by official source document/tender record
    builder_or_contractor = lookup.builder_or_contractor
    has_builder_official_support = bool(
        builder_or_contractor and (
            (builder_or_contractor.source and any(
                kw in builder_or_contractor.source.lower()
                for kw in ("official", "contract", "tender", "project", "concession", "registry", "gazette")
            ))
            or any(
                e.source_type in ("official_tender_record", "official_contract_record", "concession_agreement", "official_project_document")
                for e in valid_evidence
            )
        )
    )
    if not has_builder_official_support:
        builder_or_contractor = None

    # Road owner and maintenance authority must NOT be conflated
    road_owner = lookup.road_owner
    maintenance_authority = lookup.maintenance_authority

    # Verification status rule:
    # "verified": both road_owner AND maintenance_authority are supported by valid evidence
    # "partially_verified": some authority is supported (e.g. only road_owner), but required roles remain unresolved
    # "not_verified": no valid authority claim supported
    has_road_and_maintenance = bool(road_owner and maintenance_authority)
    authority_status = "verified" if has_road_and_maintenance else "partially_verified"

    limitations = []
    if not has_road_and_maintenance:
        limitations.append("Available authoritative evidence does not establish every authority role.")
    if rejections:
        limitations.extend(rejections)

    return AuthorityResult(
        authority_status=authority_status,
        road_owner=road_owner,
        maintenance_authority=maintenance_authority,
        builder_or_contractor=builder_or_contractor,
        evidence=valid_evidence,
        limitations=limitations,
        sources=valid_sources,
        resolved_at=lookup.resolved_at or now,
        resolution_message=lookup.resolution_message or ("Authority verified against official source records." if has_road_and_maintenance else "Authority partially verified from available official records."),
    )


def resolve_authority_for_location(location: Any) -> AuthorityResult:
    def value(name: str) -> Any:
        if isinstance(location, dict):
            return location.get(name)
        return getattr(location, name, None)

    latitude = value("latitude")
    longitude = value("longitude")
    if latitude is None or longitude is None:
        return AuthorityResult(
            authority_status="not_verified",
            limitations=[
                "Coordinates are unavailable and no authoritative road ownership or maintenance source was verified."
            ],
            resolved_at=datetime.now(timezone.utc),
            resolution_message="Authority could not be verified because coordinates were unavailable.",
        )

    return resolve_authority(
        latitude=latitude,
        longitude=longitude,
        context={
            "road": value("road"),
            "area": value("area"),
            "city": value("city"),
            "district": value("district"),
            "state": value("state"),
            "country": value("country"),
        },
    )
