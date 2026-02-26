"""
Composite query handler for multi-metric responses (P&L statement, etc.).

Queries each line item from DCL and assembles them into a single
structured NLQResponse with related_metrics.

The harness extracts composite fields from related_metrics by matching
metric/display_name against field names (see _extract_composite_field).
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from src.nlq.models.response import NLQResponse, RelatedMetric

logger = logging.getLogger(__name__)

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

# ── Intent detection ──────────────────────────────────────────────────────
_PL_PATTERN = re.compile(
    r"\b(?:p\s*&\s*l|p\s+and\s+l|profit\s+and\s+loss|profit\s*&\s*loss"
    r"|income\s+statement|financial\s+statements?|full\s+financials)\b",
    re.IGNORECASE,
)


def is_pl_statement_query(question: str) -> bool:
    """Detect if the query asks for a full P&L / income statement."""
    return bool(_PL_PATTERN.search(question))


class PLStatementHandler:
    """Builds a composite P&L response by querying all line items from DCL."""

    def __init__(self, period: str, query_fn: Callable):
        """
        Args:
            period: Resolved time period (e.g., "2025", "2025-Q3").
            query_fn: callable(metric_id, period) -> Optional[SimpleMetricResult].
                      Injected from routes.py to avoid circular imports.
        """
        self.period = period
        self.query_fn = query_fn

    def execute(self) -> Optional[NLQResponse]:
        """Query all P&L line items and assemble response.

        Runs queries sequentially to preserve request-scoped context variables
        (data_mode, force_local) that the DCL client depends on.
        """
        results: Dict[str, Any] = {}

        for metric in PL_LINE_ITEMS:
            try:
                result = self.query_fn(metric, self.period)
                if result is not None:
                    results[metric] = result
            except Exception as e:
                logger.warning(f"P&L query failed for {metric}: {e}")

        # Validate minimum required fields
        resolved_required = PL_REQUIRED & set(results.keys())
        if len(resolved_required) < PL_MIN_REQUIRED:
            logger.warning(
                f"P&L composite: only {len(resolved_required)}/{len(PL_REQUIRED)} "
                f"required fields resolved ({resolved_required}). Returning None."
            )
            return None

        # Build related_metrics in presentation order
        related: List[RelatedMetric] = []
        for metric_id in PL_LINE_ITEMS:
            result = results.get(metric_id)
            if result is None:
                continue
            related.append(RelatedMetric(
                metric=result.metric,
                display_name=result.display_name,
                value=result.value,
                formatted_value=result.formatted_value,
                period=str(result.period),
                confidence=0.95,
                match_type="exact",
                rationale="P&L line item",
                domain=result.domain.value if hasattr(result.domain, "value") else str(result.domain),
            ))

        # Build human-readable text answer
        lines = [f"**P&L Statement — {self.period}**\n"]
        for rm in related:
            lines.append(f"  {rm.display_name}: {rm.formatted_value}")
        answer_text = "\n".join(lines)

        # Get data_source from first available result
        first = next(iter(results.values()))

        return NLQResponse(
            success=True,
            answer=answer_text,
            value=None,
            unit=None,
            confidence=0.95,
            parsed_intent="PL_STATEMENT",
            resolved_metric="pl_statement",
            resolved_period=self.period,
            related_metrics=related,
            response_type="text",
            data_source=first.data_source,
        )
