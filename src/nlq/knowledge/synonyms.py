"""
Synonym mappings for metrics and periods.

CRITICAL: Users say "top line", "turnover", "sales" meaning "revenue".
All metric references must be normalized before processing.

This module provides:
- METRIC_SYNONYMS: Maps synonyms to canonical metric names
- PERIOD_SYNONYMS: Maps period variations to canonical forms
- normalize_metric(): Convert any synonym to canonical name
- normalize_period(): Convert any period reference to canonical form
"""

from typing import Dict, List, Optional


# Maps canonical metric name -> list of synonyms
METRIC_SYNONYMS: Dict[str, List[str]] = {
    # Revenue/Sales
    "revenue": [
        "sales",
        "top line",
        "top-line",
        "topline",
        "turnover",
        "total revenue",
        "net revenue",
        "gross revenue",
    ],

    # Cost of Goods Sold
    "cogs": [
        "cost of goods sold",
        "cost of sales",
        "cost of revenue",
        "cos",
        "direct costs",
        "product costs",
    ],

    # Gross Profit
    "gross_profit": [
        "gross income",
        "gross margin dollars",
        "gross profit dollars",
    ],

    # Gross Margin Percentage
    "gross_margin_pct": [
        "gross margin",
        "gross margin %",
        "gross margin percent",
        "gm%",
        "gm pct",
    ],

    # Operating Expenses (SG&A)
    "sga": [
        "sg&a",
        "s g & a",
        "sg and a",
        "selling general and administrative",
        "operating expenses",
        "opex",
        "operating costs",
    ],

    # Selling Expenses
    "selling_expenses": [
        "sales expenses",
        "selling costs",
        "sales and marketing",
        "s&m",
    ],

    # G&A Expenses
    "g_and_a_expenses": [
        "g&a",
        "general and administrative",
        "administrative expenses",
        "admin expenses",
    ],

    # Operating Profit
    "operating_profit": [
        "operating income",
        "ebit",
        "op profit",
        "operating earnings",
        "income from operations",
    ],

    # Operating Margin Percentage
    "operating_margin_pct": [
        "operating margin",
        "operating margin %",
        "operating margin percent",
        "op margin",
        "ebit margin",
    ],

    # Net Income
    "net_income": [
        "profit",
        "net profit",
        "bottom line",
        "bottom-line",
        "bottomline",
        "earnings",
        "net earnings",
        "income",
    ],

    # Net Income Percentage
    "net_income_pct": [
        "net margin",
        "net margin %",
        "profit margin",
        "net profit margin",
        "net income margin",
    ],

    # Bookings
    "bookings": [
        "new bookings",
        "orders",
        "new orders",
        "contract value",
        "tcv",
        "total contract value",
    ],

    # Cash
    "cash": [
        "cash balance",
        "cash on hand",
        "cash and equivalents",
        "cash & equivalents",
    ],

    # Accounts Receivable
    "ar": [
        "accounts receivable",
        "receivables",
        "trade receivables",
        "a/r",
    ],

    # Accounts Payable
    "ap": [
        "accounts payable",
        "payables",
        "trade payables",
        "a/p",
    ],

    # Property, Plant & Equipment
    "ppe": [
        "property plant and equipment",
        "fixed assets",
        "pp&e",
        "capital assets",
    ],

    # Deferred Revenue
    "deferred_revenue": [
        "deferred rev",
        "unearned revenue",
        "contract liability",
        "contract liabilities",
    ],

    # Unbilled Revenue
    "unbilled_revenue": [
        "unbilled rev",
        "unbilled receivables",
        "contract asset",
        "contract assets",
    ],

    # Current Assets
    "total_current_assets": [
        "current assets",
        "total current assets",
        "working capital assets",
    ],

    # Current Liabilities
    "current_liabilities": [
        "total current liabilities",
        "short-term liabilities",
        "short term liabilities",
    ],

    # Retained Earnings
    "retained_earnings": [
        "accumulated earnings",
        "retained profits",
    ],

    # Stockholders Equity
    "stockholders_equity": [
        "shareholders equity",
        "shareholder equity",
        "equity",
        "total equity",
        "book value",
    ],

    # ARR (Annual Recurring Revenue)
    "arr": [
        "annual recurring revenue",
        "recurring revenue",
        "mrr",  # Often used interchangeably
    ],

    # Quota & Sales Performance
    "quota_attainment": [
        "quota",
        "quota attainment",
        "quota performance",
        "sales attainment",
        "attainment",
    ],
    "sales_quota": [
        "sales target",
        "target",
        "sales goal",
    ],
    "reps_at_quota_pct": [
        "reps at quota",
        "reps hitting quota",
        "quota reps",
    ],

    # Pipeline
    "pipeline": [
        "sales pipeline",
        "pipe",
        "opportunities",
        "deals",
    ],
    "qualified_pipeline": [
        "qualified pipe",
        "qualified deals",
        "qualified opportunities",
    ],

    # Win Rate
    "win_rate": [
        "win rate",
        "close rate",
        "conversion rate",
        "win pct",
    ],

    # Sales Cycle
    "sales_cycle_days": [
        "sales cycle",
        "sales_cycle",
        "cycle time",
        "deal cycle",
        "time to close",
    ],

    # Churn
    "gross_churn_pct": [
        "churn",
        "churn rate",
        "customer churn",
        "revenue churn",
        "gross churn",
    ],
    "logo_churn_pct": [
        "logo churn",
        "customer logo churn",
        "account churn",
    ],

    # NRR (Net Revenue Retention)
    "nrr": [
        "net revenue retention",
        "net retention",
        "dollar retention",
        "ndr",
        "net dollar retention",
    ],

    # Customer metrics
    "customer_count": [
        "customers",
        "customer base",
        "total customers",
        "client count",
        "clients",
    ],
    "new_logos": [
        "new customers",
        "new clients",
        "new accounts",
        "logos",
    ],

    # Customer Satisfaction
    "csat": [
        "customer satisfaction",
        "satisfaction",
        "satisfaction score",
    ],
    "nps": [
        "net promoter score",
        "promoter score",
    ],

    # Headcount
    "headcount": [
        "employees",
        "employee count",
        "head count",
        "hc",
        "fte",
        "full time employees",
    ],
    "attrition_rate": [
        "attrition",
        "turnover",
        "turnover rate",
        "employee turnover",
    ],

    # LTV/CAC
    "ltv_cac": [
        "ltv cac",
        "ltv/cac",
        "ltv to cac",
        "lifetime value to cac",
    ],
    "cac_payback_months": [
        "cac payback",
        "payback period",
        "cac payback period",
    ],

    # Magic Number
    "magic_number": [
        "magic number",
        "sales efficiency",
    ],

    # Burn Multiple
    "burn_multiple": [
        "burn multiple",
        "cash efficiency",
    ],

    # Tech/Engineering
    "uptime_pct": [
        "uptime",
        "availability",
        "system uptime",
    ],
    "tech_debt_pct": [
        "tech debt",
        "technical debt",
    ],
    "deploys_per_week": [
        "deploys",
        "deployments",
        "releases",
    ],
    "sprint_velocity": [
        "velocity",
        "sprint velocity",
        "team velocity",
    ],
}

# Build reverse lookup for faster normalization
_METRIC_REVERSE_LOOKUP: Dict[str, str] = {}
for canonical, synonyms in METRIC_SYNONYMS.items():
    _METRIC_REVERSE_LOOKUP[canonical.lower()] = canonical
    for syn in synonyms:
        _METRIC_REVERSE_LOOKUP[syn.lower()] = canonical


# Maps canonical period reference -> list of synonyms
PERIOD_SYNONYMS: Dict[str, List[str]] = {
    "last_year": [
        "prior year",
        "previous year",
        "year ago",
        "ly",
        "last fiscal year",
        "prior fiscal year",
    ],
    "this_year": [
        "current year",
        "cy",
        "this fiscal year",
        "current fiscal year",
        "ytd",  # Year to date often means this year
    ],
    "last_quarter": [
        "prior quarter",
        "previous quarter",
        "quarter ago",
        "lq",
        "last q",
    ],
    "this_quarter": [
        "current quarter",
        "cq",
        "this q",
    ],
}

# Build reverse lookup for periods
_PERIOD_REVERSE_LOOKUP: Dict[str, str] = {}
for canonical, synonyms in PERIOD_SYNONYMS.items():
    _PERIOD_REVERSE_LOOKUP[canonical.lower().replace("_", " ")] = canonical
    _PERIOD_REVERSE_LOOKUP[canonical.lower()] = canonical
    for syn in synonyms:
        _PERIOD_REVERSE_LOOKUP[syn.lower()] = canonical


def normalize_metric(raw_metric: str) -> str:
    """
    Convert a metric synonym to its canonical name.

    Args:
        raw_metric: User-provided metric name (may be synonym)

    Returns:
        Canonical metric name, or original if no match found

    Examples:
        normalize_metric("sales") -> "revenue"
        normalize_metric("top line") -> "revenue"
        normalize_metric("bottom line") -> "net_income"
        normalize_metric("EBIT") -> "operating_profit"
    """
    if not raw_metric:
        return raw_metric

    key = raw_metric.lower().strip()
    return _METRIC_REVERSE_LOOKUP.get(key, raw_metric.lower().replace(" ", "_"))


def normalize_period(raw_period: str) -> str:
    """
    Convert a period synonym to its canonical form.

    Args:
        raw_period: User-provided period reference

    Returns:
        Canonical period reference, or original if no match

    Examples:
        normalize_period("prior year") -> "last_year"
        normalize_period("current quarter") -> "this_quarter"
    """
    if not raw_period:
        return raw_period

    key = raw_period.lower().strip()
    return _PERIOD_REVERSE_LOOKUP.get(key, raw_period.lower().replace(" ", "_"))


def get_all_metric_names() -> List[str]:
    """Get list of all recognized metric names (canonical + synonyms)."""
    return list(_METRIC_REVERSE_LOOKUP.keys())


def get_canonical_metrics() -> List[str]:
    """Get list of canonical metric names only."""
    return list(METRIC_SYNONYMS.keys())
