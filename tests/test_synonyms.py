"""
Tests for synonym normalization.

Covers all metric and period variations to ensure consistent normalization.
"""

import pytest

from src.nlq.knowledge.synonyms import (
    METRIC_SYNONYMS,
    PERIOD_SYNONYMS,
    normalize_metric,
    normalize_period,
    get_all_metric_names,
    get_canonical_metrics,
)


class TestNormalizeMetric:
    """Tests for normalize_metric function."""

    # Revenue synonyms
    @pytest.mark.parametrize("synonym", [
        "revenue",
        "sales",
        "top line",
        "top-line",
        "topline",
        "turnover",
        "total revenue",
        "SALES",  # Case insensitive
        "Sales",
        "TOP LINE",
        " sales ",  # With whitespace
    ])
    def test_revenue_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "revenue"

    # Net income synonyms
    @pytest.mark.parametrize("synonym", [
        "net_income",
        "profit",
        "net profit",
        "bottom line",
        "bottom-line",
        "bottomline",
        "earnings",
        "net earnings",
        "income",
        "PROFIT",
        "Bottom Line",
    ])
    def test_net_income_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "net_income"

    # Operating profit synonyms
    @pytest.mark.parametrize("synonym", [
        "operating_profit",
        "operating income",
        "ebit",
        "EBIT",
        "op profit",
        "operating earnings",
        "income from operations",
    ])
    def test_operating_profit_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "operating_profit"

    # Gross profit synonyms
    @pytest.mark.parametrize("synonym", [
        "gross_profit",
        "gross income",
        "gross margin dollars",
        "gross profit dollars",
    ])
    def test_gross_profit_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "gross_profit"

    # COGS synonyms
    @pytest.mark.parametrize("synonym", [
        "cogs",
        "COGS",
        "cost of goods sold",
        "cost of sales",
        "cost of revenue",
        "cos",
        "COS",
        "direct costs",
        "product costs",
    ])
    def test_cogs_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "cogs"

    # SG&A synonyms
    @pytest.mark.parametrize("synonym", [
        "sga",
        "sg&a",
        "SG&A",
        "s g & a",
        "sg and a",
        "selling general and administrative",
        "operating expenses",
        "opex",
        "OPEX",
        "operating costs",
    ])
    def test_sga_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "sga"

    # Gross margin percentage synonyms
    @pytest.mark.parametrize("synonym", [
        "gross_margin_pct",
        "gross margin",
        "gross margin %",
        "gross margin percent",
        "gm%",
        "gm pct",
    ])
    def test_gross_margin_pct_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "gross_margin_pct"

    # Cash synonyms
    @pytest.mark.parametrize("synonym", [
        "cash",
        "cash balance",
        "cash on hand",
        "cash and equivalents",
        "cash & equivalents",
    ])
    def test_cash_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "cash"

    # AR synonyms
    @pytest.mark.parametrize("synonym", [
        "ar",
        "AR",
        "accounts receivable",
        "receivables",
        "trade receivables",
        "a/r",
    ])
    def test_ar_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "ar"

    # AP synonyms
    @pytest.mark.parametrize("synonym", [
        "ap",
        "AP",
        "accounts payable",
        "payables",
        "trade payables",
        "a/p",
    ])
    def test_ap_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "ap"

    # Unknown metric returns normalized version
    def test_unknown_metric_returns_lowercase_with_underscores(self):
        assert normalize_metric("Unknown Metric") == "unknown_metric"
        assert normalize_metric("some random thing") == "some_random_thing"

    # Empty/None handling
    def test_empty_string(self):
        assert normalize_metric("") == ""

    def test_none_returns_none(self):
        assert normalize_metric(None) is None

    # Bookings
    @pytest.mark.parametrize("synonym", [
        "bookings",
        "new bookings",
        "orders",
        "new orders",
    ])
    def test_bookings_synonyms(self, synonym: str):
        assert normalize_metric(synonym) == "bookings"


class TestNormalizePeriod:
    """Tests for normalize_period function."""

    # Last year synonyms
    @pytest.mark.parametrize("synonym", [
        "last_year",
        "last year",
        "prior year",
        "previous year",
        "year ago",
        "ly",
        "LY",
        "last fiscal year",
        "prior fiscal year",
        " prior year ",  # With whitespace
    ])
    def test_last_year_synonyms(self, synonym: str):
        assert normalize_period(synonym) == "last_year"

    # This year synonyms
    @pytest.mark.parametrize("synonym", [
        "this_year",
        "this year",
        "current year",
        "cy",
        "CY",
        "this fiscal year",
        "current fiscal year",
        "ytd",
    ])
    def test_this_year_synonyms(self, synonym: str):
        assert normalize_period(synonym) == "this_year"

    # Last quarter synonyms
    @pytest.mark.parametrize("synonym", [
        "last_quarter",
        "last quarter",
        "prior quarter",
        "previous quarter",
        "quarter ago",
        "lq",
        "LQ",
        "last q",
    ])
    def test_last_quarter_synonyms(self, synonym: str):
        assert normalize_period(synonym) == "last_quarter"

    # This quarter synonyms
    @pytest.mark.parametrize("synonym", [
        "this_quarter",
        "this quarter",
        "current quarter",
        "cq",
        "CQ",
        "this q",
    ])
    def test_this_quarter_synonyms(self, synonym: str):
        assert normalize_period(synonym) == "this_quarter"

    # Unknown period returns normalized version
    def test_unknown_period_returns_lowercase_with_underscores(self):
        assert normalize_period("Q4 2025") == "q4_2025"
        assert normalize_period("FY2024") == "fy2024"

    # Empty/None handling
    def test_empty_string(self):
        assert normalize_period("") == ""

    def test_none_returns_none(self):
        assert normalize_period(None) is None


class TestSynonymMaps:
    """Tests for synonym dictionary structure."""

    def test_all_canonical_metrics_have_synonyms(self):
        """Every canonical metric should have at least one synonym."""
        for canonical, synonyms in METRIC_SYNONYMS.items():
            assert len(synonyms) > 0, f"{canonical} has no synonyms"

    def test_all_canonical_periods_have_synonyms(self):
        """Every canonical period should have at least one synonym."""
        for canonical, synonyms in PERIOD_SYNONYMS.items():
            assert len(synonyms) > 0, f"{canonical} has no synonyms"

    def test_no_duplicate_synonyms_across_metrics(self):
        """No synonym should map to multiple canonical metrics."""
        seen = {}
        for canonical, synonyms in METRIC_SYNONYMS.items():
            for syn in synonyms:
                if syn in seen:
                    pytest.fail(
                        f"Synonym '{syn}' appears in both '{seen[syn]}' and '{canonical}'"
                    )
                seen[syn] = canonical

    def test_required_metrics_exist(self):
        """All required metrics from spec are defined."""
        required = [
            "revenue", "net_income", "operating_profit", "gross_profit",
            "cogs", "sga", "cash", "ar", "ap", "bookings"
        ]
        for metric in required:
            assert metric in METRIC_SYNONYMS, f"Missing required metric: {metric}"

    def test_required_periods_exist(self):
        """All required periods from spec are defined."""
        required = ["last_year", "this_year", "last_quarter", "this_quarter"]
        for period in required:
            assert period in PERIOD_SYNONYMS, f"Missing required period: {period}"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_all_metric_names_includes_synonyms(self):
        """get_all_metric_names returns both canonical and synonyms."""
        all_names = get_all_metric_names()
        assert "revenue" in all_names
        assert "sales" in all_names
        assert "top line" in all_names

    def test_get_canonical_metrics_only_returns_canonical(self):
        """get_canonical_metrics only returns canonical names."""
        canonical = get_canonical_metrics()
        assert "revenue" in canonical
        assert "sales" not in canonical  # Sales is a synonym
        assert "top line" not in canonical


class TestCaseSensitivity:
    """Ensure case-insensitive matching works properly."""

    def test_metric_case_variations(self):
        """Metrics should match regardless of case."""
        assert normalize_metric("REVENUE") == "revenue"
        assert normalize_metric("Revenue") == "revenue"
        assert normalize_metric("rEvEnUe") == "revenue"
        assert normalize_metric("EBIT") == "operating_profit"
        assert normalize_metric("ebit") == "operating_profit"

    def test_period_case_variations(self):
        """Periods should match regardless of case."""
        assert normalize_period("LAST YEAR") == "last_year"
        assert normalize_period("Last Year") == "last_year"
        assert normalize_period("LY") == "last_year"
        assert normalize_period("ly") == "last_year"
