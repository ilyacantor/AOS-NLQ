"""
Query execution against DCL for AOS-NLQ.

CRITICAL REQUIREMENTS:
1. Check metric exists BEFORE querying
2. Verify non-empty results
3. Return explicit errors for zero-row scenarios

Never return empty results silently - always provide appropriate error codes.

All data access goes through DCL's query API.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.nlq.core.confidence import ConfidenceCalculator, bounded_confidence
from src.nlq.models.query import ParsedQuery, QueryIntent
from src.nlq.models.response import QueryResult
from src.nlq.services.dcl_semantic_client import get_semantic_client

if TYPE_CHECKING:
    from src.nlq.llm.client import ClaudeClient

logger = logging.getLogger(__name__)


class QueryExecutor:
    """Executes parsed queries against DCL."""

    def __init__(self, fact_base=None, claude_client: Optional["ClaudeClient"] = None):
        """
        Initialize the query executor.

        Args:
            fact_base: Ignored - kept for backwards compatibility
            claude_client: Optional Claude client for LLM fallback on unknown breakdowns
        """
        self.dcl_client = get_semantic_client()
        self.claude_client = claude_client
        self.confidence_calculator = ConfidenceCalculator()
        self._last_data_source = None  # Track data source for structural integrity

    def _is_year_period(self, period: str) -> bool:
        """Check if a period string represents a full year (e.g., '2025' vs '2025-Q1')."""
        if not period:
            return False
        # A year period is exactly 4 digits with no quarter suffix
        return period.isdigit() and len(period) == 4

    def _query_dcl(self, metric: str, period: str) -> Optional[Any]:
        """
        Query DCL for a metric value.

        Args:
            metric: Canonical metric ID
            period: Period string (e.g., "2025", "2025-Q1")

        Returns:
            Metric value or None if not found
        """
        granularity = "annual" if self._is_year_period(period) else "quarterly"

        result = self.dcl_client.query(
            metric=metric,
            time_range={"period": period, "granularity": granularity}
        )

        if result.get("error") or result.get("status") == "error":
            logger.debug(f"DCL query failed for {metric}/{period}: {result.get('error')}")
            self._last_data_source = None
            return None

        # Capture data_source for structural integrity (source attribution)
        self._last_data_source = result.get("data_source")

        return self._extract_value_from_dcl(result, aggregate=self._is_year_period(period), metric=metric)

    def _extract_value_from_dcl(self, result: Dict[str, Any], aggregate: bool = False, metric: str = None) -> Optional[Any]:
        """Extract a single value from DCL query result.

        For annual aggregation, uses correct method based on metric unit:
        - Additive metrics (usd_millions, usd, count): sum quarterly values
        - Non-additive metrics (pct, ratio, score, days, hours): average quarterly values
        """
        data = result.get("data", [])
        if not data:
            return None

        # Handle different response formats
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict) and "value" in data[0]:
                if aggregate:
                    vals = [d.get("value", 0) for d in data if d.get("value") is not None]
                    if not vals:
                        return None
                    # Determine aggregation method from metric unit
                    _non_additive = {"pct", "ratio", "score", "days", "hours", "months", "index"}
                    _is_additive = True
                    if metric:
                        from src.nlq.knowledge.schema import get_canonical_unit
                        _is_additive = get_canonical_unit(metric) not in _non_additive
                    if _is_additive:
                        return sum(vals)
                    else:
                        return sum(vals) / len(vals)
                else:
                    # Return the specific period's value (usually last in list)
                    return data[-1].get("value")
            else:
                return data[-1] if data else None
        elif isinstance(data, (int, float)):
            return data

        return None

    def _smart_query(self, metric: str, period: str) -> Any:
        """
        Query DCL for a metric, handling annual vs quarterly periods.

        This is the proper way to handle metrics that only exist in quarterly data
        (like EBITDA) when the user asks for annual values.
        """
        return self._query_dcl(metric, period)

    def execute(self, parsed_query: ParsedQuery) -> QueryResult:
        """
        Execute a parsed query against DCL.

        Tries graph resolution first via POST /api/dcl/resolve. If the graph
        can answer (can_answer=True), uses the graph result. Otherwise falls
        back to the existing flat query path.

        Args:
            parsed_query: Structured query from the parser

        Returns:
            QueryResult with value or error information

        CRITICAL: This method performs validation checks before returning
        results to ensure we never return empty/invalid data silently.
        """
        # =====================================================================
        # GRAPH RESOLUTION — try semantic graph first, fall back to flat query
        # =====================================================================
        graph_result = self._try_graph_resolution(parsed_query)
        if graph_result is not None:
            return graph_result

        # =====================================================================
        # FLAT QUERY PATH — existing behavior (fallback)
        # =====================================================================

        # Execute the query based on intent
        # Note: Breakdown queries skip metric validation since they use breakdown_metrics
        if parsed_query.intent == QueryIntent.BREAKDOWN_QUERY:
            return self._execute_breakdown_query(parsed_query)

        # Check 1: Does the metric exist in DCL catalog?
        # Try negotiating the name first — NLQ may use a different canonical
        # name than DCL (e.g. gross_margin_pct vs gross_margin).
        catalog = self.dcl_client.get_catalog()
        available_metrics = set(catalog.metrics.keys())
        if parsed_query.metric not in available_metrics:
            negotiated = self.dcl_client._negotiate_metric_id(parsed_query.metric)
            if negotiated != parsed_query.metric and negotiated in available_metrics:
                logger.info(f"Negotiated metric: {parsed_query.metric} → {negotiated}")
                parsed_query.metric = negotiated
            else:
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

        # Note: Period validation removed - DCL handles this and returns empty if no data
        return self._execute_point_query(parsed_query)

    def _try_graph_resolution(self, parsed_query: ParsedQuery) -> Optional[QueryResult]:
        """
        Attempt to resolve query via DCL's semantic graph traversal.

        Returns QueryResult if graph can answer, None to fall back to flat query.
        """
        concepts = [parsed_query.metric] if parsed_query.metric else []
        if not concepts:
            return None

        # Extract dimensions from parsed query
        dimensions = []
        if parsed_query.dimension:
            dimensions.append(parsed_query.dimension)

        # Extract filters from parsed query (entity-based filtering)
        filters = []
        if parsed_query.entity:
            filters.append({"dimension": "entity", "value": parsed_query.entity})

        try:
            graph_response = self.dcl_client.resolve_via_graph(
                concepts=concepts,
                dimensions=dimensions if dimensions else None,
                filters=filters if filters else None,
            )
        except Exception as e:
            logger.debug(f"Graph resolution attempt failed: {e}")
            return None

        # If graph can't answer, fall back to flat query
        if not graph_response.get("can_answer", False):
            reason = graph_response.get("reason", "")
            source = graph_response.get("source", "")
            if reason:
                logger.info(f"Graph cannot answer (source={source}): {reason}")
            return None

        # Graph answered — format into QueryResult
        return self._format_graph_result(graph_response, parsed_query)

    def _format_graph_result(
        self,
        graph_response: Dict[str, Any],
        parsed_query: ParsedQuery,
    ) -> QueryResult:
        """
        Format a successful graph resolution into NLQ's QueryResult.

        Extracts value, confidence, provenance, and warnings from the
        graph response and packages them into the standard QueryResult format.
        """
        confidence = graph_response.get("confidence", 0.0)
        warnings = graph_response.get("warnings", [])

        # Build metadata from graph provenance
        metadata = {
            "resolution_source": "dcl_graph",
            "provenance": graph_response.get("provenance"),
            "join_paths": graph_response.get("join_paths"),
            "filters_resolved": graph_response.get("filters_resolved"),
            "warnings": warnings,
            "resolved_concepts": graph_response.get("resolved_concepts"),
        }

        # Extract primary value from resolved concepts
        resolved_concepts = graph_response.get("resolved_concepts", [])
        value = None
        if resolved_concepts:
            primary = resolved_concepts[0]
            value = primary.get("value")
            # If no direct value, package the full resolution as the value
            if value is None:
                value = {
                    "concept": primary.get("concept", parsed_query.metric),
                    "system": primary.get("system"),
                    "field": primary.get("field"),
                    "confidence": primary.get("confidence", confidence),
                    "provenance": graph_response.get("provenance"),
                }

        # If graph returned data directly, use it
        if graph_response.get("data"):
            value = graph_response["data"]

        # Extract data_source from graph response
        graph_source = graph_response.get("source", "")
        data_source = "dcl" if graph_source == "dcl_graph" else graph_source or None

        return QueryResult(
            success=True,
            value=value,
            confidence=bounded_confidence(confidence),
            query_type="graph_resolution",
            metadata=metadata,
            data_source=data_source,
        )

    def _execute_point_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute a single metric, single period query."""
        if not parsed_query.resolved_period:
            return QueryResult(
                success=False,
                error="UNRESOLVED_PERIOD",
                message="Period could not be resolved",
                confidence=0.0
            )

        # Use _smart_query to handle annual periods by aggregating quarterly data
        result = self._smart_query(
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
            confidence=bounded_confidence(confidence),
            data_source=self._last_data_source
        )

    def _execute_comparison_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute a comparison between two periods."""
        if not parsed_query.resolved_period:
            return QueryResult(
                success=False,
                error="UNRESOLVED_PERIOD",
                message="Period could not be resolved for comparison",
                confidence=0.0
            )

        # Get values for both periods (use _smart_query to aggregate quarterly data for annual periods)
        value1 = self._smart_query(
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

        value2 = self._smart_query(
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
            confidence=bounded_confidence(0.95),
            data_source=self._last_data_source
        )

    def _execute_trend_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute a trend query across multiple periods."""
        metric = parsed_query.metric
        if not metric:
            return QueryResult(
                success=False,
                error="MISSING_METRIC",
                message="Trend query requires a metric",
                confidence=0.0
            )

        # Determine periods to query based on trend_periods or default to quarterly
        if parsed_query.trend_periods:
            periods = parsed_query.trend_periods
        else:
            # Default: Get last 8 quarters
            periods = [
                "2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4",
                "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"
            ]

        # Query each period via DCL
        trend_data = []
        for period in periods:
            value = self._query_dcl(metric, period)
            if value is not None:
                trend_data.append({
                    "period": period,
                    "value": value
                })

        if not trend_data:
            return QueryResult(
                success=False,
                error="NO_DATA_FOR_TREND",
                message=f"No data found for {metric} across the specified periods",
                confidence=0.0
            )

        # Calculate trend direction
        if len(trend_data) >= 2:
            first_val = trend_data[0]["value"]
            last_val = trend_data[-1]["value"]
            change_pct = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0
            trend_direction = "increasing" if change_pct > 0 else "decreasing" if change_pct < 0 else "flat"
        else:
            change_pct = 0
            trend_direction = "insufficient data"

        return QueryResult(
            success=True,
            value={
                "metric": metric,
                "trend_data": trend_data,
                "change_pct": round(change_pct, 1),
                "trend_direction": trend_direction,
                "period_count": len(trend_data)
            },
            confidence=0.95,
            query_type="trend",
            metadata={
                "metric": metric,
                "periods": [d["period"] for d in trend_data]
            },
            data_source=self._last_data_source
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

        # Get values for all periods via DCL
        values = []
        for period in parsed_query.aggregation_periods:
            value = self._query_dcl(parsed_query.metric, period)
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
            confidence=bounded_confidence(0.95),
            data_source=self._last_data_source
        )

    def _execute_breakdown_query(self, parsed_query: ParsedQuery) -> QueryResult:
        """Execute a breakdown query (multiple metrics for one period)."""
        breakdown_metrics = parsed_query.breakdown_metrics

        # Fallback: If no breakdown_metrics provided, derive from the primary metric
        if not breakdown_metrics:
            breakdown_metrics = self._derive_breakdown_metrics(parsed_query.metric)

        if not breakdown_metrics:
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

        # Get values for all metrics we have data for (use _smart_query for annual aggregation)
        breakdown = {}
        for metric in breakdown_metrics:
            value = self._smart_query(metric, period)
            if value is not None:
                breakdown[metric] = value

        # Graceful fallback: if none of the suggested metrics have data,
        # fall back to core metrics that always exist (revenue, margin, etc.)
        if not breakdown:
            fallback_metrics = ["revenue", "gross_margin_pct", "operating_profit", "arr"]
            for metric in fallback_metrics:
                value = self._smart_query(metric, period)
                if value is not None:
                    breakdown[metric] = value
                    break  # Just need one to show something useful

        # Still nothing? Try the primary metric itself
        if not breakdown and parsed_query.metric:
            value = self._smart_query(parsed_query.metric, period)
            if value is not None:
                breakdown[parsed_query.metric] = value

        return QueryResult(
            success=True,
            value={
                "period": period,
                "breakdown": breakdown,
            },
            confidence=bounded_confidence(0.95)
        )

    def _derive_breakdown_metrics(self, metric: str) -> list[str]:
        """
        Derive breakdown metrics from a primary metric when LLM doesn't provide them.

        Strategy:
        1. Check BREAKDOWN_MAPPINGS for predefined breakdowns (fast)
        2. If not found, ask the LLM what drives this metric (graceful fallback)

        Uses actual metrics that exist in the fact base.
        """
        BREAKDOWN_MAPPINGS = {
            # Revenue & Sales
            "revenue": ["new_logo_revenue", "expansion_revenue", "renewal_revenue"],
            "arr": ["new_logo_revenue", "expansion_revenue", "renewal_revenue"],
            "bookings": ["new_logo_revenue", "expansion_revenue", "pipeline", "win_rate_pct"],
            # Profitability
            "gross_profit": ["revenue", "cogs"],
            "gross_margin_pct": ["revenue", "cogs", "gross_profit"],
            "operating_profit": ["revenue", "cogs", "sga", "gross_profit"],
            "operating_margin_pct": ["revenue", "operating_profit", "sga"],
            "net_income": ["revenue", "gross_profit", "operating_profit", "sga"],
            "net_income_pct": ["revenue", "gross_profit", "operating_profit", "sga"],
            "cogs": ["revenue", "gross_margin_pct"],
            # Expenses
            "sga": ["selling_expenses", "g_and_a_expenses"],
            "cloud_spend": ["cloud_spend_pct_revenue", "revenue"],
            # Pipeline & Sales
            "pipeline": ["qualified_pipeline", "win_rate_pct", "sales_cycle_days", "avg_deal_size"],
            "win_rate_pct": ["pipeline", "qualified_pipeline", "avg_deal_size", "sales_cycle_days"],
            "quota_attainment_pct": ["reps_at_quota_pct", "sales_headcount", "pipeline", "win_rate_pct"],
            # Retention & Churn
            "gross_churn_pct": ["logo_churn_pct", "nrr", "customer_count"],
            "nrr": ["gross_churn_pct", "expansion_revenue", "renewal_revenue"],
            "customer_count": ["new_logos", "logo_churn_pct", "nrr"],
            # Efficiency Metrics
            "magic_number": ["arr", "sga", "sales_headcount"],
            "ltv_cac": ["cac_payback_months", "gross_churn_pct", "nrr"],
            "burn_multiple": ["revenue", "operating_profit", "net_income"],
            # People
            "headcount": ["engineering_headcount", "product_headcount", "sales_headcount", "marketing_headcount", "cs_headcount", "ga_headcount"],
            "attrition_rate_pct": ["headcount", "hires", "attrition"],
            "attrition": ["headcount", "hires", "attrition_rate_pct"],
            # Customer Success
            "nps": ["csat", "support_tickets", "resolution_hours"],
            "csat": ["nps", "support_tickets", "resolution_hours", "first_response_hours"],
            # Tech & Engineering
            "uptime_pct": ["downtime_hours", "deploys_per_week", "security_vulns"],
            "tech_debt_pct": ["code_coverage_pct", "bug_escape_rate", "critical_bugs"],
            # Balance Sheet
            "ar": ["revenue", "deferred_revenue", "unbilled_revenue"],
            "ap": ["revenue", "cogs", "current_liabilities"],
            "cash": ["revenue", "cogs", "sga", "operating_profit"],
        }

        # Normalize metric name for lookup
        metric_lower = metric.lower().replace("-", "_").replace(" ", "_")

        # First: check predefined mappings (fast path)
        if metric_lower in BREAKDOWN_MAPPINGS:
            return BREAKDOWN_MAPPINGS[metric_lower]

        # Second: ask LLM for breakdown components (graceful fallback)
        if self.claude_client:
            logger.info(f"No predefined breakdown for '{metric}', asking LLM...")
            llm_components = self.claude_client.get_breakdown_components(metric)
            if llm_components:
                return llm_components

        # No breakdown available
        return []
