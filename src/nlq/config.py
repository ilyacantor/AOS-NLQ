"""
Configuration management for AOS-NLQ.

Handles environment variables, settings, and configuration loading.
Uses pydantic-settings for validation and type safety.

IMPORTANT: Module-level constants defined here (like DEFAULT_TENANT_ID)
are import-safe — they use os.environ directly, not pydantic Settings,
so they work even before the full app is configured. This allows service
modules to import them at the top level for dataclass defaults.
"""

import os
from datetime import date
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# Import-safe constants (no pydantic dependency — safe for dataclass defaults)
# ---------------------------------------------------------------------------

# Single source of truth for the default tenant ID.
# Configurable via NLQ_DEFAULT_TENANT_ID env var. Previously hardcoded
# in 4 separate files; now centralized here.
DEFAULT_TENANT_ID: str = os.environ.get(
    "NLQ_DEFAULT_TENANT_ID",
    "00000000-0000-0000-0000-000000000001",
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Required
    anthropic_api_key: str = Field(
        ...,
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

    # Multi-tenancy
    default_tenant_id: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        description=(
            "Default tenant UUID for single-tenant deployments. "
            "Set via NLQ_DEFAULT_TENANT_ID env var to override."
        ),
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
