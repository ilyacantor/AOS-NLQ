"""
Response models for AOS-NLQ.

Contains Pydantic models for:
- API response structure (NLQResponse)
- Internal query execution results (QueryResult)

CRITICAL: Confidence scores are bounded [0.0, 1.0] using Pydantic Field constraints.
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class QueryResult(BaseModel):
    """Internal model for query execution results."""

    success: bool = Field(
        ...,
        description="Whether the query executed successfully"
    )

    value: Optional[Any] = Field(
        default=None,
        description="Raw query result value"
    )

    error: Optional[str] = Field(
        default=None,
        description="Error code if query failed"
    )

    message: Optional[str] = Field(
        default=None,
        description="Human-readable message"
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score, always bounded [0.0, 1.0]"
    )


class NLQResponse(BaseModel):
    """Output model for natural language query responses."""

    success: bool = Field(
        ...,
        description="Whether the query was successful"
    )

    answer: Optional[str] = Field(
        default=None,
        description="Human-readable answer"
    )

    value: Optional[Any] = Field(
        default=None,
        description="Raw numeric value"
    )

    unit: Optional[str] = Field(
        default=None,
        description="Unit of measurement (e.g., 'USD millions', 'percent')"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score, ALWAYS bounded [0.0, 1.0]"
    )

    # Debugging/transparency fields
    parsed_intent: Optional[str] = Field(
        default=None,
        description="Detected query intent"
    )

    resolved_metric: Optional[str] = Field(
        default=None,
        description="Canonical metric name after normalization"
    )

    resolved_period: Optional[str] = Field(
        default=None,
        description="Absolute period after resolution"
    )

    # Error handling
    error_code: Optional[str] = Field(
        default=None,
        description="Error code for failed queries"
    )

    error_message: Optional[str] = Field(
        default=None,
        description="Human-readable error message"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "answer": "Revenue for 2025 was $125.5 million",
                "value": 125.5,
                "unit": "USD millions",
                "confidence": 0.95,
                "parsed_intent": "POINT_QUERY",
                "resolved_metric": "revenue",
                "resolved_period": "2025",
                "error_code": None,
                "error_message": None
            }
        }
    )
