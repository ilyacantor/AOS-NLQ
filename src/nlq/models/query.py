"""
Request and query models for AOS-NLQ.

Contains Pydantic models for:
- API request validation (NLQRequest)
- Internal parsed query representation (ParsedQuery)
"""

from datetime import date
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class QueryMode(str, Enum):
    """Query processing modes."""
    STATIC = "static"  # Cache-only, no LLM fallback
    AI = "ai"          # Cache + LLM fallback


class QueryIntent(str, Enum):
    """Types of query intents supported by the NLQ engine."""
    POINT_QUERY = "POINT_QUERY"           # Single metric, single period
    COMPARISON_QUERY = "COMPARISON_QUERY"  # Compare two periods
    TREND_QUERY = "TREND_QUERY"           # Multiple periods over time
    AGGREGATION_QUERY = "AGGREGATION_QUERY"  # Sum/avg over periods
    BREAKDOWN_QUERY = "BREAKDOWN_QUERY"   # Breakdown by dimension


class PeriodType(str, Enum):
    """Types of time periods."""
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    HALF_YEAR = "half_year"
    YTD = "ytd"


class NLQRequest(BaseModel):
    """Input model for natural language query requests."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language question about financial data"
    )

    reference_date: Optional[date] = Field(
        default=None,
        description="Date context for relative references (e.g., 'last quarter'). Defaults to today."
    )

    mode: QueryMode = Field(
        default=QueryMode.AI,
        description="Query mode: 'static' for cache-only, 'ai' for cache + LLM fallback"
    )

    session_id: Optional[str] = Field(
        default=None,
        description="Browser session ID for LLM call tracking"
    )

    data_mode: Optional[str] = Field(
        default="live",
        description="Data mode: 'live' for DCL, 'demo' for local fact_base.json"
    )

    persona: Optional[str] = Field(
        default=None,
        description="Active persona (CFO/CRO/COO/CTO/CHRO). Authoritative for dashboard generation."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "What was revenue last year?",
                "reference_date": "2026-01-27",
                "mode": "ai",
                "session_id": "ses_1234567890_abc123"
            }
        }
    )


class ParsedQuery(BaseModel):
    """Internal representation of a parsed natural language query."""

    intent: QueryIntent = Field(
        ...,
        description="The type of query being made"
    )

    metric: str = Field(
        ...,
        description="Canonical metric name (normalized from synonyms)"
    )

    period_type: PeriodType = Field(
        ...,
        description="Type of time period"
    )

    period_reference: str = Field(
        ...,
        description="Period reference (e.g., '2024', 'last_quarter', 'Q4 2025')"
    )

    is_relative: bool = Field(
        default=False,
        description="Whether the period reference is relative to reference_date"
    )

    resolved_period: Optional[str] = Field(
        default=None,
        description="Absolute period after resolution (e.g., '2025-Q4')"
    )

    comparison_period: Optional[str] = Field(
        default=None,
        description="Second period for comparison queries"
    )

    # Aggregation query fields
    aggregation_type: Optional[str] = Field(
        default=None,
        description="Type of aggregation: 'sum' or 'average'"
    )

    aggregation_periods: Optional[List[str]] = Field(
        default=None,
        description="List of periods to aggregate over"
    )

    # Trend query fields
    trend_periods: Optional[List[str]] = Field(
        default=None,
        description="List of periods to show in trend (e.g., yearly periods for 'by year' queries)"
    )

    # Breakdown query fields
    breakdown_metrics: Optional[List[str]] = Field(
        default=None,
        description="List of metrics to show in breakdown"
    )

    raw_metric: Optional[str] = Field(
        default=None,
        description="Original metric term before normalization"
    )

    # Entity extraction (DCL integration)
    entity: Optional[str] = Field(
        default=None,
        description="Company/customer entity name extracted from query (e.g., 'Acme Corp')"
    )

    dimension: Optional[str] = Field(
        default=None,
        description="Breakdown dimension extracted from query (e.g., 'region', 'segment')"
    )
