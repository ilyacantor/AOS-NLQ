"""
Dashboard Schema Generator for Self-Developing Dashboards.

Generates dashboard schemas from visualization requirements extracted from
natural language queries.
"""

import uuid
from typing import Any, Dict, List, Optional

from src.nlq.core.visualization_intent import (
    ChartTypeHint,
    VisualizationIntent,
    VisualizationRequirements,
)
from src.nlq.knowledge.display import get_display_name, get_domain
from src.nlq.knowledge.schema import get_metric_unit
from src.nlq.models.dashboard_schema import (
    AggregationType,
    ChartConfig,
    DashboardSchema,
    DataBinding,
    DimensionBinding,
    DrillDownConfig,
    GridPosition,
    InteractionConfig,
    InteractionType,
    KPIConfig,
    LayoutConfig,
    MetricBinding,
    TableConfig,
    TimeBinding,
    TimeGranularity,
    Widget,
    WidgetType,
)


def generate_dashboard_schema(
    query: str,
    requirements: VisualizationRequirements,
    fact_base: Any = None,
) -> DashboardSchema:
    """
    Generate a dashboard schema from visualization requirements.

    Args:
        query: Original natural language query
        requirements: Extracted visualization requirements
        fact_base: Optional fact base for data validation

    Returns:
        Complete DashboardSchema
    """
    dashboard_id = f"dash_{uuid.uuid4().hex[:8]}"
    title = _generate_title(query, requirements)

    widgets = []

    if requirements.intent == VisualizationIntent.SINGLE_METRIC_TREND:
        widgets = _generate_single_metric_trend(requirements)
    elif requirements.intent == VisualizationIntent.BREAKDOWN_CHART:
        widgets = _generate_breakdown_chart(requirements)
    elif requirements.intent == VisualizationIntent.COMPARISON_CHART:
        widgets = _generate_comparison_chart(requirements)
    elif requirements.intent == VisualizationIntent.DRILL_DOWN_VIEW:
        widgets = _generate_drill_down_view(requirements)
    elif requirements.intent == VisualizationIntent.MULTI_METRIC_DASHBOARD:
        widgets = _generate_multi_metric_dashboard(requirements)
    elif requirements.intent == VisualizationIntent.FULL_DASHBOARD:
        widgets = _generate_full_dashboard(requirements)
    else:
        # Simple KPI for simple answers that were promoted to viz
        widgets = _generate_simple_kpi(requirements)

    # Determine default time binding
    time_binding = TimeBinding(
        period="2025",
        granularity=TimeGranularity(requirements.time_granularity or "quarterly"),
    )

    return DashboardSchema(
        id=dashboard_id,
        title=title,
        description=f"Generated from: {query}",
        source_query=query,
        layout=LayoutConfig(columns=12, row_height=80, gap=16, padding=24),
        widgets=widgets,
        time_range=time_binding,
        confidence=requirements.confidence,
        version=1,
        refinement_history=[],
    )


def _generate_title(query: str, requirements: VisualizationRequirements) -> str:
    """Generate a dashboard title from the query."""
    if requirements.metrics:
        metric_names = [get_display_name(m) for m in requirements.metrics[:2]]
        if requirements.dimensions:
            dim_name = requirements.dimensions[0].title()
            return f"{' & '.join(metric_names)} by {dim_name}"
        elif requirements.time_dimension:
            return f"{' & '.join(metric_names)} Over Time"
        else:
            return f"{' & '.join(metric_names)} Dashboard"
    return "Custom Dashboard"


def _get_format_string(metric: str) -> str:
    """Get format string for a metric."""
    unit = get_metric_unit(metric)
    if unit == "%":
        return "0.0%"
    elif unit == "USD millions":
        return "$0.0M"
    elif unit == "USD":
        return "$0.00"
    elif unit == "months":
        return "0.0 mo"
    elif unit == "x":
        return "0.0x"
    elif unit in ["people", "customers", "count"]:
        return "0,0"
    return "0.0"


def _infer_chart_type(
    requirements: VisualizationRequirements,
    has_time: bool = False,
    has_dimension: bool = False,
) -> WidgetType:
    """Infer the best chart type from requirements."""
    if requirements.chart_hint != ChartTypeHint.AUTO:
        hint_map = {
            ChartTypeHint.LINE: WidgetType.LINE_CHART,
            ChartTypeHint.BAR: WidgetType.BAR_CHART,
            ChartTypeHint.PIE: WidgetType.DONUT_CHART,
            ChartTypeHint.DONUT: WidgetType.DONUT_CHART,
            ChartTypeHint.TABLE: WidgetType.DATA_TABLE,
            ChartTypeHint.KPI: WidgetType.KPI_CARD,
            ChartTypeHint.AREA: WidgetType.AREA_CHART,
            ChartTypeHint.STACKED: WidgetType.STACKED_BAR,
        }
        return hint_map.get(requirements.chart_hint, WidgetType.BAR_CHART)

    # Auto-infer
    if has_time and not has_dimension:
        return WidgetType.LINE_CHART
    elif has_dimension and not has_time:
        return WidgetType.BAR_CHART
    elif has_time and has_dimension:
        return WidgetType.LINE_CHART  # Multiple series
    else:
        return WidgetType.KPI_CARD


def _generate_simple_kpi(requirements: VisualizationRequirements) -> List[Widget]:
    """Generate a simple KPI card."""
    widgets = []
    col = 1

    for metric in requirements.metrics[:4]:
        widgets.append(Widget(
            id=f"kpi_{metric}",
            type=WidgetType.KPI_CARD,
            title=get_display_name(metric),
            data=DataBinding(
                metrics=[MetricBinding(
                    metric=metric,
                    format=_get_format_string(metric),
                )],
                time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
            ),
            position=GridPosition(column=col, row=1, col_span=3, row_span=2),
            kpi_config=KPIConfig(show_trend=True, show_sparkline=True),
        ))
        col += 3

    return widgets


def _generate_single_metric_trend(requirements: VisualizationRequirements) -> List[Widget]:
    """Generate a trend chart for a single metric."""
    widgets = []
    metric = requirements.metrics[0] if requirements.metrics else "revenue"
    granularity = TimeGranularity(requirements.time_granularity or "quarterly")

    # KPI summary at top
    widgets.append(Widget(
        id=f"kpi_{metric}",
        type=WidgetType.KPI_CARD,
        title=f"Current {get_display_name(metric)}",
        data=DataBinding(
            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
            time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
        ),
        position=GridPosition(column=1, row=1, col_span=3, row_span=2),
        kpi_config=KPIConfig(show_trend=True, show_sparkline=False),
    ))

    # Trend chart
    widgets.append(Widget(
        id=f"trend_{metric}",
        type=WidgetType.LINE_CHART,
        title=f"{get_display_name(metric)} Over Time",
        data=DataBinding(
            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
            time=TimeBinding(period="last 8 quarters", granularity=granularity),
        ),
        position=GridPosition(column=4, row=1, col_span=9, row_span=3),
        chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
    ))

    return widgets


def _generate_breakdown_chart(requirements: VisualizationRequirements) -> List[Widget]:
    """Generate a breakdown chart by dimension."""
    widgets = []
    metric = requirements.metrics[0] if requirements.metrics else "revenue"
    dimension = requirements.dimensions[0] if requirements.dimensions else "region"

    # KPI summary
    widgets.append(Widget(
        id=f"kpi_{metric}",
        type=WidgetType.KPI_CARD,
        title=f"Total {get_display_name(metric)}",
        data=DataBinding(
            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
            time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
        ),
        position=GridPosition(column=1, row=1, col_span=3, row_span=2),
        kpi_config=KPIConfig(show_trend=True, show_sparkline=True),
    ))

    # Breakdown chart
    chart_type = WidgetType.BAR_CHART
    if len(requirements.dimensions) > 1:
        chart_type = WidgetType.STACKED_BAR

    interactions = []
    if requirements.drill_down_requested:
        interactions.append(InteractionConfig(
            type=InteractionType.DRILL_DOWN,
            enabled=True,
            drill_down=DrillDownConfig(
                target_dimension="rep",
                query_template=f"Show me {get_display_name(metric)} for {{value}} by rep",
            ),
        ))

    widgets.append(Widget(
        id=f"breakdown_{metric}_by_{dimension}",
        type=chart_type,
        title=f"{get_display_name(metric)} by {dimension.title()}",
        data=DataBinding(
            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
            dimensions=[DimensionBinding(dimension=dimension, sort_by="value", sort_order="desc")],
            time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
        ),
        position=GridPosition(column=4, row=1, col_span=9, row_span=3),
        chart_config=ChartConfig(show_legend=True, show_grid=True, animate=True),
        interactions=interactions,
    ))

    # Data table for details
    widgets.append(Widget(
        id=f"table_{metric}_by_{dimension}",
        type=WidgetType.DATA_TABLE,
        title="Details",
        data=DataBinding(
            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
            dimensions=[DimensionBinding(dimension=dimension, sort_by="value", sort_order="desc")],
            time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
        ),
        position=GridPosition(column=1, row=3, col_span=3, row_span=3),
        table_config=TableConfig(sortable=True, show_totals=True),
    ))

    return widgets


def _generate_comparison_chart(requirements: VisualizationRequirements) -> List[Widget]:
    """Generate a comparison chart."""
    widgets = []
    metrics = requirements.metrics[:2] if len(requirements.metrics) >= 2 else requirements.metrics + ["gross_margin_pct"]

    # KPIs for each metric
    col = 1
    for metric in metrics[:2]:
        widgets.append(Widget(
            id=f"kpi_{metric}",
            type=WidgetType.KPI_CARD,
            title=get_display_name(metric),
            data=DataBinding(
                metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
                time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
            ),
            position=GridPosition(column=col, row=1, col_span=3, row_span=2),
            kpi_config=KPIConfig(show_trend=True, show_sparkline=True),
        ))
        col += 3

    # Comparison chart
    widgets.append(Widget(
        id="comparison_chart",
        type=WidgetType.LINE_CHART,
        title="Comparison Over Time",
        data=DataBinding(
            metrics=[MetricBinding(metric=m, format=_get_format_string(m)) for m in metrics[:2]],
            time=TimeBinding(period="last 8 quarters", granularity=TimeGranularity.QUARTERLY),
        ),
        position=GridPosition(column=1, row=3, col_span=12, row_span=3),
        chart_config=ChartConfig(show_legend=True, show_grid=True, animate=True),
    ))

    return widgets


def _generate_drill_down_view(requirements: VisualizationRequirements) -> List[Widget]:
    """Generate a view with drill-down capability."""
    widgets = []
    metric = requirements.metrics[0] if requirements.metrics else "revenue"
    dimension = requirements.dimensions[0] if requirements.dimensions else "region"

    # Summary KPI
    widgets.append(Widget(
        id=f"kpi_{metric}",
        type=WidgetType.KPI_CARD,
        title=f"Total {get_display_name(metric)}",
        data=DataBinding(
            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
            time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
        ),
        position=GridPosition(column=1, row=1, col_span=4, row_span=2),
        kpi_config=KPIConfig(show_trend=True, show_sparkline=True),
    ))

    # Main chart with drill-down
    widgets.append(Widget(
        id=f"main_{metric}_by_{dimension}",
        type=WidgetType.BAR_CHART,
        title=f"{get_display_name(metric)} by {dimension.title()} (click to drill down)",
        data=DataBinding(
            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
            dimensions=[DimensionBinding(dimension=dimension, sort_by="value", sort_order="desc")],
            time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
        ),
        position=GridPosition(column=5, row=1, col_span=8, row_span=3),
        chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
        interactions=[
            InteractionConfig(
                type=InteractionType.DRILL_DOWN,
                enabled=True,
                drill_down=DrillDownConfig(
                    target_dimension="rep" if dimension != "rep" else "customer",
                    query_template=f"Show me {get_display_name(metric)} for {{value}} by {'rep' if dimension != 'rep' else 'customer'}",
                ),
            )
        ],
    ))

    # Trend chart
    widgets.append(Widget(
        id=f"trend_{metric}",
        type=WidgetType.LINE_CHART,
        title=f"{get_display_name(metric)} Trend",
        data=DataBinding(
            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
            time=TimeBinding(period="last 8 quarters", granularity=TimeGranularity.QUARTERLY),
        ),
        position=GridPosition(column=1, row=3, col_span=4, row_span=3),
        chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
    ))

    return widgets


def _generate_multi_metric_dashboard(requirements: VisualizationRequirements) -> List[Widget]:
    """Generate a dashboard with multiple KPIs."""
    widgets = []
    metrics = requirements.metrics[:6] if requirements.metrics else ["revenue", "gross_margin_pct", "net_income"]

    # KPI row
    col = 1
    for i, metric in enumerate(metrics[:4]):
        widgets.append(Widget(
            id=f"kpi_{metric}",
            type=WidgetType.KPI_CARD,
            title=get_display_name(metric),
            data=DataBinding(
                metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
                time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
            ),
            position=GridPosition(column=col, row=1, col_span=3, row_span=2),
            kpi_config=KPIConfig(show_trend=True, show_sparkline=True),
        ))
        col += 3

    # Primary metric trend
    primary_metric = metrics[0]
    widgets.append(Widget(
        id=f"trend_{primary_metric}",
        type=WidgetType.LINE_CHART,
        title=f"{get_display_name(primary_metric)} Trend",
        data=DataBinding(
            metrics=[MetricBinding(metric=primary_metric, format=_get_format_string(primary_metric))],
            time=TimeBinding(period="last 8 quarters", granularity=TimeGranularity.QUARTERLY),
        ),
        position=GridPosition(column=1, row=3, col_span=6, row_span=3),
        chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
    ))

    # Secondary metrics comparison
    if len(metrics) > 1:
        widgets.append(Widget(
            id="metrics_comparison",
            type=WidgetType.BAR_CHART,
            title="Metrics Overview",
            data=DataBinding(
                metrics=[MetricBinding(metric=m, format=_get_format_string(m)) for m in metrics[1:4]],
                time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
            ),
            position=GridPosition(column=7, row=3, col_span=6, row_span=3),
            chart_config=ChartConfig(show_legend=True, show_grid=True, animate=True),
        ))

    return widgets


def _generate_full_dashboard(requirements: VisualizationRequirements) -> List[Widget]:
    """Generate a full executive-style dashboard."""
    widgets = []

    # Use detected metrics or default to CFO metrics
    metrics = requirements.metrics if requirements.metrics else ["revenue", "gross_margin_pct", "net_income", "pipeline"]

    # Top KPI row - use the detected metrics, pad with defaults if needed
    kpi_metrics = metrics[:4]  # Take first 4 metrics
    if len(kpi_metrics) < 4:
        # Pad with relevant metrics based on context
        defaults = ["revenue", "gross_margin_pct", "net_income", "pipeline"]
        for m in defaults:
            if m not in kpi_metrics and len(kpi_metrics) < 4:
                kpi_metrics.append(m)

    col = 1
    for metric in kpi_metrics:
        widgets.append(Widget(
            id=f"kpi_{metric}",
            type=WidgetType.KPI_CARD,
            title=get_display_name(metric),
            data=DataBinding(
                metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
                time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
            ),
            position=GridPosition(column=col, row=1, col_span=3, row_span=2),
            kpi_config=KPIConfig(show_trend=True, show_sparkline=True),
        ))
        col += 3

    # Primary metric trend chart
    primary_metric = metrics[0] if metrics else "revenue"
    widgets.append(Widget(
        id=f"{primary_metric}_trend",
        type=WidgetType.LINE_CHART,
        title=f"{get_display_name(primary_metric)} Trend",
        data=DataBinding(
            metrics=[MetricBinding(metric=primary_metric, format=_get_format_string(primary_metric))],
            time=TimeBinding(period="last 8 quarters", granularity=TimeGranularity.QUARTERLY),
        ),
        position=GridPosition(column=1, row=3, col_span=6, row_span=3),
        chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
    ))

    # Primary metric by dimension
    dimension = requirements.dimensions[0] if requirements.dimensions else "region"
    widgets.append(Widget(
        id=f"{primary_metric}_by_{dimension}",
        type=WidgetType.BAR_CHART,
        title=f"{get_display_name(primary_metric)} by {dimension.title()}",
        data=DataBinding(
            metrics=[MetricBinding(metric=primary_metric, format=_get_format_string(primary_metric))],
            dimensions=[DimensionBinding(dimension=dimension, sort_by="value", sort_order="desc")],
            time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
        ),
        position=GridPosition(column=7, row=3, col_span=6, row_span=3),
        chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
        interactions=[
            InteractionConfig(
                type=InteractionType.DRILL_DOWN,
                enabled=True,
                drill_down=DrillDownConfig(
                    target_dimension="rep",
                    query_template="Show me revenue for {value} by rep",
                ),
            )
        ],
    ))

    return widgets


def refine_dashboard_schema(
    current_schema: DashboardSchema,
    refinement_query: str,
    requirements: VisualizationRequirements,
) -> DashboardSchema:
    """
    Refine an existing dashboard schema based on a natural language refinement request.

    Args:
        current_schema: The current dashboard schema
        refinement_query: Natural language refinement request
        requirements: Extracted requirements from refinement query

    Returns:
        Updated DashboardSchema
    """
    q = refinement_query.lower()

    # Make a copy of the schema
    updated_schema = current_schema.model_copy(deep=True)

    # Check for trend chart request (e.g., "Add a quarterly trend chart for Revenue" or "Show burn rate trend")
    if ("trend" in q or "over time" in q) and any(w in q for w in ["add", "show", "display"]):
        # Add a trend chart for the requested metric
        metrics_to_chart = requirements.metrics if requirements.metrics else []

        # Also try to extract metric from common patterns like "trend chart for revenue"
        if not metrics_to_chart:
            import re
            metric_match = re.search(r"(?:trend|chart|over time)\s+(?:for|of)\s+(\w+)", q)
            if metric_match:
                metrics_to_chart = [metric_match.group(1).lower()]

        for metric in metrics_to_chart:
            # Check if we already have a trend chart for this metric
            trend_id = f"trend_{metric}"
            if not any(w.id == trend_id for w in updated_schema.widgets):
                # Find next available position
                max_row = max((w.position.row + w.position.row_span for w in updated_schema.widgets), default=0)

                granularity_str = "quarterly"
                if "monthly" in q:
                    granularity_str = "monthly"
                elif "yearly" in q or "annual" in q:
                    granularity_str = "yearly"

                updated_schema.widgets.append(Widget(
                    id=trend_id,
                    type=WidgetType.LINE_CHART,
                    title=f"{get_display_name(metric)} Over Time",
                    data=DataBinding(
                        metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
                        time=TimeBinding(period="last 8 quarters", granularity=TimeGranularity(granularity_str)),
                    ),
                    position=GridPosition(column=1, row=max_row + 1, col_span=6, row_span=3),
                    chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
                ))

    # Common refinements - Add KPI card
    elif "add" in q and any(m in q for m in ["kpi", "card", "metric"]):
        # Add a new KPI card
        for metric in requirements.metrics:
            if not any(w.id == f"kpi_{metric}" for w in updated_schema.widgets):
                # Find next available column
                max_col = max((w.position.column + w.position.col_span for w in updated_schema.widgets), default=1)
                if max_col > 10:
                    max_col = 1  # Wrap to new row
                    max_row = max((w.position.row + w.position.row_span for w in updated_schema.widgets), default=1)
                else:
                    max_row = 1

                updated_schema.widgets.append(Widget(
                    id=f"kpi_{metric}",
                    type=WidgetType.KPI_CARD,
                    title=get_display_name(metric),
                    data=DataBinding(
                        metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
                        time=updated_schema.time_range,
                    ),
                    position=GridPosition(column=max_col, row=max_row, col_span=3, row_span=2),
                    kpi_config=KPIConfig(show_trend=True, show_sparkline=True),
                ))

    elif "bar chart" in q or "make that a bar" in q:
        # Convert chart type to bar
        for widget in updated_schema.widgets:
            if widget.type in [WidgetType.LINE_CHART, WidgetType.DONUT_CHART]:
                widget.type = WidgetType.BAR_CHART

    elif "line chart" in q or "make that a line" in q:
        # Convert chart type to line
        for widget in updated_schema.widgets:
            if widget.type in [WidgetType.BAR_CHART, WidgetType.DONUT_CHART]:
                widget.type = WidgetType.LINE_CHART

    elif "filter" in q or "only" in q:
        # Add filter to data bindings - extract filter value from query
        import re
        # Match patterns like "filter to AMER", "only EMEA", "filter by region APAC"
        filter_match = re.search(r"(?:filter\s+(?:to|by)?|only)\s*(?:\w+\s+)?(\b(?:AMER|EMEA|APAC|LATAM|Enterprise|Professional|Team|Starter|Q[1-4])\b)", q, re.IGNORECASE)
        if filter_match:
            filter_value = filter_match.group(1).upper()
            # Determine dimension based on filter value
            filter_dim = "region"
            if filter_value in ["ENTERPRISE", "PROFESSIONAL", "TEAM", "STARTER"]:
                filter_dim = "product"
                filter_value = filter_value.title()
            elif filter_value.startswith("Q"):
                filter_dim = "quarter"

            # Add filter to all widgets
            for widget in updated_schema.widgets:
                widget.data.filters[filter_dim] = filter_value
            updated_schema.title = f"{updated_schema.title} - {filter_value}"

    elif "remove" in q or "delete" in q:
        # Remove widgets matching criteria
        widgets_to_keep = []
        for widget in updated_schema.widgets:
            should_remove = False
            for metric in requirements.metrics:
                if metric in widget.id:
                    should_remove = True
                    break
            if not should_remove:
                widgets_to_keep.append(widget)
        updated_schema.widgets = widgets_to_keep

    elif "comparison" in q or "compare" in q or "last quarter" in q or "prior" in q:
        # Add comparison to widgets
        for widget in updated_schema.widgets:
            if widget.data.time:
                widget.data.time.comparison = "prior_period"

    # Handle "break down by" dimension changes
    if "break" in q and "down" in q and "by" in q:
        # Extract new dimension from requirements or query
        new_dimension = None
        if requirements.dimensions:
            new_dimension = requirements.dimensions[0]
        else:
            # Try to extract from query pattern "by <dimension>"
            import re
            dim_match = re.search(r"\bby\s+(region|rep|product|segment|stage|quarter)\b", q)
            if dim_match:
                new_dimension = dim_match.group(1)

        if new_dimension:
            # Update chart widgets with the new dimension
            for widget in updated_schema.widgets:
                if widget.type in [WidgetType.BAR_CHART, WidgetType.LINE_CHART,
                                   WidgetType.STACKED_BAR, WidgetType.DONUT_CHART]:
                    # Replace existing dimensions with new one
                    widget.data.dimensions = [
                        DimensionBinding(dimension=new_dimension, sort_by="value", sort_order="desc")
                    ]
                    # Update widget title
                    if widget.data.metrics:
                        metric = widget.data.metrics[0].metric
                        widget.title = f"{get_display_name(metric)} by {new_dimension.title()}"
                        widget.id = f"breakdown_{metric}_by_{new_dimension}"
                elif widget.type == WidgetType.DATA_TABLE:
                    widget.data.dimensions = [
                        DimensionBinding(dimension=new_dimension, sort_by="value", sort_order="desc")
                    ]
                    widget.id = f"table_{new_dimension}"

            # Update schema title
            if updated_schema.widgets:
                first_chart = next(
                    (w for w in updated_schema.widgets if w.type in [WidgetType.BAR_CHART, WidgetType.LINE_CHART]),
                    None
                )
                if first_chart and first_chart.data.metrics:
                    metric = first_chart.data.metrics[0].metric
                    updated_schema.title = f"{get_display_name(metric)} by {new_dimension.title()}"

    # Update version and history
    updated_schema.version += 1
    updated_schema.refinement_history.append(refinement_query)

    return updated_schema
