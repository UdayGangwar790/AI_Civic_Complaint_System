"""
CVKI - Civic Vision & Knowledge Intelligence
Module 11.3: Observability, Audit Monitoring & Operational Metrics
"""

from collections import defaultdict
from dataclasses import dataclass, field
import math
import re
from threading import Lock
import time
from typing import Any, Optional


SENSITIVE_KEY_PATTERNS = [
    re.compile(r"pass(word)?", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"key", re.IGNORECASE),
    re.compile(r"auth", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"jwt", re.IGNORECASE),
]


def redact_sensitive_value(key: str, value: Any) -> Any:
    """
    Redacts sensitive field values such as passwords, tokens, API keys, and JWTs.
    """
    if value is None:
        return None
    for pattern in SENSITIVE_KEY_PATTERNS:
        if pattern.search(key):
            if isinstance(value, str):
                if len(value) <= 6:
                    return "***"
                return f"{value[:2]}***{value[-2:]}"
            return "***"
    return value


def redact_sensitive_dict(data: Any) -> Any:
    """
    Recursively redacts sensitive keys from a dict or list structure.
    """
    if isinstance(data, dict):
        return {k: redact_sensitive_dict(redact_sensitive_value(k, v)) for k, v in data.items()}
    elif isinstance(data, list):
        return [redact_sensitive_dict(item) for item in data]
    return data


def compute_percentiles(values: list[float]) -> dict[str, float]:
    """
    Computes count, mean, median, P95, P99, and max for a list of numeric values.
    """
    if not values:
        return {
            "count": 0,
            "mean_ms": 0.0,
            "median_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "max_ms": 0.0,
        }
    sorted_v = sorted(values)
    n = len(sorted_v)
    mean_v = sum(sorted_v) / n

    def p(pct: float) -> float:
        if n == 1:
            return sorted_v[0]
        k = (n - 1) * (pct / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_v[int(k)]
        d0 = sorted_v[int(f)] * (c - k)
        d1 = sorted_v[int(c)] * (k - f)
        return d0 + d1

    return {
        "count": n,
        "mean_ms": round(mean_v, 3),
        "median_ms": round(p(50), 3),
        "p95_ms": round(p(95), 3),
        "p99_ms": round(p(99), 3),
        "max_ms": round(sorted_v[-1], 3),
    }


class MetricsCollector:
    """
    Thread-safe in-memory operational metrics collector.
    Collects performance metrics, latency percentiles, error classifications,
    cache effectiveness, and civic intelligence lifecycle outcomes.
    """

    _MAX_LATENCY_RESERVOIR = 5_000

    def __init__(self) -> None:
        self._lock = Lock()
        self._api_requests_total = 0
        self._api_errors_total = 0
        self._api_latencies: list[float] = []
        self._api_status_counts: dict[int, int] = defaultdict(int)
        self._api_error_categories: dict[str, int] = defaultdict(int)

        self._cv_latencies: list[float] = []
        self._decision_support_latencies: list[float] = []
        self._authority_latencies: list[float] = []
        self._external_provider_latencies: dict[str, list[float]] = defaultdict(list)
        self._gov_integration_latencies: list[float] = []

        self._cache_hits: dict[str, int] = defaultdict(int)
        self._cache_misses: dict[str, int] = defaultdict(int)

        self._field_inspection_audits: dict[str, int] = defaultdict(int)
        self._decision_recommendations: dict[str, int] = defaultdict(int)
        self._human_reviews_count: int = 0
        self._unknown_outcomes_count: int = 0

    def record_api_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        error_category: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._api_requests_total += 1
            self._api_status_counts[status_code] += 1
            if len(self._api_latencies) < self._MAX_LATENCY_RESERVOIR:
                self._api_latencies.append(duration_ms)
            else:
                self._api_latencies[self._api_requests_total % self._MAX_LATENCY_RESERVOIR] = duration_ms

            if status_code >= 400:
                self._api_errors_total += 1
                cat = error_category or f"http_{status_code}"
                self._api_error_categories[cat] += 1

    def record_cv_inference(self, duration_ms: float) -> None:
        with self._lock:
            if len(self._cv_latencies) < self._MAX_LATENCY_RESERVOIR:
                self._cv_latencies.append(duration_ms)
            else:
                self._cv_latencies[len(self._cv_latencies) % self._MAX_LATENCY_RESERVOIR] = duration_ms

    def record_decision_support(self, duration_ms: float, priority: Optional[str] = None) -> None:
        with self._lock:
            if len(self._decision_support_latencies) < self._MAX_LATENCY_RESERVOIR:
                self._decision_support_latencies.append(duration_ms)
            if priority:
                self._decision_recommendations[priority] += 1

    def record_authority_resolution(self, duration_ms: float, cache_hit: bool = False) -> None:
        with self._lock:
            if len(self._authority_latencies) < self._MAX_LATENCY_RESERVOIR:
                self._authority_latencies.append(duration_ms)
            if cache_hit:
                self._cache_hits["authority"] += 1
            else:
                self._cache_misses["authority"] += 1

    def record_external_provider(self, provider: str, duration_ms: float, success: bool = True) -> None:
        with self._lock:
            reservoir = self._external_provider_latencies[provider]
            if len(reservoir) < 1_000:
                reservoir.append(duration_ms)
            if not success:
                self._unknown_outcomes_count += 1

    def record_government_integration(self, duration_ms: float, outcome: str) -> None:
        with self._lock:
            if len(self._gov_integration_latencies) < self._MAX_LATENCY_RESERVOIR:
                self._gov_integration_latencies.append(duration_ms)
            if "unknown" in outcome.lower() or "timeout" in outcome.lower():
                self._unknown_outcomes_count += 1

    def record_cache_access(self, cache_name: str, hit: bool) -> None:
        with self._lock:
            if hit:
                self._cache_hits[cache_name] += 1
            else:
                self._cache_misses[cache_name] += 1

    def record_field_inspection_audit(self, outcome: str) -> None:
        with self._lock:
            self._field_inspection_audits[outcome] += 1

    def record_human_review(self) -> None:
        with self._lock:
            self._human_reviews_count += 1

    def record_unknown_outcome(self) -> None:
        with self._lock:
            self._unknown_outcomes_count += 1

    def get_metrics_summary(self) -> dict[str, Any]:
        with self._lock:
            api_latency_summary = compute_percentiles(self._api_latencies)
            cv_latency_summary = compute_percentiles(self._cv_latencies)
            ds_latency_summary = compute_percentiles(self._decision_support_latencies)
            auth_latency_summary = compute_percentiles(self._authority_latencies)
            gov_latency_summary = compute_percentiles(self._gov_integration_latencies)

            ext_summaries = {
                prov: compute_percentiles(lats)
                for prov, lats in self._external_provider_latencies.items()
            }

            total_hits = sum(self._cache_hits.values())
            total_misses = sum(self._cache_misses.values())
            total_cache_reqs = total_hits + total_misses
            hit_ratio = round(total_hits / total_cache_reqs, 4) if total_cache_reqs > 0 else 0.0

            return {
                "api": {
                    "requests_total": self._api_requests_total,
                    "errors_total": self._api_errors_total,
                    "status_counts": dict(self._api_status_counts),
                    "error_categories": dict(self._api_error_categories),
                    "latency": api_latency_summary,
                },
                "subsystems": {
                    "cv_inference": cv_latency_summary,
                    "decision_support": ds_latency_summary,
                    "authority_resolution": auth_latency_summary,
                    "government_integration": gov_latency_summary,
                    "external_providers": ext_summaries,
                },
                "cache": {
                    "hits": dict(self._cache_hits),
                    "misses": dict(self._cache_misses),
                    "overall_hit_ratio": hit_ratio,
                },
                "operational_outcomes": {
                    "field_inspection_audits": dict(self._field_inspection_audits),
                    "decision_recommendations": dict(self._decision_recommendations),
                    "human_reviews_recorded": self._human_reviews_count,
                    "unknown_outcomes": self._unknown_outcomes_count,
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._api_requests_total = 0
            self._api_errors_total = 0
            self._api_latencies.clear()
            self._api_status_counts.clear()
            self._api_error_categories.clear()
            self._cv_latencies.clear()
            self._decision_support_latencies.clear()
            self._authority_latencies.clear()
            self._external_provider_latencies.clear()
            self._gov_integration_latencies.clear()
            self._cache_hits.clear()
            self._cache_misses.clear()
            self._field_inspection_audits.clear()
            self._decision_recommendations.clear()
            self._human_reviews_count = 0
            self._unknown_outcomes_count = 0


metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    return metrics_collector
