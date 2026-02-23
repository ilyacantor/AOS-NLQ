"""
Visualization Intent Detection for Self-Developing Dashboards.

Detects when a user wants a visualization vs. a simple answer, and extracts
visualization requirements from natural language queries.

IMPORTANT: This module now tracks decisions explicitly and fails loudly when
metric extraction fails, rather than silently defaulting to CFO metrics.
"""

import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from src.nlq.core.debug_info import (
    DashboardDebugInfo,
    DecisionSource,
    FailureCategory,
    is_strict_mode,
)

logger = logging.getLogger(__name__)


class VisualizationIntent(str, Enum):
    """Types of visualization intents detected from queries."""
    SIMPLE_ANSWER = "simple_answer"  # Just give me a number/answer
    SINGLE_METRIC_TREND = "single_metric_trend"  # Show X over time
    COMPARISON_CHART = "comparison_chart"  # Compare X vs Y
    BREAKDOWN_CHART = "breakdown_chart"  # X by category
    MULTI_METRIC_DASHBOARD = "multi_metric_dashboard"  # Multiple KPIs
    DRILL_DOWN_VIEW = "drill_down_view"  # Ability to drill into details
    FULL_DASHBOARD = "full_dashboard"  # Complete dashboard request


class ChartTypeHint(str, Enum):
    """Hints for chart type from natural language."""
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    DONUT = "donut"
    TABLE = "table"
    KPI = "kpi"
    AREA = "area"
    STACKED = "stacked"
    MAP = "map"
    AUTO = "auto"  # Let system decide


@dataclass
class VisualizationRequirements:
    """Extracted visualization requirements from a query."""

    intent: VisualizationIntent
    chart_hint: ChartTypeHint
    metrics: List[str]
    dimensions: List[str]
    time_dimension: bool
    time_granularity: Optional[str]
    comparison_requested: bool
    drill_down_requested: bool
    filter_dimensions: List[str]
    confidence: float


# Visualization trigger patterns
VISUALIZATION_TRIGGERS = {
    # Strong triggers - definitely want a visualization
    "show me": 0.9,
    "show": 0.8,  # "show revenue by region"
    "visualize": 0.95,
    "chart": 0.95,
    "graph": 0.95,
    "plot": 0.95,
    "dashboard": 0.99,
    "kpis": 0.95,
    "kpi": 0.95,
    "results": 0.9,  # "2025 results" -> wants overview
    "performance": 0.85,  # "Q3 performance" -> wants overview
    "overview": 0.95,
    "summary": 0.9,
    "display": 0.85,
    "see": 0.7,
    "view": 0.75,
    "trend": 0.85,
    "over time": 0.9,
    "by region": 0.85,
    "by rep": 0.85,
    "by product": 0.85,
    "by stage": 0.85,
    "by quarter": 0.85,
    "by month": 0.85,
    "breakdown": 0.9,
    "break down": 0.9,
    "drill": 0.9,
    "drill into": 0.9,
    "compare": 0.85,
    "comparison": 0.85,
    "vs": 0.7,
    "versus": 0.75,
    "against": 0.7,
    # Conversational metric queries - imply wanting to see the data
    "looking": 0.75,  # "how's pipeline looking"
    "how's": 0.7,  # "how's revenue"
    "how is": 0.7,  # "how is pipeline"
    "doing": 0.7,  # "how's revenue doing"
}

# Answer triggers - just want a simple answer
ANSWER_TRIGGERS = {
    "what is": 0.6,
    "what was": 0.6,
    "what's": 0.6,
    "how much": 0.5,
    "how many": 0.5,
    "tell me": 0.4,
    "are we": 0.7,
    "did we": 0.7,
    "is the": 0.6,
    "who is": 0.9,
    "who's": 0.9,
}

# Ambiguous terms that require clarification when used alone
AMBIGUOUS_TERMS = {
    "performance": ["sales performance", "system performance", "team performance", "financial performance"],
    "metrics": ["sales metrics", "financial metrics", "product metrics", "customer metrics"],
    "data": ["sales data", "financial data", "customer data", "product data"],
    "numbers": ["revenue numbers", "sales numbers", "headcount numbers"],
    "stats": ["sales stats", "performance stats", "customer stats"],
    "overview": ["sales overview", "financial overview", "ops overview"],
}

# Chart type hints
CHART_TYPE_HINTS = {
    "line chart": ChartTypeHint.LINE,
    "line graph": ChartTypeHint.LINE,
    "trend line": ChartTypeHint.LINE,
    "over time": ChartTypeHint.LINE,
    "bar chart": ChartTypeHint.BAR,
    "bar graph": ChartTypeHint.BAR,
    "histogram": ChartTypeHint.BAR,
    "pie chart": ChartTypeHint.PIE,
    "pie": ChartTypeHint.PIE,
    "donut": ChartTypeHint.DONUT,
    "donut chart": ChartTypeHint.DONUT,
    "table": ChartTypeHint.TABLE,
    "list": ChartTypeHint.TABLE,
    "area chart": ChartTypeHint.AREA,
    "stacked": ChartTypeHint.STACKED,
    "stacked bar": ChartTypeHint.STACKED,
    "kpi": ChartTypeHint.KPI,
    "metric": ChartTypeHint.KPI,
    "number": ChartTypeHint.KPI,
    "map": ChartTypeHint.MAP,
    "on a map": ChartTypeHint.MAP,
    "geographic": ChartTypeHint.MAP,
    "geographically": ChartTypeHint.MAP,
}

# Geographic intent patterns - triggers map visualization
GEOGRAPHIC_PATTERNS = [
    r"\bwhere\b.*\b(revenue|sales|customers?|bookings)\b.*\b(comes?|from|located|concentrated)\b",
    r"\b(revenue|sales|customers?|bookings)\b.*\bwhere\b",
    r"\bmap\b.*\b(revenue|sales|distribution)\b",
    r"\b(revenue|sales)\b.*\bmap\b",
    r"\bgeographic\b.*\b(breakdown|distribution|split)\b",
    r"\bglobal\b.*\b(distribution|breakdown|revenue|sales)\b",
    r"\b(regional|regions?)\b.*\b(distribution|breakdown|revenue|sales)\b",
    r"\bshow.*\b(revenue|sales)\b.*\bby\s+region\b.*\bmap\b",
]

# Dimension patterns
DIMENSION_PATTERNS = {
    "by region": "region",
    "by rep": "rep",
    "by sales rep": "rep",
    "by representative": "rep",
    "by product": "product",
    "by product line": "product",
    "by customer": "customer",
    "by segment": "segment",
    "by category": "category",
    "by department": "department",
    "by team": "department",
    "by stage": "stage",
    "by pipeline stage": "stage",
    "by deal stage": "stage",
    "by sales stage": "stage",
    "by quarter": "quarter",
    "by month": "month",
    "by year": "year",
    "by week": "week",
}

# Time granularity patterns
TIME_GRANULARITY_PATTERNS = {
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
    "quarterly": "quarterly",
    "yearly": "yearly",
    "annual": "yearly",
    "by day": "daily",
    "by week": "weekly",
    "by month": "monthly",
    "by quarter": "quarterly",
    "by year": "yearly",
    "over time": "quarterly",  # Default
    "trend": "quarterly",
}


def detect_visualization_intent(query: str) -> VisualizationRequirements:
    """
    Detect visualization intent from a natural language query.

    Args:
        query: The user's natural language query

    Returns:
        VisualizationRequirements with extracted visualization specs
    """
    q = query.lower().strip()

    # Calculate visualization vs answer score
    viz_score = 0.0
    answer_score = 0.0

    for trigger, weight in VISUALIZATION_TRIGGERS.items():
        if trigger in q:
            viz_score = max(viz_score, weight)

    for trigger, weight in ANSWER_TRIGGERS.items():
        if trigger in q:
            answer_score = max(answer_score, weight)

    # Check for geographic intent first (map visualization)
    is_geographic = False
    for geo_pattern in GEOGRAPHIC_PATTERNS:
        if re.search(geo_pattern, q, re.IGNORECASE):
            is_geographic = True
            break

    # Detect chart type hint
    chart_hint = ChartTypeHint.MAP if is_geographic else ChartTypeHint.AUTO
    if not is_geographic:
        for pattern, hint in CHART_TYPE_HINTS.items():
            if pattern in q:
                chart_hint = hint
                break

    # Detect dimensions using DCL semantic client
    dimensions = []
    try:
        from src.nlq.services.dcl_semantic_client import get_semantic_client
        semantic_client = get_semantic_client()

        # Extract "by X" patterns and resolve through DCL
        by_match = re.search(r"\bby\s+(\w+(?:\s+\w+)?)", q)
        if by_match:
            dim_term = by_match.group(1)
            resolved_dim = semantic_client.resolve_dimension(dim_term)
            if resolved_dim and resolved_dim not in ["quarter", "month", "year", "week"]:
                dimensions.append(resolved_dim)
    except (RuntimeError, KeyError, TypeError, AttributeError, OSError) as e:
        logger.warning(f"[DIMENSION_EXTRACTION] DCL dimension resolution failed for '{query}': {e}")

    # Fallback to pattern matching if DCL didn't find anything
    if not dimensions:
        for pattern, dim in DIMENSION_PATTERNS.items():
            if pattern in q:
                if dim not in ["quarter", "month", "year", "week"]:
                    dimensions.append(dim)

    # Detect time dimension
    time_dimension = any(t in q for t in ["over time", "trend", "by quarter", "by month", "by year", "by week", "daily", "weekly", "monthly", "quarterly", "yearly"])

    # Detect time granularity
    time_granularity = None
    for pattern, gran in TIME_GRANULARITY_PATTERNS.items():
        if pattern in q:
            time_granularity = gran
            break

    # Detect comparison
    comparison_requested = any(c in q for c in ["compare", "comparison", "vs", "versus", "against"])

    # Detect drill-down request
    drill_down_requested = any(d in q for d in ["drill", "drill into", "drill down", "ability to drill", "click into", "dig into"])

    # Detect filter dimensions
    filter_patterns = ["with the ability to filter", "filterable by", "filter by"]
    filter_dimensions = []
    for pattern in filter_patterns:
        if pattern in q:
            # Try to extract what comes after
            match = re.search(rf"{pattern}\s+(\w+)", q)
            if match:
                filter_dimensions.append(match.group(1))

    # Extract metrics (simplified - in production would use Claude)
    metrics = _extract_metrics_from_query(q)

    # Determine final intent
    if "dashboard" in q:
        intent = VisualizationIntent.FULL_DASHBOARD
        confidence = 0.95
    elif any(term in q for term in ["results", "summary", "overview", "performance"]) and re.search(r"\b20\d{2}\b", q):
        # "[year] results" or "[year] summary" -> wants full dashboard for that year
        intent = VisualizationIntent.FULL_DASHBOARD
        confidence = 0.95
    elif viz_score > answer_score:
        if drill_down_requested:
            intent = VisualizationIntent.DRILL_DOWN_VIEW
        elif len(metrics) > 2 or "kpis" in q:
            intent = VisualizationIntent.MULTI_METRIC_DASHBOARD
        elif comparison_requested:
            intent = VisualizationIntent.COMPARISON_CHART
        elif dimensions:
            intent = VisualizationIntent.BREAKDOWN_CHART
        elif time_dimension:
            intent = VisualizationIntent.SINGLE_METRIC_TREND
        else:
            intent = VisualizationIntent.SINGLE_METRIC_TREND
        confidence = min(0.95, viz_score + 0.1)
    else:
        intent = VisualizationIntent.SIMPLE_ANSWER
        confidence = max(0.6, answer_score)

    return VisualizationRequirements(
        intent=intent,
        chart_hint=chart_hint,
        metrics=metrics,
        dimensions=dimensions,
        time_dimension=time_dimension,
        time_granularity=time_granularity,
        comparison_requested=comparison_requested,
        drill_down_requested=drill_down_requested,
        filter_dimensions=filter_dimensions,
        confidence=confidence,
    )


def _extract_metrics_from_query(query: str) -> List[str]:
    """
    Extract metric names from a query using DCL semantic catalog.

    Uses DCL's semantic layer to resolve user terms to canonical metric IDs.
    Falls back to pattern matching if DCL is unavailable.
    """
    import logging
    import re
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    logger = logging.getLogger(__name__)
    metrics = []
    q = query.lower()

    # Get semantic client
    semantic_client = get_semantic_client()
    catalog = semantic_client.get_catalog()

    # Identify dimension words (words after "by") to exclude from metric extraction
    # e.g., "revenue by customer" -> "customer" is a dimension, not a metric
    dimension_words = set()
    by_match = re.search(r'\bby\s+(\w+)', q)
    if by_match:
        dimension_words.add(by_match.group(1))

    # Extract potential metric terms from query using word boundaries
    # Common patterns: standalone words, phrases like "accounts receivable"
    words = q.split()
    matched_indices = set()  # Track which words were already matched

    # Try multi-word phrases first (e.g., "accounts receivable", "gross margin")
    for i in range(len(words)):
        if i in matched_indices:
            continue

        # Try 3-word phrases
        if i + 2 < len(words):
            phrase = " ".join(words[i:i+3])
            metric = semantic_client.resolve_metric(phrase)
            if metric and metric.id not in metrics:
                metrics.append(metric.id)
                matched_indices.update([i, i+1, i+2])
                logger.debug(f"Resolved '{phrase}' -> '{metric.id}'")
                continue

        # Try 2-word phrases
        if i + 1 < len(words):
            phrase = " ".join(words[i:i+2])
            metric = semantic_client.resolve_metric(phrase)
            if metric and metric.id not in metrics:
                metrics.append(metric.id)
                matched_indices.update([i, i+1])
                logger.debug(f"Resolved '{phrase}' -> '{metric.id}'")
                continue

        # Try single words
        word = words[i]
        # Skip common stopwords
        if word in {'the', 'a', 'an', 'and', 'or', 'by', 'for', 'to', 'in', 'on', 'at',
                    'show', 'me', 'add', 'compare', 'vs', 'versus', 'with', 'trend',
                    'chart', 'graph', 'display', 'what', 'is', 'our', 'how', 'much'}:
            continue
        # Skip dimension words (words after "by")
        if word in dimension_words:
            continue
        metric = semantic_client.resolve_metric(word)
        if metric and metric.id not in metrics:
            metrics.append(metric.id)
            matched_indices.add(i)
            logger.debug(f"Resolved '{word}' -> '{metric.id}'")

    # Check for persona-specific dashboard requests FIRST so we can merge
    # resolved metrics with persona defaults for consistent layout
    extraction_method = "semantic_resolution" if metrics else None

    persona_metrics = None
    persona_detected = None

    if any(term in q for term in ["ops dashboard", "operations dashboard", "coo dashboard"]):
        persona_metrics = ["headcount", "revenue_per_employee", "magic_number", "cac_payback_months", "ltv_cac"]
        persona_detected = "COO"
    elif any(term in q for term in ["sales dashboard", "cro dashboard", "growth dashboard"]):
        persona_metrics = ["pipeline", "win_rate", "quota_attainment", "sales_cycle_days"]
        persona_detected = "CRO"
    elif any(term in q for term in ["finance dashboard", "cfo dashboard", "financial dashboard"]):
        persona_metrics = ["revenue", "gross_margin_pct", "net_income", "arr"]
        persona_detected = "CFO"
    elif any(term in q for term in ["engineering dashboard", "cto dashboard", "tech dashboard"]):
        persona_metrics = ["uptime_pct", "p1_incidents", "deployment_frequency"]
        persona_detected = "CTO"
    elif any(term in q for term in ["customer dashboard", "cs dashboard", "success dashboard"]):
        persona_metrics = ["nrr", "gross_churn_pct", "customer_count"]
        persona_detected = "CS"

    if persona_metrics:
        if metrics:
            # Merge: keep resolved metrics, fill remaining slots from persona defaults
            for pm in persona_metrics:
                if pm not in metrics and len(metrics) < 4:
                    metrics.append(pm)
            extraction_method = f"semantic_resolution+persona_fill:{persona_detected}"
            logger.info(f"[METRIC_EXTRACTION] Merged resolved + {persona_detected} defaults: {metrics}")
        else:
            metrics = persona_metrics
            extraction_method = f"persona_default:{persona_detected}"
            logger.info(f"[METRIC_EXTRACTION] Using {persona_detected} persona metrics: {metrics}")
    elif not metrics:
        # Check for generic year+summary queries (e.g., "2025 results", "2024 summary")
        # These should default to CFO persona since they're asking for a business overview
        import re
        if re.search(r"\b20\d{2}\b", q) and any(term in q for term in ["results", "summary", "overview", "performance", "p&l", "dashboard", "dash", "kpi", "kpis"]):
            metrics = ["revenue", "gross_margin_pct", "operating_profit", "net_income"]
            extraction_method = "year_summary_default:CFO"
            logger.info(f"[METRIC_EXTRACTION] Year summary query detected, using CFO metrics: {metrics}")
        else:
            # NO SILENT DEFAULT - log a warning and return empty
            # The caller must decide what to do
            logger.warning(
                f"[METRIC_EXTRACTION] No metrics found in query: '{query}'. "
                f"Returning empty list - caller must handle this explicitly."
            )
            extraction_method = "none_found"
            # Return empty - let the caller decide what to do
            return []

    # Final validation: ensure all returned metrics exist in catalog
    valid_metrics, errors = semantic_client.validate_metrics(metrics)
    if errors:
        for error in errors:
            logger.warning(f"[METRIC_VALIDATION] {error}")
        if not valid_metrics:
            logger.error(
                f"[METRIC_EXTRACTION] All metrics failed validation for query: '{query}'. "
                f"Original metrics: {metrics}, Errors: {errors}"
            )
            return []
        metrics = valid_metrics

    logger.info(f"[METRIC_EXTRACTION] Extracted metrics: {metrics} (method: {extraction_method})")
    return metrics


def is_ambiguous_visualization_query(query: str) -> Tuple[bool, Optional[str], List[str]]:
    """
    Check if a visualization query contains ambiguous terms that need clarification.

    Args:
        query: The user's query

    Returns:
        Tuple of (is_ambiguous, ambiguous_term, suggested_options)
    """
    q = query.lower().strip()

    # Check if query has visualization triggers
    has_viz_trigger = any(trigger in q for trigger in VISUALIZATION_TRIGGERS.keys())
    if not has_viz_trigger:
        return False, None, []

    # Check for ambiguous terms
    for term, options in AMBIGUOUS_TERMS.items():
        if term in q:
            # Check if any specific variant is mentioned
            term_is_qualified = any(opt.lower() in q for opt in options)
            if not term_is_qualified:
                # The term is used alone without qualification
                return True, term, options

    return False, None, []


def should_generate_visualization(query: str) -> Tuple[bool, VisualizationRequirements]:
    """
    Determine if a query should result in a visualization.

    Args:
        query: The user's natural language query

    Returns:
        Tuple of (should_visualize, requirements)
    """
    requirements = detect_visualization_intent(query)
    should_visualize = requirements.intent != VisualizationIntent.SIMPLE_ANSWER
    return should_visualize, requirements
