"""
Shared query processing helpers for NLQ API.

This module consolidates duplicated logic between /query and /query/galaxy endpoints.
Both endpoints share the same core query processing logic, differing only in response format.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from src.nlq.models.response import Domain, MatchType, IntentMapResponse, IntentNode, NLQResponse
from src.nlq.knowledge.display import get_display_name
from src.nlq.knowledge.schema import get_metric_unit
from src.nlq.core.personality import detect_persona_from_metric, detect_persona_from_question
from src.nlq.core.dates import current_year, current_quarter


@dataclass
class SimpleMetricResult:
    """Core result from a simple metric query."""
    metric: str
    value: float
    formatted_value: str
    unit: str
    display_name: str
    domain: Domain
    answer: str
    period: str = field(default_factory=current_quarter)
    data_quality: float = 1.0  # From DCL metadata.quality_score
    freshness: str = "0h"  # From DCL provenance[].freshness
    source: str = "dcl"  # "dcl" when from live DCL
    run_provenance: Optional[Dict[str, Any]] = None  # DCL run provenance for Trust Badge
    data_source: Optional[str] = None  # "live" or "dcl"
    data_source_reason: Optional[str] = None  # Why fallback occurred (only when demo)


@dataclass
class GuidedDiscoveryResult:
    """Core result from a guided discovery query."""
    domain_name: str
    domain: Domain
    metrics: List[str]
    response_text: str


@dataclass
class MissingDataResult:
    """Core result when query asks about non-existent data."""
    response_text: str


@dataclass
class IngestStatusResult:
    """Core result from an ingest/infrastructure status query."""
    response_text: str
    sources: List[str]
    tenants: List[str]
    total_rows: int
    pipe_count: int
    available: bool


def determine_domain(metric: str) -> Domain:
    """Determine the domain for a metric."""
    if metric in ["pipeline", "win_rate_pct", "quota_attainment_pct", "sales_cycle_days"]:
        return Domain.GROWTH
    elif metric in ["headcount"]:
        return Domain.PEOPLE
    elif metric in ["customer_count", "nrr", "churn_rate_pct"]:
        return Domain.OPS
    return Domain.FINANCE


def determine_domain_from_name(domain_name: str) -> Domain:
    """Determine domain enum from domain name string."""
    if domain_name == "customer":
        return Domain.OPS
    elif domain_name == "sales":
        return Domain.GROWTH
    return Domain.FINANCE


# =============================================================================
# RESPONSE ADAPTERS - Convert shared results to endpoint-specific responses
# =============================================================================

def simple_metric_to_nlq_response(result: SimpleMetricResult) -> NLQResponse:
    """Convert SimpleMetricResult to NLQResponse for /query endpoint."""
    return NLQResponse(
        success=True,
        answer=result.answer,
        value=result.value,
        unit=result.unit,
        confidence=0.95,
        parsed_intent="POINT_QUERY",
        resolved_metric=result.metric,
        resolved_period=result.period,
        response_type="text",
        data_source=result.data_source,
        provenance=result.run_provenance,
    )


def simple_metric_to_galaxy_response(result: SimpleMetricResult, question: str) -> IntentMapResponse:
    """Convert SimpleMetricResult to IntentMapResponse for /query/galaxy endpoint."""
    node_id = f"{result.metric}_1"
    # Detect persona from metric first, then from question, fallback to CFO
    persona = detect_persona_from_metric(result.metric) or detect_persona_from_question(question) or "CFO"

    # Extract source system from run provenance if available
    source_system = None
    if result.run_provenance and result.run_provenance.get("source_systems"):
        source_system = ", ".join(result.run_provenance["source_systems"])

    return IntentMapResponse(
        query=question,
        query_type="POINT_QUERY",
        ambiguity_type=None,
        persona=persona,
        overall_confidence=0.95,
        overall_data_quality=result.data_quality,
        node_count=1,
        nodes=[IntentNode(
            id=node_id,
            metric=result.metric,
            display_name=result.display_name,
            match_type=MatchType.EXACT,
            domain=result.domain,
            confidence=0.95,
            data_quality=result.data_quality,
            freshness=result.freshness,
            value=result.value,
            formatted_value=result.formatted_value,
            period=current_year(),
            semantic_label="Direct Answer",
            source_system=source_system,
        )],
        primary_node_id=node_id,
        primary_answer=result.answer,
        text_response=result.answer,
        needs_clarification=False,
        clarification_prompt=None,
        provenance=result.run_provenance,
        data_source=result.data_source,
    )


def guided_discovery_to_nlq_response(result: GuidedDiscoveryResult) -> NLQResponse:
    """Convert GuidedDiscoveryResult to NLQResponse for /query endpoint."""
    return NLQResponse(
        success=True,
        answer=result.response_text,
        value=None,
        unit=None,
        confidence=0.9,
        parsed_intent="GUIDED_DISCOVERY",
        resolved_metric=None,
        resolved_period=current_year(),
        response_type="text",
    )


def guided_discovery_to_galaxy_response(result: GuidedDiscoveryResult, question: str) -> IntentMapResponse:
    """Convert GuidedDiscoveryResult to IntentMapResponse for /query/galaxy endpoint."""
    nodes = []
    for metric in result.metrics:
        display_name = get_display_name(metric)
        nodes.append(IntentNode(
            id=f"discovery_{metric}",
            metric=metric,
            display_name=display_name,
            match_type=MatchType.POTENTIAL,
            domain=result.domain,
            confidence=0.85,
            data_quality=1.0,
            freshness="0h",
            value=None,
            formatted_value=None,
            period=current_year(),
            semantic_label="Available Metric",
        ))

    return IntentMapResponse(
        query=question,
        query_type="GUIDED_DISCOVERY",
        ambiguity_type=None,
        persona=detect_persona_from_question(question) or "CFO",
        overall_confidence=0.9,
        overall_data_quality=1.0,
        node_count=len(nodes),
        nodes=nodes,
        primary_node_id=nodes[0].id if nodes else None,
        primary_answer=result.response_text,
        text_response=result.response_text,
        needs_clarification=False,
        clarification_prompt=None,
    )


def missing_data_to_nlq_response(result: MissingDataResult) -> NLQResponse:
    """Convert MissingDataResult to NLQResponse for /query endpoint."""
    return NLQResponse(
        success=True,
        answer=result.response_text,
        value=None,
        unit=None,
        confidence=0.8,
        parsed_intent="MISSING_DATA",
        resolved_metric=None,
        resolved_period=None,
        response_type="text",
    )


def missing_data_to_galaxy_response(result: MissingDataResult, question: str) -> IntentMapResponse:
    """Convert MissingDataResult to IntentMapResponse for /query/galaxy endpoint."""
    return IntentMapResponse(
        query=question,
        query_type="MISSING_DATA",
        ambiguity_type=None,
        persona=detect_persona_from_question(question) or "CFO",
        overall_confidence=0.8,
        overall_data_quality=0.0,
        node_count=0,
        nodes=[],
        primary_node_id=None,
        primary_answer=result.response_text,
        text_response=result.response_text,
        needs_clarification=False,
        clarification_prompt=None,
    )


def people_response_to_galaxy(people_response: NLQResponse, question: str) -> IntentMapResponse:
    """Convert NLQResponse from people query to IntentMapResponse for Galaxy view."""
    nodes = []
    if people_response.value is not None:
        nodes.append(IntentNode(
            id="people_1",
            metric=people_response.resolved_metric or "people",
            display_name=people_response.resolved_metric or "People",
            match_type=MatchType.EXACT,
            domain=Domain.PEOPLE,
            confidence=people_response.confidence,
            data_quality=1.0,
            freshness="0h",
            value=people_response.value,
            formatted_value=f"{people_response.value} {people_response.unit}" if people_response.value else None,
            period=people_response.resolved_period or "",
            semantic_label="People/HR",
        ))

    return IntentMapResponse(
        query=question,
        query_type="PEOPLE",
        ambiguity_type=None,
        persona="People",
        overall_confidence=people_response.confidence,
        overall_data_quality=1.0,
        node_count=len(nodes),
        nodes=nodes,
        primary_node_id="people_1" if nodes else None,
        primary_answer=people_response.answer,
        text_response=people_response.answer,
        needs_clarification=False,
        clarification_prompt=None,
    )


def off_topic_to_nlq_response(off_topic_text: str) -> NLQResponse:
    """Convert off-topic response to NLQResponse."""
    return NLQResponse(
        success=True,
        answer=off_topic_text,
        value=None,
        unit=None,
        confidence=1.0,
        parsed_intent="OFF_TOPIC",
        resolved_metric=None,
        resolved_period=None,
    )


def ingest_status_to_nlq_response(result: IngestStatusResult) -> NLQResponse:
    """Convert IngestStatusResult to NLQResponse for /query endpoint."""
    return NLQResponse(
        success=True,
        answer=result.response_text,
        value=None,
        unit=None,
        confidence=0.95,
        parsed_intent="INGEST_STATUS",
        resolved_metric=None,
        resolved_period=None,
        response_type="text",
    )


def ingest_status_to_galaxy_response(result: IngestStatusResult, question: str) -> IntentMapResponse:
    """Convert IngestStatusResult to IntentMapResponse for /query/galaxy endpoint."""
    persona = detect_persona_from_question(question) or "CTO"
    nodes = []
    # Create a node for each connected source so Galaxy view shows them
    for source in result.sources:
        nodes.append(IntentNode(
            id=f"ingest_{source.lower().replace(' ', '_')}",
            metric=source.lower().replace(" ", "_"),
            display_name=source,
            match_type=MatchType.EXACT,
            domain=Domain.OPS,
            confidence=0.95,
            data_quality=1.0,
            freshness="0h",
            value=None,
            formatted_value="Connected",
            period="live",
            semantic_label="Data Source",
            source_system=source,
        ))

    return IntentMapResponse(
        query=question,
        query_type="INGEST_STATUS",
        ambiguity_type=None,
        persona=persona,
        overall_confidence=0.95,
        overall_data_quality=1.0,
        node_count=len(nodes),
        nodes=nodes,
        primary_node_id=nodes[0].id if nodes else None,
        primary_answer=result.response_text,
        text_response=result.response_text,
        needs_clarification=False,
        clarification_prompt=None,
    )


def breakdown_to_galaxy_response(result: NLQResponse, question: str) -> IntentMapResponse:
    """Convert NLQResponse breakdown result to IntentMapResponse for /query/galaxy endpoint."""
    persona = (
        detect_persona_from_metric(result.resolved_metric)
        or detect_persona_from_question(question)
        or "CFO"
    )

    nodes = []
    # If dashboard_data exists, create a node per breakdown item
    if result.dashboard_data:
        for widget_data in result.dashboard_data.values():
            series_list = widget_data.get("series", [])
            for series in series_list:
                for item in series.get("data", []):
                    label = item.get("label", "")
                    value = item.get("value")
                    node_id = f"bd_{label.lower().replace(' ', '_')}"
                    metric = result.resolved_metric or "unknown"
                    unit = get_metric_unit(metric) if result.resolved_metric else "$"
                    if unit == "%":
                        fmt = f"{round(value, 1)}%" if value is not None else "N/A"
                    else:
                        fmt = f"${round(value, 1)}M" if value is not None else "N/A"
                    nodes.append(IntentNode(
                        id=node_id,
                        metric=metric,
                        display_name=f"{label}",
                        match_type=MatchType.EXACT,
                        domain=determine_domain(metric),
                        confidence=0.9,
                        data_quality=1.0,
                        freshness="0h",
                        value=value,
                        formatted_value=fmt,
                        period=result.resolved_period or current_quarter(),
                        semantic_label=label,
                    ))

    # Fallback: no dashboard_data (graph resolution or error paths) → single text node
    if not nodes:
        node_id = f"bd_{result.resolved_metric or 'text'}_1"
        nodes.append(IntentNode(
            id=node_id,
            metric=result.resolved_metric or "unknown",
            display_name=get_display_name(result.resolved_metric) if result.resolved_metric else "Breakdown",
            match_type=MatchType.EXACT,
            domain=determine_domain(result.resolved_metric or "unknown"),
            confidence=result.confidence or 0.8,
            data_quality=1.0,
            freshness="0h",
            value=None,
            formatted_value=None,
            period=result.resolved_period or current_quarter(),
            semantic_label="Breakdown",
        ))

    return IntentMapResponse(
        query=question,
        query_type="BREAKDOWN",
        ambiguity_type=None,
        persona=persona,
        overall_confidence=result.confidence or 0.9,
        overall_data_quality=1.0,
        node_count=len(nodes),
        nodes=nodes,
        primary_node_id=nodes[0].id if nodes else None,
        primary_answer=result.answer,
        text_response=result.answer or "",
        needs_clarification=False,
        clarification_prompt=None,
        provenance=result.provenance if isinstance(result.provenance, dict) else None,
        data_source=result.data_source,
    )


def off_topic_to_galaxy_response(off_topic_text: str, question: str, persona: str) -> IntentMapResponse:
    """Convert off-topic response to IntentMapResponse for Galaxy view."""
    return IntentMapResponse(
        query=question,
        query_type="OFF_TOPIC",
        ambiguity_type=None,
        persona=persona,
        overall_confidence=1.0,
        overall_data_quality=1.0,
        node_count=0,
        nodes=[],
        primary_node_id=None,
        primary_answer=off_topic_text,
        text_response=off_topic_text,
        needs_clarification=False,
        clarification_prompt=None,
    )
