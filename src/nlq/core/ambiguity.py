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
    ],
    AmbiguityType.SUMMARY: [
        r"in a nutshell",               # Summary request
        r"^\d{4} in a nutshell",        # "2025 in a nutshell"
    ],
    AmbiguityType.COMPARISON: [
        r"\bvs\.?\s",                   # "bookings vs revenue"
        r"compare.*to",                 # "compare this year to last"
        r"(this|last) year to (last|this)",
    ],
    AmbiguityType.VAGUE_METRIC: [
        r"how['\u2019]?d we do",        # "how'd we do" - wants key financials
        r"^whats? the margin",          # "whats the margin" - which margin?
        r"^quick ratio stuff",          # Vague ratio reference
        r"^the numbers$",               # Very vague
    ],
    AmbiguityType.YES_NO: [
        r"^are we profitable",          # Boolean question
        r"^we growing\??$",             # "we growing?"
        r"^is .*\?$",                   # "is X?"
    ],
    AmbiguityType.BROAD_REQUEST: [
        r"give me the p&l",             # Wants full P&L
        r"full (report|breakdown)",     # Comprehensive request
    ],
    AmbiguityType.JUDGMENT_CALL: [
        r"too (high|low)\??$",          # "costs too high?"
        r"good (enough|result)",        # Subjective judgment
    ],
    AmbiguityType.SHORTHAND: [
        r"^cash position",              # Common shorthand
    ],
    AmbiguityType.CONTEXT_DEPENDENT: [
        r"^what about\s+q\d",           # "what about Q2" - which Q2?
        r"^year over year$",            # Missing metric
        r"^yoy$",                       # Missing metric
    ],
    AmbiguityType.CASUAL_LANGUAGE: [
        r"hows .*looking",              # "hows the top line looking"
        r"where are we on",             # "where are we on AR"
        r"\bpls\b|\bplease\b$",         # "opex breakdown pls"
    ],
    AmbiguityType.INCOMPLETE: [
        r"^rev\??$",                    # "rev?" - incomplete metric
        r"^q\d\s*numbers?",             # "q4 numbers"
        r"^20\d{2}\s*$",                # Just a year
    ],
}

# Candidate metrics for each ambiguity type
AMBIGUITY_CANDIDATES = {
    AmbiguityType.INCOMPLETE: {
        "rev": ["revenue"],
        "q4": ["revenue", "net_income"],
        "default": ["revenue", "net_income"],
    },
    AmbiguityType.CASUAL_LANGUAGE: {
        "top line": ["revenue"],
        "ar": ["ar"],
        "opex": ["sga", "selling_expense", "ga_expense"],
        "default": ["revenue", "net_income"],
    },
    AmbiguityType.VAGUE_METRIC: {
        "how'd we do": ["revenue", "net_income"],  # Key financials
        "how": ["revenue", "net_income"],
        "margin": ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
        "ratio": ["current_assets", "current_liabilities"],
        "default": ["revenue", "net_income"],
    },
    AmbiguityType.YES_NO: {
        "profitable": ["net_income_pct", "net_income"],
        "growing": ["revenue"],
        "default": ["net_income", "revenue"],
    },
    AmbiguityType.BROAD_REQUEST: {
        "p&l": ["revenue", "cogs", "gross_profit", "sga", "operating_profit", "net_income"],
        "default": ["revenue", "gross_profit", "operating_profit", "net_income"],
    },
    AmbiguityType.IMPLIED_CONTEXT: {
        "hit": ["revenue"],
        "default": ["revenue"],
    },
    AmbiguityType.JUDGMENT_CALL: {
        "costs": ["cogs", "sga"],
        "default": ["cogs", "sga"],
    },
    AmbiguityType.SHORTHAND: {
        "cash position": ["cash"],
        "default": ["cash"],
    },
    AmbiguityType.CONTEXT_DEPENDENT: {
        "q2": ["revenue", "net_income"],
        "yoy": ["revenue"],
        "year over year": ["revenue"],
        "default": ["revenue", "net_income"],
    },
    AmbiguityType.COMPARISON: {
        "bookings vs revenue": ["bookings", "revenue"],
        "vs": ["bookings", "revenue"],
        "compare": ["revenue", "net_income", "operating_margin_pct"],
        "default": ["revenue", "net_income", "operating_margin_pct"],
    },
    AmbiguityType.SUMMARY: {
        "nutshell": ["revenue", "net_income", "operating_margin_pct"],
        "default": ["revenue", "net_income", "operating_margin_pct"],
    },
    AmbiguityType.BURN_RATE: {
        "burn rate": ["cogs", "sga"],  # Show actual costs for profitable companies
        "runway": ["cogs", "sga"],
        "default": ["cogs", "sga"],
    },
}

# Clarification prompts for each ambiguity type
CLARIFICATION_PROMPTS = {
    AmbiguityType.INCOMPLETE: "Could you be more specific? Which metric are you interested in?",
    AmbiguityType.CASUAL_LANGUAGE: None,  # Usually can be inferred
    AmbiguityType.VAGUE_METRIC: "Which margin - Gross, Operating, or Net?",
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
