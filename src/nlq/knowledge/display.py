"""
Display names and domain mappings for Galaxy visualization.

DISPLAY_NAMES: Human-readable labels for metrics
METRIC_DOMAINS: Domain classification for circle colors
"""

from src.nlq.models.response import Domain

# Human-readable display names
DISPLAY_NAMES = {
    # P&L
    "revenue": "Revenue",
    "net_income": "Net Income",
    "operating_profit": "Operating Profit",
    "gross_profit": "Gross Profit",
    "cogs": "COGS",
    "sga": "SG&A",
    "selling_expenses": "Selling Expenses",
    "g_and_a_expenses": "G&A Expenses",

    # Margins
    "gross_margin_pct": "Gross Margin",
    "operating_margin_pct": "Operating Margin",
    "net_income_pct": "Net Margin",

    # Growth
    "bookings": "Bookings",
    "sales_pipeline": "Sales Pipeline",
    "expansion_revenue": "Expansion Revenue",
    "revenue_churn": "Revenue Churn",
    "yoy_growth": "YoY Growth",

    # Balance Sheet - Assets
    "cash": "Cash",
    "ar": "Accounts Receivable",
    "deferred_revenue": "Deferred Revenue",
    "current_assets": "Current Assets",
    "total_assets": "Total Assets",
    "ppe": "PP&E",
    "intangibles": "Intangible Assets",
    "inventory": "Inventory",
    "goodwill": "Goodwill",

    # Balance Sheet - Liabilities
    "ap": "Accounts Payable",
    "current_liabilities": "Current Liabilities",
    "total_liabilities": "Total Liabilities",
    "long_term_debt": "Long-term Debt",

    # Balance Sheet - Equity
    "stockholders_equity": "Stockholders' Equity",
    "retained_earnings": "Retained Earnings",

    # Ratios
    "dso": "Days Sales Outstanding",
    "dpo": "Days Payables Outstanding",
    "working_capital": "Working Capital",

    # Other
    "depreciation": "Depreciation",
    "amortization": "Amortization",
    "capex": "CapEx",
    "tax_expense": "Tax Expense",

    # Special
    "not_applicable": "N/A",
}

# Domain classification for circle colors
# Finance = Blue, Growth = Pink, Ops = Green, Product = Purple
METRIC_DOMAINS = {
    # Finance (Blue) - Core financials
    "revenue": Domain.FINANCE,
    "net_income": Domain.FINANCE,
    "operating_profit": Domain.FINANCE,
    "gross_profit": Domain.FINANCE,
    "cogs": Domain.FINANCE,
    "sga": Domain.FINANCE,
    "selling_expenses": Domain.FINANCE,
    "g_and_a_expenses": Domain.FINANCE,
    "gross_margin_pct": Domain.FINANCE,
    "operating_margin_pct": Domain.FINANCE,
    "net_income_pct": Domain.FINANCE,
    "cash": Domain.FINANCE,
    "ar": Domain.FINANCE,
    "ap": Domain.FINANCE,
    "deferred_revenue": Domain.FINANCE,
    "current_assets": Domain.FINANCE,
    "current_liabilities": Domain.FINANCE,
    "total_assets": Domain.FINANCE,
    "total_liabilities": Domain.FINANCE,
    "stockholders_equity": Domain.FINANCE,
    "retained_earnings": Domain.FINANCE,
    "ppe": Domain.FINANCE,
    "intangibles": Domain.FINANCE,
    "long_term_debt": Domain.FINANCE,
    "tax_expense": Domain.FINANCE,
    "depreciation": Domain.FINANCE,
    "amortization": Domain.FINANCE,
    "capex": Domain.FINANCE,

    # Growth (Pink) - Sales & growth metrics
    "bookings": Domain.GROWTH,
    "sales_pipeline": Domain.GROWTH,
    "expansion_revenue": Domain.GROWTH,
    "revenue_churn": Domain.GROWTH,
    "yoy_growth": Domain.GROWTH,

    # Ops (Green) - Operational metrics
    "dso": Domain.OPS,
    "dpo": Domain.OPS,
    "working_capital": Domain.OPS,
    "inventory": Domain.OPS,

    # Product (Purple) - Product metrics
    # (Currently not used in financial data, placeholder for future)
}

# Default domain for unknown metrics
DEFAULT_DOMAIN = Domain.FINANCE


def get_display_name(metric: str) -> str:
    """
    Get human-readable display name for a metric.

    Args:
        metric: The canonical metric name

    Returns:
        Human-readable display name
    """
    return DISPLAY_NAMES.get(metric, metric.replace("_", " ").title())


def get_domain(metric: str) -> Domain:
    """
    Get domain classification for a metric.

    Args:
        metric: The canonical metric name

    Returns:
        Domain enum value
    """
    return METRIC_DOMAINS.get(metric, DEFAULT_DOMAIN)
