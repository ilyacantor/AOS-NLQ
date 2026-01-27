#!/usr/bin/env python3
"""
Performance benchmarking script for AOS-NLQ.

Measures:
- Query parsing latency
- Period resolution latency
- Fact base query latency
- End-to-end response time

Usage:
    python scripts/benchmark.py
    python scripts/benchmark.py --iterations 100
"""

import argparse
import statistics
import sys
import time
from datetime import date
from pathlib import Path
from typing import Callable, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


REFERENCE_DATE = date(2026, 1, 27)


def benchmark(func: Callable, iterations: int = 50, warmup: int = 5) -> dict:
    """
    Benchmark a function.

    Args:
        func: Function to benchmark (no arguments)
        iterations: Number of iterations
        warmup: Number of warmup iterations

    Returns:
        Dict with timing statistics
    """
    # Warmup
    for _ in range(warmup):
        func()

    # Benchmark
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms

    return {
        "min_ms": min(times),
        "max_ms": max(times),
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0,
        "p95_ms": sorted(times)[int(len(times) * 0.95)],
        "iterations": iterations,
    }


def benchmark_period_resolver(iterations: int) -> dict:
    """Benchmark period resolution."""
    from src.nlq.core.resolver import PeriodResolver

    resolver = PeriodResolver(reference_date=REFERENCE_DATE)

    test_periods = [
        "last_year",
        "this_year",
        "last_quarter",
        "this_quarter",
        "2024",
        "Q4 2025",
        "2025-Q3",
    ]

    def run():
        for period in test_periods:
            resolver.resolve(period)

    return benchmark(run, iterations)


def benchmark_fact_base_query(iterations: int) -> dict:
    """Benchmark fact base queries."""
    from src.nlq.knowledge.fact_base import FactBase

    fb = FactBase()
    fb_path = project_root / "data" / "fact_base.json"
    if not fb_path.exists():
        return {"error": "Fact base not found"}

    fb.load(fb_path)

    available_periods = list(fb.available_periods)[:4]
    metrics = ["revenue", "bookings", "gross_margin_pct", "net_income"]

    def run():
        for period in available_periods:
            for metric in metrics:
                fb.query(metric, period)

    return benchmark(run, iterations)


def benchmark_synonym_normalization(iterations: int) -> dict:
    """Benchmark synonym normalization."""
    from src.nlq.knowledge.synonyms import normalize_metric, normalize_period

    test_metrics = [
        "sales", "revenue", "top line", "turnover",
        "profit", "bottom line", "net income",
        "ebit", "operating profit", "gross margin"
    ]

    test_periods = [
        "last year", "prior year", "previous quarter",
        "this quarter", "current year"
    ]

    def run():
        for m in test_metrics:
            normalize_metric(m)
        for p in test_periods:
            normalize_period(p)

    return benchmark(run, iterations)


def benchmark_confidence_calculation(iterations: int) -> dict:
    """Benchmark confidence score calculation."""
    from src.nlq.core.confidence import ConfidenceCalculator, bounded_confidence

    calculator = ConfidenceCalculator()

    def run():
        # Various scenarios
        for intent in [0.0, 0.5, 1.0]:
            for entity in [0.0, 0.5, 1.0]:
                for data in [0.0, 0.5, 1.0]:
                    score = calculator.calculate(intent, entity, data)
                    bounded_confidence(score)

    return benchmark(run, iterations)


def print_results(name: str, results: dict) -> None:
    """Print benchmark results."""
    if "error" in results:
        print(f"\n{name}:")
        print(f"  ERROR: {results['error']}")
        return

    print(f"\n{name}:")
    print(f"  Iterations: {results['iterations']}")
    print(f"  Mean:   {results['mean_ms']:.3f} ms")
    print(f"  Median: {results['median_ms']:.3f} ms")
    print(f"  Min:    {results['min_ms']:.3f} ms")
    print(f"  Max:    {results['max_ms']:.3f} ms")
    print(f"  P95:    {results['p95_ms']:.3f} ms")
    print(f"  Stdev:  {results['stdev_ms']:.3f} ms")


def main():
    parser = argparse.ArgumentParser(description="Benchmark AOS-NLQ performance")
    parser.add_argument("--iterations", "-n", type=int, default=50,
                       help="Number of benchmark iterations")
    args = parser.parse_args()

    print("=" * 60)
    print("AOS-NLQ PERFORMANCE BENCHMARK")
    print("=" * 60)
    print(f"Iterations per benchmark: {args.iterations}")

    # Run benchmarks
    print("\nRunning benchmarks...")

    results = {
        "Period Resolution": benchmark_period_resolver(args.iterations),
        "Fact Base Query": benchmark_fact_base_query(args.iterations),
        "Synonym Normalization": benchmark_synonym_normalization(args.iterations),
        "Confidence Calculation": benchmark_confidence_calculation(args.iterations),
    }

    # Print results
    for name, result in results.items():
        print_results(name, result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_mean = sum(
        r.get("mean_ms", 0) for r in results.values() if "error" not in r
    )
    print(f"\nTotal processing overhead (excluding LLM): {total_mean:.3f} ms")
    print("\nNote: LLM latency (Claude API) is typically 500-2000ms additional")
    print("Target: Total response time < 2000ms")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
