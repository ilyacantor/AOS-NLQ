"""
Revenue variance bridge (waterfall) handler.

Decomposes year-over-year revenue change by region using live DCL
dimensional data. All data from DCL via the semantic client.
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


ROUNDING_TOLERANCE = 0.5  # $M


class BridgeHandler:
    """Builds a revenue variance bridge by querying DCL for regional revenue."""

    def __init__(
        self,
        query_fn: Callable,
        year_start: str = "2024",
        year_end: str = "2025",
        entity_id: Optional[str] = None,
    ):
        self.query_fn = query_fn
        self.year_start = year_start
        self.year_end = year_end
        self.entity_id = entity_id

    def _query_annual(self, metric: str, year: str) -> Optional[float]:
        """Query a single metric for a full year via the existing metric resolver."""
        result = self.query_fn(metric, year)
        if result is None:
            return None
        return result.value

    def _query_regional_revenue(self, year: str) -> Dict[str, float]:
        """Query revenue by region for a full year from DCL.

        Returns dict mapping region name -> annual revenue value.
        """
        from src.nlq.services.dcl_semantic_client import get_semantic_client
        client = get_semantic_client()
        result = client.query(
            metric="revenue",
            dimensions=["region"],
            time_range={"period": year, "granularity": "quarterly"},
            entity_id=self.entity_id,
        )

        if result.get("error") or not result.get("data"):
            return {}

        # Sum quarterly values per region for the year
        region_totals: Dict[str, float] = {}
        for row in result.get("data", []):
            if not isinstance(row, dict):
                continue
            period = str(row.get("period", ""))
            if year not in period:
                continue
            dims = row.get("dimensions") or {}
            region = dims.get("region", "Unknown")
            value = row.get("value")
            if value is not None:
                region_totals[region] = region_totals.get(region, 0.0) + value

        return region_totals

    def execute(self) -> Optional[NLQResponse]:
        """Query revenue totals and regional breakdown, compute the waterfall."""
        fy_start_label = f"FY {self.year_start}"
        fy_end_label = f"FY {self.year_end}"

        # Query revenue totals
        rev_start = self._query_annual("revenue", self.year_start)
        rev_end = self._query_annual("revenue", self.year_end)

        if rev_start is None and rev_end is None:
            logger.warning("Bridge: could not resolve revenue for either period")
            return None

        # Query regional revenue for both years
        regions_start = self._query_regional_revenue(self.year_start)
        regions_end = self._query_regional_revenue(self.year_end)

        # Compute per-region deltas
        all_regions = sorted(set(regions_start.keys()) | set(regions_end.keys()))
        region_deltas: List[Tuple[str, float]] = []
        for region in all_regions:
            start_val = regions_start.get(region, 0.0)
            end_val = regions_end.get(region, 0.0)
            delta = round(end_val - start_val, 2)
            region_deltas.append((region, delta))

        # Sort by absolute delta descending (largest movers first)
        region_deltas.sort(key=lambda x: abs(x[1]), reverse=True)

        # Build bars
        bars: List[BridgeChartBar] = []

        # Bar 1: Start total
        bars.append(BridgeChartBar(
            label=f"{fy_start_label} Revenue",
            value=rev_start,
            type="total",
            running_total=rev_start,
        ))

        # Regional driver bars
        running = rev_start if rev_start is not None else 0.0
        for region, delta in region_deltas:
            bar_type = "increase" if delta >= 0 else "decrease"
            running = round(running + delta, 2)
            bars.append(BridgeChartBar(
                label=f"{region} Growth",
                value=delta,
                type=bar_type,
                running_total=round(running, 2),
            ))

        # Check rounding gap
        if rev_end is not None and rev_start is not None:
            gap = round(rev_end - running, 2)
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

        # Determine data source
        first_result = self.query_fn("revenue", self.year_end)
        data_source = first_result.data_source if first_result else None

        bridge_data = BridgeChartData(
            bridge_type="revenue",
            title=f"Revenue Bridge: {fy_start_label} → {fy_end_label}",
            subtitle="All amounts in $M",
            period_start=fy_start_label,
            period_end=fy_end_label,
            start_value=rev_start,
            end_value=rev_end,
            bars=bars,
            data_source=data_source,
        )

        # Build text answer
        total_change = round(rev_end - rev_start, 1) if rev_start and rev_end else None
        pct_change = round(total_change / rev_start * 100, 1) if total_change and rev_start else None
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
        if total_change is not None:
            sign = "+" if total_change >= 0 else ""
            lines.append(f"\nChange: {sign}${total_change:.1f}M ({sign}{pct_change:.1f}%)")

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
