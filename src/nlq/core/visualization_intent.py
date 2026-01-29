"""
Visualization Intent Detection for Self-Developing Dashboards.

Detects when a user wants a visualization vs. a simple answer, and extracts
visualization requirements from natural language queries.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


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
    "visualize": 0.95,
    "chart": 0.95,
    "graph": 0.95,
    "plot": 0.95,
    "dashboard": 0.99,
    "display": 0.85,
    "see": 0.7,
    "view": 0.75,
    "trend": 0.85,
    "over time": 0.9,
    "by region": 0.85,
    "by rep": 0.85,
    "by product": 0.85,
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
}

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

    # Detect chart type hint
    chart_hint = ChartTypeHint.AUTO
    for pattern, hint in CHART_TYPE_HINTS.items():
        if pattern in q:
            chart_hint = hint
            break

    # Detect dimensions
    dimensions = []
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
    Extract metric names from a query.

    This is a simplified extraction. In production, this would use Claude
    for more accurate semantic extraction.
    """
    metrics = []
    q = query.lower()

    # Common metric patterns
    metric_patterns = {
        "revenue": ["revenue", "sales", "top line", "bookings"],
        "gross_margin_pct": ["gross margin", "margin", "gm"],
        "net_income": ["net income", "profit", "bottom line"],
        "pipeline": ["pipeline"],
        "gross_churn_pct": ["churn", "churn rate", "gross churn"],
        "nrr": ["nrr", "net retention", "net revenue retention"],
        "headcount": ["headcount", "employees", "staff", "team size"],
        "win_rate": ["win rate", "close rate"],
        "quota_attainment": ["quota", "quota attainment", "attainment"],
        "cac_payback_months": ["cac payback", "payback"],
        "ltv_cac": ["ltv/cac", "ltv cac", "lifetime value"],
        "magic_number": ["magic number", "efficiency"],
        "uptime_pct": ["uptime", "availability"],
        "p1_incidents": ["incidents", "p1", "outages"],
    }

    for canonical, patterns in metric_patterns.items():
        for pattern in patterns:
            if pattern in q:
                if canonical not in metrics:
                    metrics.append(canonical)
                break

    # If no specific metrics found, default to revenue
    if not metrics:
        metrics = ["revenue"]

    return metrics


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
