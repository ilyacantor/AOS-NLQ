"""
Configuration management for AOS-NLQ.

Handles environment variables, settings, and configuration loading.
Uses pydantic-settings for validation and type safety.

Tenant ID resolution: use get_tenant_id() — resolves from AOS_TENANT_ID
env var, then from the most recent data/tenants/*.json file. Never falls
back silently; raises RuntimeError if no tenant can be determined.
"""

import json
import logging
import os
import uuid as _uuid_mod
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

_config_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tenant ID resolution (replaces the old DEFAULT_TENANT_ID constant)
# ---------------------------------------------------------------------------

_tenant_id_cache: Optional[str] = None


def get_tenant_id() -> Optional[str]:
    """Resolve the active tenant ID.

    Resolution order:
      1. AOS_TENANT_ID environment variable
      2. Most recently modified file in data/tenants/*.json (reads tenant_id from JSON content)
      3. None — logged loudly, never crashes

    The resolved value is validated as a UUID before returning.
    If it is not a valid UUID, returns None and logs an actionable error.

    The result is cached after first resolution. Call reset_tenant_cache()
    to clear (useful in tests).
    """
    global _tenant_id_cache
    if _tenant_id_cache is not None:
        return _tenant_id_cache

    raw_tid: Optional[str] = None
    source: str = "unknown"

    # 1. Environment variable
    env_tid = os.environ.get("AOS_TENANT_ID", "").strip()
    if env_tid:
        raw_tid = env_tid
        source = "AOS_TENANT_ID env var"
    else:
        # 2. Most recent tenant JSON file — read tenant_id from file content
        tenants_dir = Path(__file__).resolve().parent.parent.parent / "data" / "tenants"
        if tenants_dir.is_dir():
            tenant_files = sorted(
                tenants_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if tenant_files:
                with open(tenant_files[0]) as f:
                    tenant_data = json.load(f)
                raw_tid = tenant_data.get("tenant_id", tenant_files[0].stem)
                source = f"JSON file {tenant_files[0].name}"

    if raw_tid is None:
        _config_logger.error(
            "FATAL CONFIG: Cannot determine tenant_id. "
            "AOS_TENANT_ID env var is empty/missing and no tenant JSON files found. "
            "Set AOS_TENANT_ID to a valid UUID on Render. "
            "Returning None — all tenant-filtered queries will be skipped."
        )
        return None

    # Validate UUID format before caching
    try:
        _uuid_mod.UUID(raw_tid)
    except (ValueError, AttributeError):
        raise RuntimeError(
            f"FATAL CONFIG: get_tenant_id() resolved '{raw_tid}' from {source}, "
            f"but this is NOT a valid UUID. The rag_sessions/rag_cache_entries tables "
            f"require UUID tenant_id columns. "
            f"Set AOS_TENANT_ID to a valid UUID (e.g. '00000000-0000-0000-0000-000000000001')."
        )

    _tenant_id_cache = raw_tid
    return _tenant_id_cache


def reset_tenant_cache() -> None:
    """Clear the cached tenant ID. For testing only."""
    global _tenant_id_cache
    _tenant_id_cache = None


# ---------------------------------------------------------------------------
# SE identity resolution — from DCL /api/dcl/snapshots (tenant_runs table)
# ---------------------------------------------------------------------------

_dcl_ingest_id_cache: Optional[str] = None


def get_dcl_ingest_id() -> str:
    """Resolve the active SE pipeline identity from DCL's tenant_runs table.

    Calls GET /api/dcl/snapshots?tenant_id=<UUID> and returns the
    current snapshot's dcl_ingest_id. The SE pipeline writes via PG
    direct and updates tenant_runs atomically.

    Does NOT require Convergence to be running.
    """
    global _dcl_ingest_id_cache
    if _dcl_ingest_id_cache is not None:
        return _dcl_ingest_id_cache

    import httpx

    dcl_url = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not dcl_url:
        raise RuntimeError(
            "DCL_API_URL environment variable is not set — "
            "cannot resolve SE identity from DCL."
        )

    tenant_id = get_tenant_id()
    params = {"tenant_id": tenant_id} if tenant_id else {}

    try:
        resp = httpx.get(f"{dcl_url}/api/dcl/snapshots", params=params, timeout=10.0)
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to DCL at {dcl_url} — "
            f"is the DCL service running on port 8004?"
        )

    if resp.status_code != 200:
        raise RuntimeError(
            f"DCL /api/dcl/snapshots returned {resp.status_code}: {resp.text[:500]}"
        )

    snapshots = resp.json().get("snapshots", [])
    current = next((s for s in snapshots if s.get("is_current")), None)
    if not current:
        raise RuntimeError(
            f"No active SE pipeline identity found in DCL at {dcl_url}. "
            f"tenant_runs has no current_run_id for this tenant. "
            f"Run the SE pipeline first."
        )

    _dcl_ingest_id_cache = current["dcl_ingest_id"]
    _config_logger.info(
        "Resolved dcl_ingest_id=%s from DCL tenant_runs (SE identity)",
        _dcl_ingest_id_cache,
    )
    return _dcl_ingest_id_cache


def reset_dcl_ingest_cache() -> None:
    """Clear the cached dcl_ingest_id. For testing or after new pipeline ingest."""
    global _dcl_ingest_id_cache
    _dcl_ingest_id_cache = None


# ---------------------------------------------------------------------------
# ME identity resolution — from Convergence engagement/active
# ---------------------------------------------------------------------------

_convergence_run_id_cache: Optional[str] = None


def get_convergence_run_id() -> str:
    """Resolve the active pipeline_run_id from Convergence.

    Calls Convergence's /engagement/active?tenant_id=<UUID> to get the
    current_pipeline_run_id. This is the ME identity — used when
    Reports queries hit Convergence (combining, overlap, bridge, QoE).

    Requires CONVERGENCE_API_URL to be set and Convergence to be running.
    """
    global _convergence_run_id_cache
    if _convergence_run_id_cache is not None:
        return _convergence_run_id_cache

    import httpx

    tenant_id = get_tenant_id()
    if not tenant_id:
        raise RuntimeError(
            "Cannot resolve convergence_run_id — tenant_id is not available. "
            "Set AOS_TENANT_ID env var first."
        )

    convergence_url = os.environ.get("CONVERGENCE_API_URL", "").rstrip("/")
    if not convergence_url:
        raise RuntimeError(
            "CONVERGENCE_API_URL environment variable is not set — "
            "cannot resolve pipeline_run_id from Convergence."
        )

    url = f"{convergence_url}/api/convergence/engagement/active"
    try:
        resp = httpx.get(url, params={"tenant_id": tenant_id}, timeout=10.0)
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to Convergence at {convergence_url} — "
            f"is the Convergence service running on port 8010?"
        )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Convergence engagement/active returned {resp.status_code}: "
            f"{resp.text[:500]}"
        )

    data = resp.json()
    run_id = data.get("current_pipeline_run_id")
    if not run_id:
        raise RuntimeError(
            "Convergence engagement/active did not return current_pipeline_run_id — "
            "no pipeline run has been ingested for this tenant. "
            "Run the ingest pipeline first."
        )

    _convergence_run_id_cache = run_id
    _config_logger.info(
        "Resolved convergence_run_id=%s from Convergence engagement/active (ME identity)",
        run_id,
    )
    return _convergence_run_id_cache


def reset_convergence_run_cache() -> None:
    """Clear the cached convergence_run_id. For testing or after new pipeline ingest."""
    global _convergence_run_id_cache
    _convergence_run_id_cache = None


# ---------------------------------------------------------------------------
# Unified identity resolution — mode-aware
# ---------------------------------------------------------------------------


def get_identity() -> dict:
    """Get tenant_id + pipeline_run_id for the current request mode.

    SE mode: pipeline_run_id from DCL (get_dcl_ingest_id)
    ME mode: pipeline_run_id from Convergence (get_convergence_run_id)

    If _snapshot_id_ctx is set (operator selected a specific snapshot),
    uses that directly as pipeline_run_id for SE mode.
    """
    from src.nlq.services.dcl_semantic_client import _aos_mode_ctx, _snapshot_id_ctx

    mode = _aos_mode_ctx.get()
    tenant_id = get_tenant_id()

    if mode == "ME":
        pipeline_run_id = get_convergence_run_id()
    else:
        snapshot_override = _snapshot_id_ctx.get()
        if snapshot_override:
            pipeline_run_id = snapshot_override
        else:
            pipeline_run_id = get_dcl_ingest_id()

    return {"tenant_id": tenant_id, "pipeline_run_id": pipeline_run_id}


# ---------------------------------------------------------------------------
# Snapshot catalog — for the frontend selector
# ---------------------------------------------------------------------------


def get_available_snapshots() -> list:
    """Fetch available snapshots from DCL's tenant_runs table.

    Calls GET /api/dcl/snapshots?tenant_id=<UUID> which reads
    tenant_runs and enriches each run with triple counts.

    Returns list of dicts sorted current-first:
    [{dcl_ingest_id, snapshot_name, run_timestamp, total_rows, pipe_count}]
    """
    import httpx

    dcl_url = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not dcl_url:
        raise RuntimeError(
            "DCL_API_URL environment variable is not set — "
            "cannot fetch available snapshots."
        )

    tenant_id = get_tenant_id()
    params = {"tenant_id": tenant_id} if tenant_id else {}

    try:
        resp = httpx.get(f"{dcl_url}/api/dcl/snapshots", params=params, timeout=10.0)
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to DCL at {dcl_url} — "
            f"is the DCL service running?"
        )

    if resp.status_code != 200:
        raise RuntimeError(
            f"DCL /api/dcl/snapshots returned {resp.status_code}: {resp.text[:500]}"
        )

    data = resp.json()
    snapshots = data.get("snapshots", [])

    # Add pipe_count field (not tracked in tenant_runs, but the frontend type expects it)
    for s in snapshots:
        s.setdefault("pipe_count", 0)

    return snapshots


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Required — reads bare ANTHROPIC_API_KEY (no NLQ_ prefix) to match
    # render.yaml and direct os.environ.get() call sites in llm/client.py.
    anthropic_api_key: str = Field(
        ...,
        validation_alias="ANTHROPIC_API_KEY",
        description="Anthropic API key for Claude"
    )

    # Optional with defaults
    reference_date: Optional[date] = Field(
        default=None,
        description="Reference date for relative period resolution. Defaults to today."
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    api_host: str = Field(
        default="0.0.0.0",
        description="API host to bind to"
    )

    api_port: int = Field(
        default=8000,
        description="API port to listen on"
    )

    # Paths
    test_questions_path: str = Field(
        default="data/nlq_test_questions.json",
        description="Path to the test questions JSON file"
    )

    class Config:
        env_prefix = "NLQ_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
