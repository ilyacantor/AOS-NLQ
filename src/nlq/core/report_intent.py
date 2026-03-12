"""
Report intent detection — identifies Standard Reporting Package queries.

Distinguishes report requests from:
- Simple metric queries ("what is revenue?")
- P&L composite queries ("show me the P&L") — handled by composite_query.py
- Dashboard requests ("build me a CFO dashboard") — handled by visualization_intent.py

Report queries are things like:
- "Show me the P&L actual vs prior year"
- "Generate a balance sheet for Q3"
- "Cash flow statement for 2025"
- "Full year forecast vs prior year actuals"
- "Quarterly income statement Q2 2025 vs Q2 2024"
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ReportIntent:
    statement_type: str  # "income_statement", "balance_sheet", "cash_flow"
    variant: str  # "full_year_act_vs_py", "quarterly_act_vs_py", etc.
    selected_quarter: Optional[str] = None  # e.g., "2025-Q3"
    raw_question: str = ""


# ---------------------------------------------------------------------------
# Statement-type patterns
# ---------------------------------------------------------------------------

_INCOME_STATEMENT_PATTERN = re.compile(
    r"\b(?:p\s*&\s*l|p\s+and\s+l|profit\s+and\s+loss|profit\s*&\s*loss"
    r"|income\s+statement)\b",
    re.IGNORECASE,
)

_BALANCE_SHEET_PATTERN = re.compile(
    r"\b(?:balance\s+sheet|bs)\b",
    re.IGNORECASE,
)

_CASH_FLOW_PATTERN = re.compile(
    r"\b(?:cash\s+flow(?:\s+statement)?|socf|statement\s+of\s+cash\s+flows)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Comparison / variant patterns
# ---------------------------------------------------------------------------

_ACT_VS_PY_PATTERN = re.compile(
    r"(?:act(?:ual)?s?\s+vs?\.?\s+(?:prior\s+year|py|last\s+year|prev(?:ious)?\s+year)"
    r"|vs?\.?\s+(?:prior\s+year|py|last\s+year|prev(?:ious)?\s+year)"
    r"|(?:prior\s+year|py|last\s+year|prev(?:ious)?\s+year)\s+comp(?:arison)?"
    r"|year[\s-]+over[\s-]+year|yoy"
    r"|act(?:ual)?s?\s+vs?\.?\s+act(?:ual)?s?)",
    re.IGNORECASE,
)

_CF_VS_PY_PATTERN = re.compile(
    r"(?:(?:current\s+)?forecast\s+(?:for\s+)?(?:Q[1-4]\s+\d{4}\s+)?vs?\.?\s+(?:prior\s+year|py|last\s+year|prev(?:ious)?\s+year)"
    r"|cf\s+vs?\.?\s+py"
    r"|forecast\s+comp(?:arison)?)",
    re.IGNORECASE,
)

_FULL_YEAR_PATTERN = re.compile(
    r"\b(?:full\s+year|annual|fy\s*\d{2,4}|fy)\b",
    re.IGNORECASE,
)

_QUARTER_PATTERN = re.compile(
    r"\bQ([1-4])\b",
    re.IGNORECASE,
)

_YEAR_PATTERN = re.compile(
    r"\b(20\d{2})\b",
)

# Generic comparison language — catches "vs", "compared to", "against", etc.
# Only triggers when a statement type is also present.
_GENERIC_COMPARISON_PATTERN = re.compile(
    r"(?:\bvs?\.?\b|\bversus\b|\bcompared?\s+to\b|\bagainst\b|\brelative\s+to\b)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Negative patterns — these should NOT be caught as report queries
# ---------------------------------------------------------------------------

# Bare statement requests without comparison language → let composite_query handle
# (e.g., "show me the P&L", "what's the income statement")
_BARE_STATEMENT_PATTERN = re.compile(
    r"^(?:show\s+(?:me\s+)?(?:the\s+)?|what(?:'s|\s+is)\s+(?:the\s+)?|give\s+me\s+(?:the\s+)?"
    r"|pull\s+(?:up\s+)?(?:the\s+)?|display\s+(?:the\s+)?|get\s+(?:me\s+)?(?:the\s+)?)"
    r"(?:p\s*&\s*l|p\s+and\s+l|profit\s+and\s+loss|profit\s*&\s*loss|income\s+statement"
    r"|financial\s+statements?|full\s+financials)\s*\??$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

def _detect_statement_type(question: str) -> Optional[str]:
    """Identify which financial statement is requested."""
    if _INCOME_STATEMENT_PATTERN.search(question):
        return "income_statement"
    if _BALANCE_SHEET_PATTERN.search(question):
        return "balance_sheet"
    if _CASH_FLOW_PATTERN.search(question):
        return "cash_flow"
    return None


def _detect_variant(question: str, statement_type: str) -> Optional[str]:
    """Determine the comparison variant from the question text.

    Returns None if no comparison language is found — meaning this is
    not a report query (it's a bare statement request).
    """
    has_cf_vs_py = bool(_CF_VS_PY_PATTERN.search(question))
    has_act_vs_py = bool(_ACT_VS_PY_PATTERN.search(question))
    has_full_year = bool(_FULL_YEAR_PATTERN.search(question))
    has_quarter = bool(_QUARTER_PATTERN.search(question))

    # CF vs PY takes priority if explicitly stated
    if has_cf_vs_py:
        if has_full_year:
            return "full_year_cf_vs_py_act"
        if has_quarter:
            return "quarterly_cf_vs_py"
        return "full_year_cf_vs_py_act"

    # Explicit Act vs PY
    if has_act_vs_py:
        if has_full_year:
            return "full_year_act_vs_py"
        if has_quarter:
            return "quarterly_act_vs_py"
        return "full_year_act_vs_py"

    # Generic comparison language (e.g., "P&L vs last year")
    if _GENERIC_COMPARISON_PATTERN.search(question):
        if has_full_year:
            return "full_year_act_vs_py"
        if has_quarter:
            return "quarterly_act_vs_py"
        return "full_year_act_vs_py"

    # Balance sheet and cash flow without explicit comparison default to
    # quarterly act vs PY for the latest completed quarter — these statements
    # are inherently comparative in a reporting package context.
    if statement_type in ("balance_sheet", "cash_flow"):
        if has_full_year:
            return "full_year_act_vs_py"
        return "quarterly_act_vs_py"

    # Income statement without any comparison language → not a report query.
    # Let composite_query.py handle bare "show me the P&L".
    return None


def _extract_quarter(question: str) -> Optional[str]:
    """Extract a specific quarter reference like '2025-Q3' from the question."""
    q_match = _QUARTER_PATTERN.search(question)
    if not q_match:
        return None

    quarter_num = q_match.group(1)
    year_match = _YEAR_PATTERN.search(question)

    if year_match:
        year = year_match.group(1)
    else:
        # Default to current year
        from src.nlq.core.dates import current_quarter
        year = current_quarter()[:4]

    return f"{year}-Q{quarter_num}"


def _latest_completed_quarter() -> str:
    """Return the most recently completed quarter, e.g. '2025-Q4'."""
    from src.nlq.core.dates import current_quarter
    cq = current_quarter()  # e.g. "2026-Q1"
    year, q_num = int(cq[:4]), int(cq[-1])
    if q_num == 1:
        return f"{year - 1}-Q4"
    return f"{year}-Q{q_num - 1}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_report_intent(question: str) -> Optional[ReportIntent]:
    """Detect whether *question* is a Standard Reporting Package query.

    Returns a :class:`ReportIntent` describing the statement type and
    comparison variant, or ``None`` if this is not a report query.

    The detector is intentionally conservative — it only matches when the
    question contains both a recognized financial statement type *and*
    comparison/reporting language. Bare "show me the P&L" queries return
    None so the existing composite_query handler can take them.
    """
    statement_type = _detect_statement_type(question)
    if statement_type is None:
        return None

    # Bare P&L / income statement without comparison → not a report query
    if statement_type == "income_statement" and _BARE_STATEMENT_PATTERN.search(question):
        return None

    variant = _detect_variant(question, statement_type)
    if variant is None:
        return None

    # Determine selected quarter for quarterly variants
    selected_quarter = None
    if "quarterly" in variant:
        selected_quarter = _extract_quarter(question)
        if selected_quarter is None:
            # Default to latest completed quarter
            selected_quarter = _latest_completed_quarter()

    intent = ReportIntent(
        statement_type=statement_type,
        variant=variant,
        selected_quarter=selected_quarter,
        raw_question=question,
    )
    logger.info("Report intent detected: %s", intent)
    return intent
