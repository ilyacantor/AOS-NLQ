"""
Fact base loader and query interface for AOS-NLQ.

The fact base contains the actual financial data that queries run against.
It supports both quarterly and annual data with various period formats.

Handles:
- Loading fact base from JSON
- Period format normalization
- Data existence checks
- Single metric/period queries
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


class FactBase:
    """
    Financial fact base for NLQ queries.

    Loads financial data from JSON and provides query interface.
    """

    def __init__(self):
        """Initialize empty fact base."""
        self._data: Dict[str, Any] = {}
        self._raw_data: Dict[str, Any] = {}  # Store raw data for dimensional breakdowns
        self._periods: Set[str] = set()
        self._metrics: Set[str] = set()
        self._loaded = False

    def load(self, filepath: Union[str, Path]) -> None:
        """
        Load fact base from JSON file.

        Args:
            filepath: Path to the fact base JSON file

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Fact base not found: {filepath}")

        with open(filepath, "r") as f:
            raw_data = json.load(f)

        self._raw_data = raw_data  # Store raw data for dimensional breakdowns
        self._process_data(raw_data)
        self._loaded = True
        logger.info(f"Loaded fact base with {len(self._periods)} periods and {len(self._metrics)} metrics")

    def _process_data(self, raw_data: Dict) -> None:
        """Process raw JSON into queryable format."""
        # Handle actual fact_base.json structure with "quarterly" and "annual"
        if "quarterly" in raw_data:
            self._process_quarterly_array(raw_data["quarterly"])
        if "annual" in raw_data:
            self._process_annual_dict(raw_data["annual"])

        # Fallback for other structures
        if not self._data:
            if "quarterly_data" in raw_data:
                self._process_quarterly_data(raw_data["quarterly_data"])
            elif "periods" in raw_data:
                self._process_periods_data(raw_data["periods"])
            else:
                # Assume top-level is period -> metrics mapping
                self._data = raw_data
                self._extract_metadata()

    def _process_quarterly_array(self, quarterly_data: List[Dict]) -> None:
        """Process quarterly data array with 'period' field."""
        for entry in quarterly_data:
            # Use the 'period' field directly if available
            period_key = entry.get("period")
            if not period_key:
                # Fallback to constructing from year/quarter
                year = entry.get("year")
                quarter = entry.get("quarter")
                if year and quarter:
                    # Handle quarter as string like "Q1" or integer
                    q = quarter if isinstance(quarter, str) else f"Q{quarter}"
                    q = q.replace("Q", "")  # Get just the number
                    period_key = f"{year}-Q{q}"

            if period_key:
                self._periods.add(period_key)
                self._data[period_key] = {}

                for key, value in entry.items():
                    if key not in ("year", "quarter", "period"):
                        metric_key = key.lower().replace(" ", "_")
                        self._data[period_key][metric_key] = value
                        self._metrics.add(metric_key)

    def _process_annual_dict(self, annual_data: Dict) -> None:
        """Process annual data dict with year keys."""
        for year_key, metrics in annual_data.items():
            self._periods.add(year_key)
            self._data[year_key] = {}

            for metric_name, value in metrics.items():
                metric_key = metric_name.lower().replace(" ", "_")
                self._data[year_key][metric_key] = value
                self._metrics.add(metric_key)

    def _process_quarterly_data(self, quarterly_data: List[Dict]) -> None:
        """Process quarterly data array format (legacy)."""
        for entry in quarterly_data:
            year = entry.get("year")
            quarter = entry.get("quarter")

            if year and quarter:
                period_key = f"{year}-Q{quarter}"
                self._periods.add(period_key)

                self._data[period_key] = {}
                for key, value in entry.items():
                    if key not in ("year", "quarter", "period"):
                        metric_key = key.lower().replace(" ", "_")
                        self._data[period_key][metric_key] = value
                        self._metrics.add(metric_key)

                annual_key = str(year)
                if annual_key not in self._data:
                    self._data[annual_key] = {}
                    self._periods.add(annual_key)

    def _process_periods_data(self, periods_data: Dict) -> None:
        """Process periods dict format."""
        for period_key, metrics in periods_data.items():
            self._periods.add(period_key)
            self._data[period_key] = {}

            for metric_name, value in metrics.items():
                metric_key = metric_name.lower().replace(" ", "_")
                self._data[period_key][metric_key] = value
                self._metrics.add(metric_key)

    def _extract_metadata(self) -> None:
        """Extract periods and metrics from loaded data."""
        for period_key, metrics in self._data.items():
            if isinstance(metrics, dict):
                self._periods.add(period_key)
                for metric_name in metrics.keys():
                    self._metrics.add(metric_name.lower().replace(" ", "_"))

    @property
    def available_metrics(self) -> Set[str]:
        """Get set of all available metric names."""
        return self._metrics.copy()

    @property
    def available_periods(self) -> Set[str]:
        """Get set of all available period keys."""
        return self._periods.copy()

    def has_period(self, period_key: str) -> bool:
        """
        Check if data exists for a period.

        Args:
            period_key: Period key like "2024" or "2025-Q4"

        Returns:
            True if data exists for this period
        """
        normalized = self._normalize_period_key(period_key)
        return normalized in self._data

    def has_metric(self, metric_name: str) -> bool:
        """
        Check if a metric exists in the fact base.

        Args:
            metric_name: Canonical metric name

        Returns:
            True if metric exists
        """
        return metric_name.lower() in self._metrics

    def query(self, metric: str, period: str) -> Optional[Any]:
        """
        Query a single metric for a single period.

        Args:
            metric: Canonical metric name (e.g., "revenue")
            period: Period key (e.g., "2024" or "2025-Q4")

        Returns:
            Metric value if found, None otherwise

        CRITICAL: Returns None if no data - caller must handle this case.
        """
        normalized_period = self._normalize_period_key(period)
        normalized_metric = metric.lower().replace(" ", "_")

        if normalized_period not in self._data:
            return None

        period_data = self._data[normalized_period]
        if not isinstance(period_data, dict):
            return None

        return period_data.get(normalized_metric)

    def query_annual(self, metric: str, year: int) -> Optional[Any]:
        """
        Query annual data, aggregating quarterly if needed.

        Args:
            metric: Canonical metric name
            year: Year to query

        Returns:
            Annual value (sum of quarters for flow metrics, end of year for stock metrics)
        """
        # Try direct annual lookup first
        annual_key = str(year)
        if annual_key in self._data:
            result = self.query(metric, annual_key)
            if result is not None:
                return result

        # Aggregate from quarters
        quarters = [f"{year}-Q{q}" for q in range(1, 5)]
        values = []
        for q in quarters:
            val = self.query(metric, q)
            if val is not None:
                values.append(val)

        if not values:
            return None

        # Sum for income statement items, last value for balance sheet
        # This is a simplification - real implementation would check metric type
        return sum(values)

    def _normalize_period_key(self, period_key: str) -> str:
        """
        Normalize period key format.

        Handles variations like:
        - "2024-Q4", "2024_Q4", "Q4 2024" -> "2024-Q4"
        - "2024" -> "2024"
        """
        key = period_key.strip().upper()

        # Already in standard format
        if key in self._data:
            return key

        # Try lowercase
        key_lower = period_key.strip().lower()
        if key_lower in self._data:
            return key_lower

        # Handle Q4 2024 format
        import re
        match = re.match(r'Q(\d)\s*(\d{4})', key)
        if match:
            return f"{match.group(2)}-Q{match.group(1)}"

        # Handle 2024_Q4 format
        match = re.match(r'(\d{4})[-_]Q(\d)', key)
        if match:
            return f"{match.group(1)}-Q{match.group(2)}"

        return period_key

    def get_periods_for_year(self, year: int) -> List[str]:
        """Get all quarterly periods for a given year."""
        return [p for p in self._periods if p.startswith(str(year))]

    def to_dict(self) -> Dict:
        """Export fact base as dictionary."""
        return {
            "periods": list(self._periods),
            "metrics": list(self._metrics),
            "data": self._data,
        }
