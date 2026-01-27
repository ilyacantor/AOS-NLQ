"""
Tests for ambiguous query handling.

Tests the 20 ambiguous questions defined in the spec:
- Incomplete queries ("rev?", "q4 numbers")
- Casual language ("how'd we do")
- Vague metrics ("whats the margin")
- Yes/no questions ("are we profitable")
- Broad requests ("give me the P&L")
- And more...
"""

import pytest
from pathlib import Path

from src.nlq.core.ambiguity import (
    CLARIFICATION_PROMPTS,
    detect_ambiguity,
    needs_clarification,
)
from src.nlq.core.node_generator import generate_nodes_for_ambiguous_query
from src.nlq.knowledge.fact_base import FactBase
from src.nlq.models.response import AmbiguityType, MatchType


@pytest.fixture
def fact_base():
    """Load the fact base for testing."""
    fb = FactBase()
    fb.load(Path(__file__).parent.parent / "data" / "fact_base.json")
    return fb


class TestAmbiguityDetection:
    """Test ambiguity type detection."""

    def test_detect_incomplete_rev(self):
        """'rev?' should be detected as INCOMPLETE."""
        amb_type, candidates, _ = detect_ambiguity("rev?")
        assert amb_type == AmbiguityType.INCOMPLETE
        assert "revenue" in candidates

    def test_detect_casual_how_did_we_do(self):
        """'how'd we do last year' should be VAGUE_METRIC (wants key financials)."""
        amb_type, candidates, _ = detect_ambiguity("how'd we do last year")
        assert amb_type == AmbiguityType.VAGUE_METRIC
        assert len(candidates) > 0

    def test_detect_vague_metric_margin(self):
        """'whats the margin' should be VAGUE_METRIC."""
        amb_type, candidates, _ = detect_ambiguity("whats the margin")
        assert amb_type == AmbiguityType.VAGUE_METRIC
        # Should include all three margin types
        assert "gross_margin_pct" in candidates
        assert "operating_margin_pct" in candidates
        assert "net_income_pct" in candidates

    def test_detect_yes_no_profitable(self):
        """'are we profitable' should be YES_NO."""
        amb_type, candidates, _ = detect_ambiguity("are we profitable")
        assert amb_type == AmbiguityType.YES_NO
        assert "net_income" in candidates or "operating_profit" in candidates

    def test_detect_broad_request_pl(self):
        """'give me the P&L' should be BROAD_REQUEST."""
        amb_type, candidates, _ = detect_ambiguity("give me the p&l")
        assert amb_type == AmbiguityType.BROAD_REQUEST
        assert len(candidates) >= 4  # Should include multiple P&L metrics

    def test_detect_shorthand_cash_position(self):
        """'cash position' should be SHORTHAND."""
        amb_type, candidates, _ = detect_ambiguity("cash position")
        assert amb_type == AmbiguityType.SHORTHAND
        assert "cash" in candidates

    def test_detect_not_applicable_burn_rate(self):
        """'burn rate' should be NOT_APPLICABLE."""
        amb_type, candidates, _ = detect_ambiguity("burn rate?")
        assert amb_type == AmbiguityType.NOT_APPLICABLE
        assert "burn_rate" in candidates  # Candidates track the concept, not literal "not_applicable"

    def test_non_ambiguous_returns_none(self):
        """Clear questions should not be detected as ambiguous."""
        amb_type, candidates, _ = detect_ambiguity("What was revenue in 2025?")
        assert amb_type is None


class TestClarificationPrompts:
    """Test clarification prompt generation."""

    def test_vague_metric_needs_clarification(self):
        """Vague metric should need clarification."""
        assert needs_clarification(AmbiguityType.VAGUE_METRIC) is True

    def test_casual_language_no_clarification(self):
        """Casual language usually can be inferred."""
        assert needs_clarification(AmbiguityType.CASUAL_LANGUAGE) is False

    def test_broad_request_no_clarification(self):
        """Broad requests just provide everything."""
        assert needs_clarification(AmbiguityType.BROAD_REQUEST) is False

    def test_clarification_prompt_for_margin(self):
        """Vague metric should have margin clarification."""
        amb_type, _, clarification = detect_ambiguity("whats the margin")
        assert clarification is not None
        assert "margin" in clarification.lower() or "Gross" in clarification


class TestAmbiguousNodeGeneration:
    """Test node generation for ambiguous queries."""

    def test_vague_metric_candidates_in_middle_ring(self, fact_base):
        """Vague metric candidates should all be POTENTIAL."""
        nodes = generate_nodes_for_ambiguous_query(
            AmbiguityType.VAGUE_METRIC,
            ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
            "2025",
            fact_base,
        )

        candidate_nodes = [n for n in nodes if "candidate" in n.id]
        assert len(candidate_nodes) == 3

        for node in candidate_nodes:
            assert node.match_type == MatchType.POTENTIAL

    def test_vague_metric_equal_confidence(self, fact_base):
        """All vague metric candidates should have equal confidence."""
        nodes = generate_nodes_for_ambiguous_query(
            AmbiguityType.VAGUE_METRIC,
            ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
            "2025",
            fact_base,
        )

        candidate_nodes = [n for n in nodes if "candidate" in n.id]
        confidences = [n.confidence for n in candidate_nodes]

        # All should be equal
        assert len(set(confidences)) == 1

    def test_broad_request_all_exact(self, fact_base):
        """Broad request metrics should all be EXACT."""
        nodes = generate_nodes_for_ambiguous_query(
            AmbiguityType.BROAD_REQUEST,
            ["revenue", "cogs", "gross_profit", "sga", "operating_profit", "net_income"],
            "2025",
            fact_base,
        )

        for node in nodes:
            assert node.match_type == MatchType.EXACT

    def test_not_applicable_has_hypothesis(self, fact_base):
        """NOT_APPLICABLE should have hypothesis node."""
        nodes = generate_nodes_for_ambiguous_query(
            AmbiguityType.NOT_APPLICABLE,
            ["burn_rate", "net_income"],
            "2025",
            fact_base,
        )

        # First node should be the N/A hypothesis
        na_node = nodes[0]
        assert na_node.match_type == MatchType.HYPOTHESIS
        assert na_node.confidence < 0.5

    def test_context_nodes_added(self, fact_base):
        """Ambiguous queries should include context nodes."""
        nodes = generate_nodes_for_ambiguous_query(
            AmbiguityType.VAGUE_METRIC,
            ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
            "2025",
            fact_base,
        )

        context_nodes = [n for n in nodes if "context" in n.id]
        assert len(context_nodes) >= 1


class TestThe20AmbiguousQuestions:
    """Test handling of the 20 specific ambiguous questions from the spec."""

    @pytest.mark.parametrize("question,expected_type", [
        ("rev?", AmbiguityType.INCOMPLETE),
        ("how'd we do last year", AmbiguityType.VAGUE_METRIC),  # Ground truth: vague_metric
        ("whats the margin", AmbiguityType.VAGUE_METRIC),
        ("q4 numbers", AmbiguityType.INCOMPLETE),
        ("are we profitable", AmbiguityType.YES_NO),
        ("hows the top line looking", AmbiguityType.CASUAL_LANGUAGE),
        ("give me the p&l", AmbiguityType.BROAD_REQUEST),
        ("did we hit 150", AmbiguityType.IMPLIED_CONTEXT),
        ("costs too high?", AmbiguityType.JUDGMENT_CALL),
        ("cash position", AmbiguityType.SHORTHAND),
        ("year over year", AmbiguityType.CONTEXT_DEPENDENT),
        ("what about Q2", AmbiguityType.CONTEXT_DEPENDENT),
        ("burn rate?", AmbiguityType.NOT_APPLICABLE),
        ("opex breakdown pls", AmbiguityType.CASUAL_LANGUAGE),
        ("we growing?", AmbiguityType.YES_NO),
        ("2025 in a nutshell", AmbiguityType.SUMMARY),
        ("bookings vs revenue", AmbiguityType.COMPARISON),
        ("compare this year to last", AmbiguityType.COMPARISON),
    ])
    def test_ambiguous_question_detection(self, question, expected_type):
        """Test that specific ambiguous questions are detected correctly."""
        amb_type, candidates, _ = detect_ambiguity(question)
        assert amb_type == expected_type, f"'{question}' should be {expected_type}, got {amb_type}"

    def test_margin_question_has_three_candidates(self, fact_base):
        """'whats the margin' should have three margin candidates."""
        amb_type, candidates, _ = detect_ambiguity("whats the margin")

        nodes = generate_nodes_for_ambiguous_query(
            amb_type, candidates, "2025", fact_base
        )

        # Should have nodes for gross, operating, and net margin
        metrics = [n.metric for n in nodes if "candidate" in n.id]
        assert "gross_margin_pct" in metrics
        assert "operating_margin_pct" in metrics
        assert "net_income_pct" in metrics

    def test_pl_request_has_full_breakdown(self, fact_base):
        """'give me the P&L' should return full P&L metrics."""
        amb_type, candidates, _ = detect_ambiguity("give me the p&l")

        nodes = generate_nodes_for_ambiguous_query(
            amb_type, candidates, "2025", fact_base
        )

        # Should have revenue, costs, profits
        metrics = [n.metric for n in nodes]
        assert "revenue" in metrics
        assert any("profit" in m or "income" in m for m in metrics)
