"""
Dashboard API routes for Self-Developing Dashboards.

Endpoints:
- POST /v1/query/dashboard: Generate dashboard schema from NL query
- POST /v1/dashboard/refine: Refine existing dashboard with NL
- GET /v1/dashboard/{id}: Get dashboard by ID (from cache)
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.nlq.core.dashboard_generator import (
    generate_dashboard_schema,
    refine_dashboard_schema,
)
from src.nlq.core.visualization_intent import (
    VisualizationIntent,
    detect_visualization_intent,
    should_generate_visualization,
)
from src.nlq.models.dashboard_schema import (
    DashboardGenerationResponse,
    DashboardRefinementRequest,
    DashboardRefinementResponse,
    DashboardSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory cache for generated dashboards (in production, use Redis or DB)
_dashboard_cache: Dict[str, DashboardSchema] = {}


class DashboardQueryRequest(BaseModel):
    """Request model for dashboard generation."""
    question: str = Field(..., description="Natural language query for dashboard")
    reference_date: Optional[str] = Field(default=None, description="Reference date for time calculations")
    conversation_id: Optional[str] = Field(default=None, description="Conversation ID for context")


@router.post("/query/dashboard", response_model=DashboardGenerationResponse)
async def generate_dashboard(request: DashboardQueryRequest) -> DashboardGenerationResponse:
    """
    Generate a dashboard schema from a natural language query.

    This endpoint:
    1. Detects visualization intent from the query
    2. Extracts metrics, dimensions, and chart preferences
    3. Generates a complete dashboard schema
    4. Returns the schema for frontend rendering

    Example queries:
    - "Show me revenue by region over time"
    - "Create a dashboard with revenue, margin, and pipeline KPIs"
    - "Visualize sales trends with ability to drill into reps"
    """
    try:
        logger.info(f"Dashboard generation request: {request.question}")

        # Detect visualization intent
        should_viz, requirements = should_generate_visualization(request.question)

        if not should_viz:
            # User doesn't want a visualization, suggest using /query endpoint
            return DashboardGenerationResponse(
                success=False,
                dashboard=None,
                error="This query appears to be asking for a simple answer. Use /v1/query instead.",
                query=request.question,
                intent_detected=requirements.intent.value,
                confidence=requirements.confidence,
                suggestions=[
                    "Try adding 'show me' or 'visualize' to create a dashboard",
                    "Ask for a 'trend' or 'breakdown' to get a chart",
                    f"Example: 'Show me {requirements.metrics[0] if requirements.metrics else 'revenue'} by region over time'",
                ],
            )

        # Generate dashboard schema
        dashboard = generate_dashboard_schema(
            query=request.question,
            requirements=requirements,
        )

        # Cache the dashboard for potential refinement
        _dashboard_cache[dashboard.id] = dashboard

        # Generate suggestions for refinement
        suggestions = _generate_refinement_suggestions(dashboard, requirements)

        logger.info(f"Generated dashboard {dashboard.id} with {len(dashboard.widgets)} widgets")

        return DashboardGenerationResponse(
            success=True,
            dashboard=dashboard,
            error=None,
            query=request.question,
            intent_detected=requirements.intent.value,
            confidence=requirements.confidence,
            suggestions=suggestions,
        )

    except Exception as e:
        logger.error(f"Dashboard generation failed: {e}", exc_info=True)
        return DashboardGenerationResponse(
            success=False,
            dashboard=None,
            error=str(e),
            query=request.question,
            intent_detected="unknown",
            confidence=0.0,
            suggestions=["Try simplifying your query", "Check that the metrics you're asking about exist"],
        )


@router.post("/dashboard/refine", response_model=DashboardRefinementResponse)
async def refine_dashboard(request: DashboardRefinementRequest) -> DashboardRefinementResponse:
    """
    Refine an existing dashboard with a natural language request.

    Example refinements:
    - "Add a pipeline KPI card"
    - "Make that a bar chart"
    - "Filter to EMEA only"
    - "Add comparison to last quarter"
    - "Remove the trend chart"
    """
    try:
        logger.info(f"Dashboard refinement request: {request.refinement_query} for {request.dashboard_id}")

        # Get current dashboard from cache
        current_dashboard = _dashboard_cache.get(request.dashboard_id)
        if not current_dashboard:
            return DashboardRefinementResponse(
                success=False,
                dashboard=None,
                error=f"Dashboard {request.dashboard_id} not found",
                changes_made=[],
                confidence=0.0,
            )

        # Detect intent from refinement query
        _, requirements = should_generate_visualization(request.refinement_query)

        # Apply refinement
        updated_dashboard = refine_dashboard_schema(
            current_schema=current_dashboard,
            refinement_query=request.refinement_query,
            requirements=requirements,
        )

        # Update cache
        _dashboard_cache[updated_dashboard.id] = updated_dashboard

        # Determine what changed
        changes_made = _detect_changes(current_dashboard, updated_dashboard, request.refinement_query)

        logger.info(f"Refined dashboard {updated_dashboard.id}, changes: {changes_made}")

        return DashboardRefinementResponse(
            success=True,
            dashboard=updated_dashboard,
            error=None,
            changes_made=changes_made,
            confidence=requirements.confidence,
        )

    except Exception as e:
        logger.error(f"Dashboard refinement failed: {e}", exc_info=True)
        return DashboardRefinementResponse(
            success=False,
            dashboard=None,
            error=str(e),
            changes_made=[],
            confidence=0.0,
        )


@router.get("/dashboard/{dashboard_id}")
async def get_dashboard(dashboard_id: str) -> DashboardSchema:
    """
    Get a cached dashboard by ID.
    """
    dashboard = _dashboard_cache.get(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {dashboard_id} not found")
    return dashboard


@router.get("/dashboard/intent/check")
async def check_intent(question: str) -> dict:
    """
    Check if a query would generate a visualization (for UI hints).

    Returns the detected intent without generating a full dashboard.
    """
    should_viz, requirements = should_generate_visualization(question)

    return {
        "query": question,
        "should_visualize": should_viz,
        "intent": requirements.intent.value,
        "chart_hint": requirements.chart_hint.value,
        "metrics": requirements.metrics,
        "dimensions": requirements.dimensions,
        "time_dimension": requirements.time_dimension,
        "drill_down_requested": requirements.drill_down_requested,
        "confidence": requirements.confidence,
    }


def _generate_refinement_suggestions(
    dashboard: DashboardSchema,
    requirements,
) -> list:
    """Generate suggestions for how to refine the dashboard."""
    suggestions = []

    # Suggest adding missing common metrics
    existing_metrics = set()
    for widget in dashboard.widgets:
        for metric in widget.data.metrics:
            existing_metrics.add(metric.metric)

    common_metrics = ["revenue", "gross_margin_pct", "net_income", "pipeline", "churn"]
    missing = [m for m in common_metrics if m not in existing_metrics]
    if missing:
        suggestions.append(f"Add {missing[0]} KPI: 'Add a {missing[0]} card'")

    # Suggest chart type changes
    has_line = any(w.type.value == "line_chart" for w in dashboard.widgets)
    has_bar = any(w.type.value == "bar_chart" for w in dashboard.widgets)

    if has_line and not has_bar:
        suggestions.append("Try a bar chart: 'Make that a bar chart'")
    elif has_bar and not has_line:
        suggestions.append("Try a line chart: 'Make that a line chart'")

    # Suggest drill-down
    if not requirements.drill_down_requested:
        suggestions.append("Add drill-down: 'Let me drill into reps'")

    # Suggest comparison
    suggestions.append("Add comparison: 'Compare to last quarter'")

    # Suggest filter
    if requirements.dimensions:
        dim = requirements.dimensions[0]
        suggestions.append(f"Filter data: 'Filter to EMEA only'")

    return suggestions[:4]  # Limit to 4 suggestions


def _detect_changes(
    old: DashboardSchema,
    new: DashboardSchema,
    query: str,
) -> list:
    """Detect what changes were made between dashboard versions."""
    changes = []

    old_widget_ids = {w.id for w in old.widgets}
    new_widget_ids = {w.id for w in new.widgets}

    # Added widgets
    added = new_widget_ids - old_widget_ids
    for widget_id in added:
        widget = next(w for w in new.widgets if w.id == widget_id)
        changes.append(f"Added {widget.type.value}: {widget.title}")

    # Removed widgets
    removed = old_widget_ids - new_widget_ids
    for widget_id in removed:
        widget = next(w for w in old.widgets if w.id == widget_id)
        changes.append(f"Removed {widget.type.value}: {widget.title}")

    # Changed widget types
    for new_widget in new.widgets:
        old_widget = next((w for w in old.widgets if w.id == new_widget.id), None)
        if old_widget and old_widget.type != new_widget.type:
            changes.append(f"Changed {old_widget.title} from {old_widget.type.value} to {new_widget.type.value}")

    if not changes:
        changes.append(f"Applied refinement: {query}")

    return changes
