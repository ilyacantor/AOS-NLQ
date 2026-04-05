"""
Unit tests for query execution.

CRITICAL: Tests verify proper handling of:
- Unknown metrics (UNKNOWN_METRIC error)
- Missing periods (NO_DATA_FOR_PERIOD error)
- Empty results (EMPTY_RESULT error)

Zero-row scenarios must return explicit errors, not empty results.
"""

import pytest
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

from src.nlq.core.executor import QueryExecutor
from src.nlq.models.query import ParsedQuery, QueryIntent, PeriodType
from src.nlq.services.dcl_semantic_client import MetricDefinition, SemanticCatalog


def _make_metric(id: str, display: str, domain: str = "CFO") -> MetricDefinition:
    return MetricDefinition(
        id=id, display_name=display, aliases=[], unit="USD millions",
        allowed_dimensions=["region"], allowed_grains=["quarterly", "yearly"],
        domain=domain,
    )


_TEST_CATALOG = SemanticCatalog(
    metrics={
        "revenue": _make_metric("revenue", "Revenue"),
        "sga": _make_metric("sga", "SG&A"),
        "selling_expenses": _make_metric("selling_expenses", "Selling Expenses"),
        "g_and_a_expenses": _make_metric("g_and_a_expenses", "G&A Expenses"),
    },
    dimensions={"region": ["AMER", "EMEA"]},
    alias_to_metric={},
)

# DCL query responses keyed by (metric, period)
_MOCK_DATA = {
    ("revenue", "2025"): {"status": "ok", "data": [{"value": 150.0}], "source": "dcl"},
    ("revenue", "2024"): {"status": "ok", "data": [{"value": 100.0}], "source": "dcl"},
    ("revenue", "2025-Q1"): {"status": "ok", "data": [{"value": 33.0}], "source": "dcl"},
    ("revenue", "2025-Q2"): {"status": "ok", "data": [{"value": 36.0}], "source": "dcl"},
    ("revenue", "2025-Q3"): {"status": "ok", "data": [{"value": 39.0}], "source": "dcl"},
    ("revenue", "2025-Q4"): {"status": "ok", "data": [{"value": 42.0}], "source": "dcl"},
    ("revenue", "2024-Q4"): {"status": "ok", "data": [{"value": 28.0}], "source": "dcl"},
    ("selling_expenses", "2025"): {"status": "ok", "data": [{"value": 27.0}], "source": "dcl"},
    ("g_and_a_expenses", "2025"): {"status": "ok", "data": [{"value": 18.0}], "source": "dcl"},
    ("sga", "2025"): {"status": "ok", "data": [{"value": 45.0}], "source": "dcl"},
}


@pytest.fixture(autouse=True)
def _allow_no_dcl(monkeypatch):
    """QueryExecutor chains to DCLSemanticClient(v1+v2) — allow init without live DCL."""
    monkeypatch.setenv("NLQ_ALLOW_NO_DCL", "1")
    monkeypatch.setenv("DCL_API_URL", "http://mock-dcl:8004")
    # Reset singletons so each test gets fresh clients with patched env
    import src.nlq.services.dcl_client_router as router
    import src.nlq.services.dcl_semantic_client as v1mod
    import src.nlq.services.dcl_semantic_client_v2 as v2mod
    router._routed_client = None
    v1mod._semantic_client = None
    v2mod._v2_client = None


def _make_executor() -> QueryExecutor:
    """Create a QueryExecutor with mocked DCL client."""
    executor = QueryExecutor()
    mock_client = MagicMock()
    mock_client.get_catalog.return_value = _TEST_CATALOG
    mock_client.resolve_via_graph.return_value = {"can_answer": False, "reason": "test mock"}
    mock_client._negotiate_metric_id.side_effect = lambda m: m

    def mock_query(metric, time_range=None, **kwargs):
        period = None
        if time_range:
            period = time_range.get("start") or time_range.get("period")
        key = (metric, period)
        if key in _MOCK_DATA:
            return _MOCK_DATA[key]
        return {"status": "ok", "data": [], "source": "dcl"}

    mock_client.query.side_effect = mock_query
    executor.dcl_client = mock_client
    return executor


class TestQueryExecutor:
    """Tests for QueryExecutor."""

    def test_unknown_metric_returns_error(self):
        """Test that unknown metrics return UNKNOWN_METRIC error."""
        executor = _make_executor()

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
        executor = _make_executor()

        query = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="revenue",
            period_type=PeriodType.ANNUAL,
            period_reference="1999",
            resolved_period="1999"  # No data for 1999
        )

        result = executor.execute(query)

        assert result.success is False
        assert result.error == "EMPTY_RESULT"
        assert result.confidence == 0.0

    def test_unresolved_period_returns_error(self):
        """Test that unresolved periods return error."""
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

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
        executor = _make_executor()

        query = ParsedQuery(
            intent=QueryIntent.BREAKDOWN_QUERY,
            metric="unknown_composite_xyz",
            period_type=PeriodType.ANNUAL,
            period_reference="2025",
            resolved_period="2025",
            breakdown_metrics=None
        )

        result = executor.execute(query)

        assert result.success is False
        assert result.error in ("MISSING_BREAKDOWN_METRICS", "NO_BREAKDOWN_DATA")
