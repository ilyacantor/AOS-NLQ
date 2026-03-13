"""
Health, schema, and pipeline status endpoints.

Extracted from routes.py (C1) — these are read-only operational endpoints
with no dependency on the query pipeline.
"""

import logging
import os
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.nlq.api.session import get_session_stats

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# MODELS
# =============================================================================


class HealthResponse(BaseModel):
    status: str
    version: str
    fact_base_loaded: bool
    claude_available: bool
    session_count: int = 0
    max_sessions: int = 100
    live_data_available: bool = False


class PipelineStatusResponse(BaseModel):
    """Pipeline status for the permanent UI status light."""
    dcl_connected: bool
    dcl_mode: Optional[str] = None  # "Ingest", "Demo", "Live", "Farm", or None
    metric_count: int = 0
    catalog_source: Optional[str] = None  # "dcl", "local", "local_fallback", or None
    last_run_id: Optional[str] = None
    last_run_timestamp: Optional[str] = None
    last_source_systems: Optional[List[str]] = None
    freshness: Optional[str] = None


class SchemaResponse(BaseModel):
    metrics: List[str]
    periods: List[str]
    metric_details: Dict = {}


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    Health check endpoint.

    Returns service status and component availability.
    Checks DCL connectivity for data access.
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    dcl_available = False
    claude_available = False

    try:
        # Check DCL connectivity by getting the catalog
        dcl_client = get_semantic_client()
        from src.nlq.services.dcl_semantic_client import diag
        diag(f"[NLQ-DIAG] /health: dcl_url={dcl_client.dcl_url}, catalog_source={dcl_client.catalog_source}")
        catalog = dcl_client.get_catalog()
        dcl_available = len(catalog.metrics) > 0
        diag(f"[NLQ-DIAG] /health: dcl_available={dcl_available}, metrics={len(catalog.metrics)}, source={dcl_client.catalog_source}")
    except (RuntimeError, KeyError, TypeError, AttributeError, OSError) as e:
        print(f"[NLQ-DIAG] /health: DCL check FAILED: {e}")
        logger.warning(f"DCL health check failed: {e}")

    try:
        # Don't actually call Claude for health check to avoid costs
        claude_available = os.environ.get("ANTHROPIC_API_KEY") is not None
    except (KeyError, TypeError) as e:
        logger.warning(f"Claude API key check failed: {e}")

    # live_data_available: true when we have a working data source (DCL ingest
    # or local fact base).  The banner should only warn when queries would
    # actually return zeros — not when DCL's ingest store happens to be empty
    # while the local fact base is perfectly fine.
    live_data_available = dcl_available  # catalog has metrics → data is available
    if not live_data_available:
        try:
            live_data_available = dcl_client.has_live_ingest_data()
        except (RuntimeError, AttributeError) as e:
            logger.warning("Live ingest data check failed: %s", e)

    session_stats = get_session_stats()
    return HealthResponse(
        status="healthy" if dcl_available else "degraded",
        version="0.1.0",
        fact_base_loaded=dcl_available,  # Field name kept for backwards compatibility
        claude_available=claude_available,
        session_count=session_stats["total_sessions"],
        max_sessions=session_stats["max_sessions"],
        live_data_available=live_data_available,
    )


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
async def pipeline_status(data_mode: Optional[str] = None) -> PipelineStatusResponse:
    """
    Return data pipeline connection status for the UI status light.

    Polls the DCL semantic client to determine:
    - Whether DCL is connected (live API vs local fallback)
    - What mode it's running in (Ingest/Demo/Live/Farm)
    - Last run provenance if available

    The frontend polls this every 30s to keep the header status light current.
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    if data_mode == "demo":
        dcl_client = get_semantic_client()
        try:
            local_catalog = dcl_client._build_local_catalog()
            metric_count = len(local_catalog.metrics)
        except (FileNotFoundError, IOError, KeyError, ValueError):
            metric_count = 0
        return PipelineStatusResponse(
            dcl_connected=False,
            dcl_mode=None,
            metric_count=metric_count,
            catalog_source="local",
        )

    # Live/ingest mode: check DCL connectivity via health endpoint
    dcl_client = get_semantic_client()
    health = dcl_client.check_dcl_health()
    dcl_connected = health.get("connected", False)
    raw_mode = health.get("data_mode")  # Real-time from DCL, not cached

    # Get metric count and source from catalog (may be cached up to 5 min)
    metric_count = 0
    catalog_source = dcl_client.catalog_source  # may be "none" before first load
    try:
        catalog = dcl_client.get_catalog()
        metric_count = len(catalog.metrics)
        catalog_source = dcl_client.catalog_source  # re-read after load
    except (RuntimeError, KeyError, TypeError, AttributeError, OSError) as e:
        logger.warning("DCL catalog check failed in pipeline_status: %s", e)

    # Provenance: from health response (real-time) + catalog ingest summary
    last_run_id = health.get("last_run_id")
    last_run_timestamp = health.get("last_updated")
    last_source_systems = None
    freshness_display = None

    if dcl_connected:
        summary = dcl_client.get_ingest_summary()
        if summary and summary.available:
            last_source_systems = summary.source_systems or None

    return PipelineStatusResponse(
        dcl_connected=dcl_connected,
        dcl_mode=raw_mode,
        metric_count=metric_count,
        catalog_source=catalog_source if catalog_source != "none" else None,
        last_run_id=last_run_id,
        last_run_timestamp=last_run_timestamp,
        last_source_systems=last_source_systems,
        freshness=freshness_display,
    )


@router.get("/schema", response_model=SchemaResponse)
async def schema() -> SchemaResponse:
    """
    Return available metrics and periods.

    Useful for building UIs and understanding what queries are supported.
    Fetches metric information from DCL semantic catalog.
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    dcl_client = get_semantic_client()
    catalog = dcl_client.get_catalog()

    # Get metric details from DCL catalog
    metric_details = {}
    for metric_id, metric in catalog.metrics.items():
        metric_details[metric_id] = {
            "display_name": metric.display_name,
            "type": "metric",  # All DCL metrics are metrics
            "unit": metric.unit,
            "domain": metric.domain,
            "allowed_dimensions": metric.allowed_dimensions,
        }

    # Default periods supported
    periods = ["2024", "2025", "2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4",
               "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]

    return SchemaResponse(
        metrics=sorted(list(catalog.metrics.keys())),
        periods=sorted(periods),
        metric_details=metric_details,
    )
