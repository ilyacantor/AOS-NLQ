"""
Tenant Data Service for DCL.

Loads per-tenant metric data from data/tenants/{tenant_id}.json and
serves structured queries with support for:
  - Simple metric lookups (point queries)
  - Dimensional breakdowns (e.g., revenue by region)
  - Ranked queries with order_by and limit
  - Metric alias resolution (e.g., "uptime" → "uptime_pct")
  - Ingest statistics

This is the authoritative data path for the /api/dcl/query endpoint.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.nlq.config import get_tenant_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "tenants"


class TenantDataService:
    """Loads and queries tenant-specific metric data."""

    def __init__(self, tenant_id: str = None):
        self._tenant_id = tenant_id or get_tenant_id()
        self._data: Optional[Dict[str, Any]] = None
        self._load()

    def _load(self):
        """Load tenant data from JSON file."""
        path = _DATA_DIR / f"{self._tenant_id}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Tenant data file not found: {path}. "
                f"Ensure data/tenants/{self._tenant_id}.json exists."
            )
        try:
            with open(path, "r") as f:
                self._data = json.load(f)
            logger.info(
                f"Loaded tenant data for {self._data.get('tenant_id', self._tenant_id)}: "
                f"{len(self._data.get('quarterly', []))} quarters"
            )
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load tenant data: {e}")
            self._data = {}

    @property
    def current_period(self) -> str:
        return self._data.get("current_period", "2026-Q4")

    @property
    def metric_aliases(self) -> Dict[str, str]:
        return self._data.get("metric_aliases", {})

    def resolve_metric(self, metric: str) -> str:
        """Resolve metric aliases (e.g., 'uptime' → 'uptime_pct')."""
        return self.metric_aliases.get(metric, metric)

    def query(
        self,
        metric: str,
        dimensions: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a metric query against tenant data.

        Args:
            metric: Canonical metric ID or alias
            dimensions: Dimensions to break down by
            order_by: "asc" or "desc" for sorting
            limit: Max number of results
            period: Period to query (defaults to current_period)

        Returns:
            Dict with 'value', 'data', 'metric', 'period', 'status' keys
        """
        if not self._data:
            return {"error": "No tenant data loaded", "status": "error"}

        # Resolve metric alias
        resolved_metric = self.resolve_metric(metric)
        target_period = period or self.current_period

        # Dimensional query
        if dimensions:
            return self._query_dimensional(
                metric, resolved_metric, dimensions, order_by, limit, target_period
            )

        # Simple point query
        return self._query_point(metric, resolved_metric, target_period)

    def _query_point(
        self, original_metric: str, resolved_metric: str, period: str
    ) -> Dict[str, Any]:
        """Execute a simple point query for a single metric value."""
        quarterly = self._data.get("quarterly", [])

        for entry in quarterly:
            if entry.get("period") == period:
                if resolved_metric in entry:
                    value = entry[resolved_metric]
                    return {
                        "metric": original_metric,
                        "value": value,
                        "period": period,
                        "data": [{"period": period, "value": value}],
                        "status": "ok",
                    }

        return {
            "metric": original_metric,
            "value": None,
            "error": f"Metric '{resolved_metric}' not found for period {period}",
            "status": "not_found",
        }

    def _query_dimensional(
        self,
        original_metric: str,
        resolved_metric: str,
        dimensions: List[str],
        order_by: Optional[str],
        limit: Optional[int],
        period: str,
    ) -> Dict[str, Any]:
        """Execute a dimensional breakdown query."""
        dim = dimensions[0] if dimensions else None
        if not dim:
            return self._query_point(original_metric, resolved_metric, period)

        # Try multiple key patterns to find the dimensional data
        # Pattern: {metric}_by_{dimension}, {resolved_metric}_by_{dimension}
        candidates = [
            f"{original_metric}_by_{dim}",
            f"{resolved_metric}_by_{dim}",
        ]

        # Also try removing common suffixes: _pct, _rate, _score
        for suffix in ("_pct", "_rate", "_score", "_count", "_days", "_hours"):
            if resolved_metric.endswith(suffix):
                base = resolved_metric[: -len(suffix)]
                candidates.append(f"{base}_by_{dim}")

        # Also try the metric without "gross_" prefix
        if resolved_metric.startswith("gross_"):
            candidates.append(f"{resolved_metric[6:]}_by_{dim}")

        dim_data = None
        for key in candidates:
            if key in self._data:
                raw = self._data[key]
                if isinstance(raw, dict) and period in raw:
                    dim_data = raw[period]
                    break

        if dim_data is None:
            return {
                "metric": original_metric,
                "data": [],
                "error": f"No dimensional data for {original_metric} by {dim}",
                "status": "not_found",
            }

        # Convert dict to list of {dimension: name, value: val}
        data_list = []
        if isinstance(dim_data, dict):
            for name, value in dim_data.items():
                if name in ("Total", "total"):
                    continue
                data_list.append({dim: name, "value": value})

        # Sort if requested
        if order_by:
            reverse = order_by.lower() == "desc"
            data_list.sort(
                key=lambda x: x.get("value", 0)
                if isinstance(x.get("value"), (int, float))
                else 0,
                reverse=reverse,
            )

        # Limit
        if limit and limit > 0:
            data_list = data_list[:limit]

        return {
            "metric": original_metric,
            "data": data_list,
            "period": period,
            "status": "ok",
        }

    def get_ingest_stats(self) -> Dict[str, Any]:
        """Return ingest statistics for this tenant."""
        ingest = self._data.get("ingest", {})
        if not ingest:
            return {
                "unique_sources": 0,
                "total_rows_buffered": 0,
                "sources": [],
                "tenant": self._data.get("tenant_id", self._tenant_id),
            }

        return {
            "unique_sources": ingest.get("unique_sources", 0),
            "total_rows_buffered": ingest.get("total_rows_buffered", 0),
            "source_count": ingest.get("unique_sources", 0),
            "sources": [s.get("source_system") for s in ingest.get("sources", [])],
            "tenant": ingest.get("tenant", self._data.get("tenant_id", self._tenant_id)),
        }

    def get_ingest_runs(self) -> Dict[str, Any]:
        """Return detailed ingest run data for this tenant."""
        ingest = self._data.get("ingest", {})
        runs = ingest.get("runs", [])
        return {
            "runs": runs,
            "total_runs": len(runs),
            "total_rows": ingest.get("total_rows_buffered", 0),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_instance: Optional[TenantDataService] = None


def get_tenant_data_service(tenant_id: str = None) -> TenantDataService:
    """Get the singleton TenantDataService instance."""
    global _instance
    resolved = tenant_id or get_tenant_id()
    if _instance is None or _instance._tenant_id != resolved:
        _instance = TenantDataService(resolved)
    return _instance
