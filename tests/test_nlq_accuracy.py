#!/usr/bin/env python3
"""
NLQ Intent Recognition - Exhaustive Accuracy Testing

Tests every metric and time period combination through the tiered resolution system.
Goal: 100% accuracy without LLM calls.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.nlq.knowledge.synonyms import normalize_metric, METRIC_SYNONYMS, _METRIC_REVERSE_LOOKUP

import pytest
pytestmark = pytest.mark.skip(reason="fact_base removed — tests need rewrite for DCL")


@dataclass
class TestResult:
    query: str
    expected_metric: str
    expected_value: float
    actual_metric: Optional[str]
    actual_value: Optional[float]
    passed: bool
    failure_reason: str = ""
    tier: str = ""  # "exact", "embedding", "failed"


@dataclass
class TestReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    results: List[TestResult] = field(default_factory=list)
    missing_synonyms: Set[str] = field(default_factory=set)
    failed_queries: List[str] = field(default_factory=list)


def load_fact_base() -> Tuple[object, dict]:
    """Load fact base and return both the object and raw data."""
    raise RuntimeError("FactBase removed — needs rewrite for DCL")

    with open('data/fact_base.json', 'r') as f:
        raw_data = json.load(f)

    return fb, raw_data


def extract_all_metrics(raw_data: dict) -> Set[str]:
    """Extract all metric names from fact_base.json."""
    metrics = set()

    # From quarterly data
    if 'quarterly' in raw_data:
        for entry in raw_data['quarterly']:
            for key in entry.keys():
                if key not in ('year', 'quarter', 'period'):
                    metrics.add(key)

    # From annual data
    if 'annual' in raw_data:
        for year_data in raw_data['annual'].values():
            if isinstance(year_data, dict):
                for key in year_data.keys():
                    metrics.add(key)

    return metrics


def get_synonym_coverage(metrics: Set[str]) -> Tuple[Set[str], Set[str]]:
    """Check which metrics have synonyms defined."""
    covered = set()
    not_covered = set()

    for metric in metrics:
        if metric in METRIC_SYNONYMS or metric in _METRIC_REVERSE_LOOKUP:
            covered.add(metric)
        else:
            not_covered.add(metric)

    return covered, not_covered


def generate_query_variations(metric: str) -> List[str]:
    """Generate different query phrasings for a metric."""
    # Convert underscores to spaces for natural language
    natural_name = metric.replace("_", " ")

    variations = [
        # Bare term
        metric,
        natural_name,
        # What is/what's
        f"what is {metric}",
        f"what is {natural_name}",
        f"what's {natural_name}",
        f"whats {natural_name}",
        f"what's our {natural_name}",
        # Show me
        f"show me {natural_name}",
        # How much/how's
        f"how much {natural_name}",
        f"how is {natural_name}",
        # With periods
        f"{natural_name} 2025",
        f"{natural_name} this year",
        f"2025 {natural_name}",
    ]

    return variations


def generate_misspellings(word: str) -> List[str]:
    """Generate common misspellings of a word."""
    if len(word) < 3:
        return []

    misspellings = []

    # Double a letter
    for i in range(len(word)):
        misspellings.append(word[:i] + word[i] + word[i:])

    # Missing a letter
    for i in range(len(word)):
        misspellings.append(word[:i] + word[i+1:])

    # Transposed letters
    for i in range(len(word) - 1):
        chars = list(word)
        chars[i], chars[i+1] = chars[i+1], chars[i]
        misspellings.append(''.join(chars))

    return misspellings[:3]  # Limit to 3 variations


def test_metric_resolution(query: str, expected_metric: str, fb) -> TestResult:
    """Test if a query resolves to the expected metric."""
    # Tier 1: Try exact synonym match (mimics routes.py logic)
    query_clean = query.lower().strip()

    # Strip common prefixes (same as routes.py)
    prefixes = [
        "what is ", "what's ", "what was ", "whats ",
        "how much ", "how is ", "how's ", "hows ",
        "tell me ", "show me ", "get me ", "give me ",
        "our ", "the ", "current ", "total ",
        "can you show me ", "can you tell me ",
    ]
    for prefix in prefixes:
        if query_clean.startswith(prefix):
            query_clean = query_clean[len(prefix):]
    query_clean = query_clean.rstrip("?").strip()

    # Strip period suffixes (e.g., "revenue 2025", "margin this year")
    period_suffixes = [
        " 2024", " 2025", " 2026",
        " this year", " last year", " this quarter", " last quarter",
        " q1", " q2", " q3", " q4",
        " ytd", " mtd", " qtd",
    ]
    for suffix in period_suffixes:
        if query_clean.endswith(suffix):
            query_clean = query_clean[:-len(suffix)].strip()

    # Strip period prefixes (e.g., "2025 revenue", "q3 margin")
    period_prefixes = [
        "2024 ", "2025 ", "2026 ",
        "q1 ", "q2 ", "q3 ", "q4 ",
    ]
    for prefix in period_prefixes:
        if query_clean.startswith(prefix):
            query_clean = query_clean[len(prefix):].strip()

    # Try synonym lookup with cleaned query
    resolved = normalize_metric(query_clean)

    # Check if resolution matches expected
    if resolved == expected_metric:
        value = fb.query_annual(expected_metric, 2025)
        return TestResult(
            query=query,
            expected_metric=expected_metric,
            expected_value=value,
            actual_metric=resolved,
            actual_value=value,
            passed=True,
            tier="exact"
        )

    # Try original query (no cleaning) as fallback
    resolved_orig = normalize_metric(query.lower().strip().rstrip("?"))
    if resolved_orig == expected_metric:
        value = fb.query_annual(expected_metric, 2025)
        return TestResult(
            query=query,
            expected_metric=expected_metric,
            expected_value=value,
            actual_metric=resolved_orig,
            actual_value=value,
            passed=True,
            tier="exact"
        )

    # Check if resolved metric has the same VALUE as expected (handles aliases like sales=revenue)
    expected_value = fb.query_annual(expected_metric, 2025)
    resolved_value = fb.query_annual(resolved, 2025) if resolved else None

    if resolved_value is not None and expected_value is not None and resolved_value == expected_value:
        # Same value - this is an acceptable alias (e.g., sales -> revenue)
        return TestResult(
            query=query,
            expected_metric=expected_metric,
            expected_value=expected_value,
            actual_metric=resolved,
            actual_value=resolved_value,
            passed=True,
            tier="alias"
        )

    # Failed to resolve
    return TestResult(
        query=query,
        expected_metric=expected_metric,
        expected_value=expected_value,
        actual_metric=resolved if resolved != query_clean.replace(" ", "_") else None,
        actual_value=None,
        passed=False,
        failure_reason=f"Resolved to '{resolved}' instead of '{expected_metric}'",
        tier="failed"
    )


def run_accuracy_tests() -> TestReport:
    """Run comprehensive accuracy tests."""
    print("=" * 70)
    print("NLQ INTENT RECOGNITION - ACCURACY TESTING")
    print("=" * 70)

    fb, raw_data = load_fact_base()
    all_metrics = extract_all_metrics(raw_data)
    covered, not_covered = get_synonym_coverage(all_metrics)

    print(f"\nMetrics in fact_base.json: {len(all_metrics)}")
    print(f"  - With synonyms: {len(covered)}")
    print(f"  - Without synonyms: {len(not_covered)}")

    if not_covered:
        print(f"\n⚠️  Metrics MISSING synonym coverage:")
        for m in sorted(not_covered):
            print(f"    - {m}")

    report = TestReport()
    report.missing_synonyms = not_covered

    print("\n" + "=" * 70)
    print("TESTING METRIC RESOLUTION")
    print("=" * 70)

    # Test each metric
    for metric in sorted(all_metrics):
        variations = generate_query_variations(metric)

        for query in variations:
            result = test_metric_resolution(query, metric, fb)
            report.results.append(result)
            report.total += 1

            if result.passed:
                report.passed += 1
            else:
                report.failed += 1
                report.failed_queries.append(query)

    return report


def print_report(report: TestReport):
    """Print the test report."""
    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)

    print(f"\nTotal tests: {report.total}")
    print(f"Passed: {report.passed} ({100*report.passed/report.total:.1f}%)")
    print(f"Failed: {report.failed} ({100*report.failed/report.total:.1f}%)")

    if report.failed > 0:
        print(f"\n❌ FAILED QUERIES ({min(50, report.failed)} of {report.failed}):")
        print("-" * 70)

        failed_results = [r for r in report.results if not r.passed]
        for result in failed_results[:50]:
            print(f"  Query: '{result.query}'")
            print(f"    Expected: {result.expected_metric}")
            print(f"    Got: {result.actual_metric}")
            print(f"    Reason: {result.failure_reason}")
            print()

    if report.missing_synonyms:
        print(f"\n⚠️  METRICS NEEDING SYNONYMS ({len(report.missing_synonyms)}):")
        print("-" * 70)
        for metric in sorted(report.missing_synonyms):
            print(f"  - {metric}")

    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)

    # Analyze failure patterns
    failed_by_metric = {}
    for result in report.results:
        if not result.passed:
            metric = result.expected_metric
            if metric not in failed_by_metric:
                failed_by_metric[metric] = []
            failed_by_metric[metric].append(result.query)

    if failed_by_metric:
        print("\nMetrics with highest failure rates:")
        sorted_failures = sorted(failed_by_metric.items(), key=lambda x: -len(x[1]))
        for metric, queries in sorted_failures[:10]:
            print(f"  - {metric}: {len(queries)} failures")
            print(f"    Sample queries: {queries[:3]}")


def generate_missing_synonyms(report: TestReport) -> str:
    """Generate synonym entries for missing metrics."""
    lines = []
    lines.append("\n# Add these to METRIC_SYNONYMS in synonyms.py:\n")

    for metric in sorted(report.missing_synonyms):
        natural_name = metric.replace("_", " ")
        lines.append(f'    "{metric}": [')
        lines.append(f'        "{natural_name}",')

        # Generate some common variations
        words = metric.split("_")
        if len(words) > 1:
            # Abbreviated version
            abbrev = "".join(w[0] for w in words)
            lines.append(f'        "{abbrev}",')

        lines.append(f'    ],\n')

    return "\n".join(lines)


def generate_misspellings_for_metric(metric: str) -> List[Tuple[str, str]]:
    """Generate common misspellings for a metric. Returns (misspelled, correct) pairs."""
    natural_name = metric.replace("_", " ")
    words = natural_name.split()

    misspellings = []

    # Common typos
    typo_map = {
        "revenue": ["revnue", "reveune", "revennue", "revanue"],
        "margin": ["margn", "marginn", "mragin"],
        "ebitda": ["ebitd", "ebidta", "eebitda"],
        "pipeline": ["pieline", "pipleine", "pipline"],
        "headcount": ["headcont", "heacount", "headcoutn"],
        "churn": ["chrn", "churnn"],
        "quota": ["qouta", "quoat"],
        "attrition": ["attrtion", "attriton"],
    }

    for word in words:
        if word in typo_map:
            for typo in typo_map[word]:
                misspelled = natural_name.replace(word, typo)
                misspellings.append((misspelled, metric))

    return misspellings


def run_misspelling_tests(fb) -> Tuple[int, int, List[Tuple[str, str, str]]]:
    """Run misspelling tolerance tests. Returns (passed, failed, failures)."""
    # Common metrics to test misspellings for
    test_metrics = [
        "revenue", "gross_margin_pct", "ebitda", "pipeline", "headcount",
        "churn_pct", "quota_attainment_pct", "attrition_rate_pct", "nrr", "arr"
    ]

    passed = 0
    failed = 0
    failures = []

    for metric in test_metrics:
        misspellings = generate_misspellings_for_metric(metric)

        for misspelled, correct in misspellings:
            result = test_metric_resolution(misspelled, correct, fb)
            if result.passed:
                passed += 1
            else:
                failed += 1
                failures.append((misspelled, correct, result.actual_metric or "None"))

    return passed, failed, failures


if __name__ == "__main__":
    report = run_accuracy_tests()
    print_report(report)

    if report.missing_synonyms:
        print("\n" + "=" * 70)
        print("SUGGESTED SYNONYM ADDITIONS")
        print("=" * 70)
        print(generate_missing_synonyms(report))

    # Run misspelling tests
    print("\n" + "=" * 70)
    print("MISSPELLING TOLERANCE TESTS")
    print("=" * 70)
    fb, _ = load_fact_base()
    mis_passed, mis_failed, mis_failures = run_misspelling_tests(fb)
    mis_total = mis_passed + mis_failed
    if mis_total > 0:
        print(f"\nMisspelling tests: {mis_passed}/{mis_total} ({100*mis_passed/mis_total:.1f}%)")
        if mis_failures:
            print(f"\n⚠️  Failed misspellings ({len(mis_failures)}):")
            for misspelled, correct, got in mis_failures[:20]:
                print(f"  '{misspelled}' → expected '{correct}', got '{got}'")
    else:
        print("No misspelling tests generated.")

    # Exit with error code if tests failed
    if report.failed > 0:
        print(f"\n❌ {report.failed} standard tests failed!")
        sys.exit(1)
    elif mis_failed > mis_total * 0.05:  # Allow up to 5% misspelling failures
        print(f"\n⚠️  {mis_failed} misspelling tests failed (>{mis_total * 0.05:.0f} threshold)")
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        sys.exit(0)
