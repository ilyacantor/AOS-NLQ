"""
Value formatting and text response utilities.

Extracted from routes.py (C1) — pure formatting functions with no side effects.
Used by both /query and /query/galaxy pipelines.
"""

from typing import List, Optional

from src.nlq.models.query import QueryIntent
from src.nlq.models.response import (
    AmbiguityType,
    IntentNode,
    MatchType,
    RelatedMetric,
)


def nodes_to_related_metrics(nodes: List[IntentNode]) -> List[RelatedMetric]:
    """Convert Galaxy View nodes to Text View related metrics."""
    return [
        RelatedMetric(
            metric=node.metric,
            display_name=node.display_name,
            value=node.value,
            formatted_value=node.formatted_value,
            period=node.period,
            confidence=node.confidence,
            match_type=node.match_type.value,
            rationale=node.rationale,
            domain=node.domain.value if node.domain else None,
        )
        for node in nodes
    ]


def format_enriched_text_response(
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
        return format_ambiguous_response(
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


def format_ambiguous_response(
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
            parts.append("This concept doesn't apply to your data")
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


def format_value_with_unit(value: float, unit: str) -> str:
    """Format a value with its unit for answer text."""
    if unit == "%":
        return f"{round(value, 1)}%"
    elif unit == "USD millions":
        return f"${round(value, 1)}M"
    elif unit == "USD":
        return f"${round(value, 2):,.2f}"
    elif unit == "millions/month":
        return f"${round(value, 2)}M/mo"
    elif unit == "days":
        return f"{round(value, 1)} days"
    elif unit == "hours":
        return f"{round(value, 1)} hours"
    elif unit == "months":
        return f"{round(value, 1)} months"
    elif unit == "people":
        return f"{int(value):,}"
    elif unit == "customers":
        return f"{int(value):,}"
    elif unit in ("tickets", "bugs", "vulnerabilities", "incidents", "deploys", "features", "points"):
        return f"{int(value):,}"
    elif unit == "score":
        return f"{round(value, 2)}"
    elif unit == "x":
        return f"{round(value, 2)}x"
    else:
        return f"{round(value, 2)}"


def format_answer(parsed, result, unit: str) -> tuple:
    """Format the answer based on intent type."""
    metric_display = parsed.metric.replace('_', ' ').title()

    if parsed.intent == QueryIntent.POINT_QUERY:
        # Guard against non-numeric values (e.g., dict from graph resolution)
        if not isinstance(result.value, (int, float)):
            formatted_value = result.value
            formatted_str = str(result.value)
        else:
            formatted_value = round(result.value, 1)
            formatted_str = format_value_with_unit(result.value, unit)
        answer = f"{metric_display} for {parsed.resolved_period} was {formatted_str}"
        return answer, formatted_value

    elif parsed.intent == QueryIntent.COMPARISON_QUERY:
        data = result.value
        val1 = round(data["value1"], 1)
        val2 = round(data["value2"], 1)
        diff = round(data["difference"], 1)
        pct = round(data["pct_change"], 1) if data["pct_change"] else 0

        period1, period2 = data["period1"], data["period2"]
        val1_str = format_value_with_unit(val1, unit)
        val2_str = format_value_with_unit(val2, unit)
        diff_str = format_value_with_unit(abs(diff), unit)

        direction = "increased" if diff > 0 else "decreased"
        answer = f"{metric_display} {direction} from {val2_str} ({period2}) to {val1_str} ({period1}), a change of {diff_str} ({abs(pct)}%)"
        return answer, {"value1": val1, "value2": val2, "difference": diff, "pct_change": pct}

    elif parsed.intent == QueryIntent.TREND_QUERY:
        data = result.value
        trend_dir = data.get("trend_direction", "unknown")
        change = data.get("change_pct", 0)
        answer = f"{metric_display} has been {trend_dir} ({change:+.1f}% change over {data.get('period_count', 0)} periods)"
        return answer, data

    elif parsed.intent == QueryIntent.AGGREGATION_QUERY:
        data = result.value
        agg_type = data.get("aggregation_type", "sum")
        agg_result = data.get("result", 0)
        formatted_value = round(agg_result, 1)
        formatted_str = format_value_with_unit(agg_result, unit)
        periods = data.get("periods", [])
        answer = f"The {agg_type} of {metric_display} across {len(periods)} periods is {formatted_str}"
        return answer, formatted_value

    elif parsed.intent == QueryIntent.BREAKDOWN_QUERY:
        data = result.value
        breakdown = data.get("breakdown", {})
        period = data.get("period", parsed.resolved_period)
        parts = []
        for metric, value in breakdown.items():
            display = metric.replace('_', ' ').title()
            parts.append(f"{display}: {format_value_with_unit(value, unit)}")
        answer = f"Breakdown for {period}: {', '.join(parts)}" if parts else f"Breakdown for {period} (no data)"
        return answer, data

    # Default
    formatted_value = result.value
    formatted_str = format_value_with_unit(formatted_value, unit) if isinstance(formatted_value, (int, float)) else str(formatted_value)
    answer = f"{metric_display} for {parsed.resolved_period} was {formatted_str}"
    return answer, formatted_value
