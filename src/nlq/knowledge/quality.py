"""
Data quality and freshness mappings for Galaxy visualization.

Quality and freshness vary by metric type:
- High quality: Audited financials
- Medium quality: Operational systems
- Lower quality: Forecasts/estimates

Freshness indicates how often metrics update:
- Real-time: Cash, bookings
- Weekly: AR, AP
- Monthly: Revenue, expenses
"""

# Data quality varies by metric source (0.0 to 1.0)
METRIC_DATA_QUALITY = {
    # High quality - from audited financials
    "revenue": 0.95,
    "net_income": 0.95,
    "gross_profit": 0.95,
    "operating_profit": 0.95,
    "cogs": 0.95,
    "sga": 0.95,
    "selling_expenses": 0.95,
    "g_and_a_expenses": 0.95,

    # Good quality - from operational systems
    "bookings": 0.88,
    "ar": 0.90,
    "ap": 0.90,
    "cash": 0.92,
    "deferred_revenue": 0.90,
    "current_assets": 0.90,
    "current_liabilities": 0.90,
    "total_assets": 0.92,
    "total_liabilities": 0.92,
    "stockholders_equity": 0.92,
    "retained_earnings": 0.92,
    "ppe": 0.90,
    "intangibles": 0.88,

    # Medium quality - calculated metrics
    "gross_margin_pct": 0.90,
    "operating_margin_pct": 0.90,
    "net_income_pct": 0.90,
    "yoy_growth": 0.88,

    # Lower quality - forecasts or estimates
    "sales_pipeline": 0.70,
    "expansion_revenue": 0.75,
    "revenue_churn": 0.80,
}

# How often each metric type updates
METRIC_FRESHNESS = {
    # Real-time / daily
    "cash": "2h",
    "bookings": "4h",
    "sales_pipeline": "6h",

    # Weekly
    "ar": "12h",
    "ap": "12h",
    "deferred_revenue": "12h",

    # Monthly / quarterly
    "revenue": "24h",
    "net_income": "24h",
    "cogs": "24h",
    "gross_profit": "24h",
    "operating_profit": "24h",
    "sga": "24h",
    "selling_expenses": "24h",
    "g_and_a_expenses": "24h",
    "gross_margin_pct": "24h",
    "operating_margin_pct": "24h",
    "net_income_pct": "24h",
    "yoy_growth": "24h",
    "current_assets": "24h",
    "current_liabilities": "24h",
    "total_assets": "24h",
    "total_liabilities": "24h",
    "retained_earnings": "24h",

    # Slow-moving
    "ppe": "48h",
    "intangibles": "48h",
    "stockholders_equity": "48h",
    "expansion_revenue": "48h",
    "revenue_churn": "48h",
}

# Default values
DEFAULT_DATA_QUALITY = 0.80
DEFAULT_FRESHNESS = "24h"


def get_data_quality(metric: str) -> float:
    """
    Get data quality score for a metric.

    Args:
        metric: The metric name

    Returns:
        Data quality score (0.0 to 1.0)
    """
    return METRIC_DATA_QUALITY.get(metric, DEFAULT_DATA_QUALITY)


def get_freshness(metric: str) -> str:
    """
    Get freshness indicator for a metric.

    Args:
        metric: The metric name

    Returns:
        Freshness string (e.g., "2h", "24h", "48h")
    """
    return METRIC_FRESHNESS.get(metric, DEFAULT_FRESHNESS)


def get_freshness_level(freshness: str) -> str:
    """
    Convert freshness string to level for dot color.

    Args:
        freshness: Freshness string (e.g., "2h", "24h")

    Returns:
        "fresh" (green), "stale" (yellow), or "old" (red)
    """
    # Parse hours from string
    import re
    match = re.match(r"(\d+)h", freshness)
    if not match:
        return "old"

    hours = int(match.group(1))

    if hours <= 6:
        return "fresh"
    elif hours <= 24:
        return "stale"
    else:
        return "old"
