"""
Unit tests for query parsing.

Tests the QueryParser class which uses Claude to extract:
- Intent
- Metric
- Period type and reference
- Relative vs absolute periods
"""

import pytest
from unittest.mock import MagicMock

from src.nlq.core.parser import QueryParser
from src.nlq.models.query import QueryIntent, PeriodType


class TestQueryParser:
    """Tests for QueryParser."""

    def test_parse_point_query(self, mock_claude_client, mock_claude_response):
        """Test parsing a simple point query."""
        mock_claude_client.parse_query.return_value = mock_claude_response(
            intent="POINT_QUERY",
            metric="revenue",
            period_type="annual",
            period_reference="2024",
            is_relative=False
        )

        parser = QueryParser(mock_claude_client)
        result = parser.parse("What was revenue in 2024?")

        assert result.intent == QueryIntent.POINT_QUERY
        assert result.metric == "revenue"
        assert result.period_type == PeriodType.ANNUAL
        assert result.is_relative is False

    def test_parse_relative_period(self, mock_claude_client, mock_claude_response):
        """Test parsing a query with relative period."""
        mock_claude_client.parse_query.return_value = mock_claude_response(
            intent="POINT_QUERY",
            metric="revenue",
            period_type="annual",
            period_reference="last_year",
            is_relative=True
        )

        parser = QueryParser(mock_claude_client)
        result = parser.parse("What was revenue last year?")

        assert result.is_relative is True
        assert result.period_reference == "last_year"

    def test_parse_normalizes_synonyms(self, mock_claude_client, mock_claude_response):
        """Test that synonyms are normalized to canonical names."""
        mock_claude_client.parse_query.return_value = mock_claude_response(
            intent="POINT_QUERY",
            metric="sales",  # Synonym for revenue
            period_type="annual",
            period_reference="2024",
            is_relative=False
        )

        parser = QueryParser(mock_claude_client)
        result = parser.parse("What were sales in 2024?")

        # Should normalize "sales" to "revenue"
        assert result.metric == "revenue"

    def test_parse_quarterly_query(self, mock_claude_client, mock_claude_response):
        """Test parsing a quarterly query."""
        mock_claude_client.parse_query.return_value = mock_claude_response(
            intent="POINT_QUERY",
            metric="gross_margin_pct",
            period_type="quarterly",
            period_reference="Q4 2025",
            is_relative=False
        )

        parser = QueryParser(mock_claude_client)
        result = parser.parse("What was gross margin in Q4 2025?")

        assert result.period_type == PeriodType.QUARTERLY
        assert result.metric == "gross_margin_pct"

    def test_parse_comparison_query(self, mock_claude_client, mock_claude_response):
        """Test parsing a comparison query."""
        mock_claude_client.parse_query.return_value = mock_claude_response(
            intent="COMPARISON_QUERY",
            metric="revenue",
            period_type="annual",
            period_reference="2024",
            is_relative=False
        )

        parser = QueryParser(mock_claude_client)
        result = parser.parse("How did revenue change from 2023 to 2024?")

        assert result.intent == QueryIntent.COMPARISON_QUERY
