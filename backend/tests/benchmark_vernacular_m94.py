"""
CVKI - M9.4 Performance Benchmark Script
Benchmarks MultilingualVernacularNormalizer operations across 100 warmup-stabilized iterations.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("backend"))

import statistics
import time

from app.services.multimodal.vernacular_normalizer import (
    MultilingualVernacularNormalizer,
)


def benchmark_m94():
    ITERATIONS = 100
    normalizer = MultilingualVernacularNormalizer()
    text = "pani road pe jama h near MG Road and sign board toota gya h"

    # Warmup
    for _ in range(10):
        _ = normalizer.normalize(text)

    # 1. Normalization latency
    latencies = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        _ = normalizer.normalize(text)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

    # 2. Repeated normalization on varied language samples
    samples = [
        "manhole khula pada hai naali ke paas",
        "सड़क पर भारी जलभराव है",
        "traffic sign missing near metro pillar 42",
        "shayad road pe paani hai pata nahi",
    ]
    repeated_latencies = []
    for _ in range(ITERATIONS):
        s = samples[_ % len(samples)]
        t0 = time.perf_counter()
        _ = normalizer.normalize(s)
        t1 = time.perf_counter()
        repeated_latencies.append((t1 - t0) * 1000.0)

    def print_stats(name, lats):
        print(f"=== {name} (sample count: {len(lats)}) ===")
        print(f"  Mean:   {statistics.mean(lats):.4f} ms")
        print(f"  Median: {statistics.median(lats):.4f} ms")
        print(f"  Min:    {min(lats):.4f} ms")
        print(f"  Max:    {max(lats):.4f} ms")

    print_stats("M9.4 Vernacular Normalization", latencies)
    print_stats("M9.4 Repeated Multi-Language Normalization", repeated_latencies)


if __name__ == "__main__":
    benchmark_m94()
