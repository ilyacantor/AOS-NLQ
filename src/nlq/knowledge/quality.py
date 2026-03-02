"""
Data quality and freshness mappings for Galaxy visualization.

Quality and freshness vary by metric type:
- High quality: Audited financials
- Medium quality: Operational systems
- Lower quality: Forecasts/estimates

Freshness is cadence-relative — staleness depends on how often the metric updates:
- Real-time: Cash, bookings — stale after 24h
- Weekly: AR, AP — stale after 7 days
- Periodic: Revenue, expenses — always fresh (monthly/quarterly cadence)
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

# --- Cadence categories ---
# Staleness is relative to how often a metric naturally updates.
CADENCE_REALTIME = "realtime"   # Daily or more frequent — stale after 24h
CADENCE_WEEKLY = "weekly"       # Weekly refresh — stale after 7 days
CADENCE_PERIODIC = "periodic"   # Monthly/quarterly — always fresh

# Stale/old thresholds (hours) per cadence
CADENCE_THRESHOLDS = {
    CADENCE_REALTIME: {"stale": 24, "old": 72},      # >24h stale, >3d old
    CADENCE_WEEKLY: {"stale": 168, "old": 336},       # >7d stale, >14d old
    CADENCE_PERIODIC: {"stale": None, "old": None},   # never stale
}

# Map each metric to its update cadence
METRIC_CADENCE = {
    # Real-time / daily
    "cash": CADENCE_REALTIME,
    "bookings": CADENCE_REALTIME,
    "sales_pipeline": CADENCE_REALTIME,

    # Weekly
    "ar": CADENCE_WEEKLY,
    "ap": CADENCE_WEEKLY,
    "deferred_revenue": CADENCE_WEEKLY,

    # Monthly / quarterly — always fresh
    "revenue": CADENCE_PERIODIC,
    "net_income": CADENCE_PERIODIC,
    "cogs": CADENCE_PERIODIC,
    "gross_profit": CADENCE_PERIODIC,
    "operating_profit": CADENCE_PERIODIC,
    "sga": CADENCE_PERIODIC,
    "selling_expenses": CADENCE_PERIODIC,
    "g_and_a_expenses": CADENCE_PERIODIC,
    "gross_margin_pct": CADENCE_PERIODIC,
    "operating_margin_pct": CADENCE_PERIODIC,
    "net_income_pct": CADENCE_PERIODIC,
    "yoy_growth": CADENCE_PERIODIC,
    "current_assets": CADENCE_PERIODIC,
    "current_liabilities": CADENCE_PERIODIC,
    "total_assets": CADENCE_PERIODIC,
    "total_liabilities": CADENCE_PERIODIC,
    "retained_earnings": CADENCE_PERIODIC,

    # Slow-moving — always fresh
    "ppe": CADENCE_PERIODIC,
    "intangibles": CADENCE_PERIODIC,
    "stockholders_equity": CADENCE_PERIODIC,
    "expansion_revenue": CADENCE_PERIODIC,
    "revenue_churn": CADENCE_PERIODIC,
}

# How old the data typically is (display value for Galaxy nodes)
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
DEFAULT_CADENCE = CADENCE_PERIODIC


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


def get_cadence(metric: str) -> str:
    """
    Get the update cadence for a metric.

    Args:
        metric: The metric name

    Returns:
        Cadence string: "realtime", "weekly", or "periodic"
    """
    return METRIC_CADENCE.get(metric, DEFAULT_CADENCE)


def get_freshness_level(freshness: str, metric: str = "") -> str:
    """
    Convert freshness string to level for dot color, relative to the
    metric's update cadence.

    Cadence rules:
    - Periodic (monthly/quarterly): always fresh
    - Weekly: fresh ≤7d, stale 7-14d, old >14d
    - Real-time: fresh ≤24h, stale 24-72h, old >72h

    Args:
        freshness: Freshness string (e.g., "2h", "24h")
        metric: Metric name (used to look up cadence). If empty,
                falls back to realtime thresholds.

    Returns:
        "fresh" (green), "stale" (yellow), or "old" (red)
    """
    import re

    cadence = get_cadence(metric) if metric else CADENCE_REALTIME
    thresholds = CADENCE_THRESHOLDS[cadence]

    # Periodic metrics are always fresh
    if thresholds["stale"] is None:
        return "fresh"

    match = re.match(r"(\d+)h", freshness)
    if not match:
        return "old"

    hours = int(match.group(1))

    if hours <= thresholds["stale"]:
        return "fresh"
    elif hours <= thresholds["old"]:
        return "stale"
    else:
        return "old"
