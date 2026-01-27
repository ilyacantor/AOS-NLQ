"""
API route definitions for AOS-NLQ.

Endpoints:
- POST /v1/query: Process natural language query (NLQResponse)
- POST /v1/query/galaxy: Process query with Galaxy visualization (IntentMapResponse)
- GET /v1/health: Health check
- GET /v1/schema: Return available metrics and periods

All endpoints return JSON responses with consistent structure.
"""

import logging
import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.nlq.core.ambiguity import detect_ambiguity, needs_clarification
from src.nlq.core.confidence import bounded_confidence
from src.nlq.core.executor import QueryExecutor
from src.nlq.core.node_generator import (
    calculate_overall_metrics,
    generate_nodes_for_aggregation_query,
    generate_nodes_for_ambiguous_query,
    generate_nodes_for_breakdown_query,
    generate_nodes_for_comparison_query,
    generate_nodes_for_point_query,
)
from src.nlq.core.parser import QueryParser
from src.nlq.core.resolver import PeriodResolver
from src.nlq.knowledge.fact_base import FactBase
from src.nlq.knowledge.schema import FINANCIAL_SCHEMA, get_metric_unit
from src.nlq.llm.client import ClaudeClient
from src.nlq.models.query import NLQRequest, QueryIntent
from src.nlq.models.response import AmbiguityType, IntentMapResponse, IntentNode, MatchType, NLQResponse

logger = logging.getLogger(__name__)


def _format_enriched_text_response(
    nodes: List[IntentNode],
    query_type: str,
    ambiguity_type: Optional[AmbiguityType],
    clarification: Optional[str],
) -> str:
    """
    Generate enriched text response from nodes.

    Patterns by query type:
    - POINT_QUERY: "{Primary}. Related: {metric1} was {value1}, {metric2} was {value2}."
    - VAGUE_METRIC: "{All candidates}. For context: {supporting}. Which did you mean?"
    - YES_NO: "{Yes/No with reason}. Supporting data: {evidence metrics}."
    - INCOMPLETE: "Assuming {interpretation}: {answer}. Related: {context}."
    - BROAD_REQUEST: "**Summary:** {structured list}. Key insight: {observation}."
    - NOT_APPLICABLE: "{Concept} doesn't apply. Instead: {alternatives}."
    - COMPARISON: "{Period1} vs {Period2}: {comparisons}. Change: {deltas}."
    """
    if not nodes:
        return "No data available for this query."

    # Separate nodes by ring
    exact_nodes = [n for n in nodes if n.match_type == MatchType.EXACT]
    potential_nodes = [n for n in nodes if n.match_type == MatchType.POTENTIAL]
    hypothesis_nodes = [n for n in nodes if n.match_type == MatchType.HYPOTHESIS]

    # Format helper
    def format_node_value(node: IntentNode) -> str:
        if node.formatted_value:
            return f"{node.display_name}: {node.formatted_value}"
        elif node.value is not None:
            return f"{node.display_name}: {node.value}"
        return node.display_name

    # Handle by ambiguity type first
    if ambiguity_type:
        return _format_ambiguous_response(
            ambiguity_type, exact_nodes, potential_nodes, hypothesis_nodes, clarification
        )

    # Handle by query type
    if query_type == "POINT_QUERY":
        return _format_point_query_response(exact_nodes, potential_nodes, hypothesis_nodes)

    elif query_type == "COMPARISON_QUERY":
        return _format_comparison_response(exact_nodes, potential_nodes)

    elif query_type == "AGGREGATION_QUERY":
        return _format_aggregation_response(exact_nodes, potential_nodes)

    elif query_type == "BREAKDOWN_QUERY":
        return _format_breakdown_response(exact_nodes, hypothesis_nodes)

    else:
        # Default: list all nodes
        parts = [format_node_value(n) for n in nodes if n.formatted_value]
        return ", ".join(parts) if parts else "Query processed."


def _format_point_query_response(
    exact_nodes: List[IntentNode],
    potential_nodes: List[IntentNode],
    hypothesis_nodes: List[IntentNode],
) -> str:
    """Format POINT_QUERY: Primary answer + Related context."""
    parts = []

    # Primary answer from EXACT nodes
    if exact_nodes:
        primary = exact_nodes[0]
        if primary.formatted_value:
            parts.append(f"{primary.display_name} was {primary.formatted_value}")
            if primary.period:
                parts[0] += f" for {primary.period}"

    # Related context from POTENTIAL nodes
    if potential_nodes:
        related = []
        for node in potential_nodes[:3]:  # Limit to 3 related
            if node.formatted_value:
                related.append(f"{node.display_name} was {node.formatted_value}")
        if related:
            parts.append(f"Related: {', '.join(related)}")

    # Additional context from HYPOTHESIS if interesting
    if hypothesis_nodes and len(hypothesis_nodes) > 0:
        ctx = hypothesis_nodes[0]
        if ctx.formatted_value and ctx.rationale:
            parts.append(f"Context: {ctx.display_name} ({ctx.formatted_value})")

    return ". ".join(parts) + "." if parts else "No data available."


def _format_comparison_response(
    exact_nodes: List[IntentNode],
    potential_nodes: List[IntentNode],
) -> str:
    """Format COMPARISON_QUERY: Period vs Period with change."""
    parts = []

    # Get the comparison values from EXACT nodes
    if len(exact_nodes) >= 2:
        n1, n2 = exact_nodes[0], exact_nodes[1]
        parts.append(f"{n1.display_name}: {n1.formatted_value} ({n1.period}) vs {n2.formatted_value} ({n2.period})")
    elif exact_nodes:
        parts.append(f"{exact_nodes[0].display_name}: {exact_nodes[0].formatted_value}")

    # Add change/delta from POTENTIAL if available
    for node in potential_nodes:
        if "change" in node.metric.lower() or "delta" in node.metric.lower():
            parts.append(f"Change: {node.formatted_value}")
            break

    # Add related metrics context
    related = [n for n in potential_nodes if "change" not in n.metric.lower()]
    if related:
        rel_parts = [f"{n.display_name}: {n.formatted_value}" for n in related[:2] if n.formatted_value]
        if rel_parts:
            parts.append(f"Related: {', '.join(rel_parts)}")

    return ". ".join(parts) + "." if parts else "Comparison data unavailable."


def _format_aggregation_response(
    exact_nodes: List[IntentNode],
    potential_nodes: List[IntentNode],
) -> str:
    """Format AGGREGATION_QUERY: Result + component breakdown."""
    parts = []

    # Primary aggregation result
    if exact_nodes:
        primary = exact_nodes[0]
        parts.append(f"{primary.display_name}: {primary.formatted_value}")

    # Component values from remaining EXACT nodes
    if len(exact_nodes) > 1:
        components = [f"{n.display_name}: {n.formatted_value}" for n in exact_nodes[1:4] if n.formatted_value]
        if components:
            parts.append(f"Components: {', '.join(components)}")

    # Related context
    if potential_nodes:
        related = [f"{n.display_name}: {n.formatted_value}" for n in potential_nodes[:2] if n.formatted_value]
        if related:
            parts.append(f"Related: {', '.join(related)}")

    return ". ".join(parts) + "." if parts else "Aggregation result unavailable."


def _format_breakdown_response(
    exact_nodes: List[IntentNode],
    hypothesis_nodes: List[IntentNode],
) -> str:
    """Format BREAKDOWN_QUERY: Structured list of components."""
    parts = []

    if exact_nodes:
        # Summary header
        period = exact_nodes[0].period or "current period"
        parts.append(f"**Breakdown for {period}:**")

        # List all components
        for node in exact_nodes:
            if node.formatted_value:
                parts.append(f"• {node.display_name}: {node.formatted_value}")

    # Key insight from context
    if hypothesis_nodes:
        ctx = hypothesis_nodes[0]
        if ctx.formatted_value:
            parts.append(f"Context: {ctx.display_name} at {ctx.formatted_value}")

    return " ".join(parts) if parts else "Breakdown data unavailable."


def _format_ambiguous_response(
    ambiguity_type: AmbiguityType,
    exact_nodes: List[IntentNode],
    potential_nodes: List[IntentNode],
    hypothesis_nodes: List[IntentNode],
    clarification: Optional[str],
) -> str:
    """Format response for ambiguous queries."""
    parts = []

    if ambiguity_type == AmbiguityType.VAGUE_METRIC:
        # All candidates are equal possibilities
        candidates = [f"{n.display_name}: {n.formatted_value}" for n in potential_nodes if n.formatted_value]
        if candidates:
            parts.append(", ".join(candidates))
        # Context
        if hypothesis_nodes:
            ctx = [f"{n.display_name}: {n.formatted_value}" for n in hypothesis_nodes[:2] if n.formatted_value]
            if ctx:
                parts.append(f"For context: {', '.join(ctx)}")
        # Clarification
        if clarification:
            parts.append(clarification)

    elif ambiguity_type == AmbiguityType.YES_NO:
        # Lead with yes/no answer based on primary
        if exact_nodes:
            primary = exact_nodes[0]
            # Determine yes/no based on value
            if primary.value and isinstance(primary.value, (int, float)):
                answer = "Yes" if primary.value > 0 else "No"
                parts.append(f"{answer} - {primary.display_name} is {primary.formatted_value}")
            else:
                parts.append(f"{primary.display_name}: {primary.formatted_value}")
        # Supporting data
        supporting = [f"{n.display_name}: {n.formatted_value}" for n in potential_nodes if n.formatted_value]
        if supporting:
            parts.append(f"Supporting data: {', '.join(supporting[:3])}")

    elif ambiguity_type == AmbiguityType.INCOMPLETE:
        # Show assumed interpretation
        if exact_nodes:
            primary = exact_nodes[0]
            parts.append(f"Assuming you meant {primary.display_name}: {primary.formatted_value}")
        # Related context
        related = [f"{n.display_name}: {n.formatted_value}" for n in potential_nodes[:2] if n.formatted_value]
        if related:
            parts.append(f"Related: {', '.join(related)}")
        if clarification:
            parts.append(clarification)

    elif ambiguity_type == AmbiguityType.BROAD_REQUEST:
        # Summary of all metrics
        parts.append("**Summary:**")
        all_metrics = exact_nodes + potential_nodes
        for node in all_metrics[:6]:
            if node.formatted_value:
                parts.append(f"• {node.display_name}: {node.formatted_value}")
        # Key insight
        if hypothesis_nodes:
            parts.append(f"Context: {hypothesis_nodes[0].display_name}")

    elif ambiguity_type == AmbiguityType.NOT_APPLICABLE:
        # Explain N/A and offer alternatives
        na_node = next((n for n in hypothesis_nodes if n.metric == "not_applicable"), None)
        if na_node:
            parts.append(f"This concept doesn't apply to your data")
        # Alternatives
        alternatives = [f"{n.display_name}: {n.formatted_value}" for n in potential_nodes if n.formatted_value]
        if alternatives:
            parts.append(f"Instead, consider: {', '.join(alternatives[:2])}")

    elif ambiguity_type in (AmbiguityType.CASUAL_LANGUAGE, AmbiguityType.SHORTHAND):
        # Interpret and provide full context
        if exact_nodes:
            primary = exact_nodes[0]
            parts.append(f"{primary.display_name}: {primary.formatted_value}")
        # Related
        related = [f"{n.display_name}: {n.formatted_value}" for n in potential_nodes[:3] if n.formatted_value]
        if related:
            parts.append(f"Related: {', '.join(related)}")

    else:
        # Default: list all values
        all_nodes = exact_nodes + potential_nodes + hypothesis_nodes
        values = [f"{n.display_name}: {n.formatted_value}" for n in all_nodes if n.formatted_value]
        parts.append(", ".join(values[:5]) if values else "Multiple interpretations possible")
        if clarification:
            parts.append(clarification)

    return ". ".join(parts) + "." if parts else "Query interpreted with multiple possibilities."

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


def _handle_ambiguous_query_text(
    question: str,
    ambiguity_type: AmbiguityType,
    candidates: list,
    clarification: Optional[str],
    fact_base: FactBase,
) -> NLQResponse:
    """Handle an ambiguous query and return text response."""
    from datetime import date as date_type
    period = str(date_type.today().year)

    # Build answer based on ambiguity type
    if ambiguity_type == AmbiguityType.NOT_APPLICABLE:
        # Concept doesn't apply - show alternatives
        concept = candidates[0] if candidates else "this concept"
        alternatives = []
        for alt in candidates[1:3]:
            val = fact_base.query(alt, period) if fact_base else None
            if val is not None:
                unit = get_metric_unit(alt)
                formatted = f"{round(val, 1)}%" if unit == "%" else f"${round(val, 1)}M"
                display = alt.replace('_', ' ').title()
                alternatives.append(f"{display}: {formatted}")

        answer = f"'{concept.replace('_', ' ')}' doesn't apply to this company (we're profitable)."
        if alternatives:
            answer += f" Instead, consider: {', '.join(alternatives)}."

        return NLQResponse(
            success=True,
            answer=answer,
            value=None,
            unit=None,
            confidence=0.6,
            parsed_intent="AMBIGUOUS",
            resolved_metric=None,
            resolved_period=period,
        )

    elif ambiguity_type == AmbiguityType.VAGUE_METRIC:
        # Multiple possible metrics
        options = []
        for metric in candidates[:4]:
            val = fact_base.query(metric, period) if fact_base else None
            if val is not None:
                unit = get_metric_unit(metric)
                formatted = f"{round(val, 1)}%" if unit == "%" else f"${round(val, 1)}M"
                display = metric.replace('_', ' ').title()
                options.append(f"{display}: {formatted}")

        answer = ", ".join(options) if options else "Multiple metrics match your query."
        if clarification:
            answer += f" {clarification}"

        return NLQResponse(
            success=True,
            answer=answer,
            value=None,
            unit=None,
            confidence=0.7,
            parsed_intent="AMBIGUOUS",
            resolved_metric=None,
            resolved_period=period,
        )

    elif ambiguity_type == AmbiguityType.BROAD_REQUEST:
        # User wants multiple metrics
        parts = []
        for metric in candidates[:6]:
            val = fact_base.query(metric, period) if fact_base else None
            if val is not None:
                unit = get_metric_unit(metric)
                formatted = f"{round(val, 1)}%" if unit == "%" else f"${round(val, 1)}M"
                display = metric.replace('_', ' ').title()
                parts.append(f"{display}: {formatted}")

        answer = f"Summary for {period}: " + ", ".join(parts) if parts else "Financial summary requested."

        return NLQResponse(
            success=True,
            answer=answer,
            value=None,
            unit=None,
            confidence=0.85,
            parsed_intent="AMBIGUOUS",
            resolved_metric=None,
            resolved_period=period,
        )

    else:
        # Default handling for other ambiguity types (YES_NO, INCOMPLETE, CASUAL, etc.)
        if candidates:
            primary = candidates[0]
            val = fact_base.query(primary, period) if fact_base else None
            if val is not None:
                unit = get_metric_unit(primary)
                formatted = f"{round(val, 1)}%" if unit == "%" else f"${round(val, 1)}M"
                display = primary.replace('_', ' ').title()
                answer = f"{display} for {period}: {formatted}"

                # Add related context
                if len(candidates) > 1:
                    related = []
                    for rel in candidates[1:3]:
                        rel_val = fact_base.query(rel, period) if fact_base else None
                        if rel_val is not None:
                            rel_unit = get_metric_unit(rel)
                            rel_fmt = f"{round(rel_val, 1)}%" if rel_unit == "%" else f"${round(rel_val, 1)}M"
                            rel_display = rel.replace('_', ' ').title()
                            related.append(f"{rel_display}: {rel_fmt}")
                    if related:
                        answer += f". Related: {', '.join(related)}"

                return NLQResponse(
                    success=True,
                    answer=answer,
                    value=val,
                    unit=unit,
                    confidence=0.75,
                    parsed_intent="AMBIGUOUS",
                    resolved_metric=primary,
                    resolved_period=period,
                )

        return NLQResponse(
            success=True,
            answer=clarification or "Query interpreted with multiple possibilities.",
            value=None,
            unit=None,
            confidence=0.5,
            parsed_intent="AMBIGUOUS",
            resolved_metric=None,
            resolved_period=period,
        )


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

        # Check for ambiguity first (same as Galaxy endpoint)
        ambiguity_type, candidates, clarification = detect_ambiguity(request.question)

        if ambiguity_type and ambiguity_type != AmbiguityType.NONE:
            # Handle ambiguous query with text response
            return _handle_ambiguous_query_text(
                request.question,
                ambiguity_type,
                candidates,
                clarification,
                fact_base,
            )

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


@router.post("/intent-map", response_model=IntentMapResponse)
@router.post("/query/galaxy", response_model=IntentMapResponse)
async def query_galaxy(request: NLQRequest) -> IntentMapResponse:
    """
    Process a natural language query and return Galaxy visualization data.

    Returns IntentMapResponse with:
    - Nodes for orbital rings (EXACT, POTENTIAL, HYPOTHESIS)
    - Confidence and data quality metrics
    - Persona and disambiguation info
    """
    try:
        fact_base = get_fact_base()
        claude_client = get_claude_client()

        parser = QueryParser(claude_client)
        reference_date = request.reference_date or date.today()
        resolver = PeriodResolver(reference_date)
        executor = QueryExecutor(fact_base)

        # Check for ambiguity first
        ambiguity_type, candidates, clarification = detect_ambiguity(request.question)

        if ambiguity_type and ambiguity_type != AmbiguityType.NONE:
            # Handle ambiguous query
            return _handle_ambiguous_query_galaxy(
                request.question,
                ambiguity_type,
                candidates,
                clarification,
                fact_base,
                resolver,
            )

        # Parse the query
        parsed = parser.parse(request.question)
        logger.info(f"Parsed query for galaxy: {parsed}")

        # Resolve periods
        resolved = resolver.resolve(parsed.period_reference)
        parsed.resolved_period = resolver.to_period_key(resolved)

        if parsed.intent == QueryIntent.COMPARISON_QUERY and parsed.comparison_period:
            comp_resolved = resolver.resolve(parsed.comparison_period)
            parsed.comparison_period = resolver.to_period_key(comp_resolved)

        if parsed.intent == QueryIntent.AGGREGATION_QUERY and parsed.aggregation_periods:
            resolved_agg_periods = []
            for period in parsed.aggregation_periods:
                agg_resolved = resolver.resolve(period)
                resolved_agg_periods.append(resolver.to_period_key(agg_resolved))
            parsed.aggregation_periods = resolved_agg_periods

        # Execute the query
        result = executor.execute(parsed)

        if not result.success:
            return _create_error_galaxy_response(
                request.question,
                parsed.intent.value,
                result.error,
                result.message,
            )

        # Generate nodes based on intent
        nodes = _generate_nodes_for_intent(parsed, result, fact_base)

        # Calculate overall metrics
        overall_confidence, overall_data_quality = calculate_overall_metrics(nodes)

        # Format enriched text response using nodes
        text_response = _format_enriched_text_response(
            nodes,
            parsed.intent.value,
            None,  # No ambiguity for clear queries
            None,  # No clarification needed
        )

        # Get primary node
        primary_node_id = nodes[0].id if nodes else None

        return IntentMapResponse(
            query=request.question,
            query_type=parsed.intent.value,
            ambiguity_type=None,
            persona="CFO",  # Default persona
            overall_confidence=overall_confidence,
            overall_data_quality=overall_data_quality,
            node_count=len(nodes),
            nodes=nodes,
            primary_node_id=primary_node_id,
            primary_answer=text_response,
            text_response=text_response,
            needs_clarification=False,
            clarification_prompt=None,
        )

    except ValueError as e:
        logger.error(f"Query parsing error: {e}")
        return _create_error_galaxy_response(
            request.question,
            "UNKNOWN",
            "PARSE_ERROR",
            str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error processing galaxy query: {e}")
        return _create_error_galaxy_response(
            request.question,
            "UNKNOWN",
            "INTERNAL_ERROR",
            "An unexpected error occurred",
        )


def _handle_ambiguous_query_galaxy(
    question: str,
    ambiguity_type: AmbiguityType,
    candidates: list,
    clarification: Optional[str],
    fact_base: FactBase,
    resolver: PeriodResolver,
) -> IntentMapResponse:
    """Handle an ambiguous query and return Galaxy response."""
    # Default to current year
    period = str(date.today().year)

    # Generate nodes for ambiguous query
    nodes = generate_nodes_for_ambiguous_query(
        ambiguity_type,
        candidates,
        period,
        fact_base,
    )

    overall_confidence, overall_data_quality = calculate_overall_metrics(nodes)

    # Build enriched text response for ambiguous query
    text_response = _format_enriched_text_response(
        nodes,
        "AMBIGUOUS",
        ambiguity_type,
        clarification,
    )

    return IntentMapResponse(
        query=question,
        query_type="AMBIGUOUS",
        ambiguity_type=ambiguity_type,
        persona="CFO",
        overall_confidence=overall_confidence,
        overall_data_quality=overall_data_quality,
        node_count=len(nodes),
        nodes=nodes,
        primary_node_id=None,
        primary_answer=None,
        text_response=text_response,
        needs_clarification=needs_clarification(ambiguity_type),
        clarification_prompt=clarification,
    )


def _generate_nodes_for_intent(parsed, result, fact_base) -> list:
    """Generate nodes based on query intent."""
    if parsed.intent == QueryIntent.POINT_QUERY:
        return generate_nodes_for_point_query(
            parsed.metric,
            result.value,
            parsed.resolved_period,
            fact_base,
        )

    elif parsed.intent == QueryIntent.COMPARISON_QUERY:
        data = result.value
        return generate_nodes_for_comparison_query(
            parsed.metric,
            data["period1"],
            data["value1"],
            data["period2"],
            data["value2"],
            data["difference"],
            data["pct_change"],
            fact_base,
        )

    elif parsed.intent == QueryIntent.AGGREGATION_QUERY:
        data = result.value
        return generate_nodes_for_aggregation_query(
            parsed.metric,
            data["aggregation_type"],
            data["result"],
            data["periods"],
            data["values"],
            fact_base,
        )

    elif parsed.intent == QueryIntent.BREAKDOWN_QUERY:
        data = result.value
        return generate_nodes_for_breakdown_query(
            data["breakdown"],
            data["period"],
            fact_base,
        )

    else:
        # Fallback to point query style
        return generate_nodes_for_point_query(
            parsed.metric,
            result.value,
            parsed.resolved_period,
            fact_base,
        )


def _create_error_galaxy_response(
    question: str,
    query_type: str,
    error_code: str,
    error_message: str,
) -> IntentMapResponse:
    """Create an error response for Galaxy endpoint."""
    return IntentMapResponse(
        query=question,
        query_type=query_type,
        ambiguity_type=None,
        persona="CFO",
        overall_confidence=0.0,
        overall_data_quality=0.0,
        node_count=0,
        nodes=[],
        primary_node_id=None,
        primary_answer=None,
        text_response=f"Error: {error_message}",
        needs_clarification=False,
        clarification_prompt=None,
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
