"""
Query execution against the fact base for AOS-NLQ.

CRITICAL REQUIREMENTS:
1. Check metric exists BEFORE querying
2. Check period exists BEFORE querying
3. Verify non-empty results
4. Return explicit errors for zero-row scenarios

Never return empty results silently - always provide appropriate error codes.
"""

import logging
from typing import Optional

from src.nlq.core.confidence import ConfidenceCalculator, bounded_confidence
from src.nlq.knowledge.fact_base import FactBase
from src.nlq.models.query import ParsedQuery, QueryIntent
from src.nlq.models.response import QueryResult

logger = logging.getLogger(__name__)


class QueryExecutor:
    """Executes parsed queries against the fact base."""

    def __init__(self, fact_base: FactBase):
        """
        Initialize the query executor.

        Args:
            fact_base: The fact base to query against
        """
        self.fact_base = fact_base
        self.confidence_calculator = ConfidenceCalculator()

    def execute(self, parsed_query: ParsedQuery) -> QueryResult:
        """
        Execute a parsed query against the fact base.

        Args:
            parsed_query: Structured query from the parser

        Returns:
            QueryResult with value or error information

        CRITICAL: This method performs three validation checks before returning
        results to ensure we never return empty/invalid data silently.
        """
        # Check 1: Does the metric exist in our schema?
        available_metrics = self.fact_base.available_metrics
        if parsed_query.metric not in available_metrics:
            return QueryResult(
                success=False,
                error="UNKNOWN_METRIC",
                message=f"Metric '{parsed_query.metric}' not found. Available: {', '.join(sorted(available_metrics)[:10])}...",
                confidence=0.0
            )

        # Check 2: Does the period exist in our data?
        period_key = parsed_query.resolved_period
        if not period_key:
            return QueryResult(
                success=False,
                error="UNRESOLVED_PERIOD",
                message="Period could not be resolved. Please specify a valid time period.",
                confidence=0.0
            )

        if not self.fact_base.has_period(period_key):
            available_periods = self.fact_base.available_periods
            return QueryResult(
                success=False,
                error="NO_DATA_FOR_PERIOD",
                message=f"No data available for period '{period_key}'. Available: {', '.join(sorted(available_periods)[:5])}...",
                confidence=0.0
            )

        # Execute the query based on intent
        if parsed_query.intent == QueryIntent.POINT_QUERY:
            return self._execute_point_query(parsed_query)
        elif parsed_query.intent == QueryIntent.COMPARISON_QUERY:
            return self._execute_comparison_query(parsed_query)
        elif parsed_query.intent == QueryIntent.TREND_QUERY:
            return self._execute_trend_query(parsed_query)
        elif parsed_query.intent == QueryIntent.AGGREGATION_QUERY:
            return self._execute_aggregation_query(parsed_query)
        else:
            # Default to point query for unrecognized intents
            return self._execute_point_query(parsed_query)

    def _execute_point_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute a single metric, single period query."""
        result = self.fact_base.query(
            parsed_query.metric,
            parsed_query.resolved_period
        )

        # Check 3: Verify non-empty result
        if result is None:
            return QueryResult(
                success=False,
                error="EMPTY_RESULT",
                message=f"No data found for {parsed_query.metric} in {parsed_query.resolved_period}",
                confidence=0.0
            )

        # Calculate confidence based on data quality
        confidence = self.confidence_calculator.calculate(
            intent_score=1.0,  # Point queries are unambiguous
            entity_score=1.0,  # Metric found
            data_score=1.0     # Data exists
        )

        return QueryResult(
            success=True,
            value=result,
            confidence=bounded_confidence(confidence)
        )

    def _execute_comparison_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute a comparison between two periods."""
        # Get values for both periods
        value1 = self.fact_base.query(
            parsed_query.metric,
            parsed_query.resolved_period
        )

        if not parsed_query.comparison_period:
            return QueryResult(
                success=False,
                error="MISSING_COMPARISON_PERIOD",
                message="Comparison query requires two periods",
                confidence=0.0
            )

        value2 = self.fact_base.query(
            parsed_query.metric,
            parsed_query.comparison_period
        )

        if value1 is None or value2 is None:
            return QueryResult(
                success=False,
                error="INCOMPLETE_COMPARISON_DATA",
                message="Data not available for one or both periods",
                confidence=0.0
            )

        # Calculate difference and percentage change
        diff = value1 - value2
        pct_change = (diff / value2 * 100) if value2 != 0 else None

        return QueryResult(
            success=True,
            value={
                "period1": parsed_query.resolved_period,
                "value1": value1,
                "period2": parsed_query.comparison_period,
                "value2": value2,
                "difference": diff,
                "pct_change": pct_change
            },
            confidence=bounded_confidence(0.95)
        )

    def _execute_trend_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute a trend query across multiple periods."""
        # TODO: Implement trend queries
        return QueryResult(
            success=False,
            error="NOT_IMPLEMENTED",
            message="Trend queries are not yet implemented",
            confidence=0.0
        )

    def _execute_aggregation_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute an aggregation query (sum, average, etc.)."""
        # TODO: Implement aggregation queries
        return QueryResult(
            success=False,
            error="NOT_IMPLEMENTED",
            message="Aggregation queries are not yet implemented",
            confidence=0.0
        )
