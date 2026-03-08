"""
Configuration management for AOS-NLQ.

Handles environment variables, settings, and configuration loading.
Uses pydantic-settings for validation and type safety.

Tenant ID resolution: use get_tenant_id() — resolves from AOS_TENANT_ID
env var, then from the most recent data/tenants/*.json file. Never falls
back silently; raises RuntimeError if no tenant can be determined.
"""

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# Tenant ID resolution (replaces the old DEFAULT_TENANT_ID constant)
# ---------------------------------------------------------------------------

_tenant_id_cache: Optional[str] = None


def get_tenant_id() -> str:
    """Resolve the active tenant ID.

    Resolution order:
      1. AOS_TENANT_ID environment variable
      2. Most recently modified file in data/tenants/*.json (stem = tenant_id)
      3. RuntimeError — no silent fallback

    The result is cached after first resolution. Call reset_tenant_cache()
    to clear (useful in tests).
    """
    global _tenant_id_cache
    if _tenant_id_cache is not None:
        return _tenant_id_cache

    # 1. Environment variable
    env_tid = os.environ.get("AOS_TENANT_ID")
    if env_tid:
        _tenant_id_cache = env_tid
        return _tenant_id_cache

    # 2. Most recent tenant JSON file
    tenants_dir = Path(__file__).resolve().parent.parent.parent / "data" / "tenants"
    if tenants_dir.is_dir():
        tenant_files = sorted(tenants_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if tenant_files:
            _tenant_id_cache = tenant_files[0].stem
            return _tenant_id_cache

    raise RuntimeError(
        "Cannot determine tenant_id: AOS_TENANT_ID env var is not set and "
        f"no tenant JSON files found in {tenants_dir}. "
        "Set AOS_TENANT_ID or ensure data/tenants/<tenant_id>.json exists."
    )


def reset_tenant_cache() -> None:
    """Clear the cached tenant ID. For testing only."""
    global _tenant_id_cache
    _tenant_id_cache = None


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
    fact_base_path: str = Field(
        default="data/fact_base.json",
        description="Path to the fact base JSON file"
    )

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
