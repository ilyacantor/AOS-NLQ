"""
Demo seed data for Maestra — Meridian and Cascadia entity profiles.

Used in demo mode when Maestra starts a Convergence engagement.
These provide the intel briefs and pre-populated contour maps
so the demo doesn't start from zero.
"""

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
