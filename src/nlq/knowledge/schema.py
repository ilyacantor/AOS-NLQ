"""
Financial data schema definitions for AOS-NLQ.

Defines the structure of financial data including:
- Available metrics and their properties
- Data types and units
- Validation rules

This schema is used to validate queries and provide metadata.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MetricType(str, Enum):
    """Types of financial metrics."""
    CURRENCY = "currency"       # Dollar amounts (revenue, profit)
    PERCENTAGE = "percentage"   # Percentages (margins)
    COUNT = "count"            # Counts (headcount)
    RATIO = "ratio"            # Ratios


class MetricDefinition(BaseModel):
    """Definition of a financial metric."""

    name: str = Field(..., description="Canonical metric name")
    display_name: str = Field(..., description="Human-readable name")
    metric_type: MetricType = Field(..., description="Type of metric")
    unit: str = Field(..., description="Unit of measurement")
    description: Optional[str] = Field(None, description="Metric description")
    is_derived: bool = Field(default=False, description="Whether computed from other metrics")


# Core financial metrics schema
FINANCIAL_SCHEMA: Dict[str, MetricDefinition] = {
    # Income Statement - Revenue
    "revenue": MetricDefinition(
        name="revenue",
        display_name="Revenue",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Total revenue from all sources"
    ),
    "bookings": MetricDefinition(
        name="bookings",
        display_name="Bookings",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="New contract bookings"
    ),

    # Income Statement - Costs
    "cogs": MetricDefinition(
        name="cogs",
        display_name="Cost of Goods Sold",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Direct costs of producing goods/services"
    ),
    "gross_profit": MetricDefinition(
        name="gross_profit",
        display_name="Gross Profit",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Revenue minus COGS",
        is_derived=True
    ),
    "gross_margin_pct": MetricDefinition(
        name="gross_margin_pct",
        display_name="Gross Margin %",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Gross profit as percentage of revenue",
        is_derived=True
    ),

    # Income Statement - Operating Expenses
    "selling_expenses": MetricDefinition(
        name="selling_expenses",
        display_name="Selling Expenses",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Sales and marketing expenses"
    ),
    "g_and_a_expenses": MetricDefinition(
        name="g_and_a_expenses",
        display_name="G&A Expenses",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="General and administrative expenses"
    ),
    "sga": MetricDefinition(
        name="sga",
        display_name="SG&A",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Selling, general & administrative expenses",
        is_derived=True
    ),

    # Income Statement - Profitability
    "operating_profit": MetricDefinition(
        name="operating_profit",
        display_name="Operating Profit",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Gross profit minus operating expenses",
        is_derived=True
    ),
    "operating_margin_pct": MetricDefinition(
        name="operating_margin_pct",
        display_name="Operating Margin %",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Operating profit as percentage of revenue",
        is_derived=True
    ),
    "net_income": MetricDefinition(
        name="net_income",
        display_name="Net Income",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Bottom line profit"
    ),
    "net_income_pct": MetricDefinition(
        name="net_income_pct",
        display_name="Net Income %",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Net income as percentage of revenue",
        is_derived=True
    ),

    # Balance Sheet - Assets
    "cash": MetricDefinition(
        name="cash",
        display_name="Cash",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Cash and cash equivalents"
    ),
    "ar": MetricDefinition(
        name="ar",
        display_name="Accounts Receivable",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Money owed by customers"
    ),
    "ppe": MetricDefinition(
        name="ppe",
        display_name="PP&E",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Property, plant and equipment"
    ),
    "total_current_assets": MetricDefinition(
        name="total_current_assets",
        display_name="Total Current Assets",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Assets convertible to cash within a year"
    ),

    # Balance Sheet - Liabilities
    "ap": MetricDefinition(
        name="ap",
        display_name="Accounts Payable",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Money owed to suppliers"
    ),
    "current_liabilities": MetricDefinition(
        name="current_liabilities",
        display_name="Current Liabilities",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Obligations due within a year"
    ),
    "deferred_revenue": MetricDefinition(
        name="deferred_revenue",
        display_name="Deferred Revenue",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Payments received for future delivery"
    ),

    # Balance Sheet - Equity
    "unbilled_revenue": MetricDefinition(
        name="unbilled_revenue",
        display_name="Unbilled Revenue",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Revenue earned but not yet billed"
    ),
    "retained_earnings": MetricDefinition(
        name="retained_earnings",
        display_name="Retained Earnings",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Accumulated net income not distributed"
    ),
    "stockholders_equity": MetricDefinition(
        name="stockholders_equity",
        display_name="Stockholders' Equity",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Total shareholder equity"
    ),
}


def get_metric_unit(metric_name: str) -> str:
    """Get the unit for a metric."""
    if metric_name in FINANCIAL_SCHEMA:
        return FINANCIAL_SCHEMA[metric_name].unit
    return "unknown"


def get_metric_type(metric_name: str) -> Optional[MetricType]:
    """Get the type for a metric."""
    if metric_name in FINANCIAL_SCHEMA:
        return FINANCIAL_SCHEMA[metric_name].metric_type
    return None


def get_all_metrics() -> List[str]:
    """Get list of all defined metrics."""
    return list(FINANCIAL_SCHEMA.keys())
