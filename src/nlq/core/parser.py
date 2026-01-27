"""
Query parsing and intent extraction for AOS-NLQ.

Uses Claude API to parse natural language queries and extract:
- Intent (POINT_QUERY, COMPARISON_QUERY, TREND_QUERY, etc.)
- Metric being queried
- Period type and reference
- Whether the period is relative

The parser normalizes metrics using the synonym system.
"""

import json
import logging
from typing import Optional

from src.nlq.knowledge.synonyms import normalize_metric, normalize_period
from src.nlq.llm.client import ClaudeClient
from src.nlq.models.query import ParsedQuery, QueryIntent, PeriodType

logger = logging.getLogger(__name__)


class QueryParser:
    """Parses natural language queries into structured representations."""

    def __init__(self, claude_client: ClaudeClient):
        """
        Initialize the query parser.

        Args:
            claude_client: Claude API client for LLM-based parsing
        """
        self.claude_client = claude_client

    def parse(self, question: str) -> ParsedQuery:
        """
        Parse a natural language question into a structured query.

        Args:
            question: Natural language question about financial data

        Returns:
            ParsedQuery with extracted intent, metric, and period information

        Raises:
            ValueError: If the question cannot be parsed
        """
        # Use Claude to extract query components
        raw_parse = self.claude_client.parse_query(question)

        # Normalize the metric using synonym system
        raw_metric = raw_parse.get("metric", "")
        normalized_metric = normalize_metric(raw_metric)

        # Normalize period reference
        raw_period = raw_parse.get("period_reference", "")
        normalized_period = normalize_period(raw_period)

        # Normalize comparison period if present
        raw_comparison = raw_parse.get("comparison_period")
        normalized_comparison = normalize_period(raw_comparison) if raw_comparison else None

        # Normalize aggregation periods if present
        raw_agg_periods = raw_parse.get("aggregation_periods", [])
        normalized_agg_periods = [normalize_period(p) for p in raw_agg_periods] if raw_agg_periods else None

        # Normalize breakdown metrics if present
        raw_breakdown = raw_parse.get("breakdown_metrics", [])
        normalized_breakdown = [normalize_metric(m) for m in raw_breakdown] if raw_breakdown else None

        # Map string intent to enum
        intent_str = raw_parse.get("intent", "POINT_QUERY")
        try:
            intent = QueryIntent(intent_str)
        except ValueError:
            intent = QueryIntent.POINT_QUERY

        # Map period type to enum
        period_type_str = raw_parse.get("period_type", "annual")
        try:
            period_type = PeriodType(period_type_str)
        except ValueError:
            period_type = PeriodType.ANNUAL

        return ParsedQuery(
            intent=intent,
            metric=normalized_metric,
            period_type=period_type,
            period_reference=normalized_period,
            is_relative=raw_parse.get("is_relative", False),
            raw_metric=raw_metric,
            comparison_period=normalized_comparison,
            aggregation_type=raw_parse.get("aggregation_type"),
            aggregation_periods=normalized_agg_periods,
            breakdown_metrics=normalized_breakdown,
        )

    def parse_without_llm(self, question: str) -> Optional[ParsedQuery]:
        """
        Attempt to parse a query using rule-based matching (no LLM call).

        This is useful for simple queries and testing without API costs.

        Args:
            question: Natural language question

        Returns:
            ParsedQuery if successfully parsed, None if LLM needed
        """
        # TODO: Implement rule-based parsing for common patterns
        # This would handle queries like "What was revenue in 2024?"
        # without needing to call the LLM
        return None
