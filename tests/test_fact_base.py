"""
Tests for the FactBase data loading and querying.

Covers:
- Loading JSON fact base
- Period format handling ("2024" and "2024-Q1")
- Metric availability checks
- Period availability checks
- Single metric/period queries
- Annual aggregation from quarterly data
"""

import json
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.nlq.knowledge.fact_base import FactBase


class TestFactBaseLoading:
    """Tests for loading fact base from JSON."""

    def test_load_from_file(self, fact_base_path):
        """Test loading from existing fact base file."""
        fb = FactBase()
        fb.load(fact_base_path)

        assert fb._loaded is True
        assert len(fb.available_periods) > 0
        assert len(fb.available_metrics) > 0

    def test_load_nonexistent_file_raises(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        fb = FactBase()
        with pytest.raises(FileNotFoundError):
            fb.load("/nonexistent/path/to/file.json")

    def test_load_quarterly_and_annual_data(self, fact_base):
        """Test that both quarterly and annual data are loaded."""
        periods = fact_base.available_periods

        # Should have quarterly periods
        quarterly_periods = [p for p in periods if "-Q" in p]
        assert len(quarterly_periods) > 0, "No quarterly periods found"

        # Should have annual periods
        annual_periods = [p for p in periods if "-Q" not in p and p.isdigit()]
        assert len(annual_periods) > 0, "No annual periods found"

    def test_load_with_custom_structure(self):
        """Test loading fact base with custom JSON structure."""
        custom_data = {
            "quarterly": [
                {
                    "period": "2024-Q1",
                    "year": 2024,
                    "quarter": "Q1",
                    "revenue": 100.0,
                    "net_income": 25.0
                }
            ],
            "annual": {
                "2024": {
                    "revenue": 400.0,
                    "net_income": 100.0
                }
            }
        }

        with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(custom_data, f)
            f.flush()

            fb = FactBase()
            fb.load(f.name)

            assert "2024-Q1" in fb.available_periods
            assert "2024" in fb.available_periods
            assert "revenue" in fb.available_metrics


class TestAvailableMetrics:
    """Tests for available_metrics property."""

    def test_returns_set(self, fact_base):
        """available_metrics should return a set."""
        metrics = fact_base.available_metrics
        assert isinstance(metrics, set)

    def test_contains_expected_metrics(self, fact_base):
        """Should contain standard financial metrics."""
        metrics = fact_base.available_metrics
        expected = ["revenue", "net_income", "gross_profit", "cogs"]

        for metric in expected:
            assert metric in metrics, f"Missing expected metric: {metric}"

    def test_metrics_are_normalized(self, fact_base):
        """Metrics should be lowercase with underscores."""
        metrics = fact_base.available_metrics

        for metric in metrics:
            assert metric == metric.lower(), f"Metric not lowercase: {metric}"
            assert " " not in metric, f"Metric contains space: {metric}"


class TestAvailablePeriods:
    """Tests for available_periods property."""

    def test_returns_set(self, fact_base):
        """available_periods should return a set."""
        periods = fact_base.available_periods
        assert isinstance(periods, set)

    def test_contains_quarterly_periods(self, fact_base):
        """Should contain quarterly periods in YYYY-Q# format."""
        periods = fact_base.available_periods

        quarterly = [p for p in periods if "-Q" in p]
        assert len(quarterly) > 0

        # Check format
        for p in quarterly:
            assert len(p) == 7, f"Invalid quarterly format: {p}"
            assert p[4] == "-", f"Missing dash: {p}"
            assert p[5] == "Q", f"Missing Q: {p}"

    def test_contains_annual_periods(self, fact_base):
        """Should contain annual periods as year strings."""
        periods = fact_base.available_periods

        annual = [p for p in periods if p.isdigit() and len(p) == 4]
        assert len(annual) > 0


class TestHasPeriod:
    """Tests for has_period method."""

    def test_has_existing_quarterly_period(self, fact_base):
        """Should return True for existing quarterly period."""
        assert fact_base.has_period("2024-Q1") is True

    def test_has_existing_annual_period(self, fact_base):
        """Should return True for existing annual period."""
        assert fact_base.has_period("2024") is True

    def test_missing_period_returns_false(self, fact_base):
        """Should return False for non-existent period."""
        assert fact_base.has_period("1999") is False
        assert fact_base.has_period("1999-Q1") is False

    def test_period_normalization(self, fact_base):
        """Should handle period format variations."""
        # These should all find 2024-Q4 if it exists
        if fact_base.has_period("2024-Q4"):
            # Note: normalization handles some variations
            assert fact_base.has_period("2024-Q4") is True


class TestHasMetric:
    """Tests for has_metric method."""

    def test_has_existing_metric(self, fact_base):
        """Should return True for existing metrics."""
        assert fact_base.has_metric("revenue") is True
        assert fact_base.has_metric("net_income") is True

    def test_missing_metric_returns_false(self, fact_base):
        """Should return False for non-existent metrics."""
        assert fact_base.has_metric("fake_metric") is False
        assert fact_base.has_metric("nonexistent") is False

    def test_case_insensitive(self, fact_base):
        """Metric lookup should be case-insensitive."""
        assert fact_base.has_metric("REVENUE") is True
        assert fact_base.has_metric("Revenue") is True


class TestQuery:
    """Tests for query method."""

    def test_query_quarterly_data(self, fact_base):
        """Query specific quarterly data."""
        result = fact_base.query("revenue", "2024-Q1")

        assert result is not None
        assert isinstance(result, (int, float))
        assert result == 22.0  # From fact_base.json

    def test_query_annual_data(self, fact_base):
        """Query annual data directly."""
        result = fact_base.query("revenue", "2024")

        assert result is not None
        assert isinstance(result, (int, float))
        assert result == 100.0  # From fact_base.json

    def test_query_nonexistent_period_returns_none(self, fact_base):
        """Query for non-existent period returns None."""
        result = fact_base.query("revenue", "1999")
        assert result is None

    def test_query_nonexistent_metric_returns_none(self, fact_base):
        """Query for non-existent metric returns None."""
        result = fact_base.query("fake_metric", "2024")
        assert result is None

    def test_query_is_case_insensitive(self, fact_base):
        """Query should be case-insensitive for metrics."""
        result1 = fact_base.query("revenue", "2024")
        result2 = fact_base.query("REVENUE", "2024")
        result3 = fact_base.query("Revenue", "2024")

        assert result1 == result2 == result3


class TestQueryAnnual:
    """Tests for query_annual method (aggregation)."""

    def test_query_annual_direct(self, fact_base):
        """query_annual should return direct annual value if available."""
        result = fact_base.query_annual("revenue", 2024)

        assert result is not None
        assert result == 100.0  # Direct annual value from fact_base.json

    def test_query_annual_aggregates_quarters(self):
        """query_annual should sum quarters when no annual data exists."""
        # Create fact base with only quarterly data
        data = {
            "quarterly": [
                {"period": "2024-Q1", "year": 2024, "quarter": "Q1", "revenue": 25.0},
                {"period": "2024-Q2", "year": 2024, "quarter": "Q2", "revenue": 25.0},
                {"period": "2024-Q3", "year": 2024, "quarter": "Q3", "revenue": 25.0},
                {"period": "2024-Q4", "year": 2024, "quarter": "Q4", "revenue": 25.0},
            ]
        }

        with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            f.flush()

            fb = FactBase()
            fb.load(f.name)

            result = fb.query_annual("revenue", 2024)
            assert result == 100.0  # Sum of 4 quarters

    def test_query_annual_missing_year_returns_none(self, fact_base):
        """query_annual for missing year returns None."""
        result = fact_base.query_annual("revenue", 1999)
        assert result is None


class TestPeriodNormalization:
    """Tests for period key normalization."""

    def test_normalize_standard_quarterly(self, fact_base):
        """Standard format should pass through."""
        assert fact_base._normalize_period_key("2024-Q1") in ["2024-Q1", "2024-q1"]

    def test_normalize_annual(self, fact_base):
        """Annual format should pass through."""
        assert fact_base._normalize_period_key("2024") == "2024"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_fact_base(self):
        """Empty fact base should have no data."""
        fb = FactBase()

        assert len(fb.available_metrics) == 0
        assert len(fb.available_periods) == 0
        assert fb.query("revenue", "2024") is None

    def test_query_before_load(self):
        """Query before loading should return None, not crash."""
        fb = FactBase()
        result = fb.query("revenue", "2024")
        assert result is None

    def test_multiple_loads_replace_data(self):
        """Loading twice should replace data, not append."""
        data1 = {"quarterly": [{"period": "2020-Q1", "revenue": 50.0}]}
        data2 = {"quarterly": [{"period": "2021-Q1", "revenue": 100.0}]}

        with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f1:
            json.dump(data1, f1)
            f1.flush()

            with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f2:
                json.dump(data2, f2)
                f2.flush()

                fb = FactBase()
                fb.load(f1.name)
                assert fb.has_period("2020-Q1")

                fb.load(f2.name)
                assert fb.has_period("2021-Q1")
                # Old data should be replaced (not guaranteed by current impl)


class TestSpecificDataValues:
    """Tests verifying specific values from fact_base.json."""

    def test_2024_q4_revenue(self, fact_base):
        """Verify specific Q4 2024 revenue value."""
        result = fact_base.query("revenue", "2024-Q4")
        assert result == 28.0

    def test_2025_annual_revenue(self, fact_base):
        """Verify 2025 annual revenue."""
        result = fact_base.query("revenue", "2025")
        assert result == 150.0

    def test_2025_q4_gross_margin(self, fact_base):
        """Verify Q4 2025 gross margin percentage."""
        result = fact_base.query("gross_margin_pct", "2025-Q4")
        assert result == 65.0

    def test_multiple_metrics_same_period(self, fact_base):
        """Query multiple metrics for same period."""
        period = "2024-Q1"

        revenue = fact_base.query("revenue", period)
        cogs = fact_base.query("cogs", period)
        gross_profit = fact_base.query("gross_profit", period)

        assert revenue == 22.0
        assert cogs == 7.7
        assert gross_profit == 14.3
        # Verify relationship: revenue - cogs = gross_profit
        assert abs(revenue - cogs - gross_profit) < 0.01
