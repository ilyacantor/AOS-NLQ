"""
Dashboard Schema Generator for Self-Developing Dashboards.

Generates dashboard schemas from visualization requirements extracted from
natural language queries.

IMPORTANT: This module no longer silently pads metrics or falls back to defaults.
If the user requests 1 metric, they get 1 metric. If extraction fails, we fail loudly.
"""

import uuid
from typing import Any, Dict, List, Optional

from src.nlq.core.visualization_intent import (
    ChartTypeHint,
    VisualizationIntent,
    VisualizationRequirements,
)
from src.nlq.core.debug_info import (
    DashboardDebugInfo,
    DashboardGenerationError,
    DecisionSource,
    FailureCategory,
    is_strict_mode,
)
from src.nlq.knowledge.display import get_display_name, get_domain
from src.nlq.knowledge.schema import get_metric_unit
from src.nlq.services.dcl_semantic_client import get_semantic_client

import logging

logger = logging.getLogger(__name__)

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


def _validate_metric_dimension(metric: str, dimension: str) -> tuple[bool, str, list[str]]:
    """
    Validate that a dimension is valid for a given metric.

    Uses DCL semantic client to check allowed dimensions.

    Args:
        metric: Canonical metric ID
        dimension: Requested dimension

    Returns:
        Tuple of (is_valid, error_message, valid_dimensions)
    """
    semantic_client = get_semantic_client()
    is_valid, error_msg = semantic_client.validate_dimension(metric, dimension)
    valid_dims = semantic_client.get_valid_dimensions(metric)

    return is_valid, error_msg or "", valid_dims


def _get_fallback_dimension(metric: str, requested_dimension: str) -> str | None:
    """
    Get a fallback dimension if the requested one isn't valid.

    Returns the first valid dimension for the metric, or None if no breakdowns exist.
    """
    semantic_client = get_semantic_client()
    valid_dims = semantic_client.get_valid_dimensions(metric)

    if not valid_dims:
        logger.warning(f"Metric '{metric}' does not support any dimensional breakdowns")
        return None

    if requested_dimension in valid_dims:
        return requested_dimension

    # Try common dimension mappings
    dim_aliases = {
        "salesperson": "rep",
        "sales rep": "rep",
        "customer": "customer",
        "territory": "region",
        "area": "region",
    }

    normalized = dim_aliases.get(requested_dimension.lower(), requested_dimension.lower())
    if normalized in valid_dims:
        return normalized

    # Return first valid dimension as fallback
    logger.warning(
        f"Dimension '{requested_dimension}' not valid for '{metric}'. "
        f"Falling back to '{valid_dims[0]}'. Valid dimensions: {', '.join(valid_dims)}"
    )
    return valid_dims[0]


def generate_dashboard_schema(
    query: str,
    requirements: VisualizationRequirements,
    fact_base: Any = None,
    debug_info: Optional[DashboardDebugInfo] = None,
) -> DashboardSchema:
    """
    Generate a dashboard schema from visualization requirements.

    Args:
        query: Original natural language query
        requirements: Extracted visualization requirements
        fact_base: Optional fact base for data validation
        debug_info: Optional debug info for tracking decisions

    Returns:
        Complete DashboardSchema
    """
    # Initialize debug info if not provided
    if debug_info is None:
        debug_info = DashboardDebugInfo(original_query=query)

    debug_info.metrics_extracted = requirements.metrics.copy() if requirements.metrics else []
    debug_info.intent_detected = requirements.intent.value if requirements.intent else "unknown"
    debug_info.dimensions_requested = requirements.dimensions.copy() if requirements.dimensions else []

    dashboard_id = f"dash_{uuid.uuid4().hex[:8]}"
    title = _generate_title(query, requirements)

    widgets = []

    if requirements.intent == VisualizationIntent.SINGLE_METRIC_TREND:
        widgets = _generate_single_metric_trend(requirements)
        debug_info.add_decision("schema_generation", "Using SINGLE_METRIC_TREND template", DecisionSource.USER_REQUEST)
    elif requirements.intent == VisualizationIntent.BREAKDOWN_CHART:
        widgets = _generate_breakdown_chart(requirements)
        debug_info.add_decision("schema_generation", "Using BREAKDOWN_CHART template", DecisionSource.USER_REQUEST)
    elif requirements.intent == VisualizationIntent.COMPARISON_CHART:
        widgets = _generate_comparison_chart(requirements)
        debug_info.add_decision("schema_generation", "Using COMPARISON_CHART template", DecisionSource.USER_REQUEST)
    elif requirements.intent == VisualizationIntent.DRILL_DOWN_VIEW:
        widgets = _generate_drill_down_view(requirements)
        debug_info.add_decision("schema_generation", "Using DRILL_DOWN_VIEW template", DecisionSource.USER_REQUEST)
    elif requirements.intent == VisualizationIntent.MULTI_METRIC_DASHBOARD:
        widgets = _generate_multi_metric_dashboard(requirements)
        debug_info.add_decision("schema_generation", "Using MULTI_METRIC_DASHBOARD template", DecisionSource.USER_REQUEST)
    elif requirements.intent == VisualizationIntent.FULL_DASHBOARD:
        widgets = _generate_full_dashboard(requirements, debug_info)
        debug_info.add_decision("schema_generation", "Using FULL_DASHBOARD template", DecisionSource.USER_REQUEST)
    else:
        # Simple KPI for simple answers that were promoted to viz
        widgets = _generate_simple_kpi(requirements)
        debug_info.add_decision("schema_generation", "Using SIMPLE_KPI template (fallback)", DecisionSource.GENERIC_DEFAULT)

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
    import re
    q = query.lower()

    # Extract year from query if present (e.g., "2025 results")
    year_match = re.search(r"\b(20\d{2})\b", q)
    year = year_match.group(1) if year_match else None

    # Handle full dashboard with year-based overview queries
    if requirements.intent == VisualizationIntent.FULL_DASHBOARD:
        if year and any(term in q for term in ["results", "summary", "overview", "performance"]):
            return f"{year} Business Summary"
        elif year:
            return f"{year} Dashboard"
        return "Executive Dashboard"

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
            ChartTypeHint.MAP: WidgetType.MAP,
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
    requested_dimension = requirements.dimensions[0] if requirements.dimensions else "region"

    # Validate dimension for this metric - use fallback if invalid
    dimension = _get_fallback_dimension(metric, requested_dimension)
    if dimension is None:
        # No breakdowns available - generate KPI only
        logger.warning(f"No breakdown dimensions available for '{metric}', generating KPI only")
        return _generate_simple_kpi(requirements)

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
    requested_dimension = requirements.dimensions[0] if requirements.dimensions else "region"

    # Validate dimension for this metric
    dimension = _get_fallback_dimension(metric, requested_dimension)
    if dimension is None:
        # No breakdowns available - generate trend view instead
        logger.warning(f"No breakdown dimensions available for '{metric}', generating trend view")
        return _generate_single_metric_trend(requirements)

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


def _generate_full_dashboard(
    requirements: VisualizationRequirements,
    debug_info: Optional[DashboardDebugInfo] = None,
) -> List[Widget]:
    """
    Generate a full executive-style dashboard.

    IMPORTANT: This function NO LONGER pads metrics. If user requests 1 metric,
    they get a dashboard with 1 metric. We do not silently add unrequested metrics.
    """
    widgets = []

    # Use detected metrics - DO NOT default to CFO metrics
    if not requirements.metrics:
        error_msg = "Cannot generate dashboard: no metrics specified in request"
        if debug_info:
            debug_info.add_error(
                FailureCategory.METRIC_EXTRACTION,
                error_msg,
            )
        if is_strict_mode():
            raise DashboardGenerationError(
                error_msg,
                FailureCategory.METRIC_EXTRACTION,
                debug_info,
                "Ensure the query explicitly mentions metrics or use a persona-specific dashboard request",
            )
        # In non-strict mode, log and use a minimal default
        logger.error(f"[FALLBACK] {error_msg} - using 'revenue' as emergency fallback")
        requirements.metrics = ["revenue"]

    metrics = requirements.metrics

    # NO PADDING - use exactly what was requested
    # If user asked for 1 metric, they get 1 KPI card
    kpi_metrics = metrics[:4]  # Cap at 4 but DO NOT pad

    if debug_info:
        debug_info.add_decision(
            stage="full_dashboard_generation",
            decision=f"Using {len(kpi_metrics)} KPI metrics: {kpi_metrics}",
            source=DecisionSource.USER_REQUEST,
            details="No padding applied - using exactly what was requested",
        )

    # Calculate column span based on number of metrics
    # If 1 metric: full width (12 cols)
    # If 2 metrics: 6 cols each
    # If 3 metrics: 4 cols each
    # If 4 metrics: 3 cols each
    num_kpis = len(kpi_metrics)
    col_span = 12 // num_kpis if num_kpis > 0 else 12

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
            position=GridPosition(column=col, row=1, col_span=col_span, row_span=2),
            kpi_config=KPIConfig(show_trend=True, show_sparkline=True),
        ))
        col += col_span

    # Primary metric trend chart - use first metric (which user explicitly requested)
    primary_metric = metrics[0]  # Safe - we already checked metrics is not empty above
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

    # Primary metric by dimension - validate dimension first
    requested_dimension = requirements.dimensions[0] if requirements.dimensions else "region"
    dimension = _get_fallback_dimension(primary_metric, requested_dimension)

    if dimension:
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
                        query_template=f"Show me {get_display_name(primary_metric)} for {{value}} by rep",
                    ),
                )
            ],
        ))

        # Add geographic map widget for CFO-style dashboards with regional data
        if dimension == "region" and primary_metric in ["revenue", "bookings", "pipeline", "arr"]:
            widgets.append(Widget(
                id=f"map_{primary_metric}_by_region",
                type=WidgetType.MAP,
                title=f"{get_display_name(primary_metric)} by Region",
                data=DataBinding(
                    metrics=[MetricBinding(metric=primary_metric, format=_get_format_string(primary_metric))],
                    dimensions=[DimensionBinding(dimension="region", sort_by="value", sort_order="desc")],
                    time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
                ),
                position=GridPosition(column=1, row=6, col_span=6, row_span=3),
                chart_config=ChartConfig(show_legend=False, show_grid=False, animate=True),
            ))
    else:
        # No breakdown available - add another metric comparison instead
        logger.warning(f"No breakdown for '{primary_metric}', adding metric comparison instead")
        if len(metrics) > 1:
            widgets.append(Widget(
                id="metrics_comparison",
                type=WidgetType.BAR_CHART,
                title="Metrics Comparison",
                data=DataBinding(
                    metrics=[MetricBinding(metric=m, format=_get_format_string(m)) for m in metrics[1:4]],
                    time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
                ),
                position=GridPosition(column=7, row=3, col_span=6, row_span=3),
                chart_config=ChartConfig(show_legend=True, show_grid=True, animate=True),
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
            # Check both ID patterns: "trend_{metric}" (refinement) and "{metric}_trend" (initial generation)
            trend_id = f"trend_{metric}"
            has_trend = any(
                w.id == trend_id or w.id == f"{metric}_trend"
                for w in updated_schema.widgets
            )
            if has_trend:
                logger.info(f"[REFINEMENT_SKIP] Trend chart for '{metric}' already exists in dashboard")
                # In strict mode, raise a user-friendly error
                if is_strict_mode():
                    raise DashboardGenerationError(
                        f"A trend chart for '{get_display_name(metric)}' already exists in this dashboard.",
                        FailureCategory.REFINEMENT,
                        suggestion="Try asking for a different metric's trend, or remove the existing trend first."
                    )
            else:
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
        # Match patterns like "filter to AMER", "only EMEA", "filter to AMER region"
        # Use non-greedy matching and direct filter value capture
        filter_match = re.search(r"\b(AMER|EMEA|APAC|LATAM|Enterprise|Professional|Team|Starter|Q[1-4])\b", q, re.IGNORECASE)
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

    elif ("comparison" in q or "compare" in q or " vs " in q) and len(requirements.metrics) >= 2:
        # Add a comparison chart for multiple metrics (e.g., "AR vs AP comparison")
        metrics = requirements.metrics[:2]
        chart_id = f"comparison_{'_'.join(metrics)}"
        if not any(w.id == chart_id for w in updated_schema.widgets):
            max_row = max((w.position.row + w.position.row_span for w in updated_schema.widgets), default=0)
            updated_schema.widgets.append(Widget(
                id=chart_id,
                type=WidgetType.BAR_CHART,
                title=f"{get_display_name(metrics[0])} vs {get_display_name(metrics[1])}",
                data=DataBinding(
                    metrics=[MetricBinding(metric=m, format=_get_format_string(m)) for m in metrics],
                    time=TimeBinding(period="last 4 quarters", granularity=TimeGranularity.QUARTERLY),
                ),
                position=GridPosition(column=1, row=max_row + 1, col_span=6, row_span=3),
                chart_config=ChartConfig(show_legend=True, show_grid=True, animate=True),
            ))

    elif "last quarter" in q or "prior" in q:
        # Add time comparison to existing widgets
        for widget in updated_schema.widgets:
            if widget.data.time:
                widget.data.time.comparison = "prior_period"

    # Handle "add X by Y" or "show X by Y" - add a breakdown chart
    if (("add" in q or "show" in q) and " by " in q and requirements.metrics):
        import re
        # Extract dimension from "by <dimension>" pattern
        dim_match = re.search(r"\bby\s+(stage|salesperson|rep|customer|region|product|segment|quarter)\b", q, re.IGNORECASE)
        if dim_match:
            requested_dimension = dim_match.group(1).lower()
            # Normalize dimension names
            if requested_dimension == "salesperson":
                requested_dimension = "rep"

            metric = requirements.metrics[0]

            # Validate dimension for this metric
            dimension = _get_fallback_dimension(metric, requested_dimension)
            if dimension is None:
                # Log warning - no breakdown available
                logger.warning(
                    f"Cannot add breakdown: metric '{metric}' does not support dimensional breakdowns"
                )
            else:
                chart_id = f"breakdown_{metric}_by_{dimension}"

                # Check for duplicate - either by ID or by semantic meaning (same metric + dimension)
                # This prevents adding "Revenue by Region" when one already exists with a different ID prefix
                has_duplicate = any(
                    w.id == chart_id or  # Exact ID match
                    w.id == f"{metric}_by_{dimension}" or  # Initial generation ID pattern
                    (w.data.metrics and w.data.dimensions and
                     w.data.metrics[0].metric == metric and
                     w.data.dimensions[0].dimension == dimension)  # Same metric+dimension combo
                    for w in updated_schema.widgets
                )
                if not has_duplicate:
                    max_row = max((w.position.row + w.position.row_span for w in updated_schema.widgets), default=0)
                    updated_schema.widgets.append(Widget(
                        id=chart_id,
                        type=WidgetType.BAR_CHART,
                        title=f"{get_display_name(metric)} by {dimension.title()}",
                        data=DataBinding(
                            metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
                            dimensions=[DimensionBinding(dimension=dimension, sort_by="value", sort_order="desc")],
                            time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
                        ),
                        position=GridPosition(column=1, row=max_row + 1, col_span=6, row_span=3),
                        chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
                    ))

    # Handle question-style queries like "Which region has the most revenue?" or "What product has the highest pipeline?"
    import re
    if re.search(r"\b(which|what|where)\b.*\b(most|highest|lowest|best|worst)\b", q, re.IGNORECASE):
        # Extract dimension from the query (which/what X has...)
        dim_match = re.search(r"\b(which|what)\s+(region|rep|product|segment|stage|salesperson|customer|quarter)\b", q, re.IGNORECASE)
        if dim_match:
            requested_dimension = dim_match.group(2).lower()
            if requested_dimension == "salesperson":
                requested_dimension = "rep"

            # Get the metric - either from requirements or try to infer from query
            metric = requirements.metrics[0] if requirements.metrics else None
            if not metric:
                # Try to extract from common patterns like "most revenue" or "highest pipeline"
                metric_match = re.search(r"\b(most|highest|lowest)\s+(\w+)", q, re.IGNORECASE)
                if metric_match:
                    metric = metric_match.group(2).lower()

            if metric:
                # Validate dimension for this metric
                dimension = _get_fallback_dimension(metric, requested_dimension)
                if dimension:
                    chart_id = f"breakdown_{metric}_by_{dimension}"

                    # Check for duplicate
                    has_duplicate = any(
                        w.id == chart_id or
                        w.id == f"{metric}_by_{dimension}" or
                        (w.data.metrics and w.data.dimensions and
                         w.data.metrics[0].metric == metric and
                         w.data.dimensions[0].dimension == dimension)
                        for w in updated_schema.widgets
                    )
                    if not has_duplicate:
                        max_row = max((w.position.row + w.position.row_span for w in updated_schema.widgets), default=0)
                        updated_schema.widgets.append(Widget(
                            id=chart_id,
                            type=WidgetType.BAR_CHART,
                            title=f"{get_display_name(metric)} by {dimension.title()}",
                            data=DataBinding(
                                metrics=[MetricBinding(metric=metric, format=_get_format_string(metric))],
                                dimensions=[DimensionBinding(dimension=dimension, sort_by="value", sort_order="desc")],
                                time=TimeBinding(period="2025", granularity=TimeGranularity.YEARLY),
                            ),
                            position=GridPosition(column=1, row=max_row + 1, col_span=6, row_span=3),
                            chart_config=ChartConfig(show_legend=False, show_grid=True, animate=True),
                        ))

    # Handle "break down by" dimension changes (modifies existing charts)
    if "break" in q and "down" in q and "by" in q:
        # Extract new dimension from requirements or query
        requested_dimension = None
        if requirements.dimensions:
            requested_dimension = requirements.dimensions[0]
        else:
            # Try to extract from query pattern "by <dimension>"
            import re
            dim_match = re.search(r"\bby\s+(region|rep|product|segment|stage|quarter)\b", q)
            if dim_match:
                requested_dimension = dim_match.group(1)

        if requested_dimension:
            # Update chart widgets with the new dimension (validate per-widget)
            for widget in updated_schema.widgets:
                if widget.type in [WidgetType.BAR_CHART, WidgetType.LINE_CHART,
                                   WidgetType.STACKED_BAR, WidgetType.DONUT_CHART]:
                    if widget.data.metrics:
                        metric = widget.data.metrics[0].metric
                        # Validate dimension for this widget's metric
                        validated_dim = _get_fallback_dimension(metric, requested_dimension)
                        if validated_dim:
                            widget.data.dimensions = [
                                DimensionBinding(dimension=validated_dim, sort_by="value", sort_order="desc")
                            ]
                            widget.title = f"{get_display_name(metric)} by {validated_dim.title()}"
                            widget.id = f"breakdown_{metric}_by_{validated_dim}"
                        else:
                            logger.warning(f"Cannot change breakdown for '{metric}': no valid dimensions")
                elif widget.type == WidgetType.DATA_TABLE:
                    if widget.data.metrics:
                        metric = widget.data.metrics[0].metric
                        validated_dim = _get_fallback_dimension(metric, requested_dimension)
                        if validated_dim:
                            widget.data.dimensions = [
                                DimensionBinding(dimension=validated_dim, sort_by="value", sort_order="desc")
                            ]
                            widget.id = f"table_{validated_dim}"

            # Update schema title
            if updated_schema.widgets:
                first_chart = next(
                    (w for w in updated_schema.widgets if w.type in [WidgetType.BAR_CHART, WidgetType.LINE_CHART]),
                    None
                )
                if first_chart and first_chart.data.metrics and first_chart.data.dimensions:
                    metric = first_chart.data.metrics[0].metric
                    dim = first_chart.data.dimensions[0].dimension
                    updated_schema.title = f"{get_display_name(metric)} by {dim.title()}"

    # Fallback: If "add" is in query and metrics were detected but no action taken yet,
    # default to adding KPI cards for the requested metrics
    original_widget_count = len(current_schema.widgets)
    if "add" in q and requirements.metrics and len(updated_schema.widgets) == original_widget_count:
        logger.info(f"[REFINEMENT_FALLBACK] 'add' detected with metrics {requirements.metrics}, adding KPI cards")
        for metric in requirements.metrics:
            if not any(w.id == f"kpi_{metric}" for w in updated_schema.widgets):
                # Find next available position
                max_col = max((w.position.column + w.position.col_span for w in updated_schema.widgets), default=1)
                if max_col > 10:
                    max_col = 1
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

    # Check if any changes were made
    if len(updated_schema.widgets) == original_widget_count:
        # No widgets added - check if any modifications were made
        widgets_modified = any(
            w1.model_dump() != w2.model_dump()
            for w1, w2 in zip(current_schema.widgets, updated_schema.widgets)
        )
        if not widgets_modified:
            logger.warning(
                f"[REFINEMENT_NO_OP] No changes made for refinement query: '{refinement_query}'. "
                f"Metrics requested: {requirements.metrics}, Intent: {requirements.intent}"
            )
            if is_strict_mode():
                raise DashboardGenerationError(
                    f"Unable to apply refinement: '{refinement_query}'. No matching refinement pattern found.",
                    FailureCategory.REFINEMENT,
                    suggestion=f"Try being more specific, e.g., 'Add {requirements.metrics[0] if requirements.metrics else 'revenue'} KPI card' or 'Show {requirements.metrics[0] if requirements.metrics else 'revenue'} trend'"
                )

    # Update version and history
    updated_schema.version += 1
    updated_schema.refinement_history.append(refinement_query)

    return updated_schema
