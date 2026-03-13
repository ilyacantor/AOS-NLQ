"""
Dashboard API routes — surviving endpoints after query consolidation.

All query-generating endpoints (generate_dashboard, refine_dashboard) were removed.
All queries now go through /api/v1/query (routes.py).

Surviving endpoints:
- GET  /v1/dashboard/{id}: Get dashboard by ID (from cache)
- POST /v1/dashboard/filter: Apply cross-widget filters
- GET  /v1/dashboard/intent/check: Check if a query would generate a visualization
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.nlq.core.dates import current_year
from src.nlq.core.visualization_intent import (
    should_generate_visualization,
)
from src.nlq.models.dashboard_schema import (
    DashboardSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory cache for generated dashboards (in production, use Redis or DB)
_dashboard_cache: Dict[str, DashboardSchema] = {}


# _resolve_widget_data removed — only used by deleted generate_dashboard/refine_dashboard


# ─── DELETED: DashboardQueryRequest, generate_dashboard(), refine_dashboard() ───
# All queries now go through /api/v1/query (routes.py query() handler).
# Dashboard generation/refinement logic lives in the main waterfall.
# ─────────────────────────────────────────────────────────────────────


@router.get("/dashboard/{dashboard_id}")
async def get_dashboard(dashboard_id: str) -> DashboardSchema:
    """
    Get a cached dashboard by ID.
    """
    dashboard = _dashboard_cache.get(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {dashboard_id} not found")
    return dashboard


class DashboardFilterRequest(BaseModel):
    """Request model for cross-widget filtering."""
    dashboard_id: str = Field(..., description="Dashboard ID to filter")
    filters: dict = Field(..., description="Filters to apply (dimension -> value)")
    session_id: str = Field(default="default", description="Session ID for state tracking")


class DashboardFilterResponse(BaseModel):
    """Response model for filtered dashboard data."""
    success: bool = Field(..., description="Whether filtering was successful")
    widget_data: dict = Field(..., description="Updated widget data with filters applied")
    active_filters: dict = Field(..., description="Currently active filters")
    error: Optional[str] = Field(default=None, description="Error message if any")


@router.post("/dashboard/filter", response_model=DashboardFilterResponse)
async def filter_dashboard(request: DashboardFilterRequest) -> DashboardFilterResponse:
    """
    Apply cross-widget filters to a dashboard.

    When a user clicks on a chart element (e.g., a region bar), this endpoint
    recomputes all widget data with the filter applied.

    Example:
    - Click "AMER" bar -> All widgets filter to AMER region
    - Click again to clear filter
    """
    try:
        from src.nlq.core.dashboard_data_resolver import DashboardDataResolver

        logger.info(f"Filter request for {request.dashboard_id}: {request.filters}")

        # Get dashboard from cache
        dashboard = _dashboard_cache.get(request.dashboard_id)
        if not dashboard:
            return DashboardFilterResponse(
                success=False,
                widget_data={},
                active_filters={},
                error=f"Dashboard {request.dashboard_id} not found",
            )

        # Resolve data with filters via DCL
        resolver = DashboardDataResolver()
        widget_data = resolver.resolve_dashboard_data(
            dashboard,
            reference_year=current_year(),
            active_filters=request.filters,
        )

        logger.info(f"Applied filters: {request.filters}, resolved {len(widget_data)} widgets")

        return DashboardFilterResponse(
            success=True,
            widget_data=widget_data,
            active_filters=request.filters,
            error=None,
        )

    except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
        logger.error(f"Filter failed: {e}", exc_info=True)
        return DashboardFilterResponse(
            success=False,
            widget_data={},
            active_filters={},
            error=str(e),
        )
    except Exception as e:
        logger.exception(f"Unhandled error in filter: {type(e).__name__}: {e}")
        return DashboardFilterResponse(
            success=False,
            widget_data={},
            active_filters={},
            error=f"{type(e).__name__}: {e}",
        )


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


# _generate_refinement_suggestions and _detect_changes removed — only used by deleted handlers
