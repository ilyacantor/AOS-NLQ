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

    # Check if live ingest data is available
    live_data_available = False
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
        )

    dcl_client = get_semantic_client()
    dcl_connected = bool(dcl_client.dcl_url)
    raw_mode = None
    metric_count = 0
    last_run_id = None
    last_run_timestamp = None
    last_source_systems = None
    freshness_display = None

    # Probe DCL with a lightweight query to get current mode and provenance
    try:
        probe = dcl_client.query(
            metric="revenue",
            time_range={"period": "2025-Q4", "granularity": "quarterly"},
            data_mode=data_mode,
        )
        if probe.get("status") != "error":
            rp = probe.get("run_provenance", {})
            if rp:
                raw_mode = rp.get("mode")
                last_run_id = rp.get("run_id")
                last_run_timestamp = rp.get("run_timestamp")
                last_source_systems = rp.get("source_systems") or None
                freshness_display = rp.get("freshness") or None
            elif probe.get("metadata", {}).get("mode"):
                raw_mode = probe["metadata"]["mode"]
    except (RuntimeError, KeyError, TypeError, AttributeError, OSError) as e:
        logger.warning("DCL probe query failed in pipeline_status: %s", e)

    LIVE_MODES = {"farm", "ingest", "live"}
    is_live = raw_mode and raw_mode.lower() in LIVE_MODES

    try:
        catalog = dcl_client.get_catalog()
        metric_count = len(catalog.metrics)
    except (RuntimeError, KeyError, TypeError, AttributeError, OSError) as e:
        logger.warning("DCL catalog check failed in pipeline_status: %s", e)

    if not is_live:
        raw_mode = None
        last_run_id = None
        last_run_timestamp = None
        last_source_systems = None
        freshness_display = None
        try:
            local_catalog = dcl_client._build_local_catalog()
            metric_count = len(local_catalog.metrics)
        except (FileNotFoundError, IOError, KeyError, ValueError) as e:
            logger.debug("Local catalog build failed; metric_count stays at 0: %s", e)

    return PipelineStatusResponse(
        dcl_connected=bool(dcl_connected and is_live),
        dcl_mode=raw_mode,
        metric_count=metric_count,
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
