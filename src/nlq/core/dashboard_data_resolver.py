"""
Dashboard Data Resolver - Populates dashboard widgets with data from DCL.

Uses a single batch browse call to DCL (via get_all_metrics_by_period),
replacing 60+ concurrent requests that previously exhausted DCL's connection pool.

Dimensional queries (bar charts by dimension, donut, map) still use individual
DCL calls since they require server-side grouping.
"""

import logging
from typing import Any, Dict, List, Optional

from src.nlq.core.dates import current_year, current_quarter

from src.nlq.services.dcl_client_router import get_routed_client as get_semantic_client
from src.nlq.services.dcl_semantic_client import get_entity_id
from src.nlq.knowledge.schema import get_metric_unit
from src.nlq.knowledge.display import get_display_name
from src.nlq.knowledge.synonyms import normalize_metric
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


def _lookup(prefetched: Dict[str, Optional[float]], metric: str, period: str) -> Optional[float]:
    """Look up a pre-fetched metric value by canonical name and period."""
    canonical = normalize_metric(metric)
    return prefetched.get(f"{canonical}|{period}")


class DashboardDataResolver:
    """
    Resolves dashboard widget data from DCL.

    All data access goes through DCL's query API.  Batch-eligible widgets
    (KPI, time series, stacked bar, quarter tables) are resolved from a
    single browse-batch call.  Dimensional widgets use individual queries.
    """

    def __init__(self):
        """Initialize resolver. All data access goes through DCL."""
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
        Resolve data for all widgets via batch prefetch + sequential dimensional queries.

        Args:
            schema: The dashboard schema with widget definitions
            reference_year: The year to query for annual data
            active_filters: Optional dict of dimension -> value filters to apply

        Returns:
            Dict mapping widget_id to widget data
        """
        reference_year = reference_year or current_year()
        entity_id = get_entity_id()
        cq = current_quarter()
        quarters_8 = _quarter_range(8)
        quarters_4 = _quarter_range(4)
        prior_q = quarters_8[-2] if len(quarters_8) >= 2 else None
        filters = active_filters or {}

        # Phase 1: Collect all metric names from all widgets
        all_metrics: set = set()
        for w in schema.widgets:
            if not w.data or not w.data.metrics:
                continue
            for mb in w.data.metrics:
                canonical = normalize_metric(mb.metric)
                if canonical:
                    all_metrics.add(canonical)

        # Phase 2: Single batch fetch — 1 HTTP call replaces 60+
        prefetched: Dict[str, Optional[float]] = {}
        if all_metrics:
            try:
                batch_result, _ = self.dcl_client.v2.get_all_metrics_by_period(
                    list(all_metrics), entity_id=entity_id,
                )
                prefetched = batch_result
            except (RuntimeError, OSError, ConnectionError) as e:
                logger.error(f"Batch prefetch failed: {e}")
                # Widget resolvers will surface "No data" errors for each widget

        # Phase 3 & 4: Resolve each widget sequentially
        widget_data: Dict[str, Dict[str, Any]] = {}
        for widget in schema.widgets:
            try:
                data = self._resolve_widget_data(
                    widget, reference_year, filters, prefetched,
                    cq, prior_q, quarters_8, quarters_4,
                )
                if isinstance(data, dict) and data.get("error"):
                    logger.error(
                        f"Widget {widget.id} data resolution failed: {data['error']}"
                    )
                    widget_data[widget.id] = {
                        "error": data["error"],
                        "widget_id": widget.id,
                        "status": "dcl_error",
                    }
                else:
                    widget_data[widget.id] = data
            except (RuntimeError, KeyError, TypeError, ValueError, OSError, ConnectionError) as e:
                logger.error(f"Error resolving data for widget {widget.id}: {e}")
                widget_data[widget.id] = {
                    "error": str(e),
                    "widget_id": widget.id,
                    "status": "resolution_error",
                }

        return widget_data

    def _resolve_widget_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Dict[str, str],
        prefetched: Dict[str, Optional[float]],
        cq: str,
        prior_q: Optional[str],
        quarters_8: List[str],
        quarters_4: List[str],
    ) -> Dict[str, Any]:
        """Resolve data for a single widget based on its type."""
        widget_type = widget.type
        if isinstance(widget_type, str):
            wt = widget_type
        else:
            wt = widget_type.value

        if wt == "kpi_card":
            return self._resolve_kpi_data(widget, prefetched, cq, prior_q, quarters_8)
        elif wt in ("line_chart", "area_chart"):
            return self._resolve_time_series_data(widget, prefetched, quarters_8)
        elif wt in ("bar_chart", "horizontal_bar"):
            return self._resolve_category_data(widget, reference_year, filters, prefetched, cq)
        elif wt == "stacked_bar":
            return self._resolve_stacked_data(widget, prefetched, quarters_4)
        elif wt == "donut_chart":
            return self._resolve_category_data(widget, reference_year, filters, prefetched, cq)
        elif wt == "data_table":
            return self._resolve_table_data(widget, reference_year, filters, prefetched, quarters_4)
        elif wt == "map":
            return self._resolve_map_data(widget, reference_year, filters)
        elif wt == "sales_funnel":
            return self._resolve_sales_funnel_data(widget, cq)
        else:
            return {"loading": False, "error": f"Unsupported widget type: {wt}"}

    def _resolve_sales_funnel_data(self, widget: Widget, cq: str) -> Dict[str, Any]:
        """Resolve sales funnel stages via DCLSemanticClientV2.get_pipeline_stages."""
        from src.nlq.services.dcl_semantic_client_v2 import DCLSemanticClientV2
        v2 = DCLSemanticClientV2()
        stages = v2.get_pipeline_stages(entity_id=get_entity_id(), period=cq)
        if not stages:
            return {"loading": False, "error": f"No pipeline stages found for {cq}"}
        return {
            "loading": False,
            "title": widget.title,
            "subtitle": cq,
            "stages": stages,
            "data_source": "dcl_v2",
            "period": cq,
        }

    # ------------------------------------------------------------------
    # Batch-resolved widget types (use prefetched data, no DCL calls)
    # ------------------------------------------------------------------

    def _resolve_kpi_data(
        self,
        widget: Widget,
        prefetched: Dict[str, Optional[float]],
        cq: str,
        prior_q: Optional[str],
        quarters_8: List[str],
    ) -> Dict[str, Any]:
        """Resolve KPI card data from prefetched batch."""
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metric specified"}

        metric = metrics[0].metric

        # Current value: try current quarter, then sum the year
        value = _lookup(prefetched, metric, cq)
        if value is None:
            # Try annual: sum 4 most recent quarters
            recent_4 = quarters_8[-4:]
            qvals = [_lookup(prefetched, metric, q) for q in recent_4]
            non_none = [v for v in qvals if v is not None]
            if non_none:
                value = sum(non_none)

        if value is None:
            return {"loading": False, "error": f"No data for '{metric}'"}

        # Prior quarter value for trend
        prior_value = _lookup(prefetched, metric, prior_q) if prior_q else None

        # Sparkline: values for each of 8 quarters
        sparkline_data = None
        spark_values = []
        spark_present: List[bool] = []
        for q in quarters_8:
            v = _lookup(prefetched, metric, q)
            spark_present.append(v is not None)
            spark_values.append(round(v, 1) if v is not None else 0)
        if any(spark_present):
            sparkline_data = spark_values

        # Compute trend
        trend = None
        if prior_value is not None and prior_value != 0:
            pct_change = ((value - prior_value) / prior_value) * 100
            trend = {
                "direction": "up" if pct_change > 0 else "down" if pct_change < 0 else "flat",
                "percent_change": abs(round(pct_change, 1)),
                "comparison_label": f"vs {prior_q}"
            }

        formatted_value = self._format_value(metric, value)

        return {
            "loading": False,
            "value": value,
            "formatted_value": formatted_value,
            "trend": trend,
            "sparkline_data": sparkline_data,
        }

    def _resolve_time_series_data(
        self,
        widget: Widget,
        prefetched: Dict[str, Optional[float]],
        quarters_8: List[str],
    ) -> Dict[str, Any]:
        """Resolve time series data for line/area charts from prefetched batch."""
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metric specified"}

        metric = metrics[0].metric

        data_points = []
        for q in quarters_8:
            val = _lookup(prefetched, metric, q)
            if val is not None:
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

    def _resolve_stacked_data(
        self,
        widget: Widget,
        prefetched: Dict[str, Optional[float]],
        quarters_4: List[str],
    ) -> Dict[str, Any]:
        """Resolve stacked bar chart data from prefetched batch."""
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metrics specified"}

        categories = [q.split("-")[1] for q in quarters_4]
        active_metrics = metrics[:3]

        series = []
        for mb in active_metrics:
            metric = mb.metric
            data_points = []
            for q in quarters_4:
                val = _lookup(prefetched, metric, q)
                label = q.split("-")[1]
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

    def _resolve_table_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Dict[str, str],
        prefetched: Dict[str, Optional[float]],
        quarters_4: List[str],
    ) -> Dict[str, Any]:
        """Resolve data table content — batch path for quarter dimension, DCL for others."""
        metrics = widget.data.metrics
        dimensions = widget.data.dimensions
        dimension = dimensions[0].dimension if dimensions else "quarter"

        rows = []

        if dimension == "quarter":
            # Batch-eligible: look up from prefetched data
            for q in quarters_4:
                row = {"quarter": q.replace("-", " ")}
                for mb in metrics:
                    val = _lookup(prefetched, mb.metric, q)
                    row[mb.metric] = round(val, 1) if val is not None else None
                rows.append(row)
        else:
            # Dimensional: use individual DCL calls (1-2 per metric)
            cq = current_quarter()
            for metric_binding in metrics[:1]:
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

    # ------------------------------------------------------------------
    # Dimensional widget types (still need individual DCL calls)
    # ------------------------------------------------------------------

    def _resolve_category_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Dict[str, str],
        prefetched: Dict[str, Optional[float]],
        cq: str,
    ) -> Dict[str, Any]:
        """Resolve categorical data for bar/donut charts."""
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metric specified"}

        metric = metrics[0].metric
        dimensions = widget.data.dimensions
        dimension = dimensions[0].dimension if dimensions else None
        if dimension is None:
            # Multi-metric comparison — batch-eligible
            if len(metrics) > 1:
                return self._resolve_multi_metric_comparison(metrics, prefetched, cq)
            return {"loading": False, "error": f"No dimension specified for '{metric}' breakdown"}

        # Pre-computed triple breakdown (e.g., revenue.by_customer triples in PG).
        # These exist as concept="{metric}.by_{dimension}" with property=dimension_value,
        # not as a queryable DCL dimension. Must be fetched via browse-batch directly.
        triple_breakdown = self._resolve_triple_breakdown(metric, dimension)
        if triple_breakdown is not None:
            return triple_breakdown

        # Dimensional breakdown — requires individual DCL calls
        breakdown = self._try_dimensional_query(metric, dimension, filters, reference_year)

        if not breakdown:
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

    def _resolve_multi_metric_comparison(
        self,
        metrics: List[MetricBinding],
        prefetched: Dict[str, Optional[float]],
        cq: str,
    ) -> Dict[str, Any]:
        """Resolve multi-metric comparison bar chart from prefetched batch."""
        data_points = []
        for metric_binding in metrics:
            metric = metric_binding.metric
            value = _lookup(prefetched, metric, cq)
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

    def _resolve_triple_breakdown(
        self,
        metric: str,
        dimension: str,
    ) -> Optional[Dict[str, Any]]:
        """Resolve breakdown data stored as pre-computed triples.

        Some breakdowns (e.g., revenue by customer) are stored as triples with
        concept="{metric}.by_{dimension}" and property=dimension_value, rather
        than as a queryable DCL dimension. This method fetches them via
        browse-batch and returns category chart format, or None if no triples
        match.
        """
        concept = f"{metric}.by_{dimension}"
        domain = metric.split(".")[0]
        entity_id = get_entity_id()

        v2 = self.dcl_client.v2
        resp = None
        try:
            resp = v2._http.post(
                "/api/dcl/triples/browse-batch",
                json={"domains": [domain], "entity_ids": [entity_id]},
            )
        except Exception as exc:
            logger.warning("Triple breakdown browse-batch error: %s", exc)

        if resp is None or resp.status_code >= 400:
            if resp is not None:
                logger.warning(
                    "Triple breakdown browse-batch failed: %s %s",
                    resp.status_code, resp.text[:300],
                )
            return None

        triples = resp.json().get("triples_by_domain", {}).get(domain, [])

        # Aggregate across all periods: dimension_value → total
        totals: Dict[str, float] = {}
        for t in triples:
            if t.get("concept") != concept:
                continue
            label = t.get("property")
            raw = t.get("value")
            if label and raw is not None:
                totals[label] = totals.get(label, 0.0) + float(raw)

        if not totals:
            return None

        breakdown = sorted(
            [{"label": k, "value": round(v, 2)} for k, v in totals.items()],
            key=lambda p: p["value"],
            reverse=True,
        )

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

    def _resolve_map_data(
        self,
        widget: Widget,
        reference_year: str,
        filters: Dict[str, str],
    ) -> Dict[str, Any]:
        """Resolve geographic map data showing revenue by region.

        Region triples use concept="{metric}.by_region.{region}" with
        property="amount", so we fetch via browse-batch and extract the
        region suffix from each concept name.
        """
        metrics = widget.data.metrics
        if not metrics:
            return {"loading": False, "error": "No metric specified"}

        metric = metrics[0].metric
        domain = metric.split(".")[0]
        entity_id = get_entity_id()
        prefix = f"{metric}.by_region."

        v2 = self.dcl_client.v2
        try:
            resp = v2._http.post(
                "/api/dcl/triples/browse-batch",
                json={"domains": [domain], "entity_ids": [entity_id]},
            )
        except Exception as exc:
            logger.warning("Map browse-batch error: %s", exc)
            return {"loading": False, "error": f"Cannot fetch regional data: {exc}"}

        if resp.status_code >= 400:
            return {"loading": False, "error": f"DCL returned {resp.status_code}"}

        triples = resp.json().get("triples_by_domain", {}).get(domain, [])

        # Aggregate: region → total value across all periods
        totals: Dict[str, float] = {}
        for t in triples:
            concept = t.get("concept", "")
            if not concept.startswith(prefix):
                continue
            region = concept[len(prefix):]
            raw = t.get("value")
            if region and raw is not None:
                totals[region] = totals.get(region, 0.0) + float(raw)

        if not totals:
            return {"loading": False, "error": f"No regional data for '{metric}'"}

        grand_total = sum(totals.values())
        regions = []

        for region_name, value in totals.items():
            percentage = (value / grand_total * 100) if grand_total > 0 else 0
            regions.append({
                "region": region_name.upper(),
                "value": round(value, 2),
                "percentage": round(percentage, 1),
            })

        regions.sort(key=lambda r: r["value"], reverse=True)

        return {
            "loading": False,
            "map_data": {
                "total": round(grand_total, 2),
                "metric": metric,
                "regions": regions,
            },
            "series": [{
                "name": get_display_name(metric),
                "data": [{"label": r["region"], "value": r["value"]} for r in regions],
            }],
            "categories": [r["region"] for r in regions],
        }

    # ------------------------------------------------------------------
    # DCL query helper (used only by dimensional widget types)
    # ------------------------------------------------------------------

    def _query_dcl(
        self,
        metric: str,
        dimensions: List[str] = None,
        filters: Dict[str, Any] = None,
        time_range: Dict[str, Any] = None,
        grain: str = None,
    ) -> Dict[str, Any]:
        """Execute query against DCL and handle errors."""
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
            self._provenance = result["run_provenance"]

        return result

    # =========================================================================
    # HELPER METHODS FOR EXTRACTING DATA FROM DCL RESPONSES
    # =========================================================================

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
                dims_dict = item.get("dimensions", {})
                label = (
                    (dims_dict.get(dimension) if isinstance(dims_dict, dict) else None)
                    or item.get(dimension)
                    or item.get("label", item.get("name", ""))
                )
                value = item.get("value", item.get("val", 0))

                if isinstance(value, dict):
                    if metric in value:
                        value = value[metric]
                    else:
                        for v in value.values():
                            if isinstance(v, (int, float)):
                                value = v
                                break
                        else:
                            value = 0

                if label and value is not None:
                    point = {"label": str(label), "value": round(value, 2)}
                    # WS-5 B2: per-data-point provenance threading. When
                    # the DCL response carries per-triple provenance, keep
                    # it on the data point so the drill-through can show
                    # which source / pipe / fabric produced the number.
                    # Aggregated `self._provenance` (the badge data) is
                    # separate and unaffected.
                    prov = _extract_per_item_provenance(item)
                    if prov:
                        point["provenance"] = prov
                    breakdown.append(point)
                    total += value

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


# =============================================================================
# WS-5 B2 — per-triple provenance helpers
# =============================================================================

_PROVENANCE_FIELDS = (
    "source_system", "source_field", "pipe_id",
    "fabric_plane", "confidence_score",
)


def _extract_per_item_provenance(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull the 5-field provenance dict off one DCL response item.

    Returns None when the item has no provenance at all (legacy DCL
    response shape or aggregated row). Returns a dict with whichever
    of the 5 fields the item carried — partial provenance is honest
    surfacing (A1: don't fabricate missing fields).
    """
    prov = {f: item.get(f) for f in _PROVENANCE_FIELDS if item.get(f) is not None}
    return prov or None


def resolve_dashboard_with_data(
    schema: DashboardSchema,
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
