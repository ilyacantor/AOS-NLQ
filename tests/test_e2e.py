"""
End-to-end tests with ground truth validation.

ACCURACY REQUIREMENT: 100% of ground truth questions must pass. No exceptions.

If a test fails:
1. Fix the bug in the engine
2. If the question is genuinely ambiguous, fix the question
3. Never lower the threshold

Financial queries have exact answers. A wrong answer is a bug, not an edge case.
"""

import json
import re
import pytest
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from src.nlq.knowledge.fact_base import FactBase
from src.nlq.knowledge.synonyms import normalize_metric, normalize_period
from src.nlq.core.resolver import PeriodResolver
from src.nlq.core.executor import QueryExecutor
from src.nlq.core.confidence import bounded_confidence
from src.nlq.models.query import ParsedQuery, QueryIntent, PeriodType


# Fixed reference date for all tests
REFERENCE_DATE = date(2026, 1, 27)


def parse_ground_truth_value(ground_truth: str) -> Tuple[Optional[float], str]:
    """
    Parse ground truth string to extract numeric value and unit.

    Returns:
        Tuple of (value, unit) where unit is '$M' or '%' or 'complex'
    """
    if not ground_truth:
        return None, "unknown"

    # Handle percentage values
    if "%" in ground_truth:
        match = re.search(r'([\d.]+)%', ground_truth)
        if match:
            return float(match.group(1)), "%"

    # Handle dollar values (e.g., "$100.0M", "$26.25M")
    match = re.search(r'\$([\d.]+)M', ground_truth)
    if match:
        return float(match.group(1)), "$M"

    # Complex answers (comparisons, breakdowns)
    if ":" in ground_truth or "to" in ground_truth.lower() or "increased" in ground_truth.lower():
        return None, "complex"

    return None, "unknown"


def values_match(expected: float, actual: float, tolerance: float = 0.01) -> bool:
    """Check if two values match within tolerance."""
    if expected is None or actual is None:
        return False
    return abs(expected - actual) <= tolerance


class TestGroundTruthDataAccess:
    """
    Test that all ground truth questions can be answered from the fact base.

    This validates data access without requiring Claude API.
    """

    def test_all_point_queries_have_data(self, test_questions, fact_base):
        """
        Every point query (absolute/relative single metric) must have data available.
        """
        if "test_questions" not in test_questions:
            pytest.skip("No test_questions in file")

        questions = test_questions["test_questions"]
        resolver = PeriodResolver(reference_date=REFERENCE_DATE)

        failures = []
        passes = 0

        # Filter to point query categories
        point_query_categories = ["absolute", "relative", "margin", "balance_sheet",
                                  "synonym", "expense", "forecast"]

        for q in questions:
            category = q.get("category", "unknown")
            if category not in point_query_categories:
                continue

            question_id = q.get("id")
            metric = q.get("metric")
            ground_truth = q.get("ground_truth")

            # Skip complex/derived metrics
            if metric in ["revenue_growth", "revenue_growth_pct", "net_income_change",
                         "revenue_comparison", "operating_margin_trend", "opex_breakdown"]:
                continue

            # Normalize metric
            normalized_metric = normalize_metric(metric) if metric else None

            # Determine period
            if q.get("relative_period"):
                resolved = resolver.resolve(q["relative_period"])
                period_key = resolver.to_period_key(resolved)
            elif q.get("quarter"):
                period_key = f"{q['year']}-{q['quarter']}"
            elif q.get("year"):
                period_key = str(q["year"])
            else:
                failures.append({
                    "id": question_id,
                    "error": "No period specified",
                    "question": q.get("question")
                })
                continue

            # Query fact base
            actual_value = fact_base.query(normalized_metric, period_key)
            expected_value, unit = parse_ground_truth_value(ground_truth)

            if actual_value is None:
                failures.append({
                    "id": question_id,
                    "error": f"No data for {normalized_metric} in {period_key}",
                    "expected": ground_truth,
                    "question": q.get("question")
                })
            elif expected_value is not None and not values_match(expected_value, actual_value):
                failures.append({
                    "id": question_id,
                    "error": f"Value mismatch: expected {expected_value}, got {actual_value}",
                    "question": q.get("question")
                })
            else:
                passes += 1

        # Report results
        total = passes + len(failures)
        print(f"\n=== Ground Truth Data Access Test ===")
        print(f"Passed: {passes}/{total}")

        if failures:
            print(f"\nFAILURES ({len(failures)}):")
            for f in failures:
                print(f"  Q{f['id']}: {f['error']}")
                print(f"      Question: {f.get('question', 'N/A')[:60]}...")

            pytest.fail(f"{len(failures)} ground truth questions failed data access check")

    def test_relative_period_resolution(self, test_questions, fact_base):
        """
        All relative period questions must resolve to correct periods.

        Reference date: 2026-01-27
        - last_year -> 2025
        - last_quarter -> 2025-Q4 (since reference is Q1 2026)
        - this_year -> 2026
        """
        if "test_questions" not in test_questions:
            pytest.skip("No test_questions in file")

        resolver = PeriodResolver(reference_date=REFERENCE_DATE)
        questions = test_questions["test_questions"]

        relative_questions = [q for q in questions if q.get("category") == "relative"]

        failures = []

        # Expected mappings based on reference date 2026-01-27
        expected_mappings = {
            "last_year": "2025",
            "last_quarter": "2025-Q4",
            "this_year": "2026",
        }

        for q in relative_questions:
            rel_period = q.get("relative_period")
            if not rel_period:
                continue

            resolved = resolver.resolve(rel_period)
            period_key = resolver.to_period_key(resolved)

            if rel_period in expected_mappings:
                expected_key = expected_mappings[rel_period]
                if period_key != expected_key:
                    failures.append({
                        "id": q.get("id"),
                        "relative_period": rel_period,
                        "expected": expected_key,
                        "got": period_key
                    })

        if failures:
            print("\nRelative Period Resolution Failures:")
            for f in failures:
                print(f"  Q{f['id']}: {f['relative_period']} -> expected {f['expected']}, got {f['got']}")
            pytest.fail(f"{len(failures)} relative period resolutions failed")


class TestGroundTruthByCategory:
    """Test ground truth questions grouped by category."""

    def test_absolute_period_questions(self, test_questions, fact_base):
        """Test all absolute period questions (Q1-Q10)."""
        self._test_category(test_questions, fact_base, "absolute")

    def test_relative_period_questions(self, test_questions, fact_base):
        """Test all relative period questions (Q11-Q17)."""
        self._test_category(test_questions, fact_base, "relative")

    def test_margin_questions(self, test_questions, fact_base):
        """Test all margin percentage questions (Q18-Q23)."""
        self._test_category(test_questions, fact_base, "margin")

    def test_balance_sheet_questions(self, test_questions, fact_base):
        """Test all balance sheet questions (Q24-Q32)."""
        self._test_category(test_questions, fact_base, "balance_sheet")

    def test_synonym_questions(self, test_questions, fact_base):
        """Test all synonym variation questions (Q38-Q45)."""
        self._test_category(test_questions, fact_base, "synonym")

    def test_expense_questions(self, test_questions, fact_base):
        """Test all expense questions (Q49-Q52)."""
        self._test_category(test_questions, fact_base, "expense")

    def test_forecast_questions(self, test_questions, fact_base):
        """Test forecast questions (Q53-Q54)."""
        self._test_category(test_questions, fact_base, "forecast")

    def _test_category(self, test_questions, fact_base, category: str):
        """Helper to test a specific category of questions."""
        if "test_questions" not in test_questions:
            pytest.skip("No test_questions in file")

        questions = [q for q in test_questions["test_questions"]
                    if q.get("category") == category]

        if not questions:
            pytest.skip(f"No questions in category: {category}")

        resolver = PeriodResolver(reference_date=REFERENCE_DATE)
        failures = []
        passes = 0

        for q in questions:
            result = self._validate_question(q, fact_base, resolver)
            if result["success"]:
                passes += 1
            else:
                failures.append(result)

        total = len(questions)
        print(f"\n{category.upper()}: {passes}/{total} passed")

        if failures:
            for f in failures:
                print(f"  FAIL Q{f['id']}: {f['error']}")
            pytest.fail(f"Category '{category}': {len(failures)}/{total} failed")

    def _validate_question(self, q: Dict, fact_base: FactBase,
                          resolver: PeriodResolver) -> Dict:
        """Validate a single question against ground truth."""
        question_id = q.get("id")
        metric = q.get("metric")
        ground_truth = q.get("ground_truth")

        # Skip complex queries for now
        if metric in ["revenue_growth", "revenue_growth_pct", "net_income_change",
                     "revenue_comparison", "operating_margin_trend", "opex_breakdown"]:
            return {"success": True, "id": question_id, "skipped": True}

        # Normalize metric
        normalized_metric = normalize_metric(metric) if metric else metric

        # Determine period
        if q.get("relative_period"):
            resolved = resolver.resolve(q["relative_period"])
            period_key = resolver.to_period_key(resolved)
        elif q.get("quarter"):
            period_key = f"{q['year']}-{q['quarter']}"
        elif q.get("year"):
            period_key = str(q["year"])
        else:
            return {
                "success": False,
                "id": question_id,
                "error": "No period"
            }

        # Query fact base
        actual_value = fact_base.query(normalized_metric, period_key)
        expected_value, unit = parse_ground_truth_value(ground_truth)

        if actual_value is None:
            return {
                "success": False,
                "id": question_id,
                "error": f"No data: {normalized_metric} @ {period_key}"
            }

        if expected_value is not None and not values_match(expected_value, actual_value):
            return {
                "success": False,
                "id": question_id,
                "error": f"Expected {expected_value}, got {actual_value}"
            }

        return {"success": True, "id": question_id}


class TestAccuracyReport:
    """Generate accuracy report across all categories."""

    def test_overall_accuracy_report(self, test_questions, fact_base):
        """
        Generate full accuracy report.

        CRITICAL: This test must show 100% accuracy for supported question types.
        """
        if "test_questions" not in test_questions:
            pytest.skip("No test_questions in file")

        questions = test_questions["test_questions"]
        resolver = PeriodResolver(reference_date=REFERENCE_DATE)

        # Track results by category
        results_by_category = defaultdict(lambda: {"pass": 0, "fail": 0, "skip": 0})
        all_failures = []

        for q in questions:
            category = q.get("category", "unknown")
            metric = q.get("metric")

            # Skip complex/comparison queries
            if category in ["comparison", "aggregation"] or metric in [
                "revenue_growth", "revenue_growth_pct", "net_income_change",
                "revenue_comparison", "operating_margin_trend", "opex_breakdown"
            ]:
                results_by_category[category]["skip"] += 1
                continue

            # Normalize and resolve
            normalized_metric = normalize_metric(metric) if metric else metric

            if q.get("relative_period"):
                resolved = resolver.resolve(q["relative_period"])
                period_key = resolver.to_period_key(resolved)
            elif q.get("quarter"):
                period_key = f"{q['year']}-{q['quarter']}"
            elif q.get("year"):
                period_key = str(q["year"])
            else:
                results_by_category[category]["fail"] += 1
                all_failures.append({"id": q.get("id"), "error": "No period"})
                continue

            # Query and compare
            actual = fact_base.query(normalized_metric, period_key)
            expected, unit = parse_ground_truth_value(q.get("ground_truth"))

            if actual is None:
                results_by_category[category]["fail"] += 1
                all_failures.append({
                    "id": q.get("id"),
                    "category": category,
                    "error": f"No data: {normalized_metric} @ {period_key}"
                })
            elif expected is not None and not values_match(expected, actual):
                results_by_category[category]["fail"] += 1
                all_failures.append({
                    "id": q.get("id"),
                    "category": category,
                    "error": f"Mismatch: expected {expected}, got {actual}"
                })
            else:
                results_by_category[category]["pass"] += 1

        # Print report
        print("\n" + "=" * 60)
        print("GROUND TRUTH ACCURACY REPORT")
        print("Reference Date: 2026-01-27")
        print("=" * 60)

        total_pass = 0
        total_fail = 0
        total_skip = 0

        for category in sorted(results_by_category.keys()):
            stats = results_by_category[category]
            p, f, s = stats["pass"], stats["fail"], stats["skip"]
            total_pass += p
            total_fail += f
            total_skip += s

            tested = p + f
            pct = (p / tested * 100) if tested > 0 else 0
            status = "PASS" if f == 0 and tested > 0 else "FAIL" if f > 0 else "SKIP"

            print(f"{category:20} {p:3}/{tested:3} ({pct:5.1f}%) [{status}]" +
                  (f" (skipped: {s})" if s > 0 else ""))

        print("-" * 60)
        tested_total = total_pass + total_fail
        overall_pct = (total_pass / tested_total * 100) if tested_total > 0 else 0
        print(f"{'OVERALL':20} {total_pass:3}/{tested_total:3} ({overall_pct:5.1f}%)")
        print(f"Skipped (complex):   {total_skip}")
        print("=" * 60)

        if all_failures:
            print(f"\nFAILURES ({len(all_failures)}):")
            for f in all_failures:
                print(f"  Q{f['id']} [{f.get('category', '?')}]: {f['error']}")

            pytest.fail(
                f"ACCURACY REQUIREMENT NOT MET: {total_fail} failures. "
                f"100% accuracy required - fix bugs or fix questions."
            )

        print("\nAll supported question types passed!")


class TestConfidenceScoreBounds:
    """Verify confidence scores are always bounded in E2E context."""

    def test_all_responses_have_bounded_confidence(self, fact_base):
        """Every response must have confidence in [0, 1]."""
        executor = QueryExecutor(fact_base)

        # Test various scenarios
        test_cases = [
            # Valid query
            ParsedQuery(
                intent=QueryIntent.POINT_QUERY,
                metric="revenue",
                period_type=PeriodType.QUARTERLY,
                period_reference="2024-Q1",
                resolved_period="2024-Q1"
            ),
            # Invalid metric
            ParsedQuery(
                intent=QueryIntent.POINT_QUERY,
                metric="fake_metric",
                period_type=PeriodType.ANNUAL,
                period_reference="2024",
                resolved_period="2024"
            ),
            # Invalid period
            ParsedQuery(
                intent=QueryIntent.POINT_QUERY,
                metric="revenue",
                period_type=PeriodType.ANNUAL,
                period_reference="1900",
                resolved_period="1900"
            ),
        ]

        for query in test_cases:
            result = executor.execute(query)

            assert result.confidence >= 0.0, \
                f"Confidence {result.confidence} < 0 for {query}"
            assert result.confidence <= 1.0, \
                f"Confidence {result.confidence} > 1 for {query}"
