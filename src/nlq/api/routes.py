"""
API route definitions for AOS-NLQ.

Endpoints:
- POST /v1/query: Process natural language query
- GET /v1/health: Health check
- GET /v1/schema: Return available metrics and periods

All endpoints return JSON responses with consistent structure.
"""

import logging
import os
from datetime import date
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.nlq.core.confidence import bounded_confidence
from src.nlq.core.executor import QueryExecutor
from src.nlq.core.parser import QueryParser
from src.nlq.core.resolver import PeriodResolver
from src.nlq.knowledge.fact_base import FactBase
from src.nlq.knowledge.schema import FINANCIAL_SCHEMA, get_metric_unit
from src.nlq.llm.client import ClaudeClient
from src.nlq.models.query import NLQRequest, QueryIntent
from src.nlq.models.response import NLQResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# Lazy-loaded singletons
_fact_base: FactBase = None
_claude_client: ClaudeClient = None


def get_fact_base() -> FactBase:
    """Get or create the fact base singleton."""
    global _fact_base
    if _fact_base is None:
        _fact_base = FactBase()
        # Try multiple paths for fact base
        possible_paths = [
            Path("data/fact_base.json"),
            Path("/home/user/AOS-NLQ/data/fact_base.json"),
            Path("./data/fact_base.json"),
        ]
        for path in possible_paths:
            if path.exists():
                _fact_base.load(path)
                logger.info(f"Loaded fact base from {path}")
                break
        else:
            logger.warning("Fact base not found at any expected path")
    return _fact_base


def get_claude_client() -> ClaudeClient:
    """Get or create the Claude client singleton."""
    global _claude_client
    if _claude_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not configured"
            )
        _claude_client = ClaudeClient(api_key=api_key)
    return _claude_client


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    fact_base_loaded: bool
    claude_available: bool


class SchemaResponse(BaseModel):
    """Schema endpoint response."""
    metrics: List[str]
    periods: List[str]
    metric_details: Dict


@router.post("/query", response_model=NLQResponse)
async def query(request: NLQRequest) -> NLQResponse:
    """
    Process a natural language query about financial data.

    Returns the answer with confidence score bounded [0.0, 1.0].
    """
    try:
        # Get dependencies
        fact_base = get_fact_base()
        claude_client = get_claude_client()

        # Set up components
        parser = QueryParser(claude_client)
        reference_date = request.reference_date or date.today()
        resolver = PeriodResolver(reference_date)
        executor = QueryExecutor(fact_base)

        # Parse the query
        parsed = parser.parse(request.question)
        logger.info(f"Parsed query: {parsed}")

        # Resolve the primary period
        resolved = resolver.resolve(parsed.period_reference)
        parsed.resolved_period = resolver.to_period_key(resolved)
        logger.info(f"Resolved period: {parsed.resolved_period}")

        # Resolve comparison period for comparison queries
        if parsed.intent == QueryIntent.COMPARISON_QUERY and parsed.comparison_period:
            comp_resolved = resolver.resolve(parsed.comparison_period)
            parsed.comparison_period = resolver.to_period_key(comp_resolved)
            logger.info(f"Resolved comparison period: {parsed.comparison_period}")

        # Resolve aggregation periods for aggregation queries
        if parsed.intent == QueryIntent.AGGREGATION_QUERY and parsed.aggregation_periods:
            resolved_agg_periods = []
            for period in parsed.aggregation_periods:
                agg_resolved = resolver.resolve(period)
                resolved_agg_periods.append(resolver.to_period_key(agg_resolved))
            parsed.aggregation_periods = resolved_agg_periods
            logger.info(f"Resolved aggregation periods: {parsed.aggregation_periods}")

        # Execute the query
        result = executor.execute(parsed)

        if not result.success:
            return NLQResponse(
                success=False,
                confidence=bounded_confidence(result.confidence),
                error_code=result.error,
                error_message=result.message,
                parsed_intent=parsed.intent.value,
                resolved_metric=parsed.metric,
                resolved_period=parsed.resolved_period,
            )

        # Format the answer based on intent type
        unit = get_metric_unit(parsed.metric)
        answer, formatted_value = _format_answer(parsed, result, unit)

        return NLQResponse(
            success=True,
            answer=answer,
            value=formatted_value,
            unit=unit,
            confidence=bounded_confidence(result.confidence),
            parsed_intent=parsed.intent.value,
            resolved_metric=parsed.metric,
            resolved_period=parsed.resolved_period,
        )

    except ValueError as e:
        logger.error(f"Query parsing error: {e}")
        return NLQResponse(
            success=False,
            confidence=0.0,
            error_code="PARSE_ERROR",
            error_message=str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error processing query: {e}")
        return NLQResponse(
            success=False,
            confidence=0.0,
            error_code="INTERNAL_ERROR",
            error_message="An unexpected error occurred",
        )


def _format_answer(parsed, result, unit: str) -> tuple:
    """Format the answer based on intent type."""
    metric_display = parsed.metric.replace('_', ' ').title()

    if parsed.intent == QueryIntent.POINT_QUERY:
        formatted_value = round(result.value, 1)
        if unit == "%":
            answer = f"{metric_display} for {parsed.resolved_period} was {formatted_value}%"
        else:
            answer = f"{metric_display} for {parsed.resolved_period} was ${formatted_value} million"
        return answer, formatted_value

    elif parsed.intent == QueryIntent.COMPARISON_QUERY:
        data = result.value
        val1 = round(data["value1"], 1)
        val2 = round(data["value2"], 1)
        diff = round(data["difference"], 1)
        pct = round(data["pct_change"], 1) if data["pct_change"] else 0

        period1, period2 = data["period1"], data["period2"]

        if unit == "%":
            # For percentage metrics, show the values and whether it improved
            if diff > 0:
                answer = f"{metric_display} improved from {val2}% in {period2} to {val1}% in {period1}"
            elif diff < 0:
                answer = f"{metric_display} declined from {val2}% in {period2} to {val1}% in {period1}"
            else:
                answer = f"{metric_display} remained at {val1}% from {period2} to {period1}"
        else:
            # For dollar metrics, show the change
            direction = "increased" if diff > 0 else "decreased" if diff < 0 else "remained unchanged"
            answer = f"{metric_display} {direction} from ${val2} million in {period2} to ${val1} million in {period1} (${abs(diff)} million, {abs(pct)}%)"

        return answer, {"period1": period1, "value1": val1, "period2": period2, "value2": val2, "change": diff, "pct_change": pct}

    elif parsed.intent == QueryIntent.AGGREGATION_QUERY:
        data = result.value
        agg_result = round(data["result"], 1)
        agg_type = data["aggregation_type"]

        if agg_type == "average":
            if unit == "%":
                answer = f"Average {metric_display.lower()} was {agg_result}%"
            else:
                answer = f"Average {metric_display.lower()} was ${agg_result} million"
        else:  # sum
            if unit == "%":
                answer = f"Total {metric_display.lower()} was {agg_result}%"
            else:
                answer = f"Total {metric_display.lower()} was ${agg_result} million"

        return answer, agg_result

    elif parsed.intent == QueryIntent.BREAKDOWN_QUERY:
        data = result.value
        breakdown = data["breakdown"]
        period = data["period"]

        # Format breakdown as readable string
        parts = []
        for metric, value in breakdown.items():
            metric_unit = get_metric_unit(metric)
            formatted = round(value, 1)
            display = metric.replace('_', ' ').title()
            if metric_unit == "%":
                parts.append(f"{display}: {formatted}%")
            else:
                parts.append(f"{display}: ${formatted}M")

        answer = f"Breakdown for {period}: {', '.join(parts)}"
        return answer, breakdown

    else:
        # Fallback for unknown intent
        formatted_value = round(result.value, 1) if isinstance(result.value, (int, float)) else result.value
        if unit == "%":
            answer = f"{metric_display} for {parsed.resolved_period} was {formatted_value}%"
        else:
            answer = f"{metric_display} for {parsed.resolved_period} was ${formatted_value} million"
        return answer, formatted_value


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    Health check endpoint.

    Returns service status and component availability.
    """
    fact_base_loaded = False
    claude_available = False

    try:
        fb = get_fact_base()
        fact_base_loaded = len(fb.available_metrics) > 0
    except Exception:
        pass

    try:
        # Don't actually call Claude for health check to avoid costs
        claude_available = os.environ.get("ANTHROPIC_API_KEY") is not None
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if fact_base_loaded else "degraded",
        version="0.1.0",
        fact_base_loaded=fact_base_loaded,
        claude_available=claude_available,
    )


@router.get("/schema", response_model=SchemaResponse)
async def schema() -> SchemaResponse:
    """
    Return available metrics and periods.

    Useful for building UIs and understanding what queries are supported.
    """
    fact_base = get_fact_base()

    # Get metric details from schema
    metric_details = {}
    for name, defn in FINANCIAL_SCHEMA.items():
        metric_details[name] = {
            "display_name": defn.display_name,
            "type": defn.metric_type.value,
            "unit": defn.unit,
        }

    return SchemaResponse(
        metrics=sorted(list(fact_base.available_metrics)),
        periods=sorted(list(fact_base.available_periods)),
        metric_details=metric_details,
    )
