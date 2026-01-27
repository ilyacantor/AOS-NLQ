"""
Configuration management for AOS-NLQ.

Handles environment variables, settings, and configuration loading.
Uses pydantic-settings for validation and type safety.
"""

import os
from datetime import date
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


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
