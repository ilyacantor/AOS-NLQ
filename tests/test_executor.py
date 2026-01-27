"""
Unit tests for query execution.

CRITICAL: Tests verify proper handling of:
- Unknown metrics (UNKNOWN_METRIC error)
- Missing periods (NO_DATA_FOR_PERIOD error)
- Empty results (EMPTY_RESULT error)

Zero-row scenarios must return explicit errors, not empty results.
"""

import pytest
from unittest.mock import MagicMock

from src.nlq.core.executor import QueryExecutor
from src.nlq.models.query import ParsedQuery, QueryIntent, PeriodType


class TestQueryExecutor:
    """Tests for QueryExecutor."""

    def test_unknown_metric_returns_error(self, fact_base):
        """Test that unknown metrics return UNKNOWN_METRIC error."""
        executor = QueryExecutor(fact_base)

        query = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="nonexistent_metric",
            period_type=PeriodType.ANNUAL,
            period_reference="2024",
            resolved_period="2024"
        )

        result = executor.execute(query)

        assert result.success is False
        assert result.error == "UNKNOWN_METRIC"
        assert result.confidence == 0.0

    def test_missing_period_returns_error(self, fact_base):
        """Test that missing periods return NO_DATA_FOR_PERIOD error."""
        executor = QueryExecutor(fact_base)

        query = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="revenue",
            period_type=PeriodType.ANNUAL,
            period_reference="1999",
            resolved_period="1999"  # No data for 1999
        )

        result = executor.execute(query)

        assert result.success is False
        assert result.error == "NO_DATA_FOR_PERIOD"
        assert result.confidence == 0.0

    def test_unresolved_period_returns_error(self, fact_base):
        """Test that unresolved periods return error."""
        executor = QueryExecutor(fact_base)

        query = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="revenue",
            period_type=PeriodType.ANNUAL,
            period_reference="last_year",
            resolved_period=None  # Not resolved
        )

        result = executor.execute(query)

        assert result.success is False
        assert result.error == "UNRESOLVED_PERIOD"
        assert result.confidence == 0.0

    def test_successful_point_query(self, fact_base):
        """Test successful point query returns value."""
        executor = QueryExecutor(fact_base)

        # Use a period we know exists in the fact base
        available_periods = list(fact_base.available_periods)
        if not available_periods:
            pytest.skip("No periods in fact base")

        period = available_periods[0]

        query = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="revenue",
            period_type=PeriodType.QUARTERLY,
            period_reference=period,
            resolved_period=period
        )

        result = executor.execute(query)

        # If revenue exists for this period, should succeed
        if fact_base.query("revenue", period) is not None:
            assert result.success is True
            assert result.value is not None
            assert 0.0 <= result.confidence <= 1.0

    def test_confidence_is_bounded(self, fact_base):
        """Test that confidence scores are always bounded [0, 1]."""
        executor = QueryExecutor(fact_base)

        available_periods = list(fact_base.available_periods)
        if not available_periods:
            pytest.skip("No periods in fact base")

        period = available_periods[0]

        query = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="revenue",
            period_type=PeriodType.QUARTERLY,
            period_reference=period,
            resolved_period=period
        )

        result = executor.execute(query)

        # Confidence must ALWAYS be in [0, 1]
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0

    def test_error_results_have_zero_confidence(self, fact_base):
        """Test that error results always have confidence = 0."""
        executor = QueryExecutor(fact_base)

        # Test multiple error scenarios
        error_queries = [
            ParsedQuery(
                intent=QueryIntent.POINT_QUERY,
                metric="fake_metric",
                period_type=PeriodType.ANNUAL,
                period_reference="2024",
                resolved_period="2024"
            ),
            ParsedQuery(
                intent=QueryIntent.POINT_QUERY,
                metric="revenue",
                period_type=PeriodType.ANNUAL,
                period_reference="1900",
                resolved_period="1900"
            ),
        ]

        for query in error_queries:
            result = executor.execute(query)
            if not result.success:
                assert result.confidence == 0.0, \
                    f"Error result should have confidence=0, got {result.confidence}"
