"""
CVKI M6.1 Live Authority Intelligence Test Suite.
Validates official source registry, adapters, freshness tracking, safe caching,
fallback, conflict detection, builder safety, SSRF protection, and API contracts.
"""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
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
    NoConfiguredAuthorityProvider,
    resolve_authority,
    set_authority_provider,
)
from app.services.authority_adapter import (
    BBMPMunicipalRegistryAdapter,
    CompositeLiveAuthorityProvider,
    KPWDStateGazetteAdapter,
    LiveHttpAuthorityAdapter,
    MoRTHStatutoryGazetteAdapter,
    NHAIContractRegistryAdapter,
    NHAIProjectRegistryAdapter,
    get_default_live_provider,
    reset_default_live_provider,
)
from app.services.authority_cache import (
    AuthorityCacheEntry,
    InMemoryAuthorityCache,
    build_cache_key,
    get_authority_cache,
    lookup_to_cache_data,
    set_authority_cache,
)
from app.services.authority_registry import (
    OfficialSourceDefinition,
    get_official_source,
    is_safe_official_url,
    list_official_sources,
    register_official_source,
    reset_source_registry,
)


class TestLiveAuthorityM61(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def setUp(self):
        reset_source_registry()
        reset_default_live_provider()
        self.test_cache = InMemoryAuthorityCache()
        set_authority_cache(self.test_cache)
        set_authority_provider(NoConfiguredAuthorityProvider())

    def tearDown(self):
        reset_source_registry()
        reset_default_live_provider()
        set_authority_provider(NoConfiguredAuthorityProvider())

    # A. Official source accepted
    def test_A_official_source_accepted(self):
        live_provider = CompositeLiveAuthorityProvider(cache=self.test_cache)
        res = resolve_authority(
            latitude=12.91,
            longitude=77.63,
            context={"road": "NH-44 Hosur Road", "city": "Bengaluru", "state": "Karnataka"},
            provider=live_provider,
        )
        self.assertEqual(res.authority_status, "verified")
        self.assertIsNotNone(res.road_owner)
        self.assertEqual(res.road_owner.name, "Ministry of Road Transport and Highways (MoRTH)")
        self.assertIsNotNone(res.maintenance_authority)
        self.assertEqual(res.maintenance_authority.name, "National Highways Authority of India (NHAI)")
        self.assertIn(res.source_status, ["live", "cached_fresh"])
        source_ids = [s.source_id for s in res.sources]
        self.assertIn("src_morth_gazette", source_ids)
        self.assertIn("src_nhai_portal", source_ids)

    # B. Non-allowlisted source rejected
    def test_B_non_allowlisted_source_rejected(self):
        fake_source = OfficialSourceRecord(
            source_id="src_fake_portal",
            source_name="Fake Civic Blog",
            source_type="blog",
            source_url="https://untrusted-blog.xyz/claims",
            source_domain="untrusted-blog.xyz",
            evidence_summary="Random user submission",
        )
        fake_evidence = AuthorityEvidence(
            source_name="Fake Civic Blog",
            source_type="blog",
            claim="I maintain this street",
            source_url="https://untrusted-blog.xyz/claims",
            matched_attribute="maintenance_authority",
        )
        mock_provider = MagicMock()
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=None,
            maintenance_authority=AuthorityParty(name="Random Person"),
            evidence=(fake_evidence,),
            sources=(fake_source,),
        )
        res = resolve_authority(
            latitude=12.34,
            longitude=56.78,
            context={"road": "Test Lane"},
            provider=mock_provider,
        )
        self.assertEqual(res.authority_status, "not_verified")
        self.assertIsNone(res.maintenance_authority)
        self.assertTrue(any("disallowed" in lim.lower() or "rejected" in lim.lower() for lim in res.limitations))

    # C. Fresh evidence
    def test_C_fresh_evidence(self):
        now = datetime.now(timezone.utc)
        fresh_evidence = AuthorityEvidence(
            source_name="MoRTH Statutory Gazette",
            source_type="official_gazette",
            reference="Statutory Notification 2026",
            claim="Road is National Highway",
            source_url="https://morth.nic.in",
            retrieved_at=now - timedelta(days=5),
            matched_attribute="road",
        )
        mock_provider = MagicMock()
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="MoRTH", source="Gazette"),
            maintenance_authority=AuthorityParty(name="NHAI", source="Portal"),
            evidence=(
                fresh_evidence,
                AuthorityEvidence(
                    source_name="MoRTH Statutory Gazette",
                    source_type="official_gazette",
                    claim="Central Government ownership",
                    source_url="https://morth.nic.in",
                    retrieved_at=now - timedelta(days=5),
                    matched_attribute="road_owner",
                ),
                AuthorityEvidence(
                    source_name="NHAI Portal",
                    source_type="government_portal",
                    claim="NHAI maintains",
                    source_url="https://nhai.gov.in",
                    retrieved_at=now - timedelta(days=5),
                    matched_attribute="maintenance_authority",
                ),
            ),
            sources=(
                OfficialSourceRecord(
                    source_id="src_morth_gazette",
                    source_name="MoRTH Gazette",
                    source_type="official_gazette",
                    source_url="https://morth.nic.in",
                    retrieved_at=now - timedelta(days=5),
                ),
            ),
        )
        res = resolve_authority(
            latitude=12.9,
            longitude=77.6,
            context={"road": "NH-44"},
            provider=mock_provider,
        )
        self.assertEqual(res.freshness, "fresh")
        self.assertEqual(res.authority_status, "verified")

    # D. Stale evidence
    def test_D_stale_evidence(self):
        now = datetime.now(timezone.utc)
        stale_date = now - timedelta(days=120)  # > 30 days refresh policy
        stale_evidence = AuthorityEvidence(
            source_name="MoRTH Gazette",
            source_type="official_gazette",
            reference="Old 2024 Gazette",
            claim="Road is National Highway",
            source_url="https://morth.nic.in",
            retrieved_at=stale_date,
            matched_attribute="road",
        )
        mock_provider = MagicMock()
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="MoRTH", source="Gazette"),
            maintenance_authority=AuthorityParty(name="NHAI", source="Portal"),
            evidence=(
                stale_evidence,
                AuthorityEvidence(
                    source_name="MoRTH Gazette",
                    source_type="official_gazette",
                    claim="MoRTH owns road",
                    source_url="https://morth.nic.in",
                    retrieved_at=stale_date,
                    matched_attribute="road_owner",
                ),
                AuthorityEvidence(
                    source_name="NHAI Portal",
                    source_type="government_portal",
                    claim="NHAI maintains",
                    source_url="https://nhai.gov.in",
                    retrieved_at=stale_date,
                    matched_attribute="maintenance_authority",
                ),
            ),
            sources=(
                OfficialSourceRecord(
                    source_id="src_morth_gazette",
                    source_name="MoRTH Gazette",
                    source_type="official_gazette",
                    source_url="https://morth.nic.in",
                    retrieved_at=stale_date,
                ),
            ),
        )
        res = resolve_authority(
            latitude=12.9,
            longitude=77.6,
            context={"road": "NH-44"},
            provider=mock_provider,
        )
        self.assertEqual(res.freshness, "stale")
        self.assertTrue(any("stale" in lim.lower() for lim in res.limitations))

    # E. Unknown freshness
    def test_E_unknown_freshness(self):
        evidence_no_date = AuthorityEvidence(
            source_name="MoRTH Gazette",
            source_type="official_gazette",
            claim="Road is National Highway",
            source_url="https://morth.nic.in",
            retrieved_at=None,
            matched_attribute="road",
        )
        mock_provider = MagicMock()
        mock_provider.lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="MoRTH"),
            evidence=(evidence_no_date,),
            sources=(),
            freshness="unknown",
        )
        res = resolve_authority(
            latitude=12.9,
            longitude=77.6,
            context={"road": "NH-44"},
            provider=mock_provider,
        )
        self.assertEqual(res.freshness, "unknown")

    # F. Live source unavailable (without cache)
    def test_F_live_source_unavailable(self):
        failing_adapter = MagicMock()
        failing_adapter.source_id = "src_failing"
        failing_adapter.can_handle.return_value = True
        failing_adapter.fetch_lookup.side_effect = AuthorityProviderError("Gov server down")

        provider = CompositeLiveAuthorityProvider(adapters=[failing_adapter], cache=self.test_cache)
        with self.assertRaises(AuthorityProviderError):
            provider.lookup(latitude=12.34, longitude=56.78, context={"road": "Some Road"})

    # G. Cached evidence fallback
    def test_G_cached_evidence_fallback(self):
        context = {"road": "NH-44 Hosur Road", "city": "Bengaluru", "state": "Karnataka"}
        key = build_cache_key(latitude=12.91, longitude=77.63, context=context)
        now = datetime.now(timezone.utc)

        # Pre-seed cache with valid fresh entry
        cached_lookup = AuthorityLookup(
            road_owner=AuthorityParty(name="Ministry of Road Transport and Highways (MoRTH)"),
            maintenance_authority=AuthorityParty(name="National Highways Authority of India (NHAI)"),
            evidence=(
                AuthorityEvidence(
                    source_name="MoRTH Gazette",
                    source_type="official_gazette",
                    claim="Road is NH-44",
                    source_url="https://morth.nic.in",
                    matched_attribute="road",
                ),
            ),
            sources=(
                OfficialSourceRecord(
                    source_id="src_nhai_portal",
                    source_name="NHAI Portal",
                    source_type="government_portal",
                    source_url="https://nhai.gov.in",
                ),
            ),
            resolved_at=now,
            source_status="live",
            freshness="fresh",
        )
        self.test_cache.set(
            AuthorityCacheEntry(
                cache_key=key,
                source_id="seed",
                retrieved_at=now,
                expires_at=now + timedelta(hours=24),
                freshness_policy_days=30,
                data=lookup_to_cache_data(cached_lookup),
            )
        )

        # Adapter simulates timeout
        timeout_adapter = MagicMock()
        timeout_adapter.source_id = "src_timeout"
        timeout_adapter.can_handle.return_value = True
        timeout_adapter.fetch_lookup.side_effect = AuthorityProviderTimeout("Live gateway timed out")

        provider = CompositeLiveAuthorityProvider(adapters=[timeout_adapter], cache=self.test_cache)
        lookup = provider.lookup(latitude=12.91, longitude=77.63, context=context)

        self.assertIsNotNone(lookup)
        self.assertEqual(lookup.source_status, "cached_fresh")
        self.assertEqual(lookup.road_owner.name, "Ministry of Road Transport and Highways (MoRTH)")

    # H. Expired cache
    def test_H_expired_cache(self):
        context = {"road": "NH-44 Hosur Road", "city": "Bengaluru", "state": "Karnataka"}
        key = build_cache_key(latitude=12.91, longitude=77.63, context=context)
        now = datetime.now(timezone.utc)
        past = now - timedelta(days=60)

        entry = AuthorityCacheEntry(
            cache_key=key,
            source_id="seed",
            retrieved_at=past,
            expires_at=past + timedelta(days=30),  # expired 30 days ago
            freshness_policy_days=30,
            data=lookup_to_cache_data(
                AuthorityLookup(
                    road_owner=AuthorityParty(name="MoRTH"),
                    evidence=(),
                    sources=(),
                    resolved_at=past,
                )
            ),
        )
        self.assertTrue(entry.is_stale(now))

        self.test_cache.set(entry)
        timeout_adapter = MagicMock()
        timeout_adapter.source_id = "src_timeout"
        timeout_adapter.can_handle.return_value = True
        timeout_adapter.fetch_lookup.side_effect = AuthorityProviderTimeout("Timeout")

        provider = CompositeLiveAuthorityProvider(adapters=[timeout_adapter], cache=self.test_cache)
        lookup = provider.lookup(latitude=12.91, longitude=77.63, context=context)

        self.assertIsNotNone(lookup)
        self.assertEqual(lookup.source_status, "cached_stale")
        self.assertEqual(lookup.freshness, "stale")

    # I. Conflicting official sources
    def test_I_conflicting_official_sources(self):
        now = datetime.now(timezone.utc)
        adapter_nhai = MagicMock()
        adapter_nhai.source_id = "src_nhai_portal"
        adapter_nhai.can_handle.return_value = True
        adapter_nhai.fetch_lookup.return_value = AuthorityLookup(
            road_owner=AuthorityParty(name="Ministry of Road Transport and Highways (MoRTH)"),
            maintenance_authority=AuthorityParty(name="National Highways Authority of India (NHAI)"),
            evidence=(
                AuthorityEvidence(
                    source_name="MoRTH Gazette",
                    source_type="official_gazette",
                    claim="Corridor linked",
                    source_url="https://morth.nic.in",
                    matched_attribute="road",
                    retrieved_at=now,
                ),
                AuthorityEvidence(
                    source_name="MoRTH Gazette",
                    source_type="official_gazette",
                    claim="MoRTH owns road",
                    source_url="https://morth.nic.in",
                    matched_attribute="road_owner",
                    retrieved_at=now,
                ),
                AuthorityEvidence(
                    source_name="NHAI Portal",
                    source_type="government_portal",
                    claim="NHAI maintains corridor",
                    source_url="https://nhai.gov.in",
                    matched_attribute="maintenance_authority",
                    retrieved_at=now,
                ),
            ),
            sources=(
                OfficialSourceRecord(
                    source_id="src_nhai_portal",
                    source_name="NHAI Portal",
                    source_type="government_portal",
                    source_url="https://nhai.gov.in",
                ),
            ),
            resolved_at=now,
        )

        adapter_bbmp = MagicMock()
        adapter_bbmp.source_id = "src_bbmp_registry"
        adapter_bbmp.can_handle.return_value = True
        adapter_bbmp.fetch_lookup.return_value = AuthorityLookup(
            road_owner=None,
            maintenance_authority=AuthorityParty(name="Bruhat Bengaluru Mahanagara Palike (BBMP)"),
            evidence=(
                AuthorityEvidence(
                    source_name="BBMP Register",
                    source_type="municipal_registry",
                    claim="BBMP maintains corridor",
                    source_url="https://bbmp.gov.in",
                    matched_attribute="maintenance_authority",
                    retrieved_at=now,
                ),
            ),
            sources=(
                OfficialSourceRecord(
                    source_id="src_bbmp_registry",
                    source_name="BBMP Register",
                    source_type="municipal_registry",
                    source_url="https://bbmp.gov.in",
                ),
            ),
            resolved_at=now,
        )

        provider = CompositeLiveAuthorityProvider(adapters=[adapter_nhai, adapter_bbmp], cache=self.test_cache)
        res = resolve_authority(
            latitude=12.91,
            longitude=77.63,
            context={"road": "Border Corridor Road"},
            provider=provider,
        )

        # Conflict must be surfaced, NOT arbitrarily chosen
        self.assertEqual(res.source_status, "conflict")
        self.assertIsNone(res.maintenance_authority)
        self.assertEqual(len(res.conflicts), 1)
        conflict = res.conflicts[0]
        self.assertEqual(conflict.conflicting_attribute, "maintenance_authority")
        self.assertIn("NHAI", conflict.claim_a)
        self.assertIn("BBMP", conflict.claim_b)
        self.assertEqual(res.authority_status, "partially_verified")  # Road owner verified, maintainer in conflict

    # J. Road owner evidence
    def test_J_road_owner_evidence(self):
        adapter = MoRTHStatutoryGazetteAdapter()
        context = {"road": "NH-48 National Highway"}
        self.assertTrue(adapter.can_handle(latitude=12.5, longitude=77.5, context=context))
        lookup = adapter.fetch_lookup(latitude=12.5, longitude=77.5, context=context)
        self.assertIsNotNone(lookup.road_owner)
        self.assertEqual(lookup.road_owner.name, "Ministry of Road Transport and Highways (MoRTH)")
        self.assertTrue(any(e.matched_attribute == "road_owner" for e in lookup.evidence))

    # K. Maintenance authority evidence
    def test_K_maintenance_authority_evidence(self):
        adapter = NHAIProjectRegistryAdapter()
        context = {"road": "NH-44 Express Corridor"}
        self.assertTrue(adapter.can_handle(latitude=12.5, longitude=77.5, context=context))
        lookup = adapter.fetch_lookup(latitude=12.5, longitude=77.5, context=context)
        self.assertIsNotNone(lookup.maintenance_authority)
        self.assertEqual(lookup.maintenance_authority.name, "National Highways Authority of India (NHAI)")
        self.assertTrue(any(e.matched_attribute == "maintenance_authority" for e in lookup.evidence))

    # L. Builder evidence
    def test_L_builder_evidence(self):
        adapter = NHAIContractRegistryAdapter()
        context = {"road": "NH-44 Hosur Road Elevated Tollway"}
        self.assertTrue(adapter.can_handle(latitude=12.9, longitude=77.6, context=context))
        lookup = adapter.fetch_lookup(latitude=12.9, longitude=77.6, context=context)
        self.assertIsNotNone(lookup.builder_or_contractor)
        self.assertEqual(lookup.builder_or_contractor.name, "Bangalore Elevated Tollway Pvt Ltd")
        self.assertTrue(any(e.matched_attribute == "builder_or_contractor" for e in lookup.evidence))

    # M. Authority does NOT imply builder
    def test_M_authority_does_not_imply_builder(self):
        live_provider = CompositeLiveAuthorityProvider(
            adapters=[MoRTHStatutoryGazetteAdapter(), NHAIProjectRegistryAdapter()],
            cache=self.test_cache,
        )
        # Corridor with road owner and maintenance authority, but NO builder contract on record
        res = resolve_authority(
            latitude=12.9,
            longitude=77.6,
            context={"road": "NH-48 Corridor"},
            provider=live_provider,
        )
        self.assertIsNotNone(res.road_owner)
        self.assertIsNotNone(res.maintenance_authority)
        # Crucial check: builder MUST be None
        self.assertIsNone(res.builder_or_contractor)
        self.assertTrue(any("builder" in lim.lower() for lim in res.limitations))

    # N. Client cannot fabricate verification state
    def test_N_client_cannot_fabricate_verification_state(self):
        response = self.client.get(
            "/api/v1/authority/resolve?latitude=12.34&longitude=56.78&road=Arbitrary%20Road&verification_state=verified"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["authority"]
        self.assertEqual(data["authority_status"], "not_verified")
        self.assertIsNone(data["road_owner"])
        self.assertIsNone(data["maintenance_authority"])

    # O. Invalid URL
    def test_O_invalid_url(self):
        self.assertFalse(is_safe_official_url("")[0])
        self.assertFalse(is_safe_official_url("ftp://morth.nic.in")[0])
        self.assertFalse(is_safe_official_url("http:///missing-host")[0])
        self.assertFalse(is_safe_official_url("https://morth.nic.in:8080/")[0])

    # P. SSRF-sensitive URL rejection
    def test_P_ssrf_sensitive_url_rejection(self):
        # Cloud metadata
        safe, reason = is_safe_official_url("http://169.254.169.254/latest/meta-data")
        self.assertFalse(safe)
        self.assertIn("metadata", reason.lower())

        # Loopback
        safe, reason = is_safe_official_url("http://127.0.0.1/internal")
        self.assertFalse(safe)
        self.assertIn("loopback", reason.lower())

        # Localhost
        safe, reason = is_safe_official_url("http://localhost/secret")
        self.assertFalse(safe)
        self.assertIn("localhost", reason.lower())

        # Private RFC1918 subnets
        self.assertFalse(is_safe_official_url("http://10.0.0.1/")[0])
        self.assertFalse(is_safe_official_url("http://192.168.1.1/")[0])
        self.assertFalse(is_safe_official_url("http://172.16.0.1/")[0])

        # Non-allowlisted external domain
        safe, reason = is_safe_official_url("https://attacker-portal.evil.com/fake")
        self.assertFalse(safe)
        self.assertIn("allowlist", reason.lower())

        # Trusted official government domains
        self.assertTrue(is_safe_official_url("https://nhai.gov.in")[0])
        self.assertTrue(is_safe_official_url("https://morth.nic.in/gazette")[0])
        self.assertTrue(is_safe_official_url("https://bbmp.gov.in/assets")[0])

    # Q. Timeout and failure handling
    def test_Q_timeout_and_failure_handling(self):
        adapter = LiveHttpAuthorityAdapter(
            source_id="src_test_timeout",
            endpoint_url="https://nhai.gov.in/test-endpoint",
            timeout_seconds=0.001,
        )
        with self.assertRaises((AuthorityProviderTimeout, AuthorityProviderError)):
            adapter.fetch_lookup(latitude=12.0, longitude=77.0, context={})

    # Official source registry listing endpoint
    def test_sources_endpoint(self):
        response = self.client.get("/api/v1/authority/sources")
        self.assertEqual(response.status_code, 200)
        sources = response.json()
        self.assertGreaterEqual(len(sources), 4)
        source_ids = [s["source_id"] for s in sources]
        self.assertIn("src_morth_gazette", source_ids)
        self.assertIn("src_nhai_portal", source_ids)
        self.assertIn("src_bbmp_registry", source_ids)
