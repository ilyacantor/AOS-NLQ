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

    _tenant_id_cache = raw_tid
    return _tenant_id_cache


def reset_tenant_cache() -> None:
    """Clear the cached tenant ID. For testing only."""
    global _tenant_id_cache
    _tenant_id_cache = None


def get_available_snapshots() -> list:
    """Fetch available DCL snapshots for the current tenant.

    Calls GET {DCL_API_URL}/api/dcl/snapshots?tenant_id={tenant_id}.
    Returns list of snapshot dicts with dcl_ingest_id, snapshot_name,
    run_timestamp, total_rows, is_current.

    Raises RuntimeError if DCL_API_URL is not set or tenant_id is missing.
    Raises ConnectionError if DCL is unreachable.
    """
    import httpx

    dcl_url = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not dcl_url:
        raise RuntimeError(
            "DCL_API_URL is not configured — cannot fetch snapshots. "
            "Set DCL_API_URL in environment or render.yaml."
        )

    tenant_id = get_tenant_id()
    if not tenant_id:
        raise RuntimeError(
            "Cannot fetch snapshots — tenant_id is not configured. "
            "Set AOS_TENANT_ID in environment."
        )

    url = f"{dcl_url}/api/dcl/snapshots"
    try:
        resp = httpx.get(url, params={"tenant_id": tenant_id}, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("snapshots", [])
    except httpx.ConnectError as e:
        raise ConnectionError(
            f"DCL unreachable at {url} — cannot fetch snapshots: {e}"
        ) from e
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"DCL returned {e.response.status_code} for snapshots: {e.response.text}"
        ) from e


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
