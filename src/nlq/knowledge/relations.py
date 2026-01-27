"""
Metric relationship mappings for Galaxy visualization.

Defines related metrics and context metrics for each primary metric,
used to populate the middle (POTENTIAL) and outer (HYPOTHESIS) orbital rings.
"""

# Related metrics for middle ring (POTENTIAL)
# These are closely related to the primary metric
RELATED_METRICS = {
    # P&L Metrics
    "revenue": ["bookings", "net_income", "yoy_growth"],
    "bookings": ["revenue", "sales_pipeline", "deferred_revenue"],
    "net_income": ["operating_profit", "net_income_pct", "revenue"],
    "operating_profit": ["gross_profit", "sga", "operating_margin_pct"],
    "gross_profit": ["revenue", "cogs", "gross_margin_pct"],
    "cogs": ["revenue", "gross_margin_pct", "gross_profit"],
    "sga": ["selling_expenses", "g_and_a_expenses", "operating_profit"],
    "selling_expenses": ["sga", "g_and_a_expenses", "revenue"],
    "g_and_a_expenses": ["sga", "selling_expenses", "operating_profit"],

    # Margins
    "gross_margin_pct": ["operating_margin_pct", "net_income_pct", "gross_profit"],
    "operating_margin_pct": ["gross_margin_pct", "net_income_pct", "operating_profit"],
    "net_income_pct": ["operating_margin_pct", "gross_margin_pct", "net_income"],

    # Balance Sheet
    "cash": ["ar", "ap", "current_liabilities"],
    "ar": ["revenue", "dso", "deferred_revenue"],
    "ap": ["cogs", "dpo", "cash"],
    "deferred_revenue": ["revenue", "bookings", "ar"],
    "current_assets": ["cash", "ar", "inventory"],
    "current_liabilities": ["ap", "deferred_revenue", "cash"],
    "total_assets": ["current_assets", "ppe", "intangibles"],
    "total_liabilities": ["current_liabilities", "long_term_debt", "deferred_revenue"],
    "stockholders_equity": ["retained_earnings", "net_income", "total_assets"],
    "retained_earnings": ["net_income", "stockholders_equity", "cash"],
    "ppe": ["total_assets", "depreciation", "capex"],
    "intangibles": ["total_assets", "goodwill", "amortization"],

    # Growth metrics
    "yoy_growth": ["revenue", "bookings", "net_income"],
    "expansion_revenue": ["revenue", "bookings", "revenue_churn"],
    "revenue_churn": ["revenue", "expansion_revenue", "net_income"],
}

# Context metrics for outer ring (HYPOTHESIS)
# These provide additional context but are not directly related
CONTEXT_METRICS = {
    "revenue": ["expansion_revenue", "revenue_churn"],
    "net_income": ["cash", "retained_earnings"],
    "bookings": ["expansion_revenue", "revenue_churn"],
    "cash": ["net_income", "operating_profit"],
    "operating_profit": ["cash", "capex"],
    "gross_profit": ["operating_profit", "net_income"],
    "sga": ["revenue", "operating_profit"],
    "gross_margin_pct": ["revenue", "cogs"],
    "operating_margin_pct": ["revenue", "sga"],
    "net_income_pct": ["revenue", "tax_expense"],
    "ar": ["cash", "working_capital"],
    "ap": ["cash", "working_capital"],
    "deferred_revenue": ["cash", "revenue"],
}


def get_related_metrics(metric: str, limit: int = 3) -> list:
    """
    Get related metrics for the middle ring.

    Args:
        metric: The primary metric
        limit: Maximum number of related metrics to return

    Returns:
        List of related metric names
    """
    return RELATED_METRICS.get(metric, [])[:limit]


def get_context_metrics(metric: str, limit: int = 2) -> list:
    """
    Get context metrics for the outer ring.

    Args:
        metric: The primary metric
        limit: Maximum number of context metrics to return

    Returns:
        List of context metric names
    """
    return CONTEXT_METRICS.get(metric, [])[:limit]
