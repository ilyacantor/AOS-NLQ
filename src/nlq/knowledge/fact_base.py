"""
FactBase - In-memory wrapper around fact_base.json for query and test use.

Provides:
- Loading from JSON file
- Metric lookup by period (quarterly and annual)
- Period and metric availability checks
"""

import json
from pathlib import Path
from typing import Dict, Optional, Set


class FactBase:
    """Read-only wrapper around the fact_base.json data."""

    def __init__(self):
        self._loaded = False
        self._quarterly_data: Dict[str, Dict[str, float]] = {}  # period -> {metric -> value}
        self._annual_data: Dict[str, Dict[str, float]] = {}     # year -> {metric -> value}
        self._all_metrics: Set[str] = set()
        self._all_periods: Set[str] = set()

    def load(self, path) -> None:
        """Load fact base from a JSON file."""
        if isinstance(path, str):
            path = Path(path)

        with open(path, 'r') as f:
            data = json.load(f)

        self._quarterly_data.clear()
        self._annual_data.clear()
        self._all_metrics.clear()
        self._all_periods.clear()

        # Load quarterly data
        for q in data.get("quarterly", []):
            period = q.get("period", f"{q.get('year')}-{q.get('quarter')}")
            metrics = {k: v for k, v in q.items()
                       if k not in ("period", "year", "quarter") and isinstance(v, (int, float))}
            self._quarterly_data[period] = metrics
            self._all_periods.add(period)
            self._all_metrics.update(metrics.keys())

        # Load annual data
        for year_str, metrics in data.get("annual", {}).items():
            if isinstance(metrics, dict):
                self._annual_data[year_str] = {
                    k: v for k, v in metrics.items() if isinstance(v, (int, float))
                }
                self._all_periods.add(year_str)
                self._all_metrics.update(self._annual_data[year_str].keys())

        self._loaded = True

    @property
    def available_periods(self) -> Set[str]:
        return self._all_periods.copy()

    @property
    def available_metrics(self) -> Set[str]:
        return self._all_metrics.copy()

    def has_period(self, period: str) -> bool:
        return period in self._all_periods

    def has_metric(self, metric: str) -> bool:
        metric_lower = metric.lower()
        return any(m.lower() == metric_lower for m in self._all_metrics)

    def query(self, metric: str, period: str) -> Optional[float]:
        """Get a single metric value for a specific period."""
        if not metric or not period:
            return None

        metric_lower = metric.lower()

        # Check quarterly data
        if period in self._quarterly_data:
            for m, v in self._quarterly_data[period].items():
                if m.lower() == metric_lower:
                    return v

        # Check annual data
        if period in self._annual_data:
            for m, v in self._annual_data[period].items():
                if m.lower() == metric_lower:
                    return v

        return None

    def query_annual(self, metric: str, year: int) -> Optional[float]:
        """Get annual data, aggregating quarterly data if needed."""
        year_str = str(year)

        # Try direct annual data first
        if year_str in self._annual_data:
            for m, v in self._annual_data[year_str].items():
                if m.lower() == metric.lower():
                    return v

        # Aggregate quarterly data
        quarters = [f"{year_str}-Q{q}" for q in range(1, 5)]
        values = []
        for q in quarters:
            val = self.query(metric, q)
            if val is not None:
                values.append(val)

        return sum(values) if values else None

    def _normalize_period_key(self, period: str) -> str:
        """Normalize period key format."""
        if not period:
            return period
        return period.upper() if "-q" in period.lower() else period
