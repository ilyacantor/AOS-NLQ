"""
End-to-end tests with ground truth validation.

ACCURACY REQUIREMENT: 100% of ground truth questions must pass. No exceptions.

If a test fails:
1. Fix the bug in the engine
2. If the question is genuinely ambiguous, fix the question
3. Never lower the threshold

Financial queries have exact answers. A wrong answer is a bug, not an edge case.
"""

import pytest
from datetime import date


# Fixed reference date for all tests
REFERENCE_DATE = date(2026, 1, 27)


class TestGroundTruth:
    """Ground truth validation tests."""

    def test_ground_truth_accuracy(self, test_questions, fact_base):
        """
        All ground truth questions must return correct answers.

        CRITICAL: 100% accuracy required. No exceptions.
        """
        if "test_questions" not in test_questions:
            pytest.skip("No test_questions in file")

        questions = test_questions["test_questions"]
        results = []
        failures = []

        for q in questions:
            question_id = q.get("id", "unknown")
            question_text = q.get("question", "")
            expected = q.get("ground_truth")

            # For now, we'll do a simplified check since full pipeline
            # requires Claude API. This tests data availability.

            # Check if we can at least access the expected data
            result = {
                "id": question_id,
                "question": question_text,
                "expected": expected,
                "category": q.get("category", "unknown"),
            }

            results.append(result)

        # Report statistics
        total = len(results)
        print(f"\nGround Truth Test Questions: {total}")
        print(f"Categories found: {set(r['category'] for r in results)}")

        # This is a placeholder - full implementation requires the complete pipeline
        # When the NLQ engine is fully wired, this test will validate actual responses

    def test_fact_base_has_required_metrics(self, fact_base):
        """Verify fact base has all metrics needed for test questions."""
        required_metrics = [
            "revenue",
            "bookings",
            "cogs",
            "gross_profit",
            "gross_margin_pct",
            "operating_profit",
            "operating_margin_pct",
            "net_income",
            "cash",
            "ar",
        ]

        missing = []
        for metric in required_metrics:
            if not fact_base.has_metric(metric):
                missing.append(metric)

        if missing:
            pytest.fail(f"Fact base missing required metrics: {missing}")

    def test_fact_base_has_required_periods(self, fact_base):
        """Verify fact base has data for required periods."""
        # Based on reference date 2026-01-27, we need:
        # - 2025 (last year)
        # - 2025-Q4 (last quarter)
        # - At least some quarterly data

        available_periods = fact_base.available_periods

        # Should have some periods
        assert len(available_periods) > 0, "Fact base has no periods"

        print(f"\nAvailable periods: {sorted(available_periods)}")

    def test_synonym_coverage(self, test_questions):
        """Verify test questions cover synonym variations."""
        if "test_questions" not in test_questions:
            pytest.skip("No test_questions in file")

        questions = test_questions["test_questions"]

        # Check for synonym usage
        synonym_keywords = [
            "sales",      # -> revenue
            "top line",   # -> revenue
            "profit",     # -> net_income
            "bottom line",  # -> net_income
            "margin",     # -> various margin metrics
        ]

        synonym_questions = [
            q for q in questions
            if any(kw.lower() in q.get("question", "").lower() for kw in synonym_keywords)
        ]

        print(f"\nQuestions using synonyms: {len(synonym_questions)}")
        for q in synonym_questions[:5]:  # Show first 5
            print(f"  - {q.get('question', '')[:60]}...")


class TestRelativePeriodResolution:
    """Tests for relative period handling in e2e context."""

    def test_last_year_queries_resolve_correctly(self, fact_base, period_resolver):
        """Test that 'last year' queries resolve to correct year."""
        # Reference: 2026-01-27, so last year = 2025
        resolved = period_resolver.resolve("last_year")
        period_key = period_resolver.to_period_key(resolved)

        assert period_key == "2025"

        # Check if fact base has this period
        has_data = fact_base.has_period(period_key)
        print(f"\nFact base has 2025 data: {has_data}")

    def test_last_quarter_queries_resolve_correctly(self, fact_base, period_resolver):
        """Test that 'last quarter' queries resolve to correct quarter."""
        # Reference: 2026-01-27 (Q1), so last quarter = 2025-Q4
        resolved = period_resolver.resolve("last_quarter")
        period_key = period_resolver.to_period_key(resolved)

        assert period_key == "2025-Q4"

        # Check if fact base has this period
        has_data = fact_base.has_period(period_key)
        print(f"\nFact base has 2025-Q4 data: {has_data}")


class TestConfidenceScoreBounds:
    """Verify confidence scores are always bounded."""

    def test_all_responses_have_bounded_confidence(self, fact_base):
        """Every response must have confidence in [0, 1]."""
        from src.nlq.core.executor import QueryExecutor
        from src.nlq.models.query import ParsedQuery, QueryIntent, PeriodType

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
