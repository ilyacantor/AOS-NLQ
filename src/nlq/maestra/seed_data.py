"""
Demo seed data for Maestra — Meridian and Cascadia entity profiles.

Used in demo mode when Maestra starts a Convergence engagement.
These provide the intel briefs, pre-populated contour maps,
and engine results so the demo doesn't start from zero.
"""

from __future__ import annotations

from typing import Any

from src.nlq.maestra.types import IntelBrief, IntelSource


def get_meridian_intel() -> IntelBrief:
    """Pre-built intel brief for Meridian Partners."""
    return IntelBrief(
        company_overview=(
            "Meridian Partners is a PE-backed professional services holding company "
            "with $5B in annual revenue across 14 legal entities and 3 divisions: "
            "Strategy, Operations, and Technology. Headquartered in Chicago, IL. "
            "Backed by Crestview Capital since 2022."
        ),
        industry="Professional Services / Management Consulting",
        public_structure=[
            "Strategy Division (4 entities)",
            "Operations Division (6 entities)",
            "Technology Division (4 entities, including Apex acquired Q3 2025)",
        ],
        known_systems=[
            "SAP S/4HANA (Primary ERP)",
            "NetSuite (Subsidiary ERP)",
            "Oracle (Apex acquisition — cash basis)",
            "Workday (HCM)",
            "Salesforce (CRM)",
            "ADP (Payroll)",
            "Adaptive Insights (FP&A)",
            "Tableau (BI)",
            "ServiceNow (ITSM)",
            "Concur (Expense)",
            "Jira (Project Mgmt — Shadow IT)",
            "SharePoint (Document Mgmt)",
        ],
        recent_events=[
            "Acquired Apex Consulting Q3 2025 — Oracle ERP integration pending",
            "PE sponsor Crestview Capital evaluating add-on acquisitions",
            "Consolidated P&L takes 3 weeks due to dual-ERP issue (SAP vs Oracle)",
            "VP of Data Jordan Chen hired to lead data transformation initiative",
        ],
        suggested_questions=[
            "How does the Apex Oracle instance map to your SAP chart of accounts?",
            "Which cost centers exist in Oracle but not in SAP?",
            "How do you currently handle the GAAP vs cash basis reconciliation?",
            "Who owns the consolidated P&L close process?",
        ],
        sources=[
            IntelSource(url="https://meridian-partners.com/about", type="WEBSITE"),
            IntelSource(url="https://crestviewcapital.com/portfolio/meridian", type="WEBSITE"),
        ],
    )


def get_cascadia_intel() -> IntelBrief:
    """Pre-built intel brief for Cascadia Advisory."""
    return IntelBrief(
        company_overview=(
            "Cascadia Advisory is a boutique management consulting firm with $1B in "
            "annual revenue, 5 legal entities, and 2 divisions: Advisory and Managed Services. "
            "Headquartered in Seattle, WA. Founded 2015, bootstrapped until Meridian acquisition."
        ),
        industry="Management Consulting / Advisory",
        public_structure=[
            "Advisory Division (3 entities)",
            "Managed Services Division (2 entities)",
        ],
        known_systems=[
            "QuickBooks (ERP — cash basis)",
            "BambooHR (HCM)",
            "HubSpot (CRM)",
            "Gusto (Payroll)",
            "Google Workspace (Productivity)",
            "Asana (Project Mgmt)",
            "Stripe (Payments)",
            "Looker (BI — Shadow IT)",
        ],
        recent_events=[
            "Acquired by Meridian Partners — integration planning phase",
            "Key customer overlap with Meridian in financial services vertical",
            "Revenue concentration risk: top 3 customers = 35% of revenue",
            "Switching from QuickBooks to accrual basis as part of integration",
        ],
        suggested_questions=[
            "How does QuickBooks cash basis map to GAAP accrual?",
            "What is the customer definition in HubSpot vs Meridian's Salesforce?",
            "How do you track project profitability today?",
            "What reporting does your leadership team need monthly?",
        ],
        sources=[
            IntelSource(url="https://cascadia-advisory.com/about", type="WEBSITE"),
        ],
    )


# =============================================================================
# ENGINE DEMO DATA — exact numbers Maestra cites during findings
# =============================================================================


def get_cross_sell_data() -> dict[str, Any]:
    """Cross-sell pipeline results for Meridian × Cascadia."""
    return {
        "success": True,
        "engine": "cross_sell",
        "summary": {
            "total_candidates": 103,
            "total_pipeline_acv": 260_000_000,
            "high_propensity_count": 27,
            "high_propensity_acv": 94_000_000,
            "medium_propensity_count": 41,
            "medium_propensity_acv": 112_000_000,
            "low_propensity_count": 35,
            "low_propensity_acv": 54_000_000,
        },
        "top_candidates": [
            {"account": "Northwind Financial", "current_entity": "Cascadia",
             "cross_sell_from": "Meridian", "service": "Technology Strategy",
             "propensity": 0.94, "estimated_acv": 8_200_000},
            {"account": "BlueRidge Healthcare", "current_entity": "Cascadia",
             "cross_sell_from": "Meridian", "service": "Operations Transformation",
             "propensity": 0.91, "estimated_acv": 6_800_000},
            {"account": "Summit Manufacturing", "current_entity": "Meridian",
             "cross_sell_from": "Cascadia", "service": "Managed IT Services",
             "propensity": 0.89, "estimated_acv": 5_400_000},
            {"account": "Cascade Telecom", "current_entity": "Cascadia",
             "cross_sell_from": "Meridian", "service": "Risk Advisory",
             "propensity": 0.87, "estimated_acv": 4_900_000},
            {"account": "Pacific Retail Group", "current_entity": "Meridian",
             "cross_sell_from": "Cascadia", "service": "Digital Advisory",
             "propensity": 0.85, "estimated_acv": 4_300_000},
            {"account": "Redwood Logistics", "current_entity": "Cascadia",
             "cross_sell_from": "Meridian", "service": "Supply Chain Strategy",
             "propensity": 0.83, "estimated_acv": 3_800_000},
            {"account": "Evergreen Insurance", "current_entity": "Meridian",
             "cross_sell_from": "Cascadia", "service": "Managed Analytics",
             "propensity": 0.81, "estimated_acv": 3_500_000},
            {"account": "Olympus Energy", "current_entity": "Cascadia",
             "cross_sell_from": "Meridian", "service": "Technology Implementation",
             "propensity": 0.79, "estimated_acv": 3_200_000},
            {"account": "Timberline Capital", "current_entity": "Meridian",
             "cross_sell_from": "Cascadia", "service": "CFO Advisory",
             "propensity": 0.77, "estimated_acv": 2_900_000},
            {"account": "Clearwater Systems", "current_entity": "Cascadia",
             "cross_sell_from": "Meridian", "service": "Cybersecurity",
             "propensity": 0.75, "estimated_acv": 2_600_000},
        ],
        "territory_overlap": {
            "shared_prospects": 18,
            "territory_conflicts": 7,
            "expansion_lanes": 12,
        },
        "customer_migration": {
            "at_risk_accounts": 14,
            "at_risk_revenue": 89_000_000,
            "top_3_concentration_pct": 35,
            "retention_priority": [
                {"account": "Northwind Financial", "revenue": 42_000_000,
                 "risk": "high", "reason": "Key relationship holder departing"},
                {"account": "Pacific Retail Group", "revenue": 28_000_000,
                 "risk": "medium", "reason": "Contract renewal in 90 days"},
                {"account": "Cascade Telecom", "revenue": 19_000_000,
                 "risk": "medium", "reason": "Competitor RFP in progress"},
            ],
        },
    }


def get_ebitda_bridge_data() -> dict[str, Any]:
    """EBITDA bridge: reported → adjusted → pro forma."""
    return {
        "success": True,
        "engine": "ebitda_bridge",
        "bridge": {
            "reported_ebitda": 485_000_000,
            "adjustments": [
                {"category": "One-Time Transaction Costs", "amount": 32_000_000,
                 "direction": "add_back", "confidence": "confirmed"},
                {"category": "Non-Recurring Litigation", "amount": 18_000_000,
                 "direction": "add_back", "confidence": "confirmed"},
                {"category": "Management Fee Normalization", "amount": 12_000_000,
                 "direction": "add_back", "confidence": "confirmed"},
                {"category": "Lease Reclassification (IFRS 16)", "amount": -8_000_000,
                 "direction": "deduction", "confidence": "confirmed"},
                {"category": "Cascadia Cash-to-Accrual Adjustment", "amount": 15_000_000,
                 "direction": "add_back", "confidence": "estimated"},
                {"category": "Intercompany Elimination", "amount": -4_000_000,
                 "direction": "deduction", "confidence": "confirmed"},
            ],
            "adjusted_ebitda": 550_000_000,
            "synergies": [
                {"category": "Revenue Synergies (Cross-Sell)", "amount": 38_000_000,
                 "timeline": "Year 2-3", "confidence": "modeled"},
                {"category": "Cost Synergies (Vendor Consolidation)", "amount": 14_000_000,
                 "timeline": "Year 1", "confidence": "identified"},
                {"category": "Cost Synergies (G&A Reduction)", "amount": 8_000_000,
                 "timeline": "Year 1", "confidence": "identified"},
            ],
            "pro_forma_ebitda": 610_000_000,
        },
        "what_if": {
            "conservative": {"ebitda": 565_000_000, "ev": 6_780_000_000},
            "base": {"ebitda": 610_000_000, "ev": 7_320_000_000},
            "aggressive": {"ebitda": 680_000_000, "ev": 8_160_000_000},
            "spread": 1_380_000_000,
        },
    }


def get_entity_overlap_data() -> dict[str, Any]:
    """Entity overlap analysis — customers, vendors, people."""
    return {
        "success": True,
        "engine": "entity_resolution",
        "customer_overlap": {
            "meridian_customers": 847,
            "cascadia_customers": 312,
            "overlapping": 43,
            "overlap_revenue": 156_000_000,
            "unique_to_meridian": 804,
            "unique_to_cascadia": 269,
        },
        "vendor_overlap": {
            "meridian_vendors": 234,
            "cascadia_vendors": 89,
            "overlapping": 31,
            "consolidation_savings": 4_200_000,
            "top_overlapping": [
                {"vendor": "AWS", "meridian_spend": 12_400_000,
                 "cascadia_spend": 3_100_000, "savings": 1_200_000},
                {"vendor": "Salesforce", "meridian_spend": 8_600_000,
                 "cascadia_spend": 0, "savings": 0, "note": "Cascadia uses HubSpot"},
                {"vendor": "Microsoft", "meridian_spend": 6_200_000,
                 "cascadia_spend": 1_800_000, "savings": 800_000},
            ],
        },
        "people_overlap": {
            "meridian_headcount": 4_200,
            "cascadia_headcount": 680,
            "combined": 4_880,
            "by_function": [
                {"function": "Consulting", "meridian": 2_800, "cascadia": 420, "overlap_pct": 0},
                {"function": "Sales", "meridian": 380, "cascadia": 65, "overlap_pct": 12},
                {"function": "G&A", "meridian": 520, "cascadia": 95, "overlap_pct": 35},
                {"function": "Technology", "meridian": 340, "cascadia": 60, "overlap_pct": 18},
                {"function": "HR", "meridian": 160, "cascadia": 40, "overlap_pct": 40},
            ],
        },
    }


def get_cofa_mapping_data() -> dict[str, Any]:
    """COFA conflict mapping between Meridian and Cascadia charts of accounts."""
    return {
        "success": True,
        "engine": "cofa_mapping",
        "conflicts": {
            "total": 8,
            "material": 5,
            "resolved": 0,
            "items": [
                {"dimension": "Revenue Recognition", "meridian": "GAAP accrual (ASC 606)",
                 "cascadia": "Cash basis", "materiality": "critical",
                 "recommendation": "Cascadia adopts Meridian accrual basis"},
                {"dimension": "Cost Center Structure", "meridian": "4-level hierarchy (Division/Dept/CC/Project)",
                 "cascadia": "2-level (Division/Project)", "materiality": "high",
                 "recommendation": "Map Cascadia projects into Meridian CC structure"},
                {"dimension": "Customer Definition", "meridian": "Salesforce Account ID (billing entity)",
                 "cascadia": "HubSpot Company (relationship)", "materiality": "high",
                 "recommendation": "Entity resolution via name + domain matching"},
                {"dimension": "Period Close", "meridian": "15-day close (3 weeks with Apex)",
                 "cascadia": "5-day close", "materiality": "medium",
                 "recommendation": "Cascadia quick-close preserved, Meridian close target: 10 days"},
                {"dimension": "Segment Reporting", "meridian": "3 segments (Strategy/Ops/Tech)",
                 "cascadia": "2 segments (Advisory/Managed Svcs)", "materiality": "high",
                 "recommendation": "Cascadia Advisory → Strategy, Managed Services → Operations"},
                {"dimension": "Expense Classification", "meridian": "GAAP functional classification",
                 "cascadia": "Natural classification", "materiality": "medium",
                 "recommendation": "Reclassify Cascadia to functional"},
                {"dimension": "Intercompany Pricing", "meridian": "Cost-plus 5%",
                 "cascadia": "No intercompany transactions", "materiality": "low",
                 "recommendation": "Establish transfer pricing for cross-entity work"},
                {"dimension": "Currency", "meridian": "Multi-currency (USD, EUR, GBP)",
                 "cascadia": "USD only", "materiality": "low",
                 "recommendation": "No action — Cascadia domestic only"},
            ],
        },
        "it_landscape": {
            "meridian_systems": 12,
            "cascadia_systems": 8,
            "sor_conflicts": [
                {"dimension": "Financial Data", "meridian_sor": "SAP S/4HANA",
                 "cascadia_sor": "QuickBooks", "resolution": "SAP is combined SOR"},
                {"dimension": "CRM", "meridian_sor": "Salesforce",
                 "cascadia_sor": "HubSpot", "resolution": "Migrate HubSpot → Salesforce"},
                {"dimension": "HCM", "meridian_sor": "Workday",
                 "cascadia_sor": "BambooHR", "resolution": "Migrate BambooHR → Workday"},
            ],
            "approach": "Both systems keep running. Intelligence layer reads both. Migration phased over 12 months.",
        },
    }


def get_qoe_data() -> dict[str, Any]:
    """Quality of Earnings baseline data."""
    return {
        "success": True,
        "engine": "qoe",
        "sustainability_score": 68,
        "grade": "B",
        "components": [
            {"name": "Revenue Quality", "score": 72, "weight": 0.25,
             "detail": "Recurring revenue 64%, concentration risk moderate"},
            {"name": "Earnings Persistence", "score": 65, "weight": 0.20,
             "detail": "3 one-time items in trailing 4 quarters"},
            {"name": "Cash Conversion", "score": 78, "weight": 0.20,
             "detail": "FCF/EBITDA ratio 0.82"},
            {"name": "Working Capital", "score": 61, "weight": 0.15,
             "detail": "DSO trending up (48→54 days)"},
            {"name": "Customer Health", "score": 58, "weight": 0.10,
             "detail": "Top 3 = 35% revenue, NRR 108%"},
            {"name": "Accounting Quality", "score": 74, "weight": 0.10,
             "detail": "Clean audit, one cash-to-accrual conversion pending"},
        ],
        "quarterly_plan": [
            "Q1: Baseline established — combined sustainability score 68",
            "Q2: Target 72 — resolve cash-to-accrual conversion, reduce DSO",
            "Q3: Target 76 — diversify customer base, improve working capital",
            "Q4: Target 80 — full integration, unified reporting",
        ],
    }
