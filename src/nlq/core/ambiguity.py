"""
Ambiguity detection for NLQ queries.

Detects different types of query ambiguity and provides
candidate metrics for disambiguation.
"""

import re
from typing import List, Optional, Tuple

from src.nlq.models.response import AmbiguityType


# Patterns for detecting different ambiguity types
# ORDER MATTERS - more specific patterns should come before general ones
AMBIGUITY_PATTERNS = {
    # Most specific first
    AmbiguityType.BURN_RATE: [
        r"burn rate",                   # Applies but not reported discretely for profitable companies
        r"runway",                      # Similar - tracked via COGS/SG&A for profitable companies
    ],
    AmbiguityType.IMPLIED_CONTEXT: [
        r"did we hit \d+",              # "did we hit 150" - implies revenue target
        r"did we close the big",        # CRO - "did we close the big deal"
    ],
    AmbiguityType.SUMMARY: [
        r"in a nutshell",               # Summary request
        r"^\d{4} in a nutshell",        # "2025 in a nutshell"
        r"^ops summary",                # COO summary
        r"^platform overview",          # CTO summary
    ],
    AmbiguityType.COMPARISON: [
        r"\bvs\.?\s",                   # "bookings vs revenue"
        r"compare.*to",                 # "compare this year to last"
        r"(this|last) year to (last|this)",
        r"^compare quarters",           # CRO - quarter comparison
    ],
    AmbiguityType.VAGUE_METRIC: [
        r"how['\u2019]?d we do",        # "how'd we do" - wants key financials
        r"how did we do",               # "how did we do?" - same intent
        r"the margin\b",               # "show me the margin", "whats the margin"
        r"^whats? the margin",          # "whats the margin" - which margin?
        r"^quick ratio stuff",          # Vague ratio reference
        r"^the numbers$",               # Very vague
        r"^new business$",              # CRO - new logos or new revenue?
        r"^reps performing",            # CRO - sales rep performance
        r"^pipeline coverage",          # CRO - coverage ratio
        r"^sales efficiency",           # CRO - efficiency metrics
        r"^team breakdown",             # COO - headcount by function
        r"^utilization\??$",            # COO - which utilization?
        r"^any incidents",              # CTO - incident count
        r"^code quality",               # CTO - quality metrics
        r"^security posture",           # CTO - security metrics
        r"^eng productivity",           # CTO - engineering metrics
    ],
    AmbiguityType.JUDGMENT_CALL: [
        r"improving\??$",              # "is retention improving?" / "retention improving?"
        r"getting (better|worse)",      # "is margin getting better?"
        r"trending (up|down)",          # "is revenue trending up?"
        r"(declining|deteriorating)",   # "is retention declining?"
        r"on track",                    # "are we on track?"
        r"too (high|low)\??$",          # "costs too high?"
        r"good (enough|result)",        # Subjective judgment
        r"^retention ok",               # CRO - retention assessment
        r"^forecast.* good",            # CRO - forecast assessment
        r"^attrition bad",              # COO - attrition assessment
        r"^are we overstaffed",         # COO - headcount assessment
        r"^burn rate ok",              # COO - burn assessment
        r"^support overwhelmed",        # COO - support capacity assessment
        r"^shipping enough",            # CTO - features assessment
        r"^infra efficient",            # CTO - infrastructure efficiency
    ],
    AmbiguityType.YES_NO: [
        r"^are we profitable",          # CFO - profitability
        r"^we growing\??$",             # CFO - growth
        r"^is .*\?$",                   # Generic yes/no (AFTER judgment patterns)
        r"^are we (hitting|at) quota",  # CRO - quota
        r"^are we growing",             # CRO - growth
        r"^are we efficient",           # COO - efficiency
        r"^implementation.* better",    # COO - improvement
        r"^platform stable",            # CTO - stability
        r"^eng team growing",           # CTO - headcount
        r"^reliability improving",      # CTO - reliability
        r"^bugs under control",         # CTO - bugs
    ],
    AmbiguityType.BROAD_REQUEST: [
        r"p&l",                         # CFO - P&L (any mention)
        r"profit.* loss",               # CFO - profit and loss
        # Causal "why" / "what drove" patterns removed — these must flow to LLM
        # which parses them as BREAKDOWN_QUERY with proper breakdown_metrics
        # (e.g. revenue → new_logo, expansion, renewal). Intercepting here
        # short-circuited the bridge and returned a single number.
        r"full (report|breakdown)",     # Comprehensive request
        r"^support metrics",            # COO - support metrics
        r"^ops summary",                # COO - operations summary
        r"^platform overview",          # CTO - platform summary
    ],
    AmbiguityType.SHORTHAND: [
        r"^cash position",              # CFO shorthand
        r"^churn\??$",                  # CRO - churn metrics
        r"^nrr$",                       # CRO - net revenue retention
        r"^logo adds",                  # CRO - logo additions
        r"^(sales )?pipeline\??$",      # CRO - sales pipeline (handles "pipeline" and "sales pipeline")
        r"^magic number$",              # COO - sales efficiency
        r"^payback period",             # COO - CAC payback
        r"^ltv cac",                    # COO - LTV/CAC ratio
        r"^onboarding time",            # COO - onboarding
        r"^uptime\??$",                 # CTO - uptime
        r"^tech debt$",                 # CTO - tech debt
        r"^deployment frequency",       # CTO - deploys
        r"^mttr$",                      # CTO - mean time to recovery
    ],
    AmbiguityType.CONTEXT_DEPENDENT: [
        r"^what about\s+q\d",           # "what about Q2" - which Q2?
        r"^year over year$",            # Missing metric
        r"^yoy$",                       # Missing metric
        r"(^|\d{4}\s+)biggest deals",   # CRO - needs timeframe or "2025 biggest deals"
        r"^who'?s growing fastest",     # COO - fastest growing team
    ],
    AmbiguityType.CASUAL_LANGUAGE: [
        r"how['']?s? .*looking",        # "hows the top line looking" / "how's pipeline looking"
        r"where are we on",             # "where are we on AR"
        r"\bpls\b|\bplease\b$",         # "opex breakdown pls"
        r"how['']?s? (the )?funnel",    # CRO - sales funnel
        r"what['']?s expansion doing",  # CRO - expansion
        r"how['']?d q\d go",            # CRO - quarter results
        r"how['']?s hiring",            # COO - hiring status
        r"how['']?s customer success",  # COO - CS team
        r"how['']?s velocity",          # CTO - velocity
        r"how fast can we ship",        # CTO - shipping speed
    ],
    AmbiguityType.INCOMPLETE: [
        r"^rev\??$",                    # "rev?" - incomplete metric
        r"^q\d\s*numbers?",             # "q4 numbers"
        r"^20\d{2}\s*$",                # Just a year
        r"^bookings\??$",               # CRO - just bookings
        r"^close rate trend",           # CRO - trend without period
        r"^headcount\??$",              # COO - just headcount
        r"^q\d hires",                  # COO - quarterly hires
        r"^ticket volume trend",        # COO - trend
        r"^cloud costs$",               # CTO - cloud costs
        r"^q\d performance",            # CTO - quarterly performance
    ],
}

# Candidate metrics for each ambiguity type
AMBIGUITY_CANDIDATES = {
    AmbiguityType.INCOMPLETE: {
        "rev": ["revenue"],
        "q4": ["revenue", "net_income"],
        "bookings": ["bookings", "pipeline", "win_rate_pct"],
        "close rate": ["win_rate_pct"],
        "headcount": ["headcount", "engineering_headcount", "sales_headcount"],
        "q4 hires": ["hires"],
        "ticket volume": ["support_tickets"],
        "cloud costs": ["cloud_spend", "cloud_spend_pct_revenue"],
        "q4 performance": ["features_shipped", "story_points", "p1_incidents"],
        "default": ["revenue", "net_income"],
    },
    AmbiguityType.CASUAL_LANGUAGE: {
        "top line": ["revenue"],
        "ar": ["ar"],
        "opex": ["sga", "selling_expense", "ga_expense"],
        "pipeline": ["pipeline", "qualified_pipeline", "win_rate_pct"],
        "funnel": ["pipeline", "win_rate_pct", "sales_cycle_days"],
        "expansion": ["expansion_revenue"],
        "q4 go": ["bookings", "new_logos", "win_rate_pct"],
        "hiring": ["hires", "headcount"],
        "customer success": ["cs_headcount", "csat", "nps"],
        "velocity": ["sprint_velocity", "features_shipped"],
        "ship": ["lead_time_days", "deploys_per_week"],
        "default": ["revenue", "net_income"],
    },
    AmbiguityType.VAGUE_METRIC: {
        "how'd we do": ["revenue", "net_income"],
        "how": ["revenue", "net_income"],
        "margin": ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
        "ratio": ["total_current_assets", "current_liabilities"],
        "new business": ["new_logo_revenue", "new_logos", "customer_count"],
        "reps performing": ["reps_at_quota_pct", "quota_attainment_pct", "sales_headcount"],
        "pipeline coverage": ["pipeline", "sales_quota"],
        "sales efficiency": ["magic_number", "cac_payback_months"],
        "team breakdown": ["engineering_headcount", "sales_headcount", "cs_headcount", "ga_headcount"],
        "utilization": ["ps_utilization", "engineering_utilization", "support_utilization"],
        "incidents": ["p1_incidents", "p2_incidents"],
        "code quality": ["code_coverage_pct", "bug_escape_rate", "tech_debt_pct"],
        "security": ["security_vulns", "code_coverage_pct"],
        "eng productivity": ["sprint_velocity", "features_shipped", "deploys_per_week"],
        "default": ["revenue", "net_income"],
    },
    AmbiguityType.YES_NO: {
        "profitable": ["net_income_pct", "net_income"],
        "growing": ["revenue", "bookings"],
        "quota": ["quota_attainment_pct", "reps_at_quota_pct"],
        "retention": ["nrr", "churn_rate_pct"],
        "forecast": ["bookings", "win_rate_pct"],
        "efficient": ["revenue_per_employee", "magic_number"],
        "overstaffed": ["revenue_per_employee", "headcount"],
        "overwhelmed": ["support_utilization", "first_response_hours"],
        "implementation": ["implementation_days", "time_to_value_days"],
        "stable": ["uptime_pct", "mttr_p1_hours"],
        "eng team": ["engineering_headcount"],
        "reliability": ["uptime_pct"],
        "bugs": ["critical_bugs", "bug_escape_rate"],
        "shipping": ["features_shipped"],
        "default": ["net_income", "revenue"],
    },
    AmbiguityType.BROAD_REQUEST: {
        "p&l": ["revenue", "cogs", "gross_profit", "sga", "operating_profit", "net_income"],
        "rev": ["revenue", "bookings", "new_logos", "expansion_revenue", "nrr"],
        "margin": ["gross_margin_pct", "operating_margin_pct", "cogs", "sga"],
        "churn": ["churn_rate_pct", "nrr", "customer_count", "csat"],
        "cost": ["cogs", "sga", "cloud_spend", "cac"],
        "expense": ["sga", "selling_expense", "ga_expense", "cloud_spend"],
        "profit": ["net_income", "operating_profit", "gross_profit", "revenue", "cogs", "sga"],
        "growth": ["revenue", "arr", "bookings", "customer_count"],
        "support metrics": ["first_response_hours", "resolution_hours", "csat"],
        "ops summary": ["headcount", "revenue_per_employee", "magic_number", "cac_payback_months"],
        "platform overview": ["uptime_pct", "features_shipped", "cloud_spend", "engineering_headcount"],
        "default": ["revenue", "gross_profit", "operating_profit", "net_income"],
    },
    AmbiguityType.IMPLIED_CONTEXT: {
        "hit": ["revenue"],
        "close": ["bookings"],
        "biggest": ["bookings"],
        "default": ["revenue"],
    },
    AmbiguityType.JUDGMENT_CALL: {
        "retention": ["nrr", "churn_rate_pct", "logo_churn_pct"],
        "costs": ["cogs", "sga"],
        "margin": ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
        "revenue": ["revenue", "arr", "bookings"],
        "attrition": ["attrition_rate_pct", "attrition"],
        "burn rate ok": ["burn_multiple"],
        "infra": ["cost_per_transaction", "cloud_spend_pct_revenue"],
        "churn": ["churn_rate_pct", "nrr"],
        "default": ["nrr", "revenue"],
    },
    AmbiguityType.SHORTHAND: {
        "cash position": ["cash"],
        "churn": ["churn_rate_pct", "logo_churn_pct", "nrr"],
        "nrr": ["nrr"],
        "logo adds": ["customer_count", "new_logos"],
        "pipeline": ["pipeline", "qualified_pipeline", "win_rate_pct"],
        "sales pipeline": ["pipeline", "qualified_pipeline", "win_rate_pct"],
        "magic number": ["magic_number"],
        "payback": ["cac_payback_months"],
        "ltv": ["ltv_cac"],
        "onboarding": ["implementation_days", "time_to_value_days"],
        "uptime": ["uptime_pct"],
        "tech debt": ["tech_debt_pct"],
        "deployment": ["deploys_per_week"],
        "mttr": ["mttr_p1_hours", "mttr_p2_hours"],
        "default": ["cash"],
    },
    AmbiguityType.CONTEXT_DEPENDENT: {
        "q2": ["revenue", "net_income"],
        "yoy": ["revenue"],
        "year over year": ["revenue"],
        "biggest deals": ["bookings", "avg_deal_size"],
        "growing fastest": ["engineering_headcount", "sales_headcount"],
        "default": ["revenue", "net_income"],
    },
    AmbiguityType.COMPARISON: {
        "bookings vs revenue": ["bookings", "revenue"],
        "vs": ["bookings", "revenue"],
        "compare": ["revenue", "net_income", "operating_margin_pct"],
        "quarters": ["bookings"],
        "this year": ["features_shipped", "uptime_pct"],
        "default": ["revenue", "net_income", "operating_margin_pct"],
    },
    AmbiguityType.SUMMARY: {
        "nutshell": ["revenue", "net_income", "operating_margin_pct"],
        "ops": ["headcount", "revenue_per_employee", "magic_number", "cac_payback_months"],
        "platform": ["uptime_pct", "features_shipped", "cloud_spend", "engineering_headcount"],
        "default": ["revenue", "net_income", "operating_margin_pct"],
    },
    AmbiguityType.BURN_RATE: {
        "burn rate": ["cogs", "sga"],
        "runway": ["cogs", "sga"],
        "default": ["cogs", "sga"],
    },
}

# Clarification prompts for each ambiguity type
CLARIFICATION_PROMPTS = {
    AmbiguityType.INCOMPLETE: "Could you be more specific? Which metric are you interested in?",
    AmbiguityType.CASUAL_LANGUAGE: None,  # Usually can be inferred
    AmbiguityType.VAGUE_METRIC: "Which metric? For margins: Gross, Operating, or Net. For performance: Revenue, Bookings, ARR.",
    AmbiguityType.YES_NO: None,  # Can answer with context
    AmbiguityType.BROAD_REQUEST: None,  # Just provide the breakdown
    AmbiguityType.IMPLIED_CONTEXT: "What target are you referring to?",
    AmbiguityType.JUDGMENT_CALL: "Compared to what benchmark?",
    AmbiguityType.SHORTHAND: None,  # Can infer
    AmbiguityType.CONTEXT_DEPENDENT: "Year over year for which metric?",
    AmbiguityType.COMPARISON: None,  # Can provide comparison
    AmbiguityType.SUMMARY: None,  # Provide summary
    AmbiguityType.BURN_RATE: None,  # Provide cost breakdown and explain not reported discretely
}


def detect_ambiguity(question: str) -> Tuple[Optional[AmbiguityType], List[str], Optional[str]]:
    """
    Detect ambiguity type in a question.

    Args:
        question: The natural language question

    Returns:
        Tuple of (ambiguity_type, candidate_metrics, clarification_prompt)
        Returns (None, [], None) if question is not ambiguous
    """
    q = question.lower().strip()

    # Check each ambiguity type
    for amb_type, patterns in AMBIGUITY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, q, re.IGNORECASE):
                candidates = _get_candidates(amb_type, q)
                prompt = CLARIFICATION_PROMPTS.get(amb_type)
                return amb_type, candidates, prompt

    return None, [], None


def _get_candidates(amb_type: AmbiguityType, question: str) -> List[str]:
    """Get candidate metrics for an ambiguity type."""
    candidates_map = AMBIGUITY_CANDIDATES.get(amb_type, {"default": []})

    # Try to find specific candidates based on keywords
    q = question.lower()
    for keyword, metrics in candidates_map.items():
        if keyword != "default" and keyword in q:
            return metrics

    return candidates_map.get("default", [])


def needs_clarification(ambiguity_type: Optional[AmbiguityType]) -> bool:
    """
    Determine if clarification should be requested.

    Args:
        ambiguity_type: The detected ambiguity type

    Returns:
        True if clarification prompt should be shown
    """
    if ambiguity_type is None:
        return False

    return CLARIFICATION_PROMPTS.get(ambiguity_type) is not None
