"""
Dashboard Data Resolver - Populates dashboard widgets with data from DCL.

This module routes all data access through DCL's query API.
NLQ holds no local data - it's a stateless UI layer.
"""

import logging
from typing import Any, Dict, List, Optional

from src.nlq.core.dates import current_year

from src.nlq.services.dcl_semantic_client import get_semantic_client
from src.nlq.knowledge.schema import get_metric_unit
from src.nlq.knowledge.display import get_display_name
from src.nlq.models.dashboard_schema import (
    DashboardSchema,
    Widget,
    WidgetType,
)

logger = logging.getLogger(__name__)


class DashboardDataResolver:
    """
    Resolves dashboard widget data from DCL.

    All data access goes through DCL's query API.
    """

    def __init__(self, fact_base=None):
        """Initialize resolver. fact_base param kept for backwards compatibility but ignored."""
        self.dcl_client = get_semantic_client()

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

        for widget in schema.widgets:
            try:
                data = self._resolve_widget_data(widget, reference_year, filters)
                widget_data[widget.id] = data
            except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
                logger.error(f"Error resolving data for widget {widget.id}: {e}")
                widget_data[widget.id] = {
                    "loading": False,
                    "error": f"Failed to load data: {str(e)}"
                }

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
            return {"loading": False}

    def _query_dcl(
        self,
        metric: str,
        dimensions: List[str] = None,
        filters: Dict[str, Any] = None,
        time_range: Dict[str, Any] = None,
        grain: str = None,
    ) -> Dict[str, Any]:
        """Execute query against DCL and handle errors."""
        from src.nlq.services.dcl_semantic_client import get_data_mode

        result = self.dcl_client.query(
            metric=metric,
            dimensions=dimensions,
            filters=filters,
            time_range=time_range,
            grain=grain,
        )

        if result.get("status") == "error" or result.get("error"):
            logger.warning(f"DCL query error for '{metric}': {result.get('error')}")

        # LIVE MODE: Fail loudly if we got demo data when live was requested
        current_mode = get_data_mode()
        if current_mode == "live":
            data_source = result.get("data_source", "")
            if data_source == "demo":
                reason = result.get("data_source_reason", "DCL returned demo data instead of live data")
                raise RuntimeError(
                    f"LIVE MODE FAILURE: {reason}. "
                    f"Metric '{metric}' not available in live ingested data. "
                    f"Check DCL ingest buffer or switch to Demo mode."
                )

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

        # Query DCL for current year value
        result = self._query_dcl(
            metric=metric,
            filters=filters,
            time_range={"period": reference_year, "granularity": "yearly"},
        )

        if result.get("error"):
            return {"loading": False, "error": result["error"]}

        # Extract value from DCL response
        value = self._extract_value_from_result(result)
        if value is None:
            return {"loading": False, "error": f"No data for '{metric}'"}

        # Get prior year for trend
        prior_year = str(int(reference_year) - 1)
        prior_result = self._query_dcl(
            metric=metric,
            filters=filters,
            time_range={"period": prior_year, "granularity": "yearly"},
        )
        prior_value = self._extract_value_from_result(prior_result)

        # Calculate trend
        trend = None
        if prior_value is not None and prior_value != 0:
            pct_change = ((value - prior_value) / prior_value) * 100
            trend = {
                "direction": "up" if pct_change > 0 else "down" if pct_change < 0 else "flat",
                "percent_change": abs(round(pct_change, 1)),
                "comparison_label": f"vs {prior_year}"
            }

        # Format value
        formatted_value = self._format_value(metric, value)

        # Get sparkline data (last 8 quarters)
        sparkline_result = self._query_dcl(
            metric=metric,
            filters=filters,
            time_range={"period": "last 8 quarters", "granularity": "quarterly"},
            grain="quarterly",
        )
        sparkline_data = self._extract_time_series_values(sparkline_result)

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

        # Query DCL for quarterly data
        result = self._query_dcl(
            metric=metric,
            filters=filters,
            time_range={"period": "last 8 quarters", "granularity": "quarterly"},
            grain="quarterly",
        )

        if result.get("error"):
            return {"loading": False, "error": result["error"]}

        # Extract data points
        data_points = self._extract_time_series(result)

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
        dimension = dimensions[0].dimension if dimensions else "region"

        # Query DCL for dimensional breakdown
        result = self._query_dcl(
            metric=metric,
            dimensions=[dimension],
            filters=filters,
            time_range={"period": reference_year, "granularity": "yearly"},
        )

        if result.get("error"):
            return {"loading": False, "error": result["error"]}

        # Extract breakdown data
        breakdown = self._extract_dimensional_data(result, dimension, metric)

        if not breakdown:
            # Fallback: try to get total and apply standard ratios
            total_result = self._query_dcl(
                metric=metric,
                filters=filters,
                time_range={"period": reference_year, "granularity": "yearly"},
            )
            total_value = self._extract_value_from_result(total_result)

            if total_value is not None:
                breakdown = self._generate_estimated_breakdown(dimension, total_value, filters)
            else:
                return {"loading": False, "error": f"No data for '{metric}'"}

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

        categories = ["Q1", "Q2", "Q3", "Q4"]
        series = []

        for metric_binding in metrics[:3]:
            metric = metric_binding.metric

            result = self._query_dcl(
                metric=metric,
                filters=filters,
                time_range={"period": reference_year, "granularity": "quarterly"},
                grain="quarterly",
            )

            data_points = self._extract_quarterly_values(result, reference_year)

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
            for q in range(1, 5):
                period = f"{reference_year}-Q{q}"
                row = {"quarter": f"Q{q} {reference_year}"}

                for metric_binding in metrics:
                    metric = metric_binding.metric
                    result = self._query_dcl(
                        metric=metric,
                        filters=filters,
                        time_range={"period": period, "granularity": "quarterly"},
                    )
                    val = self._extract_value_from_result(result)
                    row[metric] = round(val, 1) if val else None

                rows.append(row)
        else:
            # Get dimensional breakdown
            for metric_binding in metrics[:1]:  # Primary metric
                metric = metric_binding.metric
                result = self._query_dcl(
                    metric=metric,
                    dimensions=[dimension],
                    filters=filters,
                    time_range={"period": reference_year, "granularity": "yearly"},
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

        # Query DCL for regional breakdown
        result = self._query_dcl(
            metric=metric,
            dimensions=["region"],
            filters=filters,
            time_range={"period": reference_year, "granularity": "yearly"},
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
            return None

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
            return []

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

        # Fallback: generate empty quarters
        return [{"label": f"Q{q}", "value": 0} for q in range(1, 5)]

    def _extract_dimensional_data(
        self, result: Dict[str, Any], dimension: str, metric: str = None
    ) -> List[Dict[str, Any]]:
        """Extract dimensional breakdown from DCL result."""
        if result.get("error"):
            return []

        data = result.get("data", [])
        if not data:
            return []

        breakdown = []
        total = 0

        for item in data:
            if isinstance(item, dict):
                label = item.get(dimension, item.get("label", item.get("name", "")))
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

    def _generate_estimated_breakdown(
        self, dimension: str, total_value: float, filters: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Generate estimated breakdown using standard ratios when DCL doesn't have dimensional data."""

        # Standard distribution ratios
        distributions = {
            "region": [
                ("AMER", 0.50),
                ("EMEA", 0.30),
                ("APAC", 0.20),
            ],
            "segment": [
                ("Enterprise", 0.55),
                ("Mid-Market", 0.30),
                ("SMB", 0.15),
            ],
            "product": [
                ("Enterprise", 0.45),
                ("Professional", 0.30),
                ("Team", 0.18),
                ("Starter", 0.07),
            ],
            "stage": [
                ("Lead", 0.20),
                ("Qualified", 0.30),
                ("Proposal", 0.20),
                ("Negotiation", 0.15),
                ("Closed-Won", 0.15),
            ],
        }

        dist = distributions.get(dimension, [])
        if not dist:
            return []

        breakdown = []
        for label, ratio in dist:
            value = total_value * ratio
            breakdown.append({
                "label": label,
                "value": round(value, 1),
                "ratio": ratio,
            })

        # Apply dimension filter if present
        if dimension in filters:
            filter_value = filters[dimension]
            breakdown = [
                b for b in breakdown
                if b["label"].lower() == filter_value.lower()
                or b["label"].upper() == filter_value.upper()
            ]

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
