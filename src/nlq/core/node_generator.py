"""
Node generation for Galaxy visualization.

Generates IntentNode objects for different query types:
- Point queries: Primary node + related + context
- Ambiguous queries: Multiple candidates + context
- Comparison queries: Both period nodes + context
- Aggregation queries: Result node + component nodes
- Breakdown queries: All component nodes

All data is fetched from DCL.
"""

from typing import Any, List, Optional

from src.nlq.core.confidence import bounded_confidence
from src.nlq.core.semantic_labels import get_semantic_label
from src.nlq.knowledge.display import get_display_name, get_domain
from src.nlq.knowledge.quality import get_data_quality, get_freshness
from src.nlq.knowledge.relations import get_context_metrics, get_related_metrics
from src.nlq.knowledge.schema import get_metric_unit, is_additive_metric
from src.nlq.models.response import (
    AmbiguityType,
    Domain,
    IntentNode,
    MatchType,
)


def _query_dcl_value(metric: str, period: str) -> Optional[Any]:
    """Query a metric value from DCL.

    When DCL returns multiple data points (e.g. 4 quarters for an annual
    query), this function aggregates correctly:
    - Additive metrics (revenue, counts): summed
    - Non-additive metrics (pct, ratio, score, days): averaged
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client
    dcl_client = get_semantic_client()

    from src.nlq.config import get_tenant_id
    result = dcl_client.query(metric=metric, time_range={"period": period}, tenant_id=get_tenant_id())
    if result.get("error"):
        return None
    data = result.get("data", [])
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], dict) and "value" in data[0]:
            vals = [d.get("value", 0) for d in data if d.get("value") is not None]
            if not vals:
                return None
            if is_additive_metric(metric):
                return sum(vals)
            else:
                return sum(vals) / len(vals)
        return data[-1] if data else None
    elif isinstance(data, (int, float)):
        return data
    return None


def format_value(metric: str, value: Any) -> str:
    """Format a metric value for display based on its unit type."""
    if value is None:
        return "N/A"

    # Guard against non-numeric values (e.g. dicts from breakdown queries)
    if not isinstance(value, (int, float)):
        return str(value)

    unit = get_metric_unit(metric)

    # Percentage
    if unit == "%":
        return f"{round(value, 1)}%"
    # Currency
    elif unit == "USD millions":
        return f"${round(value, 1)}M"
    elif unit == "USD":
        return f"${round(value, 2):,.2f}"
    elif unit == "millions/month":
        return f"${round(value, 2)}M/mo"
    # Time
    elif unit == "days":
        return f"{round(value, 1)} days"
    elif unit == "hours":
        return f"{round(value, 1)} hours"
    elif unit == "months":
        return f"{round(value, 1)} months"
    # Counts
    elif unit == "people":
        return f"{int(value):,} people"
    elif unit == "customers":
        return f"{int(value):,} customers"
    elif unit == "tickets":
        return f"{int(value):,} tickets"
    elif unit == "bugs":
        return f"{int(value):,} bugs"
    elif unit == "vulnerabilities":
        return f"{int(value):,} vulnerabilities"
    elif unit == "incidents":
        return f"{int(value):,} incidents"
    elif unit == "deploys":
        return f"{int(value):,} deploys"
    elif unit == "features":
        return f"{int(value):,} features"
    elif unit == "points":
        return f"{int(value):,} points"
    # Scores and ratios
    elif unit == "score":
        return f"{round(value, 2)}"
    elif unit == "x":
        return f"{round(value, 2)}x"
    # Default: just show the number
    else:
        return f"{round(value, 2)}"


def generate_nodes_for_point_query(
    metric: str,
    value: Any,
    period: str,
) -> List[IntentNode]:
    """
    Generate nodes for a direct point query.

    Creates:
    - Primary node (EXACT, inner ring)
    - Related nodes (POTENTIAL, middle ring)
    - Context nodes (HYPOTHESIS, outer ring)

    Args:
        metric: The queried metric
        value: The metric value
        period: The time period

    Returns:
        List of IntentNode objects
    """
    nodes = []
    data_quality = get_data_quality(metric)
    freshness = get_freshness(metric)

    # Primary node (EXACT match, inner ring)
    primary_confidence = 0.95
    nodes.append(IntentNode(
        id=f"{metric}-primary",
        metric=metric,
        display_name=get_display_name(metric),
        match_type=MatchType.EXACT,
        domain=get_domain(metric),
        confidence=primary_confidence,
        data_quality=data_quality,
        freshness=freshness,
        value=value,
        formatted_value=format_value(metric, value),
        period=period,
        rationale="Direct answer",
        semantic_label=get_semantic_label(primary_confidence, MatchType.EXACT)
    ))

    # Related nodes (POTENTIAL, middle ring)
    related_metrics = get_related_metrics(metric, limit=3)
    for i, related in enumerate(related_metrics):
        related_value = _query_dcl_value(related, period)
        rel_confidence = bounded_confidence(0.70 - (i * 0.05))
        rel_quality = data_quality * 0.9

        nodes.append(IntentNode(
            id=f"{related}-related-{i}",
            metric=related,
            display_name=get_display_name(related),
            match_type=MatchType.POTENTIAL,
            domain=get_domain(related),
            confidence=rel_confidence,
            data_quality=rel_quality,
            freshness=get_freshness(related),
            value=related_value,
            formatted_value=format_value(related, related_value),
            period=period,
            rationale="Related metric",
            semantic_label=get_semantic_label(rel_confidence, MatchType.POTENTIAL)
        ))

    # Context nodes (HYPOTHESIS, outer ring)
    context_metrics = get_context_metrics(metric, limit=2)
    for i, ctx in enumerate(context_metrics):
        ctx_value = _query_dcl_value(ctx, period)
        ctx_confidence = bounded_confidence(0.45 - (i * 0.10))
        ctx_quality = data_quality * 0.8

        nodes.append(IntentNode(
            id=f"{ctx}-context-{i}",
            metric=ctx,
            display_name=get_display_name(ctx),
            match_type=MatchType.HYPOTHESIS,
            domain=get_domain(ctx),
            confidence=ctx_confidence,
            data_quality=ctx_quality,
            freshness=get_freshness(ctx),
            value=ctx_value,
            formatted_value=format_value(ctx, ctx_value),
            period=period,
            rationale="Additional context",
            semantic_label=get_semantic_label(ctx_confidence, MatchType.HYPOTHESIS)
        ))

    return nodes


def generate_nodes_for_ambiguous_query(
    ambiguity_type: AmbiguityType,
    candidates: List[str],
    period: str,
) -> List[IntentNode]:
    """
    Generate nodes for an ambiguous query.

    Different ambiguity types produce different node configurations:
    - VAGUE_METRIC: All candidates as POTENTIAL (no single EXACT)
    - BROAD_REQUEST: All candidates as EXACT
    - NOT_APPLICABLE: N/A as HYPOTHESIS, alternative as POTENTIAL

    Args:
        ambiguity_type: The type of ambiguity
        candidates: List of candidate metrics
        period: The time period

    Returns:
        List of IntentNode objects
    """
    nodes = []

    if ambiguity_type == AmbiguityType.VAGUE_METRIC:
        # Multiple candidates, all POTENTIAL (no single EXACT)
        for i, metric in enumerate(candidates):
            value = _query_dcl_value(metric, period)
            confidence = 0.80  # All equal confidence

            nodes.append(IntentNode(
                id=f"{metric}-candidate-{i}",
                metric=metric,
                display_name=get_display_name(metric),
                match_type=MatchType.POTENTIAL,
                domain=get_domain(metric),
                confidence=confidence,
                data_quality=get_data_quality(metric),
                freshness=get_freshness(metric),
                value=value,
                formatted_value=format_value(metric, value),
                period=period,
                rationale="Possible interpretation",
                semantic_label="Likely"
            ))

        # Add context nodes for outer ring
        if candidates:
            context_metrics = get_context_metrics(candidates[0], limit=2)
            for i, ctx in enumerate(context_metrics):
                ctx_value = _query_dcl_value(ctx, period)
                ctx_confidence = bounded_confidence(0.45 - (i * 0.05))

                nodes.append(IntentNode(
                    id=f"{ctx}-context-{i}",
                    metric=ctx,
                    display_name=get_display_name(ctx),
                    match_type=MatchType.HYPOTHESIS,
                    domain=get_domain(ctx),
                    confidence=ctx_confidence,
                    data_quality=get_data_quality(ctx) * 0.8,
                    freshness=get_freshness(ctx),
                    value=ctx_value,
                    formatted_value=format_value(ctx, ctx_value),
                    period=period,
                    rationale="Additional context",
                    semantic_label=get_semantic_label(ctx_confidence, MatchType.HYPOTHESIS)
                ))

    elif ambiguity_type == AmbiguityType.BROAD_REQUEST:
        # Multiple metrics, all EXACT (user asked for everything)
        for i, metric in enumerate(candidates):
            value = _query_dcl_value(metric, period)
            conf = bounded_confidence(0.95 - (i * 0.03))

            nodes.append(IntentNode(
                id=f"{metric}-{i}",
                metric=metric,
                display_name=get_display_name(metric),
                match_type=MatchType.EXACT,
                domain=get_domain(metric),
                confidence=conf,
                data_quality=get_data_quality(metric),
                freshness=get_freshness(metric),
                value=value,
                formatted_value=format_value(metric, value),
                period=period,
                rationale="Requested metric",
                semantic_label="Direct Answer"
            ))

    elif ambiguity_type == AmbiguityType.BURN_RATE:
        # Burn rate applies but profitable companies don't report discretely
        # Show COGS and SG&A as the actual cost metrics
        for i, metric in enumerate(candidates):  # candidates are ["cogs", "sga"]
            value = _query_dcl_value(metric, period)
            # Both are EXACT matches since they directly answer what "burn rate" means for profitable co
            match_type = MatchType.EXACT
            conf = bounded_confidence(0.85 - (i * 0.05))
            nodes.append(IntentNode(
                id=f"{metric}-burn-{i}",
                metric=metric,
                display_name=get_display_name(metric),
                match_type=match_type,
                domain=Domain.FINANCE,
                confidence=conf,
                data_quality=get_data_quality(metric),
                freshness=get_freshness(metric),
                value=value,
                formatted_value=format_value(metric, value),
                period=period,
                rationale="Cost component (burn rate tracked via COGS/SG&A for profitable companies)",
                semantic_label="Direct Answer"
            ))

        # Add a context node explaining the situation
        nodes.append(IntentNode(
            id="burn-rate-context",
            metric="burn_rate",
            display_name="Burn Rate",
            match_type=MatchType.HYPOTHESIS,
            domain=Domain.FINANCE,
            confidence=0.70,
            data_quality=0.0,
            freshness="N/A",
            value=None,
            formatted_value="Not Reported Discretely",
            period=period,
            rationale="Profitable companies track costs via COGS/SG&A, not burn rate",
            semantic_label="Context"
        ))

    else:
        # Default: Primary candidate as EXACT, rest as POTENTIAL
        for i, metric in enumerate(candidates):
            value = _query_dcl_value(metric, period)
            match_type = MatchType.EXACT if i == 0 else MatchType.POTENTIAL
            confidence = 0.90 if i == 0 else bounded_confidence(0.75 - (i * 0.05))

            nodes.append(IntentNode(
                id=f"{metric}-{i}",
                metric=metric,
                display_name=get_display_name(metric),
                match_type=match_type,
                domain=get_domain(metric),
                confidence=confidence,
                data_quality=get_data_quality(metric),
                freshness=get_freshness(metric),
                value=value,
                formatted_value=format_value(metric, value),
                period=period,
                rationale="Best interpretation" if i == 0 else "Alternative",
                semantic_label=get_semantic_label(confidence, match_type)
            ))

    return nodes


def generate_nodes_for_comparison_query(
    metric: str,
    period1: str,
    value1: Any,
    period2: str,
    value2: Any,
    difference: float,
    pct_change: Optional[float],
) -> List[IntentNode]:
    """
    Generate nodes for a comparison query.

    Creates:
    - Two primary nodes (EXACT) for each period
    - Related nodes (POTENTIAL) for context

    Args:
        metric: The compared metric
        period1: First period (current)
        value1: Value for period1
        period2: Second period (prior)
        value2: Value for period2
        difference: Absolute difference
        pct_change: Percentage change

    Returns:
        List of IntentNode objects
    """
    nodes = []
    data_quality = get_data_quality(metric)
    freshness = get_freshness(metric)

    # Current period node (EXACT)
    nodes.append(IntentNode(
        id=f"{metric}-{period1}",
        metric=metric,
        display_name=f"{get_display_name(metric)} ({period1})",
        match_type=MatchType.EXACT,
        domain=get_domain(metric),
        confidence=0.95,
        data_quality=data_quality,
        freshness=freshness,
        value=value1,
        formatted_value=format_value(metric, value1),
        period=period1,
        rationale="Current period value",
        semantic_label="Exact Match"
    ))

    # Prior period node (EXACT)
    nodes.append(IntentNode(
        id=f"{metric}-{period2}",
        metric=metric,
        display_name=f"{get_display_name(metric)} ({period2})",
        match_type=MatchType.EXACT,
        domain=get_domain(metric),
        confidence=0.95,
        data_quality=data_quality,
        freshness=freshness,
        value=value2,
        formatted_value=format_value(metric, value2),
        period=period2,
        rationale="Prior period value",
        semantic_label="Exact Match"
    ))

    # Change node (POTENTIAL)
    change_display = f"{pct_change:+.1f}%" if pct_change else f"${difference:+.1f}M"
    nodes.append(IntentNode(
        id=f"{metric}-change",
        metric=f"{metric}_change",
        display_name="Change",
        match_type=MatchType.POTENTIAL,
        domain=get_domain(metric),
        confidence=0.90,
        data_quality=data_quality,
        freshness=freshness,
        value=pct_change or difference,
        formatted_value=change_display,
        period=f"{period2} to {period1}",
        rationale="Calculated change",
        semantic_label="Likely"
    ))

    # Related context nodes (HYPOTHESIS)
    related_metrics = get_related_metrics(metric, limit=2)
    for i, related in enumerate(related_metrics):
        rel_value = _query_dcl_value(related, period1)
        ctx_confidence = bounded_confidence(0.45 - (i * 0.10))

        nodes.append(IntentNode(
            id=f"{related}-context-{i}",
            metric=related,
            display_name=get_display_name(related),
            match_type=MatchType.HYPOTHESIS,
            domain=get_domain(related),
            confidence=ctx_confidence,
            data_quality=get_data_quality(related) * 0.8,
            freshness=get_freshness(related),
            value=rel_value,
            formatted_value=format_value(related, rel_value),
            period=period1,
            rationale="Related context",
            semantic_label=get_semantic_label(ctx_confidence, MatchType.HYPOTHESIS)
        ))

    return nodes


def generate_nodes_for_aggregation_query(
    metric: str,
    aggregation_type: str,
    result: float,
    periods: List[str],
    values: List[float],
) -> List[IntentNode]:
    """
    Generate nodes for an aggregation query.

    Creates:
    - Result node (EXACT)
    - Component nodes for each period (POTENTIAL)
    - Context nodes (HYPOTHESIS)

    Args:
        metric: The aggregated metric
        aggregation_type: "sum" or "average"
        result: The aggregated result
        periods: List of periods
        values: Values for each period

    Returns:
        List of IntentNode objects
    """
    nodes = []
    data_quality = get_data_quality(metric)

    # Result node (EXACT)
    agg_label = "Total" if aggregation_type == "sum" else "Average"
    period_range = f"{periods[0]} - {periods[-1]}" if len(periods) > 1 else periods[0]

    nodes.append(IntentNode(
        id=f"{metric}-{aggregation_type}",
        metric=metric,
        display_name=f"{agg_label} {get_display_name(metric)}",
        match_type=MatchType.EXACT,
        domain=get_domain(metric),
        confidence=0.95,
        data_quality=data_quality,
        freshness=get_freshness(metric),
        value=result,
        formatted_value=format_value(metric, result),
        period=period_range,
        rationale=f"{agg_label} of {len(periods)} periods",
        semantic_label="Exact Match"
    ))

    # Component nodes (POTENTIAL)
    for i, (period, value) in enumerate(zip(periods, values)):
        comp_confidence = bounded_confidence(0.75 - (i * 0.03))

        nodes.append(IntentNode(
            id=f"{metric}-{period}",
            metric=metric,
            display_name=f"{get_display_name(metric)} ({period})",
            match_type=MatchType.POTENTIAL,
            domain=get_domain(metric),
            confidence=comp_confidence,
            data_quality=data_quality,
            freshness=get_freshness(metric),
            value=value,
            formatted_value=format_value(metric, value),
            period=period,
            rationale="Component value",
            semantic_label=get_semantic_label(comp_confidence, MatchType.POTENTIAL)
        ))

    return nodes


def generate_nodes_for_breakdown_query(
    breakdown: dict,
    period: str,
) -> List[IntentNode]:
    """
    Generate nodes for a breakdown query.

    Creates:
    - One node for each breakdown component (EXACT)
    - Total node if applicable (EXACT)
    - Context nodes (HYPOTHESIS)

    Args:
        breakdown: Dict of metric -> value
        period: The time period

    Returns:
        List of IntentNode objects
    """
    nodes = []

    # Create nodes for each breakdown component (all EXACT)
    for i, (metric, value) in enumerate(breakdown.items()):
        confidence = bounded_confidence(0.95 - (i * 0.02))

        nodes.append(IntentNode(
            id=f"{metric}-breakdown-{i}",
            metric=metric,
            display_name=get_display_name(metric),
            match_type=MatchType.EXACT,
            domain=get_domain(metric),
            confidence=confidence,
            data_quality=get_data_quality(metric),
            freshness=get_freshness(metric),
            value=value,
            formatted_value=format_value(metric, value),
            period=period,
            rationale="Breakdown component",
            semantic_label=get_semantic_label(confidence, MatchType.EXACT)
        ))

    # Add context nodes based on first metric
    if breakdown:
        first_metric = list(breakdown.keys())[0]
        context_metrics = get_context_metrics(first_metric, limit=2)
        for i, ctx in enumerate(context_metrics):
            ctx_value = _query_dcl_value(ctx, period)
            ctx_confidence = bounded_confidence(0.45 - (i * 0.10))

            nodes.append(IntentNode(
                id=f"{ctx}-context-{i}",
                metric=ctx,
                display_name=get_display_name(ctx),
                match_type=MatchType.HYPOTHESIS,
                domain=get_domain(ctx),
                confidence=ctx_confidence,
                data_quality=get_data_quality(ctx) * 0.8,
                freshness=get_freshness(ctx),
                value=ctx_value,
                formatted_value=format_value(ctx, ctx_value),
                period=period,
                rationale="Additional context",
                semantic_label=get_semantic_label(ctx_confidence, MatchType.HYPOTHESIS)
            ))

    return nodes


def calculate_overall_metrics(nodes: List[IntentNode]) -> tuple:
    """
    Calculate overall confidence and data quality from nodes.

    Args:
        nodes: List of IntentNode objects

    Returns:
        Tuple of (overall_confidence, overall_data_quality)
    """
    if not nodes:
        return 0.0, 0.0

    # Weight by match type
    weights = {
        MatchType.EXACT: 1.0,
        MatchType.POTENTIAL: 0.5,
        MatchType.HYPOTHESIS: 0.25,
    }

    total_weight = 0.0
    weighted_confidence = 0.0
    weighted_quality = 0.0

    for node in nodes:
        weight = weights.get(node.match_type, 0.5)
        total_weight += weight
        weighted_confidence += node.confidence * weight
        weighted_quality += node.data_quality * weight

    if total_weight == 0:
        return 0.0, 0.0

    return (
        bounded_confidence(weighted_confidence / total_weight),
        bounded_confidence(weighted_quality / total_weight)
    )
