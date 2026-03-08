"""
Revenue variance bridge (waterfall) handler.

Decomposes year-over-year revenue change into New Logo, Expansion,
and Renewal drivers. All data from DCL via _build_simple_metric_result.
"""

import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

from src.nlq.models.response import (
    NLQResponse,
    BridgeChartData,
    BridgeChartBar,
)

logger = logging.getLogger(__name__)

# ── Intent detection ──────────────────────────────────────────────────────

_BRIDGE_PATTERNS = [
    re.compile(r"revenue\s+(bridge|waterfall|walk|drivers?)", re.IGNORECASE),
    re.compile(r"(why|what).*(revenue|rev).*(incr\w*|decr\w*|change\w*|grow\w*|drop\w*|move\w*|go\s+up|go\s+down|went\s+up|went\s+down|fell|rise|risen|rose|jump\w*|spike\w*|dip\w*|decline\w*|shrink\w*|shrunk)", re.IGNORECASE),
    re.compile(r"(drove|driving|explain|decompose|break\s*down).*(revenue|rev)", re.IGNORECASE),
    re.compile(r"revenue\s+growth\s+drivers?", re.IGNORECASE),
    re.compile(r"(what.s|what\s+is)\s+driving.*(revenue|rev)", re.IGNORECASE),
    re.compile(r"walk\s+me\s+through\s+revenue", re.IGNORECASE),
    re.compile(r"(what\s+changed|what.s\s+changed)\s+in\s+revenue", re.IGNORECASE),
]

# Negative patterns — must NOT match these (they have their own handlers)
_BRIDGE_NEGATIVE = [
    re.compile(r"^(what.s|what\s+is)\s+revenue\??$", re.IGNORECASE),
    re.compile(r"revenue\s+by\s+(quarter|region|segment)", re.IGNORECASE),
]


def is_bridge_query(question: str) -> Optional[str]:
    """Return bridge type if question is a bridge/waterfall request, else None."""
    for neg in _BRIDGE_NEGATIVE:
        if neg.search(question):
            return None
    for pat in _BRIDGE_PATTERNS:
        if pat.search(question):
            return "revenue"
    return None


# ── Bridge metrics ────────────────────────────────────────────────────────

BRIDGE_DRIVERS = [
    ("new_logo_revenue", "New Logo Growth"),
    ("expansion_revenue", "Expansion Growth"),
    ("renewal_revenue", "Renewal Change"),
]

ROUNDING_TOLERANCE = 0.5  # $M


class BridgeHandler:
    """Builds a revenue variance bridge by querying DCL for driver metrics."""

    def __init__(
        self,
        query_fn: Callable,
        year_start: str = "2024",
        year_end: str = "2025",
    ):
        self.query_fn = query_fn
        self.year_start = year_start
        self.year_end = year_end

    def _query_annual(self, metric: str, year: str) -> Optional[float]:
        """Query a single metric for a full year via the existing metric resolver."""
        result = self.query_fn(metric, year)
        if result is None:
            return None
        return result.value

    def execute(self) -> Optional[NLQResponse]:
        """Query all bridge metrics and compute the waterfall."""
        fy_start_label = f"FY {self.year_start}"
        fy_end_label = f"FY {self.year_end}"

        # Query revenue totals
        rev_start = self._query_annual("revenue", self.year_start)
        rev_end = self._query_annual("revenue", self.year_end)

        if rev_start is None and rev_end is None:
            logger.warning("Bridge: could not resolve revenue for either period")
            return None

        # Query driver metrics for both years
        driver_deltas: List[Tuple[str, str, Optional[float], Optional[float], Optional[float]]] = []
        for metric_key, label in BRIDGE_DRIVERS:
            val_start = self._query_annual(metric_key, self.year_start)
            val_end = self._query_annual(metric_key, self.year_end)
            if val_start is not None and val_end is not None:
                delta = round(val_end - val_start, 2)
            else:
                delta = None
            driver_deltas.append((metric_key, label, val_start, val_end, delta))

        # Build bars
        bars: List[BridgeChartBar] = []

        # Bar 1: Start total
        bars.append(BridgeChartBar(
            label=f"{fy_start_label} Revenue",
            value=rev_start,
            type="total",
            running_total=rev_start,
        ))

        # Driver bars
        running = rev_start if rev_start is not None else 0.0
        for _, label, _, _, delta in driver_deltas:
            if delta is not None:
                bar_type = "increase" if delta >= 0 else "decrease"
                running = round(running + delta, 2)
            else:
                bar_type = "increase"  # placeholder — value is null
            bars.append(BridgeChartBar(
                label=label,
                value=delta,
                type=bar_type,
                running_total=round(running, 2) if delta is not None else None,
            ))

        # Check rounding gap
        if rev_end is not None and rev_start is not None:
            expected_running = round(running, 2)
            actual_end = round(rev_end, 2)
            gap = round(actual_end - expected_running, 2)
            if abs(gap) > ROUNDING_TOLERANCE:
                running = round(running + gap, 2)
                bars.append(BridgeChartBar(
                    label="Other / Rounding",
                    value=gap,
                    type="increase" if gap >= 0 else "decrease",
                    running_total=running,
                ))

        # Bar N: End total
        bars.append(BridgeChartBar(
            label=f"{fy_end_label} Revenue",
            value=rev_end,
            type="total",
            running_total=rev_end,
        ))

        bridge_data = BridgeChartData(
            bridge_type="revenue",
            title=f"Revenue Bridge: {fy_start_label} → {fy_end_label}",
            subtitle="All amounts in $M",
            period_start=fy_start_label,
            period_end=fy_end_label,
            start_value=rev_start,
            end_value=rev_end,
            bars=bars,
        )

        # Determine data source from first successful query
        first_result = self.query_fn("revenue", self.year_end)
        data_source = first_result.data_source if first_result else None
        bridge_data.data_source = data_source

        # Build text answer
        lines = [f"**{bridge_data.title}**\n"]
        for bar in bars:
            if bar.value is not None:
                if bar.type == "total":
                    lines.append(f"  {bar.label}: ${bar.value:.1f}M")
                else:
                    sign = "+" if bar.value >= 0 else ""
                    lines.append(f"  {bar.label}: {sign}${bar.value:.1f}M")
            else:
                lines.append(f"  {bar.label}: Data unavailable")

        return NLQResponse(
            success=True,
            answer="\n".join(lines),
            value=None,
            unit="usd_millions",
            confidence=0.95,
            parsed_intent="BRIDGE_CHART",
            resolved_metric="revenue_bridge",
            resolved_period=f"{self.year_start}-{self.year_end}",
            response_type="bridge_chart",
            bridge_chart_data=bridge_data,
            data_source=data_source,
        )
