"""
Dashboard Data Resolver - Populates dashboard widgets with data from DCL.

This module routes all data access through DCL's query API.
NLQ holds no local data - it's a stateless UI layer.
"""

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from src.nlq.core.dates import current_year, current_quarter

from src.nlq.services.dcl_semantic_client import get_semantic_client
from src.nlq.knowledge.schema import get_metric_unit
from src.nlq.knowledge.display import get_display_name
from src.nlq.models.dashboard_schema import (
    DashboardSchema,
    MetricBinding,
    Widget,
    WidgetType,
)

logger = logging.getLogger(__name__)


def _quarter_range(num_quarters: int) -> List[str]:
    """Return a list of quarter strings going back num_quarters from current quarter.
    E.g., _quarter_range(4) might return ['2025-Q2', '2025-Q3', '2025-Q4', '2026-Q1'].
    """
    cq = current_quarter()  # e.g. "2026-Q1"
    year, q = int(cq[:4]), int(cq[-1])
    quarters = []
    for _ in range(num_quarters):
        quarters.append(f"{year}-Q{q}")
        q -= 1
        if q == 0:
            q = 4
            year -= 1
    quarters.reverse()
    return quarters


class DashboardDataResolver:
    """
    Resolves dashboard widget data from DCL.

    All data access goes through DCL's query API.
    """

    def __init__(self, fact_base=None):
        """Initialize resolver. fact_base param kept for backwards compatibility but ignored."""
        self.dcl_client = get_semantic_client()
        self._provenance: Optional[Dict[str, Any]] = None

    @property
    def provenance(self) -> Optional[Dict[str, Any]]:
        """Run provenance from the first successful DCL query, for the ProvenanceBadge."""
        return self._provenance

    def resolve_dashboard_data(
        self,
        schema: DashboardSchema,
        reference_year: Optional[str] = None,
        active_filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Resolve data for all widgets in a dashboard schema.

        Args:
            schema: The dashboard schema with widget definitions
            reference_year: The year to query for annual data
            active_filters: Optional dict of dimension -> value filters to apply

        Returns:
            Dict mapping widget_id to widget data
        """
        reference_year = reference_year or current_year()
        widget_data = {}
        filters = active_filters or {}

        def _resolve_one(widget: Widget) -> tuple:
            """Resolve a single widget, returning (widget_id, data_dict)."""
            try:
                data = self._resolve_widget_data(widget, reference_year, filters)
                if isinstance(data, dict) and data.get("error"):
                    logger.error(
                        f"Widget {widget.id} data resolution failed: {data['error']}"
                    )
                    return widget.id, {
                        "error": data["error"],
                        "widget_id": widget.id,
                        "status": "dcl_error",
                    }
                return widget.id, data
            except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
                logger.error(f"Error resolving data for widget {widget.id}: {e}")
                return widget.id, {
                    "error": str(e),
                    "widget_id": widget.id,
                    "status": "resolution_error",
                }

        ctx = contextvars.copy_context()
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(ctx.run, _resolve_one, w) for w in schema.widgets]
            for future in futures:
                wid, data = future.result()
                widget_data[wid] = data

        return widget_data

    def _resolve_widget_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve data for a single widget based on its type."""
        filters = filters or {}

        widget_type = widget.type
        if isinstance(widget_type, str):
            widget_type_str = widget_type
        else:
            widget_type_str = widget_type.value

        if widget_type_str == "kpi_card":
            return self._resolve_kpi_data(widget, reference_year, filters)
        elif widget_type_str in ["line_chart", "area_chart"]:
            return self._resolve_time_series_data(widget, reference_year, filters)
        elif widget_type_str in ["bar_chart", "horizontal_bar"]:
            return self._resolve_category_data(widget, reference_year, filters)
        elif widget_type_str == "stacked_bar":
            return self._resolve_stacked_data(widget, reference_year, filters)
        elif widget_type_str == "donut_chart":
            return self._resolve_donut_data(widget, reference_year, filters)
        elif widget_type_str == "data_table":
            return self._resolve_table_data(widget, reference_year, filters)
        elif widget_type_str == "map":
            return self._resolve_map_data(widget, reference_year, filters)
        else:
            return {"loading": False, "error": f"Unsupported widget type: {widget_type_str}"}

    def _query_dcl(
        self,
        metric: str,
        dimensions: List[str] = None,
        filters: Dict[str, Any] = None,
        time_range: Dict[str, Any] = None,
        grain: str = None,
    ) -> Dict[str, Any]:
        """Execute query against DCL and handle errors."""
        from src.nlq.knowledge.synonyms import normalize_metric
        from src.nlq.services.dcl_semantic_client import get_entity_id
        canonical = normalize_metric(metric)
        if canonical != metric:
            logger.info(f"Resolved metric alias '{metric}' -> '{canonical}'")
        result = self.dcl_client.query(
            metric=canonical,
            dimensions=dimensions,
            filters=filters,
            time_range=time_range,
            grain=grain,
            entity_id=get_entity_id(),
        )

        if result.get("status") == "error" or result.get("error"):
            logger.warning(f"DCL query error for '{canonical}': {result.get('error')}")
        elif self._provenance is None and result.get("run_provenance"):
            # Capture provenance from the first successful DCL query (set-once)
            self._provenance = result["run_provenance"]

        return result

    def _resolve_kpi_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve KPI card data from DCL."""
        filters = filters or {}
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metric specified"}

        metric = metrics[0].metric
        cq = current_quarter()

        # Query DCL for latest quarter value (quarterly grain is most reliable
        # because DCL ingest data is stored at quarter grain)
        result = self._query_dcl(
            metric=metric,
            filters=filters,
            time_range={"period": cq, "granularity": "quarterly"},
        )

        if result.get("error") or not result.get("data"):
            # Retry with yearly grain as fallback
            logger.info(f"KPI quarterly query failed for '{metric}', retrying with yearly grain")
            result = self._query_dcl(
                metric=metric,
                filters=filters,
                time_range={"period": reference_year, "granularity": "yearly"},
            )
            if result.get("error") or not result.get("data"):
                return {"loading": False, "error": result.get("error", f"No data for '{metric}'")}

        # Extract value from DCL response
        value = self._extract_value_from_result(result)
        if value is None:
            return {"loading": False, "error": f"No data for '{metric}'"}

        # Get prior quarter for trend (best-effort — trend is optional)
        quarters = _quarter_range(8)
        prior_q = quarters[-2] if len(quarters) >= 2 else None
        trend = None
        if prior_q:
            prior_result = self._query_dcl(
                metric=metric,
                filters=filters,
                time_range={"period": prior_q, "granularity": "quarterly"},
            )
            prior_value = self._extract_value_from_result(prior_result)
            if prior_value is not None and prior_value != 0:
                pct_change = ((value - prior_value) / prior_value) * 100
                trend = {
                    "direction": "up" if pct_change > 0 else "down" if pct_change < 0 else "flat",
                    "percent_change": abs(round(pct_change, 1)),
                    "comparison_label": f"vs {prior_q}"
                }

        # Format value
        formatted_value = self._format_value(metric, value)

        # Get sparkline data (last 8 quarters)
        sparkline_data = self._query_quarters_sparkline(metric, filters, 8)

        # Include filter info in response
        filter_label = None
        if filters:
            filter_label = ", ".join(f"{k}: {v}" for k, v in filters.items())

        return {
            "loading": False,
            "value": value,
            "formatted_value": formatted_value,
            "trend": trend,
            "sparkline_data": sparkline_data,
            "active_filter": filter_label,
        }

    def _query_quarters_sparkline(self, metric: str, filters: dict, num_quarters: int) -> Optional[List[float]]:
        """Query individual quarters and build sparkline data."""
        quarters = _quarter_range(num_quarters)
        values = []
        for q in quarters:
            result = self._query_dcl(
                metric=metric,
                filters=filters,
                time_range={"period": q, "granularity": "quarterly"},
            )
            val = self._extract_value_from_result(result)
            values.append(round(val, 1) if val is not None else 0)
        # Only return if we got at least some real data
        if any(v != 0 for v in values):
            return values
        return None

    def _resolve_time_series_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve time series data for line/area charts."""
        filters = filters or {}
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metric specified"}

        metric = metrics[0].metric

        # Query each quarter individually to build the time series
        quarters = _quarter_range(8)
        data_points = []
        for q in quarters:
            result = self._query_dcl(
                metric=metric,
                filters=filters,
                time_range={"period": q, "granularity": "quarterly"},
            )
            val = self._extract_value_from_result(result)
            if val is not None:
                # Format label nicely (2025-Q1 -> Q1 2025)
                parts = q.split("-")
                label = f"{parts[1]} {parts[0]}" if len(parts) == 2 else q
                data_points.append({"label": label, "value": round(val, 1)})

        if not data_points:
            return {"loading": False, "error": f"No time series data for '{metric}'"}

        return {
            "loading": False,
            "categories": [p["label"] for p in data_points],
            "series": [{
                "name": get_display_name(metric),
                "data": data_points,
            }]
        }

    def _resolve_category_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve categorical data for bar charts."""
        filters = filters or {}
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metric specified"}

        metric = metrics[0].metric
        dimensions = widget.data.dimensions
        dimension = dimensions[0].dimension if dimensions else None
        if dimension is None:
            # Multi-metric comparison bar chart (no dimensional breakdown)
            # Each metric becomes a category with its total value
            if len(metrics) > 1:
                return self._resolve_multi_metric_comparison(metrics, reference_year, filters)
            return {"loading": False, "error": f"No dimension specified for '{metric}' breakdown"}

        # Validate dimension — if it has no data, try valid dimensions for this metric
        breakdown = self._try_dimensional_query(metric, dimension, filters, reference_year)

        if not breakdown:
            # Requested dimension failed — try each valid dimension as fallback
            valid_dims = self.dcl_client.get_valid_dimensions(metric) if hasattr(self.dcl_client, 'get_valid_dimensions') else []
            for fallback_dim in valid_dims:
                if fallback_dim != dimension:
                    logger.info(f"Dimension '{dimension}' failed for '{metric}', trying '{fallback_dim}'")
                    breakdown = self._try_dimensional_query(metric, fallback_dim, filters, reference_year)
                    if breakdown:
                        dimension = fallback_dim
                        break

        if not breakdown:
            return {"loading": False, "error": f"No {dimension} breakdown data for '{metric}'"}

        return {
            "loading": False,
            "categories": [p["label"] for p in breakdown],
            "series": [{
                "name": get_display_name(metric),
                "data": breakdown,
            }],
            "clickable": True,
            "filter_dimension": dimension,
        }

    def _try_dimensional_query(
        self,
        metric: str,
        dimension: str,
        filters: Dict[str, str],
        reference_year: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Try querying DCL for a dimensional breakdown, returning data points or None."""
        cq = current_quarter()
        result = self._query_dcl(
            metric=metric,
            dimensions=[dimension],
            filters=filters,
            time_range={"period": cq},
        )

        if result.get("error") or not result.get("data"):
            logger.info(f"Category quarterly query failed for '{metric}' by '{dimension}', retrying with yearly")
            result = self._query_dcl(
                metric=metric,
                dimensions=[dimension],
                filters=filters,
                time_range={"period": reference_year},
            )
            if result.get("error"):
                return None

        return self._extract_dimensional_data(result, dimension, metric) or None

    def _resolve_multi_metric_comparison(
        self,
        metrics: List[MetricBinding],
        reference_year: str,
        filters: Dict[str, str],
    ) -> Dict[str, Any]:
        """Resolve multi-metric comparison bar chart — each metric is a category."""
        cq = current_quarter()
        data_points = []
        for metric_binding in metrics:
            metric = metric_binding.metric
            result = self._query_dcl(
                metric=metric,
                filters=filters,
                time_range={"period": cq, "granularity": "quarterly"},
            )
            value = self._extract_value_from_result(result)
            if value is not None:
                data_points.append({
                    "label": get_display_name(metric),
                    "value": round(value, 1),
                })

        if not data_points:
            return {"loading": False, "error": "No data for any of the requested metrics"}

        return {
            "loading": False,
            "categories": [p["label"] for p in data_points],
            "series": [{
                "name": "Metrics",
                "data": data_points,
            }],
        }

    def _resolve_stacked_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve stacked bar chart data."""
        filters = filters or {}
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metrics specified"}

        quarters = _quarter_range(4)
        categories = [q.split("-")[1] for q in quarters]  # ["Q1", "Q2", ...]
        series = []

        for metric_binding in metrics[:3]:
            metric = metric_binding.metric
            data_points = []
            for q in quarters:
                result = self._query_dcl(
                    metric=metric,
                    filters=filters,
                    time_range={"period": q, "granularity": "quarterly"},
                )
                val = self._extract_value_from_result(result)
                label = q.split("-")[1]  # "Q1"
                data_points.append({"label": label, "value": round(val, 1) if val else 0})

            series.append({
                "name": get_display_name(metric),
                "data": data_points,
            })

        return {
            "loading": False,
            "categories": categories,
            "series": series,
        }

    def _resolve_donut_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve donut chart data."""
        return self._resolve_category_data(widget, reference_year, filters)

    def _resolve_table_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve data table content."""
        filters = filters or {}
        metrics = widget.data.metrics
        dimensions = widget.data.dimensions
        dimension = dimensions[0].dimension if dimensions else "quarter"

        rows = []

        if dimension == "quarter":
            quarters = _quarter_range(4)
            for q in quarters:
                row = {"quarter": q.replace("-", " ")}

                for metric_binding in metrics:
                    metric = metric_binding.metric
                    result = self._query_dcl(
                        metric=metric,
                        filters=filters,
                        time_range={"period": q, "granularity": "quarterly"},
                    )
                    val = self._extract_value_from_result(result)
                    row[metric] = round(val, 1) if val else None

                rows.append(row)
        else:
            # Get dimensional breakdown using current quarter
            cq = current_quarter()
            for metric_binding in metrics[:1]:  # Primary metric
                metric = metric_binding.metric
                result = self._query_dcl(
                    metric=metric,
                    dimensions=[dimension],
                    filters=filters,
                    time_range={"period": cq},
                )
                if result.get("error") or not result.get("data"):
                    logger.info(f"Table quarterly query failed for '{metric}', retrying with yearly")
                    result = self._query_dcl(
                        metric=metric,
                        dimensions=[dimension],
                        filters=filters,
                        time_range={"period": reference_year},
                    )

                breakdown = self._extract_dimensional_data(result, dimension, metric)
                for item in breakdown:
                    row = {dimension: item["label"]}
                    row[metric] = item["value"]
                    rows.append(row)

        return {
            "loading": False,
            "rows": rows,
        }

    def _resolve_map_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve geographic map data showing revenue by region."""
        filters = filters or {}
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metric specified"}

        metric = metrics[0].metric

        # Query DCL for regional breakdown using current quarter
        cq = current_quarter()
        result = self._query_dcl(
            metric=metric,
            dimensions=["region"],
            filters=filters,
            time_range={"period": cq},
        )

        if result.get("error"):
            return {"loading": False, "error": result["error"]}

        # Extract regional data
        regional_data = self._extract_dimensional_data(result, "region", metric)

        if not regional_data:
            return {"loading": False, "error": f"No regional data for '{metric}'"}

        # Calculate total and percentages
        total = sum(item.get("value", 0) for item in regional_data)
        regions = []

        for item in regional_data:
            value = item.get("value", 0)
            percentage = (value / total * 100) if total > 0 else 0
            regions.append({
                "region": item.get("label", "").upper(),
                "value": round(value, 2),
                "percentage": round(percentage, 1),
            })

        # Sort by value descending
        regions.sort(key=lambda r: r["value"], reverse=True)

        return {
            "loading": False,
            "map_data": {
                "total": round(total, 2),
                "metric": metric,
                "regions": regions,
            },
            # Also provide series format for fallback rendering
            "series": [{
                "name": get_display_name(metric),
                "data": [{"label": r["region"], "value": r["value"]} for r in regions],
            }],
            "categories": [r["region"] for r in regions],
        }

    # =========================================================================
    # HELPER METHODS FOR EXTRACTING DATA FROM DCL RESPONSES
    # =========================================================================

    def _extract_value_from_result(self, result: Dict[str, Any]) -> Optional[float]:
        """Extract a single value from DCL query result."""
        if result.get("error"):
            raise RuntimeError(f"DCL query error: {result['error']}")

        data = result.get("data", [])
        if not data:
            return None

        # Handle different response formats
        if isinstance(data, list):
            if len(data) > 0:
                item = data[-1] if len(data) > 1 else data[0]  # Latest value
                if isinstance(item, dict):
                    return item.get("value", item.get("val"))
                return item
        elif isinstance(data, dict):
            return data.get("value", data.get("val"))
        elif isinstance(data, (int, float)):
            return data

        return None

    def _extract_time_series(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract time series data points from DCL result."""
        if result.get("error"):
            raise RuntimeError(f"DCL query error: {result['error']}")

        data = result.get("data", [])
        if not data:
            return []

        data_points = []
        for item in data:
            if isinstance(item, dict):
                period = item.get("period", item.get("label", ""))
                value = item.get("value", item.get("val", 0))

                # Format label nicely (Q1 2024 -> Q1 2024)
                if "-Q" in str(period):
                    parts = period.split("-")
                    label = f"{parts[1]} {parts[0]}" if len(parts) == 2 else period
                else:
                    label = str(period)

                data_points.append({
                    "label": label,
                    "value": round(value, 1) if value else 0
                })

        return data_points

    def _extract_time_series_values(self, result: Dict[str, Any]) -> Optional[List[float]]:
        """Extract just the values from time series for sparklines."""
        data_points = self._extract_time_series(result)
        if not data_points:
            return None
        return [p["value"] for p in data_points]

    def _extract_quarterly_values(
        self, result: Dict[str, Any], reference_year: str
    ) -> List[Dict[str, Any]]:
        """Extract quarterly values from result."""
        data_points = self._extract_time_series(result)

        # If we got time series data, filter to requested year
        if data_points:
            return data_points[-4:] if len(data_points) > 4 else data_points

        # No data available — return empty list (callers handle empty gracefully)
        return []

    def _extract_dimensional_data(
        self, result: Dict[str, Any], dimension: str, metric: str = None
    ) -> List[Dict[str, Any]]:
        """Extract dimensional breakdown from DCL result."""
        if result.get("error"):
            raise RuntimeError(f"DCL query error: {result['error']}")

        data = result.get("data", [])
        if not data:
            return []

        breakdown = []
        total = 0

        for item in data:
            if isinstance(item, dict):
                # DCL returns dimensions nested: {"dimensions": {"region": "AMER"}, "value": 24.0}
                # Local/legacy returns flat: {"region": "AMER", "value": 24.0}
                dims_dict = item.get("dimensions", {})
                label = (
                    (dims_dict.get(dimension) if isinstance(dims_dict, dict) else None)
                    or item.get(dimension)
                    or item.get("label", item.get("name", ""))
                )
                value = item.get("value", item.get("val", 0))

                # Handle nested value dicts (e.g., {'pipeline': 6.4, 'qualified': 3.84})
                if isinstance(value, dict):
                    # Try to get the metric value, or first numeric value
                    if metric in value:
                        value = value[metric]
                    else:
                        # Get first numeric value from the dict
                        for v in value.values():
                            if isinstance(v, (int, float)):
                                value = v
                                break
                        else:
                            value = 0

                if label and value is not None:
                    breakdown.append({"label": str(label), "value": round(value, 2)})
                    total += value

        # Add ratios
        for item in breakdown:
            item["ratio"] = round(item["value"] / total, 2) if total > 0 else 0

        return breakdown

    def _format_value(self, metric: str, value: float) -> str:
        """Format a metric value for display."""
        unit = get_metric_unit(metric)

        if unit == "%":
            return f"{round(value, 1)}%"
        elif unit in ["USD millions", "$M"]:
            return f"${round(value, 1)}M"
        elif unit == "USD":
            return f"${round(value, 2)}"
        elif unit == "months":
            return f"{round(value, 1)} mo"
        elif unit == "x":
            return f"{round(value, 1)}x"
        elif unit == "days":
            return f"{int(value)} days"
        elif unit in ["people", "customers", "count"]:
            return f"{int(value):,}"
        else:
            return f"{round(value, 1)}"


def resolve_dashboard_with_data(
    schema: DashboardSchema,
    fact_base=None,  # Kept for backwards compatibility, ignored
    reference_year: str = "2025",
) -> Dict[str, Any]:
    """
    Convenience function to resolve a dashboard with its data.

    Returns the schema plus resolved widget data.
    """
    resolver = DashboardDataResolver()
    widget_data = resolver.resolve_dashboard_data(schema, reference_year)

    return {
        "schema": schema,
        "widget_data": widget_data,
    }
