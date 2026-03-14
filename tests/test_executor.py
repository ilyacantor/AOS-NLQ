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

    def test_unknown_metric_returns_error(self):
        """Test that unknown metrics return UNKNOWN_METRIC error."""
        executor = QueryExecutor()

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

    def test_missing_period_returns_error(self):
        """Test that missing periods return NO_DATA_FOR_PERIOD error."""
        executor = QueryExecutor()

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

    def test_unresolved_period_returns_error(self):
        """Test that unresolved periods return error."""
        executor = QueryExecutor()

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

    def test_successful_point_query(self):
        """Test successful point query returns value."""
        pytest.skip("fact_base removed — test needs rewrite for DCL")

    def test_confidence_is_bounded(self):
        """Test that confidence scores are always bounded [0, 1]."""
        pytest.skip("fact_base removed — test needs rewrite for DCL")

    def test_error_results_have_zero_confidence(self):
        """Test that error results always have confidence = 0."""
        executor = QueryExecutor()

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


class TestComparisonQuery:
    """Tests for COMPARISON_QUERY intent."""

    def test_comparison_query_returns_both_values(self):
        """Test that comparison query returns values for both periods."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.COMPARISON_QUERY,
            metric="revenue",
            period_type=PeriodType.ANNUAL,
            period_reference="2025",
            resolved_period="2025",
            comparison_period="2024"
        )

        result = executor.execute(query)

        assert result.success is True
        assert isinstance(result.value, dict)
        assert "value1" in result.value
        assert "value2" in result.value
        assert "difference" in result.value
        assert "pct_change" in result.value

    def test_comparison_query_calculates_change(self):
        """Test that comparison calculates difference and percentage correctly."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.COMPARISON_QUERY,
            metric="revenue",
            period_type=PeriodType.ANNUAL,
            period_reference="2025",
            resolved_period="2025",
            comparison_period="2024"
        )

        result = executor.execute(query)

        assert result.success is True
        # 2025 revenue: 150, 2024 revenue: 100
        # difference: 50, pct_change: 50%
        assert result.value["value1"] == 150.0
        assert result.value["value2"] == 100.0
        assert result.value["difference"] == 50.0
        assert result.value["pct_change"] == 50.0

    def test_comparison_missing_comparison_period(self):
        """Test that missing comparison period returns error."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.COMPARISON_QUERY,
            metric="revenue",
            period_type=PeriodType.ANNUAL,
            period_reference="2025",
            resolved_period="2025",
            comparison_period=None
        )

        result = executor.execute(query)

        assert result.success is False
        assert result.error == "MISSING_COMPARISON_PERIOD"

    def test_quarterly_comparison(self):
        """Test comparison between quarterly periods."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.COMPARISON_QUERY,
            metric="revenue",
            period_type=PeriodType.QUARTERLY,
            period_reference="Q4 2025",
            resolved_period="2025-Q4",
            comparison_period="2024-Q4"
        )

        result = executor.execute(query)

        assert result.success is True
        # Q4 2025: 42.0, Q4 2024: 28.0
        assert result.value["value1"] == 42.0
        assert result.value["value2"] == 28.0


class TestAggregationQuery:
    """Tests for AGGREGATION_QUERY intent."""

    def test_sum_aggregation(self):
        """Test sum aggregation over multiple periods."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.AGGREGATION_QUERY,
            metric="revenue",
            period_type=PeriodType.QUARTERLY,
            period_reference="H1 2025",
            resolved_period="2025-Q1",
            aggregation_type="sum",
            aggregation_periods=["2025-Q1", "2025-Q2"]
        )

        result = executor.execute(query)

        assert result.success is True
        # Q1 2025: 33.0 + Q2 2025: 36.0 = 69.0
        assert result.value["result"] == 69.0
        assert result.value["aggregation_type"] == "sum"

    def test_average_aggregation(self):
        """Test average aggregation over quarterly periods."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.AGGREGATION_QUERY,
            metric="revenue",
            period_type=PeriodType.QUARTERLY,
            period_reference="2025",
            resolved_period="2025",
            aggregation_type="average",
            aggregation_periods=["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
        )

        result = executor.execute(query)

        assert result.success is True
        # (33 + 36 + 39 + 42) / 4 = 37.5
        assert result.value["result"] == 37.5
        assert result.value["aggregation_type"] == "average"

    def test_missing_aggregation_periods_error(self):
        """Test that missing aggregation periods returns error."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.AGGREGATION_QUERY,
            metric="revenue",
            period_type=PeriodType.QUARTERLY,
            period_reference="H1 2025",
            resolved_period="2025-Q1",
            aggregation_type="sum",
            aggregation_periods=None
        )

        result = executor.execute(query)

        assert result.success is False
        assert result.error == "MISSING_AGGREGATION_PERIODS"


class TestBreakdownQuery:
    """Tests for BREAKDOWN_QUERY intent."""

    def test_expense_breakdown(self):
        """Test expense breakdown returns multiple metrics."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.BREAKDOWN_QUERY,
            metric="sga",
            period_type=PeriodType.ANNUAL,
            period_reference="2025",
            resolved_period="2025",
            breakdown_metrics=["selling_expenses", "g_and_a_expenses", "sga"]
        )

        result = executor.execute(query)

        assert result.success is True
        assert "breakdown" in result.value
        breakdown = result.value["breakdown"]
        # 2025 annual values
        assert breakdown["selling_expenses"] == 27.0
        assert breakdown["g_and_a_expenses"] == 18.0
        assert breakdown["sga"] == 45.0

    def test_missing_breakdown_metrics_error(self):
        """Test that missing breakdown metrics returns error."""
        executor = QueryExecutor()

        query = ParsedQuery(
            intent=QueryIntent.BREAKDOWN_QUERY,
            metric="sga",
            period_type=PeriodType.ANNUAL,
            period_reference="2025",
            resolved_period="2025",
            breakdown_metrics=None
        )

        result = executor.execute(query)

        assert result.success is False
        assert result.error == "MISSING_BREAKDOWN_METRICS"
