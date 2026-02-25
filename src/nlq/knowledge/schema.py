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

    # EBITDA
    "ebitda": MetricDefinition(
        name="ebitda",
        display_name="EBITDA",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Earnings before interest, taxes, depreciation and amortization"
    ),
    "ebitda_margin_pct": MetricDefinition(
        name="ebitda_margin_pct",
        display_name="EBITDA Margin %",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="EBITDA as percentage of revenue"
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

    # ===== CRO METRICS (Growth Domain) =====

    # Revenue & Bookings
    "arr": MetricDefinition(
        name="arr",
        display_name="ARR",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Annual Recurring Revenue"
    ),
    "new_logo_revenue": MetricDefinition(
        name="new_logo_revenue",
        display_name="New Logo Revenue",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Revenue from new customers"
    ),
    "expansion_revenue": MetricDefinition(
        name="expansion_revenue",
        display_name="Expansion Revenue",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Revenue from upsells and cross-sells"
    ),
    "renewal_revenue": MetricDefinition(
        name="renewal_revenue",
        display_name="Renewal Revenue",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Revenue from contract renewals"
    ),

    # Pipeline & Conversion
    "pipeline": MetricDefinition(
        name="pipeline",
        display_name="Sales Pipeline",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Total pipeline value"
    ),
    "qualified_pipeline": MetricDefinition(
        name="qualified_pipeline",
        display_name="Qualified Pipeline",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Pipeline that meets qualification criteria"
    ),
    "win_rate_pct": MetricDefinition(
        name="win_rate_pct",
        display_name="Win Rate",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Percentage of opportunities won"
    ),
    "sales_cycle_days": MetricDefinition(
        name="sales_cycle_days",
        display_name="Sales Cycle",
        metric_type=MetricType.COUNT,
        unit="days",
        description="Average days to close a deal"
    ),
    "avg_deal_size": MetricDefinition(
        name="avg_deal_size",
        display_name="Average Deal Size",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Average contract value"
    ),

    # Churn & Retention
    "gross_churn_pct": MetricDefinition(
        name="gross_churn_pct",
        display_name="Gross Revenue Churn",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Revenue lost from churned customers"
    ),
    "nrr": MetricDefinition(
        name="nrr",
        display_name="Net Revenue Retention",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="NRR - revenue retention including expansion"
    ),
    "logo_churn_pct": MetricDefinition(
        name="logo_churn_pct",
        display_name="Logo Churn",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Percentage of customers lost"
    ),
    "customer_count": MetricDefinition(
        name="customer_count",
        display_name="Customer Count",
        metric_type=MetricType.COUNT,
        unit="customers",
        description="Total number of customers"
    ),

    # Quota & Attainment
    "sales_quota": MetricDefinition(
        name="sales_quota",
        display_name="Sales Quota",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Total sales quota"
    ),
    "quota_attainment_pct": MetricDefinition(
        name="quota_attainment_pct",
        display_name="Quota Attainment",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Percentage of quota achieved"
    ),
    "reps_at_quota_pct": MetricDefinition(
        name="reps_at_quota_pct",
        display_name="Reps at Quota %",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Percentage of reps hitting quota"
    ),
    "sales_headcount": MetricDefinition(
        name="sales_headcount",
        display_name="Sales Headcount",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of sales reps"
    ),
    "new_logos": MetricDefinition(
        name="new_logos",
        display_name="New Logos",
        metric_type=MetricType.COUNT,
        unit="customers",
        description="New customer logos added"
    ),

    # ===== COO METRICS (Operations Domain) =====

    # Headcount & Efficiency
    "headcount": MetricDefinition(
        name="headcount",
        display_name="Total Headcount",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Total employee count"
    ),
    "revenue_per_employee": MetricDefinition(
        name="revenue_per_employee",
        display_name="Revenue per Employee",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Revenue divided by headcount"
    ),
    "cost_per_employee": MetricDefinition(
        name="cost_per_employee",
        display_name="Cost per Employee",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Total cost divided by headcount"
    ),
    "employee_growth_rate": MetricDefinition(
        name="employee_growth_rate",
        display_name="Employee Growth Rate",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Year-over-year headcount growth"
    ),

    # Headcount by Function
    "engineering_headcount": MetricDefinition(
        name="engineering_headcount",
        display_name="Engineering Headcount",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of engineers"
    ),
    "product_headcount": MetricDefinition(
        name="product_headcount",
        display_name="Product Headcount",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of product team members"
    ),
    "marketing_headcount": MetricDefinition(
        name="marketing_headcount",
        display_name="Marketing Headcount",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of marketing team members"
    ),
    "cs_headcount": MetricDefinition(
        name="cs_headcount",
        display_name="Customer Success Headcount",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of CS team members"
    ),
    "ga_headcount": MetricDefinition(
        name="ga_headcount",
        display_name="G&A Headcount",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of G&A team members"
    ),
    "hires": MetricDefinition(
        name="hires",
        display_name="New Hires",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of new hires"
    ),
    "attrition": MetricDefinition(
        name="attrition",
        display_name="Attrition",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of employees who left"
    ),
    "attrition_rate_pct": MetricDefinition(
        name="attrition_rate_pct",
        display_name="Attrition Rate",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Percentage of employees who left"
    ),

    # Operational Efficiency
    "magic_number": MetricDefinition(
        name="magic_number",
        display_name="Magic Number",
        metric_type=MetricType.RATIO,
        unit="x",
        description="Sales efficiency ratio"
    ),
    "cac_payback_months": MetricDefinition(
        name="cac_payback_months",
        display_name="CAC Payback",
        metric_type=MetricType.COUNT,
        unit="months",
        description="Months to recover customer acquisition cost"
    ),
    "ltv_cac": MetricDefinition(
        name="ltv_cac",
        display_name="LTV/CAC",
        metric_type=MetricType.RATIO,
        unit="x",
        description="Customer lifetime value to CAC ratio"
    ),
    "burn_multiple": MetricDefinition(
        name="burn_multiple",
        display_name="Burn Multiple",
        metric_type=MetricType.RATIO,
        unit="x",
        description="Cash burned per dollar of ARR added"
    ),

    # Service Delivery
    "implementation_days": MetricDefinition(
        name="implementation_days",
        display_name="Implementation Time",
        metric_type=MetricType.COUNT,
        unit="days",
        description="Days to implement new customer"
    ),
    "time_to_value_days": MetricDefinition(
        name="time_to_value_days",
        display_name="Time to Value",
        metric_type=MetricType.COUNT,
        unit="days",
        description="Days for customer to see value"
    ),
    "support_tickets": MetricDefinition(
        name="support_tickets",
        display_name="Support Tickets",
        metric_type=MetricType.COUNT,
        unit="tickets",
        description="Number of support tickets"
    ),
    "first_response_hours": MetricDefinition(
        name="first_response_hours",
        display_name="First Response Time",
        metric_type=MetricType.COUNT,
        unit="hours",
        description="Hours to first support response"
    ),
    "resolution_hours": MetricDefinition(
        name="resolution_hours",
        display_name="Resolution Time",
        metric_type=MetricType.COUNT,
        unit="hours",
        description="Hours to resolve support ticket"
    ),
    "csat": MetricDefinition(
        name="csat",
        display_name="CSAT Score",
        metric_type=MetricType.RATIO,
        unit="score",
        description="Customer satisfaction score (1-5)"
    ),
    "nps": MetricDefinition(
        name="nps",
        display_name="NPS",
        metric_type=MetricType.COUNT,
        unit="score",
        description="Net Promoter Score"
    ),

    # Utilization
    "ps_utilization": MetricDefinition(
        name="ps_utilization",
        display_name="PS Utilization",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Professional services utilization"
    ),
    "engineering_utilization": MetricDefinition(
        name="engineering_utilization",
        display_name="Engineering Utilization",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Engineering team utilization"
    ),
    "support_utilization": MetricDefinition(
        name="support_utilization",
        display_name="Support Utilization",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Support team utilization"
    ),

    # ===== CTO METRICS (Product/Tech Domain) =====

    # Product & Engineering
    "features_shipped": MetricDefinition(
        name="features_shipped",
        display_name="Features Shipped",
        metric_type=MetricType.COUNT,
        unit="features",
        description="Number of features released"
    ),
    "story_points": MetricDefinition(
        name="story_points",
        display_name="Story Points",
        metric_type=MetricType.COUNT,
        unit="points",
        description="Total story points completed"
    ),
    "sprint_velocity": MetricDefinition(
        name="sprint_velocity",
        display_name="Sprint Velocity",
        metric_type=MetricType.COUNT,
        unit="points",
        description="Average points per sprint"
    ),

    # Platform Reliability
    "uptime_pct": MetricDefinition(
        name="uptime_pct",
        display_name="Uptime",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Platform availability percentage"
    ),
    "downtime_hours": MetricDefinition(
        name="downtime_hours",
        display_name="Downtime",
        metric_type=MetricType.COUNT,
        unit="hours",
        description="Total downtime hours"
    ),
    "p1_incidents": MetricDefinition(
        name="p1_incidents",
        display_name="P1 Incidents",
        metric_type=MetricType.COUNT,
        unit="incidents",
        description="Critical severity incidents"
    ),
    "p2_incidents": MetricDefinition(
        name="p2_incidents",
        display_name="P2 Incidents",
        metric_type=MetricType.COUNT,
        unit="incidents",
        description="High severity incidents"
    ),
    "mttr_p1_hours": MetricDefinition(
        name="mttr_p1_hours",
        display_name="MTTR (P1)",
        metric_type=MetricType.COUNT,
        unit="hours",
        description="Mean time to recover from P1"
    ),
    "mttr_p2_hours": MetricDefinition(
        name="mttr_p2_hours",
        display_name="MTTR (P2)",
        metric_type=MetricType.COUNT,
        unit="hours",
        description="Mean time to recover from P2"
    ),

    # Code Quality & Tech Debt
    "tech_debt_pct": MetricDefinition(
        name="tech_debt_pct",
        display_name="Tech Debt Score",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Technical debt percentage"
    ),
    "code_coverage_pct": MetricDefinition(
        name="code_coverage_pct",
        display_name="Code Coverage",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Test code coverage percentage"
    ),
    "bug_escape_rate": MetricDefinition(
        name="bug_escape_rate",
        display_name="Bug Escape Rate",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Bugs found in production"
    ),
    "critical_bugs": MetricDefinition(
        name="critical_bugs",
        display_name="Critical Bugs",
        metric_type=MetricType.COUNT,
        unit="bugs",
        description="Open critical bugs"
    ),
    "security_vulns": MetricDefinition(
        name="security_vulns",
        display_name="Security Vulnerabilities",
        metric_type=MetricType.COUNT,
        unit="vulnerabilities",
        description="Known security vulnerabilities"
    ),

    # Deployment & DevOps
    "deploys_per_week": MetricDefinition(
        name="deploys_per_week",
        display_name="Deploys per Week",
        metric_type=MetricType.COUNT,
        unit="deploys",
        description="Deployment frequency"
    ),
    "deployment_success_pct": MetricDefinition(
        name="deployment_success_pct",
        display_name="Deployment Success Rate",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Successful deployment percentage"
    ),
    "lead_time_days": MetricDefinition(
        name="lead_time_days",
        display_name="Lead Time",
        metric_type=MetricType.COUNT,
        unit="days",
        description="Days from commit to production"
    ),
    "change_failure_rate": MetricDefinition(
        name="change_failure_rate",
        display_name="Change Failure Rate",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Percentage of changes causing issues"
    ),

    # Infrastructure & Costs
    "cloud_spend": MetricDefinition(
        name="cloud_spend",
        display_name="Cloud Spend",
        metric_type=MetricType.CURRENCY,
        unit="USD millions",
        description="Cloud infrastructure spend"
    ),
    "cloud_spend_pct_revenue": MetricDefinition(
        name="cloud_spend_pct_revenue",
        display_name="Cloud Spend % Revenue",
        metric_type=MetricType.PERCENTAGE,
        unit="%",
        description="Cloud spend as percentage of revenue"
    ),
    "cost_per_transaction": MetricDefinition(
        name="cost_per_transaction",
        display_name="Cost per Transaction",
        metric_type=MetricType.CURRENCY,
        unit="USD",
        description="Infrastructure cost per transaction"
    ),
    "api_requests_millions": MetricDefinition(
        name="api_requests_millions",
        display_name="API Requests",
        metric_type=MetricType.COUNT,
        unit="millions/month",
        description="Monthly API request volume"
    ),

    # CHRO (People) metrics
    "open_roles": MetricDefinition(
        name="open_roles",
        display_name="Open Roles",
        metric_type=MetricType.COUNT,
        unit="people",
        description="Number of open job requisitions"
    ),
    "time_to_fill_days": MetricDefinition(
        name="time_to_fill_days",
        display_name="Time to Fill",
        metric_type=MetricType.COUNT,
        unit="days",
        description="Average days to fill a position"
    ),
    "engagement_score": MetricDefinition(
        name="engagement_score",
        display_name="Engagement Score",
        metric_type=MetricType.RATIO,
        unit="score",
        description="Employee engagement score"
    ),
}


# Persona to domain mapping
PERSONA_DOMAINS = {
    "CFO": "FINANCE",
    "CRO": "GROWTH",
    "COO": "OPS",
    "CTO": "PRODUCT",
    "CHRO": "PEOPLE",
}


# Metric to persona mapping
METRIC_PERSONAS = {
    # CFO metrics
    "revenue": "CFO", "net_income": "CFO", "gross_margin_pct": "CFO",
    "operating_margin_pct": "CFO", "cogs": "CFO", "sga": "CFO",
    "cash": "CFO", "ar": "CFO", "ap": "CFO", "gross_profit": "CFO",
    "operating_profit": "CFO", "net_income_pct": "CFO",
    "selling_expenses": "CFO", "g_and_a_expenses": "CFO",
    "deferred_revenue": "CFO", "unbilled_revenue": "CFO",
    "retained_earnings": "CFO", "stockholders_equity": "CFO",
    "total_current_assets": "CFO", "current_liabilities": "CFO", "ppe": "CFO",
    "ebitda": "CFO", "ebitda_margin_pct": "CFO",

    # CRO metrics
    "bookings": "CRO", "arr": "CRO", "pipeline": "CRO",
    "win_rate_pct": "CRO", "nrr": "CRO", "gross_churn_pct": "CRO",
    "new_logo_revenue": "CRO", "expansion_revenue": "CRO",
    "renewal_revenue": "CRO", "customer_count": "CRO",
    "quota_attainment_pct": "CRO", "sales_quota": "CRO",
    "reps_at_quota_pct": "CRO", "sales_headcount": "CRO",
    "qualified_pipeline": "CRO", "sales_cycle_days": "CRO",
    "avg_deal_size": "CRO", "logo_churn_pct": "CRO", "new_logos": "CRO",

    # COO metrics
    "headcount": "COO", "revenue_per_employee": "COO",
    "magic_number": "COO", "cac_payback_months": "COO", "ltv_cac": "COO",
    "nps": "COO", "csat": "COO", "ps_utilization": "COO",
    "implementation_days": "COO", "attrition": "COO", "attrition_rate_pct": "COO",
    "cost_per_employee": "COO", "employee_growth_rate": "COO",
    "engineering_headcount": "COO", "product_headcount": "COO",
    "marketing_headcount": "COO", "cs_headcount": "COO", "ga_headcount": "COO",
    "hires": "COO", "burn_multiple": "COO", "time_to_value_days": "COO",
    "support_tickets": "COO", "first_response_hours": "COO",
    "resolution_hours": "COO", "engineering_utilization": "COO",
    "support_utilization": "COO",

    # CTO metrics
    "uptime_pct": "CTO", "p1_incidents": "CTO", "mttr_p1_hours": "CTO",
    "sprint_velocity": "CTO", "features_shipped": "CTO",
    "tech_debt_pct": "CTO", "code_coverage_pct": "CTO",
    "deploys_per_week": "CTO", "cloud_spend": "CTO",
    "p2_incidents": "CTO", "mttr_p2_hours": "CTO", "downtime_hours": "CTO",
    "story_points": "CTO", "bug_escape_rate": "CTO", "critical_bugs": "CTO",
    "security_vulns": "CTO", "deployment_success_pct": "CTO",
    "lead_time_days": "CTO", "change_failure_rate": "CTO",
    "cloud_spend_pct_revenue": "CTO", "cost_per_transaction": "CTO",
    "api_requests_millions": "CTO",

    # CHRO (People) metrics - HR and workforce
    "total_headcount": "CHRO", "turnover_rate": "CHRO",
    "voluntary_turnover": "CHRO", "involuntary_turnover": "CHRO",
    "time_to_hire": "CHRO", "offer_acceptance_rate_pct": "CHRO",
    "employee_satisfaction": "CHRO", "engagement_score": "CHRO",
    "training_hours": "CHRO", "promotion_rate_pct": "CHRO",
    "diversity_pct": "CHRO", "gender_ratio": "CHRO",
    "open_roles": "CHRO", "open_positions": "CHRO", "recruiting_pipeline": "CHRO",
    "compensation_ratio": "CHRO", "benefits_cost": "CHRO",
}


def get_metric_persona(metric_name: str) -> str:
    """Get the persona for a metric."""
    return METRIC_PERSONAS.get(metric_name, "CFO")


def get_metric_unit(metric_name: str) -> str:
    """Get the unit for a metric."""
    if metric_name in FINANCIAL_SCHEMA:
        return FINANCIAL_SCHEMA[metric_name].unit
    return "unknown"


# Display unit → DCL canonical unit mapping
_UNIT_TO_CANONICAL = {
    "%": "pct",
    "USD millions": "usd_millions",
    "USD": "usd",
    "millions/month": "usd_millions",
    "people": "count",
    "customers": "count",
    "tickets": "count",
    "bugs": "count",
    "vulnerabilities": "count",
    "incidents": "count",
    "deploys": "count",
    "features": "count",
    "points": "count",
    "days": "days",
    "hours": "hours",
    "months": "months",
    "score": "score",
    "x": "ratio",
}


def get_canonical_unit(metric_name: str) -> str:
    """Get the DCL canonical unit for a metric (pct, usd_millions, count, ratio, etc.)."""
    display_unit = get_metric_unit(metric_name)
    return _UNIT_TO_CANONICAL.get(display_unit, display_unit)


def get_metric_type(metric_name: str) -> Optional[MetricType]:
    """Get the type for a metric."""
    if metric_name in FINANCIAL_SCHEMA:
        return FINANCIAL_SCHEMA[metric_name].metric_type
    return None


def get_all_metrics() -> List[str]:
    """Get list of all defined metrics."""
    return list(FINANCIAL_SCHEMA.keys())
