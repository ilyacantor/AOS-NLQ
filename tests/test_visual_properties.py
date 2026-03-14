"""
Tests for Galaxy visualization visual properties.

Tests verify:
- Ring assignment based on match_type
- Confidence bounds
- Data quality values
- Freshness indicators
- Semantic labels
"""

import pytest
from pathlib import Path

from src.nlq.core.node_generator import (
    calculate_overall_metrics,
    generate_nodes_for_ambiguous_query,
    generate_nodes_for_breakdown_query,
    generate_nodes_for_comparison_query,
    generate_nodes_for_point_query,
)
from src.nlq.core.semantic_labels import get_semantic_label
from src.nlq.knowledge.quality import get_data_quality, get_freshness, get_freshness_level
from src.nlq.models.response import AmbiguityType, Domain, MatchType

pytestmark = pytest.mark.skip(reason="fact_base removed — tests need rewrite for DCL")


class TestMatchTypeAssignment:
    """Test orbital ring assignment based on match_type."""

    def test_point_query_primary_is_exact(self, fact_base):
        """Primary node should be EXACT (inner ring)."""
        nodes = generate_nodes_for_point_query(
            "revenue", 150.0, "2025", fact_base
        )

        primary = nodes[0]
        assert primary.match_type == MatchType.EXACT

    def test_point_query_related_are_potential(self, fact_base):
        """Related nodes should be POTENTIAL (middle ring)."""
        nodes = generate_nodes_for_point_query(
            "revenue", 150.0, "2025", fact_base
        )

        # Skip first (primary) node
        related_nodes = [n for n in nodes if "related" in n.id]
        for node in related_nodes:
            assert node.match_type == MatchType.POTENTIAL

    def test_point_query_context_are_hypothesis(self, fact_base):
        """Context nodes should be HYPOTHESIS (outer ring)."""
        nodes = generate_nodes_for_point_query(
            "revenue", 150.0, "2025", fact_base
        )

        context_nodes = [n for n in nodes if "context" in n.id]
        for node in context_nodes:
            assert node.match_type == MatchType.HYPOTHESIS

    def test_ambiguous_vague_metric_all_potential(self, fact_base):
        """Vague metric queries should have all candidates as POTENTIAL."""
        nodes = generate_nodes_for_ambiguous_query(
            AmbiguityType.VAGUE_METRIC,
            ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
            "2025",
            fact_base,
        )

        candidate_nodes = [n for n in nodes if "candidate" in n.id]
        for node in candidate_nodes:
            assert node.match_type == MatchType.POTENTIAL

    def test_ambiguous_broad_request_all_exact(self, fact_base):
        """Broad request queries should have all metrics as EXACT."""
        nodes = generate_nodes_for_ambiguous_query(
            AmbiguityType.BROAD_REQUEST,
            ["revenue", "gross_profit", "operating_profit", "net_income"],
            "2025",
            fact_base,
        )

        for node in nodes:
            assert node.match_type == MatchType.EXACT


class TestConfidenceBounds:
    """Test that confidence scores are always bounded [0, 1]."""

    def test_all_nodes_have_bounded_confidence(self, fact_base):
        """Every node must have confidence in [0, 1]."""
        # Test various node generation functions
        test_cases = [
            generate_nodes_for_point_query("revenue", 150.0, "2025", fact_base),
            generate_nodes_for_comparison_query(
                "revenue", "2025", 150.0, "2024", 100.0, 50.0, 50.0, fact_base
            ),
            generate_nodes_for_breakdown_query(
                {"selling_expenses": 27.0, "g_and_a_expenses": 18.0, "sga": 45.0},
                "2025",
                fact_base,
            ),
            generate_nodes_for_ambiguous_query(
                AmbiguityType.VAGUE_METRIC,
                ["gross_margin_pct", "operating_margin_pct"],
                "2025",
                fact_base,
            ),
        ]

        for nodes in test_cases:
            for node in nodes:
                assert 0.0 <= node.confidence <= 1.0, \
                    f"Confidence {node.confidence} out of bounds for {node.id}"

    def test_overall_confidence_bounded(self, fact_base):
        """Overall confidence calculation must be bounded."""
        nodes = generate_nodes_for_point_query("revenue", 150.0, "2025", fact_base)
        overall_conf, overall_quality = calculate_overall_metrics(nodes)

        assert 0.0 <= overall_conf <= 1.0
        assert 0.0 <= overall_quality <= 1.0


class TestDataQuality:
    """Test data quality values."""

    def test_all_nodes_have_bounded_data_quality(self, fact_base):
        """Every node must have data_quality in [0, 1]."""
        nodes = generate_nodes_for_point_query("revenue", 150.0, "2025", fact_base)

        for node in nodes:
            assert 0.0 <= node.data_quality <= 1.0, \
                f"Data quality {node.data_quality} out of bounds for {node.id}"

    def test_audited_metrics_have_high_quality(self):
        """Audited financial metrics should have high data quality."""
        audited_metrics = ["revenue", "net_income", "gross_profit", "cogs"]

        for metric in audited_metrics:
            quality = get_data_quality(metric)
            assert quality >= 0.90, f"{metric} should have high data quality"

    def test_forecast_metrics_have_lower_quality(self):
        """Forecast metrics should have lower data quality."""
        forecast_metrics = ["sales_pipeline", "expansion_revenue"]

        for metric in forecast_metrics:
            quality = get_data_quality(metric)
            assert quality <= 0.80, f"{metric} should have lower data quality"


class TestFreshness:
    """Test freshness indicators."""

    def test_all_nodes_have_freshness(self, fact_base):
        """Every node must have a freshness indicator."""
        nodes = generate_nodes_for_point_query("revenue", 150.0, "2025", fact_base)

        for node in nodes:
            assert node.freshness is not None
            assert node.freshness != ""

    def test_realtime_fresh_within_24h(self):
        """Real-time metrics are fresh when ≤24h old."""
        assert get_freshness_level("2h", "cash") == "fresh"
        assert get_freshness_level("12h", "bookings") == "fresh"
        assert get_freshness_level("24h", "sales_pipeline") == "fresh"

    def test_realtime_stale_after_24h(self):
        """Real-time metrics are stale after 24h."""
        assert get_freshness_level("48h", "cash") == "stale"
        assert get_freshness_level("72h", "bookings") == "stale"

    def test_realtime_old_after_72h(self):
        """Real-time metrics are old after 72h."""
        assert get_freshness_level("96h", "cash") == "old"

    def test_weekly_fresh_within_7d(self):
        """Weekly metrics are fresh when ≤7 days old."""
        assert get_freshness_level("12h", "ar") == "fresh"
        assert get_freshness_level("168h", "ap") == "fresh"

    def test_weekly_stale_after_7d(self):
        """Weekly metrics are stale after 7 days."""
        assert get_freshness_level("200h", "ar") == "stale"
        assert get_freshness_level("336h", "deferred_revenue") == "stale"

    def test_weekly_old_after_14d(self):
        """Weekly metrics are old after 14 days."""
        assert get_freshness_level("400h", "ar") == "old"

    def test_periodic_always_fresh(self):
        """Monthly/quarterly metrics are always fresh regardless of age."""
        assert get_freshness_level("24h", "revenue") == "fresh"
        assert get_freshness_level("48h", "net_income") == "fresh"
        assert get_freshness_level("720h", "gross_profit") == "fresh"
        assert get_freshness_level("2000h", "ppe") == "fresh"

    def test_realtime_metrics_have_fresh_defaults(self):
        """Real-time metrics' default freshness values are within cadence."""
        freshness = get_freshness("cash")
        assert get_freshness_level(freshness, "cash") == "fresh"

        freshness = get_freshness("bookings")
        assert get_freshness_level(freshness, "bookings") == "fresh"


class TestSemanticLabels:
    """Test semantic label generation."""

    def test_exact_high_confidence_is_exact_match(self):
        """High confidence EXACT should be 'Exact Match'."""
        label = get_semantic_label(0.95, MatchType.EXACT)
        assert label == "Exact Match"

    def test_exact_medium_confidence_is_direct_answer(self):
        """Medium confidence EXACT should be 'Direct Answer'."""
        label = get_semantic_label(0.90, MatchType.EXACT)
        assert label == "Direct Answer"

    def test_potential_high_confidence_is_likely(self):
        """High confidence POTENTIAL should be 'Likely'."""
        label = get_semantic_label(0.80, MatchType.POTENTIAL)
        assert label == "Likely"

    def test_hypothesis_medium_confidence_is_related(self):
        """Medium confidence HYPOTHESIS should be 'Related'."""
        label = get_semantic_label(0.40, MatchType.HYPOTHESIS)
        assert label == "Related"

    def test_all_nodes_have_semantic_labels(self, fact_base):
        """Every node must have a semantic label."""
        nodes = generate_nodes_for_point_query("revenue", 150.0, "2025", fact_base)

        for node in nodes:
            assert node.semantic_label is not None
            assert node.semantic_label != ""


class TestDomainColors:
    """Test domain assignment for circle colors."""

    def test_finance_metrics_have_finance_domain(self, fact_base):
        """Finance metrics should have FINANCE domain."""
        nodes = generate_nodes_for_point_query("revenue", 150.0, "2025", fact_base)

        primary = nodes[0]
        assert primary.domain == Domain.FINANCE

    def test_growth_metrics_have_growth_domain(self, fact_base):
        """Growth metrics should have GROWTH domain."""
        nodes = generate_nodes_for_point_query("bookings", 120.0, "2025", fact_base)

        primary = nodes[0]
        assert primary.domain == Domain.GROWTH


class TestRingDistribution:
    """Test that nodes are properly distributed across rings."""

    def test_point_query_has_all_rings(self, fact_base):
        """Point query should have nodes in all three rings."""
        nodes = generate_nodes_for_point_query("revenue", 150.0, "2025", fact_base)

        inner = [n for n in nodes if n.match_type == MatchType.EXACT]
        middle = [n for n in nodes if n.match_type == MatchType.POTENTIAL]
        outer = [n for n in nodes if n.match_type == MatchType.HYPOTHESIS]

        assert len(inner) >= 1, "Should have at least 1 inner ring node"
        assert len(middle) >= 1, "Should have at least 1 middle ring node"
        assert len(outer) >= 1, "Should have at least 1 outer ring node"

    def test_ambiguous_query_no_exact_for_vague_metric(self, fact_base):
        """Ambiguous vague metric queries should have no EXACT nodes."""
        nodes = generate_nodes_for_ambiguous_query(
            AmbiguityType.VAGUE_METRIC,
            ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
            "2025",
            fact_base,
        )

        inner = [n for n in nodes if n.match_type == MatchType.EXACT]
        middle = [n for n in nodes if n.match_type == MatchType.POTENTIAL]

        assert len(inner) == 0, "Vague metric should have no EXACT nodes"
        assert len(middle) >= 3, "Should have candidates in middle ring"


class TestNodeValues:
    """Test that nodes have correct values."""

    def test_point_query_primary_has_correct_value(self, fact_base):
        """Primary node should have the queried value."""
        nodes = generate_nodes_for_point_query("revenue", 150.0, "2025", fact_base)

        primary = nodes[0]
        assert primary.value == 150.0
        assert primary.formatted_value == "$150.0M"

    def test_comparison_query_has_both_period_values(self, fact_base):
        """Comparison nodes should have values for both periods."""
        nodes = generate_nodes_for_comparison_query(
            "revenue", "2025", 150.0, "2024", 100.0, 50.0, 50.0, fact_base
        )

        period_2025 = next(n for n in nodes if "2025" in n.id and "change" not in n.id)
        period_2024 = next(n for n in nodes if "2024" in n.id)

        assert period_2025.value == 150.0
        assert period_2024.value == 100.0

    def test_breakdown_query_has_all_components(self, fact_base):
        """Breakdown nodes should have all component values."""
        breakdown = {"selling_expenses": 27.0, "g_and_a_expenses": 18.0, "sga": 45.0}
        nodes = generate_nodes_for_breakdown_query(breakdown, "2025", fact_base)

        # Check that all breakdown metrics are present
        breakdown_nodes = [n for n in nodes if "breakdown" in n.id]
        metrics_found = {n.metric for n in breakdown_nodes}

        assert "selling_expenses" in metrics_found
        assert "g_and_a_expenses" in metrics_found
        assert "sga" in metrics_found
