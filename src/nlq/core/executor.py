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

        CRITICAL: This method performs validation checks before returning
        results to ensure we never return empty/invalid data silently.
        """
        # Execute the query based on intent
        # Note: Breakdown queries skip metric validation since they use breakdown_metrics
        if parsed_query.intent == QueryIntent.BREAKDOWN_QUERY:
            return self._execute_breakdown_query(parsed_query)

        # Check 1: Does the metric exist in our schema?
        available_metrics = self.fact_base.available_metrics
        if parsed_query.metric not in available_metrics:
            return QueryResult(
                success=False,
                error="UNKNOWN_METRIC",
                message=f"Metric '{parsed_query.metric}' not found. Available: {', '.join(sorted(available_metrics)[:10])}...",
                confidence=0.0
            )

        # Route to appropriate handler
        if parsed_query.intent == QueryIntent.COMPARISON_QUERY:
            return self._execute_comparison_query(parsed_query)
        elif parsed_query.intent == QueryIntent.AGGREGATION_QUERY:
            return self._execute_aggregation_query(parsed_query)
        elif parsed_query.intent == QueryIntent.TREND_QUERY:
            return self._execute_trend_query(parsed_query)

        # For point queries, validate the period first
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
        if not parsed_query.aggregation_periods:
            return QueryResult(
                success=False,
                error="MISSING_AGGREGATION_PERIODS",
                message="Aggregation query requires periods to aggregate over",
                confidence=0.0
            )

        # Get values for all periods
        values = []
        for period in parsed_query.aggregation_periods:
            value = self.fact_base.query(parsed_query.metric, period)
            if value is not None:
                values.append((period, value))

        if not values:
            return QueryResult(
                success=False,
                error="NO_DATA_FOR_AGGREGATION",
                message=f"No data found for any of the specified periods",
                confidence=0.0
            )

        # Calculate aggregation
        agg_type = parsed_query.aggregation_type or "sum"
        all_values = [v[1] for v in values]

        if agg_type == "average":
            result_value = sum(all_values) / len(all_values)
        else:  # default to sum
            result_value = sum(all_values)

        return QueryResult(
            success=True,
            value={
                "aggregation_type": agg_type,
                "result": result_value,
                "periods": [v[0] for v in values],
                "values": [v[1] for v in values],
            },
            confidence=bounded_confidence(0.95)
        )

    def _execute_breakdown_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute a breakdown query (multiple metrics for one period)."""
        if not parsed_query.breakdown_metrics:
            return QueryResult(
                success=False,
                error="MISSING_BREAKDOWN_METRICS",
                message="Breakdown query requires metrics to break down",
                confidence=0.0
            )

        period = parsed_query.resolved_period
        if not period:
            return QueryResult(
                success=False,
                error="UNRESOLVED_PERIOD",
                message="Period could not be resolved for breakdown",
                confidence=0.0
            )

        # Get values for all metrics
        breakdown = {}
        for metric in parsed_query.breakdown_metrics:
            value = self.fact_base.query(metric, period)
            if value is not None:
                breakdown[metric] = value

        if not breakdown:
            return QueryResult(
                success=False,
                error="NO_DATA_FOR_BREAKDOWN",
                message=f"No data found for any of the specified metrics in {period}",
                confidence=0.0
            )

        return QueryResult(
            success=True,
            value={
                "period": period,
                "breakdown": breakdown,
            },
            confidence=bounded_confidence(0.95)
        )
