"""
Standard Reporting Package — multi-period financial statement generator.

Combines the period comparison engine with DCL metric queries to produce
structured financial statements with Act/CF/PY comparison columns.

Statement types:
  - P&L (Income Statement): Revenue through Net Income
  - BS (Balance Sheet): Assets, Liabilities, Equity — point-in-time only
  - SOCF (Statement of Cash Flows): Operating, Investing, Financing

The generator uses PeriodComparison from period_engine to determine
which columns to show and what data type each column contains.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Callable, Dict, List, Optional

from src.nlq.services.dcl_semantic_client import propagate_context

from src.nlq.models.response import (
    NLQResponse,
    FinancialStatementData,
    FinancialStatementLineItem,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Balance Sheet line items
# ═══════════════════════════════════════════════════════════════════════════════

BS_LINE_ITEMS = [
    "cash", "ar", "unbilled_revenue", "prepaid_expenses",
    "pp_e", "intangibles", "goodwill", "total_assets",
    "ap", "accrued_expenses", "deferred_revenue",
    "total_liabilities", "retained_earnings", "stockholders_equity",
]

# (label, indent, format, is_subtotal)
BS_LINE_ITEM_CONFIG: Dict[str, tuple] = {
    "cash":                ("Cash & Equivalents",           0, "currency", False),
    "ar":                  ("Accounts Receivable",          0, "currency", False),
    "unbilled_revenue":    ("Unbilled Revenue",             0, "currency", False),
    "prepaid_expenses":    ("Prepaid Expenses",             0, "currency", False),
    "pp_e":                ("Property, Plant & Equipment",  0, "currency", False),
    "intangibles":         ("Intangible Assets",            0, "currency", False),
    "goodwill":            ("Goodwill",                     0, "currency", False),
    "total_assets":        ("Total Assets",                 0, "currency", True),
    "ap":                  ("Accounts Payable",             0, "currency", False),
    "accrued_expenses":    ("Accrued Expenses",             0, "currency", False),
    "deferred_revenue":    ("Deferred Revenue",             0, "currency", False),
    "total_liabilities":   ("Total Liabilities",            0, "currency", True),
    "retained_earnings":   ("Retained Earnings",            0, "currency", False),
    "stockholders_equity": ("Stockholders' Equity",         0, "currency", True),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Statement of Cash Flows line items
# ═══════════════════════════════════════════════════════════════════════════════

SOCF_LINE_ITEMS = [
    "net_income", "da_expense",
    "change_in_ar", "change_in_ap", "change_in_deferred_rev",
    "cfo", "capex", "fcf",
]

SOCF_LINE_ITEM_CONFIG: Dict[str, tuple] = {
    "net_income":              ("Net Income",                  0, "currency", False),
    "da_expense":              ("Depreciation & Amortization", 1, "currency", False),
    "change_in_ar":            ("Change in A/R",               1, "currency", False),
    "change_in_ap":            ("Change in A/P",               1, "currency", False),
    "change_in_deferred_rev":  ("Change in Deferred Revenue",  1, "currency", False),
    "cfo":                     ("Cash from Operations",        0, "currency", True),
    "capex":                   ("Capital Expenditures",        0, "currency", False),
    "fcf":                     ("Free Cash Flow",              0, "currency", True),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Report Generator
# ═══════════════════════════════════════════════════════════════════════════════

class ReportGenerator:
    """Builds structured financial reports with period comparison columns.

    Combines PeriodComparison from period_engine with DCL metric queries
    to produce multi-period, multi-statement reports (P&L, BS, SOCF).
    """

    def __init__(self, query_fn: Callable, wall_clock: Optional[date] = None, entity_id: Optional[str] = None):
        """
        Args:
            query_fn: callable(metric_id, period) -> Optional[SimpleMetricResult]
            wall_clock: Override wall clock date (defaults to date.today())
            entity_id: Optional entity filter — resolved from DCL engagement state.
        """
        self.query_fn = query_fn
        self.wall_clock = wall_clock or date.today()
        self.entity_id = entity_id
        self._batch_min_confidence: Optional[float] = None

    def generate_report(
        self,
        statement_type: str,
        variant: str,
        selected_quarter: Optional[str] = None,
        segment: Optional[str] = None,
    ) -> Optional[NLQResponse]:
        """Generate a financial report with comparison columns.

        Args:
            statement_type: "income_statement", "balance_sheet", or "cash_flow"
            variant: Period comparison variant (e.g., "full_year_act_vs_py")
            selected_quarter: Required for quarterly variants (e.g., "2025-Q3")

        Returns:
            NLQResponse with financial_statement_data, or error NLQResponse.
        """
        from src.nlq.services.period_engine import validate_statement_variant

        # 1. Validate statement+variant combo
        error = validate_statement_variant(statement_type, variant)
        if error:
            return NLQResponse(
                success=False,
                answer=error,
                confidence=0.0,
                parsed_intent="REPORT_QUERY",
                resolved_metric=statement_type,
                resolved_period="",
                error_code="INVALID_VARIANT",
                error_message=error,
            )

        # 2. Compute period comparison
        from src.nlq.services.period_engine import compute_comparison

        try:
            comparison = compute_comparison(variant, self.wall_clock, selected_quarter)
        except ValueError as exc:
            logger.error(
                "Period comparison failed for variant=%s, wall_clock=%s, "
                "selected_quarter=%s: %s",
                variant, self.wall_clock, selected_quarter, exc,
            )
            return NLQResponse(
                success=False,
                answer=str(exc),
                confidence=0.0,
                parsed_intent="REPORT_QUERY",
                resolved_metric=statement_type,
                resolved_period="",
                error_code="PERIOD_ERROR",
                error_message=str(exc),
            )

        # 3. Select line items based on statement type
        if statement_type == "income_statement":
            from src.nlq.core.composite_query import PL_LINE_ITEMS, LINE_ITEM_CONFIG
            line_items = PL_LINE_ITEMS
            item_config = LINE_ITEM_CONFIG
            title = "Income Statement"
        elif statement_type == "balance_sheet":
            line_items = BS_LINE_ITEMS
            item_config = BS_LINE_ITEM_CONFIG
            title = "Balance Sheet"
        elif statement_type == "cash_flow":
            line_items = SOCF_LINE_ITEMS
            item_config = SOCF_LINE_ITEM_CONFIG
            title = "Statement of Cash Flows"
        else:
            return NLQResponse(
                success=False,
                answer=f"Unknown statement type '{statement_type}'",
                confidence=0.0,
                parsed_intent="REPORT_QUERY",
                resolved_metric=statement_type,
                resolved_period="",
                error_code="INVALID_STATEMENT",
                error_message=(
                    f"Unknown statement type '{statement_type}'. "
                    "Valid: income_statement, balance_sheet, cash_flow"
                ),
            )

        # 4. Query metrics for left and right period columns (in parallel)
        dcl_filters = {"segment": segment} if segment else None
        with ThreadPoolExecutor(max_workers=2) as pool:
            left_future = pool.submit(propagate_context(self._query_periods), line_items, comparison.left_periods, dcl_filters)
            right_future = pool.submit(propagate_context(self._query_periods), line_items, comparison.right_periods, dcl_filters)
            left_values = left_future.result()
            right_values = right_future.result()

        # 5. Validate minimum data
        if not left_values:
            return NLQResponse(
                success=False,
                answer=f"No data available for {comparison.left_label}",
                confidence=0.0,
                parsed_intent="REPORT_QUERY",
                resolved_metric=statement_type,
                resolved_period="",
                error_code="NO_DATA",
                error_message=f"No data available for {comparison.left_label}",
            )

        # 6. Build comparison columns
        periods_display = [comparison.left_label]
        if right_values:
            periods_display.append(comparison.right_label)
            periods_display.append("Variance")
            periods_display.append("Variance %")

        # 7. Build FinancialStatementLineItem list with comparison
        fs_line_items: List[FinancialStatementLineItem] = []
        for metric_id in line_items:
            if metric_id not in item_config:
                continue
            label, indent, fmt, is_sub = item_config[metric_id]

            left_val = left_values.get(metric_id)
            right_val = right_values.get(metric_id) if right_values else None

            values_dict: Dict[str, Optional[float]] = {
                comparison.left_label: left_val,
            }
            if right_values:
                values_dict[comparison.right_label] = right_val
                # Compute variance
                if (
                    left_val is not None
                    and right_val is not None
                    and right_val != 0
                ):
                    variance = round(left_val - right_val, 2)
                    variance_pct = round((variance / abs(right_val)) * 100, 1)
                    values_dict["Variance"] = variance
                    values_dict["Variance %"] = variance_pct
                else:
                    values_dict["Variance"] = None
                    values_dict["Variance %"] = None

            fs_line_items.append(FinancialStatementLineItem(
                label=label,
                key=metric_id,
                indent=indent,
                format=fmt,
                is_subtotal=is_sub,
                values=values_dict,
            ))

        from src.nlq.core.composite_query import _resolve_entity_name
        entity_name = _resolve_entity_name(self.entity_id)
        fs_data = FinancialStatementData(
            title=(
                f"{title} — {comparison.left_label} vs {comparison.right_label}"
                if right_values
                else f"{title} — {comparison.left_label}"
            ),
            entity=entity_name,
            periods=periods_display,
            line_items=fs_line_items,
            currency="USD",
            unit="millions",
        )

        # 8. Build text answer
        lines = [f"**{fs_data.title}**\n"]
        for li in fs_line_items:
            prefix = "  " * li.indent
            left_val = li.values.get(comparison.left_label)
            if left_val is not None:
                if li.format == "percent":
                    fv = f"{round(left_val, 1)}%"
                else:
                    fv = f"${round(left_val, 1)}M"
                line = f"{prefix}{li.label}: {fv}"
                right_val = (
                    li.values.get(comparison.right_label)
                    if right_values
                    else None
                )
                if right_val is not None:
                    variance = li.values.get("Variance")
                    if variance is not None:
                        sign = "+" if variance >= 0 else ""
                        if li.format == "percent":
                            line += (
                                f"  (PY: {round(right_val, 1)}%, "
                                f"{sign}{round(variance, 1)}pp)"
                            )
                        else:
                            line += (
                                f"  (PY: ${round(right_val, 1)}M, "
                                f"{sign}${round(variance, 1)}M)"
                            )
                lines.append(line)

        return NLQResponse(
            success=True,
            answer="\n".join(lines),
            value=None,
            unit=None,
            confidence=self._batch_min_confidence if self._batch_min_confidence is not None else 1.0,
            parsed_intent="REPORT_QUERY",
            resolved_metric=statement_type,
            resolved_period=(
                comparison.left_periods[0].label
                if comparison.left_periods
                else ""
            ),
            response_type="financial_statement",
            financial_statement_data=fs_data,
            data_source="live",
        )

    def _query_periods(
        self,
        line_items: List[str],
        periods: list,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Optional[float]]:
        """Query metrics across periods and aggregate.

        Uses batch fetching via DCLSemanticClientV2.get_metrics_batch()
        to minimize HTTP calls (one per DCL domain×period instead of one
        per metric×period).  Falls back to per-metric query_fn if the
        v2 batch client is unavailable or filters are present.

        For multi-period (full-year) columns:
          - Additive metrics (revenue, etc.) are summed.
          - Non-additive metrics (percentages) are averaged.
          - Point-in-time metrics (BS items) use the last period's value.

        Args:
            line_items: List of metric IDs to query.
            periods: List[PeriodInfo] from the period engine.

        Returns:
            Dict mapping metric_id -> aggregated value.
        """
        from src.nlq.knowledge.schema import is_additive_metric, is_point_in_time_metric

        if not periods:
            return {}

        # Try batch fetching via v2 client (fewer HTTP calls)
        if not filters:
            try:
                return self._query_periods_batch(line_items, periods)
            except Exception as exc:
                logger.warning(
                    "Batch fetch failed, falling back to per-metric queries: %s", exc,
                )

        # Fallback: per-metric queries with reduced concurrency
        results_map: Dict[tuple, Optional[float]] = {}

        def _fetch(metric_id: str, period_idx: int, period_label: str):
            try:
                if filters:
                    result = self.query_fn(metric_id, period_label, filters=filters)
                else:
                    result = self.query_fn(metric_id, period_label)
                if result is not None:
                    return (metric_id, period_idx, result.value)
            except Exception as exc:
                logger.warning(
                    "Report query failed for %s/%s: %s",
                    metric_id, period_label, exc,
                )
            return (metric_id, period_idx, None)

        with ThreadPoolExecutor(max_workers=min(8, len(line_items) * len(periods))) as pool:
            wrapped = propagate_context(_fetch)
            futures = [
                pool.submit(wrapped, metric_id, pi, period_info.label)
                for metric_id in line_items
                for pi, period_info in enumerate(periods)
            ]
            for future in as_completed(futures):
                metric_id, period_idx, value = future.result()
                results_map[(metric_id, period_idx)] = value

        return self._aggregate_results(line_items, periods, results_map)

    def _query_periods_batch(
        self,
        line_items: List[str],
        periods: list,
    ) -> Dict[str, Optional[float]]:
        """Batch-fetch metrics across periods using ONE browse-batch call.

        Makes a single HTTP call to DCL (no period filter), gets ALL triples
        for all domains/periods, then extracts metrics per period client-side.
        For combined entity, makes one call per entity (2 total).

        Tracks min confidence from source triples via self._batch_min_confidence.
        """
        from src.nlq.knowledge.schema import is_additive_metric, is_point_in_time_metric
        from src.nlq.services.dcl_semantic_client_v2 import get_semantic_client_v2

        v2 = get_semantic_client_v2()

        if self.entity_id == "combined":
            return self._query_periods_batch_combined(line_items, periods, v2)

        # ONE call for all periods — extract per-period values client-side
        period_labels = [p.label for p in periods]
        all_data, min_conf = v2.get_all_metrics_by_period(
            line_items, entity_id=self.entity_id,
        )
        self._batch_min_confidence = min_conf

        # Map results from "metric|period" keys to (metric, period_idx)
        results_map: Dict[tuple, Optional[float]] = {}
        for pi, period_label in enumerate(period_labels):
            for metric_id in line_items:
                key = f"{metric_id}|{period_label}"
                if key in all_data:
                    results_map[(metric_id, pi)] = all_data[key]

        return self._aggregate_results(line_items, periods, results_map)

    def _query_periods_batch_combined(
        self,
        line_items: List[str],
        periods: list,
        v2,
    ) -> Dict[str, Optional[float]]:
        """Batch-fetch for combined entity — one browse-batch call per entity.

        Makes N calls (one per entity, typically 2) instead of N×P calls.
        Each call returns all periods' data. Then aggregates across entities.
        """
        from src.nlq.knowledge.schema import is_additive_metric
        from src.nlq.core.entity_registry import get_entity_registry

        registry = get_entity_registry()
        entity_ids = registry.get_entity_ids_sync()
        if not entity_ids:
            logger.error("No entities registered — cannot build combined report")
            return {}

        period_labels = [p.label for p in periods]

        # One browse-batch call per entity (parallelized, typically 2 calls)
        entity_data: Dict[str, dict] = {}  # entity_id -> {metric|period: value}
        confidence_scores: list = []

        def _fetch_entity(eid: str):
            all_data, min_conf = v2.get_all_metrics_by_period(
                line_items, entity_id=eid,
            )
            return eid, all_data, min_conf

        with ThreadPoolExecutor(max_workers=len(entity_ids)) as pool:
            wrapped = propagate_context(_fetch_entity)
            futures = [pool.submit(wrapped, eid) for eid in entity_ids]
            for future in as_completed(futures):
                eid, all_data, min_conf = future.result()
                entity_data[eid] = all_data
                confidence_scores.append(min_conf)

        if confidence_scores:
            self._batch_min_confidence = min(confidence_scores)

        # Aggregate across entities for each (metric, period) slot
        results_map: Dict[tuple, Optional[float]] = {}
        for pi, period_label in enumerate(period_labels):
            for metric_id in line_items:
                entity_values = []
                for eid in entity_ids:
                    data = entity_data.get(eid, {})
                    val = data.get(f"{metric_id}|{period_label}")
                    if val is not None:
                        entity_values.append(val)

                if entity_values:
                    if is_additive_metric(metric_id):
                        results_map[(metric_id, pi)] = sum(entity_values)
                    else:
                        results_map[(metric_id, pi)] = (
                            sum(entity_values) / len(entity_values)
                        )

        return self._aggregate_results(line_items, periods, results_map)

    @staticmethod
    def _aggregate_results(
        line_items: List[str],
        periods: list,
        results_map: Dict[tuple, Optional[float]],
    ) -> Dict[str, Optional[float]]:
        """Aggregate per-period results into a single value per metric."""
        from src.nlq.knowledge.schema import is_additive_metric, is_point_in_time_metric

        aggregated: Dict[str, Optional[float]] = {}
        for metric_id in line_items:
            values_for_periods: List[float] = []
            for pi in range(len(periods)):
                val = results_map.get((metric_id, pi))
                if val is not None:
                    values_for_periods.append(val)

            if values_for_periods:
                if len(periods) > 1:
                    if is_additive_metric(metric_id):
                        aggregated[metric_id] = round(sum(values_for_periods), 2)
                    elif is_point_in_time_metric(metric_id):
                        aggregated[metric_id] = round(values_for_periods[-1], 2)
                    else:
                        aggregated[metric_id] = round(
                            sum(values_for_periods) / len(values_for_periods), 2
                        )
                else:
                    aggregated[metric_id] = round(values_for_periods[0], 2)

        return aggregated
