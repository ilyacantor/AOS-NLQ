"""
Composite query handler for multi-metric responses (P&L statement, etc.).

Queries each line item from DCL and assembles them into a single
structured NLQResponse with related_metrics and financial_statement_data.

The harness extracts composite fields from related_metrics by matching
metric/display_name against field names (see _extract_composite_field).
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from src.nlq.services.dcl_semantic_client import propagate_context

from src.nlq.models.response import (
    NLQResponse,
    RelatedMetric,
    FinancialStatementData,
    FinancialStatementLineItem,
)

logger = logging.getLogger(__name__)

# Entity ID → display name mapping
_ENTITY_NAMES = {
    "meridian": "Meridian Partners",
    "cascadia": "Cascadia Process Solutions",
    "combined": "Combined (Meridian + Cascadia)",
}


def _resolve_entity_name(entity_id: Optional[str]) -> str:
    """Resolve entity_id to display name, defaulting to Meridian."""
    if entity_id:
        return _ENTITY_NAMES.get(entity_id.lower(), entity_id.title())
    return "Meridian Partners"

# ── P&L line items in presentation order ──────────────────────────────────
PL_LINE_ITEMS = [
    "revenue",
    "cogs",
    "gross_profit",
    "gross_margin_pct",
    "sm_expense",
    "rd_expense",
    "ga_expense",
    "opex",
    "ebitda",
    "ebitda_margin_pct",
    "operating_profit",
    "net_income",
    "net_margin_pct",
]

# Minimum required fields — if fewer than this many resolve, skip
PL_REQUIRED = {"revenue", "cogs", "gross_profit", "ebitda", "net_income"}
PL_MIN_REQUIRED = 3

# ── Line item display config: (label, indent, format, is_subtotal) ────────
LINE_ITEM_CONFIG: Dict[str, tuple] = {
    "revenue":          ("Revenue",                      0, "currency", False),
    "cogs":             ("Cost of Goods Sold",           1, "currency", False),
    "gross_profit":     ("Gross Profit",                 0, "currency", True),
    "gross_margin_pct": ("Gross Margin %",               0, "percent",  False),
    "sm_expense":       ("Sales & Marketing",            1, "currency", False),
    "rd_expense":       ("Research & Development",       1, "currency", False),
    "ga_expense":       ("General & Administrative",     1, "currency", False),
    "opex":             ("Total Operating Expenses",     0, "currency", True),
    "ebitda":           ("EBITDA",                       0, "currency", True),
    "ebitda_margin_pct":("EBITDA Margin %",              0, "percent",  False),
    "operating_profit": ("Operating Profit",             0, "currency", True),
    "net_income":       ("Net Income",                   0, "currency", True),
    "net_margin_pct":   ("Net Margin %",                 0, "percent",  False),
}

# ── Intent detection ──────────────────────────────────────────────────────
_PL_PATTERN = re.compile(
    r"\b(?:p\s*&\s*l|p\s+and\s+l|profit\s+and\s+loss|profit\s*&\s*loss"
    r"|income\s+statement|financial\s+statements?|full\s+financials)\b",
    re.IGNORECASE,
)


def is_pl_statement_query(question: str) -> bool:
    """Detect if the query asks for a full P&L / income statement."""
    return bool(_PL_PATTERN.search(question))


def determine_pl_periods(period_spec: Optional[str]) -> List[str]:
    """Determine which quarterly periods to include in the P&L.

    Args:
        period_spec: None (all available), "2025" (full year), "2025-Q3" (single quarter)

    Returns:
        List of quarterly period strings like ["2024-Q1", "2024-Q2", ...]
    """
    if period_spec and re.match(r"^20\d{2}-Q[1-4]$", period_spec):
        return [period_spec]

    if period_spec and re.match(r"^20\d{2}$", period_spec):
        year = period_spec
        return [f"{year}-Q1", f"{year}-Q2", f"{year}-Q3", f"{year}-Q4"]

    # Default: generate all quarters from 2024 through the current quarter.
    # DCL queries will return data for periods that have it; periods without
    # data will simply have no line items. No fact_base.json dependency.
    from src.nlq.core.dates import current_quarter
    cq = current_quarter()  # e.g. "2026-Q1"

    periods = []
    for year in range(2024, 2027):
        for q in range(1, 5):
            p = f"{year}-Q{q}"
            if p <= cq:
                periods.append(p)
    return periods


class PLStatementHandler:
    """Builds a composite P&L response by querying all line items from DCL."""

    def __init__(self, periods: List[str], query_fn: Callable, entity_id: Optional[str] = None):
        """
        Args:
            periods: List of quarterly periods (e.g., ["2024-Q1", "2024-Q2", ...]).
            query_fn: callable(metric_id, period) -> Optional[SimpleMetricResult].
                      Injected from routes.py to avoid circular imports.
            entity_id: Optional entity filter (e.g., "meridian", "cascadia").
        """
        self.periods = periods
        self.query_fn = query_fn
        self.entity_id = entity_id

    def execute(self) -> Optional[NLQResponse]:
        """Query all P&L line items for all periods and assemble response."""
        from src.nlq.knowledge.schema import is_additive_metric

        # values[metric][period] = float
        values: Dict[str, Dict[str, Optional[float]]] = {}
        first_result: Any = None

        def _fetch(metric: str, period: str):
            try:
                result = self.query_fn(metric, period)
                return (metric, period, result)
            except Exception as e:
                logger.warning(f"P&L query failed for {metric}/{period}: {e}")
                return (metric, period, None)

        total_queries = len(self.periods) * len(PL_LINE_ITEMS)
        with ThreadPoolExecutor(max_workers=min(32, total_queries)) as pool:
            wrapped = propagate_context(_fetch)
            futures = [
                pool.submit(wrapped, metric, period)
                for period in self.periods
                for metric in PL_LINE_ITEMS
            ]
            for future in as_completed(futures):
                metric, period, result = future.result()
                if result is not None:
                    if first_result is None:
                        first_result = result
                    values.setdefault(metric, {})[period] = result.value

        # Validate minimum required fields (at least some data for required metrics)
        resolved_required = PL_REQUIRED & set(values.keys())
        if len(resolved_required) < PL_MIN_REQUIRED:
            logger.warning(
                f"P&L composite: only {len(resolved_required)}/{len(PL_REQUIRED)} "
                f"required fields resolved ({resolved_required}). Returning None."
            )
            return None

        # Compute FY totals per year
        years_in_scope = sorted(set(p.split("-")[0] for p in self.periods))
        fy_periods = []
        for year in years_in_scope:
            year_quarters = [p for p in self.periods if p.startswith(year)]
            if len(year_quarters) < 4:
                continue  # Only show FY total for complete years
            fy_label = f"FY {year}"
            fy_periods.append((fy_label, year, year_quarters))

        # Build display period labels
        display_periods: List[str] = []
        for period in self.periods:
            # "2024-Q1" -> "Q1 2024"
            parts = period.split("-")
            display_periods.append(f"{parts[1]} {parts[0]}")

        # Insert FY totals after each year's quarters
        final_periods: List[str] = []
        for dp in display_periods:
            final_periods.append(dp)
            # Check if this is the last quarter of a year that has FY total
            for fy_label, year, _ in fy_periods:
                if dp == f"Q4 {year}":
                    final_periods.append(fy_label)

        # Compute FY aggregate values
        for metric, metric_values in values.items():
            _is_additive = is_additive_metric(metric)
            for fy_label, year, year_quarters in fy_periods:
                qvals = [metric_values.get(q) for q in year_quarters]
                non_null = [v for v in qvals if v is not None]
                if non_null:
                    if _is_additive:
                        metric_values[fy_label] = sum(non_null)
                    else:
                        metric_values[fy_label] = sum(non_null) / len(non_null)
                else:
                    metric_values[fy_label] = None

        # Build FinancialStatementLineItem list
        line_items: List[FinancialStatementLineItem] = []
        for metric_id in PL_LINE_ITEMS:
            if metric_id not in values and metric_id not in LINE_ITEM_CONFIG:
                continue
            label, indent, fmt, is_sub = LINE_ITEM_CONFIG[metric_id]
            metric_values = values.get(metric_id, {})
            # Map internal period keys to display labels
            display_values: Dict[str, Optional[float]] = {}
            for period in self.periods:
                parts = period.split("-")
                dp = f"{parts[1]} {parts[0]}"
                display_values[dp] = metric_values.get(period)
            for fy_label, _, _ in fy_periods:
                display_values[fy_label] = metric_values.get(fy_label)

            line_items.append(FinancialStatementLineItem(
                label=label,
                key=metric_id,
                indent=indent,
                format=fmt,
                is_subtotal=is_sub,
                values=display_values,
            ))

        entity_name = _resolve_entity_name(self.entity_id)
        fs_data = FinancialStatementData(
            title="Income Statement",
            entity=entity_name,
            periods=final_periods,
            line_items=line_items,
            currency="USD",
            unit="millions",
        )

        # Build related_metrics for backward compat (first period values)
        first_period = self.periods[0] if self.periods else None
        related: List[RelatedMetric] = []
        if first_period:
            for metric_id in PL_LINE_ITEMS:
                result_val = values.get(metric_id, {}).get(first_period)
                if result_val is None:
                    continue
                label, _, fmt, _ = LINE_ITEM_CONFIG[metric_id]
                if fmt == "percent":
                    fv = f"{round(result_val, 1)}%"
                else:
                    fv = f"${round(result_val, 1)}M"
                related.append(RelatedMetric(
                    metric=metric_id,
                    display_name=label,
                    value=result_val,
                    formatted_value=fv,
                    period=first_period,
                    confidence=0.95,
                    match_type="exact",
                    rationale="P&L line item",
                    domain="finance",
                ))

        # Build human-readable text answer
        lines = [f"**Income Statement — {', '.join(final_periods)}**\n"]
        for li in line_items:
            prefix = "  " * li.indent
            first_val = next((li.values[p] for p in final_periods if li.values.get(p) is not None), None)
            if first_val is not None:
                if li.format == "percent":
                    fv = f"{round(first_val, 1)}%"
                else:
                    fv = f"${round(first_val, 1)}M"
                lines.append(f"{prefix}{li.label}: {fv}")

        return NLQResponse(
            success=True,
            answer="\n".join(lines),
            value=None,
            unit=None,
            confidence=0.95,
            parsed_intent="PL_STATEMENT",
            resolved_metric="pl_statement",
            resolved_period=self.periods[0] if self.periods else "",
            related_metrics=related if related else None,
            response_type="financial_statement",
            financial_statement_data=fs_data,
            data_source=first_result.data_source if first_result else None,
        )
