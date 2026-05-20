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

# In-memory cache for dashboards.
#   - Dynamic dashboards generated from NL queries land here keyed by
#     `dash_<8hex>` IDs (legacy code path).
#   - Persona dashboards (WS-5 B1) land here keyed by stable IDs like
#     `persona_finops` via load_persona_dashboards() at startup.
# Both shapes coexist; the existing GET /api/v1/dashboard/{id} endpoint
# serves either kind transparently.
_dashboard_cache: Dict[str, DashboardSchema] = {}


def populate_persona_cache(dashboards: Dict[str, DashboardSchema]) -> None:
    """WS-5 B1: invoked from main.py startup_event with the result of
    load_persona_dashboards(). Idempotent — re-invoking replaces the
    persona entries but does not touch dynamic `dash_<8hex>` entries."""
    for dashboard_id, dashboard in dashboards.items():
        _dashboard_cache[dashboard_id] = dashboard
    logger.info(
        "dashboard_routes: persona cache populated with %d dashboards: %s",
        len(dashboards), sorted(dashboards.keys()),
    )


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


@router.get("/dashboard/{dashboard_id}/resolved")
async def get_dashboard_resolved(dashboard_id: str) -> Dict[str, Any]:
    """WS-5 B3: returns the dashboard schema plus resolved widget data.

    For persona dashboards (id prefix `persona_`), tile data resolves
    through the AAM cross-source-query endpoint — every widget data
    point carries per-row provenance from the AOS-MCP envelope.

    Dynamic dashboards (`dash_<8hex>` IDs) are not supported by this
    endpoint today; use /api/v1/query for those.
    """
    dashboard = _dashboard_cache.get(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail=f"Dashboard {dashboard_id} not found")
    if not dashboard_id.startswith("persona_"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"/dashboard/{{id}}/resolved is for persona dashboards only "
                f"(id prefix 'persona_'). Got: {dashboard_id!r}. Use /api/v1/query "
                f"for dynamic dashboards."
            ),
        )
    from src.nlq.config import get_tenant_id
    from src.nlq.services.dcl_semantic_client import set_entity_id
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver

    # I2: tenant_id is resolved at the route boundary — missing → 422 before
    # any AAM fan-out, so identity never degrades downstream.
    try:
        tenant_id = get_tenant_id()
    except RuntimeError as tid_err:
        raise HTTPException(
            status_code=422,
            detail={"error": "missing_tenant_id", "message": str(tid_err)},
        )

    try:
        resolver = PersonaDashboardResolver(tenant_id=tenant_id)
        widget_data = resolver.resolve(dashboard)
        entity_id = resolver.resolved_entity_id
        # I6: keep the persona route's entity ContextVar handling identical
        # to the main /query path so any downstream read resolves correctly.
        set_entity_id(entity_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        set_entity_id(None)
    return {
        "schema": dashboard.model_dump(),
        "widget_data": widget_data,
        "tenant_id": tenant_id,
        "entity_id": entity_id,
    }


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

    except (RuntimeError, KeyError, TypeError, ValueError, OSError, ConnectionError) as e:
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
    try:
        should_viz, requirements = should_generate_visualization(question)
    except (RuntimeError, ConnectionError) as e:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot check visualization intent — DCL unavailable: {e}",
        )

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
