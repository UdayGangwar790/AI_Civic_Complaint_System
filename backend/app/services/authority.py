from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any
from urllib.parse import urlparse

from app.schemas.authority import (
    AuthorityConflict,
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
    # M6.1 official types
    "official_government_page",
    "official_open_data",
    "official_api",
    "official_project_registry",
    "official_tender",
    "official_contract",
    "official_concession_document",
    # Legacy official types
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

BUILDER_EVIDENCE_TYPES = {
    "official_tender",
    "official_contract",
    "official_concession_document",
    "official_project_registry",
    "official_tender_record",
    "official_contract_record",
    "official_project_document",
    "concession_agreement",
}


def is_trusted_official_domain(url_or_domain: str | None) -> bool:
    """
    Validates whether a URL or domain belongs to an official government / public sector allowlist
    and satisfies SSRF security protections.
    """
    from app.services.authority_registry import is_safe_official_url
    is_safe, _ = is_safe_official_url(url_or_domain)
    return is_safe


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
    source_status: str | None = None
    freshness: str = "unknown"
    conflicts: tuple[AuthorityConflict, ...] = ()


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
        if stype not in OFFICIAL_SOURCE_TYPES:
            rejections.append(f"Evidence source type '{item.source_type}' is not approved by official source policy.")
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
        if stype not in OFFICIAL_SOURCE_TYPES:
            rejections.append(f"Source type '{src.source_type}' is not approved by official source policy.")
            continue
        if src.source_url and not is_trusted_official_domain(src.source_url):
            rejections.append(f"Source URL '{src.source_url}' does not meet official government domain trust criteria.")
            continue
        valid_sources.append(src)

    return valid_evidence, valid_sources, rejections


def has_verified_builder_evidence(evidence: list[AuthorityEvidence]) -> bool:
    has_location_link = any(
        item.matched_attribute in {"road", "jurisdiction"}
        and item.verification_state == "verified"
        for item in evidence
    )
    has_builder_record = any(
        item.matched_attribute == "builder_or_contractor"
        and item.verification_state == "verified"
        and item.source_type.strip().lower() in BUILDER_EVIDENCE_TYPES
        for item in evidence
    )
    return has_location_link and has_builder_record


def _citizen_explanation(
    authority_status: str,
    *,
    has_location_link: bool,
    has_road_owner: bool,
    has_maintenance_authority: bool,
) -> str:
    if not has_location_link:
        return (
            "CVKI could not link available authority records to the reported road or jurisdiction, "
            "so it has not verified a responsible authority."
        )
    if authority_status == "verified":
        return (
            "Available source records are explicitly linked to this road and support both road ownership "
            "and maintenance responsibility."
        )
    if authority_status == "partially_verified":
        supported_roles = []
        if has_road_owner:
            supported_roles.append("road ownership")
        if has_maintenance_authority:
            supported_roles.append("maintenance responsibility")
        return (
            f"Available source records support {' and '.join(supported_roles)}, but do not verify both "
            "road ownership and maintenance responsibility."
        )
    return (
        "CVKI found evidence linked to this road or jurisdiction, but the available records do not "
        "establish road ownership or maintenance responsibility."
    )


def resolve_authority(
    *,
    latitude: float,
    longitude: float,
    context: dict[str, str | None],
    live: bool = False,
    provider: AuthoritySourceProvider | None = None,
) -> AuthorityResult:
    """
    Resolves evidence-based authority intelligence from configured official sources.
    Strictly differentiates between road_owner, maintenance_authority, and builder_or_contractor.
    Never guesses authority from geographic location alone.
    Supports live official source adapters, safe caching, freshness tracking, and conflict detection.
    """
    now = datetime.now(timezone.utc)
    base_limitation = (
        "Administrative jurisdiction does not by itself establish responsible road authority. "
        "No authoritative road ownership or maintenance source verified this location."
    )

    active_provider = provider
    if active_provider is None:
        if live:
            from app.services.authority_adapter import get_default_live_provider
            active_provider = get_default_live_provider()
        else:
            active_provider = authority_provider

    lookup = active_provider.lookup(
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
            citizen_explanation="CVKI could not fully verify the responsible authority from its available sources.",
            source_status="not_found",
            freshness="unknown",
            conflicts=[],
        )

    raw_evidence = list(lookup.evidence)
    raw_sources = list(lookup.sources)
    valid_evidence, valid_sources, rejections = _validate_evidence_and_sources(raw_evidence, raw_sources)

    if not valid_evidence:
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
            citizen_explanation="CVKI could not fully verify the responsible authority from its available sources.",
            source_status="unavailable" if rejections else "not_found",
            freshness="unknown",
            conflicts=[],
        )

    has_location_link = any(
        item.matched_attribute in {"road", "jurisdiction"}
        for item in valid_evidence
    )
    road_owner = lookup.road_owner if has_location_link and any(
        item.matched_attribute == "road_owner" for item in valid_evidence
    ) else None
    maintenance_authority = lookup.maintenance_authority if has_location_link and any(
        item.matched_attribute == "maintenance_authority" for item in valid_evidence
    ) else None
    builder_has_explicit_record = bool(
        lookup.builder_or_contractor
        and has_location_link
        and any(
            item.matched_attribute == "builder_or_contractor"
            and (item.source_type or "").strip().lower() in BUILDER_EVIDENCE_TYPES
            for item in valid_evidence
        )
    )

    # Conflict detection and handling
    conflicts = list(getattr(lookup, "conflicts", ()))
    has_maint_conflict = any(c.conflicting_attribute == "maintenance_authority" for c in conflicts)
    has_owner_conflict = any(c.conflicting_attribute == "road_owner" for c in conflicts)

    if has_maint_conflict:
        maintenance_authority = None
    if has_owner_conflict:
        road_owner = None

    # Freshness calculation
    from app.services.authority_adapter import _calculate_evidence_freshness
    evidence_trail = []
    has_any_stale = False
    has_any_fresh = False

    for item in valid_evidence:
        attribute = item.matched_attribute
        if attribute in {"road", "jurisdiction"}:
            verification_state = "verified"
            explanation = "This source record is explicitly linked to the reported road or jurisdiction."
        elif attribute == "road_owner" and road_owner:
            verification_state = "verified"
            explanation = "This source record supports road ownership for the linked location."
        elif attribute == "maintenance_authority" and maintenance_authority:
            verification_state = "verified"
            explanation = "This source record supports maintenance responsibility for the linked location."
        elif attribute == "builder_or_contractor" and builder_has_explicit_record:
            verification_state = "verified"
            explanation = "This contract, tender, or project record explicitly supports the builder or contractor for the linked location."
        elif attribute in {"road_owner", "maintenance_authority", "builder_or_contractor"} and not has_location_link:
            verification_state = "not_verified"
            explanation = "This authority claim is not linked to evidence identifying the reported road or jurisdiction."
        elif attribute == "maintenance_authority" and has_maint_conflict:
            verification_state = "not_verified"
            explanation = "Conflicting official records exist for maintenance responsibility on this corridor."
        elif attribute == "road_owner" and has_owner_conflict:
            verification_state = "not_verified"
            explanation = "Conflicting official records exist for road ownership on this corridor."
        elif attribute is None:
            verification_state = "not_verified"
            explanation = "This source record is not linked to a specific field and cannot verify an authority role."
        else:
            verification_state = "not_verified"
            explanation = "This source record does not support a returned authority field."

        item_freshness = item.freshness
        if item_freshness == "unknown" and item.retrieved_at:
            item_freshness = _calculate_evidence_freshness(item.retrieved_at, 30)
        if item_freshness == "stale":
            has_any_stale = True
        elif item_freshness == "fresh":
            has_any_fresh = True

        evidence_trail.append(item.model_copy(update={
            "verification_state": verification_state,
            "explanation": explanation,
            "freshness": item_freshness,
        }))

    builder_or_contractor = (
        lookup.builder_or_contractor
        if lookup.builder_or_contractor and has_verified_builder_evidence(evidence_trail)
        else None
    )

    has_road_and_maintenance = bool(road_owner and maintenance_authority)
    has_any_authority_role = bool(road_owner or maintenance_authority)
    if has_location_link and has_road_and_maintenance:
        authority_status = "verified"
    elif has_location_link and has_any_authority_role:
        authority_status = "partially_verified"
    else:
        authority_status = "not_verified"

    limitations = []
    if not has_location_link:
        limitations.append("Available evidence does not link authority claims to the reported road or jurisdiction.")
    elif not has_any_authority_role:
        limitations.append("Available evidence does not establish road ownership or maintenance responsibility.")
    elif not has_road_and_maintenance:
        limitations.append("Available evidence does not establish every authority role.")
    if rejections:
        limitations.extend(rejections)
    if conflicts:
        limitations.append("Official sources provide conflicting authority records for this location.")
    if has_any_stale:
        limitations.append("Available evidence is stale and requires re-verification against live official sources.")
    if not builder_or_contractor:
        limitations.append("Builder or contractor information is unverified: requires explicit official contract, tender, or concession documentation linked to the road.")

    citizen_explanation = _citizen_explanation(
        authority_status,
        has_location_link=has_location_link,
        has_road_owner=road_owner is not None,
        has_maintenance_authority=maintenance_authority is not None,
    )
    if conflicts:
        citizen_explanation = "Official sources provide conflicting authority information for this corridor."

    overall_freshness = getattr(lookup, "freshness", "unknown")
    if has_any_stale:
        overall_freshness = "stale"
    elif has_any_fresh and overall_freshness == "unknown":
        overall_freshness = "fresh"

    source_status = getattr(lookup, "source_status", None)
    if conflicts:
        source_status = "conflict"
    elif not source_status:
        source_status = "live" if valid_sources else "not_found"

    resolution_message = lookup.resolution_message
    if conflicts:
        resolution_message = "Official sources provide conflicting authority information."
    elif not resolution_message:
        resolution_message = (
            "Authority verified against official source records."
            if has_road_and_maintenance
            else "Authority partially verified from available official records."
        )

    return AuthorityResult(
        authority_status=authority_status,
        road_owner=road_owner,
        maintenance_authority=maintenance_authority,
        builder_or_contractor=builder_or_contractor,
        evidence=evidence_trail,
        limitations=limitations,
        sources=valid_sources,
        resolved_at=lookup.resolved_at or now,
        resolution_message=resolution_message,
        citizen_explanation=citizen_explanation,
        source_status=source_status,
        freshness=overall_freshness,
        conflicts=conflicts,
    )


def resolve_authority_for_location(
    location: Any,
    live: bool = False,
    provider: AuthoritySourceProvider | None = None,
) -> AuthorityResult:
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
            citizen_explanation="CVKI could not fully verify the responsible authority because coordinates were unavailable.",
            source_status="not_found",
            freshness="unknown",
            conflicts=[],
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
        live=live,
        provider=provider,
    )
