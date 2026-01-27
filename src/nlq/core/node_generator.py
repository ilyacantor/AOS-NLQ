"""
Node generation for Galaxy visualization.

Generates IntentNode objects for different query types:
- Point queries: Primary node + related + context
- Ambiguous queries: Multiple candidates + context
- Comparison queries: Both period nodes + context
- Aggregation queries: Result node + component nodes
- Breakdown queries: All component nodes
"""

from typing import Any, List, Optional

from src.nlq.core.confidence import bounded_confidence
from src.nlq.core.semantic_labels import get_semantic_label
from src.nlq.knowledge.display import get_display_name, get_domain
from src.nlq.knowledge.quality import get_data_quality, get_freshness
from src.nlq.knowledge.relations import get_context_metrics, get_related_metrics
from src.nlq.knowledge.schema import get_metric_unit
from src.nlq.models.response import (
    AmbiguityType,
    Domain,
    IntentNode,
    MatchType,
)


def format_value(metric: str, value: Any) -> str:
    """Format a metric value for display."""
    if value is None:
        return "N/A"

    unit = get_metric_unit(metric)
    if unit == "%":
        return f"{round(value, 1)}%"
    else:
        return f"${round(value, 1)}M"


def generate_nodes_for_point_query(
    metric: str,
    value: Any,
    period: str,
    fact_base: Any,
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
        fact_base: FactBase instance for fetching related values

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
        related_value = fact_base.query(related, period) if fact_base else None
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
        ctx_value = fact_base.query(ctx, period) if fact_base else None
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
    fact_base: Any,
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
        fact_base: FactBase instance for fetching values

    Returns:
        List of IntentNode objects
    """
    nodes = []

    if ambiguity_type == AmbiguityType.VAGUE_METRIC:
        # Multiple candidates, all POTENTIAL (no single EXACT)
        for i, metric in enumerate(candidates):
            value = fact_base.query(metric, period) if fact_base else None
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
                ctx_value = fact_base.query(ctx, period) if fact_base else None
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
            value = fact_base.query(metric, period) if fact_base else None
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

    elif ambiguity_type == AmbiguityType.NOT_APPLICABLE:
        # Primary is HYPOTHESIS (doesn't apply), alternative is POTENTIAL
        if candidates:
            nodes.append(IntentNode(
                id="not-applicable",
                metric="not_applicable",
                display_name=candidates[0] if candidates else "N/A",
                match_type=MatchType.HYPOTHESIS,
                domain=Domain.FINANCE,
                confidence=0.30,
                data_quality=0.0,
                freshness="N/A",
                value=None,
                formatted_value="Not Applicable",
                period=period,
                rationale="Concept doesn't apply to this company",
                semantic_label="Context"
            ))

            # Add alternative metric
            if len(candidates) > 1:
                alt_metric = candidates[1]
                alt_value = fact_base.query(alt_metric, period) if fact_base else None
                nodes.append(IntentNode(
                    id=f"{alt_metric}-alternative",
                    metric=alt_metric,
                    display_name=get_display_name(alt_metric),
                    match_type=MatchType.POTENTIAL,
                    domain=get_domain(alt_metric),
                    confidence=0.75,
                    data_quality=get_data_quality(alt_metric),
                    freshness=get_freshness(alt_metric),
                    value=alt_value,
                    formatted_value=format_value(alt_metric, alt_value),
                    period=period,
                    rationale="Relevant alternative",
                    semantic_label="Likely"
                ))

    else:
        # Default: Primary candidate as EXACT, rest as POTENTIAL
        for i, metric in enumerate(candidates):
            value = fact_base.query(metric, period) if fact_base else None
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
    fact_base: Any,
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
        fact_base: FactBase instance

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
        rel_value = fact_base.query(related, period1) if fact_base else None
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
    fact_base: Any,
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
        fact_base: FactBase instance

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
    fact_base: Any,
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
        fact_base: FactBase instance

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
            ctx_value = fact_base.query(ctx, period) if fact_base else None
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
