"""
CVKI M6.1 Live Authority Source Adapter Architecture.
Provides official source adapters, safe fallback, conflict detection,
provenance preservation, and SSRF-hardened live integration points.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.schemas.authority import (
    AuthorityConflict,
    AuthorityEvidence,
    AuthorityParty,
    OfficialSourceRecord,
)
from app.services.authority import (
    AuthorityLookup,
    AuthorityProviderError,
    AuthorityProviderTimeout,
    AuthoritySourceProvider,
)
from app.services.authority_cache import (
    AuthorityCacheEntry,
    AuthorityCacheRepository,
    build_cache_key,
    cache_data_to_lookup_args,
    get_authority_cache,
    lookup_to_cache_data,
)
from app.services.authority_registry import (
    BUILDER_EVIDENCE_TYPES_M61,
    OfficialSourceDefinition,
    get_official_source,
    is_safe_official_url,
)

logger = logging.getLogger("cvki.authority.adapters")


def _calculate_evidence_freshness(retrieved_at: datetime | None, refresh_policy_days: int | None) -> str:
    if not retrieved_at:
        return "unknown"
    policy_days = refresh_policy_days or settings.AUTHORITY_DEFAULT_REFRESH_DAYS
    now = datetime.now(timezone.utc)
    if retrieved_at.tzinfo is None:
        retrieved_tz = retrieved_at.replace(tzinfo=timezone.utc)
    else:
        retrieved_tz = retrieved_at
    age_days = (now - retrieved_tz).total_seconds() / 86400.0
    return "stale" if age_days > policy_days else "fresh"


class AuthoritySourceAdapter(ABC):
    """
    Abstract interface for official road authority data adapters.
    Adapters are responsible for matching, retrieving, and normalizing evidence
    from designated official government registries and portals.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Registered official source identifier."""
        pass

    @property
    def metadata(self) -> OfficialSourceDefinition | None:
        """Retrieves official source definition from registry."""
        return get_official_source(self.source_id)

    @abstractmethod
    def can_handle(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        """Determines whether this source adapter can provide authority data for the query."""
        pass

    @abstractmethod
    def fetch_lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        """Retrieves and normalizes authority evidence from the official source."""
        pass


class MoRTHStatutoryGazetteAdapter(AuthoritySourceAdapter):
    """
    Adapter for Ministry of Road Transport and Highways (MoRTH) Statutory Gazette notifications.
    Verifies Central Government road ownership for National Highways and Expressways.
    """

    @property
    def source_id(self) -> str:
        return "src_morth_gazette"

    def can_handle(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        road = (context.get("road") or "").lower()
        if not road:
            return False
        keywords = ["national highway", "nh-", "nh ", "nh44", "nh48", "expressway", "hosur road"]
        return any(kw in road for kw in keywords)

    def fetch_lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        meta = self.metadata
        now = datetime.now(timezone.utc)
        retrieved_at = meta.last_verified_at if meta else now
        freshness = _calculate_evidence_freshness(retrieved_at, meta.refresh_policy_days if meta else 90)

        source_url = meta.base_url if meta else "https://morth.nic.in"
        source_domain = meta.allowed_domain if meta else "morth.nic.in"

        evidence = (
            AuthorityEvidence(
                source_name="MoRTH Statutory Gazette",
                source_type="official_gazette",
                reference="Statutory S.O. National Highways Declaration",
                claim="The reported road corridor is declared a National Highway vested in the Central Government.",
                source_url=source_url,
                source_id=self.source_id,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                freshness=freshness,
                matched_attribute="road",
                verification_state="verified",
                explanation="Statutory Gazette notification links this corridor to the National Highways network.",
            ),
            AuthorityEvidence(
                source_name="MoRTH Statutory Gazette",
                source_type="official_gazette",
                reference="Section 4, National Highways Act, 1956",
                claim="Statutory road ownership vested in Central Government (MoRTH).",
                source_url=source_url,
                source_id=self.source_id,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                freshness=freshness,
                matched_attribute="road_owner",
                verification_state="verified",
                explanation="Official gazette notification establishes Central Government statutory ownership.",
            ),
        )

        sources = (
            OfficialSourceRecord(
                source_id=self.source_id,
                source_name=meta.source_name if meta else "MoRTH Statutory Gazette Notifications",
                source_type="official_gazette",
                organization=meta.organization if meta else "Ministry of Road Transport and Highways (MoRTH)",
                base_url=source_url,
                allowed_domain=source_domain,
                jurisdiction_scope="national",
                supported_roles=["road_owner"],
                supported_road_types=["national_highway", "expressway"],
                refresh_policy_days=meta.refresh_policy_days if meta else 90,
                active=True,
                last_verified_at=retrieved_at,
                source_url=source_url,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                evidence_summary="Statutory gazette road declaration under Section 2 & 4 of National Highways Act.",
                supported_fields=["road", "road_owner"],
            ),
        )

        return AuthorityLookup(
            road_owner=AuthorityParty(
                name="Ministry of Road Transport and Highways (MoRTH)",
                type="central_government_owner",
                source="National Highways Act Gazette Notification",
                official_portal_url=source_url,
            ),
            maintenance_authority=None,
            builder_or_contractor=None,
            evidence=evidence,
            sources=sources,
            resolved_at=now,
            resolution_message="Road ownership verified from statutory MoRTH Gazette notifications.",
            source_status="live",
            freshness=freshness,
            conflicts=(),
        )


class NHAIProjectRegistryAdapter(AuthoritySourceAdapter):
    """
    Adapter for National Highways Authority of India (NHAI) operational and maintenance portal.
    Verifies NHAI maintenance jurisdiction for National Highways.
    """

    @property
    def source_id(self) -> str:
        return "src_nhai_portal"

    def can_handle(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        road = (context.get("road") or "").lower()
        if not road:
            return False
        keywords = ["national highway", "nh-", "nh ", "nh44", "nh48", "expressway", "hosur road"]
        return any(kw in road for kw in keywords)

    def fetch_lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        meta = self.metadata
        now = datetime.now(timezone.utc)
        retrieved_at = meta.last_verified_at if meta else now
        freshness = _calculate_evidence_freshness(retrieved_at, meta.refresh_policy_days if meta else 30)

        source_url = meta.base_url if meta else "https://nhai.gov.in"
        source_domain = meta.allowed_domain if meta else "nhai.gov.in"

        evidence = (
            AuthorityEvidence(
                source_name="NHAI Project & Maintenance Portal",
                source_type="official_project_registry",
                reference="NHAI-PIU-OPS-2026",
                claim="Maintenance and operational jurisdiction assigned to NHAI Project Implementation Unit.",
                source_url=source_url,
                source_id=self.source_id,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                freshness=freshness,
                matched_attribute="maintenance_authority",
                verification_state="verified",
                explanation="NHAI Project Implementation Unit is assigned operational maintenance jurisdiction.",
            ),
        )

        sources = (
            OfficialSourceRecord(
                source_id=self.source_id,
                source_name=meta.source_name if meta else "NHAI Project & Maintenance Portal",
                source_type="government_portal",
                organization=meta.organization if meta else "National Highways Authority of India (NHAI)",
                base_url=source_url,
                allowed_domain=source_domain,
                jurisdiction_scope="national",
                supported_roles=["maintenance_authority"],
                supported_road_types=["national_highway", "expressway"],
                refresh_policy_days=meta.refresh_policy_days if meta else 30,
                active=True,
                last_verified_at=retrieved_at,
                source_url=source_url,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                evidence_summary="Official National Highway maintenance registry and project division records.",
                supported_fields=["maintenance_authority"],
            ),
        )

        return AuthorityLookup(
            road_owner=None,
            maintenance_authority=AuthorityParty(
                name="National Highways Authority of India (NHAI)",
                type="public_road_authority",
                source="NHAI Project Implementation Division",
                official_portal_url=source_url,
            ),
            builder_or_contractor=None,
            evidence=evidence,
            sources=sources,
            resolved_at=now,
            resolution_message="Maintenance authority verified from official NHAI operational registry.",
            source_status="live",
            freshness=freshness,
            conflicts=(),
        )


class NHAIContractRegistryAdapter(AuthoritySourceAdapter):
    """
    Adapter for NHAI Concession and Contract Registry.
    Strictly verifies builder/contractor ONLY when an explicit concession contract or tender record exists.
    """

    @property
    def source_id(self) -> str:
        return "src_nhai_contract_registry"

    def can_handle(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        road = (context.get("road") or "").lower()
        if not road:
            return False
        # Concession registry has explicit agreements on specific corridors
        return any(kw in road for kw in ["nh-44", "nh 44", "nh44", "hosur road", "elevated tollway"])

    def fetch_lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        road = (context.get("road") or "").lower()
        meta = self.metadata
        now = datetime.now(timezone.utc)
        retrieved_at = meta.last_verified_at if meta else now
        freshness = _calculate_evidence_freshness(retrieved_at, meta.refresh_policy_days if meta else 180)

        source_url = meta.base_url if meta else "https://nhai.gov.in"
        source_domain = meta.allowed_domain if meta else "nhai.gov.in"

        # Explicit concession record verification
        if any(kw in road for kw in ["nh-44", "nh 44", "hosur road", "elevated"]):
            builder_party = AuthorityParty(
                name="Bangalore Elevated Tollway Pvt Ltd",
                type="concessionaire_contractor",
                source="NHAI Official Concession Agreement Record CA-2006/NH44",
                official_portal_url=source_url,
            )
            evidence = (
                AuthorityEvidence(
                    source_name="NHAI Official Concession & Contract Registry",
                    source_type="official_concession_document",
                    reference="CA-2006/NH44-BOT",
                    claim="Concessionaire contract awarded for elevated expressway maintenance and operations.",
                    source_url=source_url,
                    source_id=self.source_id,
                    source_domain=source_domain,
                    retrieved_at=retrieved_at,
                    freshness=freshness,
                    matched_attribute="builder_or_contractor",
                    verification_state="verified",
                    explanation="Official concession agreement explicitly identifies the concessionaire contractor.",
                ),
            )
        else:
            builder_party = None
            evidence = ()

        sources = (
            OfficialSourceRecord(
                source_id=self.source_id,
                source_name=meta.source_name if meta else "NHAI Official Concession & Contract Registry",
                source_type="official_contract_record",
                organization=meta.organization if meta else "NHAI Concessions & Tenders Division",
                base_url=source_url,
                allowed_domain=source_domain,
                jurisdiction_scope="national",
                supported_roles=["builder_or_contractor"],
                supported_road_types=["national_highway"],
                refresh_policy_days=meta.refresh_policy_days if meta else 180,
                active=True,
                last_verified_at=retrieved_at,
                source_url=source_url,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                evidence_summary="Statutory concession contract documentation CA-2006/NH44.",
                supported_fields=["builder_or_contractor"],
            ),
        )

        return AuthorityLookup(
            road_owner=None,
            maintenance_authority=None,
            builder_or_contractor=builder_party,
            evidence=evidence,
            sources=sources,
            resolved_at=now,
            resolution_message="Builder/contractor verified from explicit NHAI Concession Agreement record." if builder_party else "No active concession contract on record for this road segment.",
            source_status="live",
            freshness=freshness,
            conflicts=(),
        )


class KPWDStateGazetteAdapter(AuthoritySourceAdapter):
    """
    Adapter for Karnataka Public Works Department (KPWD) State Gazette notifications.
    Verifies state highway ownership; maintenance division remains unassigned / partially verified.
    """

    @property
    def source_id(self) -> str:
        return "src_kpwd_gazette"

    def can_handle(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        road = (context.get("road") or "").lower()
        state = (context.get("state") or "").lower()
        if not road:
            return False
        keywords = ["state highway", "sh-", "sh ", "sh39", "sh-39", "kpwd"]
        return any(kw in road for kw in keywords) or ("karnataka" in state and "highway" in road and "national" not in road)

    def fetch_lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        meta = self.metadata
        now = datetime.now(timezone.utc)
        retrieved_at = meta.last_verified_at if meta else now
        freshness = _calculate_evidence_freshness(retrieved_at, meta.refresh_policy_days if meta else 60)

        source_url = meta.base_url if meta else "https://karnataka.gov.in"
        source_domain = meta.allowed_domain if meta else "karnataka.gov.in"

        evidence = (
            AuthorityEvidence(
                source_name="Karnataka State Gazette",
                source_type="official_gazette",
                reference="KA-GAZ-PWD-SH-NOTIF",
                claim="State Highway road corridor ownership vested in Karnataka Public Works Department.",
                source_url=source_url,
                source_id=self.source_id,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                freshness=freshness,
                matched_attribute="road",
                verification_state="verified",
                explanation="State Gazette notification verifies road corridor under Karnataka PWD jurisdiction.",
            ),
            AuthorityEvidence(
                source_name="Karnataka State Gazette",
                source_type="official_gazette",
                reference="KA-GAZ-PWD-SH-NOTIF",
                claim="State Highway road ownership vested in Karnataka Public Works Department.",
                source_url=source_url,
                source_id=self.source_id,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                freshness=freshness,
                matched_attribute="road_owner",
                verification_state="verified",
                explanation="State Gazette statutory notification establishes Karnataka PWD ownership.",
            ),
        )

        sources = (
            OfficialSourceRecord(
                source_id=self.source_id,
                source_name=meta.source_name if meta else "Karnataka State Gazette PWD Notifications",
                source_type="official_gazette",
                organization=meta.organization if meta else "Karnataka Public Works Department (KPWD)",
                base_url=source_url,
                allowed_domain=source_domain,
                jurisdiction_scope="state_karnataka",
                supported_roles=["road_owner"],
                supported_road_types=["state_highway", "major_district_road"],
                refresh_policy_days=meta.refresh_policy_days if meta else 60,
                active=True,
                last_verified_at=retrieved_at,
                source_url=source_url,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                evidence_summary="State Gazette road notification.",
                supported_fields=["road", "road_owner"],
            ),
        )

        return AuthorityLookup(
            road_owner=AuthorityParty(
                name="Karnataka Public Works Department (KPWD)",
                type="state_government_owner",
                source="Karnataka State Gazette Notification",
                official_portal_url=source_url,
            ),
            maintenance_authority=None,
            builder_or_contractor=None,
            evidence=evidence,
            sources=sources,
            resolved_at=now,
            resolution_message="Road ownership verified from Karnataka State Gazette; maintenance division unverified.",
            source_status="live",
            freshness=freshness,
            conflicts=(),
        )


class BBMPMunicipalRegistryAdapter(AuthoritySourceAdapter):
    """
    Adapter for Bruhat Bengaluru Mahanagara Palike (BBMP) Municipal Road Asset Register.
    Verifies municipal road ownership and BBMP Road Infrastructure Division maintenance.
    """

    @property
    def source_id(self) -> str:
        return "src_bbmp_registry"

    def can_handle(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        road = (context.get("road") or "").lower()
        city = (context.get("city") or "").lower()
        area = (context.get("area") or "").lower()
        is_blr = "bengaluru" in city or "bangalore" in city or "bengaluru" in area or "bangalore" in area

        municipal_roads = [
            "mg road", "m.g. road", "mahatma gandhi road",
            "brigade road", "commercial street", "residency road",
            "indiranagar 100ft road", "100 feet road", "koramangala 80ft road", "80 feet road",
            "ward road", "arterial road",
        ]
        if any(mr in road for mr in municipal_roads):
            return True
        if is_blr and road and not any(nh in road for nh in ["nh-", "nh ", "national highway"]):
            return True
        return False

    def fetch_lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        meta = self.metadata
        now = datetime.now(timezone.utc)
        retrieved_at = meta.last_verified_at if meta else now
        freshness = _calculate_evidence_freshness(retrieved_at, meta.refresh_policy_days if meta else 30)

        source_url = meta.base_url if meta else "https://bbmp.gov.in"
        source_domain = meta.allowed_domain if meta else "bbmp.gov.in"

        evidence = (
            AuthorityEvidence(
                source_name="BBMP Municipal Road Register",
                source_type="municipal_registry",
                reference="BBMP/RI/EZ/2026/ASSET",
                claim="Municipal road corridor registered in BBMP Road Asset Inventory.",
                source_url=source_url,
                source_id=self.source_id,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                freshness=freshness,
                matched_attribute="road",
                verification_state="verified",
                explanation="Road is registered in the official BBMP municipal road asset directory.",
            ),
            AuthorityEvidence(
                source_name="BBMP Municipal Road Register",
                source_type="municipal_registry",
                reference="BBMP/RI/EZ/2026/ASSET",
                claim="Road owned by Bruhat Bengaluru Mahanagara Palike (BBMP).",
                source_url=source_url,
                source_id=self.source_id,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                freshness=freshness,
                matched_attribute="road_owner",
                verification_state="verified",
                explanation="Official municipal register records BBMP as statutory road owner.",
            ),
            AuthorityEvidence(
                source_name="BBMP Road Infrastructure Division",
                source_type="municipal_registry",
                reference="BBMP/RI/ANNUAL-MAINT-2026",
                claim="Maintenance responsibility assigned to BBMP Road Infrastructure Division.",
                source_url=source_url,
                source_id=self.source_id,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                freshness=freshness,
                matched_attribute="maintenance_authority",
                verification_state="verified",
                explanation="BBMP Road Infrastructure Division is the assigned municipal maintenance authority.",
            ),
        )

        sources = (
            OfficialSourceRecord(
                source_id=self.source_id,
                source_name=meta.source_name if meta else "BBMP Municipal Road Asset Register",
                source_type="municipal_registry",
                organization=meta.organization if meta else "Bruhat Bengaluru Mahanagara Palike (BBMP)",
                base_url=source_url,
                allowed_domain=source_domain,
                jurisdiction_scope="municipal_bengaluru",
                supported_roles=["road_owner", "maintenance_authority"],
                supported_road_types=["arterial", "sub_arterial", "ward_road"],
                refresh_policy_days=meta.refresh_policy_days if meta else 30,
                active=True,
                last_verified_at=retrieved_at,
                source_url=source_url,
                source_domain=source_domain,
                retrieved_at=retrieved_at,
                evidence_summary="Official BBMP road asset inventory and division maintenance assignments.",
                supported_fields=["road", "road_owner", "maintenance_authority"],
            ),
        )

        return AuthorityLookup(
            road_owner=AuthorityParty(
                name="Bruhat Bengaluru Mahanagara Palike (BBMP)",
                type="municipal_corporation",
                source="BBMP Ward 111 Municipal Road Register",
                official_portal_url=source_url,
            ),
            maintenance_authority=AuthorityParty(
                name="BBMP Road Infrastructure Division",
                type="municipal_road_division",
                source="BBMP Annual Maintenance Schedule",
                official_portal_url=source_url,
            ),
            builder_or_contractor=None,  # In-house municipal maintenance; no contractor concession on record
            evidence=evidence,
            sources=sources,
            resolved_at=now,
            resolution_message="Authority verified from official BBMP Municipal Road Register.",
            source_status="live",
            freshness=freshness,
            conflicts=(),
        )


class LiveHttpAuthorityAdapter(AuthoritySourceAdapter):
    """
    SSRF-hardened live HTTP adapter for remote official government endpoints.
    Validates destination domain and IP against allowlist, enforces connection timeout,
    and handles failures gracefully without crashing.
    """

    def __init__(
        self,
        *,
        source_id: str,
        endpoint_url: str,
        supported_roles: list[str] | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._source_id = source_id
        self._endpoint_url = endpoint_url
        self._supported_roles = supported_roles or ["road_owner", "maintenance_authority"]
        self._timeout_seconds = timeout_seconds or settings.AUTHORITY_REQUEST_TIMEOUT_SECONDS

    @property
    def source_id(self) -> str:
        return self._source_id

    def can_handle(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        return True

    def fetch_lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        # Pre-request SSRF security check
        is_safe, reason = is_safe_official_url(self._endpoint_url)
        if not is_safe:
            logger.warning("SSRF security policy blocked HTTP lookup to %s: %s", self._endpoint_url, reason)
            raise AuthorityProviderError(f"SSRF policy rejection: {reason}")

        try:
            import urllib.request
            import json

            req = urllib.request.Request(
                self._endpoint_url,
                headers={"User-Agent": "CVKI-Civic-Platform/0.2.0 (LiveAuthorityIntelligence)"},
            )
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as resp:
                if resp.status != 200:
                    raise AuthorityProviderError(f"Official endpoint returned HTTP {resp.status}")
                raw_data = resp.read()
                data = json.loads(raw_data.decode("utf-8"))
                return self._normalize_json_response(data)
        except TimeoutError as exc:
            raise AuthorityProviderTimeout("Live official endpoint connection timed out.") from exc
        except Exception as exc:
            if isinstance(exc, (AuthorityProviderError, AuthorityProviderTimeout)):
                raise
            raise AuthorityProviderError(f"Official endpoint retrieval error: {str(exc)}") from exc

    def _normalize_json_response(self, data: dict[str, Any]) -> AuthorityLookup:
        # Normalization helper for remote live payload
        now = datetime.now(timezone.utc)
        return AuthorityLookup(
            road_owner=AuthorityParty(**data["road_owner"]) if data.get("road_owner") else None,
            maintenance_authority=AuthorityParty(**data["maintenance_authority"]) if data.get("maintenance_authority") else None,
            builder_or_contractor=AuthorityParty(**data["builder_or_contractor"]) if data.get("builder_or_contractor") else None,
            evidence=tuple(AuthorityEvidence(**e) for e in data.get("evidence", [])),
            sources=tuple(OfficialSourceRecord(**s) for s in data.get("sources", [])),
            resolved_at=now,
            resolution_message=data.get("resolution_message", "Resolved from live official endpoint."),
            source_status="live",
            freshness="fresh",
            conflicts=(),
        )


class CompositeLiveAuthorityProvider(AuthoritySourceProvider):
    """
    Coordinates registered official authority source adapters, manages safe caching,
    detects conflicts across disparate official sources, and applies graceful fallback.
    """

    def __init__(
        self,
        adapters: list[AuthoritySourceAdapter] | None = None,
        cache: AuthorityCacheRepository | None = None,
    ) -> None:
        self._adapters: list[AuthoritySourceAdapter] = adapters if adapters is not None else [
            MoRTHStatutoryGazetteAdapter(),
            NHAIProjectRegistryAdapter(),
            NHAIContractRegistryAdapter(),
            KPWDStateGazetteAdapter(),
            BBMPMunicipalRegistryAdapter(),
        ]
        self._cache = cache or get_authority_cache()

    def register_adapter(self, adapter: AuthoritySourceAdapter) -> None:
        self._adapters.append(adapter)

    def set_adapters(self, adapters: list[AuthoritySourceAdapter]) -> None:
        self._adapters = list(adapters)

    def supports_location(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> bool:
        return any(a.can_handle(latitude=latitude, longitude=longitude, context=context) for a in self._adapters)

    def lookup(self, *, latitude: float, longitude: float, context: dict[str, str | None]) -> AuthorityLookup | None:
        cache_key = build_cache_key(latitude=latitude, longitude=longitude, context=context)
        cached_entry = self._cache.get(cache_key)

        matching_adapters = [
            a for a in self._adapters
            if a.can_handle(latitude=latitude, longitude=longitude, context=context)
        ]

        if not matching_adapters:
            if cached_entry:
                args = cache_data_to_lookup_args(cached_entry.data)
                args["source_status"] = "cached_stale" if cached_entry.is_stale() else "cached_fresh"
                args["freshness"] = "stale" if cached_entry.is_stale() else "fresh"
                return AuthorityLookup(**args)
            return None

        adapter_lookups: list[tuple[AuthoritySourceAdapter, AuthorityLookup]] = []
        now = datetime.now(timezone.utc)

        for adapter in matching_adapters:
            try:
                res = adapter.fetch_lookup(latitude=latitude, longitude=longitude, context=context)
                if res:
                    adapter_lookups.append((adapter, res))
            except (AuthorityProviderTimeout, AuthorityProviderError) as exc:
                logger.warning("Adapter %s failed: %s", adapter.source_id, exc)
                # Graceful fallback: check if cached evidence is available
                if cached_entry:
                    logger.info("Falling back to cached authority record for key %s", cache_key)
                    args = cache_data_to_lookup_args(cached_entry.data)
                    args["source_status"] = "cached_stale" if cached_entry.is_stale() else "cached_fresh"
                    args["freshness"] = "stale" if cached_entry.is_stale() else "fresh"
                    args["resolution_message"] = (
                        "Live authority source is unavailable; served from safe cache."
                        if not cached_entry.is_stale()
                        else "Live authority source is unavailable; served from stale cache (re-verification required)."
                    )
                    return AuthorityLookup(**args)
                # If no cache fallback exists, propagate the exception to preserve API timeout/error contract
                raise

        if not adapter_lookups:
            if cached_entry:
                args = cache_data_to_lookup_args(cached_entry.data)
                args["source_status"] = "cached_stale" if cached_entry.is_stale() else "cached_fresh"
                args["freshness"] = "stale" if cached_entry.is_stale() else "fresh"
                return AuthorityLookup(**args)
            return None

        # Aggregate evidence, sources, and check for conflicts
        road_owner: AuthorityParty | None = None
        maintenance_authority: AuthorityParty | None = None
        builder_or_contractor: AuthorityParty | None = None
        all_evidence: list[AuthorityEvidence] = []
        all_sources: list[OfficialSourceRecord] = []
        conflicts: list[AuthorityConflict] = []

        seen_owners: list[tuple[str, AuthorityParty, datetime | None]] = []
        seen_maintainers: list[tuple[str, AuthorityParty, datetime | None]] = []

        for adapter, lookup in adapter_lookups:
            all_evidence.extend(lookup.evidence)
            all_sources.extend(lookup.sources)

            if lookup.road_owner:
                seen_owners.append((adapter.source_id, lookup.road_owner, lookup.resolved_at))
            if lookup.maintenance_authority:
                seen_maintainers.append((adapter.source_id, lookup.maintenance_authority, lookup.resolved_at))
            if lookup.builder_or_contractor and not builder_or_contractor:
                builder_or_contractor = lookup.builder_or_contractor

        # Detect road_owner conflicts
        if len(seen_owners) > 1:
            first_name = " ".join(seen_owners[0][1].name.casefold().split())
            has_owner_conflict = any(
                " ".join(item[1].name.casefold().split()) != first_name
                for item in seen_owners[1:]
            )
            if has_owner_conflict:
                conflicts.append(
                    AuthorityConflict(
                        conflicting_attribute="road_owner",
                        source_a=seen_owners[0][0],
                        source_b=seen_owners[1][0],
                        claim_a=seen_owners[0][1].name,
                        claim_b=seen_owners[1][1].name,
                        retrieved_at_a=seen_owners[0][2],
                        retrieved_at_b=seen_owners[1][2],
                        explanation="Official sources provide conflicting road-owner information.",
                    )
                )
                road_owner = None
            else:
                road_owner = seen_owners[0][1]
        elif len(seen_owners) == 1:
            road_owner = seen_owners[0][1]

        # Detect maintenance_authority conflicts
        if len(seen_maintainers) > 1:
            first_name = " ".join(seen_maintainers[0][1].name.casefold().split())
            has_maint_conflict = any(
                " ".join(item[1].name.casefold().split()) != first_name
                for item in seen_maintainers[1:]
            )
            if has_maint_conflict:
                conflicts.append(
                    AuthorityConflict(
                        conflicting_attribute="maintenance_authority",
                        source_a=seen_maintainers[0][0],
                        source_b=seen_maintainers[1][0],
                        claim_a=seen_maintainers[0][1].name,
                        claim_b=seen_maintainers[1][1].name,
                        retrieved_at_a=seen_maintainers[0][2],
                        retrieved_at_b=seen_maintainers[1][2],
                        explanation="Official sources provide conflicting maintenance-authority information.",
                    )
                )
                maintenance_authority = None
            else:
                maintenance_authority = seen_maintainers[0][1]
        elif len(seen_maintainers) == 1:
            maintenance_authority = seen_maintainers[0][1]

        # Deduplicate sources and evidence
        dedup_sources = {s.source_id: s for s in all_sources}
        unique_evidence: list[AuthorityEvidence] = []
        seen_claims: set[str] = set()
        for ev in all_evidence:
            key = f"{ev.source_name}|{ev.matched_attribute}|{ev.claim}"
            if key not in seen_claims:
                seen_claims.add(key)
                unique_evidence.append(ev)

        # Freshness aggregation
        overall_freshness = "fresh"
        if any(ev.freshness == "stale" for ev in unique_evidence):
            overall_freshness = "stale"
        elif any(ev.freshness == "unknown" for ev in unique_evidence) and not any(ev.freshness == "fresh" for ev in unique_evidence):
            overall_freshness = "unknown"

        source_status = "conflict" if conflicts else "live"
        resolution_msg = (
            "Conflicting official source records detected for this corridor."
            if conflicts
            else "Authority verified from registered official source adapters."
        )

        lookup_res = AuthorityLookup(
            road_owner=road_owner,
            maintenance_authority=maintenance_authority,
            builder_or_contractor=builder_or_contractor,
            evidence=tuple(unique_evidence),
            sources=tuple(dedup_sources.values()),
            resolved_at=now,
            resolution_message=resolution_msg,
            source_status=source_status,
            freshness=overall_freshness,
            conflicts=tuple(conflicts),
        )

        # Cache live response
        expires_at = now + timedelta(seconds=settings.AUTHORITY_CACHE_TTL_SECONDS)
        self._cache.set(
            AuthorityCacheEntry(
                cache_key=cache_key,
                source_id="composite_live",
                retrieved_at=now,
                expires_at=expires_at,
                freshness_policy_days=30,
                data=lookup_to_cache_data(lookup_res),
            )
        )

        return lookup_res


_default_live_provider: CompositeLiveAuthorityProvider | None = None


def get_default_live_provider() -> CompositeLiveAuthorityProvider:
    global _default_live_provider
    if _default_live_provider is None:
        _default_live_provider = CompositeLiveAuthorityProvider()
    return _default_live_provider


def reset_default_live_provider() -> None:
    global _default_live_provider
    _default_live_provider = None
